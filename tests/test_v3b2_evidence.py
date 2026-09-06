from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, FrozenInstanceError
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import kil.v3b2_evidence as evidence_module

from kil.v3b2_contracts import PRIVATE_MANIFEST_FIELDS, TRACKS
from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_manifests import (
    WorkloadIdentity,
    expected_object_keys,
    render_kind_config,
    render_objects,
)
from kil.v3b2_evidence import (
    CLAIM_EXCLUSIONS,
    CapturedSource,
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
ROOT = Path(__file__).resolve().parents[1]
PROFILE = V3B2Profile.load(ROOT / "deploy/kind/v3b2-profile.json")
RUN_ID = "v3b2-" + "1" * 64
KIL_IMAGE_ID = "sha256:" + "d" * 64
ENVOY_DIGEST = "docker.io/envoyproxy/envoy@sha256:" + "e" * 64


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
    from tests.test_v3b2_inventory import snapshot

    inventory = snapshot()
    workload = WorkloadIdentity(RUN_ID, KIL_IMAGE_ID, ENVOY_DIGEST)
    profile_sha = sha256((ROOT / "deploy/kind/v3b2-profile.json").read_bytes()).hexdigest()
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
    object_rows = [asdict(item) for item in inventory.objects]
    image_rows = [asdict(item) for item in inventory.pod_images]
    for image in image_rows:
        if image["image_role"] == "workload" and image["container"] == "driver":
            bound = next(
                item
                for item in object_rows
                if item["kind"] == "Pod"
                and item["namespace"] == image["namespace"]
                and item["name"] == "driver"
            )
            image["uid"] = bound["uid"]
            image["resource_version"] = bound["resource_version"]
    expected_topology = {
        "namespaces": list(inventory.namespaces),
        "object_keys": [
            list(item)
            for item in sorted((
                *expected_object_keys(PROFILE),
                ("v1", "Namespace", "", "kube-system"),
                ("apps/v1", "DaemonSet", "kube-system", "calico-node"),
                ("apps/v1", "Deployment", "kube-system", "calico-kube-controllers"),
            ))
        ],
        "pod_image_keys": [
            [item.image_role, item.container_type, item.namespace, item.container]
            for item in inventory.pod_images
        ],
        "endpoint_keys": [
            [item.namespace, item.service, item.port_name, item.protocol, item.port]
            for item in inventory.endpoints
        ],
        "calico_readiness": {
            "node_desired": 1, "node_ready": 1,
            "controller_desired": 1, "controller_ready": 1,
        },
    }
    expected_policy = {
        "edges": [
            {
                **asdict(item),
                "source_roles": list(item.source_roles),
                "destination_roles": list(item.destination_roles),
                "protocol_ports": [list(pair) for pair in item.protocol_ports],
            }
            for item in inventory.policy_graph
        ]
    }
    return {
        "schema_version": "kil.v3b2-private-manifest.v1",
        "run_id": RUN_ID,
        "execution_nonce": "9" * 64,
        "source_commit": "c" * 40,
        "profile_sha256": profile_sha,
        "tool_identities": {"kind": "0.32.0"},
        "content_identities": {
            "run_id": RUN_ID,
            "profile_sha256": profile_sha,
            "kind_config_sha256": sha256(render_kind_config(PROFILE)).hexdigest(),
            "objects_manifest_sha256": sha256(render_objects(PROFILE, workload)).hexdigest(),
            "calico_manifest_sha256": PROFILE.calico_manifest_sha256,
            "kind_node_image": PROFILE.kind_node_image,
            "calico_images": {name: image for name, image in PROFILE.calico_images},
            "kil_image_id": KIL_IMAGE_ID,
            "envoy_image_digest": ENVOY_DIGEST,
        },
        "expected_topology": expected_topology,
        "expected_policy_graph": expected_policy,
        "request_cases": cases,
        "runtime_identities": {
            "topology_attestation": {
                "cluster_incarnation_uid": inventory.cluster_incarnation_uid,
                "node_container_id": inventory.node_container_id,
                "namespaces": list(inventory.namespaces),
                "objects": object_rows,
                "pod_images": image_rows,
                "endpoints": [
                    {**asdict(item), "addresses": list(item.addresses)}
                    for item in inventory.endpoints
                ],
                "calico_readiness": {
                    "node_desired": inventory.calico_node_desired,
                    "node_ready": inventory.calico_node_ready,
                    "controller_desired": inventory.calico_controller_desired,
                    "controller_ready": inventory.calico_controller_ready,
                },
            },
            "policy_attestation": {
                "edges": [
                    {
                        **asdict(item),
                        "source_roles": list(item.source_roles),
                        "destination_roles": list(item.destination_roles),
                        "protocol_ports": [list(pair) for pair in item.protocol_ports],
                    }
                    for item in inventory.policy_graph
                ]
            },
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
            unit = Path(directory).resolve() / "private" / "driver-diagnostic"
            with self.assertRaises(EvidenceError):
                capture_source(reader, reader.expected, private_diagnostic_path=unit)
            raw = unit / "raw.bin"
            diagnostic = json.loads((unit / "diagnostic.json").read_text())
            self.assertEqual(raw.read_bytes(), payload)
            self.assertEqual(diagnostic["sha256"], sha256(payload).hexdigest())
            self.assertEqual(stat_mode(raw), 0o600)
            self.assertEqual(stat_mode(unit), 0o700)

    def test_private_diagnostic_rejects_invalid_and_symlinked_ancestry(self):
        payload = b'{"partial":true}'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            real = root / "real"
            real.mkdir(mode=0o700)
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)
            sentinel = real / "sentinel"
            sentinel.write_text("preserve")
            with self.assertRaises(EvidenceError):
                reader = Reader(payload)
                capture_source(reader, reader.expected, private_diagnostic_path=alias / "raw")
            self.assertEqual(sentinel.read_text(), "preserve")
            self.assertFalse((real / "raw").exists())
            with self.assertRaises(EvidenceError):
                reader = Reader(payload)
                capture_source(reader, reader.expected, private_diagnostic_path="bad")  # type: ignore[arg-type]
            with self.assertRaises(EvidenceError):
                evidence_module._persist_private_diagnostic(None, payload)  # type: ignore[arg-type]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            private = root / "private"
            private.mkdir(mode=0o700)
            moved = root / "moved"
            decoy = root / "decoy"
            decoy.mkdir(mode=0o700)
            sentinel = decoy / "sentinel"
            sentinel.write_text("preserve")
            original_write = evidence_module._write_regular_at
            calls = 0

            def retarget(directory_fd: int, name: str, data: bytes) -> None:
                nonlocal calls
                original_write(directory_fd, name, data)
                calls += 1
                if calls == 1:
                    private.rename(moved)
                    private.symlink_to(decoy, target_is_directory=True)

            reader = Reader(payload)
            with patch.object(evidence_module, "_write_regular_at", side_effect=retarget):
                with self.assertRaises(EvidenceError):
                    capture_source(
                        reader,
                        reader.expected,
                        private_diagnostic_path=private / "raw",
                    )
            self.assertEqual(sentinel.read_text(), "preserve")
            self.assertFalse((decoy / "raw").exists())
            self.assertFalse((moved / "raw").exists())

    def test_private_diagnostic_unit_is_absent_on_second_write_or_rename_failure(self):
        payload = b'{"partial":true}'
        for failure in ("second_write", "rename"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                private = root / "private"
                private.mkdir(mode=0o700)
                unit = private / "diagnostic-unit"
                reader = Reader(payload)
                if failure == "second_write":
                    original = evidence_module._write_regular_at
                    calls = 0

                    def fail_second(directory_fd: int, name: str, data: bytes) -> None:
                        nonlocal calls
                        calls += 1
                        if calls == 2:
                            raise OSError("private detail")
                        original(directory_fd, name, data)

                    context = patch.object(evidence_module, "_write_regular_at", side_effect=fail_second)
                else:
                    context = patch.object(
                        evidence_module,
                        "_rename_directory_exclusive",
                        side_effect=OSError("private detail"),
                    )
                with context, self.assertRaises(EvidenceError) as caught:
                    capture_source(reader, reader.expected, private_diagnostic_path=unit)
                self.assertNotIn("private detail", str(caught.exception))
                self.assertFalse(unit.exists())
                self.assertEqual(list(private.iterdir()), [])

    def test_private_diagnostic_exclusive_rename_preserves_raced_destination(self):
        payload = b'{"partial":true}'
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory).resolve() / "private"
            private.mkdir(mode=0o700)
            unit = private / "diagnostic-unit"
            original = evidence_module._rename_directory_exclusive

            def race_destination(
                source_fd: int,
                source: str,
                destination_fd: int,
                destination: str,
            ) -> None:
                os.mkdir(destination, 0o700, dir_fd=destination_fd)
                descriptor = os.open(
                    destination,
                    os.O_RDONLY | os.O_DIRECTORY,
                    dir_fd=destination_fd,
                )
                try:
                    evidence_module._write_regular_at(descriptor, "sentinel", b"preserve")
                finally:
                    os.close(descriptor)
                original(source_fd, source, destination_fd, destination)

            reader = Reader(payload)
            with patch.object(
                evidence_module,
                "_rename_directory_exclusive",
                side_effect=race_destination,
            ), self.assertRaises(EvidenceError):
                capture_source(reader, reader.expected, private_diagnostic_path=unit)
            self.assertEqual((unit / "sentinel").read_bytes(), b"preserve")
            self.assertFalse((unit / "raw.bin").exists())
            self.assertFalse((unit / "diagnostic.json").exists())
            self.assertEqual({entry.name for entry in private.iterdir()}, {unit.name})

    def test_private_diagnostic_rejects_detached_parent_after_rename(self):
        payload = b'{"partial":true}'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            private = root / "private"
            private.mkdir(mode=0o700)
            moved = root / "moved-private"
            unit = private / "diagnostic-unit"
            original = evidence_module._rename_directory_exclusive

            def detach_after_rename(
                source_fd: int,
                source: str,
                destination_fd: int,
                destination: str,
            ) -> None:
                original(source_fd, source, destination_fd, destination)
                private.rename(moved)
                private.mkdir(mode=0o700)

            with patch.object(
                evidence_module,
                "_rename_directory_exclusive",
                side_effect=detach_after_rename,
            ), self.assertRaises(EvidenceError):
                evidence_module._persist_private_diagnostic(unit, payload)
            self.assertFalse(unit.exists())
            self.assertEqual((moved / unit.name / "raw.bin").read_bytes(), payload)

    def test_private_diagnostic_reverifies_content_after_rename(self):
        payload = b'{"partial":true}'
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory).resolve() / "private"
            private.mkdir(mode=0o700)
            unit = private / "diagnostic-unit"
            original = evidence_module._rename_directory_exclusive

            def alter_after_rename(
                source_fd: int,
                source: str,
                destination_fd: int,
                destination: str,
            ) -> None:
                original(source_fd, source, destination_fd, destination)
                (unit / "raw.bin").write_bytes(b"changed")

            with patch.object(
                evidence_module,
                "_rename_directory_exclusive",
                side_effect=alter_after_rename,
            ), self.assertRaises(EvidenceError):
                evidence_module._persist_private_diagnostic(unit, payload)

    def test_source_adapter_exceptions_are_sanitized_but_process_control_propagates(self):
        identity = SourceIdentity("x", "u", "1", "c", 0, sha256(b"").hexdigest())

        class Broken:
            def identity(self) -> SourceIdentity:
                raise RuntimeError("private adapter detail")

            def read(self, maximum: int) -> bytes:
                return b""

        with self.assertRaises(EvidenceError) as caught:
            capture_source(Broken(), identity)
        self.assertNotIn("private adapter detail", str(caught.exception))

        class Cancelled(Broken):
            def identity(self) -> SourceIdentity:
                raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            capture_source(Cancelled(), identity)

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

    def test_public_projection_rejects_embedded_cross_platform_host_paths(self):
        for value in (
            "prefix /private/tmp/kil-secret suffix",
            "prefix /home/name/kil-secret suffix",
            "prefix /VAR/FOLDERS/ab/cd suffix",
            "file:///Users/name/private.json",
            r"prefix C:\Users\name\secret suffix",
            r"prefix \\server\share\secret suffix",
            "unix:///private/tmp/kil.sock",
            "unix://local-socket",
            "prefix ~/kil-secret suffix",
            "prefix $HOME/kil-secret suffix",
            r"prefix %USERPROFILE%\kil-secret suffix",
        ):
            with self.subTest(value=value), self.assertRaises(PublicBoundaryError):
                validate_public_projection({"value": value})
        with self.assertRaises(PublicBoundaryError):
            validate_public_projection({"prefix /PRIVATE/TMP/secret suffix": True})

    def test_original_foreign_names_are_rejected_anywhere_in_projection(self):
        evidence = private_evidence()
        for leaked in ("client-a", "prefix client-a suffix", "xclient-a", "client-ax"):
            candidate = deepcopy(evidence)
            candidate["runtime_identities"]["topology_attestation"]["objects"][0]["uid"] = leaked  # type: ignore[index]
            with self.subTest(leaked=leaked), self.assertRaises(EvidenceError):
                build_public_bundle(candidate)

    def test_structural_foreign_name_rule_allows_reviewed_vocabulary_collisions(self):
        evidence = private_evidence()
        names = ("default", "id")
        for side in (
            evidence["foreign_profiles_before"],
            evidence["runtime_identities"]["foreign_profiles_after"],  # type: ignore[index]
        ):
            for record, name in zip(side, names, strict=True):  # type: ignore[arg-type]
                record["name"] = name
        public = build_public_bundle(evidence)
        self.assertEqual(public["topology_attestation"]["namespaces"][0], "default")  # type: ignore[index]
        validate_public_projection(
            {"xdefault-key": "reviewed"},
            forbidden_names=("default", "id"),
        )
        with self.assertRaises(PublicBoundaryError):
            validate_public_projection(
                {"provenance": "prefix client-a suffix"},
                forbidden_names=("client-a",),
            )
        with tempfile.TemporaryDirectory() as directory:
            published = publish_bundle(evidence, Path(directory).resolve() / "public")
            self.assertEqual(verify_bundle(published).schema_family, "v3b2-run")

    def test_original_foreign_names_are_rejected_in_dynamic_identity_fields(self):
        evidence = private_evidence()
        for field, value in (
            ("cluster_incarnation_uid", "xclient-a"),
            ("uid", "xclient-a"),
            ("resource_version", "client-ax"),
            ("pod", "envoy-client-a"),
        ):
            candidate = deepcopy(evidence)
            topology = candidate["runtime_identities"]["topology_attestation"]  # type: ignore[index]
            if field == "cluster_incarnation_uid":
                topology[field] = value  # type: ignore[index]
            elif field == "pod":
                topology["pod_images"][5][field] = value  # type: ignore[index]
            else:
                topology["objects"][0][field] = value  # type: ignore[index]
            with self.subTest(field=field), self.assertRaises(EvidenceError):
                build_public_bundle(candidate)
        for field in ("arch", "runtime"):
            candidate = deepcopy(evidence)
            candidate["foreign_profiles_before"][0][field] = "client-a"  # type: ignore[index]
            candidate["runtime_identities"]["foreign_profiles_after"][0][field] = "client-a"  # type: ignore[index]
            with self.subTest(field=field), self.assertRaises(EvidenceError):
                build_public_bundle(candidate)

    def test_foreign_profiles_are_keyed_sorted_and_bind_normalized_resources(self):
        evidence = private_evidence()
        projected = project_foreign_profiles(evidence["foreign_profiles_before"], evidence["runtime_identities"]["foreign_profiles_after"], b"private-key")  # type: ignore[index]
        self.assertTrue(projected["unchanged"])
        self.assertEqual(projected["before"], projected["after"])
        self.assertEqual(projected["before"], sorted(projected["before"], key=lambda item: item["pseudonym"]))
        self.assertNotIn("client-a", json.dumps(projected))
        changed = private_evidence(request_free=True)
        changed["runtime_identities"]["foreign_profiles_after"][0]["cpus"] = 9  # type: ignore[index]
        bundle = build_public_bundle(changed)
        self.assertFalse(bundle["foreign_profile_attestation"]["unchanged"])
        self.assertEqual(bundle["result_class"], "diagnostic_foreign_state_mismatch")
        self.assertEqual(bundle["request_results"], [])
        self.assertEqual(bundle["semantic_joins"], [])
        self.assertEqual(bundle["source_attestations"], [])
        nominal_mismatch = private_evidence()
        nominal_mismatch["runtime_identities"]["foreign_profiles_after"][0]["cpus"] = 9  # type: ignore[index]
        with self.assertRaises(EvidenceError):
            build_public_bundle(nominal_mismatch)

    def test_private_expected_topology_and_policy_are_exact_and_cross_bound(self):
        for request_free in (False, True):
            for mutation in ("topology", "policy"):
                evidence = private_evidence(request_free=request_free)
                if request_free:
                    evidence["runtime_identities"]["foreign_profiles_after"][0]["cpus"] = 9  # type: ignore[index]
                if mutation == "topology":
                    evidence["expected_topology"]["object_keys"][0][3] = "other"  # type: ignore[index]
                else:
                    evidence["expected_policy_graph"]["edges"][0]["destination_roles"] = ["other"]  # type: ignore[index]
                with self.subTest(request_free=request_free, mutation=mutation), self.assertRaises(EvidenceError):
                    build_public_bundle(evidence)

    def test_foreign_mismatch_verifier_rejects_repaired_request_evidence(self):
        evidence = private_evidence(request_free=True)
        evidence["runtime_identities"]["foreign_profiles_after"][0]["cpus"] = 9  # type: ignore[index]
        with tempfile.TemporaryDirectory() as directory:
            published = publish_bundle(evidence, Path(directory).resolve() / "public")
            manifest_path = published / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            digest = "f" * 64
            manifest["request_results"] = [{
                "track": TRACKS[0], "request_id": "v3b1-central-request",
                "attempt": 1, "decision": "permit", "http_status": 200,
                "decision_digest": digest, "target_markers": 1,
            }]
            manifest_path.write_bytes(canonical(manifest))
            self._repair_commitment_and_sums(published)
            with self.assertRaises(EvidenceError):
                verify_bundle(published)

    def test_private_manifest_field_set_and_claims_are_exact(self):
        evidence = private_evidence()
        self.assertEqual(set(evidence), PRIVATE_MANIFEST_FIELDS)
        bundle = build_public_bundle(evidence)
        self.assertEqual(tuple(bundle["claim_exclusions"]), CLAIM_EXCLUSIONS)
        self.assertNotIn("9" * 64, json.dumps(bundle))

    def test_publication_and_verifier_reject_tree_and_semantic_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
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
            root = Path(directory).resolve()
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
            root = Path(directory).resolve()
            published = publish_bundle(private_evidence(), root / "public")
            requests = (published / "requests.jsonl").read_bytes().splitlines()
            (published / "requests.jsonl").chmod(0o600)
            (published / "requests.jsonl").write_bytes(b"\n".join(reversed(requests)) + b"\n")
            self._rewrite_sums(published)
            with self.assertRaises(EvidenceError):
                verify_bundle(published)

    def test_repaired_join_and_inventory_semantic_drift_are_rejected(self):
        mutations = (
            "join_decision",
            "join_status",
            "join_markers",
            "join_upstream",
            "join_digest",
            "extra_object",
            "cluster_uid",
            "endpoint",
            "readiness",
            "policy",
            "image",
            "pod_name",
            "pin",
            "run",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                published = publish_bundle(private_evidence(), root / "public")
                manifest_path = published / "manifest.json"
                manifest = json.loads(manifest_path.read_text())
                if mutation == "join_decision":
                    manifest["semantic_joins"][0]["decision"] = "deny"
                elif mutation == "join_status":
                    manifest["semantic_joins"][0]["http_status"] = 418
                elif mutation == "join_markers":
                    manifest["semantic_joins"][0]["target_markers"] = 0
                elif mutation == "join_upstream":
                    manifest["semantic_joins"][0]["envoy_upstream_attempted"] = False
                elif mutation == "join_digest":
                    manifest["semantic_joins"][0]["decision_digest"] = "f" * 64
                elif mutation == "extra_object":
                    manifest["topology_attestation"]["objects"].append(deepcopy(manifest["topology_attestation"]["objects"][0]))
                elif mutation == "cluster_uid":
                    manifest["topology_attestation"]["cluster_incarnation_uid"] = "wrong"
                elif mutation == "endpoint":
                    manifest["topology_attestation"]["endpoints"][0]["service"] = "other"
                elif mutation == "readiness":
                    manifest["topology_attestation"]["calico_readiness"]["node_ready"] = 0
                elif mutation == "policy":
                    manifest["policy_attestation"]["edges"][0]["destination_roles"] = ["target"]
                elif mutation == "image":
                    manifest["topology_attestation"]["pod_images"][0]["image"] = ENVOY_DIGEST
                elif mutation == "pod_name":
                    for item in manifest["topology_attestation"]["pod_images"]:
                        if item["image_role"] == "calico-cni":
                            item["pod"] = "controller-z"
                elif mutation == "pin":
                    manifest["content_identities"]["calico_manifest_sha256"] = "f" * 64
                else:
                    manifest["content_identities"]["run_id"] = "v3b2-" + "2" * 64
                manifest_path.chmod(0o600)
                manifest_path.write_bytes(canonical(manifest))
                self._repair_commitment_and_sums(published)
                with self.assertRaises(EvidenceError):
                    verify_bundle(published)

    def test_symlink_ancestry_is_rejected_for_publish_and_verify(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            real = root / "real"
            real.mkdir()
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)
            sentinel = real / "sentinel"
            sentinel.write_text("preserve")
            with self.assertRaises(EvidenceError):
                publish_bundle(private_evidence(), alias / "public")
            self.assertEqual(sentinel.read_text(), "preserve")
            published = publish_bundle(private_evidence(), real / "public")
            with self.assertRaises(EvidenceError):
                verify_bundle(alias / "public" / published.name)
            self.assertEqual(sentinel.read_text(), "preserve")

    def test_public_parent_replacement_is_rejected_before_staging_and_rename(self):
        for boundary in ("after_prepare", "before_rename"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                parent = root / "public"
                parent.mkdir(mode=0o700)
                moved = root / "moved"
                decoy = root / "decoy"
                decoy.mkdir(mode=0o700)
                sentinel = decoy / "sentinel"
                sentinel.write_text("preserve")

                def replace_parent() -> None:
                    parent.rename(moved)
                    decoy.rename(parent)

                if boundary == "after_prepare":
                    original_prepare = evidence_module._prepare_public_parent

                    def prepared(path: object):
                        result = original_prepare(path)
                        replace_parent()
                        return result

                    context = patch.object(evidence_module, "_prepare_public_parent", side_effect=prepared)
                else:
                    original_verify = evidence_module._verify_v3b2
                    replaced = False

                    def verified(payloads):
                        nonlocal replaced
                        result = original_verify(payloads)
                        if not replaced:
                            replace_parent()
                            replaced = True
                        return result

                    context = patch.object(evidence_module, "_verify_v3b2", side_effect=verified)
                with context, self.assertRaises(EvidenceError):
                    publish_bundle(private_evidence(), parent)
                self.assertEqual((parent / "sentinel").read_text(), "preserve")
                self.assertFalse((parent / RUN_ID).exists())

    def test_post_rename_failure_never_moves_a_raced_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve() / "public"
            parent.mkdir(mode=0o700)
            detached = parent / "detached-owned"
            destination = parent / RUN_ID
            original_anchor = evidence_module._assert_anchor_path
            calls = 0

            def replace_after_final_check(path, identity, label):
                nonlocal calls
                result = original_anchor(path, identity, label)
                calls += 1
                if calls == 3:
                    destination.rename(detached)
                    destination.mkdir(mode=0o700)
                    (destination / "sentinel").write_text("preserve")
                    raise EvidenceError("force post-rename failure")
                return result

            with patch.object(
                evidence_module,
                "_assert_anchor_path",
                side_effect=replace_after_final_check,
            ), self.assertRaises(EvidenceError):
                publish_bundle(private_evidence(), parent)
            self.assertEqual((destination / "sentinel").read_text(), "preserve")
            self.assertTrue((detached / "manifest.json").is_file())
            self.assertEqual(
                [entry for entry in parent.iterdir() if ".failed-" in entry.name],
                [],
            )

    def test_post_rename_semantic_failure_leaves_owned_bundle_for_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve() / "public"
            parent.mkdir(mode=0o700)
            destination = parent / RUN_ID
            original_verify = evidence_module._verify_v3b2
            calls = 0

            def fail_after_rename(payloads):
                nonlocal calls
                result = original_verify(payloads)
                calls += 1
                if calls == 2:
                    raise EvidenceError("force post-rename semantic failure")
                return result

            with patch.object(
                evidence_module,
                "_verify_v3b2",
                side_effect=fail_after_rename,
            ), self.assertRaises(EvidenceError):
                publish_bundle(private_evidence(), parent)
            self.assertTrue((destination / "manifest.json").is_file())
            self.assertEqual(
                [entry for entry in parent.iterdir() if ".failed-" in entry.name],
                [],
            )

    def test_publication_rejects_a_parent_detached_after_rename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            parent = root / "public"
            parent.mkdir(mode=0o700)
            moved = root / "moved-public"
            original = evidence_module._rename_directory_exclusive
            calls = 0

            def detach_parent(
                source_fd: int,
                source: str,
                destination_fd: int,
                destination: str,
            ) -> None:
                nonlocal calls
                original(source_fd, source, destination_fd, destination)
                calls += 1
                if calls == 1:
                    parent.rename(moved)
                    parent.mkdir(mode=0o700)
                    (parent / "sentinel").write_text("preserve")

            with patch.object(
                evidence_module,
                "_rename_directory_exclusive",
                side_effect=detach_parent,
            ), self.assertRaises(EvidenceError):
                publish_bundle(private_evidence(), parent)
            self.assertEqual((parent / "sentinel").read_text(), "preserve")
            self.assertFalse((parent / RUN_ID).exists())

    def test_public_apis_totalize_malformed_types_and_unicode(self):
        identity = SourceIdentity("x", "u", "1", "c", 0, sha256(b"").hexdigest())
        with self.assertRaises(EvidenceError):
            SourceIdentity("bad\ud800", "uid", "1", "cid", 0, sha256(b"").hexdigest())
        with self.assertRaises(EvidenceError):
            CapturedSource(identity, b"different")
        with self.assertRaises(EvidenceError):
            VerifiedBundle("v3b2-run", "bad\ud800", "result", "not_promoted", HEX_A)
        with self.assertRaises(EvidenceError):
            capture_source(object(), SourceIdentity("x", "u", "1", "c", 0, sha256(b"").hexdigest()))  # type: ignore[arg-type]
        with self.assertRaises(EvidenceError):
            build_public_bundle(None)
        with self.assertRaises(PublicBoundaryError):
            validate_public_projection(None)
        with self.assertRaises(PublicBoundaryError):
            validate_public_projection({"value": "bad\ud800"})
        with self.assertRaises(PublicBoundaryError):
            validate_public_projection({"bad\ud800": "value"})
        with self.assertRaises(PublicBoundaryError):
            validate_public_projection({"value": 1.0})
        with self.assertRaises(EvidenceError):
            project_foreign_profiles(
                [{"name": "bad\ud800", "status": "Running", "arch": "a", "cpus": 1, "memory": 1, "disk": 1, "runtime": "docker"}],
                [],
                b"key",
            )
        with self.assertRaises(EvidenceError):
            project_foreign_profiles(
                [{"name": "foreign", "status": "Running", "arch": "bad\ud800", "cpus": 1, "memory": 1, "disk": 1, "runtime": "docker"}],
                [],
                b"key",
            )
        with self.assertRaises(EvidenceError):
            publish_bundle(private_evidence(), None)  # type: ignore[arg-type]
        with self.assertRaises(EvidenceError):
            verify_bundle(None)  # type: ignore[arg-type]

    def test_duplicate_checksum_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            published = publish_bundle(private_evidence(), root / "public")
            sums = published / "SHA256SUMS"
            sums.chmod(0o600)
            sums.write_bytes(sums.read_bytes() + sums.read_bytes().splitlines(keepends=True)[0])
            with self.assertRaises(EvidenceError):
                verify_bundle(published)

    def test_verifier_totalizes_closed_member_shape_failures_before_rendering(self):
        mutations = (
            "empty_request",
            "missing_request_key",
            "extra_request_key",
            "malformed_join_member",
            "extra_join_key",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                published = publish_bundle(
                    private_evidence(),
                    Path(directory).resolve() / "public",
                )
                manifest_path = published / "manifest.json"
                manifest = json.loads(manifest_path.read_text())
                if mutation == "empty_request":
                    manifest["request_results"] = [{}]
                elif mutation == "missing_request_key":
                    del manifest["request_results"][0]["decision_digest"]
                elif mutation == "extra_request_key":
                    manifest["request_results"][0]["extra"] = "closed"
                elif mutation == "malformed_join_member":
                    manifest["semantic_joins"][0] = []
                else:
                    manifest["semantic_joins"][0]["extra"] = "closed"
                manifest_path.chmod(0o600)
                manifest_path.write_bytes(canonical(manifest))
                self._repair_commitment_from_existing_artifacts(published)
                with self.assertRaises(EvidenceError):
                    verify_bundle(published)

    def test_missing_symlink_malformed_and_oversized_are_rejected(self):
        mutations = ("missing", "symlink", "malformed", "oversized")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
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
            root = Path(directory).resolve()
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

    @staticmethod
    def _repair_commitment_and_sums(bundle: Path) -> None:
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        artifacts = evidence_module._artifacts(manifest)
        for name, payload in artifacts.items():
            path = bundle / name
            path.chmod(0o600)
            path.write_bytes(payload)
        manifest["public_commitment_sha256"] = evidence_module._public_commitment(manifest, artifacts)
        manifest_path.write_bytes(canonical(manifest))
        V3B2EvidenceTest._rewrite_sums(bundle)

    @staticmethod
    def _repair_commitment_from_existing_artifacts(bundle: Path) -> None:
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        artifacts = {
            name: (bundle / name).read_bytes()
            for name in evidence_module._DATA_FILES
        }
        manifest["public_commitment_sha256"] = evidence_module._public_commitment(
            manifest,
            artifacts,
        )
        manifest_path.write_bytes(canonical(manifest))
        V3B2EvidenceTest._rewrite_sums(bundle)


if __name__ == "__main__":
    unittest.main()
