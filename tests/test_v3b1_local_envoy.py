from dataclasses import FrozenInstanceError
import errno
from hashlib import sha256
import http.client
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

import tools.v3b1_local_envoy as local_envoy_module

from kil.canonical import canonical_json
from kil.live_authz import LiveTrack
from kil.v3b_preflight import V3BProfile
from tools.v3b1_harness_contract import (
    ContractError,
    DockerInventory,
    IntegrationContractFixture,
    RequestFailureProvenance,
    SCHEMA_VERSION,
    SourceCollectionStatus,
    load_integration_contract,
    normalize_transport_exception,
    parse_inventory_rows,
)
from tools.v3b1_local_envoy import (
    _complete_request_attempt,
    _bind_journal_manifest,
    _persist_journal,
    _prepare_failure_provisional,
    _runtime_root,
    ACTIVE_STATE_PATH,
    authoritative_bundle_attestation,
    CommandResult,
    ControllerError,
    LocalEnvoyController,
    RETRY_CONTROL_HEADERS,
    build_runtime_commands,
    create_run_manifest,
    claim_request_attempt,
    comparison_facts_sha256,
    create_lifecycle_journal,
    collection_commands,
    finalize_teardown_evidence,
    finalize_publication,
    journal_event,
    join_evidence,
    load_bound_active_state,
    load_lifecycle_journal,
    make_parser,
    materialize_run_inputs,
    parse_colima_profiles,
    persist_active_state,
    recovery_plan,
    stage_build_context,
    select_registry_digest,
    teardown_commands,
    validate_container_attestation,
    validate_image_architecture,
    verify_public_checksums,
    validate_colima_profiles,
    validate_dedicated_colima_profile,
    validate_request_journal,
    write_evidence_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE = V3BProfile.load(ROOT / "deploy/kind/v3b-profile.json")
HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64
PYTHON_DIGEST = f"docker.io/library/python@sha256:{HEX_A}"
ENVOY_DIGEST = f"docker.io/envoyproxy/envoy@sha256:{HEX_B}"
KIL_IMAGE_ID = f"sha256:{HEX_C}"
TOOL_IDENTITIES = {
    name: {
        "archive_sha256": HEX_A,
        "executable_sha256": HEX_B,
        "byte_size": index + 1,
        "version_output": version,
        "checksum_attestation": "upstream_sidecar",
    }
    for index, (name, version) in enumerate(
        (
            ("docker", "Docker version 29.7.2"),
            ("kind", "kind v0.32.0"),
            ("kubectl", "kubectl v1.36.3"),
        )
    )
}
ENGINE_PROVENANCE = {
    "server_version": "29.7.2",
    "api_version": "1.52",
    "git_commit": "abcdef0",
    "go_version": "go1.25.7",
    "os": "linux",
    "architecture": "arm64",
    "kernel_version": "6.12.0",
    "storage_driver": "overlayfs",
    "cgroup_driver": "cgroupfs",
    "cgroup_version": "2",
}


class HarnessIntegrationContractTest(unittest.TestCase):
    FIXTURE = ROOT / "tests/fixtures/v3b1-integration-contract.json"

    def test_fixture_is_canonical_closed_frozen_and_explicitly_provenanced(self):
        fixture = load_integration_contract(self.FIXTURE)

        self.assertEqual(fixture.schema_version, "kil.v3b1-integration-contract.v1")
        self.assertEqual(
            {case.provenance for case in fixture.cases},
            {"observed", "reconstructed"},
        )
        self.assertEqual(
            {case.name for case in fixture.cases if case.provenance == "observed"},
            {
                "cycle-3-post-stop-docker-cp-decision-path-absent",
            },
        )
        self.assertEqual(
            {case.name for case in fixture.cases if case.provenance == "reconstructed"},
            {
                "cycle-1-observed-network-values-reconstructed-inventory",
                "cycle-2-observed-network-values-reconstructed-inventory",
                "cycle-3-network-not-found-replacement-inventory",
                "cycle-3-request-send-socket-failure",
                "cycle-3-target-copy-error",
            },
        )
        with self.assertRaises(FrozenInstanceError):
            fixture.cases[0].provenance = "reconstructed"

    def test_request_failure_provenance_is_closed_and_sanitized(self):
        record = RequestFailureProvenance.from_mapping(
            {
                "stage": "response_headers",
                "exception_class": "ConnectionResetError",
                "errno": None,
                "errno_name": None,
                "connect_monotonic_ns": 10,
                "send_monotonic_ns": 20,
                "failure_monotonic_ns": 30,
                "request_bytes_may_have_been_sent": True,
                "attempt_count": 1,
                "retry_performed": False,
            }
        )

        self.assertTrue(record.request_bytes_may_have_been_sent)
        with self.assertRaises(FrozenInstanceError):
            record.stage = "request_send"
        with self.assertRaises(ContractError):
            RequestFailureProvenance.from_mapping(
                {
                    **record.to_mapping(),
                    "raw_exception_message": "connection reset by peer",
                }
            )
        with self.assertRaises(ContractError):
            RequestFailureProvenance.from_mapping(
                {**record.to_mapping(), "stage": "connect"}
            )
        with self.assertRaises(ContractError):
            RequestFailureProvenance.from_mapping(
                {
                    **record.to_mapping(),
                    "stage": "response_body",
                    "request_bytes_may_have_been_sent": False,
                }
            )
        with self.assertRaises(ContractError):
            RequestFailureProvenance.from_mapping(
                {**record.to_mapping(), "attempt_count": True}
            )

    def test_request_failure_provenance_closes_transport_facts(self):
        base = {
            "stage": "request_send",
            "exception_class": "ConnectionResetError",
            "errno": errno.ECONNRESET,
            "errno_name": "ECONNRESET",
            "connect_monotonic_ns": 10,
            "send_monotonic_ns": 20,
            "failure_monotonic_ns": 30,
            "request_bytes_may_have_been_sent": False,
            "attempt_count": 1,
            "retry_performed": False,
        }

        for stage, may_have_sent in (
            ("request_send", False),
            ("response_headers", True),
            ("response_body", True),
        ):
            with self.subTest(stage=stage):
                parsed = RequestFailureProvenance.from_mapping(
                    {
                        **base,
                        "stage": stage,
                        "request_bytes_may_have_been_sent": may_have_sent,
                    }
                )
                self.assertEqual(parsed.stage, stage)

        for changed in (
            {"errno_name": "ECONNREFUSED"},
            {"connect_monotonic_ns": 21},
            {"retry_performed": True},
            {"stage": []},
            {"exception_class": {}},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(ContractError):
                    RequestFailureProvenance.from_mapping({**base, **changed})

    def test_transport_exception_normalizer_is_closed_and_message_free(self):
        cases = (
            (
                http.client.RemoteDisconnected("private upstream detail"),
                ("ConnectionResetError", None, None),
            ),
            (
                http.client.IncompleteRead(b"private partial response", 100),
                ("ConnectionError", None, None),
            ),
            (
                http.client.BadStatusLine("private malformed status"),
                ("ConnectionError", None, None),
            ),
            (
                ConnectionRefusedError(errno.ECONNREFUSED, "private socket path"),
                ("ConnectionRefusedError", errno.ECONNREFUSED, "ECONNREFUSED"),
            ),
            (
                BrokenPipeError(errno.EPIPE, "private request detail"),
                ("BrokenPipeError", errno.EPIPE, "EPIPE"),
            ),
            (
                TimeoutError(errno.ETIMEDOUT, "private host"),
                ("TimeoutError", errno.ETIMEDOUT, "ETIMEDOUT"),
            ),
            (
                OSError(errno.EIO, "private device detail"),
                ("OSError", errno.EIO, "EIO"),
            ),
        )

        for error, expected in cases:
            with self.subTest(error_type=type(error).__name__):
                self.assertEqual(normalize_transport_exception(error), expected)
        with self.assertRaises(ContractError):
            normalize_transport_exception(ValueError("not a transport failure"))

    def test_source_collection_status_enforces_closed_terminal_shapes(self):
        empty_sha = sha256(b"").hexdigest()
        copied = SourceCollectionStatus.from_mapping(
            {
                "track": "credential_policy_baseline",
                "source": "authz_decisions",
                "status": "copied",
                "container_id": HEX_A,
                "container_name": "kil-v3b1-authz-credential-policy-baseline-a1b2c3d4e5f6",
                "source_byte_count": 0,
                "source_sha256": empty_sha,
                "copied_byte_count": 0,
                "copied_sha256": empty_sha,
                "error_class": None,
            }
        )
        missing = SourceCollectionStatus.from_mapping(
            {
                **copied.to_mapping(),
                "status": "missing",
                "source_byte_count": None,
                "source_sha256": None,
                "copied_byte_count": None,
                "copied_sha256": None,
                "error_class": "source_missing",
            }
        )
        malformed = SourceCollectionStatus.from_mapping(
            {
                **copied.to_mapping(),
                "status": "malformed",
                "source_byte_count": 3,
                "source_sha256": sha256(b"bad").hexdigest(),
                "copied_byte_count": 3,
                "copied_sha256": sha256(b"bad").hexdigest(),
                "error_class": "invalid_json",
            }
        )
        command_failed_empty = SourceCollectionStatus.from_mapping(
            {
                **missing.to_mapping(),
                "status": "copy_error",
                "error_class": "command_failed",
            }
        )
        command_failed_after_observation = SourceCollectionStatus.from_mapping(
            {
                **copied.to_mapping(),
                "status": "copy_error",
                "copied_byte_count": None,
                "copied_sha256": None,
                "error_class": "command_failed",
            }
        )

        self.assertEqual(copied.source_byte_count, 0)
        self.assertEqual(copied.copied_sha256, empty_sha)
        self.assertIsNone(missing.copied_sha256)
        self.assertEqual(malformed.status, "malformed")
        self.assertIsNone(command_failed_empty.source_sha256)
        self.assertEqual(command_failed_after_observation.source_sha256, empty_sha)
        with self.assertRaises(ContractError):
            SourceCollectionStatus.from_mapping(
                {**copied.to_mapping(), "status": "missing"}
            )
        with self.assertRaises(ContractError):
            SourceCollectionStatus.from_mapping(
                {**copied.to_mapping(), "error_message": "permission denied"}
            )
        with self.assertRaises(ContractError):
            SourceCollectionStatus.from_mapping(
                {**copied.to_mapping(), "container_id": "a" * 12}
            )
        for changed in (
            {"track": []},
            {"source": {}},
            {"status": []},
            {"status": "copy_error", "error_class": []},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(ContractError):
                    SourceCollectionStatus.from_mapping(
                        {**copied.to_mapping(), **changed}
                    )
        for rejected in (
            {
                **copied.to_mapping(),
                "copied_sha256": sha256(b"other").hexdigest(),
            },
            {
                **malformed.to_mapping(),
                "copied_sha256": sha256(b"other").hexdigest(),
            },
            {
                **command_failed_empty.to_mapping(),
                "copied_byte_count": 0,
                "copied_sha256": empty_sha,
            },
            {
                **command_failed_after_observation.to_mapping(),
                "copied_byte_count": 0,
                "copied_sha256": empty_sha,
            },
        ):
            with self.subTest(rejected=rejected):
                with self.assertRaises(ContractError):
                    SourceCollectionStatus.from_mapping(rejected)

    def test_source_collection_status_binds_both_mismatch_sides(self):
        source_sha = sha256(b"source").hexdigest()
        copied_sha = sha256(b"copied").hexdigest()
        base = {
            "track": "credential_policy_baseline",
            "source": "target_markers",
            "status": "copy_error",
            "container_id": HEX_A,
            "container_name": "kil-v3b1-target-credential-policy-baseline-a1b2c3d4e5f6",
            "source_byte_count": 6,
            "source_sha256": source_sha,
            "copied_byte_count": 6,
            "copied_sha256": copied_sha,
            "error_class": "digest_mismatch",
        }

        digest_mismatch = SourceCollectionStatus.from_mapping(base)
        size_mismatch = SourceCollectionStatus.from_mapping(
            {
                **base,
                "copied_byte_count": 7,
                "error_class": "size_mismatch",
            }
        )

        self.assertNotEqual(
            digest_mismatch.source_sha256,
            digest_mismatch.copied_sha256,
        )
        self.assertNotEqual(
            size_mismatch.source_byte_count,
            size_mismatch.copied_byte_count,
        )
        rejected = (
            {**base, "copied_sha256": None},
            {**base, "copied_sha256": source_sha},
            {
                **base,
                "copied_byte_count": 7,
                "error_class": "digest_mismatch",
            },
            {
                **base,
                "copied_byte_count": 6,
                "error_class": "size_mismatch",
            },
            {
                **base,
                "copied_byte_count": 7,
                "copied_sha256": source_sha,
                "error_class": "size_mismatch",
            },
        )
        for record in rejected:
            with self.subTest(record=record):
                with self.assertRaises(ContractError):
                    SourceCollectionStatus.from_mapping(record)

    def test_source_collection_cross_binds_role_track_and_run_suffix(self):
        empty_sha = sha256(b"").hexdigest()
        roles = {
            "authz_decisions": "authz",
            "target_markers": "target",
            "envoy_access": "envoy",
        }
        tracks = (
            "credential_policy_baseline",
            "signed_state_only",
            "signed_plus_local_reduce",
        )

        for source, role in roles.items():
            for track in tracks:
                with self.subTest(source=source, track=track):
                    record = SourceCollectionStatus.from_mapping(
                        {
                            "track": track,
                            "source": source,
                            "status": "copied",
                            "container_id": HEX_A,
                            "container_name": (
                                f"kil-v3b1-{role}-{track.replace('_', '-')}-"
                                "a1b2c3d4e5f6"
                            ),
                            "source_byte_count": 0,
                            "source_sha256": empty_sha,
                            "copied_byte_count": 0,
                            "copied_sha256": empty_sha,
                            "error_class": None,
                        }
                    )
                    self.assertEqual(record.source, source)

        base = {
            "track": "credential_policy_baseline",
            "source": "authz_decisions",
            "status": "missing",
            "container_id": HEX_A,
            "container_name": (
                "kil-v3b1-authz-credential-policy-baseline-a1b2c3d4e5f6"
            ),
            "source_byte_count": None,
            "source_sha256": None,
            "copied_byte_count": None,
            "copied_sha256": None,
            "error_class": "source_missing",
        }
        for invalid_name in (
            "kil-v3b1-target-credential-policy-baseline-a1b2c3d4e5f6",
            "kil-v3b1-authz-signed-state-only-a1b2c3d4e5f6",
            "kil-v3b1-authz-credential-policy-baseline-a1b2c3d4e5",
            "kil-v3b1-authz-credential-policy-baseline-A1B2C3D4E5F6",
        ):
            with self.subTest(invalid_name=invalid_name):
                with self.assertRaises(ContractError):
                    SourceCollectionStatus.from_mapping(
                        {**base, "container_name": invalid_name}
                    )

    def test_inventory_rows_require_full_ids_exact_names_and_uniqueness(self):
        first_name = (
            "kil-v3b1-authz-credential-policy-baseline-aaaaaaaaaaaa"
        )
        second_name = "kil-v3b1-envoy-signed-state-only-bbbbbbbbbbbb"
        third_name = (
            "kil-v3b1-target-signed-plus-local-reduce-cccccccccccc"
        )
        payload = (
            canonical_json({"id": HEX_A, "name": first_name})
            + "\n"
            + canonical_json({"id": HEX_B, "name": second_name})
            + "\n"
        )

        inventory = parse_inventory_rows(payload, "container")

        self.assertIsInstance(inventory, DockerInventory)
        self.assertEqual(
            [entry.object_id for entry in inventory.entries],
            [HEX_A, HEX_B],
        )
        self.assertEqual(
            [entry.name for entry in inventory.entries],
            [first_name, second_name],
        )
        validator_name = (
            "kil-v3b1-validate-signed-plus-local-reduce-dddddddddddd"
        )
        validator = parse_inventory_rows(
            canonical_json({"id": HEX_C, "name": validator_name}) + "\n",
            "container",
        )
        self.assertEqual(validator.entries[0].name, validator_name)
        network_name = (
            "kil-v3b1-network-credential-policy-baseline-eeeeeeeeeeee"
        )
        network = parse_inventory_rows(
            canonical_json({"id": HEX_C, "name": network_name}) + "\n",
            "network",
        )
        self.assertEqual(network.entries[0].name, network_name)
        self.assertEqual(parse_inventory_rows("", "network").entries, ())
        for rejected in (
            canonical_json({"id": "a" * 12, "name": first_name}) + "\n",
            payload + canonical_json({"id": HEX_A, "name": third_name}) + "\n",
            payload + canonical_json({"id": HEX_C, "name": second_name}) + "\n",
            canonical_json({"extra": 1, "id": HEX_A, "name": first_name}) + "\n",
            canonical_json({"id": HEX_A, "name": "-kil-v3b1-one"}) + "\n",
            canonical_json({"id": HEX_A, "name": "k" * 129}) + "\n",
            canonical_json({"id": HEX_A, "name": "ordinary-container"}) + "\n",
            canonical_json({"id": HEX_A, "name": network_name}) + "\n",
        ):
            with self.subTest(rejected=rejected):
                with self.assertRaises(ContractError):
                    parse_inventory_rows(rejected, "container")
        with self.assertRaises(ContractError):
            parse_inventory_rows(
                canonical_json({"id": HEX_A, "name": first_name}) + "\n",
                "network",
            )
        with self.assertRaises(ContractError):
            parse_inventory_rows("", [])

    def test_fixture_loader_rejects_duplicate_fields_and_noncanonical_json(self):
        with tempfile.TemporaryDirectory(dir=self.FIXTURE.parent) as directory:
            path = Path(directory) / "fixture.json"
            path.write_text(
                '{"cases":[],"schema_version":"kil.v3b1-integration-contract.v1",'
                '"schema_version":"kil.v3b1-integration-contract.v1"}\n'
            )
            with self.assertRaisesRegex(ContractError, "duplicate"):
                load_integration_contract(path)
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "kil.v3b1-integration-contract.v1",
                        "cases": [],
                    },
                    indent=2,
                )
                + "\n"
            )
            with self.assertRaisesRegex(ContractError, "canonical"):
                load_integration_contract(path)

    def test_fixture_loader_rejects_forbidden_sensitive_fields(self):
        original = json.loads(self.FIXTURE.read_text())
        forbidden = (
            ("raw_exception_message", "connection refused"),
            ("authorization", "redacted"),
            ("signed_state", "redacted"),
            ("private_key", "redacted"),
            ("private_path", "redacted"),
            ("environment", {"SECRET_VALUE": "redacted"}),
        )
        with tempfile.TemporaryDirectory(dir=self.FIXTURE.parent) as directory:
            path = Path(directory) / "fixture.json"
            for key, value in forbidden:
                with self.subTest(key=key):
                    changed = json.loads(json.dumps(original))
                    changed["cases"][0]["record"][key] = value
                    path.write_text(canonical_json(changed) + "\n")
                    with self.assertRaisesRegex(
                        ContractError,
                        "forbidden sensitive field",
                    ):
                        load_integration_contract(path)

    def test_fixture_loader_scans_tokens_in_allowed_string_fields(self):
        original = json.loads(self.FIXTURE.read_text())
        token_values = (
            ("github-classic", "gh" + "p_" + "A" * 36),
            ("github-fine-grained", "github_" + "pat_" + "A" * 24),
            ("aws-access-key", "AK" + "IA" + "A" * 16),
            ("bearer", "Bea" + "rer " + "A" * 32),
            ("pem", "-----BEGIN " + "PRIVATE KEY-----"),
            (
                "compact-jws",
                ".".join(
                    (
                        "eyJhbGciOiJFZERTQSJ9",
                        "eyJzdWIiOiJ3b3JrbG9hZCJ9",
                        "c2lnbmF0dXJl",
                    )
                ),
            ),
        )
        with tempfile.TemporaryDirectory(dir=self.FIXTURE.parent) as directory:
            path = Path(directory) / "fixture.json"
            for label, token_value in token_values:
                with self.subTest(label=label):
                    changed = json.loads(json.dumps(original))
                    changed["cases"][0]["name"] = token_value
                    path.write_text(canonical_json(changed) + "\n")
                    with self.assertRaisesRegex(
                        ContractError,
                        "secret or credential",
                    ):
                        load_integration_contract(path)

            changed = json.loads(json.dumps(original))
            changed["cases"][0]["name"] = "/private/runtime/evidence"
            path.write_text(canonical_json(changed) + "\n")
            with self.assertRaisesRegex(ContractError, "absolute private path"):
                load_integration_contract(path)

            changed = json.loads(json.dumps(original))
            changed["cases"][0]["name"] = "KIL_PRIVATE=value"
            path.write_text(canonical_json(changed) + "\n")
            with self.assertRaisesRegex(ContractError, "environment"):
                load_integration_contract(path)

    def test_fixture_loader_rejects_symlink_ancestry_and_overlong_integers(self):
        with tempfile.TemporaryDirectory(dir=self.FIXTURE.parent) as directory:
            root = Path(directory)
            real = root / "real"
            real.mkdir()
            fixture = real / "fixture.json"
            fixture.write_bytes(self.FIXTURE.read_bytes())
            linked = root / "linked"
            linked.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ContractError, "symlink"):
                load_integration_contract(linked / "fixture.json")

            overlong = root / "overlong.json"
            overlong.write_text(
                '{"cases":[],"schema_version":' + "1" * 5000 + "}\n"
            )
            with self.assertRaises(ContractError):
                load_integration_contract(overlong)

        with self.assertRaises(ContractError):
            parse_inventory_rows(
                '{"id":' + "1" * 5000 + ',"name":"ordinary"}\n',
                "container",
            )

    def test_fixture_tuple_members_are_validated_before_attribute_access(self):
        with self.assertRaises(ContractError):
            IntegrationContractFixture(SCHEMA_VERSION, ([],))

    def test_fixture_loader_does_not_use_unbounded_path_read(self):
        original_read_bytes = Path.read_bytes
        calls = []

        def track_unbounded_read(path):
            calls.append(path)
            return original_read_bytes(path)

        with mock.patch.object(Path, "read_bytes", track_unbounded_read):
            fixture = load_integration_contract(self.FIXTURE)
        self.assertEqual(fixture.schema_version, SCHEMA_VERSION)
        self.assertEqual(calls, [])

    def test_fixture_loader_rejects_open_file_identity_mismatch(self):
        actual = os.stat(self.FIXTURE, follow_symlinks=False)
        fields = list(actual)
        fields[1] += 1
        mismatched = os.stat_result(fields)
        with mock.patch("os.fstat", return_value=mismatched):
            with self.assertRaisesRegex(ContractError, "identity"):
                load_integration_contract(self.FIXTURE)

    def test_fixture_loader_rejects_post_read_path_size_change(self):
        original_lstat = os.lstat
        fixture_calls = 0

        def changed_final_size(candidate):
            nonlocal fixture_calls
            info = original_lstat(candidate)
            if Path(candidate) == self.FIXTURE:
                fixture_calls += 1
                if fixture_calls == 2:
                    fields = list(info)
                    fields[6] += 1
                    return os.stat_result(fields)
            return info

        with mock.patch("os.lstat", side_effect=changed_final_size):
            with self.assertRaisesRegex(ContractError, "identity or size"):
                load_integration_contract(self.FIXTURE)

    def test_fixture_loader_rejects_algorithm_prefixed_private_key(self):
        original = json.loads(self.FIXTURE.read_text())
        with tempfile.TemporaryDirectory(dir=self.FIXTURE.parent) as directory:
            path = Path(directory) / "fixture.json"
            changed = json.loads(json.dumps(original))
            changed["cases"][0]["name"] = "-----BEGIN " + "RSA PRIVATE KEY-----"
            path.write_text(canonical_json(changed) + "\n")
            with self.assertRaisesRegex(ContractError, "secret"):
                load_integration_contract(path)


class FakeRunner:
    def __init__(self, replies=()):
        self.replies = list(replies)
        self.calls = []

    def run(
        self,
        argv,
        *,
        cwd=None,
        input_text=None,
        env=None,
        timeout_s=30,
    ):
        self.calls.append((list(argv), cwd, input_text, env, timeout_s))
        if self.replies:
            return self.replies.pop(0)
        return CommandResult(0, "", "")


class BuildRunner(FakeRunner):
    def run(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        if "build" in argv:
            iid = Path(argv[argv.index("--iidfile") + 1])
            iid.parent.mkdir(parents=True, exist_ok=True)
            iid.write_text(KIL_IMAGE_ID + "\n", encoding="ascii")
            return CommandResult(0, "", "")
        if "inspect" in argv:
            if "{{json .}}" in argv:
                return CommandResult(
                    0, '{"Os":"linux","Architecture":"arm64"}\n', ""
                )
            return CommandResult(0, KIL_IMAGE_ID + "\n", "")
        if "save" in argv:
            archive = Path(argv[argv.index("--output") + 1])
            archive.write_bytes(b"locked-image-archive")
            return CommandResult(0, "", "")
        return CommandResult(1, "", "unexpected command")


def manifest(
    *,
    docker_host="unix:///Users/lab/.colima/kil-v3-lab/docker.sock",
    execution_nonce="0" * 64,
):
    return create_run_manifest(
        PROFILE,
        profile_sha256=sha256(
            (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
        ).hexdigest(),
        python_image_digest=PYTHON_DIGEST,
        envoy_image_digest=ENVOY_DIGEST,
        kil_image_id=KIL_IMAGE_ID,
        kil_archive_sha256=HEX_A,
        docker_host=docker_host,
        execution_nonce=execution_nonce,
    )


def request_record(run_manifest, track, **changes):
    denied = track is LiveTrack.SIGNED_PLUS_LOCAL_REDUCE
    client_digest = (
        "3" * 64
        if denied
        else (
            "1" * 64
            if track is LiveTrack.CREDENTIAL_POLICY_BASELINE
            else "2" * 64
        )
    )
    comparison = {
        "method": "POST",
        "path": "/consequential/admin",
        "authorization_sha256": sha256(
            b"Bearer v3b1-lab-credential"
        ).hexdigest(),
        "adversarial_headers": {
            "x-kil-decision-digest": "f" * 64,
            "x-kil-issuer": "https://attacker.invalid",
            "x-kil-local-evidence": '{"divergence":"0"}',
            "x-kil-mode": "credential_policy_baseline",
            "x-kil-track": "client-selected-track",
            "x-kil-verified-subject": "spiffe://attacker.invalid/workload",
        },
        "retry_control_headers": dict(RETRY_CONTROL_HEADERS),
    }
    value = {
        "schema_version": "kil.v3b1-request.v1",
        "run_id": run_manifest["run_id"],
        "request_id": run_manifest["request_id"],
        "track": track.value,
        "method": "POST",
        "path": "/consequential/admin",
        "attempt_count": 1,
        "retry_observed": False,
        "retry_control_headers": dict(RETRY_CONTROL_HEADERS),
        "authorization_sha256": comparison["authorization_sha256"],
        "q_state_present": track is not LiveTrack.CREDENTIAL_POLICY_BASELINE,
        "q_state_sha256": (
            None
            if track is LiveTrack.CREDENTIAL_POLICY_BASELINE
            else ("4" if track is LiveTrack.SIGNED_STATE_ONLY else "5") * 64
        ),
        "adversarial_headers": comparison["adversarial_headers"],
        "comparison_facts_sha256": comparison_facts_sha256(comparison),
        "send_monotonic_ns": 10,
        "receive_monotonic_ns": 20,
        "client_response_status": 403 if denied else 200,
        "client_decision_digest": client_digest,
    }
    value.update(changes)
    return value


def decision_record(run_manifest, track, *, status, outcome, digest):
    if outcome == "error":
        adapter_reasons = []
        engine_reasons = []
    elif track is LiveTrack.CREDENTIAL_POLICY_BASELINE:
        adapter_reasons = ["baseline_permitted"]
        engine_reasons = []
    elif track is LiveTrack.SIGNED_STATE_ONLY:
        adapter_reasons = []
        engine_reasons = ["permitted"]
    else:
        adapter_reasons = []
        engine_reasons = ["insufficient_charge"]
    return {
        "schema_version": "kil.v3b-authz-record.v1",
        "request_id": run_manifest["request_id"],
        "track": track.value,
        "method": "POST",
        "path": "/consequential/admin",
        "outcome": outcome,
        "http_status": status,
        "decision_digest": digest,
        "adapter_reasons": adapter_reasons,
        "engine_reasons": engine_reasons,
        "untrusted_header_names": [],
        "monotonic_ns": 100,
    }


def envoy_record(run_manifest, track, *, status, upstream, digest):
    return {
        "run_id": run_manifest["run_id"],
        "request_id": run_manifest["request_id"],
        "track": track.value,
        "response_code": str(status),
        "upstream_host": upstream,
        "upstream_service_time": "1" if upstream != "-" else "-",
        "decision_digest": digest,
    }


def target_record(run_manifest, track, digest):
    return {
        "schema_version": "kil.v3b-target-record.v1",
        "run_id": run_manifest["run_id"],
        "request_id": run_manifest["request_id"],
        "track": track.value,
        "path": "/consequential/admin",
        "decision_digest": digest,
        "received_monotonic_ns": 110,
        "response_monotonic_ns": 120,
    }


class ControllerContractTest(unittest.TestCase):
    def test_cli_exposes_only_the_five_approved_subcommands(self):
        parser = make_parser()

        for name in ("preflight", "up", "run", "collect", "down"):
            self.assertEqual(parser.parse_args([name]).command, name)
        with self.assertRaises(SystemExit):
            parser.parse_args(["destroy"])

    def test_colima_and_docker_commands_are_exact_and_context_local(self):
        controller = LocalEnvoyController(
            ROOT,
            FakeRunner(),
            home=Path("/Users/lab"),
            port_probe=lambda port: False,
            tool_verifier=lambda: {},
        )

        self.assertEqual(
            controller.colima_start_command(HEX_A),
            [
                "colima",
                "start",
                "--profile",
                "kil-v3-lab",
                "--runtime",
                "docker",
                "--activate=false",
                "--ssh-config=false",
                "--cpus",
                "4",
                "--memory",
                "8",
                "--disk",
                "60",
                "--vm-type",
                "vz",
                "--kubernetes=false",
                "--arch=aarch64",
                "--save-config=true",
                "--template=false",
                "--binfmt=false",
                "--vz-rosetta=false",
                "--mount-inotify=false",
                "--network-mode=shared",
                "--network-address=false",
                "--network-host-addresses=false",
                "--network-preferred-route=false",
                "--port-forwarder=ssh",
                "--ssh-agent=false",
                "--nested-virtualization=false",
                "--mount",
                str(ROOT / ".tools/v3b1-staging" / HEX_A),
                "--mount-type=virtiofs",
            ],
        )
        encoded_colima = canonical_json(controller.colima_start_command(HEX_A))
        self.assertNotIn("--rosetta=false", encoded_colima)
        self.assertNotIn("--host-addresses=false", encoded_colima)
        docker = controller.docker_command("image", "ls")
        self.assertEqual(
            docker[:5],
            [
                str(ROOT / ".tools/bin/docker"),
                "--config",
                str(ROOT / ".tools/v3b1-docker-config"),
                "--host",
                "unix:///Users/lab/.colima/kil-v3-lab/docker.sock",
            ],
        )
        self.assertNotIn("context", docker)
        for ambient in (
            "DOCKER_CONTEXT",
            "DOCKER_HOST",
            "DOCKER_AUTH_CONFIG",
            "DOCKER_CONFIG",
            "BUILDX_BUILDER",
        ):
            self.assertNotIn(ambient, controller.docker_env)
        self.assertEqual(controller.docker_env["DOCKER_BUILDKIT"], "0")

    def test_preflight_reuses_tool_verifier_and_rejects_other_running_profiles(self):
        verified = []
        runner = FakeRunner(
            [
                CommandResult(0, "colima version 0.10.3\n", ""),
                CommandResult(0, "limactl version 2.2.0\n", ""),
                CommandResult(
                    0,
                    '{"name":"personal","status":"Running","arch":"aarch64",'
                    '"cpus":4,"memory":8589934592,"disk":64424509440,'
                    '"runtime":"docker"}\n',
                    "",
                ),
            ]
        )
        controller = LocalEnvoyController(
            ROOT,
            runner,
            home=Path("/Users/lab"),
            port_probe=lambda port: False,
            tool_verifier=lambda: verified.append(True) or TOOL_IDENTITIES,
        )

        with self.assertRaisesRegex(ControllerError, "non-dedicated"):
            controller.preflight()

        self.assertEqual(verified, [True])
        flattened = [part for call, *_ in runner.calls for part in call]
        self.assertNotIn("start", flattened)

    def test_preflight_profile_parser_is_closed_and_ports_are_fixed(self):
        records = parse_colima_profiles(
            '[{"name":"kil-v3-lab","status":"Stopped","arch":"aarch64",'
            '"cpus":4,"memory":8589934592,"disk":64424509440,'
            '"runtime":"docker"}]'
        )
        validate_colima_profiles(records)
        projected = parse_colima_profiles(
            '{"name":"kil-v3-lab","status":"Stopped","arch":"aarch64",'
            '"cpus":4,"memory":8589934592,"disk":64424509440,"runtime":"docker"}'
        )
        self.assertEqual(projected, records)
        attested = validate_dedicated_colima_profile(
            {
                "name": "kil-v3-lab",
                "status": "Running",
                "arch": "aarch64",
                "cpus": 4,
                "memory": 8589934592,
                "disk": 64424509440,
                "runtime": "docker",
            }
        )
        self.assertEqual(attested["runtime"], "docker")
        self.assertEqual(attested["memory"], 8)
        self.assertEqual(attested["disk"], 60)
        for changed in (
            {"cpus": 2},
            {"memory": 8},
            {"disk": 60},
            {"status": "Stopped"},
            {"runtime": "containerd"},
        ):
            bad = dict(attested)
            bad.update(changed)
            with self.assertRaisesRegex(ControllerError, "dedicated Colima"):
                validate_dedicated_colima_profile(bad)
        with self.assertRaisesRegex(ControllerError, "fields"):
            parse_colima_profiles(
                '[{"name":"kil-v3-lab","status":"Stopped"}]'
            )
        with self.assertRaisesRegex(ControllerError, "non-dedicated"):
            validate_colima_profiles(
                ({"name": "default", "status": "Running"},)
            )
        with self.assertRaisesRegex(ControllerError, "fields"):
            parse_colima_profiles(
                '[{"name":"kil-v3-lab","status":"Stopped","extra":1}]'
            )

        occupied = LocalEnvoyController(
            ROOT,
            FakeRunner(),
            home=Path("/Users/lab"),
            port_probe=lambda port: port == 18081,
            tool_verifier=lambda: {},
        )
        with self.assertRaisesRegex(ControllerError, "18081"):
            occupied.validate_ports()

    def test_post_start_colima_attestation_checks_actual_list_and_saved_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = (Path(directory) / "repo").resolve()
            home = Path(directory) / "home"
            profile = root / "deploy/kind/v3b-profile.json"
            profile.parent.mkdir(parents=True)
            profile.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )
            saved = home / ".colima/kil-v3-lab/colima.yaml"
            saved.parent.mkdir(parents=True)
            staging = root / ".tools/v3b1-staging" / HEX_A
            staging.mkdir(parents=True)
            (staging / f"ownership-{HEX_A}.json").write_text(
                canonical_json(
                    {
                        "schema_version": "kil.v3b1-colima-ownership.v1",
                        "execution_nonce": HEX_A,
                        "profile": "kil-v3-lab",
                    }
                )
                + "\n"
            )
            saved.write_text(
                "cpu: 4\nmemory: 8\ndisk: 60\narch: aarch64\n"
                "runtime: docker\nvmType: vz\nmountType: virtiofs\n"
                "mountInotify: false\nrosetta: false\nbinfmt: false\n"
                "sshConfig: false\nforwardAgent: false\nnestedVirtualization: false\n"
                "portForwarder: ssh\nkubernetes:\n  enabled: false\n"
                "network:\n  # shell && policy ! are inert full comments\n"
                "  mode: shared\n  dns: []\n  # bounded whole-section parsing\n"
                "  address: false\n  interface: en0\n"
                "  hostAddresses: false\n  preferredRoute: false\nmounts:\n"
                f"  - location: {staging}\n    # mount && ! comment\n    writable: false\n"
            )
            list_record = (
                '{"name":"kil-v3-lab","status":"Running",'
                '"arch":"aarch64","cpus":4,"memory":8589934592,'
                '"disk":64424509440,"runtime":"docker"}\n'
            )
            runner = FakeRunner([CommandResult(0, list_record, "")])
            controller = LocalEnvoyController(
                root,
                runner,
                home=home,
                port_probe=lambda port: False,
                tool_verifier=lambda: {},
            )

            attestation = controller._attest_colima_after_start(HEX_A)

            self.assertEqual(attestation["profile"]["cpus"], 4)
            self.assertEqual(
                attestation["saved_config"]["mount"], str(staging)
            )
            self.assertEqual(len(runner.calls), 1)
            self.assertEqual(runner.calls[0][0], ["colima", "list", "--json"])

            alias = staging.parent / "staging-alias"
            alias.symlink_to(staging, target_is_directory=True)
            saved.write_text(saved.read_text().replace(str(staging), str(alias)))
            runner.replies.append(CommandResult(0, list_record, ""))
            with self.assertRaisesRegex(ControllerError, "staging mount"):
                controller._attest_colima_after_start(HEX_A)

    def test_registry_tags_resolve_to_exact_repository_digests(self):
        output = json.dumps(
            [
                f"docker.io/library/python@sha256:{HEX_A}",
                f"mirror.invalid/python@sha256:{HEX_B}",
            ]
        )
        self.assertEqual(
            select_registry_digest(
                "docker.io/library/python:3.12.13-slim", output
            ),
            PYTHON_DIGEST,
        )
        self.assertEqual(
            select_registry_digest(
                "docker.io/library/python:3.12.13-slim",
                f'["python@sha256:{HEX_A}"]',
            ),
            PYTHON_DIGEST,
        )
        with self.assertRaisesRegex(ControllerError, "registry digest"):
            select_registry_digest(
                "docker.io/library/python:3.12.13-slim",
                '["docker.io/library/python:latest"]',
            )
        with self.assertRaisesRegex(ControllerError, "repository"):
            select_registry_digest(
                "docker.io/library/python:3.12.13-slim",
                f'["mirror.invalid/python@sha256:{HEX_A}"]',
            )

    def test_injected_runner_builds_once_with_digest_platform_and_legacy_builder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "deploy/kind").mkdir(parents=True)
            (root / "deploy/kind/v3b-profile.json").write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )
            (root / "deploy/kind/Dockerfile.v3b").write_text(
                "ARG PYTHON_BASE_IMAGE\nFROM ${PYTHON_BASE_IMAGE}\n"
            )
            (root / "deploy/kind/Dockerfile.v3b.dockerignore").write_text(
                "**\n!deploy/kind/Dockerfile.v3b\n"
            )
            for relative in (
                "README.md",
                "pyproject.toml",
                "deploy/kind/requirements-v3b-build.txt",
                "deploy/kind/requirements-v3b-runtime.txt",
                "src/kil/__init__.py",
                "src/kil/canonical.py",
                "src/kil/decay.py",
                "src/kil/domain.py",
                "src/kil/engine.py",
                "src/kil/ext_authz_http.py",
                "src/kil/live_authz.py",
                "src/kil/q_state.py",
                "src/kil/target_http.py",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(relative + "\n")
            runner = BuildRunner()
            controller = LocalEnvoyController(
                root,
                runner,
                home=Path("/Users/lab"),
                port_probe=lambda port: False,
                tool_verifier=lambda: {},
            )
            controller._prepare_private_roots()

            image_id, archive_sha = controller._build_kil_image(
                PYTHON_DIGEST, build_key=HEX_A
            )

            self.assertEqual(image_id, KIL_IMAGE_ID)
            self.assertEqual(
                archive_sha, sha256(b"locked-image-archive").hexdigest()
            )
            commands = [call[0] for call in runner.calls]
            builds = [command for command in commands if "build" in command]
            self.assertEqual(len(builds), 1)
            build = builds[0]
            self.assertIn("linux/arm64", build)
            self.assertIn("--pull=false", build)
            self.assertIn(f"PYTHON_BASE_IMAGE={PYTHON_DIGEST}", build)
            self.assertNotIn("buildx", canonical_json(commands))
            self.assertTrue(all("--host" in command for command in commands))
            self.assertTrue(all("--config" in command for command in commands))
            context = Path(build[-1])
            self.assertEqual(context.parent.name, HEX_A)
            second_image_id, _ = controller._build_kil_image(
                PYTHON_DIGEST, build_key=HEX_B
            )
            self.assertEqual(second_image_id, KIL_IMAGE_ID)
            second_build = [
                call[0] for call in runner.calls if "build" in call[0]
            ][-1]
            self.assertEqual(Path(second_build[-1]).parent.name, HEX_B)
            self.assertNotEqual(context, Path(second_build[-1]))

    def test_manifest_is_content_addressed_and_refuses_mutable_images(self):
        value = manifest()

        self.assertRegex(value["run_id"], r"^v3b1-[a-f0-9]{64}$")
        self.assertEqual(value["evidence_scope"], "local_envoy_boundary")
        self.assertEqual(value["envoy_image_digest"], ENVOY_DIGEST)
        self.assertEqual(value["kil_image_id"], KIL_IMAGE_ID)
        self.assertEqual(len(value["containers"]), 9)
        different = create_run_manifest(
            PROFILE,
            profile_sha256=HEX_A,
            python_image_digest=PYTHON_DIGEST,
            envoy_image_digest=ENVOY_DIGEST,
            kil_image_id=KIL_IMAGE_ID,
            kil_archive_sha256=HEX_A,
            docker_host="unix:///socket",
            execution_nonce=HEX_B,
        )
        self.assertNotEqual(value["run_id"], different["run_id"])
        with self.assertRaisesRegex(ControllerError, "digest"):
            create_run_manifest(
                PROFILE,
                profile_sha256=HEX_A,
                python_image_digest="docker.io/library/python:3.12.13-slim",
                envoy_image_digest=ENVOY_DIGEST,
                kil_image_id=KIL_IMAGE_ID,
                kil_archive_sha256=HEX_A,
                docker_host="unix:///socket",
            )
        with self.assertRaisesRegex(ControllerError, "image ID"):
            create_run_manifest(
                PROFILE,
                profile_sha256=HEX_A,
                python_image_digest=PYTHON_DIGEST,
                envoy_image_digest=ENVOY_DIGEST,
                kil_image_id="kil-v3b1:latest",
                kil_archive_sha256=HEX_A,
                docker_host="unix:///socket",
            )

    def test_inputs_are_read_only_closed_and_requests_are_central_and_adversarial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = manifest()

            material = materialize_run_inputs(root, value)

            self.assertEqual(tuple(material.requests), tuple(LiveTrack))
            self.assertTrue(
                material.runtime_root.is_relative_to(
                    root / ".tools/v3b1-staging" / ("0" * 64)
                )
            )
            comparable = []
            for track, planned in material.requests.items():
                comparable.append(
                    (
                        planned["method"],
                        planned["path"],
                        planned["authorization"],
                        planned["adversarial_headers"],
                        planned["retry_control_headers"],
                    )
                )
                headers = planned["adversarial_headers"]
                for name in (
                    "x-kil-track",
                    "x-kil-decision-digest",
                    "x-kil-mode",
                    "x-kil-local-evidence",
                    "x-kil-verified-subject",
                    "x-kil-issuer",
                ):
                    self.assertIn(name, headers)
                self.assertEqual(
                    planned["retry_control_headers"], RETRY_CONTROL_HEADERS
                )
                track_root = material.runtime_root / track.value
                for name in ("authz.json", "target.json", "envoy.json"):
                    path = track_root / name
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
                authz = json.loads((track_root / "authz.json").read_text())
                target = json.loads((track_root / "target.json").read_text())
                self.assertEqual(authz["track"], track.value)
                self.assertEqual(target["track"], track.value)
                self.assertNotIn("private", canonical_json(authz))
                self.assertEqual(target["run_id"], value["run_id"])
                self.assertIsNone(planned["q_state"])
            self.assertTrue(all(item == comparable[0] for item in comparable))

    def test_runtime_is_three_internal_networks_nine_labeled_containers_and_localhost_gateways(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = manifest(docker_host="unix:///tmp/kil.sock")
            materialize_run_inputs(root, value)

            commands = build_runtime_commands(
                root, value, docker_binary=Path("/locked/docker")
            )

            network_commands = [
                command
                for command in commands
                if "network" in command and "create" in command
            ]
            self.assertEqual(len(network_commands), 3)
            self.assertTrue(all("--internal" in command for command in network_commands))
            self.assertTrue(all("bridge" in command for command in network_commands))
            run_commands = [command for command in commands if "run" in command]
            detached = [command for command in run_commands if "-d" in command]
            validators = [command for command in run_commands if "--rm" in command]
            self.assertEqual(len(detached), 9)
            self.assertEqual(len(validators), 3)
            self.assertTrue(
                all("kil.v3b1.role=validator" in command for command in validators)
            )
            self.assertTrue(
                all("kil.v3b1.managed=true" in command for command in validators)
            )
            for command in detached:
                name = command[command.index("--name") + 1]
                self.assertTrue(name.startswith("kil-v3b1-"))
                self.assertIn("kil.v3b1.managed=true", command)
            kil_services = [
                command
                for command in detached
                if any(role in command for role in ("kil.v3b1.role=authz", "kil.v3b1.role=target"))
            ]
            self.assertEqual(len(kil_services), 6)
            for command in kil_services:
                self.assertIn("--platform", command)
                self.assertIn("linux/arm64", command)
                self.assertIn("--pull=never", command)
                self.assertIn("--read-only", command)
                self.assertIn("no-new-privileges", command)
                self.assertIn("ALL", command)
                self.assertIn("65532:65532", command)
                self.assertIn(KIL_IMAGE_ID, command)
                self.assertNotIn("latest", command)
                self.assertIn("--tmpfs", command)
                self.assertIn("--memory-swap", command)
                self.assertIn("256m", command)
                self.assertIn("--restart=no", command)
                self.assertIn("--stop-timeout", command)
                self.assertIn("--log-driver", command)
                self.assertIn("json-file", command)
                self.assertIn("max-size=1m", command)
                self.assertIn("max-file=1", command)
                self.assertTrue(
                    any(value.startswith("/evidence:rw,") for value in command)
                )
                self.assertFalse(any("dst=/ledger" in value for value in command))
            targets = [
                command
                for command in kil_services
                if "kil.v3b1.role=target" in command
            ]
            self.assertTrue(
                all("/evidence/targets.jsonl" in "".join(command) for command in targets)
            )
            self.assertTrue(all("O_EXCL" in "".join(command) for command in targets))
            gateways = [
                command
                for command in detached
                if "kil.v3b1.role=envoy" in command
            ]
            self.assertEqual(
                sorted(
                    command[command.index("--publish") + 1]
                    for command in gateways
                ),
                [
                    "127.0.0.1:18080:8080/tcp",
                    "127.0.0.1:18081:8080/tcp",
                    "127.0.0.1:18082:8080/tcp",
                ],
            )
            self.assertTrue(all(ENVOY_DIGEST in command for command in gateways))
            self.assertTrue(all("65532:65532" in command for command in gateways))
            self.assertTrue(all("--disable-hot-restart" in command for command in gateways))
            self.assertTrue(all("/usr/local/bin/envoy" in command for command in gateways))
            self.assertTrue(all("--pull=never" in command for command in validators))
            for command in gateways:
                self.assertIn("--memory-swap", command)
                self.assertIn("--restart=no", command)
                self.assertIn("--stop-timeout", command)
                self.assertIn("--log-driver", command)
            run_networks = {
                command[command.index("--name") + 1]: command[
                    command.index("--network") + 1
                ]
                for command in detached
            }
            for track in value["tracks"]:
                self.assertEqual(
                    {
                        run_networks[track["authz_container"]],
                        run_networks[track["target_container"]],
                        run_networks[track["envoy_container"]],
                    },
                    {track["network"]},
                )

            copies = collection_commands(
                root, value, docker_binary=Path("/locked/docker")
            )
            self.assertEqual(len([command for command in copies if "cp" in command]), 6)
            for command in copies:
                self.assertEqual(command[0], "/locked/docker")
                self.assertIn("--config", command)
                self.assertIn("--host", command)
                self.assertIn("unix:///tmp/kil.sock", command)

    def test_active_state_and_manifest_tampering_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "artifacts" / "manifest.json"
            state = root / ".tools" / "state" / "v3b1-active.json"
            value = manifest()
            output.parent.mkdir(parents=True)
            output.write_text(canonical_json(value) + "\n", encoding="utf-8")
            persist_active_state(state, output, value)

            loaded = load_bound_active_state(state)
            self.assertEqual(loaded["run_id"], value["run_id"])

            output.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ControllerError, "manifest"):
                load_bound_active_state(state)

            output.write_text(canonical_json(value) + "\n", encoding="utf-8")
            raw = json.loads(state.read_text())
            raw["networks"][0]["name"] = "kil-v3b1-tampered"
            state.write_text(canonical_json(raw) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ControllerError, "state binding"):
                load_bound_active_state(state)

    def test_teardown_is_exact_and_contains_no_discovery_or_broad_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            state_path = root / "active.json"
            value = manifest(docker_host="unix:///tmp/kil.sock")
            manifest_path.write_text(canonical_json(value) + "\n")
            persist_active_state(state_path, manifest_path, value)
            state = load_bound_active_state(state_path)
            self.assertTrue(state["profile_created"])

            commands = teardown_commands(
                state, docker_binary=Path("/locked/docker")
            )

            removed = [command[-1] for command in commands if "rm" in command and "network" not in command]
            expected_order = [
                item["id"]
                for role in ("envoy", "authz", "target")
                for item in state["objects"]
                if item["role"] == role
            ]
            self.assertEqual(removed, expected_order)
            stop_indexes = [
                index
                for index, command in enumerate(commands)
                if command[0] == "/locked/docker" and "stop" in command
            ]
            remove_indexes = [
                index
                for index, command in enumerate(commands)
                if "rm" in command and "network" not in command
            ]
            self.assertLess(max(stop_indexes), min(remove_indexes))
            network_removes = [command for command in commands if "network" in command and "rm" in command]
            self.assertEqual(len(network_removes), 3)
            self.assertEqual(
                {command[-1] for command in network_removes},
                {item["id"] for item in state["network_objects"]},
            )
            self.assertEqual(
                commands[-2:],
                [
                    ["colima", "stop", "--profile", "kil-v3-lab"],
                    [
                        "colima",
                        "delete",
                        "--profile",
                        "kil-v3-lab",
                        "--force",
                        "--data",
                    ],
                ],
            )
            encoded = canonical_json(commands)
            teardown_parts = [part for command in commands for part in command]
            self.assertNotIn("--time", teardown_parts)
            self.assertIn("--timeout", teardown_parts)
            for forbidden in ("*", "prune", "system", "ps", "context", "-aq"):
                self.assertNotIn(forbidden, encoded)

            unowned = dict(state)
            unowned["profile_created"] = False
            unowned.pop("binding_sha256")
            with self.assertRaisesRegex(ControllerError, "profile ownership"):
                teardown_commands(unowned, docker_binary=Path("/locked/docker"))

    def test_default_active_state_is_an_exact_ignored_repository_path(self):
        self.assertEqual(
            ACTIVE_STATE_PATH,
            ROOT / ".tools/state/v3b1-active.json",
        )


class JoinContractTest(unittest.TestCase):
    def all_records(self):
        value = manifest()
        digests = {
            LiveTrack.CREDENTIAL_POLICY_BASELINE: "1" * 64,
            LiveTrack.SIGNED_STATE_ONLY: "2" * 64,
            LiveTrack.SIGNED_PLUS_LOCAL_REDUCE: "3" * 64,
        }
        requests = [request_record(value, track) for track in LiveTrack]
        decisions = []
        envoy = []
        targets = []
        for track in LiveTrack:
            denied = track is LiveTrack.SIGNED_PLUS_LOCAL_REDUCE
            status = 403 if denied else 200
            outcome = "deny" if denied else "permit"
            upstream = "-" if denied else "10.0.0.2:8080"
            decisions.append(
                decision_record(
                    value,
                    track,
                    status=status,
                    outcome=outcome,
                    digest=digests[track],
                )
            )
            envoy.append(
                envoy_record(
                    value,
                    track,
                    status=status,
                    upstream=upstream,
                    digest=digests[track],
                )
            )
            if not denied:
                targets.append(target_record(value, track, digests[track]))
        return value, requests, decisions, envoy, targets

    def test_permit_permit_deny_join_requires_exact_digest_and_marker_counts(self):
        value, requests, decisions, envoy, targets = self.all_records()

        joins = join_evidence(value, requests, decisions, envoy, targets)

        self.assertEqual([item["outcome"] for item in joins], ["permit", "permit", "deny"])
        self.assertEqual([item["target_marker_count"] for item in joins], [1, 1, 0])
        self.assertTrue(all(item["valid"] for item in joins))
        self.assertIsNone(joins[-1]["upstream_host"])
        self.assertEqual(joins[-1]["decision_digest"], "3" * 64)

    def test_envoy_dash_is_absent_and_authz_5xx_does_not_invent_a_digest(self):
        value = manifest()
        track = LiveTrack.SIGNED_STATE_ONLY
        joins = join_evidence(
            value,
            [
                request_record(
                    value,
                    track,
                    client_response_status=503,
                    client_decision_digest=None,
                )
            ],
            [decision_record(value, track, status=503, outcome="error", digest=None)],
            [envoy_record(value, track, status=503, upstream="-", digest="-")],
            [],
            require_all_tracks=False,
        )

        self.assertEqual(joins[0]["outcome"], "error")
        self.assertIsNone(joins[0]["envoy_decision_digest"])
        self.assertIsNone(joins[0]["upstream_host"])
        self.assertEqual(joins[0]["target_marker_count"], 0)
        self.assertTrue(joins[0]["valid"])

        with self.assertRaisesRegex(ControllerError, "5xx.*sentinel"):
            join_evidence(
                value,
                [
                    request_record(
                        value,
                        track,
                        client_response_status=503,
                        client_decision_digest="7" * 64,
                    )
                ],
                [
                    decision_record(
                        value, track, status=503, outcome="error", digest="7" * 64
                    )
                ],
                [
                    envoy_record(
                        value, track, status=503, upstream="-", digest="7" * 64
                    )
                ],
                [],
                require_all_tracks=False,
            )

    def test_spoofed_client_run_id_or_digest_mismatch_is_rejected(self):
        value, requests, decisions, envoy, targets = self.all_records()
        envoy[0]["run_id"] = "client-selected-run"
        with self.assertRaisesRegex(ControllerError, "run_id"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        targets[0]["decision_digest"] = "f" * 64
        with self.assertRaisesRegex(ControllerError, "digest"):
            join_evidence(value, requests, decisions, envoy, targets)

    def test_duplicate_markers_duplicate_records_and_retry_are_invalid(self):
        value, requests, decisions, envoy, targets = self.all_records()
        targets.append(dict(targets[0]))
        with self.assertRaisesRegex(ControllerError, "duplicate target"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        envoy.append(dict(envoy[0]))
        with self.assertRaisesRegex(ControllerError, "duplicate envoy"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        requests.append(dict(requests[0]))
        with self.assertRaisesRegex(ControllerError, "duplicate request"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        decisions.append(dict(decisions[0]))
        with self.assertRaisesRegex(ControllerError, "duplicate decision"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        requests[0]["retry_observed"] = True
        requests[0]["attempt_count"] = 2
        with self.assertRaisesRegex(ControllerError, "retry"):
            join_evidence(value, requests, decisions, envoy, targets)

    def test_policy_deny_requires_no_upstream_and_zero_markers(self):
        value, requests, decisions, envoy, targets = self.all_records()
        envoy[-1]["upstream_host"] = "10.0.0.3:8080"
        with self.assertRaisesRegex(ControllerError, "deny"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        envoy[-1]["decision_digest"] = "-"
        with self.assertRaisesRegex(ControllerError, "403"):
            join_evidence(value, requests, decisions, envoy, targets)

    def test_all_deny_and_client_response_mismatch_are_rejected(self):
        value, requests, decisions, envoy, targets = self.all_records()
        for index in (0, 1):
            decisions[index]["outcome"] = "deny"
            decisions[index]["http_status"] = 403
            envoy[index]["response_code"] = "403"
            envoy[index]["upstream_host"] = "-"
            envoy[index]["upstream_service_time"] = "-"
            requests[index]["client_response_status"] = 403
        targets.clear()
        with self.assertRaisesRegex(ControllerError, "permit / permit / deny"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        requests[0]["client_response_status"] = 403
        with self.assertRaisesRegex(ControllerError, "client response"):
            join_evidence(value, requests, decisions, envoy, targets)

    def test_wrong_target_path_and_bad_upstream_service_time_are_rejected(self):
        value, requests, decisions, envoy, targets = self.all_records()
        targets[0]["path"] = "/benign/read"
        with self.assertRaisesRegex(ControllerError, "target path"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        envoy[0]["upstream_service_time"] = "01"
        with self.assertRaisesRegex(ControllerError, "service time"):
            join_evidence(value, requests, decisions, envoy, targets)

    def test_short_requests_and_unredacted_or_unknown_reasons_are_rejected(self):
        value, requests, decisions, envoy, targets = self.all_records()
        del requests[0]["client_response_status"]
        with self.assertRaisesRegex(ControllerError, "fields"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        decisions[0]["adapter_reasons"] = ["Bearer secret"]
        with self.assertRaisesRegex(ControllerError, "type/value/redaction"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        decisions[-1]["engine_reasons"] = ["permitted"]
        with self.assertRaisesRegex(ControllerError, "causal"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        decisions[0]["untrusted_header_names"] = ["x-kil-mode"]
        with self.assertRaisesRegex(ControllerError, "header boundary"):
            join_evidence(value, requests, decisions, envoy, targets)


class _RunClock:
    def __init__(self) -> None:
        self.now_ns = 1_000_000_000
        self.sleeps: list[float] = []

    def monotonic_ns(self) -> int:
        value = self.now_ns
        self.now_ns += 1
        return value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now_ns += int(seconds * 1_000_000_000)

    def advance(self, nanoseconds: int) -> None:
        self.now_ns += nanoseconds


class _FailingRunClock(_RunClock):
    def __init__(self, fail_call: int) -> None:
        super().__init__()
        self.fail_call = fail_call
        self.calls = 0

    def monotonic_ns(self) -> int:
        self.calls += 1
        if self.calls == self.fail_call:
            raise ControllerError("injected monotonic bookkeeping failure")
        return super().monotonic_ns()


class _RunResponse:
    def __init__(self, connection, behavior) -> None:
        self.connection = connection
        self.behavior = behavior
        self.status = behavior["status"]

    def read(self, size: int) -> bytes:
        self.connection.events.append(("read", self.connection.port, size))
        error = self.behavior.get("body_error")
        if error is not None:
            raise error
        return b""

    def getheader(self, name: str):
        if name.lower() == "x-kil-decision-digest":
            return self.behavior["digest"]
        return None


class _RunSocket:
    def __init__(self, behavior, events, port) -> None:
        self.behavior = behavior
        self.events = events
        self.port = port
        self.timeouts = []

    def settimeout(self, timeout) -> None:
        self.events.append(("socket_timeout", self.port, timeout))
        self.timeouts.append(timeout)
        error = self.behavior.get("socket_timeout_error")
        if error is not None:
            raise error


class _RunConnection:
    def __init__(
        self,
        *,
        host,
        port,
        timeout,
        behavior,
        events,
        journal_path,
        request_path,
        clock,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.behavior = behavior
        self.events = events
        self.journal_path = journal_path
        self.request_path = request_path
        self.clock = clock
        self.connected = False
        self.closed = False
        self.request_count = 0
        self.sock = None
        self.socket_object = None

    def _request_states(self):
        return {
            key: value["status"]
            for key, value in load_lifecycle_journal(self.journal_path)[
                "requests"
            ].items()
        }

    def connect(self) -> None:
        self.events.append(
            (
                "connect",
                self.port,
                self.timeout,
                self._request_states(),
                self.request_path.exists(),
            )
        )
        self.clock.advance(int(self.behavior.get("connect_advance_ns", 0)))
        error = self.behavior.get("connect_error")
        if error is not None:
            raise error
        self.connected = True
        if self.behavior.get("socket_timeout_unsupported"):
            self.sock = object()
        else:
            self.socket_object = _RunSocket(
                self.behavior, self.events, self.port
            )
            self.sock = self.socket_object

    def request(self, method, path, *, body, headers) -> None:
        if not self.connected:
            raise AssertionError("request occurred before explicit TCP readiness")
        self.request_count += 1
        self.events.append(
            (
                "request",
                self.port,
                method,
                path,
                dict(headers),
                self._request_states(),
            )
        )
        error = self.behavior.get("request_error")
        if error is not None:
            raise error

    def getresponse(self):
        self.events.append(("response_headers", self.port))
        error = self.behavior.get("headers_error")
        if error is not None:
            raise error
        return _RunResponse(self, self.behavior)

    def close(self) -> None:
        if self.closed:
            return
        self.events.append(("close", self.port))
        error = self.behavior.get("close_error")
        if error is not None and self.behavior.get("close_error_leaves_open"):
            raise error
        if self.behavior.get("close_unconfirmed"):
            return
        self.closed = True
        self.sock = None
        if error is not None:
            raise error


class _RunConnectionFactory:
    RESPONSE = {
        18080: (200, "1" * 64),
        18081: (200, "2" * 64),
        18082: (403, "3" * 64),
    }

    def __init__(self, behaviors, *, events, journal_path, request_path, clock):
        self.behaviors = list(behaviors)
        self.events = events
        self.journal_path = journal_path
        self.request_path = request_path
        self.clock = clock
        self.connections = []

    def __call__(self, host, port, *, timeout):
        if not self.behaviors:
            raise AssertionError("unexpected HTTP connection construction")
        behavior = dict(self.behaviors.pop(0))
        status, digest = self.RESPONSE[port]
        behavior.setdefault("status", status)
        behavior.setdefault("digest", digest)
        self.events.append(("factory", host, port, timeout))
        connection = _RunConnection(
            host=host,
            port=port,
            timeout=timeout,
            behavior=behavior,
            events=self.events,
            journal_path=self.journal_path,
            request_path=self.request_path,
            clock=self.clock,
        )
        self.connections.append(connection)
        return connection


class GatewayReadinessTest(unittest.TestCase):
    def make_controller(self, directory, behaviors):
        root = Path(directory) / "repo"
        profile_path = root / "deploy/kind/v3b-profile.json"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_bytes((ROOT / "deploy/kind/v3b-profile.json").read_bytes())
        events = []
        clock = _RunClock()

        class RunOnlyController(LocalEnvoyController):
            def _load_and_reverify(self):
                return self.bound_state, self.bound_manifest

            def collect(self):
                self.run_events.append(("collect",))
                return self.root / "collected"

        controller = RunOnlyController(
            root,
            FakeRunner(),
            home=Path(directory) / "home",
            port_probe=lambda port: False,
            tool_verifier=lambda: TOOL_IDENTITIES,
        )
        controller._prepare_private_roots()
        value = manifest(docker_host=controller.docker_host)
        private_manifest = controller.manifest_root / f"{value['run_id']}.json"
        private_manifest.parent.mkdir(parents=True, exist_ok=True)
        private_manifest.write_text(canonical_json(value) + "\n")
        create_lifecycle_journal(
            controller.journal_path,
            private_root=controller.private_root,
            repository_root=root,
            docker_host=controller.docker_host,
            source_commit="d" * 40,
            execution_nonce=HEX_A,
            global_context="personal",
        )
        _bind_journal_manifest(controller.journal_path, private_manifest, value)
        controller.bound_state = {"manifest_path": str(private_manifest)}
        controller.bound_manifest = value
        controller.run_events = events
        request_path = _runtime_root(root, value) / "requests.jsonl"
        factory = _RunConnectionFactory(
            behaviors,
            events=events,
            journal_path=controller.journal_path,
            request_path=request_path,
            clock=clock,
        )
        # These assignments let the behavioral tests reach the missing feature
        # before the constructor-injection test turns GREEN.
        controller.connection_factory = factory
        controller.monotonic_ns = clock.monotonic_ns
        controller.sleeper = clock.sleep
        return controller, factory, clock, request_path, events

    def run_with_fake_http(self, controller):
        with mock.patch(
            "tools.v3b1_local_envoy.http.client.HTTPConnection",
            side_effect=AssertionError("global HTTPConnection bypassed injection"),
        ):
            return controller.run()

    @staticmethod
    def install_failing_clock(controller, factory, fail_call):
        clock = _FailingRunClock(fail_call)
        factory.clock = clock
        controller.monotonic_ns = clock.monotonic_ns
        controller.sleeper = clock.sleep
        return clock

    def install_readiness_poison(
        self,
        controller,
        *,
        readiness_nonce=HEX_B,
        mode=0o600,
    ):
        journal_event(
            controller.journal_path,
            "readiness_session_started",
            {"readiness_nonce": readiness_nonce},
        )
        unsigned = {
            "schema_version": "kil.v3b1-readiness-poison.v1",
            "execution_nonce": HEX_A,
            "readiness_nonce": readiness_nonce,
            "reason_category": "connection_close_ambiguous",
        }
        value = {
            **unsigned,
            "binding_sha256": sha256(
                canonical_json(unsigned).encode("utf-8")
            ).hexdigest(),
        }
        path = controller.private_root / "readiness-poison.json"
        path.write_text(canonical_json(value) + "\n")
        path.chmod(mode)
        return path

    def test_connection_factory_clock_and_sleeper_are_injected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            profile = root / "deploy/kind/v3b-profile.json"
            profile.parent.mkdir(parents=True)
            profile.write_bytes((ROOT / "deploy/kind/v3b-profile.json").read_bytes())
            factory = object()
            monotonic_ns = object()
            sleeper = object()

            controller = LocalEnvoyController(
                root,
                FakeRunner(),
                home=Path(directory) / "home",
                port_probe=lambda port: False,
                tool_verifier=lambda: TOOL_IDENTITIES,
                connection_factory=factory,
                monotonic_ns=monotonic_ns,
                sleeper=sleeper,
            )

            self.assertIs(controller.connection_factory, factory)
            self.assertIs(controller.monotonic_ns, monotonic_ns)
            self.assertIs(controller.sleeper, sleeper)

    def test_all_gateway_connections_complete_before_any_request_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, _, events = self.make_controller(
                directory, [{}, {}, {}]
            )

            self.run_with_fake_http(controller)

            connect_events = [event for event in events if event[0] == "connect"]
            self.assertEqual([event[1] for event in connect_events], [18080, 18081, 18082])
            self.assertTrue(all(event[2] <= 1.0 for event in connect_events))
            self.assertTrue(
                all(set(event[3].values()) == {"not_attempted"} for event in connect_events)
            )
            self.assertTrue(all(event[4] is False for event in connect_events))
            first_request = next(index for index, event in enumerate(events) if event[0] == "request")
            last_connect = max(index for index, event in enumerate(events) if event[0] == "connect")
            self.assertLess(last_connect, first_request)
            self.assertTrue(all(connection.closed for connection in factory.connections))

    def test_readiness_sends_no_http_bytes_and_requests_once_per_track(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, request_path, events = self.make_controller(
                directory, [{}, {}, {}]
            )

            self.run_with_fake_http(controller)

            request_events = [event for event in events if event[0] == "request"]
            self.assertEqual([event[1] for event in request_events], [18080, 18081, 18082])
            self.assertTrue(all(connection.request_count == 1 for connection in factory.connections))
            self.assertTrue(request_path.is_file())
            self.assertEqual(len(request_path.read_text().splitlines()), 3)

    def test_failed_readiness_round_closes_every_socket_and_retries_full_order(self):
        with tempfile.TemporaryDirectory() as directory:
            secret = "private socket /Users/lab/.colima/secret.sock"
            controller, factory, clock, _, events = self.make_controller(
                directory,
                [
                    {},
                    {"connect_error": ConnectionRefusedError(errno.ECONNREFUSED, secret)},
                    {},
                    {},
                    {},
                ],
            )

            self.run_with_fake_http(controller)

            self.assertEqual(
                [event[2] for event in events if event[0] == "factory"],
                [18080, 18081, 18080, 18081, 18082],
            )
            self.assertTrue(factory.connections[0].closed)
            self.assertTrue(factory.connections[1].closed)
            self.assertEqual(clock.sleeps, [0.25])
            journal = load_lifecycle_journal(controller.journal_path)
            failures = [
                event for event in journal["events"]
                if event["event"] == "readiness_connect_failed"
            ]
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0]["details"]["track"], "signed_state_only")
            self.assertNotIn(secret, controller.journal_path.read_text())

    def test_readiness_exhaustion_keeps_all_tracks_unattempted_and_no_request_file(self):
        with tempfile.TemporaryDirectory() as directory:
            secret = "private readiness timeout"
            controller, factory, _, request_path, events = self.make_controller(
                directory,
                [
                    {
                        "connect_error": TimeoutError(errno.ETIMEDOUT, secret),
                        "connect_advance_ns": 30_000_000_000,
                        "close_error": OSError(errno.EIO, "private close"),
                    }
                ],
            )

            with self.assertRaisesRegex(ControllerError, "readiness"):
                self.run_with_fake_http(controller)

            journal = load_lifecycle_journal(controller.journal_path)
            self.assertEqual(
                {value["status"] for value in journal["requests"].values()},
                {"not_attempted"},
            )
            session_events = [
                event
                for event in journal["events"]
                if event["event"] == "readiness_session_started"
            ]
            completion_events = [
                event
                for event in journal["events"]
                if event["event"] == "readiness_connect_complete"
            ]
            self.assertEqual(len(session_events), 1)
            self.assertEqual(completion_events, [])
            self.assertRegex(
                session_events[0]["details"]["readiness_nonce"], r"^[a-f0-9]{64}$"
            )
            self.assertFalse(request_path.exists())
            self.assertFalse(any(event[0] == "request" for event in events))
            self.assertTrue(factory.connections[0].closed)
            raw = controller.journal_path.read_text()
            self.assertNotIn(secret, raw)
            self.assertNotIn("private close", raw)

    def test_clock_failure_after_third_connect_closes_the_complete_set(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, request_path, events = self.make_controller(
                directory, [{}, {}, {}]
            )
            self.install_failing_clock(controller, factory, fail_call=8)

            with self.assertRaisesRegex(
                ControllerError, "monotonic bookkeeping failure"
            ):
                self.run_with_fake_http(controller)

            self.assertEqual(
                [event[1] for event in events if event[0] == "close"],
                [18080, 18081, 18082],
            )
            self.assertTrue(all(connection.closed for connection in factory.connections))
            self.assertFalse(request_path.exists())
            self.assertFalse(any(event[0] == "request" for event in events))
            self.assertFalse(any(event[0] == "collect" for event in events))

    def test_clock_failure_after_third_connect_poison_blocks_retry_on_ambiguity(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, first_factory, _, request_path, events = self.make_controller(
                directory, [{"close_unconfirmed": True}, {}, {}]
            )
            self.install_failing_clock(controller, first_factory, fail_call=8)

            with self.assertRaisesRegex(
                ControllerError, "monotonic bookkeeping failure"
            ):
                self.run_with_fake_http(controller)

            self.assertEqual(
                [event[1] for event in events if event[0] == "close"],
                [18080, 18081, 18082],
            )
            self.assertFalse(first_factory.connections[0].closed)
            poison_events = [
                event
                for event in load_lifecycle_journal(controller.journal_path)["events"]
                if event["event"] == "connection_close_failed"
            ]
            self.assertEqual(len(poison_events), 1)

            retry_events = []
            retry_clock = _RunClock()
            retry_factory = _RunConnectionFactory(
                [{}, {}, {}],
                events=retry_events,
                journal_path=controller.journal_path,
                request_path=request_path,
                clock=retry_clock,
            )
            controller.connection_factory = retry_factory
            controller.monotonic_ns = retry_clock.monotonic_ns
            controller.sleeper = retry_clock.sleep

            with self.assertRaisesRegex(
                ControllerError, "poison|teardown|manual recovery"
            ):
                self.run_with_fake_http(controller)

            self.assertEqual(retry_factory.connections, [])
            self.assertFalse(any(event[0] == "request" for event in retry_events))
            self.assertFalse(any(event[0] == "collect" for event in retry_events))

    def test_failure_timestamp_clock_error_closes_every_round_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, request_path, events = self.make_controller(
                directory,
                [
                    {},
                    {
                        "connect_error": ConnectionRefusedError(
                            errno.ECONNREFUSED, "private readiness detail"
                        )
                    },
                ],
            )
            self.install_failing_clock(controller, factory, fail_call=5)

            with self.assertRaisesRegex(
                ControllerError, "monotonic bookkeeping failure"
            ):
                self.run_with_fake_http(controller)

            self.assertEqual(len(factory.connections), 2)
            self.assertEqual(
                [event[1] for event in events if event[0] == "close"],
                [18080, 18081],
            )
            self.assertTrue(all(connection.closed for connection in factory.connections))
            self.assertFalse(request_path.exists())
            self.assertFalse(any(event[0] == "request" for event in events))
            self.assertFalse(any(event[0] == "collect" for event in events))

    def test_complete_set_must_finish_within_the_single_readiness_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, request_path, events = self.make_controller(
                directory,
                [{}, {}, {"connect_advance_ns": 30_000_000_000}],
            )

            with self.assertRaisesRegex(ControllerError, "readiness"):
                self.run_with_fake_http(controller)

            journal = load_lifecycle_journal(controller.journal_path)
            self.assertEqual(
                {value["status"] for value in journal["requests"].values()},
                {"not_attempted"},
            )
            session_events = [
                event
                for event in journal["events"]
                if event["event"] == "readiness_session_started"
            ]
            completion_events = [
                event
                for event in journal["events"]
                if event["event"] == "readiness_connect_complete"
            ]
            self.assertEqual(len(session_events), 1)
            self.assertEqual(completion_events, [])
            self.assertFalse(request_path.exists())
            self.assertFalse(any(event[0] == "request" for event in events))
            self.assertTrue(all(connection.closed for connection in factory.connections))

    def test_claim_persistence_failure_occurs_after_readiness_and_sends_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, request_path, events = self.make_controller(
                directory, [{}, {}, {}]
            )

            with mock.patch(
                "tools.v3b1_local_envoy.claim_request_attempt",
                side_effect=ControllerError("injected persistence failure"),
            ):
                with self.assertRaisesRegex(ControllerError, "persistence failure"):
                    self.run_with_fake_http(controller)

            self.assertEqual(
                [event[1] for event in events if event[0] == "connect"],
                [18080, 18081, 18082],
            )
            self.assertFalse(any(event[0] == "request" for event in events))
            self.assertFalse(request_path.exists())
            self.assertTrue(all(connection.closed for connection in factory.connections))

    def test_readiness_journal_persistence_failure_closes_the_ready_set(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, request_path, events = self.make_controller(
                directory, [{}, {}, {}]
            )
            real_journal_event = journal_event

            def fail_readiness_event(path, event, details):
                if event == "readiness_connect_complete":
                    raise ControllerError("injected readiness journal failure")
                return real_journal_event(path, event, details)

            with mock.patch(
                "tools.v3b1_local_envoy.journal_event",
                side_effect=fail_readiness_event,
            ):
                with self.assertRaisesRegex(ControllerError, "journal failure"):
                    self.run_with_fake_http(controller)

            self.assertFalse(any(event[0] == "request" for event in events))
            self.assertFalse(request_path.exists())
            self.assertTrue(all(connection.closed for connection in factory.connections))

    def assert_failed_round_close_ambiguity(self, first_behavior, category):
        with tempfile.TemporaryDirectory() as directory:
            secret = "private close message with Bearer credential"
            controller, factory, _, request_path, events = self.make_controller(
                directory,
                [
                    first_behavior(secret),
                    {
                        "connect_error": ConnectionRefusedError(
                            errno.ECONNREFUSED, "private primary detail"
                        )
                    },
                    {},
                    {},
                    {},
                ],
            )

            with self.assertRaisesRegex(
                ControllerError, "readiness.*closure|closure.*readiness"
            ):
                self.run_with_fake_http(controller)

            self.assertEqual(
                [event[2] for event in events if event[0] == "factory"],
                [18080, 18081],
            )
            self.assertFalse(any(event[0] == "request" for event in events))
            self.assertFalse(any(event[0] == "collect" for event in events))
            self.assertFalse(request_path.exists())
            journal = load_lifecycle_journal(controller.journal_path)
            self.assertEqual(
                [event["event"] for event in journal["events"]][-2:],
                ["readiness_connect_failed", "connection_close_failed"],
            )
            close_details = journal["events"][-1]["details"]
            self.assertEqual(
                close_details["failures"],
                [
                    {
                        "track": "credential_policy_baseline",
                        "category": category,
                    }
                ],
            )
            serialized = canonical_json(close_details)
            self.assertNotIn(secret, serialized)
            self.assertNotIn("private primary", serialized)
            self.assertEqual(
                len([event for event in events if event[0] == "close"]), 2
            )

    def test_failed_readiness_close_exception_stops_before_the_next_round(self):
        self.assert_failed_round_close_ambiguity(
            lambda secret: {
                "close_error": OSError(errno.EIO, secret),
                "close_error_leaves_open": True,
            },
            "close_raised",
        )

    def test_failed_readiness_unconfirmed_close_stops_before_the_next_round(self):
        self.assert_failed_round_close_ambiguity(
            lambda secret: {"close_unconfirmed": True},
            "close_unconfirmed",
        )

    def test_successful_requests_do_not_collect_when_any_close_is_ambiguous(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, _, events = self.make_controller(
                directory,
                [
                    {
                        "close_error": OSError(errno.EIO, "private close"),
                        "close_error_leaves_open": True,
                    },
                    {},
                    {},
                ],
            )

            with self.assertRaisesRegex(ControllerError, "closure"):
                self.run_with_fake_http(controller)

            self.assertEqual(sum(item.request_count for item in factory.connections), 3)
            self.assertEqual(
                len([event for event in events if event[0] == "close"]), 3
            )
            self.assertFalse(any(event[0] == "collect" for event in events))
            close_event = load_lifecycle_journal(controller.journal_path)["events"][-1]
            self.assertEqual(close_event["event"], "connection_close_failed")
            self.assertIsNone(close_event["details"]["primary_failure"])

    def test_transport_primary_is_retained_when_close_is_also_ambiguous(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, _, events = self.make_controller(
                directory,
                [
                    {
                        "request_error": BrokenPipeError(
                            errno.EPIPE, "private request"
                        ),
                        "close_error": OSError(errno.EIO, "private close"),
                        "close_error_leaves_open": True,
                    },
                    {},
                    {},
                ],
            )

            with self.assertRaisesRegex(
                ControllerError, "request_send.*closure|closure.*request_send"
            ):
                self.run_with_fake_http(controller)

            journal = load_lifecycle_journal(controller.journal_path)
            self.assertEqual(journal["events"][-2]["event"], "request_send_failed")
            self.assertEqual(journal["events"][-1]["event"], "connection_close_failed")
            self.assertEqual(
                journal["events"][-1]["details"]["primary_failure"],
                "request_send",
            )
            self.assertEqual(
                len([event for event in events if event[0] == "close"]), 3
            )
            self.assertFalse(any(event[0] == "collect" for event in events))

    def test_poisoned_run_retry_sends_nothing_and_requires_teardown(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, first_factory, _, request_path, events = self.make_controller(
                directory,
                [
                    {"close_unconfirmed": True},
                    {
                        "connect_error": ConnectionRefusedError(
                            errno.ECONNREFUSED, "private readiness detail"
                        )
                    },
                ],
            )
            with self.assertRaisesRegex(ControllerError, "closure"):
                self.run_with_fake_http(controller)
            old_socket = first_factory.connections[0]
            self.assertFalse(old_socket.closed)
            self.assertFalse(
                (controller.private_root / "readiness-poison.json").exists()
            )

            retry_events = []
            retry_clock = _RunClock()
            retry_factory = _RunConnectionFactory(
                [{}, {}, {}],
                events=retry_events,
                journal_path=controller.journal_path,
                request_path=request_path,
                clock=retry_clock,
            )
            controller.connection_factory = retry_factory
            controller.monotonic_ns = retry_clock.monotonic_ns
            controller.sleeper = retry_clock.sleep

            with self.assertRaisesRegex(
                ControllerError, "poison|teardown|manual recovery"
            ):
                self.run_with_fake_http(controller)

            self.assertEqual(retry_factory.connections, [])
            self.assertFalse(any(event[0] == "request" for event in retry_events))
            self.assertFalse(any(event[0] == "collect" for event in retry_events))
            self.assertFalse(old_socket.closed)

    def test_double_journal_failure_persists_independent_poison_and_blocks_retry(self):
        close_behaviors = (
            {
                "close_error": OSError(
                    errno.EIO, "private close message with Bearer credential"
                ),
                "close_error_leaves_open": True,
            },
            {"close_unconfirmed": True},
        )
        for close_behavior in close_behaviors:
            with (
                self.subTest(close_behavior=close_behavior),
                tempfile.TemporaryDirectory() as directory,
            ):
                controller, first_factory, _, request_path, _ = self.make_controller(
                    directory,
                    [
                        close_behavior,
                        {
                            "connect_error": ConnectionRefusedError(
                                errno.ECONNREFUSED,
                                "private readiness message with signed state",
                            )
                        },
                    ],
                )
                real_journal_event = journal_event

                def fail_both_poison_appends(path, event, details):
                    if event == "readiness_connect_failed":
                        raise ControllerError("injected readiness journal failure")
                    if event == "connection_close_failed":
                        raise ControllerError("injected close journal failure")
                    return real_journal_event(path, event, details)

                with mock.patch(
                    "tools.v3b1_local_envoy.journal_event",
                    side_effect=fail_both_poison_appends,
                ):
                    with self.assertRaisesRegex(
                        ControllerError, "readiness journal failure"
                    ):
                        self.run_with_fake_http(controller)

                poison_path = controller.private_root / "readiness-poison.json"
                self.assertTrue(poison_path.is_file())
                self.assertEqual(stat.S_IMODE(poison_path.stat().st_mode), 0o600)
                poison = json.loads(poison_path.read_text())
                self.assertEqual(
                    set(poison),
                    {
                        "schema_version",
                        "execution_nonce",
                        "readiness_nonce",
                        "reason_category",
                        "binding_sha256",
                    },
                )
                self.assertEqual(
                    poison_path.read_bytes(),
                    (canonical_json(poison) + "\n").encode("utf-8"),
                )
                self.assertEqual(poison["execution_nonce"], HEX_A)
                self.assertEqual(
                    poison["reason_category"], "connection_close_ambiguous"
                )
                self.assertNotIn("Bearer", poison_path.read_text())
                self.assertNotIn("signed state", poison_path.read_text())
                self.assertFalse(first_factory.connections[0].closed)

                retry_events = []
                retry_clock = _RunClock()
                retry_factory = _RunConnectionFactory(
                    [{}, {}, {}],
                    events=retry_events,
                    journal_path=controller.journal_path,
                    request_path=request_path,
                    clock=retry_clock,
                )
                controller.connection_factory = retry_factory
                controller.monotonic_ns = retry_clock.monotonic_ns
                controller.sleeper = retry_clock.sleep

                with self.assertRaisesRegex(
                    ControllerError, "poison|teardown|manual recovery"
                ):
                    self.run_with_fake_http(controller)

                self.assertEqual(retry_factory.connections, [])
                self.assertFalse(
                    any(event[0] == "request" for event in retry_events)
                )
                self.assertFalse(
                    any(event[0] == "collect" for event in retry_events)
                )

    def test_readiness_poison_integrity_is_checked_before_connection_construction(self):
        mutations = ("binding", "mode", "symlink")
        for mutation in mutations:
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as directory,
            ):
                controller, factory, _, _, events = self.make_controller(
                    directory, [{}, {}, {}]
                )
                poison_path = self.install_readiness_poison(controller)
                if mutation == "binding":
                    value = json.loads(poison_path.read_text())
                    value["readiness_nonce"] = HEX_C
                    poison_path.write_text(canonical_json(value) + "\n")
                elif mutation == "mode":
                    poison_path.chmod(0o644)
                else:
                    outside = Path(directory) / "outside-poison.json"
                    outside.write_bytes(poison_path.read_bytes())
                    poison_path.unlink()
                    poison_path.symlink_to(outside)

                with self.assertRaisesRegex(
                    ControllerError,
                    "poison|binding|mode|symbolic|unsafe|teardown|manual recovery",
                ):
                    self.run_with_fake_http(controller)

                self.assertEqual(factory.connections, [])
                self.assertFalse(any(event[0] == "request" for event in events))

    def test_down_retains_poison_until_exact_absence_then_clears_it(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, _, _, _, _ = self.make_controller(
                directory, [{}, {}, {}]
            )
            poison_path = self.install_readiness_poison(controller)
            controller.runner = FakeRunner(
                [
                    CommandResult(
                        0,
                        '{"name":"kil-v3-lab","status":"Running",'
                        '"arch":"aarch64","cpus":4,'
                        '"memory":8589934592,"disk":64424509440,'
                        '"runtime":"docker"}\n',
                        "",
                    )
                ]
            )

            with self.assertRaisesRegex(ControllerError, "manual recovery"):
                controller.down()
            self.assertTrue(poison_path.exists())

            controller.runner = FakeRunner(
                [
                    CommandResult(0, "[]\n", ""),
                    CommandResult(0, "personal\n", ""),
                ]
            )
            controller.down()

            self.assertFalse(poison_path.exists())

    def assert_readiness_record_failure_closes_round(self, patcher, message):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, _, events = self.make_controller(
                directory,
                [
                    {},
                    {
                        "connect_error": ConnectionRefusedError(
                            errno.ECONNREFUSED, "private readiness detail"
                        )
                    },
                    {},
                    {},
                    {},
                ],
            )

            with patcher():
                with self.assertRaisesRegex(ControllerError, message):
                    self.run_with_fake_http(controller)

            self.assertEqual(len(factory.connections), 2)
            self.assertTrue(all(connection.closed for connection in factory.connections))
            self.assertEqual(
                len([event for event in events if event[0] == "close"]), 2
            )
            self.assertFalse(any(event[0] == "request" for event in events))
            self.assertFalse(any(event[0] == "collect" for event in events))

    def test_normalization_failure_still_closes_every_round_connection(self):
        self.assert_readiness_record_failure_closes_round(
            lambda: mock.patch(
                "tools.v3b1_local_envoy.normalize_transport_exception",
                side_effect=ContractError("injected normalization failure"),
            ),
            "transport failure is not closed",
        )

    def test_readiness_journal_failure_still_closes_every_round_connection(self):
        real_journal_event = journal_event

        def fail_connect_failure(path, event, details):
            if event == "readiness_connect_failed":
                raise ControllerError("injected readiness journal failure")
            return real_journal_event(path, event, details)

        self.assert_readiness_record_failure_closes_round(
            lambda: mock.patch(
                "tools.v3b1_local_envoy.journal_event",
                side_effect=fail_connect_failure,
            ),
            "readiness journal failure",
        )

    def test_retained_sockets_receive_explicit_request_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, _, events = self.make_controller(
                directory, [{}, {}, {}]
            )

            self.run_with_fake_http(controller)

            self.assertEqual(
                [event[1:] for event in events if event[0] == "socket_timeout"],
                [(18080, 5.0), (18081, 5.0), (18082, 5.0)],
            )
            self.assertTrue(
                all(connection.socket_object.timeouts == [5.0] for connection in factory.connections)
            )

    def test_near_deadline_sockets_are_reset_to_request_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, _, events = self.make_controller(
                directory,
                [{"connect_advance_ns": 29_000_000_000}, {}, {}],
            )

            self.run_with_fake_http(controller)

            connect_timeouts = [
                event[3] for event in events if event[0] == "factory"
            ]
            self.assertEqual(connect_timeouts[0], 1.0)
            self.assertTrue(all(0 < timeout < 1.0 for timeout in connect_timeouts[1:]))
            self.assertTrue(
                all(connection.socket_object.timeouts == [5.0] for connection in factory.connections)
            )

    def test_request_timeout_reset_failure_closes_all_before_intent(self):
        for behavior in (
            {"socket_timeout_unsupported": True},
            {"socket_timeout_error": OSError(errno.EIO, "private timeout")},
        ):
            with self.subTest(behavior=behavior), tempfile.TemporaryDirectory() as directory:
                controller, factory, _, request_path, events = self.make_controller(
                    directory, [behavior, {}, {}]
                )

                with self.assertRaisesRegex(ControllerError, "request timeout"):
                    self.run_with_fake_http(controller)

                self.assertEqual(
                    [event[1] for event in events if event[0] == "socket_timeout"],
                    (
                        [18081, 18082]
                        if behavior.get("socket_timeout_unsupported")
                        else [18080, 18081, 18082]
                    ),
                )
                self.assertTrue(all(connection.closed for connection in factory.connections))
                self.assertFalse(any(event[0] == "request" for event in events))
                self.assertFalse(any(event[0] == "collect" for event in events))
                self.assertFalse(request_path.exists())
                journal = load_lifecycle_journal(controller.journal_path)
                self.assertEqual(
                    {item["status"] for item in journal["requests"].values()},
                    {"not_attempted"},
                )

    def assert_transport_stage(self, stage, behavior, expected_class, expected_errno):
        with tempfile.TemporaryDirectory() as directory:
            behaviors = [{}, {}, {}]
            behaviors[0] = {
                **behavior,
                "close_error": OSError(errno.EIO, "private close detail"),
            }
            controller, factory, _, request_path, events = self.make_controller(
                directory, behaviors
            )

            with self.assertRaisesRegex(ControllerError, stage):
                self.run_with_fake_http(controller)

            journal = load_lifecycle_journal(controller.journal_path)
            baseline = journal["requests"]["credential_policy_baseline"]
            self.assertEqual(baseline["status"], "failed")
            self.assertTrue(recovery_plan(journal)["request_replay_forbidden"])
            failures = [
                event for event in journal["events"]
                if event["event"] == "request_send_failed"
            ]
            self.assertEqual(len(failures), 1)
            details = failures[0]["details"]
            self.assertEqual(
                set(details),
                {"track", "intent_id", "record_sha256", "provenance"},
            )
            self.assertEqual(details["intent_id"], baseline["intent_id"])
            self.assertIsNone(details["record_sha256"])
            provenance = RequestFailureProvenance.from_mapping(details["provenance"])
            self.assertEqual(provenance.stage, stage)
            self.assertEqual(provenance.exception_class, expected_class)
            self.assertEqual(provenance.errno, expected_errno)
            self.assertTrue(provenance.request_bytes_may_have_been_sent)
            self.assertEqual(provenance.attempt_count, 1)
            self.assertFalse(provenance.retry_performed)
            self.assertFalse(request_path.exists())
            self.assertEqual(sum(connection.request_count for connection in factory.connections), 1)
            self.assertTrue(all(connection.closed for connection in factory.connections))
            serialized_details = canonical_json(details)
            self.assertNotIn("private", serialized_details)
            self.assertNotIn("token", serialized_details)
            self.assertFalse(any(event[0] == "collect" for event in events))

    def test_request_send_failure_has_closed_sanitized_provenance(self):
        self.assert_transport_stage(
            "request_send",
            {"request_error": BrokenPipeError(errno.EPIPE, "private request token")},
            "BrokenPipeError",
            errno.EPIPE,
        )

    def test_response_header_failure_has_closed_sanitized_provenance(self):
        self.assert_transport_stage(
            "response_headers",
            {"headers_error": http.client.RemoteDisconnected("private response")},
            "ConnectionResetError",
            None,
        )

    def test_response_body_failure_has_closed_sanitized_provenance(self):
        self.assert_transport_stage(
            "response_body",
            {"body_error": http.client.IncompleteRead(b"private body", 100)},
            "ConnectionError",
            None,
        )

    def test_failed_request_replay_is_rejected_before_reconnect(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, _, _, _, _ = self.make_controller(
                directory,
                [
                    {"request_error": BrokenPipeError(errno.EPIPE, "private")},
                    {},
                    {},
                ],
            )
            with self.assertRaises(ControllerError):
                self.run_with_fake_http(controller)

            events = []
            clock = _RunClock()
            request_path = _runtime_root(root=controller.root, manifest=controller.bound_manifest) / "requests.jsonl"
            second_factory = _RunConnectionFactory(
                [{}, {}, {}],
                events=events,
                journal_path=controller.journal_path,
                request_path=request_path,
                clock=clock,
            )
            controller.connection_factory = second_factory
            controller.monotonic_ns = clock.monotonic_ns
            controller.sleeper = clock.sleep

            with self.assertRaisesRegex(ControllerError, "attempted|replay|ambiguous"):
                self.run_with_fake_http(controller)

            self.assertEqual(second_factory.connections, [])

    def test_signed_state_is_issued_only_after_complete_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, _, _, _, events = self.make_controller(
                directory, [{}, {}, {}]
            )

            def signer(claims, private_key):
                events.append(("sign", claims.issuer))
                return "signed-state"

            with mock.patch("tools.v3b1_local_envoy.issue_q_state", side_effect=signer):
                self.run_with_fake_http(controller)

            last_connect = max(index for index, event in enumerate(events) if event[0] == "connect")
            sign_positions = [index for index, event in enumerate(events) if event[0] == "sign"]
            timeout_positions = [
                index for index, event in enumerate(events)
                if event[0] == "socket_timeout"
            ]
            self.assertEqual(len(sign_positions), 2)
            self.assertEqual(len(timeout_positions), 3)
            self.assertTrue(all(last_connect < index for index in sign_positions))
            self.assertLess(max(timeout_positions), min(sign_positions))
            signed_requests = [
                event for event in events
                if event[0] == "request" and event[1] in {18081, 18082}
            ]
            self.assertTrue(
                all("x-kil-q-state" in event[4] for event in signed_requests)
            )

    def test_crash_after_readiness_before_intent_requires_fresh_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, first_factory, _, _, events = self.make_controller(
                directory, [{}, {}, {}]
            )
            with mock.patch(
                "tools.v3b1_local_envoy.claim_request_attempt",
                side_effect=ControllerError("injected pre-intent crash"),
            ):
                with self.assertRaisesRegex(ControllerError, "pre-intent crash"):
                    self.run_with_fake_http(controller)
            self.assertTrue(all(connection.closed for connection in first_factory.connections))

            second_events = []
            second_clock = _RunClock()
            request_path = first_factory.request_path
            second_factory = _RunConnectionFactory(
                [{}, {}, {}],
                events=second_events,
                journal_path=controller.journal_path,
                request_path=request_path,
                clock=second_clock,
            )
            controller.connection_factory = second_factory
            controller.monotonic_ns = second_clock.monotonic_ns
            controller.sleeper = second_clock.sleep
            with mock.patch(
                "tools.v3b1_local_envoy.claim_request_attempt",
                side_effect=ControllerError("second pre-intent crash"),
            ):
                with self.assertRaisesRegex(ControllerError, "second pre-intent crash"):
                    self.run_with_fake_http(controller)

            self.assertEqual(
                [event[1] for event in second_events if event[0] == "connect"],
                [18080, 18081, 18082],
            )
            journal = load_lifecycle_journal(controller.journal_path)
            self.assertEqual(
                {value["status"] for value in journal["requests"].values()},
                {"not_attempted"},
            )
            session_events = [
                event
                for event in journal["events"]
                if event["event"] == "readiness_session_started"
            ]
            completion_events = [
                event
                for event in journal["events"]
                if event["event"] == "readiness_connect_complete"
            ]
            self.assertEqual(len(session_events), 2)
            self.assertEqual(len(completion_events), 2)
            session_nonces = [
                event["details"]["readiness_nonce"] for event in session_events
            ]
            completion_nonces = [
                event["details"]["readiness_nonce"] for event in completion_events
            ]
            self.assertEqual(session_nonces, completion_nonces)
            self.assertEqual(len(set(session_nonces)), 2)

    def test_readiness_journal_event_schema_rejects_extra_secret_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, _, _, _, _ = self.make_controller(
                directory, [{}, {}, {}]
            )

            with self.assertRaisesRegex(ControllerError, "readiness.*closed"):
                journal_event(
                    controller.journal_path,
                    "readiness_connect_complete",
                    {
                        "readiness_nonce": HEX_B,
                        "round": 1,
                        "host": "127.0.0.1",
                        "tracks": [track.value for track in LiveTrack],
                        "ports": [18080, 18081, 18082],
                        "ready_monotonic_ns": 1,
                        "raw_message": "Bearer should-never-be-journaled",
                    },
                )


def _record_test_readiness(journal_path: Path, nonce: str = HEX_B) -> str:
    journal_event(
        journal_path,
        "readiness_session_started",
        {"readiness_nonce": nonce},
    )
    journal_event(
        journal_path,
        "readiness_connect_complete",
        {
            "readiness_nonce": nonce,
            "round": 1,
            "host": "127.0.0.1",
            "tracks": [track.value for track in LiveTrack],
            "ports": [18080, 18081, 18082],
            "ready_monotonic_ns": 1,
        },
    )
    return nonce


class JournalRecoveryTest(unittest.TestCase):
    def create(self, root: Path) -> Path:
        private_root = root / ".tools/v3b1-private"
        private_root.mkdir(parents=True)
        journal = private_root / "journal.json"
        create_lifecycle_journal(
            journal,
            private_root=private_root,
            repository_root=root,
            docker_host="unix:///Users/lab/.colima/kil-v3-lab/docker.sock",
            source_commit="d" * 40,
            execution_nonce=HEX_A,
            global_context="personal",
        )
        return journal

    def test_private_roots_are_resolved_contained_and_never_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside"
            outside.mkdir()
            linked = root / ".tools/v3b1-private"
            linked.parent.mkdir()
            linked.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ControllerError, "symbolic|contain"):
                create_lifecycle_journal(
                    linked / "journal.json",
                    private_root=linked,
                    repository_root=root,
                    docker_host="unix:///socket",
                    source_commit="d" * 40,
                    execution_nonce=HEX_A,
                    global_context="default",
                )

        for linked_relative in (
            ".tools/state",
            ".tools/v3b1-private/manifests",
            "artifacts/generated",
        ):
            with self.subTest(linked_relative=linked_relative), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "repo"
                profile = root / "deploy/kind/v3b-profile.json"
                profile.parent.mkdir(parents=True)
                profile.write_bytes(
                    (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
                )
                outside = Path(directory) / "outside"
                outside.mkdir()
                linked = root / linked_relative
                linked.parent.mkdir(parents=True, exist_ok=True)
                linked.symlink_to(outside, target_is_directory=True)
                controller = LocalEnvoyController(
                    root,
                    FakeRunner(),
                    home=Path("/Users/lab"),
                    port_probe=lambda port: False,
                    tool_verifier=lambda: {},
                )
                with self.assertRaisesRegex(ControllerError, "symbolic|contained"):
                    controller._prepare_private_roots()
                self.assertEqual(list(outside.iterdir()), [])

    def test_completed_child_symlink_rejects_archive_before_external_move(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            profile = root / "deploy/kind/v3b-profile.json"
            profile.parent.mkdir(parents=True)
            profile.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )
            controller = LocalEnvoyController(
                root,
                FakeRunner(
                    [
                        CommandResult(0, "[]\n", ""),
                        CommandResult(0, "personal\n", ""),
                    ]
                ),
                home=Path("/Users/lab"),
                port_probe=lambda port: False,
                tool_verifier=lambda: {},
            )
            controller._prepare_private_roots()
            outside = Path(directory) / "outside-completed"
            outside.mkdir()
            completed = controller.private_root / "completed"
            if completed.exists():
                completed.rmdir()
            completed.symlink_to(outside, target_is_directory=True)
            create_lifecycle_journal(
                controller.journal_path,
                private_root=controller.private_root,
                repository_root=root,
                docker_host=controller.docker_host,
                source_commit="d" * 40,
                execution_nonce=HEX_A,
                global_context="personal",
            )

            with self.assertRaisesRegex(ControllerError, "symbolic|contained"):
                controller.down()

            self.assertTrue(controller.journal_path.exists())
            self.assertEqual(list(outside.iterdir()), [])

    def test_journal_is_hash_bound_and_request_intent_is_never_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = self.create(root)
            readiness_nonce = _record_test_readiness(journal)
            intent = claim_request_attempt(
                journal,
                LiveTrack.SIGNED_STATE_ONLY,
                readiness_nonce=readiness_nonce,
            )
            self.assertEqual(intent["status"], "intent_persisted")
            with self.assertRaisesRegex(ControllerError, "already attempted|ambiguous"):
                claim_request_attempt(
                    journal,
                    LiveTrack.SIGNED_STATE_ONLY,
                    readiness_nonce=readiness_nonce,
                )
            loaded = load_lifecycle_journal(journal)
            self.assertEqual(
                loaded["requests"][LiveTrack.SIGNED_STATE_ONLY.value]["status"],
                "intent_persisted",
            )
            raw = json.loads(journal.read_text())
            raw["phase"] = "tampered"
            journal.write_text(canonical_json(raw) + "\n")
            with self.assertRaisesRegex(ControllerError, "binding"):
                load_lifecycle_journal(journal)

    def test_manifest_only_journal_cannot_claim_request_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = self.create(root)
            value = manifest()
            private_manifest = (
                root
                / ".tools/v3b1-private/manifests"
                / f"{value['run_id']}.json"
            )
            private_manifest.parent.mkdir(parents=True)
            private_manifest.write_text(canonical_json(value) + "\n")
            _bind_journal_manifest(journal, private_manifest, value)

            with self.assertRaisesRegex(ControllerError, "readiness"):
                claim_request_attempt(journal, LiveTrack.CREDENTIAL_POLICY_BASELINE)

            loaded = load_lifecycle_journal(journal)
            self.assertEqual(
                loaded["requests"][LiveTrack.CREDENTIAL_POLICY_BASELINE.value],
                {"status": "not_attempted", "intent_id": None},
            )

    def test_unpaired_stale_readiness_completion_cannot_authorize_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = self.create(Path(directory))
            with self.assertRaisesRegex(ControllerError, "fresh|readiness"):
                journal_event(
                    journal,
                    "readiness_connect_complete",
                    {
                        "readiness_nonce": HEX_B,
                        "round": 1,
                        "host": "127.0.0.1",
                        "tracks": [track.value for track in LiveTrack],
                        "ports": [18080, 18081, 18082],
                        "ready_monotonic_ns": 1,
                    },
                )

    def test_new_readiness_session_invalidates_a_crashed_session_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = self.create(Path(directory))
            stale_nonce = _record_test_readiness(journal, HEX_B)
            journal_event(
                journal,
                "readiness_session_started",
                {"readiness_nonce": HEX_C},
            )

            with self.assertRaisesRegex(ControllerError, "fresh|readiness"):
                claim_request_attempt(
                    journal,
                    LiveTrack.CREDENTIAL_POLICY_BASELINE,
                    readiness_nonce=stale_nonce,
                )
            self.assertEqual(
                load_lifecycle_journal(journal)["requests"]
                [LiveTrack.CREDENTIAL_POLICY_BASELINE.value]["status"],
                "not_attempted",
            )

    def poisoned_readiness(self, journal: Path, nonce: str = HEX_B) -> None:
        _record_test_readiness(journal, nonce)
        journal_event(
            journal,
            "connection_close_failed",
            {
                "readiness_nonce": nonce,
                "stage": "readiness_round",
                "primary_failure": "request_processing",
                "failures": [
                    {
                        "track": LiveTrack.CREDENTIAL_POLICY_BASELINE.value,
                        "category": "close_unconfirmed",
                    }
                ],
            },
        )

    def test_poisoned_readiness_rejects_later_completion_and_failure_events(self):
        later_events = (
            (
                "readiness_connect_complete",
                {
                    "readiness_nonce": HEX_B,
                    "round": 2,
                    "host": "127.0.0.1",
                    "tracks": [track.value for track in LiveTrack],
                    "ports": [18080, 18081, 18082],
                    "ready_monotonic_ns": 2,
                },
            ),
            (
                "readiness_connect_failed",
                {
                    "readiness_nonce": HEX_B,
                    "track": LiveTrack.CREDENTIAL_POLICY_BASELINE.value,
                    "host": "127.0.0.1",
                    "port": 18080,
                    "round": 2,
                    "connect_monotonic_ns": 2,
                    "failure_monotonic_ns": 3,
                    "exception_class": "ConnectionRefusedError",
                    "errno": errno.ECONNREFUSED,
                    "errno_name": "ECONNREFUSED",
                    "request_bytes_may_have_been_sent": False,
                },
            ),
        )
        for event_name, details in later_events:
            with self.subTest(event_name=event_name), tempfile.TemporaryDirectory() as directory:
                journal = self.create(Path(directory))
                self.poisoned_readiness(journal)

                with self.assertRaisesRegex(ControllerError, "poison|terminal"):
                    journal_event(journal, event_name, details)

    def test_poisoned_readiness_cannot_be_resurrected_to_authorize_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = self.create(Path(directory))
            self.poisoned_readiness(journal)
            value = load_lifecycle_journal(journal)
            events = value["events"]
            events.append(
                {
                    "sequence": len(events) + 1,
                    "event": "readiness_connect_complete",
                    "details": {
                        "readiness_nonce": HEX_B,
                        "round": 2,
                        "host": "127.0.0.1",
                        "tracks": [track.value for track in LiveTrack],
                        "ports": [18080, 18081, 18082],
                        "ready_monotonic_ns": 2,
                    },
                }
            )
            events.append(
                {
                    "sequence": len(events) + 1,
                    "event": "request_send_intent",
                    "details": {
                        "track": LiveTrack.CREDENTIAL_POLICY_BASELINE.value,
                        "intent_id": HEX_A,
                    },
                }
            )
            value["requests"][LiveTrack.CREDENTIAL_POLICY_BASELINE.value] = {
                "status": "intent_persisted",
                "intent_id": HEX_A,
            }
            value["phase"] = "request_send_intent"
            _persist_journal(journal, value)

            with self.assertRaisesRegex(ControllerError, "poison|terminal"):
                load_lifecycle_journal(journal)

    def test_readiness_session_nonce_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = self.create(Path(directory))
            _record_test_readiness(journal, HEX_B)

            with self.assertRaisesRegex(ControllerError, "nonce.*reus|unique"):
                journal_event(
                    journal,
                    "readiness_session_started",
                    {"readiness_nonce": HEX_B},
                )

    def test_reused_readiness_nonce_is_rejected_during_recovery_load(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = self.create(Path(directory))
            _record_test_readiness(journal, HEX_B)
            value = load_lifecycle_journal(journal)
            events = value["events"]
            events.append(
                {
                    "sequence": len(events) + 1,
                    "event": "readiness_session_started",
                    "details": {"readiness_nonce": HEX_B},
                }
            )
            value["phase"] = "readiness_session_started"
            _persist_journal(journal, value)

            with self.assertRaisesRegex(ControllerError, "nonce.*reus|unique"):
                load_lifecycle_journal(journal)

    def test_request_intent_event_fields_are_closed_and_secret_free(self):
        for mutation in (
            {"raw_message": "Bearer secret"},
            {"intent_id": "Bearer secret"},
            {"track": "attacker_selected"},
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                journal = self.create(Path(directory))
                readiness_nonce = _record_test_readiness(journal)
                claim_request_attempt(
                    journal,
                    LiveTrack.CREDENTIAL_POLICY_BASELINE,
                    readiness_nonce=readiness_nonce,
                )
                value = load_lifecycle_journal(journal)
                intent_event = next(
                    event
                    for event in value["events"]
                    if event["event"] == "request_send_intent"
                )
                intent_event["details"].update(mutation)
                _persist_journal(journal, value)

                with self.assertRaisesRegex(
                    ControllerError, "intent.*closed|intent.*invalid|intent_id"
                ):
                    load_lifecycle_journal(journal)

    def test_request_intent_must_cross_bind_the_durable_request_state(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = self.create(Path(directory))
            readiness_nonce = _record_test_readiness(journal)
            claim_request_attempt(
                journal,
                LiveTrack.CREDENTIAL_POLICY_BASELINE,
                readiness_nonce=readiness_nonce,
            )
            value = load_lifecycle_journal(journal)
            intent_event = next(
                event
                for event in value["events"]
                if event["event"] == "request_send_intent"
            )
            intent_event["details"]["intent_id"] = HEX_C
            _persist_journal(journal, value)

            with self.assertRaisesRegex(ControllerError, "bind"):
                load_lifecycle_journal(journal)

    def test_request_intent_before_complete_current_readiness_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = self.create(Path(directory))
            readiness_nonce = _record_test_readiness(journal)
            claim_request_attempt(
                journal,
                LiveTrack.CREDENTIAL_POLICY_BASELINE,
                readiness_nonce=readiness_nonce,
            )
            value = load_lifecycle_journal(journal)
            session = next(
                event
                for event in value["events"]
                if event["event"] == "readiness_session_started"
            )
            completion = next(
                event
                for event in value["events"]
                if event["event"] == "readiness_connect_complete"
            )
            intent = next(
                event
                for event in value["events"]
                if event["event"] == "request_send_intent"
            )
            other = [
                event
                for event in value["events"]
                if event is not session
                and event is not completion
                and event is not intent
            ]
            value["events"] = other + [session, intent, completion]
            for sequence, event in enumerate(value["events"], start=1):
                event["sequence"] = sequence
            _persist_journal(journal, value)

            with self.assertRaisesRegex(ControllerError, "complete current readiness"):
                load_lifecycle_journal(journal)

    def test_ambiguous_colima_start_requires_manual_recovery_and_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "deploy/kind/v3b-profile.json"
            profile.parent.mkdir(parents=True)
            profile.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )
            runner = FakeRunner(
                [
                    CommandResult(
                        0,
                        '{"name":"kil-v3-lab","status":"Running",'
                        '"arch":"aarch64","cpus":4,"memory":8589934592,'
                        '"disk":64424509440,"runtime":"docker"}\n',
                        "",
                    )
                ]
            )
            controller = LocalEnvoyController(
                root,
                runner,
                home=Path("/Users/lab"),
                port_probe=lambda port: False,
                tool_verifier=lambda: {},
            )
            controller._prepare_private_roots()
            journal = controller.journal_path
            create_lifecycle_journal(
                journal,
                private_root=controller.private_root,
                repository_root=root,
                docker_host=controller.docker_host,
                source_commit="d" * 40,
                execution_nonce=HEX_A,
                global_context="personal",
            )
            journal_event(
                journal,
                "preflight_complete",
                {"dedicated_profile_absent": True},
            )
            journal_event(
                journal,
                "colima_start_intent",
                {"profile": "kil-v3-lab", "command_sha256": HEX_B},
            )

            with self.assertRaisesRegex(ControllerError, "manual recovery"):
                controller.down()

            self.assertFalse(load_lifecycle_journal(journal)["profile_created"])
            flattened = [part for call, *_ in runner.calls for part in call]
            self.assertNotIn("delete", flattened)
            self.assertNotIn("stop", flattened)

    def test_successful_start_without_attestation_is_not_owned_or_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            profile = root / "deploy/kind/v3b-profile.json"
            profile.parent.mkdir(parents=True)
            profile.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )

            class FailedAttestationController(LocalEnvoyController):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.deleted = False
                    self.commands = []

                def preflight(self):
                    return {
                        "profiles": (),
                        "ports": self.profile.gateway_ports,
                        "tool_identities": TOOL_IDENTITIES,
                    }

                def _clean_source_identity(self):
                    return "d" * 40

                def _capture_global_context(self):
                    return "personal"

                def _execute(self, argv, *, timeout_s, docker=False):
                    self.commands.append(list(argv))
                    if list(argv[:3]) == ["colima", "list", "--json"]:
                        return CommandResult(
                            0,
                            "[]\n"
                            if self.deleted
                            else (
                                '{"name":"kil-v3-lab","status":"Running",'
                                '"arch":"aarch64","cpus":4,'
                                '"memory":8589934592,"disk":64424509440,'
                                '"runtime":"docker"}\n'
                            ),
                            "",
                        )
                    if argv[0:2] == ["colima", "delete"]:
                        self.deleted = True
                    return CommandResult(0, "", "")

                def _attest_colima_after_start(self, execution_nonce=None):
                    raise ControllerError("injected post-start attestation failure")

                def _assert_only_recorded_managed(self, state, *, expect_present):
                    return None

            controller = FailedAttestationController(
                root,
                FakeRunner(),
                home=Path(directory) / "home",
                port_probe=lambda port: False,
                tool_verifier=lambda: TOOL_IDENTITIES,
            )

            with self.assertRaisesRegex(ControllerError, "attestation failure"):
                controller.up()

            journal = load_lifecycle_journal(controller.journal_path)
            self.assertFalse(journal["profile_created"])
            self.assertEqual(
                [event["event"] for event in journal["events"]][-3:],
                [
                    "colima_start_returned",
                    "colima_attestation_intent",
                    "colima_attestation_failed",
                ],
            )

            with self.assertRaisesRegex(ControllerError, "manual recovery"):
                controller.down()

            self.assertFalse(controller.deleted)
            flattened = [part for command in controller.commands for part in command]
            self.assertNotIn("delete", flattened)
            self.assertNotIn("stop", flattened)

    def test_each_mutation_phase_leaves_a_recoverable_intent(self):
        phases = (
            "colima_start",
            "image_resolution",
            "image_build",
            "network_create",
            "container_create",
            "evidence_collect",
            "container_stop",
            "container_remove",
            "network_remove",
            "colima_delete",
            "publication",
        )
        for phase in phases:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                journal = self.create(root)
                journal_event(
                    journal,
                    f"{phase}_intent",
                    {"injected_failure": True},
                )
                plan = recovery_plan(load_lifecycle_journal(journal))
                self.assertEqual(plan["last_event"], f"{phase}_intent")
                self.assertTrue(plan["fail_closed"])

    def test_request_records_are_bound_to_one_successful_journal_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = self.create(root)
            value = manifest()
            track = LiveTrack.CREDENTIAL_POLICY_BASELINE
            record = request_record(value, track)
            readiness_nonce = _record_test_readiness(journal)
            claim_request_attempt(
                journal, track, readiness_nonce=readiness_nonce
            )
            _complete_request_attempt(
                journal,
                track,
                success=True,
                record_sha256=sha256(
                    (canonical_json(record) + "\n").encode("utf-8")
                ).hexdigest(),
            )
            validate_request_journal(
                [record], load_lifecycle_journal(journal), require_all=False
            )

            mutated = dict(record)
            mutated["receive_monotonic_ns"] += 1
            with self.assertRaisesRegex(ControllerError, "request.*SHA"):
                validate_request_journal(
                    [mutated], load_lifecycle_journal(journal), require_all=False
                )

            with self.assertRaisesRegex(ControllerError, "transition"):
                journal_event(
                    journal,
                    "request_send_complete",
                    {
                        "track": track.value,
                        "record_sha256": sha256(
                            (canonical_json(record) + "\n").encode("utf-8")
                        ).hexdigest(),
                    },
                )

        with tempfile.TemporaryDirectory() as directory:
            journal = self.create(Path(directory))
            track = LiveTrack.CREDENTIAL_POLICY_BASELINE
            readiness_nonce = _record_test_readiness(journal)
            claim_request_attempt(
                journal, track, readiness_nonce=readiness_nonce
            )
            with self.assertRaisesRegex(ControllerError, "null|SHA"):
                _complete_request_attempt(
                    journal, track, success=True, record_sha256=None
                )


class TeardownContinuationTest(unittest.TestCase):
    def make_freeze_controller(
        self,
        directory,
        *,
        injections=None,
        no_run=False,
        payload_overrides=None,
    ):
        root = Path(directory) / "repo"
        profile_path = root / "deploy/kind/v3b-profile.json"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_bytes(
            (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
        )
        value = manifest()
        _, requests, decisions, envoy, targets = JoinContractTest().all_records()
        payloads = {}
        for track in LiveTrack:
            payloads[(track.value, "authz_decisions")] = (
                canonical_json(
                    next(item for item in decisions if item["track"] == track.value)
                )
                + "\n"
            ).encode("utf-8")
            payloads[(track.value, "envoy_access")] = (
                canonical_json(
                    next(item for item in envoy if item["track"] == track.value)
                )
                + "\n"
            ).encode("utf-8")
            payloads[(track.value, "target_markers")] = b"".join(
                (canonical_json(item) + "\n").encode("utf-8")
                for item in targets
                if item["track"] == track.value
            )
        if no_run:
            payloads = {key: b"" for key in payloads}
        payloads.update(payload_overrides or {})

        class FreezeController(LocalEnvoyController):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.commands = []
                self.command_states = []
                self.payloads = dict(payloads)
                self.injections = dict(injections or {})
                self.bound_state = None
                self.running = set()
                self.alive = set()

            def _inspect_container(
                self,
                identifier,
                manifest_value,
                role,
                track,
                *,
                require_running=True,
            ):
                if identifier not in self.alive:
                    raise ControllerError("injected source container is absent")
                return next(
                    item
                    for item in self.bound_state["objects"]
                    if item["id"] == identifier
                )

            def _execute(self, argv, *, timeout_s, docker=False):
                command = list(argv)
                self.commands.append(command)
                self.command_states.append(set(self.running))
                objects = {item["id"]: item for item in self.bound_state["objects"]}
                if "stop" in command:
                    self.running.discard(command[-1])
                    return CommandResult(0, command[-1] + "\n", "")
                if "logs" in command:
                    item = objects[command[-1]]
                    key = (item["track"], "envoy_access")
                    if self.injections.get(key) == "command_failed":
                        raise ControllerError("injected Envoy log failure")
                    payload = self.payloads[key]
                    if self.injections.get(key) == "malformed":
                        payload = b"not-json\n"
                    if self.injections.get(key) == "duplicate":
                        payload += payload
                    return CommandResult(0, payload.decode("utf-8"), "")
                if "exec" in command:
                    identifier = command[command.index("exec") + 1]
                    item = objects[identifier]
                    source = (
                        "authz_decisions"
                        if item["role"] == "authz"
                        else "target_markers"
                    )
                    key = (item["track"], source)
                    if self.injections.get(key) == "probe_failed":
                        raise ControllerError("injected probe failure")
                    if self.injections.get(key) == "missing":
                        observation = {
                            "exists": False,
                            "regular_file": False,
                            "byte_count": None,
                            "sha256": None,
                        }
                    else:
                        payload = self.payloads[key]
                        if self.injections.get(key) == "malformed":
                            payload = b"not-json\n"
                        if self.injections.get(key) == "duplicate":
                            payload += payload
                        observation = {
                            "exists": True,
                            "regular_file": True,
                            "byte_count": len(payload),
                            "sha256": sha256(payload).hexdigest(),
                        }
                    return CommandResult(0, canonical_json(observation) + "\n", "")
                if "cp" in command:
                    source_spec = command[-2]
                    identifier = source_spec.split(":", 1)[0]
                    item = objects[identifier]
                    source = (
                        "authz_decisions"
                        if item["role"] == "authz"
                        else "target_markers"
                    )
                    key = (item["track"], source)
                    if self.injections.get(key) == "copy_error":
                        raise ControllerError("injected copy failure")
                    payload = self.payloads[key]
                    if self.injections.get(key) == "malformed":
                        payload = b"not-json\n"
                    if self.injections.get(key) == "duplicate":
                        payload += payload
                    if self.injections.get(key) == "digest_mismatch":
                        payload = payload[:-1] + b"x" if payload else b"x"
                    if self.injections.get(key) == "size_mismatch":
                        payload += b"x"
                    Path(command[-1]).write_bytes(payload)
                    return CommandResult(0, "", "")
                if "inspect" in command and "{{.State.Running}}" in command:
                    return CommandResult(
                        0, "true\n" if command[-1] in self.running else "false\n", ""
                    )
                raise AssertionError(f"unexpected freeze command: {command}")

        controller = FreezeController(
            root,
            FakeRunner(),
            home=Path(directory) / "home",
            port_probe=lambda port: False,
            tool_verifier=lambda: TOOL_IDENTITIES,
        )
        controller._prepare_private_roots()
        private_manifest = controller.private_root / "manifests/run.json"
        private_manifest.parent.mkdir(parents=True, exist_ok=True)
        private_manifest.write_text(canonical_json(value) + "\n")
        create_lifecycle_journal(
            controller.journal_path,
            private_root=controller.private_root,
            repository_root=root,
            docker_host=controller.docker_host,
            source_commit="d" * 40,
            execution_nonce="0" * 64,
            global_context="personal",
        )
        _bind_journal_manifest(controller.journal_path, private_manifest, value)
        if not no_run:
            readiness_nonce = _record_test_readiness(controller.journal_path)
            for track, record in zip(LiveTrack, requests, strict=True):
                claim_request_attempt(
                    controller.journal_path,
                    track,
                    readiness_nonce=readiness_nonce,
                )
                _complete_request_attempt(
                    controller.journal_path,
                    track,
                    success=True,
                    record_sha256=sha256(
                        (canonical_json(record) + "\n").encode("utf-8")
                    ).hexdigest(),
                )
            request_path = _runtime_root(root, value) / "requests.jsonl"
            request_path.parent.mkdir(parents=True, exist_ok=True)
            request_path.write_bytes(
                b"".join(
                    (canonical_json(record) + "\n").encode("utf-8")
                    for record in requests
                )
            )
        persist_active_state(controller.state_path, private_manifest, value)
        controller.bound_state = load_bound_active_state(controller.state_path)
        controller.running = {
            item["id"] for item in controller.bound_state["objects"]
        }
        controller.alive = set(controller.running)
        return controller, controller.bound_state, value

    def test_freeze_persists_nonce_bound_epoch_and_all_nine_terminal_legs(self):
        injections = {
            ("credential_policy_baseline", "authz_decisions"): "missing",
            ("signed_state_only", "target_markers"): "copy_error",
            ("signed_plus_local_reduce", "envoy_access"): "malformed",
        }
        with tempfile.TemporaryDirectory() as directory:
            controller, state, value = self.make_freeze_controller(
                directory, injections=injections
            )

            result = controller._freeze_sources(
                state, value, attempted_complete=True
            )

            self.assertFalse(result.complete)
            self.assertEqual(len(result.statuses), 9)
            self.assertEqual(
                {status.status for status in result.statuses},
                {"copied", "missing", "copy_error", "malformed"},
            )
            missing_status = next(
                status for status in result.statuses if status.status == "missing"
            )
            self.assertFalse(
                result.raw_paths[(missing_status.track, missing_status.source)].exists()
            )
            journal = load_lifecycle_journal(controller.journal_path)
            intents = [
                event
                for event in journal["events"]
                if event["event"] == "source_collection_intent"
            ]
            terminals = [
                event
                for event in journal["events"]
                if event["event"] == "source_collection_terminal"
            ]
            self.assertEqual(len(intents), 9)
            self.assertEqual(len(terminals), 9)
            started = next(
                event
                for event in journal["events"]
                if event["event"] == "evidence_freeze_started"
            )
            completed = next(
                event
                for event in journal["events"]
                if event["event"] == "evidence_freeze_complete"
            )
            expected_epoch = sha256(
                canonical_json(
                    {
                        "execution_nonce": "0" * 64,
                        "purpose": "v3b1-evidence-freeze-v1",
                        "run_id": value["run_id"],
                    }
                ).encode("utf-8")
            ).hexdigest()
            self.assertEqual(started["details"]["collection_epoch"], expected_epoch)
            self.assertEqual(completed["details"]["collection_epoch"], expected_epoch)
            self.assertLess(intents[-1]["sequence"], terminals[0]["sequence"])

    def test_freeze_uses_exact_closed_probe_and_accepts_observed_zero_byte_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, state, value = self.make_freeze_controller(
                directory, no_run=True
            )

            result = controller._freeze_sources(
                state, value, attempted_complete=False
            )

            empty_target = next(
                status
                for status in result.statuses
                if status.track == "signed_plus_local_reduce"
                and status.source == "target_markers"
            )
            self.assertEqual(empty_target.status, "copied")
            self.assertEqual(empty_target.source_byte_count, 0)
            self.assertEqual(empty_target.copied_byte_count, 0)
            self.assertEqual(empty_target.source_sha256, sha256(b"").hexdigest())
            probes = [command for command in controller.commands if "exec" in command]
            self.assertEqual(len(probes), 6)
            self.assertEqual(
                {command[-1] for command in probes},
                {"/evidence/decisions.jsonl", "/evidence/targets.jsonl"},
            )
            self.assertTrue(
                all("/usr/local/bin/python" in command and "-c" in command for command in probes)
            )
            self.assertTrue(all("sh" not in command and "bash" not in command for command in probes))

    def test_freeze_preserves_malformed_bytes_and_hash_binds_copy_mismatches(self):
        injections = {
            ("credential_policy_baseline", "authz_decisions"): "malformed",
            ("signed_state_only", "authz_decisions"): "digest_mismatch",
            ("signed_plus_local_reduce", "authz_decisions"): "size_mismatch",
        }
        with tempfile.TemporaryDirectory() as directory:
            controller, state, value = self.make_freeze_controller(
                directory, injections=injections
            )

            result = controller._freeze_sources(
                state, value, attempted_complete=True
            )

            by_track = {
                status.track: status
                for status in result.statuses
                if status.source == "authz_decisions"
            }
            self.assertEqual(by_track["credential_policy_baseline"].status, "malformed")
            self.assertEqual(by_track["signed_state_only"].error_class, "digest_mismatch")
            self.assertEqual(
                by_track["signed_plus_local_reduce"].error_class, "size_mismatch"
            )
            malformed_path = result.raw_paths[
                ("credential_policy_baseline", "authz_decisions")
            ]
            self.assertEqual(malformed_path.read_bytes(), b"not-json\n")
            self.assertEqual(
                sha256(malformed_path.read_bytes()).hexdigest(),
                by_track["credential_policy_baseline"].copied_sha256,
            )

    def test_probe_result_is_closed_canonical_and_rejects_nonregular_sources(self):
        empty_sha = sha256(b"").hexdigest()
        valid = {
            "exists": True,
            "regular_file": True,
            "byte_count": 0,
            "sha256": empty_sha,
        }

        self.assertEqual(
            LocalEnvoyController._parse_probe_observation(
                canonical_json(valid) + "\n"
            ),
            (True, 0, empty_sha),
        )
        for payload in (
            json.dumps(valid) + "\n",
            canonical_json({**valid, "extra": 1}) + "\n",
            canonical_json(
                {
                    "exists": True,
                    "regular_file": False,
                    "byte_count": None,
                    "sha256": None,
                }
            )
            + "\n",
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ControllerError):
                    LocalEnvoyController._parse_probe_observation(payload)

    def test_invalid_cardinality_is_malformed_and_never_builds_joins(self):
        key = ("credential_policy_baseline", "authz_decisions")
        with tempfile.TemporaryDirectory() as directory:
            controller, state, value = self.make_freeze_controller(
                directory, injections={key: "duplicate"}
            )

            freeze = controller._freeze_sources(
                state, value, attempted_complete=True
            )
            status = next(
                item
                for item in freeze.statuses
                if (item.track, item.source) == key
            )
            output, attestations, completed, rejection = (
                controller._prepare_teardown_evidence(
                    value,
                    state["objects"],
                    freeze,
                )
            )

            self.assertEqual(status.status, "malformed")
            self.assertEqual(status.error_class, "invalid_cardinality")
            self.assertFalse(completed)
            self.assertEqual(attestations, [])
            self.assertIsNone(rejection)
            self.assertEqual((output / "joins.jsonl").read_bytes(), b"")

    def test_incomplete_freeze_resets_stale_joins_and_preserves_only_copied_sources(self):
        for injected in ("missing", "malformed"):
            with (
                self.subTest(injected=injected),
                tempfile.TemporaryDirectory() as directory,
            ):
                key = ("credential_policy_baseline", "authz_decisions")
                controller, state, value = self.make_freeze_controller(
                    directory, injections={key: injected}
                )
                _, requests, decisions, envoy, targets = (
                    JoinContractTest().all_records()
                )
                raw_decisions = {
                    track: (
                        canonical_json(
                            next(
                                item
                                for item in decisions
                                if item["track"] == track.value
                            )
                        )
                        + "\n"
                    ).encode("utf-8")
                    for track in LiveTrack
                }
                seeded = write_evidence_bundle(
                    controller._private_provisional_root(),
                    value,
                    requests=requests,
                    decisions=decisions,
                    envoy=envoy,
                    targets=targets,
                    joins=join_evidence(value, requests, decisions, envoy, targets),
                    raw_decisions=raw_decisions,
                )
                self.assertNotEqual((seeded / "joins.jsonl").read_bytes(), b"")

                freeze = controller._freeze_sources(
                    state, value, attempted_complete=True
                )
                output, _, completed, rejection = (
                    controller._prepare_teardown_evidence(
                        value, state["objects"], freeze
                    )
                )

                copied_key = ("signed_state_only", "authz_decisions")
                copied_path = freeze.raw_paths[copied_key]
                self.assertFalse(completed)
                self.assertIsNone(rejection)
                self.assertEqual((output / "joins.jsonl").read_bytes(), b"")
                self.assertEqual(
                    (
                        output
                        / "raw/decisions/credential_policy_baseline.jsonl"
                    ).read_bytes(),
                    b"",
                )
                self.assertEqual(
                    (
                        output / "raw/decisions/signed_state_only.jsonl"
                    ).read_bytes(),
                    copied_path.read_bytes(),
                )

    def test_all_nine_legs_totalize_type_and_integer_parse_failures(self):
        _, _, decisions, _, _ = JoinContractTest().all_records()
        outcome_record = dict(decisions[0])
        outcome_record["outcome"] = []
        outcome_list = (canonical_json(outcome_record) + "\n").encode("utf-8")
        overlong_integer = b'{"value":' + (b"9" * 5000) + b"}\n"
        keys = [
            (track.value, source)
            for track in LiveTrack
            for source in ("envoy_access", "authz_decisions", "target_markers")
        ]
        for key in keys:
            malformed = (
                outcome_list if key[1] == "authz_decisions" else overlong_integer
            )
            with (
                self.subTest(key=key),
                tempfile.TemporaryDirectory() as directory,
            ):
                controller, state, value = self.make_freeze_controller(
                    directory, payload_overrides={key: malformed}
                )

                freeze = controller._freeze_before_service_teardown(
                    state,
                    value,
                    attempted_complete=True,
                    transient_objects=[],
                )

                selected = next(
                    status
                    for status in freeze.statuses
                    if (status.track, status.source) == key
                )
                self.assertFalse(freeze.complete)
                self.assertEqual(len(freeze.statuses), 9)
                self.assertEqual(selected.status, "malformed")
                self.assertEqual(selected.error_class, "invalid_json")
                self.assertEqual(freeze.raw_paths[key].read_bytes(), malformed)
                self.assertEqual(
                    len(
                        [
                            event
                            for event in load_lifecycle_journal(
                                controller.journal_path
                            )["events"]
                            if event["event"] == "source_collection_terminal"
                        ]
                    ),
                    9,
                )
                self.assertTrue(
                    any(
                        event["event"] == "evidence_freeze_complete"
                        for event in load_lifecycle_journal(
                            controller.journal_path
                        )["events"]
                    )
                )
                self.assertEqual(controller.running, set())

    def test_copied_ledgers_are_atomically_fsynced_before_terminal_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, state, value = self.make_freeze_controller(directory)
            actual_write = local_envoy_module._write_file
            actual_journal = local_envoy_module.journal_event
            actual_fsync = os.fsync
            actual_replace = os.replace
            active = {"key": None}
            durability = {}
            ordering = []

            def tracked_write(path, payload, mode=0o600):
                path = Path(path)
                source = {
                    "decisions.jsonl": "authz_decisions",
                    "targets.jsonl": "target_markers",
                }.get(path.name)
                key = (
                    (path.parent.name, source)
                    if source is not None and "source-freezes" in path.parts
                    else None
                )
                active["key"] = key
                if key is not None:
                    durability[key] = {"fsync": 0, "replace": 0}
                try:
                    actual_write(path, payload, mode)
                finally:
                    active["key"] = None
                if key is not None:
                    ordering.append(("durable", key, len(controller.commands)))

            def tracked_fsync(descriptor):
                if active["key"] is not None:
                    durability[active["key"]]["fsync"] += 1
                return actual_fsync(descriptor)

            def tracked_replace(source, destination):
                if active["key"] is not None:
                    durability[active["key"]]["replace"] += 1
                return actual_replace(source, destination)

            def tracked_journal(path, event, details):
                if event == "source_collection_terminal":
                    record = details["record"]
                    ordering.append(
                        (
                            "terminal",
                            (record["track"], record["source"]),
                            len(controller.commands),
                        )
                    )
                return actual_journal(path, event, details)

            with (
                mock.patch(
                    "tools.v3b1_local_envoy._write_file",
                    side_effect=tracked_write,
                ),
                mock.patch(
                    "tools.v3b1_local_envoy.os.fsync",
                    side_effect=tracked_fsync,
                ),
                mock.patch(
                    "tools.v3b1_local_envoy.os.replace",
                    side_effect=tracked_replace,
                ),
                mock.patch(
                    "tools.v3b1_local_envoy.journal_event",
                    side_effect=tracked_journal,
                ),
            ):
                controller._freeze_sources(
                    state, value, attempted_complete=True
                )

            ledger_keys = {
                (track.value, source)
                for track in LiveTrack
                for source in ("authz_decisions", "target_markers")
            }
            self.assertEqual(set(durability), ledger_keys)
            for key in ledger_keys:
                self.assertGreaterEqual(durability[key]["fsync"], 2)
                self.assertEqual(durability[key]["replace"], 1)
                durable_index = next(
                    index
                    for index, item in enumerate(ordering)
                    if item[:2] == ("durable", key)
                )
                terminal_index = next(
                    index
                    for index, item in enumerate(ordering)
                    if item[:2] == ("terminal", key)
                )
                self.assertLess(durable_index, terminal_index)

    def test_completed_freeze_recovery_reattests_private_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, state, value = self.make_freeze_controller(directory)
            freeze = controller._freeze_sources(
                state, value, attempted_complete=True
            )
            path = freeze.raw_paths[
                ("credential_policy_baseline", "authz_decisions")
            ]
            path.chmod(0o600)
            path.write_bytes(b"changed\n")

            with self.assertRaisesRegex(ControllerError, "changed"):
                controller._freeze_sources(
                    {**state, "objects": []},
                    value,
                    attempted_complete=True,
                )

    def test_freeze_recovery_skips_terminal_legs_and_never_recopies_after_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, state, value = self.make_freeze_controller(directory)
            first = controller._freeze_sources(
                state, value, attempted_complete=True
            )
            first_command_count = len(controller.commands)

            second = controller._freeze_sources(
                {**state, "objects": []}, value, attempted_complete=True
            )

            self.assertTrue(first.complete)
            self.assertTrue(second.complete)
            self.assertEqual(len(controller.commands), first_command_count)
            self.assertEqual(first.statuses, second.statuses)

    def test_incomplete_freeze_retries_only_unfinished_leg_while_source_is_alive(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, state, value = self.make_freeze_controller(directory)
            original_event = journal_event
            calls = {"terminals": 0}

            def crash_after_first_terminal(path, event, details):
                updated = original_event(path, event, details)
                if event == "source_collection_terminal":
                    calls["terminals"] += 1
                    if calls["terminals"] == 1:
                        raise RuntimeError("injected crash")
                return updated

            with mock.patch(
                "tools.v3b1_local_envoy.journal_event",
                side_effect=crash_after_first_terminal,
            ):
                with self.assertRaisesRegex(RuntimeError, "injected crash"):
                    controller._freeze_sources(
                        state, value, attempted_complete=True
                    )
            before = len(controller.commands)

            recovered = controller._freeze_sources(
                state, value, attempted_complete=True
            )

            self.assertTrue(recovered.complete)
            self.assertEqual(len(controller.commands) - before, 14)
            journal = load_lifecycle_journal(controller.journal_path)
            terminals = [
                event
                for event in journal["events"]
                if event["event"] == "source_collection_terminal"
            ]
            self.assertEqual(len(terminals), 9)

    def test_incomplete_recovery_records_dead_source_without_recopying_it(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, state, value = self.make_freeze_controller(directory)
            original_event = journal_event
            calls = {"terminals": 0}

            def crash_after_first_terminal(path, event, details):
                updated = original_event(path, event, details)
                if event == "source_collection_terminal":
                    calls["terminals"] += 1
                    if calls["terminals"] == 1:
                        raise RuntimeError("injected crash")
                return updated

            with mock.patch(
                "tools.v3b1_local_envoy.journal_event",
                side_effect=crash_after_first_terminal,
            ):
                with self.assertRaisesRegex(RuntimeError, "injected crash"):
                    controller._freeze_sources(
                        state, value, attempted_complete=True
                    )
            dead = next(
                item
                for item in state["objects"]
                if item["role"] == "target"
                and item["track"] == "signed_state_only"
            )
            controller.alive.remove(dead["id"])
            current_state = {
                **state,
                "objects": [
                    item for item in state["objects"] if item["id"] != dead["id"]
                ],
            }
            before = len(controller.commands)

            recovered = controller._freeze_sources(
                current_state, value, attempted_complete=True
            )

            status = next(
                item
                for item in recovered.statuses
                if item.container_id == dead["id"]
                and item.source == "target_markers"
            )
            self.assertFalse(recovered.complete)
            self.assertEqual(status.status, "copy_error")
            self.assertEqual(status.error_class, "command_failed")
            issued = controller.commands[before:]
            self.assertFalse(
                any(
                    dead["id"] in command
                    and ("exec" in command or "cp" in command or "logs" in command)
                    for command in issued
                )
            )

    def test_teardown_freeze_stops_all_envoys_before_capture_and_services_after_durable_freeze(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, state, value = self.make_freeze_controller(
                directory, no_run=True
            )

            result = controller._freeze_before_service_teardown(
                state,
                value,
                attempted_complete=False,
                transient_objects=[],
            )

            self.assertFalse(result.complete)
            objects = state["objects"]
            envoy_ids = {
                item["id"] for item in objects if item["role"] == "envoy"
            }
            service_ids = {
                item["id"]
                for item in objects
                if item["role"] in {"authz", "target"}
            }
            stops = [command for command in controller.commands if "stop" in command]
            self.assertEqual({command[-1] for command in stops[:3]}, envoy_ids)
            log_indexes = [
                index
                for index, command in enumerate(controller.commands)
                if "logs" in command
            ]
            probe_indexes = [
                index
                for index, command in enumerate(controller.commands)
                if "exec" in command
            ]
            self.assertEqual(len(log_indexes), 3)
            self.assertLess(max(log_indexes), min(probe_indexes))
            for command, running in zip(
                controller.commands, controller.command_states, strict=True
            ):
                if "logs" in command or "exec" in command or "cp" in command:
                    self.assertTrue(envoy_ids.isdisjoint(running))
                    self.assertTrue(service_ids.issubset(running))
            journal = load_lifecycle_journal(controller.journal_path)
            freeze_complete = next(
                event["sequence"]
                for event in journal["events"]
                if event["event"] == "evidence_freeze_complete"
            )
            service_stop_intents = [
                event["sequence"]
                for event in journal["events"]
                if event["event"] == "container_stop_intent"
                and event["details"].get("role") in {"authz", "target"}
            ]
            self.assertEqual(len(service_stop_intents), 6)
            self.assertLess(freeze_complete, min(service_stop_intents))

    def test_zero_request_freeze_builds_incomplete_nonpromotable_bundle_without_joins(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, state, value = self.make_freeze_controller(
                directory, no_run=True
            )
            freeze = controller._freeze_sources(
                state, value, attempted_complete=False
            )

            output, attestations, completed, rejection = (
                controller._prepare_teardown_evidence(
                    value,
                    state["objects"],
                    freeze,
                )
            )

            self.assertIsNotNone(output)
            self.assertEqual(attestations, [])
            self.assertFalse(completed)
            self.assertIsNone(rejection)
            self.assertEqual((output / "joins.jsonl").read_bytes(), b"")
            self.assertIn("non-promotable", (output / "summary.md").read_text())

    def test_evidence_rejection_never_blocks_exact_owned_profile_deletion(self):
        for failure in (
            "missing_file",
            "malformed_json",
            "wrong_outcome",
            "no_run",
        ):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "repo"
                profile_path = root / "deploy/kind/v3b-profile.json"
                profile_path.parent.mkdir(parents=True)
                profile_path.write_bytes(
                    (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
                )

                class InjectedDownController(LocalEnvoyController):
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, **kwargs)
                        self.commands = []
                        self.deleted = False
                        self.injected_failure = failure
                        self.bound_state = None
                        self.bound_manifest = None
                        self.request_records = []

                    def _execute(self, argv, *, timeout_s, docker=False):
                        self.commands.append(list(argv))
                        if list(argv[:3]) == ["colima", "list", "--json"]:
                            return CommandResult(
                                0,
                                "[]\n"
                                if self.deleted
                                else (
                                    '{"name":"kil-v3-lab","status":"Running",'
                                    '"arch":"aarch64","cpus":4,'
                                    '"memory":8589934592,"disk":64424509440,'
                                    '"runtime":"docker"}\n'
                                ),
                                "",
                            )
                        if "delete" in argv and argv[0] == "colima":
                            self.deleted = True
                            return CommandResult(0, "", "")
                        if "{{.State.Running}}" in argv:
                            return CommandResult(0, "false\n", "")
                        if "context" in argv and "show" in argv:
                            return CommandResult(0, "personal\n", "")
                        return CommandResult(0, "", "")

                    def _attest_colima_after_start(self, execution_nonce=None):
                        return {"test_attestation": True}

                    def _load_for_down(self):
                        return (
                            self.bound_state,
                            self.bound_manifest,
                            load_lifecycle_journal(self.journal_path),
                        )

                    def _assert_only_recorded_managed(self, state, *, expect_present):
                        return None

                    def _inspect_container(self, identifier, manifest_value, role, track, *, require_running=True):
                        return next(
                            item
                            for item in self.bound_state["objects"]
                            if item["id"] == identifier
                        )

                    def _inspect_network(self, identifier, manifest_value, track, *, require_complete_membership=True):
                        return next(
                            item
                            for item in self.bound_state["network_objects"]
                            if item["id"] == identifier
                        )

                    def _docker_object_exists(self, kind, identifier):
                        return False

                    def _request_records(self, manifest_value):
                        return list(self.request_records)

                controller = InjectedDownController(
                    root,
                    FakeRunner(),
                    home=Path(directory) / "home",
                    port_probe=lambda port: False,
                    tool_verifier=lambda: TOOL_IDENTITIES,
                )
                controller._prepare_private_roots()
                value = manifest(
                    docker_host=controller.docker_host,
                    execution_nonce=HEX_A,
                )
                private_manifest = controller.private_root / "manifests/run.json"
                private_manifest.parent.mkdir(parents=True, exist_ok=True)
                private_manifest.write_text(canonical_json(value) + "\n")
                create_lifecycle_journal(
                    controller.journal_path,
                    private_root=controller.private_root,
                    repository_root=root,
                    docker_host=controller.docker_host,
                    source_commit="d" * 40,
                    execution_nonce=HEX_A,
                    global_context="personal",
                )
                journal_event(
                    controller.journal_path,
                    "preflight_complete",
                    {"tool_identities": TOOL_IDENTITIES},
                )
                journal_event(
                    controller.journal_path,
                    "colima_attestation_complete",
                    {"profile": "kil-v3-lab", "attestation": {}},
                )
                journal_event(
                    controller.journal_path,
                    "engine_provenance_observed",
                    ENGINE_PROVENANCE,
                )
                _bind_journal_manifest(
                    controller.journal_path, private_manifest, value
                )
                persist_active_state(
                    controller.state_path, private_manifest, value
                )
                controller.bound_state = load_bound_active_state(
                    controller.state_path
                )
                controller.bound_manifest = value
                _, requests, _, _, _ = JoinContractTest().all_records()
                controller.request_records = requests
                if failure != "no_run":
                    readiness_nonce = _record_test_readiness(controller.journal_path)
                    for track, record in zip(LiveTrack, requests, strict=True):
                        claim_request_attempt(
                            controller.journal_path,
                            track,
                            readiness_nonce=readiness_nonce,
                        )
                        _complete_request_attempt(
                            controller.journal_path,
                            track,
                            success=True,
                            record_sha256=sha256(
                                (canonical_json(record) + "\n").encode("utf-8")
                            ).hexdigest(),
                        )

                published = controller.down()

                self.assertTrue(controller.deleted)
                self.assertTrue(
                    any(command[0:2] == ["colima", "delete"] for command in controller.commands)
                )
                public_manifest = json.loads(
                    (published / "manifest.json").read_text()
                )
                self.assertFalse(public_manifest["run_complete"])
                self.assertIn("failure", public_manifest["bundle_class"])
                if failure == "no_run":
                    self.assertEqual((published / "joins.jsonl").read_bytes(), b"")

    def test_post_delete_recovery_reconstructs_pending_failure_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            profile_path = root / "deploy/kind/v3b-profile.json"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )

            class PostDeleteRecoveryController(LocalEnvoyController):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.commands = []

                def _execute(self, argv, *, timeout_s, docker=False):
                    self.commands.append(list(argv))
                    if list(argv[:3]) == ["colima", "list", "--json"]:
                        return CommandResult(0, "[]\n", "")
                    if "context" in argv and "show" in argv:
                        return CommandResult(0, "personal\n", "")
                    raise AssertionError(f"unexpected recovery command: {argv}")

            controller = PostDeleteRecoveryController(
                root,
                FakeRunner(),
                home=Path(directory) / "home",
                port_probe=lambda port: False,
                tool_verifier=lambda: TOOL_IDENTITIES,
            )
            controller._prepare_private_roots()
            value, requests, decisions, envoy, targets = (
                JoinContractTest().all_records()
            )
            private_manifest = controller.private_root / "manifests/run.json"
            private_manifest.write_text(canonical_json(value) + "\n")
            create_lifecycle_journal(
                controller.journal_path,
                private_root=controller.private_root,
                repository_root=root,
                docker_host=controller.docker_host,
                source_commit="d" * 40,
                execution_nonce=HEX_A,
                global_context="personal",
            )
            journal_event(
                controller.journal_path,
                "preflight_complete",
                {"tool_identities": TOOL_IDENTITIES},
            )
            journal_event(
                controller.journal_path,
                "colima_attestation_complete",
                {"profile": "kil-v3-lab", "attestation": {}},
            )
            journal_event(
                controller.journal_path,
                "engine_provenance_observed",
                ENGINE_PROVENANCE,
            )
            _bind_journal_manifest(
                controller.journal_path, private_manifest, value
            )
            stale = write_evidence_bundle(
                controller.provisional_root,
                value,
                requests=requests,
                decisions=decisions,
                envoy=envoy,
                targets=targets,
                joins=join_evidence(value, requests, decisions, envoy, targets),
            )
            stale_authority = authoritative_bundle_attestation(stale)
            journal_event(
                controller.journal_path,
                "evidence_collect_complete",
                {
                    "completed": False,
                    "bundle_sha256": sha256(
                        (stale / "SHA256SUMS").read_bytes()
                    ).hexdigest(),
                    "authoritative_attestation": stale_authority,
                },
            )
            journal_event(
                controller.journal_path,
                "colima_delete_intent",
                {"profile": "kil-v3-lab"},
            )
            journal_event(
                controller.journal_path,
                "colima_delete_complete",
                {"profile": "kil-v3-lab", "verified_absent": True},
            )
            intent = journal_event(
                controller.journal_path,
                "post_teardown_failure_bundle_intent",
                {
                    "run_id": value["run_id"],
                    "evidence_rejection": "injected collection rejection",
                    "replacement": "deterministic_empty_failure_v1",
                },
            )
            intent_sequence = len(intent["events"])

            # Crash point: replacement is complete, but its authority was not journaled.
            _prepare_failure_provisional(
                controller.provisional_root, value, reset=True
            )

            published = controller.down()

            public_manifest = json.loads((published / "manifest.json").read_text())
            self.assertFalse(public_manifest["run_complete"])
            self.assertEqual(public_manifest["promotion_status"], "not_promoted")
            self.assertIn("failure", public_manifest["bundle_class"])
            self.assertNotEqual(
                public_manifest["authoritative_bundle_sha256"],
                stale_authority["binding_sha256"],
            )
            self.assertEqual(
                [command for command in controller.commands if "delete" in command],
                [],
            )
            archived = controller.completed_root / f"{value['run_id']}.journal.json"
            recovered = load_lifecycle_journal(archived)
            completions = [
                event
                for event in recovered["events"]
                if event["event"] == "post_teardown_failure_bundle_prepared"
                and event["details"].get("intent_sequence") == intent_sequence
            ]
            self.assertEqual(len(completions), 1)
            recovered_authority = completions[0]["details"][
                "authoritative_attestation"
            ]
            self.assertEqual(
                public_manifest["authoritative_bundle_sha256"],
                recovered_authority["binding_sha256"],
            )
            self.assertEqual(
                list(controller.evidence_root.iterdir()), [published]
            )


class RuntimeAttestationTest(unittest.TestCase):
    def test_minimal_staged_build_context_is_exact_and_hashed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            staging = Path(directory) / "private/context"
            for relative in (
                "README.md",
                "pyproject.toml",
                "deploy/kind/Dockerfile.v3b",
                "deploy/kind/Dockerfile.v3b.dockerignore",
                "deploy/kind/requirements-v3b-build.txt",
                "deploy/kind/requirements-v3b-runtime.txt",
                "src/kil/__init__.py",
                "src/kil/canonical.py",
                "src/kil/decay.py",
                "src/kil/domain.py",
                "src/kil/engine.py",
                "src/kil/ext_authz_http.py",
                "src/kil/live_authz.py",
                "src/kil/q_state.py",
                "src/kil/target_http.py",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(relative + "\n")
            extra = root / "secret.txt"
            extra.write_text("must not stage\n")

            attestation = stage_build_context(root, staging)

            staged = {
                path.relative_to(staging).as_posix()
                for path in staging.rglob("*")
                if path.is_file()
            }
            self.assertNotIn("secret.txt", staged)
            self.assertEqual(staged, set(attestation["files"]))
            self.assertRegex(attestation["context_sha256"], r"^[a-f0-9]{64}$")

    def test_container_attestation_closes_security_resources_mounts_and_ports(self):
        expected = {
            "name": "kil-v3b1-authz-track",
            "role": "authz",
            "track": LiveTrack.SIGNED_STATE_ONLY.value,
            "image_id": KIL_IMAGE_ID,
            "network": "kil-v3b1-network-track",
            "config_path": "/private/authz.json",
            "config_sha256": HEX_A,
            "gateway_port": None,
        }
        actual = {
            "id": "9" * 64,
            "name": expected["name"],
            "image_id": KIL_IMAGE_ID,
            "user": "65532:65532",
            "readonly_rootfs": True,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges"],
            "nano_cpus": 500_000_000,
            "memory": 268_435_456,
            "memory_swap": 268_435_456,
            "pids_limit": 128,
            "restart_policy": "no",
            "stop_timeout": 10,
            "log_driver": "json-file",
            "log_options": {"max-file": "1", "max-size": "1m"},
            "tmpfs": {
                "/evidence": "rw,noexec,nosuid,nodev,size=16m,uid=65532,gid=65532,mode=0700",
                "/tmp": "rw,noexec,nosuid,nodev,size=16m,uid=65532,gid=65532,mode=0700",
            },
            "mounts": [
                {
                    "source": expected["config_path"],
                    "destination": "/config/authz.json",
                    "rw": False,
                }
            ],
            "networks": [expected["network"]],
            "port_bindings": {},
            "platform": "linux/arm64",
            "entrypoint": [],
            "command": [
                "python",
                "-c",
                (
                    "import os,runpy;"
                    "fd=os.open('/evidence/decisions.jsonl',"
                    "os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);"
                    "os.close(fd);"
                    "runpy.run_module('kil.ext_authz_http',run_name='__main__')"
                ),
                "--config",
                "/config/authz.json",
            ],
            "environment": ["PATH=/usr/local/bin"],
        }
        validated = validate_container_attestation(actual, expected)
        self.assertEqual(validated["id"], "9" * 64)
        for mutation, message in (
            (("readonly_rootfs", False), "read-only"),
            (("memory_swap", 536_870_912), "memory"),
            (("networks", ["cross-track"]), "network"),
        ):
            broken = dict(actual)
            broken[mutation[0]] = mutation[1]
            with self.assertRaisesRegex(ControllerError, message):
                validate_container_attestation(broken, expected)

    def test_stopped_envoy_accepts_only_exact_image_and_runtime_label_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            profile_path = root / "deploy/kind/v3b-profile.json"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )
            controller = LocalEnvoyController(
                root,
                FakeRunner(),
                home=Path(directory) / "home",
                port_probe=lambda port: False,
                tool_verifier=lambda: TOOL_IDENTITIES,
            )
            controller._prepare_private_roots()
            value = manifest()
            track = LiveTrack.CREDENTIAL_POLICY_BASELINE
            track_value = next(
                item for item in value["tracks"] if item["track"] == track.value
            )
            config_path = controller._config_path(value, "envoy", track.value)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text("{}\n")
            config_path.chmod(0o444)
            runtime_labels = {
                "kil.v3b1.managed": "true",
                "kil.v3b1.run-id": value["run_id"],
                "kil.v3b1.role": "envoy",
                "kil.v3b1.track": track.value,
            }
            immutable_labels = {"org.opencontainers.image.version": "22.04"}

            def inspections(
                *,
                image_labels=immutable_labels,
                container_labels=None,
            ):
                merged = {**image_labels, **runtime_labels}
                if container_labels is not None:
                    merged = container_labels
                container = {
                    "Id": "9" * 64,
                    "Name": f"/{track_value['envoy_container']}",
                    "Image": value["envoy_image_id"],
                    "Config": {
                        "Image": value["envoy_image_digest"],
                        "Labels": merged,
                        "User": "65532:65532",
                        "StopTimeout": 10,
                        "Entrypoint": ["/usr/local/bin/envoy"],
                        "Cmd": [
                            "--config-path",
                            "/etc/envoy/envoy.json",
                            "--disable-hot-restart",
                            "--concurrency",
                            "1",
                        ],
                        "Env": ["PATH=/usr/local/bin"],
                    },
                    "HostConfig": {
                        "ReadonlyRootfs": True,
                        "CapDrop": ["ALL"],
                        "SecurityOpt": ["no-new-privileges"],
                        "NanoCpus": 500_000_000,
                        "Memory": 268_435_456,
                        "MemorySwap": 268_435_456,
                        "PidsLimit": 128,
                        "RestartPolicy": {"Name": "no"},
                        "LogConfig": {
                            "Type": "json-file",
                            "Config": {"max-file": "1", "max-size": "1m"},
                        },
                        "Tmpfs": {
                            "/tmp": "rw,noexec,nosuid,nodev,size=16777216,uid=65532,gid=65532,mode=448"
                        },
                        "PortBindings": {
                            "8080/tcp": [
                                {
                                    "HostIp": "127.0.0.1",
                                    "HostPort": str(track_value["gateway_port"]),
                                }
                            ]
                        },
                    },
                    "State": {"Running": False},
                    "NetworkSettings": {
                        "Networks": {track_value["network"]: {}}
                    },
                    "Mounts": [
                        {
                            "Source": str(config_path),
                            "Destination": "/etc/envoy/envoy.json",
                            "RW": False,
                        }
                    ],
                }
                image = {
                    "Os": "linux",
                    "Architecture": "arm64",
                    "Config": {
                        "Env": ["PATH=/usr/local/bin"],
                        "Labels": image_labels,
                    },
                }
                return [
                    CommandResult(0, canonical_json(container) + "\n", ""),
                    CommandResult(0, canonical_json(image) + "\n", ""),
                ]

            controller.runner = FakeRunner(inspections())
            inspected = controller._inspect_container(
                "9" * 64,
                value,
                "envoy",
                track.value,
                require_running=False,
            )
            self.assertEqual(inspected["labels"], runtime_labels)

            conflict_labels = {
                **immutable_labels,
                "kil.v3b1.role": "image-owned-conflict",
            }
            controller.runner = FakeRunner(inspections(image_labels=conflict_labels))
            with self.assertRaisesRegex(ControllerError, "label.*conflict"):
                controller._inspect_container(
                    "9" * 64,
                    value,
                    "envoy",
                    track.value,
                    require_running=False,
                )

            for reserved_labels in (
                {
                    **immutable_labels,
                    "kil.v3b1.role": "envoy",
                },
                {
                    **immutable_labels,
                    "kil.v3b1.future-reserved": "image-owned",
                },
            ):
                with self.subTest(reserved_labels=reserved_labels):
                    controller.runner = FakeRunner(
                        inspections(image_labels=reserved_labels)
                    )
                    with self.assertRaisesRegex(
                        ControllerError, "reserved.*label|label.*namespace"
                    ):
                        controller._inspect_container(
                            "9" * 64,
                            value,
                            "envoy",
                            track.value,
                            require_running=False,
                        )

            controller.runner = FakeRunner(
                inspections(
                    container_labels={
                        **immutable_labels,
                        **runtime_labels,
                        "unexpected.runtime.label": "forbidden",
                    }
                )
            )
            with self.assertRaisesRegex(ControllerError, "labels.*exact|label.*extra"):
                controller._inspect_container(
                    "9" * 64,
                    value,
                    "envoy",
                    track.value,
                    require_running=False,
                )

    def test_stopped_transient_validator_uses_exact_immutable_label_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            profile_path = root / "deploy/kind/v3b-profile.json"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )
            value = manifest()
            track = LiveTrack.SIGNED_STATE_ONLY
            runtime_labels = {
                "kil.v3b1.managed": "true",
                "kil.v3b1.run-id": value["run_id"],
                "kil.v3b1.role": "validator",
                "kil.v3b1.track": track.value,
            }
            immutable_labels = {"org.opencontainers.image.version": "22.04"}
            name = (
                f"kil-v3b1-validate-{track.value.replace('_', '-')}-"
                f"{str(value['content_identity_sha256'])[:12]}"
            )
            raw = {
                "Id": "8" * 64,
                "Name": f"/{name}",
                "Image": value["envoy_image_id"],
                "Config": {
                    "Image": value["envoy_image_digest"],
                    "Labels": {**immutable_labels, **runtime_labels},
                    "User": "65532:65532",
                    "Entrypoint": ["/usr/local/bin/envoy"],
                    "Cmd": [
                        "--mode",
                        "validate",
                        "--config-path",
                        "/etc/envoy/envoy.json",
                        "--disable-hot-restart",
                        "--concurrency",
                        "1",
                    ],
                },
                "HostConfig": {
                    "ReadonlyRootfs": True,
                    "CapDrop": ["ALL"],
                    "SecurityOpt": ["no-new-privileges"],
                    "NetworkMode": "none",
                    "PortBindings": {},
                },
                "State": {"Running": False},
            }
            image = {
                "Os": "linux",
                "Architecture": "arm64",
                "Config": {"Labels": immutable_labels},
            }
            controller = LocalEnvoyController(
                root,
                FakeRunner(
                    [
                        CommandResult(0, canonical_json(raw) + "\n", ""),
                        CommandResult(0, canonical_json(image) + "\n", ""),
                    ]
                ),
                home=Path(directory) / "home",
                port_probe=lambda port: False,
                tool_verifier=lambda: TOOL_IDENTITIES,
            )
            controller._prepare_private_roots()

            inspected = controller._inspect_validation_container(
                "8" * 64, value, track
            )

            self.assertEqual(inspected["labels"], runtime_labels)
            self.assertFalse(raw["State"]["Running"])

    def test_network_inspection_uses_one_closed_json_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            profile_path = root / "deploy/kind/v3b-profile.json"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )
            value = manifest()
            track = LiveTrack.CREDENTIAL_POLICY_BASELINE
            track_value = next(
                item for item in value["tracks"] if item["track"] == track.value
            )
            labels = {
                "kil.v3b1.managed": "true",
                "kil.v3b1.run-id": value["run_id"],
                "kil.v3b1.track": track.value,
            }
            member_names = [
                track_value["authz_container"],
                track_value["target_container"],
                track_value["envoy_container"],
            ]

            def member(name):
                return {
                    "Name": name,
                    "EndpointID": "e" * 64,
                    "MacAddress": "02:42:ac:12:00:02",
                    "IPv4Address": "172.18.0.2/16",
                    "IPv6Address": "",
                }

            network = {
                "Id": "a" * 64,
                "Name": track_value["network"],
                "Driver": "bridge",
                "Internal": True,
                "Labels": labels,
                "Containers": {
                    f"{index}" * 64: member(name)
                    for index, name in enumerate(member_names, start=1)
                },
                "Created": "2026-08-30T00:00:00Z",
                "Scope": "local",
            }
            observed_literal = (
                f"{network['Id']}\\n{network['Name']}\\nbridge\\ntrue\\n"
                f"{canonical_json(labels)}\n"
            )

            class NetworkRunner(FakeRunner):
                def __init__(self, payload):
                    super().__init__()
                    self.payload = payload

                def run(self, argv, **kwargs):
                    self.calls.append((list(argv), kwargs))
                    template = argv[argv.index("--format") + 1]
                    if template == "{{json .}}":
                        return CommandResult(
                            0, canonical_json(self.payload) + "\n", ""
                        )
                    return CommandResult(0, observed_literal, "")

            runner = NetworkRunner(network)
            controller = LocalEnvoyController(
                root,
                runner,
                home=Path(directory) / "home",
                port_probe=lambda port: False,
                tool_verifier=lambda: TOOL_IDENTITIES,
            )
            controller._prepare_private_roots()

            inspected = controller._inspect_network(
                "a" * 64, value, track.value
            )

            self.assertEqual(inspected["name"], track_value["network"])
            self.assertEqual(len(runner.calls), 1)
            self.assertIn("{{json .}}", runner.calls[0][0])

            partial = {**network, "Containers": {
                "1" * 64: member(member_names[0])
            }}
            controller.runner = NetworkRunner(partial)
            controller._inspect_network(
                "a" * 64,
                value,
                track.value,
                require_complete_membership=False,
            )

            malformed = {**network, "Internal": "true"}
            duplicate = {
                **network,
                "Containers": {
                    **network["Containers"],
                    "f" * 64: member(member_names[0]),
                },
            }
            unknown = {
                **network,
                "Containers": {
                    "f" * 64: member("kil-v3b1-attacker")
                },
            }
            extra_label = {
                **network,
                "Labels": {**labels, "kil.v3b1.role": "network"},
            }
            for rejected, message in (
                (malformed, "network.*type|shape"),
                (duplicate, "duplicate.*membership|membership"),
                (unknown, "cross-track|membership"),
                (extra_label, "label"),
            ):
                with self.subTest(message=message):
                    controller.runner = NetworkRunner(rejected)
                    with self.assertRaisesRegex(ControllerError, message):
                        controller._inspect_network(
                            "a" * 64,
                            value,
                            track.value,
                            require_complete_membership=False,
                        )

    def test_image_architecture_is_exact_linux_arm64(self):
        validate_image_architecture({"Os": "linux", "Architecture": "arm64"})
        with self.assertRaisesRegex(ControllerError, "architecture"):
            validate_image_architecture({"Os": "linux", "Architecture": "amd64"})

class EvidenceBundleTest(unittest.TestCase):
    def test_bundle_is_canonical_complete_checksummed_and_claim_bounded(self):
        value, requests, decisions, envoy, targets = JoinContractTest().all_records()
        joins = join_evidence(value, requests, decisions, envoy, targets)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            output = write_evidence_bundle(
                root,
                value,
                requests=requests,
                decisions=decisions,
                envoy=envoy,
                targets=targets,
                joins=joins,
            )

            self.assertEqual(output.name, value["run_id"])
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {
                    "requests.jsonl",
                    "decisions.jsonl",
                    "envoy.jsonl",
                    "targets.jsonl",
                    "joins.jsonl",
                    "manifest.json",
                    "summary.md",
                    "SHA256SUMS",
                    "raw",
                },
            )
            for name in (
                "requests.jsonl",
                "decisions.jsonl",
                "envoy.jsonl",
                "targets.jsonl",
                "joins.jsonl",
            ):
                for line in (output / name).read_text().splitlines():
                    self.assertEqual(line, canonical_json(json.loads(line)))
            normalized = [
                json.loads(line)
                for line in (output / "decisions.jsonl").read_text().splitlines()
            ]
            self.assertTrue(
                all(
                    item["schema_version"]
                    == "kil.v3b1-collected-decision.v1"
                    and item["source_schema_version"]
                    == "kil.v3b-authz-record.v1"
                    and item["run_id_provenance"]
                    == "manifest_attested_enrichment"
                    for item in normalized
                )
            )
            with self.assertRaisesRegex(ControllerError, "attested resume"):
                write_evidence_bundle(
                    root,
                    value,
                    requests=requests,
                    decisions=decisions,
                    envoy=envoy,
                    targets=targets,
                    joins=joins,
                )
            manifest_line = (output / "manifest.json").read_text().strip()
            self.assertEqual(manifest_line, canonical_json(json.loads(manifest_line)))
            summary = (output / "summary.md").read_text().lower()
            self.assertIn("local_envoy_boundary", summary)
            self.assertIn("teardown: pending", summary)
            self.assertNotIn("teardown: complete", summary)
            for forbidden in (
                "kind_cluster_validated",
                "historical prevention",
                "production performance",
            ):
                self.assertNotIn(forbidden, summary)
            sums = (output / "SHA256SUMS").read_text().splitlines()
            self.assertEqual(len(sums), 10)
            for line in sums:
                digest, name = line.split("  ", 1)
                self.assertEqual(
                    digest, sha256((output / name).read_bytes()).hexdigest()
                )

            finalize_teardown_evidence(output, value["run_id"])
            finalized = json.loads((output / "manifest.json").read_text())
            self.assertEqual(finalized["teardown"]["status"], "complete")
            self.assertIn(
                "teardown: complete",
                (output / "summary.md").read_text().lower(),
            )
            for line in (output / "SHA256SUMS").read_text().splitlines():
                digest, name = line.split("  ", 1)
                self.assertEqual(
                    digest, sha256((output / name).read_bytes()).hexdigest()
                )

    def test_publication_is_atomic_sanitized_attested_and_checksum_complete(self):
        value, requests, decisions, envoy, targets = JoinContractTest().all_records()
        joins = join_evidence(value, requests, decisions, envoy, targets)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provisional_parent = root / "private"
            provisional = write_evidence_bundle(
                provisional_parent,
                value,
                requests=requests,
                decisions=decisions,
                envoy=envoy,
                targets=targets,
                joins=joins,
            )
            authoritative = authoritative_bundle_attestation(provisional)
            public_parent = root / "public"
            def payload(records):
                return b"".join(
                    (canonical_json(record) + "\n").encode("utf-8")
                    for record in records
                )

            source_attestations = [
                {
                    "track": track.value,
                    "container_ids": {
                        "authz": f"{index + 1}" * 64,
                        "target": f"{index + 4}" * 64,
                        "envoy": f"{index + 7}" * 64,
                    },
                    "image_ids": {
                        "authz": KIL_IMAGE_ID,
                        "target": KIL_IMAGE_ID,
                        "envoy": f"sha256:{HEX_B}",
                    },
                    "config_sha256": {
                        "authz": HEX_A,
                        "target": HEX_A,
                        "envoy": HEX_A,
                    },
                    "raw_decisions_sha256": sha256(
                        (
                            provisional
                            / "raw/decisions"
                            / f"{track.value}.jsonl"
                        ).read_bytes()
                    ).hexdigest(),
                    "raw_decision_count": 1,
                    "raw_envoy_sha256": sha256(
                        payload(
                            [
                                record
                                for record in envoy
                                if record["track"] == track.value
                            ]
                        )
                    ).hexdigest(),
                    "raw_envoy_count": 1,
                    "raw_targets_sha256": sha256(
                        payload(
                            [
                                record
                                for record in targets
                                if record["track"] == track.value
                            ]
                        )
                    ).hexdigest(),
                    "raw_target_count": 0 if index == 2 else 1,
                }
                for index, track in enumerate(LiveTrack)
            ]

            extra_raw = provisional / "raw/decisions/extra.jsonl"
            extra_raw.write_text("{}\n")
            with self.assertRaisesRegex(ControllerError, "artifact set"):
                finalize_publication(
                    provisional,
                    public_parent,
                    value,
                    source_attestations=source_attestations,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                )
            extra_raw.unlink()
            wrong_sources = [dict(item) for item in source_attestations]
            wrong_sources[0]["raw_decisions_sha256"] = HEX_A
            with self.assertRaisesRegex(ControllerError, "source bytes"):
                finalize_publication(
                    provisional,
                    public_parent,
                    value,
                    source_attestations=wrong_sources,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                )

            missing_tool = dict(TOOL_IDENTITIES)
            missing_tool.pop("kubectl")
            with self.assertRaisesRegex(ControllerError, "tool.*closed|tool.*set"):
                finalize_publication(
                    provisional,
                    public_parent,
                    value,
                    source_attestations=source_attestations,
                    tool_identities=missing_tool,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                )
            extra_engine = {**ENGINE_PROVENANCE, "socket": "/Users/lab/docker.sock"}
            with self.assertRaisesRegex(ControllerError, "engine.*closed"):
                finalize_publication(
                    provisional,
                    public_parent,
                    value,
                    source_attestations=source_attestations,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=extra_engine,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                )

            outside_public = root / "outside-public"
            outside_public.mkdir()
            linked_public = root / "linked-public"
            linked_public.symlink_to(outside_public, target_is_directory=True)
            with self.assertRaisesRegex(ControllerError, "symbolic|contained"):
                finalize_publication(
                    provisional,
                    linked_public,
                    value,
                    source_attestations=source_attestations,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                    repository_root=root,
                )
            linked_public.unlink()
            outside_staging = root / "outside-staging"
            outside_staging.mkdir()
            publication_staging = provisional.parent / ".publication-staging"
            publication_staging.symlink_to(
                outside_staging, target_is_directory=True
            )
            with self.assertRaisesRegex(ControllerError, "symbolic|contained"):
                finalize_publication(
                    provisional,
                    public_parent,
                    value,
                    source_attestations=source_attestations,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                    repository_root=root,
                )
            publication_staging.unlink()

            authoritative_bytes = {
                path.relative_to(provisional).as_posix(): path.read_bytes()
                for path in provisional.rglob("*")
                if path.is_file()
            }

            for authoritative_name in (
                "requests.jsonl",
                "decisions.jsonl",
                "joins.jsonl",
            ):
                with self.subTest(authoritative_name=authoritative_name):
                    authoritative_path = provisional / authoritative_name
                    original = authoritative_path.read_bytes()
                    authoritative_path.chmod(0o600)
                    authoritative_path.write_bytes(original + b"\n")
                    sums_path = provisional / "SHA256SUMS"
                    original_sums = sums_path.read_bytes()
                    sums_path.chmod(0o600)
                    rewritten_sums = []
                    for line in original_sums.decode("ascii").splitlines():
                        _, relative = line.split("  ", 1)
                        digest = (
                            sha256(authoritative_path.read_bytes()).hexdigest()
                            if relative == authoritative_name
                            else line.split("  ", 1)[0]
                        )
                        rewritten_sums.append(f"{digest}  {relative}\n")
                    sums_path.write_text("".join(rewritten_sums), encoding="ascii")
                    sums_path.chmod(0o444)
                    with self.assertRaisesRegex(
                        ControllerError, "authoritative.*binding|authoritative.*changed"
                    ):
                        finalize_publication(
                            provisional,
                            public_parent,
                            value,
                            source_attestations=source_attestations,
                            tool_identities=TOOL_IDENTITIES,
                            engine_provenance=ENGINE_PROVENANCE,
                            global_context_before="personal",
                            global_context_after="personal",
                            completed=True,
                            authoritative_attestation=authoritative,
                        )
                    self.assertFalse((public_parent / value["run_id"]).exists())
                    authoritative_path.write_bytes(original)
                    authoritative_path.chmod(0o444)
                    sums_path.chmod(0o600)
                    sums_path.write_bytes(original_sums)
                    sums_path.chmod(0o444)
                    self.assertEqual(
                        {
                            path.relative_to(provisional).as_posix(): path.read_bytes()
                            for path in provisional.rglob("*")
                            if path.is_file()
                        },
                        authoritative_bytes,
                    )

            def fail_after_manifest(stage, path):
                if stage == "after_public_manifest":
                    raise RuntimeError("injected publication crash")

            with self.assertRaisesRegex(RuntimeError, "injected publication"):
                finalize_publication(
                    provisional,
                    public_parent,
                    value,
                    source_attestations=source_attestations,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                    publication_fault=fail_after_manifest,
                )
            self.assertFalse((public_parent / value["run_id"]).exists())
            self.assertEqual(
                {
                    path.relative_to(provisional).as_posix(): path.read_bytes()
                    for path in provisional.rglob("*")
                    if path.is_file()
                },
                authoritative_bytes,
            )

            def mutate_staged_request(stage, path):
                if stage == "after_public_manifest":
                    request_path = path / "requests.jsonl"
                    request_path.chmod(0o600)
                    request_path.write_bytes(b"{}\n")

            with self.assertRaisesRegex(
                ControllerError, "artifact hash|source attestation|request"
            ):
                finalize_publication(
                    provisional,
                    public_parent,
                    value,
                    source_attestations=source_attestations,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                    publication_fault=mutate_staged_request,
                )
            self.assertFalse((public_parent / value["run_id"]).exists())
            self.assertEqual(
                {
                    path.relative_to(provisional).as_posix(): path.read_bytes()
                    for path in provisional.rglob("*")
                    if path.is_file()
                },
                authoritative_bytes,
            )

            def mutate_staged_summary(stage, path):
                if stage == "after_public_manifest":
                    summary_path = path / "summary.md"
                    summary_path.chmod(0o600)
                    summary_path.write_text("mutated staged summary\n")

            with self.assertRaisesRegex(ControllerError, "summary"):
                finalize_publication(
                    provisional,
                    public_parent,
                    value,
                    source_attestations=source_attestations,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                    publication_fault=mutate_staged_summary,
                )
            self.assertFalse((public_parent / value["run_id"]).exists())
            self.assertEqual(
                {
                    path.relative_to(provisional).as_posix(): path.read_bytes()
                    for path in provisional.rglob("*")
                    if path.is_file()
                },
                authoritative_bytes,
            )

            published = finalize_publication(
                provisional,
                public_parent,
                value,
                source_attestations=source_attestations,
                tool_identities=TOOL_IDENTITIES,
                engine_provenance=ENGINE_PROVENANCE,
                global_context_before="personal",
                global_context_after="personal",
                completed=True,
                authoritative_attestation=authoritative,
            )

            self.assertEqual(published, public_parent / value["run_id"])
            self.assertTrue(provisional.exists())
            self.assertEqual(
                {
                    path.relative_to(provisional).as_posix(): path.read_bytes()
                    for path in provisional.rglob("*")
                    if path.is_file()
                },
                authoritative_bytes,
            )
            public_manifest = json.loads(
                (published / "manifest.json").read_text()
            )
            encoded = canonical_json(public_manifest)
            self.assertNotIn("/Users/", encoded)
            self.assertNotIn("docker_host", public_manifest)
            self.assertEqual(
                public_manifest["bundle_class"],
                "intermediate_provisional_local_boundary",
            )
            self.assertEqual(public_manifest["promotion_status"], "not_promoted")
            self.assertEqual(
                public_manifest["evidence_policy"],
                {"inputs": "modeled", "outputs": "observed"},
            )
            self.assertEqual(
                public_manifest["source_attestations"], source_attestations
            )
            self.assertEqual(
                public_manifest["artifact_hash_rule"],
                "sha256_excludes_manifest_summary_and_SHA256SUMS",
            )
            self.assertEqual(
                public_manifest["authoritative_bundle_sha256"],
                authoritative["binding_sha256"],
            )
            verify_public_checksums(published)
            with self.assertRaisesRegex(ControllerError, "clobber"):
                finalize_publication(
                    published,
                    public_parent,
                    value,
                    source_attestations=source_attestations,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                )

            extra = published / "unchecked.txt"
            extra.write_text("unchecked\n")
            with self.assertRaisesRegex(ControllerError, "unchecked|complete"):
                verify_public_checksums(published)
            extra.unlink()
            sums = (published / "SHA256SUMS").read_text().splitlines()
            (published / "SHA256SUMS").chmod(0o600)
            (published / "SHA256SUMS").write_text("\n".join(sums[:-1]) + "\n")
            with self.assertRaisesRegex(ControllerError, "omission|complete"):
                verify_public_checksums(published)

    def test_incomplete_run_publishes_nonpromotable_failure_bundle(self):
        value, requests, _, _, _ = JoinContractTest().all_records()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provisional = _prepare_failure_provisional(
                root / "private",
                value,
                requests=requests,
                reset=True,
            )
            self.assertEqual((provisional / "joins.jsonl").read_bytes(), b"")
            authoritative = authoritative_bundle_attestation(provisional)
            published = finalize_publication(
                provisional,
                root / "public",
                value,
                source_attestations=[],
                tool_identities=TOOL_IDENTITIES,
                engine_provenance=ENGINE_PROVENANCE,
                global_context_before="default",
                global_context_after="default",
                completed=False,
                authoritative_attestation=authoritative,
            )
            manifest_value = json.loads((published / "manifest.json").read_text())
            self.assertFalse(manifest_value["run_complete"])
            self.assertEqual(manifest_value["promotion_status"], "not_promoted")
            self.assertIn("failure", manifest_value["bundle_class"])

    def test_incomplete_provisional_preserves_copied_partial_sources(self):
        value, requests, decisions, envoy, targets = JoinContractTest().all_records()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            partial_raw = {
                track: (
                    (canonical_json(decisions[0]) + "\n").encode("utf-8")
                    if track is LiveTrack.CREDENTIAL_POLICY_BASELINE
                    else b""
                )
                for track in LiveTrack
            }

            output = _prepare_failure_provisional(
                root,
                value,
                requests=requests[:1],
                raw_decisions=partial_raw,
                envoy=envoy[:1],
                targets=targets[:1],
            )

            self.assertEqual(
                (output / "raw/decisions/credential_policy_baseline.jsonl").read_bytes(),
                partial_raw[LiveTrack.CREDENTIAL_POLICY_BASELINE],
            )
            self.assertEqual(len((output / "requests.jsonl").read_text().splitlines()), 1)
            self.assertEqual(len((output / "decisions.jsonl").read_text().splitlines()), 1)
            self.assertEqual(len((output / "envoy.jsonl").read_text().splitlines()), 1)
            self.assertEqual(len((output / "targets.jsonl").read_text().splitlines()), 1)
            self.assertEqual((output / "joins.jsonl").read_bytes(), b"")


if __name__ == "__main__":
    unittest.main()
