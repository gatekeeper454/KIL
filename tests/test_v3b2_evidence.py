from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest

from kil.v3b2_contracts import PRIVATE_MANIFEST_FIELDS, TRACKS
from kil.v3b2_evidence import (
    CLAIM_EXCLUSIONS,
    EvidenceError,
    PublicBoundaryError,
    SourceIdentity,
    VerifiedBundle,
    build_public_bundle,
    capture_source,
    join_nominal_evidence,
    project_foreign_profiles,
    publish_bundle,
    validate_public_projection,
    verify_bundle,
)


HEX_A = "a" * 64
HEX_B = "b" * 64


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def stat_mode(path: Path) -> int:
    return os.stat(path, follow_symlinks=False).st_mode & 0o777


class Reader:
    def __init__(self, payload: bytes, *, after: SourceIdentity | None = None):
        self.payload = payload
        self.expected = SourceIdentity("driver", "uid-1", "7", "container-1", len(payload), sha256(payload).hexdigest())
        self.after = after or self.expected
        self.calls = 0

    def identity(self) -> SourceIdentity:
        self.calls += 1
        return self.expected if self.calls == 1 else self.after

    def read(self, maximum: int) -> bytes:
        return self.payload[: maximum + 1]


def private_evidence(*, request_free: bool = False) -> dict[str, object]:
    cases = []
    attestations: list[dict[str, object]] = []
    expected = (("permit", 200, 1), ("permit", 200, 1), ("deny", 403, 0))
    if not request_free:
        for index, (track, outcome) in enumerate(zip(TRACKS, expected, strict=True)):
            decision, status, markers = outcome
            digest = sha256(f"{track}:{decision}".encode()).hexdigest()
            cases.append({"track": track, "request_id": "v3b1-central-request", "expected_decision": decision, "expected_http_status": status, "expected_target_markers": markers})
            records = {
                "driver": [{"track": track, "request_id": "v3b1-central-request", "attempt": 1, "decision": decision, "http_status": status, "decision_digest": digest}],
                "decision": [{"track": track, "request_id": "v3b1-central-request", "decision": decision, "decision_digest": digest}],
                "envoy": [{"track": track, "request_id": "v3b1-central-request", "decision_digest": digest, "upstream_attempted": decision == "permit", "upstream_status": status if decision == "permit" else None}],
                "target": ([{"track": track, "request_id": "v3b1-central-request", "marker": 1}] if markers else []),
            }
            for kind, items in records.items():
                attestations.append({"kind": kind, "track": track, "records": items})
    before = [
        {"name": "client-a", "status": "Running", "arch": "aarch64", "cpus": 2, "memory": 4, "disk": 20, "runtime": "docker"},
        {"name": "client-b", "status": "Stopped", "arch": "aarch64", "cpus": 4, "memory": 8, "disk": 40, "runtime": "containerd"},
    ]
    return {
        "schema_version": "kil.v3b2-private-manifest.v1",
        "run_id": "run-v3b2-001",
        "execution_nonce": "e" * 64,
        "source_commit": "c" * 40,
        "profile_sha256": HEX_B,
        "tool_identities": {"kind": "0.32.0"},
        "content_identities": {"calico_manifest_sha256": HEX_A},
        "expected_topology": {"namespaces": ["kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed"]},
        "expected_policy_graph": {"closed": True},
        "request_cases": cases,
        "runtime_identities": {
            "topology_attestation": {"closed": True},
            "policy_attestation": {"closed": True},
            "foreign_profiles_after": deepcopy(before),
            "global_context_after": "personal",
            "owned_teardown": {"cluster_absent": True, "profile_absent": True, "private_active_state_absent": True},
        },
        "source_attestations": attestations,
        "foreign_profiles_before": before,
        "global_context_before": "personal",
    }


class V3B2EvidenceTest(unittest.TestCase):
    def test_source_records_are_frozen_and_capture_is_stable_and_bounded(self):
        payload = canonical({"ok": True})
        reader = Reader(payload)
        captured = capture_source(reader, reader.expected, maximum=len(payload))
        self.assertEqual(captured.payload, payload)
        with self.assertRaises(FrozenInstanceError):
            captured.identity.logical_name = "changed"  # type: ignore[misc]
        drift = SourceIdentity("driver", "uid-1", "8", "container-1", len(payload), sha256(payload).hexdigest())
        with self.assertRaises(EvidenceError):
            capture_source(Reader(payload, after=drift), reader.expected)
        with self.assertRaises(EvidenceError):
            capture_source(Reader(payload + b"x"), Reader(payload + b"x").expected, maximum=len(payload))

    def test_malformed_capture_is_preserved_only_in_private_hash_bound_diagnostic(self):
        payload = b'{"partial":true}'
        reader = Reader(payload)
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "private" / "driver.raw"
            with self.assertRaises(EvidenceError):
                capture_source(reader, reader.expected, private_diagnostic_path=raw)
            self.assertEqual(raw.read_bytes(), payload)
            diagnostic = json.loads((raw.parent / "driver.raw.diagnostic.json").read_text())
            self.assertEqual(diagnostic["sha256"], sha256(payload).hexdigest())
            self.assertEqual(stat_mode(raw), 0o600)

    def test_nominal_tuple_and_target_cardinality_are_exact(self):
        bundle = build_public_bundle(private_evidence())
        self.assertEqual(
            tuple((item["decision"], item["http_status"], item["target_markers"]) for item in bundle["request_results"]),
            (("permit", 200, 1), ("permit", 200, 1), ("deny", 403, 0)),
        )
        mutated = private_evidence()
        mutated["source_attestations"][-1]["records"].append({"track": TRACKS[-1], "request_id": "v3b1-central-request", "marker": 1})  # type: ignore[index,union-attr]
        with self.assertRaises(EvidenceError):
            join_nominal_evidence(mutated)

    def test_permit_and_denial_joins_are_rederived(self):
        joins = join_nominal_evidence(private_evidence())
        self.assertEqual(len(joins), 3)
        self.assertTrue(all(join["decision_digest_equal"] for join in joins))
        self.assertFalse(joins[2]["envoy_upstream_attempted"])

    def test_retry_cross_track_and_repaired_digest_are_rejected(self):
        for mutate in ("retry", "cross_track", "digest"):
            evidence = private_evidence()
            driver = evidence["source_attestations"][0]["records"][0]  # type: ignore[index]
            if mutate == "retry":
                driver["attempt"] = 2
            elif mutate == "cross_track":
                driver["track"] = TRACKS[1]
            else:
                driver["decision_digest"] = "f" * 64
            with self.subTest(mutate=mutate), self.assertRaises(EvidenceError):
                join_nominal_evidence(evidence)

    def test_semantic_and_teardown_integer_boolean_coercions_are_rejected(self):
        for location, field, value in (
            (("request_cases", 2), "expected_target_markers", False),
            (("source_attestations", 0, "records", 0), "attempt", True),
            (("source_attestations", 3, "records", 0), "marker", True),
        ):
            evidence = private_evidence()
            target = evidence
            for part in location:
                target = target[part]  # type: ignore[index]
            target[field] = value  # type: ignore[index]
            with self.subTest(field=field), self.assertRaises(EvidenceError):
                join_nominal_evidence(evidence)
        evidence = private_evidence()
        evidence["runtime_identities"]["owned_teardown"]["cluster_absent"] = 1  # type: ignore[index]
        with self.assertRaises(EvidenceError):
            build_public_bundle(evidence)

    def test_request_free_bundle_is_diagnostic_and_contains_no_requests(self):
        bundle = build_public_bundle(private_evidence(request_free=True))
        self.assertEqual(bundle["result_class"], "diagnostic_request_free_kind_calico_readiness")
        self.assertEqual(bundle["promotion_status"], "not_promoted")
        self.assertEqual(bundle["request_results"], [])
        self.assertEqual(bundle["semantic_joins"], [])

    def test_public_projection_rejects_private_material_recursively(self):
        public = build_public_bundle(private_evidence())
        for value in ("/Users/name", "Bearer secret", "kil-private-nonce", "foreign-profile-name"):
            candidate = deepcopy(public)
            candidate["topology_attestation"] = {"nested": [{"value": value}]}
            with self.subTest(value=value), self.assertRaises(PublicBoundaryError):
                validate_public_projection(candidate)

    def test_foreign_profiles_are_keyed_sorted_and_bind_normalized_resources(self):
        evidence = private_evidence()
        projected = project_foreign_profiles(evidence["foreign_profiles_before"], evidence["runtime_identities"]["foreign_profiles_after"], b"private-key")  # type: ignore[index]
        self.assertTrue(projected["unchanged"])
        self.assertEqual(projected["before"], projected["after"])
        self.assertEqual(projected["before"], sorted(projected["before"], key=lambda item: item["pseudonym"]))
        self.assertNotIn("client-a", json.dumps(projected))
        changed = deepcopy(evidence)
        changed["runtime_identities"]["foreign_profiles_after"][0]["cpus"] = 9  # type: ignore[index]
        bundle = build_public_bundle(changed)
        self.assertFalse(bundle["foreign_profile_attestation"]["unchanged"])
        self.assertEqual(bundle["result_class"], "diagnostic_foreign_state_mismatch")

    def test_private_manifest_field_set_and_claims_are_exact(self):
        evidence = private_evidence()
        self.assertEqual(set(evidence), PRIVATE_MANIFEST_FIELDS)
        bundle = build_public_bundle(evidence)
        self.assertEqual(tuple(bundle["claim_exclusions"]), CLAIM_EXCLUSIONS)
        self.assertNotIn("e" * 64, json.dumps(bundle))

    def test_publication_and_verifier_reject_tree_and_semantic_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            published = publish_bundle(private_evidence(), root / "public")
            verified = verify_bundle(published)
            self.assertIsInstance(verified, VerifiedBundle)
            self.assertEqual(verified.schema_family, "v3b2-run")
            self.assertEqual(set(path.name for path in published.iterdir()), {
                "manifest.json", "requests.jsonl", "decisions.jsonl", "envoy.jsonl", "targets.jsonl", "kubernetes.jsonl", "policies.jsonl", "joins.jsonl", "summary.md", "live.html", "SHA256SUMS",
            })
            (published / "extra").write_text("x")
            with self.assertRaises(EvidenceError):
                verify_bundle(published)

    def test_verifier_rejects_replacement_after_semantic_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            published = publish_bundle(private_evidence(), root / "public")
            victim = published / "summary.md"
            def replace() -> None:
                victim.chmod(0o600)
                old = victim.with_name("summary.old")
                victim.rename(old)
                victim.write_bytes(old.read_bytes())
                old.unlink()
            with self.assertRaises(EvidenceError):
                verify_bundle(published, before_completion=replace)

    def test_wrong_order_duplicate_checksum_and_repaired_hash_drift_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            published = publish_bundle(private_evidence(), root / "public")
            requests = (published / "requests.jsonl").read_bytes().splitlines()
            (published / "requests.jsonl").chmod(0o600)
            (published / "requests.jsonl").write_bytes(b"\n".join(reversed(requests)) + b"\n")
            self._rewrite_sums(published)
            with self.assertRaises(EvidenceError):
                verify_bundle(published)

            published = publish_bundle(private_evidence(), root / "public2")
            sums = published / "SHA256SUMS"
            sums.chmod(0o600)
            sums.write_bytes(sums.read_bytes() + sums.read_bytes().splitlines(keepends=True)[0])
            with self.assertRaises(EvidenceError):
                verify_bundle(published)

    def test_missing_symlink_malformed_and_oversized_are_rejected(self):
        mutations = ("missing", "symlink", "malformed", "oversized")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published = publish_bundle(private_evidence(), root / "public")
                target = published / "requests.jsonl"
                target.chmod(0o600)
                if mutation == "missing":
                    target.unlink()
                elif mutation == "symlink":
                    target.unlink(); target.symlink_to(published / "decisions.jsonl")
                elif mutation == "malformed":
                    target.write_bytes(b"\xff\n"); self._rewrite_sums(published)
                else:
                    target.write_bytes(b" " * (8 * 1024 * 1024 + 1)); self._rewrite_sums(published)
                with self.assertRaises(EvidenceError):
                    verify_bundle(published)

    def test_v3b1_and_v3b2_dispatch_are_independent_and_hybrid_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            v3b2 = publish_bundle(private_evidence(), root / "public")
            self.assertEqual(verify_bundle(v3b2).schema_family, "v3b2-run")
            from tests.test_v3b1_local_envoy import published_presenter_bundle
            fixture_root = root / "v3b1-fixture"
            fixture_root.mkdir()
            v3b1 = published_presenter_bundle(fixture_root)
            self.assertEqual(verify_bundle(v3b1).schema_family, "v3b1")
            hybrid = json.loads((v3b2 / "manifest.json").read_text())
            hybrid["bundle_class"] = "v3b1"
            manifest = v3b2 / "manifest.json"; manifest.chmod(0o600); manifest.write_bytes(canonical(hybrid)); self._rewrite_sums(v3b2)
            with self.assertRaises(EvidenceError):
                verify_bundle(v3b2)

    @staticmethod
    def _rewrite_sums(bundle: Path) -> None:
        lines = []
        for path in sorted((path for path in bundle.iterdir() if path.name != "SHA256SUMS"), key=lambda path: path.name):
            lines.append(f"{sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
        sums = bundle / "SHA256SUMS"
        sums.chmod(0o600)
        sums.write_text("".join(lines), encoding="ascii")


if __name__ == "__main__":
    unittest.main()
