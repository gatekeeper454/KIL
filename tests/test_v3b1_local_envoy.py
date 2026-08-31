from dataclasses import FrozenInstanceError
import errno
from hashlib import sha256
import http.client
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
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
    DRIVER_FIXTURE = (
        ROOT / "tests/fixtures/v3b1-driver-topology-integration-contract.json"
    )
    DRIVER_SCHEMA = "kil.v3b1-integration-contract.v2"

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

    def test_driver_topology_fixture_uses_its_closed_v2_inventory_schema(self):
        fixture = load_integration_contract(self.DRIVER_FIXTURE)

        self.assertEqual(fixture.schema_version, self.DRIVER_SCHEMA)
        self.assertEqual(
            {case.name for case in fixture.cases},
            {
                "cycle-4-backend-network-reconstructed-inventory",
                "cycle-4-driver-container-reconstructed-inventory",
                "cycle-4-frontend-network-reconstructed-inventory",
            },
        )

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

    def test_inventory_schema_dispatch_rejects_cross_schema_names(self):
        legacy_schema = "kil.v3b1-integration-contract.v1"
        driver_schema = self.DRIVER_SCHEMA
        legacy_network = (
            "kil-v3b1-network-credential-policy-baseline-eeeeeeeeeeee"
        )
        driver_container = "kil-v3b1-driver-signed-state-only-ffffffffffff"
        segmented_networks = tuple(
            f"kil-v3b1-{segment}-signed-state-only-ffffffffffff"
            for segment in ("frontend", "backend")
        )

        legacy = parse_inventory_rows(
            canonical_json({"id": HEX_A, "name": legacy_network}) + "\n",
            "network",
            schema_version=legacy_schema,
        )
        self.assertEqual(legacy.entries[0].name, legacy_network)
        driver = parse_inventory_rows(
            canonical_json({"id": HEX_B, "name": driver_container}) + "\n",
            "container",
            schema_version=driver_schema,
        )
        self.assertEqual(driver.entries[0].name, driver_container)
        for name in segmented_networks:
            segmented = parse_inventory_rows(
                canonical_json({"id": HEX_C, "name": name}) + "\n",
                "network",
                schema_version=driver_schema,
            )
            self.assertEqual(segmented.entries[0].name, name)

        for name, kind, schema_version in (
            (driver_container, "container", legacy_schema),
            (segmented_networks[0], "network", legacy_schema),
            (segmented_networks[1], "network", legacy_schema),
            (legacy_network, "network", driver_schema),
        ):
            with self.subTest(
                name=name, schema_version=schema_version
            ), self.assertRaises(ContractError):
                parse_inventory_rows(
                    canonical_json({"id": HEX_A, "name": name}) + "\n",
                    kind,
                    schema_version=schema_version,
                )

    def test_fixture_loader_passes_schema_to_inventory_validation(self):
        loaded_legacy = load_integration_contract(self.FIXTURE)
        with self.assertRaises(ContractError):
            IntegrationContractFixture(
                self.DRIVER_SCHEMA,
                (loaded_legacy.cases[0],),
            )

        legacy = json.loads(self.FIXTURE.read_text())
        driver = json.loads(self.DRIVER_FIXTURE.read_text())
        with tempfile.TemporaryDirectory(dir=self.FIXTURE.parent) as directory:
            path = Path(directory) / "fixture.json"
            legacy["schema_version"] = self.DRIVER_SCHEMA
            path.write_text(canonical_json(legacy) + "\n")
            with self.assertRaises(ContractError):
                load_integration_contract(path)

            driver["schema_version"] = SCHEMA_VERSION
            path.write_text(canonical_json(driver) + "\n")
            with self.assertRaises(ContractError):
                load_integration_contract(path)

    def test_inventory_parser_totalizes_encoding_recursion_and_record_failures(self):
        name = "kil-v3b1-authz-credential-policy-baseline-aaaaaaaaaaaa"
        valid = canonical_json({"id": HEX_A, "name": name}) + "\n"
        with self.assertRaises(ContractError):
            parse_inventory_rows("\ud800\n", "container")
        for target in ("_canonical_json", "DockerInventoryEntry.from_mapping"):
            with self.subTest(target=target), mock.patch(
                f"tools.v3b1_harness_contract.{target}",
                side_effect=RecursionError("adversarial nesting"),
            ):
                with self.assertRaises(ContractError):
                    parse_inventory_rows(valid, "container")

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
    def _make_inventory_controller(self, directory, runner):
        root = Path(directory)
        profile_path = root / "deploy/kind/v3b-profile.json"
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_bytes(
            (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
        )
        controller = LocalEnvoyController(
            root,
            runner,
            home=root / "home",
            port_probe=lambda port: False,
            tool_verifier=lambda: {},
        )
        controller._prepare_private_roots()
        self.assertTrue(controller.docker_config.is_dir())
        self.assertEqual(list(controller.docker_config.iterdir()), [])
        return controller

    def test_docker_inventory_commands_return_closed_full_identity_rows(self):
        first_name = "kil-v3b1-authz-credential-policy-baseline-aaaaaaaaaaaa"
        network_name = "kil-v3b1-network-credential-policy-baseline-aaaaaaaaaaaa"
        runner = FakeRunner(
            [
                CommandResult(
                    0,
                    canonical_json({"id": HEX_A, "name": first_name}) + "\n",
                    "arbitrary successful diagnostic\n",
                ),
                CommandResult(
                    0,
                    canonical_json({"id": HEX_B, "name": network_name}) + "\n",
                    "network not found text is irrelevant on success\n",
                ),
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            controller = self._make_inventory_controller(directory, runner)
            containers = controller._docker_inventory("container")
            networks = controller._docker_inventory("network")

        self.assertEqual(
            [(item.object_id, item.name) for item in containers.entries],
            [(HEX_A, first_name)],
        )
        self.assertEqual(
            [(item.object_id, item.name) for item in networks.entries],
            [(HEX_B, network_name)],
        )
        container_command = runner.calls[0][0]
        network_command = runner.calls[1][0]
        self.assertEqual(
            container_command[-5:],
            [
                "ps",
                "--all",
                "--no-trunc",
                "--format",
                '{"id":{{json .ID}},"name":{{json .Names}}}',
            ],
        )
        self.assertEqual(
            network_command[-7:],
            [
                "network",
                "ls",
                "--no-trunc",
                "--filter",
                "type=custom",
                "--format",
                '{"id":{{json .ID}},"name":{{json .Name}}}',
            ],
        )
        self.assertNotIn("inspect", container_command)
        self.assertNotIn("inspect", network_command)

    def test_docker_inventory_totalizes_parser_recursion_and_rejects_identity_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = self._make_inventory_controller(
                directory, FakeRunner([CommandResult(0, "", "")])
            )
            with mock.patch.object(
                local_envoy_module,
                "parse_inventory_rows",
                side_effect=RecursionError("nested inventory"),
            ):
                with self.assertRaisesRegex(ControllerError, "inventory.*invalid"):
                    controller._docker_inventory("container")

            expected = {HEX_A: "kil-v3b1-authz-credential-policy-baseline-aaaaaaaaaaaa"}
            for actual in (
                {HEX_B: expected[HEX_A]},
                {HEX_A: "kil-v3b1-envoy-credential-policy-baseline-aaaaaaaaaaaa"},
                {HEX_A[:12]: expected[HEX_A]},
                {**expected, HEX_B: "kil-v3b1-target-credential-policy-baseline-bbbbbbbbbbbb"},
            ):
                with self.subTest(actual=actual):
                    with self.assertRaisesRegex(ControllerError, "inventory"):
                        controller._require_exact_inventory(
                            "container", actual, expected
                        )

    def test_survivor_inventory_requires_exact_id_name_pairs_for_both_kinds(self):
        container = {
            "id": HEX_A,
            "name": "kil-v3b1-authz-credential-policy-baseline-aaaaaaaaaaaa",
        }
        network = {
            "id": HEX_B,
            "name": "kil-v3b1-network-credential-policy-baseline-bbbbbbbbbbbb",
        }
        state = {
            "objects": [container],
            "transient_objects": [],
            "network_objects": [network],
        }

        with tempfile.TemporaryDirectory() as directory:
            def controller_with(container_record):
                return self._make_inventory_controller(
                    directory,
                    FakeRunner(
                        [
                            CommandResult(
                                0, canonical_json(container_record) + "\n", ""
                            ),
                            CommandResult(0, canonical_json(network) + "\n", ""),
                        ]
                    ),
                )

            controller_with(container)._assert_only_recorded_managed(
                state, expect_present=True
            )
            with self.assertRaisesRegex(ControllerError, "inventory.*ownership"):
                controller_with(
                    {"id": HEX_C, "name": container["name"]}
                )._assert_only_recorded_managed(state, expect_present=True)

    def test_validator_lifecycle_persists_id_waits_and_attests_without_auto_remove(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile_path = root / "deploy/kind/v3b-profile.json"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )
            controller = LocalEnvoyController(
                root,
                FakeRunner(
                    [
                        CommandResult(0, HEX_B + "\n", ""),
                        CommandResult(0, "0\n", ""),
                    ]
                ),
                home=root / "home",
                port_probe=lambda port: False,
                tool_verifier=lambda: {},
            )
            controller._prepare_private_roots()
            value = manifest(docker_host=controller.docker_host)
            materialize_run_inputs(controller.root, value)
            commands = build_runtime_commands(
                controller.root, value, docker_binary=controller.docker_binary
            )
            command = next(
                item
                for item in commands
                if "kil.v3b1.role=validator" in item
            )
            create_lifecycle_journal(
                controller.journal_path,
                private_root=controller.private_root,
                repository_root=root,
                docker_host=controller.docker_host,
                source_commit="d" * 40,
                execution_nonce=HEX_A,
                global_context="personal",
            )
            track = LiveTrack.CREDENTIAL_POLICY_BASELINE
            name = command[command.index("--name") + 1]
            attested = {
                "id": HEX_B,
                "name": name,
                "role": "validator",
                "track": track.value,
            }
            with mock.patch.object(
                controller,
                "_inspect_validation_container",
                return_value=attested,
            ):
                result = controller._run_validator_command(
                    command, value, track
                )

            self.assertEqual(result, attested)
            self.assertNotIn("--rm", command)
            self.assertEqual(controller.runner.calls[1][0][-2:], ["wait", HEX_B])
            events = load_lifecycle_journal(controller.journal_path)["events"]
            self.assertEqual(
                [event["event"] for event in events],
                [
                    "validator_create_intent",
                    "validator_create_complete",
                    "config_validate_intent",
                    "config_validate_complete",
                ],
            )
            self.assertTrue(
                all(
                    event["details"].get("id") == HEX_B
                    for event in events[1:]
                )
            )

    def test_removal_history_is_closed_exact_and_replayable(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            private = root / ".tools/private"
            journal_path = private / "lifecycle.json"
            create_lifecycle_journal(
                journal_path,
                private_root=private,
                repository_root=root,
                docker_host="unix:///tmp/kil-v3-lab.sock",
                source_commit="d" * 40,
                execution_nonce=HEX_A,
                global_context="personal",
            )
            identity = {
                "id": HEX_B,
                "name": "kil-v3b1-authz-credential-policy-baseline-bbbbbbbbbbbb",
            }
            journal_event(journal_path, "container_remove_intent", identity)
            pending = load_lifecycle_journal(journal_path)
            self.assertEqual(
                local_envoy_module._removal_transition(
                    pending["events"], "container", identity
                ),
                "pending",
            )
            journal_event(journal_path, "container_remove_complete", identity)
            complete = load_lifecycle_journal(journal_path)
            self.assertEqual(
                local_envoy_module._removal_transition(
                    complete["events"], "container", identity
                ),
                "complete",
            )

            for invalid_event, invalid_details in (
                ("container_remove_intent", {**identity, "extra": True}),
                ("network_remove_intent", {**identity, "name": identity["name"]}),
                ("container_remove_complete", {"id": HEX_C, "name": identity["name"]}),
            ):
                with self.subTest(event=invalid_event):
                    with self.assertRaises(ControllerError):
                        journal_event(journal_path, invalid_event, invalid_details)

            orphan_root = root / "orphan"
            orphan_private = orphan_root / ".tools/private"
            orphan_journal = orphan_private / "lifecycle.json"
            create_lifecycle_journal(
                orphan_journal,
                private_root=orphan_private,
                repository_root=orphan_root,
                docker_host="unix:///tmp/kil-v3-lab.sock",
                source_commit="d" * 40,
                execution_nonce=HEX_C,
                global_context="personal",
            )
            with self.assertRaisesRegex(ControllerError, "creation completion"):
                journal_event(
                    orphan_journal,
                    "container_create_complete",
                    identity,
                )
            validator_name = (
                "kil-v3b1-validate-credential-policy-baseline-bbbbbbbbbbbb"
            )
            journal_event(
                orphan_journal,
                "validator_create_intent",
                {"name": validator_name},
            )
            journal_event(
                orphan_journal,
                "validator_create_complete",
                {"id": HEX_B, "name": validator_name},
            )
            with self.assertRaisesRegex(ControllerError, "created identity"):
                journal_event(
                    orphan_journal,
                    "config_validate_intent",
                    {"id": HEX_C, "name": validator_name},
                )

    def test_down_load_completes_pending_absence_but_rejects_unintended_absence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile_path = root / "deploy/kind/v3b-profile.json"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )
            controller = LocalEnvoyController(
                root,
                FakeRunner(),
                home=root / "home",
                port_probe=lambda port: False,
                tool_verifier=lambda: {},
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
            _bind_journal_manifest(controller.journal_path, private_manifest, value)
            persist_active_state(
                controller.state_path, private_manifest, value
            )
            bound = load_bound_active_state(controller.state_path)
            removed = bound["objects"][0]
            identity = {"id": removed["id"], "name": removed["name"]}

            def inventory(kind):
                records = (
                    [item for item in bound["objects"] if item != removed]
                    if kind == "container"
                    else bound["network_objects"]
                )
                return parse_inventory_rows(
                    "".join(
                        canonical_json({"id": item["id"], "name": item["name"]})
                        + "\n"
                        for item in records
                    ),
                    kind,
                )

            def inspect_container(identifier, *_args, **_kwargs):
                return next(
                    item for item in bound["objects"] if item["id"] == identifier
                )

            def inspect_network(identifier, *_args, **_kwargs):
                return next(
                    item
                    for item in bound["network_objects"]
                    if item["id"] == identifier
                )

            with mock.patch.object(controller, "_docker_inventory", side_effect=inventory), mock.patch.object(
                controller, "_inspect_container", side_effect=inspect_container
            ), mock.patch.object(
                controller, "_inspect_network", side_effect=inspect_network
            ):
                with self.assertRaisesRegex(ControllerError, "removal intent"):
                    controller._load_for_down()

                journal_event(
                    controller.journal_path,
                    "container_remove_intent",
                    identity,
                )
                unexpected = {
                    "id": HEX_C,
                    "name": "kil-v3b1-validate-signed-state-only-cccccccccccc",
                }

                def ambiguous_inventory(kind):
                    if kind == "network":
                        return inventory(kind)
                    return parse_inventory_rows(
                        canonical_json(unexpected) + "\n" + "".join(
                            canonical_json(
                                {"id": item["id"], "name": item["name"]}
                            )
                            + "\n"
                            for item in bound["objects"]
                            if item != removed
                        ),
                        kind,
                    )

                with mock.patch.object(
                    controller,
                    "_docker_inventory",
                    side_effect=ambiguous_inventory,
                ), mock.patch.object(
                    controller, "_inspect_container", side_effect=inspect_container
                ), mock.patch.object(
                    controller, "_inspect_network", side_effect=inspect_network
                ):
                    with self.assertRaises(ControllerError):
                        controller._load_for_down()
                self.assertEqual(
                    [
                        event["event"]
                        for event in load_lifecycle_journal(
                            controller.journal_path
                        )["events"]
                        if event["event"].startswith("container_remove_")
                    ],
                    ["container_remove_intent"],
                )

                recovered, _, recovered_journal = controller._load_for_down()

            self.assertEqual(len(recovered["objects"]), 8)
            self.assertNotIn(identity["id"], {item["id"] for item in recovered["objects"]})
            self.assertEqual(
                [
                    event["event"]
                    for event in recovered_journal["events"]
                    if event["event"].startswith("container_remove_")
                ],
                ["container_remove_intent", "container_remove_complete"],
            )

    def test_partial_up_and_validator_recovery_use_durable_fixed_names(self):
        for case in ("service", "validator"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                profile_path = root / "deploy/kind/v3b-profile.json"
                profile_path.parent.mkdir(parents=True)
                profile_path.write_bytes(
                    (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
                )
                controller = LocalEnvoyController(
                    root,
                    FakeRunner(),
                    home=root / "home",
                    port_probe=lambda port: False,
                    tool_verifier=lambda: {},
                )
                controller._prepare_private_roots()
                value = manifest(
                    docker_host=controller.docker_host,
                    execution_nonce=HEX_A,
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
                _bind_journal_manifest(
                    controller.journal_path, private_manifest, value
                )
                persist_active_state(
                    controller.state_path, private_manifest, value
                )
                bound = load_bound_active_state(controller.state_path)
                controller.state_path.unlink()
                if case == "service":
                    recovered_object = bound["objects"][0]
                    event = "container_create_intent"
                    complete_event = "container_create_complete"
                else:
                    track = LiveTrack.CREDENTIAL_POLICY_BASELINE
                    name = (
                        f"kil-v3b1-validate-{track.value.replace('_', '-')}-"
                        f"{str(value['content_identity_sha256'])[:12]}"
                    )
                    recovered_object = {
                        "id": HEX_B,
                        "name": name,
                        "role": "validator",
                        "track": track.value,
                    }
                    event = "validator_create_intent"
                    complete_event = "validator_create_complete"
                journal_event(
                    controller.journal_path,
                    event,
                    {"name": recovered_object["name"]},
                )
                containers = parse_inventory_rows(
                    canonical_json(
                        {
                            "id": recovered_object["id"],
                            "name": recovered_object["name"],
                        }
                    )
                    + "\n",
                    "container",
                )
                empty_networks = parse_inventory_rows("", "network")

                def inventory(kind):
                    return containers if kind == "container" else empty_networks

                with mock.patch.object(
                    controller, "_docker_inventory", side_effect=inventory
                ), mock.patch.object(
                    controller,
                    "_inspect_container",
                    return_value=recovered_object,
                ), mock.patch.object(
                    controller,
                    "_inspect_validation_container",
                    return_value=recovered_object,
                ):
                    with self.assertRaisesRegex(
                        ControllerError, "anchored|creation.*ID|partial-up"
                    ):
                        controller._load_for_down()

                journal_event(
                    controller.journal_path,
                    complete_event,
                    {
                        "id": recovered_object["id"],
                        "name": recovered_object["name"],
                    },
                )
                replacement = parse_inventory_rows(
                    canonical_json(
                        {"id": HEX_C, "name": recovered_object["name"]}
                    )
                    + "\n",
                    "container",
                )
                with mock.patch.object(
                    controller,
                    "_docker_inventory",
                    side_effect=lambda kind: (
                        replacement if kind == "container" else empty_networks
                    ),
                ):
                    with self.assertRaisesRegex(ControllerError, "identity"):
                        controller._load_for_down()

                with mock.patch.object(
                    controller, "_docker_inventory", side_effect=inventory
                ), mock.patch.object(
                    controller,
                    "_inspect_container",
                    return_value=recovered_object,
                ), mock.patch.object(
                    controller,
                    "_inspect_validation_container",
                    return_value=recovered_object,
                ):
                    recovered, _, _ = controller._load_for_down()

                collection = (
                    recovered["objects"]
                    if case == "service"
                    else recovered["transient_objects"]
                )
                self.assertEqual(collection, [recovered_object])
                if case == "validator":
                    identity = {
                        "id": recovered_object["id"],
                        "name": recovered_object["name"],
                    }
                    journal_event(
                        controller.journal_path,
                        "container_remove_intent",
                        identity,
                    )
                    with mock.patch.object(
                        controller,
                        "_docker_inventory",
                        side_effect=lambda kind: (
                            parse_inventory_rows("", "container")
                            if kind == "container"
                            else empty_networks
                        ),
                    ):
                        absent, _, absent_journal = controller._load_for_down()
                    self.assertEqual(absent["transient_objects"], [])
                    self.assertEqual(
                        local_envoy_module._removal_transition(
                            absent_journal["events"], "container", identity
                        ),
                        "complete",
                    )

    def test_cli_exposes_only_the_six_approved_subcommands(self):
        parser = make_parser()

        for name in ("preflight", "up", "run", "collect", "down"):
            self.assertEqual(parser.parse_args([name]).command, name)
        view = parser.parse_args(["view", "--bundle", "/tmp/evidence"])
        self.assertEqual(view.command, "view")
        self.assertEqual(view.bundle, Path("/tmp/evidence"))
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
                "--mount",
                str(ROOT / ".tools/v3b1-staging" / HEX_A),
                "--mount-type=virtiofs",
            ],
        )
        encoded_colima = canonical_json(controller.colima_start_command(HEX_A))
        self.assertNotIn("--rosetta=false", encoded_colima)
        self.assertNotIn("--host-addresses=false", encoded_colima)
        self.assertNotIn("--nested-virtualization", encoded_colima)
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
        identity = value["content_identity"]
        self.assertEqual(
            identity["docker_endpoint"],
            {
                "transport": "unix",
                "logical_locator": "colima_profile_socket",
                "profile": PROFILE.colima_profile,
            },
        )
        self.assertEqual(
            identity["execution_nonce_sha256"],
            sha256(("0" * 64).encode("ascii")).hexdigest(),
        )
        self.assertEqual(value["execution_nonce"], "0" * 64)
        self.assertNotIn("docker_host", canonical_json(identity))
        self.assertNotIn("/Users/", canonical_json(identity))
        self.assertNotIn("execution_nonce", identity)
        self.assertEqual(
            value["content_identity_sha256"],
            sha256(canonical_json(identity).encode("utf-8")).hexdigest(),
        )
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
        same_logical_endpoint = manifest(
            docker_host="unix:///private/alternate/colima.sock"
        )
        self.assertEqual(value["run_id"], same_logical_endpoint["run_id"])
        self.assertNotEqual(
            value["docker_host"], same_logical_endpoint["docker_host"]
        )
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
            validators = [
                command
                for command in run_commands
                if "kil.v3b1.role=validator" in command
            ]
            self.assertEqual(len(detached), 12)
            self.assertEqual(len(validators), 3)
            self.assertFalse(any("--rm" in command for command in run_commands))
            self.assertTrue(all("-d" in command for command in validators))
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
                details = {"injected_failure": True}
                if phase == "container_remove":
                    details = {
                        "id": HEX_A,
                        "name": "kil-v3b1-authz-credential-policy-baseline-aaaaaaaaaaaa",
                    }
                elif phase == "network_remove":
                    details = {
                        "id": HEX_A,
                        "name": "kil-v3b1-network-credential-policy-baseline-aaaaaaaaaaaa",
                    }
                elif phase == "container_create":
                    details = {
                        "name": "kil-v3b1-authz-credential-policy-baseline-aaaaaaaaaaaa"
                    }
                elif phase == "network_create":
                    details = {
                        "name": "kil-v3b1-network-credential-policy-baseline-aaaaaaaaaaaa"
                    }
                journal_event(
                    journal,
                    f"{phase}_intent",
                    details,
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
    def test_partial_up_failure_intent_precedes_profile_delete_and_recovers_absent(
        self,
    ):
        for crash_stage in (
            "after_profile_delete_intent",
            "after_profile_disappearance",
            "after_profile_delete_complete",
        ):
            with (
                self.subTest(crash_stage=crash_stage),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory) / "repo"
                profile_path = root / "deploy/kind/v3b-profile.json"
                profile_path.parent.mkdir(parents=True)
                profile_path.write_bytes(
                    (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
                )

                class DeleteCrashController(LocalEnvoyController):
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, **kwargs)
                        self.commands = []
                        self.deleted = False
                        self.crashed = False

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
                            if (
                                crash_stage == "after_profile_delete_intent"
                                and not self.crashed
                            ):
                                self.crashed = True
                                raise ControllerError(
                                    "injected crash after profile delete intent"
                                )
                            self.deleted = True
                            if (
                                crash_stage == "after_profile_disappearance"
                                and not self.crashed
                            ):
                                self.crashed = True
                                raise ControllerError(
                                    "injected crash after profile disappearance"
                                )
                            return CommandResult(0, "", "")
                        if "context" in argv and "show" in argv:
                            return CommandResult(0, "personal\n", "")
                        if len(argv) > 5 and argv[5] == "ps":
                            return CommandResult(0, "", "")
                        if len(argv) > 6 and argv[5:7] == ["network", "ls"]:
                            return CommandResult(0, "", "")
                        return CommandResult(0, "", "")

                    def _attest_colima_after_start(self, execution_nonce=None):
                        return {"test_attestation": True}

                    def _capture_global_context(self):
                        if (
                            crash_stage == "after_profile_delete_complete"
                            and self.deleted
                            and not self.crashed
                            and any(
                                event["event"] == "colima_delete_complete"
                                for event in load_lifecycle_journal(
                                    self.journal_path
                                )["events"]
                            )
                        ):
                            self.crashed = True
                            raise ControllerError(
                                "injected crash after profile delete completion"
                            )
                        return super()._capture_global_context()

                controller = DeleteCrashController(
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
                    {
                        "tool_identities": TOOL_IDENTITIES,
                        "ports": list(controller.profile.gateway_ports),
                        "dedicated_profile_absent": True,
                    },
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

                with self.assertRaisesRegex(ControllerError, "injected crash"):
                    controller.down()

                interrupted = load_lifecycle_journal(controller.journal_path)
                failure_intents = [
                    event
                    for event in interrupted["events"]
                    if event["event"] == "post_teardown_failure_bundle_intent"
                ]
                self.assertEqual(len(failure_intents), 1)
                partial_rejection = next(
                    event
                    for event in interrupted["events"]
                    if event["event"] == "partial_up_evidence_rejected"
                )
                delete_intent = next(
                    event
                    for event in interrupted["events"]
                    if event["event"] == "colima_delete_intent"
                )
                stop_intent = next(
                    event
                    for event in interrupted["events"]
                    if event["event"] == "colima_stop_intent"
                )
                self.assertEqual(
                    failure_intents[0]["details"],
                    {
                        "run_id": value["run_id"],
                        "evidence_rejection": "partial_up:up_complete_absent",
                        "replacement": "deterministic_empty_failure_v1",
                    },
                )
                self.assertLess(
                    partial_rejection["sequence"],
                    failure_intents[0]["sequence"],
                )
                self.assertLess(
                    failure_intents[0]["sequence"], stop_intent["sequence"]
                )
                self.assertLess(
                    failure_intents[0]["sequence"], delete_intent["sequence"]
                )
                self.assertFalse(
                    any(
                        event["event"] == "post_teardown_failure_bundle_prepared"
                        for event in interrupted["events"]
                    )
                )
                self.assertFalse(
                    (
                        controller._private_provisional_root()
                        / str(value["run_id"])
                    ).exists()
                )

                published = controller.down()

                public_manifest = json.loads(
                    (published / "manifest.json").read_text()
                )
                self.assertFalse(public_manifest["run_complete"])
                self.assertEqual(
                    public_manifest["promotion_status"], "not_promoted"
                )
                self.assertIn("failure", public_manifest["bundle_class"])
                archived_path = (
                    controller._private_completed_root()
                    / f"{value['run_id']}.journal.json"
                )
                self.assertTrue(archived_path.is_file())
                archived = load_lifecycle_journal(archived_path)
                archived_intents = [
                    event
                    for event in archived["events"]
                    if event["event"] == "post_teardown_failure_bundle_intent"
                ]
                self.assertEqual(archived_intents, failure_intents)
                prepared = [
                    event
                    for event in archived["events"]
                    if event["event"] == "post_teardown_failure_bundle_prepared"
                ]
                self.assertEqual(len(prepared), 1)
                self.assertEqual(
                    prepared[0]["details"]["intent_sequence"],
                    failure_intents[0]["sequence"],
                )
                self.assertNotIn(
                    "authoritative_bundle_sha256", public_manifest
                )
                self.assertEqual(
                    public_manifest["public_commitment_sha256"],
                    local_envoy_module._public_commitment_from_output(
                        published, public_manifest
                    ),
                )

    def test_partial_up_down_retry_keeps_initial_rejection_and_cleans_exact_remainder(
        self,
    ):
        for crash_stage in (
            "after_remove_intent",
            "after_actual_removal",
            "after_remove_complete",
            "after_final_empty_inventory",
        ):
            with (
                self.subTest(crash_stage=crash_stage),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory) / "repo"
                profile_path = root / "deploy/kind/v3b-profile.json"
                profile_path.parent.mkdir(parents=True)
                profile_path.write_bytes(
                    (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
                )

                class RetryController(LocalEnvoyController):
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, **kwargs)
                        self.objects = []
                        self.networks = []
                        self.running_ids = set()
                        self.removed_ids = set()
                        self.commands = []
                        self.deleted = False
                        self.crashed = False
                        self.replacement = None

                    def _container_inventory_records(self):
                        records = [
                            item
                            for item in self.objects
                            if item["id"] not in self.removed_ids
                        ]
                        if self.replacement is not None:
                            records.append(self.replacement)
                        return records

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
                        if "context" in argv and "show" in argv:
                            return CommandResult(0, "personal\n", "")
                        if len(argv) > 5 and argv[5] == "ps":
                            return CommandResult(
                                0,
                                "".join(
                                    canonical_json(
                                        {"id": item["id"], "name": item["name"]}
                                    )
                                    + "\n"
                                    for item in self._container_inventory_records()
                                ),
                                "",
                            )
                        if len(argv) > 6 and argv[5:7] == ["network", "ls"]:
                            return CommandResult(
                                0,
                                "".join(
                                    canonical_json(
                                        {"id": item["id"], "name": item["name"]}
                                    )
                                    + "\n"
                                    for item in self.networks
                                    if item["id"] not in self.removed_ids
                                ),
                                "",
                            )
                        if "{{.State.Running}}" in argv:
                            return CommandResult(
                                0,
                                ("true" if argv[-1] in self.running_ids else "false")
                                + "\n",
                                "",
                            )
                        if len(argv) > 5 and argv[5] == "stop":
                            self.running_ids.discard(argv[-1])
                            return CommandResult(0, argv[-1] + "\n", "")
                        if len(argv) > 5 and argv[5] == "rm":
                            if (
                                crash_stage == "after_remove_intent"
                                and not self.crashed
                            ):
                                self.crashed = True
                                raise ControllerError(
                                    "injected crash after remove intent"
                                )
                            self.removed_ids.add(argv[-1])
                            return CommandResult(0, argv[-1] + "\n", "")
                        if len(argv) > 6 and argv[5:7] == ["network", "rm"]:
                            self.removed_ids.add(argv[-1])
                            return CommandResult(0, argv[-1] + "\n", "")
                        return CommandResult(0, "", "")

                    def _attest_colima_after_start(self, execution_nonce=None):
                        return {"test_attestation": True}

                    def _inspect_container(self, identifier, *_args, **_kwargs):
                        return next(
                            item
                            for item in self.objects
                            if item["id"] == identifier
                        )

                    def _inspect_network(self, identifier, *_args, **_kwargs):
                        if (
                            crash_stage == "after_remove_complete"
                            and not self.crashed
                            and any(
                                event["event"] == "container_remove_complete"
                                for event in load_lifecycle_journal(
                                    self.journal_path
                                )["events"]
                            )
                        ):
                            self.crashed = True
                            raise ControllerError(
                                "injected crash after remove completion"
                            )
                        return next(
                            item for item in self.networks if item["id"] == identifier
                        )

                    def _assert_only_recorded_managed(self, state, *, expect_present):
                        super()._assert_only_recorded_managed(
                            state, expect_present=expect_present
                        )
                        if (
                            crash_stage == "after_actual_removal"
                            and not self.crashed
                            and self.objects[0]["id"] in self.removed_ids
                            and not any(
                                event["event"] == "container_remove_complete"
                                for event in load_lifecycle_journal(
                                    self.journal_path
                                )["events"]
                            )
                        ):
                            self.crashed = True
                            raise ControllerError(
                                "injected crash after actual removal"
                            )
                        if (
                            crash_stage == "after_final_empty_inventory"
                            and not expect_present
                            and not self.crashed
                        ):
                            self.crashed = True
                            raise ControllerError(
                                "injected crash after final empty inventory"
                            )

                controller = RetryController(
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
                private_manifest.write_text(canonical_json(value) + "\n")
                temporary_state = controller.private_root / "fixture-state.json"
                persist_active_state(temporary_state, private_manifest, value)
                complete_state = load_bound_active_state(temporary_state)
                temporary_state.unlink()
                controller.objects = [complete_state["objects"][0]]
                controller.networks = [complete_state["network_objects"][0]]
                controller.running_ids = {controller.objects[0]["id"]}
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
                    {
                        "tool_identities": TOOL_IDENTITIES,
                        "ports": list(controller.profile.gateway_ports),
                        "dedicated_profile_absent": True,
                    },
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
                for kind, item in (
                    ("network", controller.networks[0]),
                    ("container", controller.objects[0]),
                ):
                    journal_event(
                        controller.journal_path,
                        f"{kind}_create_intent",
                        {"name": item["name"]},
                    )
                    journal_event(
                        controller.journal_path,
                        f"{kind}_create_complete",
                        {"id": item["id"], "name": item["name"]},
                    )

                with self.assertRaisesRegex(ControllerError, "injected crash"):
                    controller.down()
                first_rejection = next(
                    event
                    for event in load_lifecycle_journal(
                        controller.journal_path
                    )["events"]
                    if event["event"] == "partial_up_evidence_rejected"
                )

                if crash_stage == "after_actual_removal":
                    replacement_id = "f" * 64
                    controller.replacement = {
                        "id": replacement_id,
                        "name": controller.objects[0]["name"],
                    }
                    with self.assertRaisesRegex(ControllerError, "identity"):
                        controller.down()
                    self.assertNotIn(replacement_id, controller.removed_ids)
                    self.assertFalse(controller.deleted)
                    controller.replacement = None

                published = controller.down()

                archived = load_lifecycle_journal(
                    controller._private_completed_root()
                    / f"{value['run_id']}.journal.json"
                )
                rejections = [
                    event
                    for event in archived["events"]
                    if event["event"] == "partial_up_evidence_rejected"
                ]
                self.assertEqual(rejections, [first_rejection])
                self.assertTrue(controller.deleted)
                self.assertEqual(
                    controller.removed_ids,
                    {
                        controller.objects[0]["id"],
                        controller.networks[0]["id"],
                    },
                )
                self.assertFalse(
                    json.loads((published / "manifest.json").read_text())[
                        "run_complete"
                    ]
                )
                for command in controller.commands:
                    self.assertNotIn("*", command)
                    self.assertNotIn("prune", command)
                    self.assertNotIn("-aq", command)

    def test_partial_up_down_skips_freeze_and_exactly_cleans_each_survivor_kind(self):
        for case in ("service", "validator", "network"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "repo"
                profile_path = root / "deploy/kind/v3b-profile.json"
                profile_path.parent.mkdir(parents=True)
                profile_path.write_bytes(
                    (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
                )

                class PartialUpController(LocalEnvoyController):
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, **kwargs)
                        self.bound_state = None
                        self.bound_manifest = None
                        self.commands = []
                        self.removed_ids = set()
                        self.running_ids = set()
                        self.deleted = False
                        self.freeze_calls = 0
                        self.final_empty_observed = False

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
                        if "context" in argv and "show" in argv:
                            return CommandResult(0, "personal\n", "")
                        if len(argv) > 5 and argv[5] == "ps":
                            records = [
                                item
                                for item in [
                                    *self.bound_state["objects"],
                                    *self.bound_state["transient_objects"],
                                ]
                                if item["id"] not in self.removed_ids
                            ]
                            return CommandResult(
                                0,
                                "".join(
                                    canonical_json(
                                        {"id": item["id"], "name": item["name"]}
                                    )
                                    + "\n"
                                    for item in records
                                ),
                                "",
                            )
                        if len(argv) > 6 and argv[5:7] == ["network", "ls"]:
                            records = [
                                item
                                for item in self.bound_state["network_objects"]
                                if item["id"] not in self.removed_ids
                            ]
                            return CommandResult(
                                0,
                                "".join(
                                    canonical_json(
                                        {"id": item["id"], "name": item["name"]}
                                    )
                                    + "\n"
                                    for item in records
                                ),
                                "",
                            )
                        if "{{.State.Running}}" in argv:
                            return CommandResult(
                                0,
                                ("true" if argv[-1] in self.running_ids else "false")
                                + "\n",
                                "",
                            )
                        if len(argv) > 5 and argv[5] == "stop":
                            self.running_ids.discard(argv[-1])
                            return CommandResult(0, argv[-1] + "\n", "")
                        if len(argv) > 5 and (
                            argv[5] == "rm" or argv[5:7] == ["network", "rm"]
                        ):
                            self.removed_ids.add(argv[-1])
                            return CommandResult(0, argv[-1] + "\n", "")
                        return CommandResult(0, "", "")

                    def _attest_colima_after_start(self, execution_nonce=None):
                        return {"test_attestation": True}

                    def _load_for_down(self):
                        return (
                            self.bound_state,
                            self.bound_manifest,
                            load_lifecycle_journal(self.journal_path),
                        )

                    def _inspect_container(self, identifier, *_args, **_kwargs):
                        return next(
                            item
                            for item in self.bound_state["objects"]
                            if item["id"] == identifier
                        )

                    def _inspect_validation_container(self, identifier, *_args, **_kwargs):
                        return next(
                            item
                            for item in self.bound_state["transient_objects"]
                            if item["id"] == identifier
                        )

                    def _inspect_network(self, identifier, *_args, **_kwargs):
                        return next(
                            item
                            for item in self.bound_state["network_objects"]
                            if item["id"] == identifier
                        )

                    def _freeze_before_service_teardown(self, *args, **kwargs):
                        self.freeze_calls += 1
                        raise AssertionError("partial-up teardown entered evidence freeze")

                    def _assert_only_recorded_managed(self, state, *, expect_present):
                        super()._assert_only_recorded_managed(
                            state, expect_present=expect_present
                        )
                        if not expect_present:
                            self.final_empty_observed = True

                controller = PartialUpController(
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
                    {
                        "tool_identities": TOOL_IDENTITIES,
                        "ports": list(controller.profile.gateway_ports),
                        "dedicated_profile_absent": True,
                    },
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
                state_path = controller.private_root / "partial-state.json"
                persist_active_state(state_path, private_manifest, value)
                complete_state = load_bound_active_state(state_path)
                if case == "service":
                    objects = [complete_state["objects"][0]]
                    transients = []
                    networks = []
                elif case == "validator":
                    track = LiveTrack.CREDENTIAL_POLICY_BASELINE
                    transients = [
                        {
                            "id": HEX_B,
                            "name": (
                                f"kil-v3b1-validate-{track.value.replace('_', '-')}-"
                                f"{str(value['content_identity_sha256'])[:12]}"
                            ),
                            "role": "validator",
                            "track": track.value,
                        }
                    ]
                    objects = []
                    networks = []
                else:
                    objects = []
                    transients = []
                    networks = [complete_state["network_objects"][0]]
                controller.bound_state = {
                    "objects": objects,
                    "transient_objects": transients,
                    "network_objects": networks,
                    "profile_created": True,
                    "colima_profile": "kil-v3-lab",
                    "docker_host": controller.docker_host,
                    "docker_config": str(controller.docker_config),
                }
                controller.bound_manifest = value
                controller.running_ids = {
                    item["id"] for item in [*objects, *transients]
                }

                published = controller.down()

                self.assertEqual(controller.freeze_calls, 0)
                self.assertTrue(controller.deleted)
                self.assertTrue(controller.final_empty_observed)
                self.assertEqual(
                    controller.removed_ids,
                    {
                        item["id"]
                        for item in [*objects, *transients, *networks]
                    },
                )
                events = load_lifecycle_journal(
                    controller._private_completed_root()
                    / f"{value['run_id']}.journal.json"
                )["events"]
                rejection = [
                    event
                    for event in events
                    if event["event"] == "partial_up_evidence_rejected"
                ]
                self.assertEqual(len(rejection), 1)
                self.assertFalse(rejection[0]["details"]["promotable"])
                expected_survivors = {
                    "containers": sorted(
                        (
                            {"id": item["id"], "name": item["name"]}
                            for item in [*objects, *transients]
                        ),
                        key=lambda item: (item["name"], item["id"]),
                    ),
                    "networks": sorted(
                        (
                            {"id": item["id"], "name": item["name"]}
                            for item in networks
                        ),
                        key=lambda item: (item["name"], item["id"]),
                    ),
                }
                self.assertEqual(
                    rejection[0]["details"]["survivor_identity_sha256"],
                    sha256(canonical_json(expected_survivors).encode("utf-8")).hexdigest(),
                )
                stop_completes = {
                    event["details"]["id"]
                    for event in events
                    if event["event"] == "container_stop_complete"
                }
                self.assertEqual(
                    stop_completes,
                    {item["id"] for item in [*objects, *transients]},
                )
                public_manifest = json.loads(
                    (published / "manifest.json").read_text()
                )
                self.assertFalse(public_manifest["run_complete"])
                self.assertIn("failure", public_manifest["bundle_class"])
                encoded_commands = canonical_json(controller.commands)
                for forbidden in ("*", "prune", "-aq"):
                    self.assertNotIn(forbidden, encoded_commands)

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
                    script = command[command.index("-c") + 1]
                    if "payload_hex" in script:
                        injection = self.injections.get(key)
                        if injection == "export_error":
                            raise ControllerError("injected ledger export failure")
                        if injection == "export_invalid":
                            return CommandResult(0, "not-json\n", "")
                        payload = self.payloads[key]
                        if injection == "export_digest_mismatch":
                            payload = payload[:-1] + b"x" if payload else b"x"
                        elif injection == "export_size_mismatch":
                            payload += b"x"
                        export = {
                            "byte_count": len(payload),
                            "payload_hex": payload.hex(),
                            "sha256": sha256(payload).hexdigest(),
                        }
                        return CommandResult(0, canonical_json(export) + "\n", "")
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
                    if self.injections.get(key) in {
                        "copy_error",
                        "export_error",
                        "export_invalid",
                        "export_digest_mismatch",
                        "export_size_mismatch",
                    }:
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
            ("signed_state_only", "target_markers"): "export_error",
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

    def test_failed_docker_cp_exports_exact_zero_byte_ledgers_in_container(self):
        ledger_keys = {
            (track.value, source)
            for track in LiveTrack
            for source in ("authz_decisions", "target_markers")
        }
        with tempfile.TemporaryDirectory() as directory:
            controller, state, value = self.make_freeze_controller(
                directory,
                no_run=True,
                injections={key: "copy_error" for key in ledger_keys},
            )

            result = controller._freeze_sources(
                state, value, attempted_complete=False
            )

            ledger_statuses = [
                status
                for status in result.statuses
                if status.source != "envoy_access"
            ]
            self.assertFalse(result.complete)
            self.assertTrue(
                all(status.status == "copied" for status in result.statuses)
            )
            self.assertEqual(len(ledger_statuses), 6)
            self.assertTrue(all(status.status == "copied" for status in ledger_statuses))
            self.assertTrue(
                all(
                    status.source_byte_count == status.copied_byte_count == 0
                    and status.source_sha256
                    == status.copied_sha256
                    == sha256(b"").hexdigest()
                    for status in ledger_statuses
                )
            )
            exports = [
                command
                for command in controller.commands
                if "exec" in command and "payload_hex" in command[command.index("-c") + 1]
            ]
            self.assertEqual(len(exports), 6)
            self.assertTrue(
                all(
                    command[-1] == str(128 * 1024 + 1)
                    and command[-2]
                    in {"/evidence/decisions.jsonl", "/evidence/targets.jsonl"}
                    and "/usr/local/bin/python" in command
                    and "-c" in command
                    for command in exports
                )
            )
            self.assertTrue(
                all("sh" not in command and "bash" not in command for command in exports)
            )

    def test_failed_docker_cp_exports_exact_nonempty_ledger_bytes(self):
        key = ("credential_policy_baseline", "authz_decisions")
        with tempfile.TemporaryDirectory() as directory:
            controller, state, value = self.make_freeze_controller(
                directory, injections={key: "copy_error"}
            )
            expected = controller.payloads[key]

            result = controller._freeze_sources(
                state, value, attempted_complete=True
            )

            status = next(
                item
                for item in result.statuses
                if (item.track, item.source) == key
            )
            self.assertTrue(result.complete)
            self.assertEqual(status.status, "copied")
            self.assertEqual(status.source_byte_count, len(expected))
            self.assertEqual(status.copied_sha256, sha256(expected).hexdigest())
            self.assertEqual(result.raw_paths[key].read_bytes(), expected)

    def test_real_ledger_export_script_is_exact_bounded_and_nofollow(self):
        maximum = local_envoy_module._MAX_LEDGER_EXPORT_BYTES
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "ledger.jsonl"
            for payload in (b"", b'{"track":"credential_policy_baseline"}\n'):
                with self.subTest(payload=payload):
                    ledger.write_bytes(payload)
                    completed = subprocess.run(
                        [
                            sys.executable,
                            "-c",
                            local_envoy_module._LEDGER_EXPORT,
                            str(ledger),
                            str(maximum),
                        ],
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assertEqual(completed.stderr, "")
                    exported, byte_count, digest = (
                        LocalEnvoyController._parse_ledger_export(
                            completed.stdout
                        )
                    )
                    self.assertEqual(exported, payload)
                    self.assertEqual(byte_count, len(payload))
                    self.assertEqual(digest, sha256(payload).hexdigest())
                    self.assertEqual(
                        completed.stdout,
                        canonical_json(
                            {
                                "byte_count": len(payload),
                                "payload_hex": payload.hex(),
                                "sha256": sha256(payload).hexdigest(),
                            }
                        )
                        + "\n",
                    )

            ledger.write_bytes(b"x" * (maximum + 1))
            oversize = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    local_envoy_module._LEDGER_EXPORT,
                    str(ledger),
                    str(maximum),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(oversize.returncode, 0)
            self.assertEqual(oversize.stdout, "")

            target = root / "target.jsonl"
            target.write_bytes(b"{}\n")
            ledger.unlink()
            ledger.symlink_to(target)
            symlink = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    local_envoy_module._LEDGER_EXPORT,
                    str(ledger),
                    str(maximum),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(symlink.returncode, 0)
            self.assertEqual(symlink.stdout, "")

    def test_ledger_export_preserves_malformed_source_but_rejects_bad_exports(self):
        key = ("credential_policy_baseline", "authz_decisions")
        cases = (
            ("export_digest_mismatch", None),
            ("export_size_mismatch", None),
            ("export_invalid", None),
            ("export_error", None),
            ("copy_error", b"not-json\n"),
            ("copy_error", b"x" * (128 * 1024 + 2)),
        )
        for injection, override in cases:
            with self.subTest(injection=injection, override_size=None if override is None else len(override)):
                with tempfile.TemporaryDirectory() as directory:
                    controller, state, value = self.make_freeze_controller(
                        directory,
                        injections={key: injection},
                        payload_overrides={} if override is None else {key: override},
                    )

                    result = controller._freeze_sources(
                        state, value, attempted_complete=True
                    )

                    status = next(
                        item
                        for item in result.statuses
                        if (item.track, item.source) == key
                    )
                    if override == b"not-json\n":
                        self.assertEqual(status.status, "malformed")
                        self.assertEqual(status.error_class, "invalid_json")
                        self.assertEqual(result.raw_paths[key].read_bytes(), override)
                    else:
                        self.assertEqual(status.status, "copy_error")
                        self.assertEqual(status.error_class, "command_failed")
                        self.assertFalse(result.raw_paths[key].exists())
                    self.assertFalse(result.complete)

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

    def test_nested_source_json_totalizes_all_nine_legs_and_teardown(self):
        malformed = (
            b'{"value":'
            + (b"[" * 10_000)
            + b"0"
            + (b"]" * 10_000)
            + b"}\n"
        )
        key = ("credential_policy_baseline", "target_markers")
        with tempfile.TemporaryDirectory() as directory:
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
            journal = load_lifecycle_journal(controller.journal_path)
            terminals = [
                event
                for event in journal["events"]
                if event["event"] == "source_collection_terminal"
            ]
            completed = next(
                event
                for event in journal["events"]
                if event["event"] == "evidence_freeze_complete"
            )
            self.assertFalse(freeze.complete)
            self.assertEqual(len(freeze.statuses), 9)
            self.assertEqual(len(terminals), 9)
            self.assertEqual(completed["details"]["terminal_count"], 9)
            self.assertFalse(completed["details"]["promotable"])
            self.assertEqual(selected.status, "malformed")
            self.assertEqual(selected.error_class, "invalid_json")
            self.assertEqual(selected.source_byte_count, len(malformed))
            self.assertEqual(selected.copied_byte_count, len(malformed))
            self.assertEqual(selected.source_sha256, sha256(malformed).hexdigest())
            self.assertEqual(selected.copied_sha256, sha256(malformed).hexdigest())
            self.assertEqual(freeze.raw_paths[key].read_bytes(), malformed)
            self.assertEqual(controller.running, set())

    def test_source_json_parser_normalizes_recursion_at_each_parse_boundary(self):
        nested = (
            b'{"value":'
            + (b"[" * 10_000)
            + b"0"
            + (b"]" * 10_000)
            + b"}"
        )
        with self.assertRaisesRegex(ControllerError, "closed UTF-8 JSON"):
            local_envoy_module._load_json_bytes(nested, "nested source")

        def recursive_validator(record):
            raise RecursionError("validator recursion")

        with self.assertRaisesRegex(ControllerError, "record validation failed"):
            local_envoy_module._parse_jsonl_bytes(
                b"{}\n",
                "recursive source",
                recursive_validator,
                allow_empty=False,
            )
        with (
            mock.patch(
                "tools.v3b1_local_envoy.canonical_json",
                side_effect=RecursionError("canonical recursion"),
            ),
            self.assertRaisesRegex(ControllerError, "record validation failed"),
        ):
            local_envoy_module._parse_jsonl_bytes(
                b"{}\n",
                "recursive source",
                lambda record: None,
                allow_empty=False,
            )

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

    def test_failed_post_write_envoy_freeze_quarantines_before_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, state, value = self.make_freeze_controller(directory)
            key = ("credential_policy_baseline", "envoy_access")
            _, epoch = controller._freeze_epoch(value)
            active = controller._freeze_raw_paths(value, epoch)[key]
            expected_bytes = controller.payloads[key]
            actual_write = local_envoy_module._write_file
            actual_journal = local_envoy_module.journal_event
            injected = {"failed": False}
            terminal_active_states = []

            def fail_after_envoy_write(path, payload, mode=0o600):
                actual_write(path, payload, mode)
                if Path(path) == active and not injected["failed"]:
                    injected["failed"] = True
                    raise OSError("injected Envoy post-write failure")

            def observe_terminal(path, event, details):
                if (
                    event == "source_collection_terminal"
                    and details["record"]["track"] == key[0]
                    and details["record"]["source"] == key[1]
                ):
                    terminal_active_states.append(
                        active.is_symlink() or active.exists()
                    )
                return actual_journal(path, event, details)

            with (
                mock.patch(
                    "tools.v3b1_local_envoy._write_file",
                    side_effect=fail_after_envoy_write,
                ),
                mock.patch(
                    "tools.v3b1_local_envoy.journal_event",
                    side_effect=observe_terminal,
                ),
            ):
                freeze = controller._freeze_before_service_teardown(
                    state,
                    value,
                    attempted_complete=True,
                    transient_objects=[],
                )

            status = next(
                item
                for item in freeze.statuses
                if (item.track, item.source) == key
            )
            quarantines = list(
                active.parent.glob(f".{active.name}.unattested.*")
            )
            self.assertTrue(injected["failed"])
            self.assertEqual(status.status, "copy_error")
            self.assertEqual(status.error_class, "command_failed")
            self.assertEqual(terminal_active_states, [False])
            self.assertFalse(active.is_symlink())
            self.assertFalse(active.exists())
            self.assertEqual(len(quarantines), 1)
            self.assertEqual(quarantines[0].read_bytes(), expected_bytes)
            self.assertEqual(controller.running, set())

            recovered = controller._freeze_sources(
                state, value, attempted_complete=True
            )
            self.assertFalse(recovered.complete)
            self.assertFalse(active.exists())

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

    def test_preterminal_bound_bytes_are_adopted_without_a_live_source(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, state, value = self.make_freeze_controller(directory)
            original_event = journal_event

            def fail_first_terminal(path, event, details):
                if event == "source_collection_terminal":
                    raise RuntimeError("injected terminal persistence failure")
                return original_event(path, event, details)

            with mock.patch(
                "tools.v3b1_local_envoy.journal_event",
                side_effect=fail_first_terminal,
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "terminal persistence failure"
                ):
                    controller._freeze_sources(
                        state, value, attempted_complete=True
                    )

            journal = load_lifecycle_journal(controller.journal_path)
            persisted = [
                event
                for event in journal["events"]
                if event["event"] == "evidence_freeze_leg_bytes_persisted"
            ]
            self.assertEqual(len(persisted), 1)
            details = persisted[0]["details"]
            self.assertEqual(
                set(details),
                {
                    "collection_epoch",
                    "track",
                    "source",
                    "path_relative",
                    "byte_count",
                    "sha256",
                },
            )
            key = (details["track"], details["source"])
            _, epoch = controller._freeze_epoch(value)
            self.assertEqual(details["collection_epoch"], epoch)
            self.assertEqual(
                details["path_relative"],
                f"{key[0]}/{local_envoy_module._FREEZE_FILE_NAME[key[1]]}",
            )
            frozen_path = controller._freeze_raw_paths(value, epoch)[key]
            original_bytes = frozen_path.read_bytes()
            self.assertEqual(details["byte_count"], len(original_bytes))
            self.assertEqual(details["sha256"], sha256(original_bytes).hexdigest())
            source = next(
                item
                for item in state["objects"]
                if item["track"] == key[0]
                and item["role"] == local_envoy_module._SOURCE_ROLE[key[1]]
            )
            controller.alive.remove(source["id"])
            before = len(controller.commands)

            recovered = controller._freeze_sources(
                state, value, attempted_complete=True
            )

            adopted = next(
                status
                for status in recovered.statuses
                if (status.track, status.source) == key
            )
            self.assertTrue(recovered.complete)
            self.assertEqual(adopted.status, "copied")
            self.assertEqual(frozen_path.read_bytes(), original_bytes)
            self.assertFalse(
                any(
                    source["id"] in command
                    for command in controller.commands[before:]
                )
            )

    def test_completed_mismatch_sources_are_rehash_attested_on_recovery(self):
        cases = (
            (
                ("credential_policy_baseline", "authz_decisions"),
                "digest_mismatch",
            ),
            (("signed_state_only", "target_markers"), "size_mismatch"),
        )
        for key, injection in cases:
            with (
                self.subTest(injection=injection),
                tempfile.TemporaryDirectory() as directory,
            ):
                controller, state, value = self.make_freeze_controller(
                    directory, injections={key: injection}
                )
                freeze = controller._freeze_sources(
                    state, value, attempted_complete=True
                )
                status = next(
                    item
                    for item in freeze.statuses
                    if (item.track, item.source) == key
                )
                self.assertEqual(status.status, "copy_error")
                self.assertEqual(status.error_class, injection)
                self.assertIsNotNone(status.copied_byte_count)
                frozen_path = freeze.raw_paths[key]
                frozen_path.chmod(0o600)
                frozen_path.write_bytes(b"mutated mismatch bytes\n")

                with self.assertRaisesRegex(ControllerError, "changed"):
                    controller._freeze_sources(
                        state, value, attempted_complete=True
                    )

    def test_repeated_unbound_copies_use_collision_safe_quarantines(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, state, value = self.make_freeze_controller(directory)
            original_event = journal_event

            def fail_first_byte_binding(path, event, details):
                if event == "evidence_freeze_leg_bytes_persisted":
                    raise RuntimeError("injected repeated byte binding failure")
                return original_event(path, event, details)

            for _ in range(3):
                with mock.patch(
                    "tools.v3b1_local_envoy.journal_event",
                    side_effect=fail_first_byte_binding,
                ):
                    with self.assertRaisesRegex(
                        RuntimeError, "repeated byte binding failure"
                    ):
                        controller._freeze_sources(
                            state, value, attempted_complete=True
                        )

            recovered = controller._freeze_sources(
                state, value, attempted_complete=True
            )

            key = ("credential_policy_baseline", "envoy_access")
            active = recovered.raw_paths[key]
            quarantines = sorted(
                active.parent.glob(f".{active.name}.unattested.*")
            )
            self.assertTrue(recovered.complete)
            self.assertEqual(len(quarantines), 3)
            self.assertTrue(all(path.is_file() for path in quarantines))
            self.assertTrue(active.is_file())
            self.assertFalse(active.is_symlink())

    def test_unbound_symlink_is_moved_without_following_before_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, state, value = self.make_freeze_controller(directory)
            original_event = journal_event

            def fail_first_byte_binding(path, event, details):
                if event == "evidence_freeze_leg_bytes_persisted":
                    raise RuntimeError("injected symlink byte binding failure")
                return original_event(path, event, details)

            with mock.patch(
                "tools.v3b1_local_envoy.journal_event",
                side_effect=fail_first_byte_binding,
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "symlink byte binding failure"
                ):
                    controller._freeze_sources(
                        state, value, attempted_complete=True
                    )

            _, epoch = controller._freeze_epoch(value)
            key = ("credential_policy_baseline", "envoy_access")
            active = controller._freeze_raw_paths(value, epoch)[key]
            outside = Path(directory) / "outside-source"
            outside.write_bytes(b"must not be followed or changed\n")
            active.unlink()
            active.symlink_to(outside)
            terminal_saw_unsafe_active = []

            def observe_terminal(path, event, details):
                if (
                    event == "source_collection_terminal"
                    and details["record"]["track"] == key[0]
                    and details["record"]["source"] == key[1]
                ):
                    terminal_saw_unsafe_active.append(active.is_symlink())
                return original_event(path, event, details)

            with mock.patch(
                "tools.v3b1_local_envoy.journal_event",
                side_effect=observe_terminal,
            ):
                recovered = controller._freeze_before_service_teardown(
                    state,
                    value,
                    attempted_complete=True,
                    transient_objects=[],
                )

            quarantines = sorted(
                active.parent.glob(f".{active.name}.unattested.*")
            )
            self.assertTrue(recovered.complete)
            self.assertEqual(terminal_saw_unsafe_active, [False])
            self.assertTrue(active.is_file())
            self.assertFalse(active.is_symlink())
            self.assertEqual(len(quarantines), 1)
            self.assertTrue(quarantines[0].is_symlink())
            self.assertEqual(os.readlink(quarantines[0]), str(outside))
            self.assertEqual(
                outside.read_bytes(), b"must not be followed or changed\n"
            )
            self.assertEqual(controller.running, set())

    def test_unbound_preterminal_bytes_are_quarantined_not_deleted_or_claimed(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, state, value = self.make_freeze_controller(directory)
            original_event = journal_event

            def fail_first_byte_binding(path, event, details):
                if event == "evidence_freeze_leg_bytes_persisted":
                    raise RuntimeError("injected byte binding failure")
                return original_event(path, event, details)

            with mock.patch(
                "tools.v3b1_local_envoy.journal_event",
                side_effect=fail_first_byte_binding,
            ):
                with self.assertRaisesRegex(RuntimeError, "byte binding failure"):
                    controller._freeze_sources(
                        state, value, attempted_complete=True
                    )

            _, epoch = controller._freeze_epoch(value)
            key = ("credential_policy_baseline", "envoy_access")
            frozen_path = controller._freeze_raw_paths(value, epoch)[key]
            original_bytes = frozen_path.read_bytes()
            source = next(
                item
                for item in state["objects"]
                if item["track"] == key[0] and item["role"] == "envoy"
            )
            controller.alive.remove(source["id"])

            recovered = controller._freeze_sources(
                state, value, attempted_complete=True
            )

            status = next(
                item
                for item in recovered.statuses
                if (item.track, item.source) == key
            )
            self.assertFalse(recovered.complete)
            self.assertEqual(status.status, "copy_error")
            self.assertEqual(status.error_class, "command_failed")
            self.assertFalse(frozen_path.exists())
            quarantines = list(
                frozen_path.parent.glob(f".{frozen_path.name}.unattested.*")
            )
            self.assertEqual(len(quarantines), 1)
            self.assertEqual(quarantines[0].read_bytes(), original_bytes)

    def test_teardown_evidence_rejects_frozen_source_replacement_and_symlink(self):
        _, _, _, envoy, _ = JoinContractTest().all_records()
        replacement_bytes = (
            canonical_json(
                next(
                    item
                    for item in envoy
                    if item["track"] == "credential_policy_baseline"
                )
            )
            + "\n"
        ).encode("utf-8")
        self.assertEqual(len(replacement_bytes), 323)
        for attack in ("replacement", "symlink"):
            with (
                self.subTest(attack=attack),
                tempfile.TemporaryDirectory() as directory,
            ):
                controller, state, value = self.make_freeze_controller(
                    directory, no_run=True
                )
                freeze = controller._freeze_before_service_teardown(
                    state,
                    value,
                    attempted_complete=False,
                    transient_objects=[],
                )
                key = ("credential_policy_baseline", "envoy_access")
                frozen_path = freeze.raw_paths[key]
                status = next(
                    item
                    for item in freeze.statuses
                    if (item.track, item.source) == key
                )
                self.assertEqual(status.status, "copied")
                self.assertEqual(status.copied_byte_count, 0)
                replacement = frozen_path.with_name("replacement.jsonl")
                replacement.write_bytes(replacement_bytes)
                if attack == "replacement":
                    os.replace(replacement, frozen_path)
                else:
                    frozen_path.unlink()
                    frozen_path.symlink_to(replacement)

                output, attestations, completed, rejection = (
                    controller._prepare_teardown_evidence(
                        value, state["objects"], freeze
                    )
                )

                self.assertIsNone(output)
                self.assertEqual(attestations, [])
                self.assertFalse(completed)
                self.assertIsNotNone(rejection)
                self.assertEqual(controller.running, set())
                provisional = (
                    controller._private_provisional_root() / value["run_id"]
                )
                if provisional.exists():
                    self.assertNotIn(
                        replacement_bytes,
                        [
                            path.read_bytes()
                            for path in provisional.rglob("*")
                            if path.is_file() and not path.is_symlink()
                        ],
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
                        self.removed_ids = set()

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
                        if len(argv) > 5 and argv[5] == "ps":
                            records = (
                                []
                                if self.bound_state is None
                                else [
                                    item
                                    for item in self.bound_state["objects"]
                                    if item["id"] not in self.removed_ids
                                ]
                            )
                            return CommandResult(
                                0,
                                "".join(
                                    canonical_json(
                                        {"id": item["id"], "name": item["name"]}
                                    )
                                    + "\n"
                                    for item in records
                                ),
                                "",
                            )
                        if len(argv) > 6 and argv[5:7] == ["network", "ls"]:
                            records = (
                                []
                                if self.bound_state is None
                                else [
                                    item
                                    for item in self.bound_state["network_objects"]
                                    if item["id"] not in self.removed_ids
                                ]
                            )
                            return CommandResult(
                                0,
                                "".join(
                                    canonical_json(
                                        {"id": item["id"], "name": item["name"]}
                                    )
                                    + "\n"
                                    for item in records
                                ),
                                "",
                            )
                        if len(argv) > 5 and (
                            argv[5] == "rm" or argv[5:7] == ["network", "rm"]
                        ):
                            self.removed_ids.add(argv[-1])
                            return CommandResult(0, "", "")
                        return CommandResult(0, "", "")

                    def _attest_colima_after_start(self, execution_nonce=None):
                        return {"test_attestation": True}

                    def _load_for_down(self):
                        return (
                            self.bound_state,
                            self.bound_manifest,
                            load_lifecycle_journal(self.journal_path),
                        )

                    def _inspect_container(self, identifier, manifest_value, role, track, *, require_running=True):
                        return next(
                            item
                            for item in self.bound_state["objects"]
                            if item["id"] == identifier
                        )

                    def _inspect_network(
                        self,
                        identifier,
                        manifest_value,
                        track,
                        *,
                        require_complete_membership=True,
                        require_empty_membership=False,
                    ):
                        return next(
                            item
                            for item in self.bound_state["network_objects"]
                            if item["id"] == identifier
                        )

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
                self.assertEqual(
                    len(
                        [
                            command
                            for command in controller.commands
                            if len(command) > 5 and command[5] == "ps"
                        ]
                    ),
                    14,
                )
                self.assertEqual(
                    len(
                        [
                            command
                            for command in controller.commands
                            if len(command) > 6
                            and command[5:7] == ["network", "ls"]
                        ]
                    ),
                    14,
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
            self.assertNotIn(
                "authoritative_bundle_sha256", public_manifest
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
            self.assertNotEqual(
                public_manifest["public_commitment_sha256"],
                recovered_authority["binding_sha256"],
            )
            self.assertEqual(
                public_manifest["public_commitment_sha256"],
                local_envoy_module._public_commitment_from_output(
                    published, public_manifest
                ),
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
                    "AutoRemove": False,
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
            controller.runner = NetworkRunner(partial)
            with self.assertRaisesRegex(ControllerError, "membership"):
                controller._inspect_network(
                    "a" * 64,
                    value,
                    track.value,
                    require_complete_membership=False,
                    require_empty_membership=True,
                )
            controller.runner = NetworkRunner({**network, "Containers": {}})
            controller._inspect_network(
                "a" * 64,
                value,
                track.value,
                require_complete_membership=False,
                require_empty_membership=True,
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


def presenter_source_attestations(provisional, envoy, targets):
    def payload(records):
        return b"".join(
            (canonical_json(record) + "\n").encode("utf-8")
            for record in records
        )

    return [
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
                payload([item for item in envoy if item["track"] == track.value])
            ).hexdigest(),
            "raw_envoy_count": 1,
            "raw_targets_sha256": sha256(
                payload([item for item in targets if item["track"] == track.value])
            ).hexdigest(),
            "raw_target_count": 0 if index == 2 else 1,
        }
        for index, track in enumerate(LiveTrack)
    ]


def published_presenter_bundle(
    root,
    *,
    completed=True,
    global_context="personal",
    publication_fault=None,
    publication_complete=None,
):
    value, requests, decisions, envoy, targets = JoinContractTest().all_records()
    if completed:
        joins = join_evidence(value, requests, decisions, envoy, targets)
        provisional = write_evidence_bundle(
            root / "private",
            value,
            requests=requests,
            decisions=decisions,
            envoy=envoy,
            targets=targets,
            joins=joins,
        )
        source_attestations = presenter_source_attestations(
            provisional, envoy, targets
        )
    else:
        provisional = _prepare_failure_provisional(
            root / "private", value, reset=True
        )
        source_attestations = []
    authority = authoritative_bundle_attestation(provisional)
    published = finalize_publication(
        provisional,
        root / "public",
        value,
        source_attestations=source_attestations,
        tool_identities=TOOL_IDENTITIES,
        engine_provenance=ENGINE_PROVENANCE,
        global_context_before=global_context,
        global_context_after=global_context,
        completed=completed,
        authoritative_attestation=authority,
        publication_fault=publication_fault,
        publication_complete=publication_complete,
    )
    return published


def rewrite_public_bundle_hashes(bundle, *, repair_commitment=True):
    manifest_path = bundle / "manifest.json"
    manifest_path.chmod(0o600)
    public_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for relative in tuple(public_manifest["artifact_sha256"]):
        public_manifest["artifact_sha256"][relative] = sha256(
            (bundle / relative).read_bytes()
        ).hexdigest()
    if repair_commitment and "public_commitment_sha256" in public_manifest:
        public_manifest["public_commitment_sha256"] = (
            local_envoy_module._public_commitment_from_output(
                bundle, public_manifest
            )
        )
    manifest_path.write_text(canonical_json(public_manifest) + "\n", encoding="utf-8")
    manifest_path.chmod(0o444)
    local_envoy_module._write_sums(bundle)


class PublishedRecoveryController(LocalEnvoyController):
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


def interrupted_published_recovery(root, *, completed):
    repository = root / "repo"
    profile_path = repository / "deploy/kind/v3b-profile.json"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_bytes(
        (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
    )
    controller = PublishedRecoveryController(
        repository,
        FakeRunner(),
        home=root / "home",
        port_probe=lambda port: False,
        tool_verifier=lambda: TOOL_IDENTITIES,
    )
    controller._prepare_private_roots()
    value, requests, decisions, envoy, targets = JoinContractTest().all_records()
    private_manifest = controller.manifest_root / "run.json"
    private_manifest.write_text(canonical_json(value) + "\n")
    create_lifecycle_journal(
        controller.journal_path,
        private_root=controller.private_root,
        repository_root=repository,
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
    _bind_journal_manifest(controller.journal_path, private_manifest, value)
    persist_active_state(controller.state_path, private_manifest, value)
    if completed:
        provisional = write_evidence_bundle(
            controller.provisional_root,
            value,
            requests=requests,
            decisions=decisions,
            envoy=envoy,
            targets=targets,
            joins=join_evidence(value, requests, decisions, envoy, targets),
        )
        source_attestations = presenter_source_attestations(
            provisional, envoy, targets
        )
    else:
        provisional = _prepare_failure_provisional(
            controller.provisional_root, value, reset=True
        )
        source_attestations = []
    authority = authoritative_bundle_attestation(provisional)
    journal_event(
        controller.journal_path,
        "evidence_collect_complete",
        {
            "completed": completed,
            "bundle_sha256": sha256(
                (provisional / "SHA256SUMS").read_bytes()
            ).hexdigest(),
            "authoritative_attestation": authority,
        },
    )
    journal_event(
        controller.journal_path,
        "source_attestations_persisted",
        {"source_attestations": source_attestations},
    )
    journal_event(
        controller.journal_path,
        "readiness_session_started",
        {"readiness_nonce": HEX_B},
    )
    unsigned_poison = {
        "schema_version": "kil.v3b1-readiness-poison.v1",
        "execution_nonce": HEX_A,
        "readiness_nonce": HEX_B,
        "reason_category": "connection_close_ambiguous",
    }
    poison = {
        **unsigned_poison,
        "binding_sha256": sha256(
            canonical_json(unsigned_poison).encode("utf-8")
        ).hexdigest(),
    }
    controller.readiness_poison_path.write_text(
        canonical_json(poison) + "\n"
    )
    controller.readiness_poison_path.chmod(0o600)
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
    journal_event(
        controller.journal_path,
        "publication_intent",
        {"run_id": value["run_id"], "completed": completed},
    )
    published = finalize_publication(
        provisional,
        controller.evidence_root,
        value,
        source_attestations=source_attestations,
        tool_identities=TOOL_IDENTITIES,
        engine_provenance=ENGINE_PROVENANCE,
        global_context_before="personal",
        global_context_after="personal",
        completed=completed,
        authoritative_attestation=authority,
        repository_root=repository,
        publication_staging_root=controller.publication_staging_root,
    )
    return controller, published, value


class EvidenceBundleTest(unittest.TestCase):
    KTP_CITATION_URL = (
        "https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff"
    )

    def test_synthetic_legacy_v1_compatibility_fixture_remains_accepted(self):
        fixture_root = ROOT / "tests/fixtures/v3b1-public-bundle-v1"
        fixture_bundles = tuple(
            path for path in fixture_root.iterdir() if path.is_dir()
        )
        self.assertEqual(len(fixture_bundles), 1)
        self.assertTrue(fixture_bundles[0].is_dir())
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / fixture_bundles[0].name
            shutil.copytree(fixture_bundles[0], copied)
            manifest = json.loads((copied / "manifest.json").read_text())
            self.assertEqual(
                manifest["schema_version"], "kil.v3b1-public-manifest.v1"
            )
            self.assertEqual(
                local_envoy_module.verify_presenter_bundle(copied),
                copied.resolve() / "live.html",
            )

    def assert_summary_citation_is_bound(self, output, *, public):
        summary = (output / "summary.md").read_bytes()
        self.assertEqual(summary.count(self.KTP_CITATION_URL.encode("ascii")), 1)
        summary_sha256 = sha256(summary).hexdigest()
        sums = dict(
            line.split("  ", 1)[::-1]
            for line in (output / "SHA256SUMS").read_text(encoding="ascii").splitlines()
        )
        self.assertEqual(sums["summary.md"], summary_sha256)
        if public:
            public_manifest = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                public_manifest["public_commitment_sha256"],
                local_envoy_module._public_commitment_from_output(
                    output, public_manifest
                ),
            )
        else:
            first = authoritative_bundle_attestation(output)
            second = authoritative_bundle_attestation(output)
            self.assertEqual(first, second)
            self.assertEqual(first["file_sha256"]["summary.md"], summary_sha256)

    def test_complete_summary_cites_ktp_before_private_and_public_binding(self):
        value, requests, decisions, envoy, targets = JoinContractTest().all_records()
        joins = join_evidence(value, requests, decisions, envoy, targets)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provisional = write_evidence_bundle(
                root / "private",
                value,
                requests=requests,
                decisions=decisions,
                envoy=envoy,
                targets=targets,
                joins=joins,
            )
            self.assert_summary_citation_is_bound(provisional, public=False)
            authoritative = authoritative_bundle_attestation(provisional)
            published = finalize_publication(
                provisional,
                root / "public",
                value,
                source_attestations=presenter_source_attestations(
                    provisional, envoy, targets
                ),
                tool_identities=TOOL_IDENTITIES,
                engine_provenance=ENGINE_PROVENANCE,
                global_context_before="personal",
                global_context_after="personal",
                completed=True,
                authoritative_attestation=authoritative,
            )
            self.assert_summary_citation_is_bound(published, public=True)

    def test_failure_summary_cites_ktp_before_private_and_public_binding(self):
        value = manifest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provisional = _prepare_failure_provisional(
                root / "private", value, reset=True
            )
            self.assert_summary_citation_is_bound(provisional, public=False)
            authoritative = authoritative_bundle_attestation(provisional)
            published = finalize_publication(
                provisional,
                root / "public",
                value,
                source_attestations=[],
                tool_identities=TOOL_IDENTITIES,
                engine_provenance=ENGINE_PROVENANCE,
                global_context_before="personal",
                global_context_after="personal",
                completed=False,
                authoritative_attestation=authoritative,
            )
            self.assert_summary_citation_is_bound(published, public=True)

    def assert_postvalidation_publication_mutation_is_rejected(
        self, *, completed
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completion_digests = []

            def mutate_after_validation(stage, path):
                if stage != "after_postrename_validation":
                    return
                live = path / "live.html"
                live.chmod(0o600)
                live.write_bytes(
                    b"<!doctype html><title>coherent late rewrite</title>\n"
                )
                live.chmod(0o444)
                rewrite_public_bundle_hashes(path)

            with self.assertRaisesRegex(
                ControllerError, "changed|identity|publication|presenter"
            ):
                published_presenter_bundle(
                    root,
                    completed=completed,
                    publication_fault=mutate_after_validation,
                    publication_complete=completion_digests.append,
                )
            value, _, _, _, _ = JoinContractTest().all_records()
            self.assertEqual(completion_digests, [])
            self.assertFalse((root / "public" / value["run_id"]).exists())
            self.assertEqual(
                len(
                    list(
                        (root / "private/.publication-staging").glob(
                            ".failed-publication-*"
                        )
                    )
                ),
                1,
            )

    def test_complete_publication_rejects_postvalidation_coherent_rewrite(self):
        self.assert_postvalidation_publication_mutation_is_rejected(
            completed=True
        )

    def test_failure_publication_rejects_postvalidation_coherent_rewrite(self):
        self.assert_postvalidation_publication_mutation_is_rejected(
            completed=False
        )

    def assert_recovery_postvalidation_mutation_is_rejected(self, *, completed):
        with tempfile.TemporaryDirectory() as directory:
            controller, published, value = interrupted_published_recovery(
                Path(directory), completed=completed
            )

            def mutate_after_validation(stage, path):
                if stage != "after_postrename_validation":
                    return
                live = path / "live.html"
                live.chmod(0o600)
                live.write_bytes(
                    b"<!doctype html><title>coherent recovery rewrite</title>\n"
                )
                live.chmod(0o444)
                rewrite_public_bundle_hashes(path)

            controller.publication_fault = mutate_after_validation
            with self.assertRaisesRegex(
                ControllerError, "changed|identity|publication|presenter"
            ):
                controller.down()

            self.assertTrue(published.is_dir())
            self.assert_recovery_authority_retained(controller, value)

    def test_complete_recovery_rejects_postvalidation_coherent_rewrite(self):
        self.assert_recovery_postvalidation_mutation_is_rejected(completed=True)

    def test_failure_recovery_rejects_postvalidation_coherent_rewrite(self):
        self.assert_recovery_postvalidation_mutation_is_rejected(completed=False)

    def assert_recovery_authority_retained(self, controller, value):
        self.assertTrue(controller.journal_path.is_file())
        self.assertTrue(controller.state_path.is_file())
        self.assertTrue(controller.readiness_poison_path.is_file())
        self.assertFalse(
            (controller.completed_root / f"{value['run_id']}.journal.json").exists()
        )

    def test_post_delete_recovery_reattests_complete_publication_before_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, published, value = interrupted_published_recovery(
                Path(directory), completed=True
            )
            live = published / "live.html"
            live.chmod(0o600)
            live.write_bytes(b"<!doctype html><title>repaired hash attacker</title>\n")
            live.chmod(0o444)
            rewrite_public_bundle_hashes(published)

            with self.assertRaisesRegex(
                ControllerError, "authoritative|publication|presenter|evidence"
            ):
                controller.down()

            self.assert_recovery_authority_retained(controller, value)

    def test_post_delete_recovery_reattests_failure_publication_before_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, published, value = interrupted_published_recovery(
                Path(directory), completed=False
            )
            live = published / "live.html"
            live.chmod(0o600)
            live.write_bytes(b"<!doctype html><title>repaired failure</title>\n")
            live.chmod(0o444)
            rewrite_public_bundle_hashes(published)

            with self.assertRaisesRegex(
                ControllerError, "authoritative|publication|presenter|evidence"
            ):
                controller.down()

            self.assert_recovery_authority_retained(controller, value)

    def test_post_delete_recovery_rejects_rewritten_public_class_and_run(self):
        for mutation in ("class", "run"):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as directory,
            ):
                controller, published, value = interrupted_published_recovery(
                    Path(directory), completed=False
                )
                manifest_path = published / "manifest.json"
                public = json.loads(manifest_path.read_text())
                if mutation == "class":
                    public["bundle_class"] = (
                        "intermediate_provisional_local_boundary"
                    )
                    public["run_complete"] = True
                else:
                    identity = dict(public["content_identity"])
                    identity["source_commit"] = "e" * 40
                    identity_digest = sha256(
                        canonical_json(identity).encode("utf-8")
                    ).hexdigest()
                    public["source_commit"] = "e" * 40
                    public["content_identity"] = identity
                    public["content_identity_sha256"] = identity_digest
                    public["run_id"] = f"v3b1-{identity_digest}"
                manifest_path.chmod(0o600)
                manifest_path.write_text(
                    canonical_json(public) + "\n", encoding="utf-8"
                )
                manifest_path.chmod(0o444)
                rewrite_public_bundle_hashes(published)

                with self.assertRaisesRegex(
                    ControllerError,
                    "class|identity|run|publication|source|summary|presenter",
                ):
                    controller.down()

                self.assert_recovery_authority_retained(controller, value)

    def test_post_delete_recovery_accepts_semantically_reattested_crash_after_rename(self):
        for completed in (True, False):
            with (
                self.subTest(completed=completed),
                tempfile.TemporaryDirectory() as directory,
            ):
                controller, published, value = interrupted_published_recovery(
                    Path(directory), completed=completed
                )

                recovered = controller.down()

                self.assertEqual(recovered, published)
                self.assertFalse(controller.journal_path.exists())
                self.assertFalse(controller.state_path.exists())
                self.assertFalse(controller.readiness_poison_path.exists())
                self.assertTrue(
                    (
                        controller.completed_root
                        / f"{value['run_id']}.journal.json"
                    ).is_file()
                )

    def test_publication_quarantines_postrename_mutation_and_allows_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mutated = b"mutated-after-rename\n"

            def mutate_after_rename(stage, path):
                if stage == "after_atomic_rename":
                    live = path / "live.html"
                    live.chmod(0o600)
                    live.write_bytes(mutated)
                    live.chmod(0o444)

            with self.assertRaises(ControllerError):
                published_presenter_bundle(
                    root, publication_fault=mutate_after_rename
                )
            value, _, _, envoy, targets = JoinContractTest().all_records()
            destination = root / "public" / value["run_id"]
            self.assertFalse(destination.exists())
            quarantines = list(
                (root / "private/.publication-staging").glob(
                    ".failed-publication-*"
                )
            )
            self.assertEqual(len(quarantines), 1)
            self.assertEqual((quarantines[0] / "live.html").read_bytes(), mutated)

            provisional = root / "private" / value["run_id"]
            retried = finalize_publication(
                provisional,
                root / "public",
                value,
                source_attestations=presenter_source_attestations(
                    provisional, envoy, targets
                ),
                tool_identities=TOOL_IDENTITIES,
                engine_provenance=ENGINE_PROVENANCE,
                global_context_before="personal",
                global_context_after="personal",
                completed=True,
                authoritative_attestation=authoritative_bundle_attestation(
                    provisional
                ),
            )
            self.assertEqual(
                local_envoy_module.verify_presenter_bundle(retried),
                (retried / "live.html").resolve(),
            )

    def test_publication_rejects_parent_symlink_swap_before_dirfd_rename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public_parent = root / "public"
            displaced = root / "public-displaced"
            outside = root / "outside"
            outside.mkdir()

            def swap_parent(stage, _path):
                if stage == "before_atomic_rename":
                    public_parent.mkdir(exist_ok=True)
                    public_parent.rename(displaced)
                    public_parent.symlink_to(outside, target_is_directory=True)

            with self.assertRaises(ControllerError):
                published_presenter_bundle(
                    root, publication_fault=swap_parent
                )
            self.assertEqual(list(outside.iterdir()), [])

    def test_view_rechecks_descriptor_tree_after_semantic_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            published = published_presenter_bundle(Path(directory))
            live = published / "live.html"
            original = local_envoy_module._validate_presenter_records

            def mutate_after_semantics(payloads, manifest):
                result = original(payloads, manifest)
                live.chmod(0o600)
                live.write_bytes(live.read_bytes())
                live.chmod(0o444)
                return result

            with mock.patch.object(
                local_envoy_module,
                "_validate_presenter_records",
                side_effect=mutate_after_semantics,
            ):
                with self.assertRaisesRegex(
                    ControllerError, "changed|identity|snapshot"
                ):
                    local_envoy_module.verify_presenter_bundle(published)

    def test_view_totalizes_residual_manifest_type_and_depth_failures(self):
        candidates = ("float_identity", "list_checksum", "deep", "surrogate")
        for candidate in candidates:
            with self.subTest(candidate=candidate), tempfile.TemporaryDirectory() as directory:
                published = published_presenter_bundle(Path(directory))
                manifest_path = published / "manifest.json"
                public_manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
                if candidate == "float_identity":
                    public_manifest["content_identity"]["profile_sha256"] = 1.5
                elif candidate == "list_checksum":
                    public_manifest["artifact_sha256"] = [["not", "a", "map"]]
                elif candidate == "deep":
                    value = []
                    for _ in range(10_000):
                        value = [value]
                    with self.assertRaises(ControllerError):
                        local_envoy_module._validate_public_manifest(
                            value, {}
                        )
                    continue
                else:
                    public_manifest["source_commit"] = "\ud800"
                manifest_path.chmod(0o600)
                manifest_path.write_text(
                    json.dumps(
                        public_manifest,
                        ensure_ascii=True,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                manifest_path.chmod(0o444)
                local_envoy_module._write_sums(published)
                with self.assertRaises(SystemExit) as caught:
                    local_envoy_module.main(
                        ["view", "--bundle", str(published)]
                    )
                self.assertTrue(
                    str(caught.exception).startswith("v3b1-local-envoy:")
                )

    def test_embedded_private_build_paths_are_rejected_in_public_provenance(self):
        embedded_paths = (
            "Docker version 29.7.2 build=/private/var/folders/aa/tool",
            "Docker version 29.7.2 cache=/tmp/v3b1-build/context",
            "Docker version 29.7.2 log=C:\\Users\\lab\\build.log",
        )
        for value in embedded_paths:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                poisoned_tools = json.loads(canonical_json(TOOL_IDENTITIES))
                poisoned_tools["docker"]["version_output"] = value
                run, requests, decisions, envoy, targets = (
                    JoinContractTest().all_records()
                )
                joins = join_evidence(run, requests, decisions, envoy, targets)
                provisional = write_evidence_bundle(
                    root / "private",
                    run,
                    requests=requests,
                    decisions=decisions,
                    envoy=envoy,
                    targets=targets,
                    joins=joins,
                )
                sources = presenter_source_attestations(
                    provisional, envoy, targets
                )
                with self.assertRaises(ControllerError):
                    finalize_publication(
                        provisional,
                        root / "public",
                        run,
                        source_attestations=sources,
                        tool_identities=poisoned_tools,
                        engine_provenance=ENGINE_PROVENANCE,
                        global_context_before="personal",
                        global_context_after="personal",
                        completed=True,
                        authoritative_attestation=authoritative_bundle_attestation(
                            provisional
                        ),
                    )
        with tempfile.TemporaryDirectory() as directory:
            published = published_presenter_bundle(Path(directory))
            manifest_path = published / "manifest.json"
            public_manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
            public_manifest["verified_tool_identities"]["docker"][
                "version_output"
            ] = "Docker version 29.7.2 cache=/tmp/v3b1-build/context"
            manifest_path.chmod(0o600)
            manifest_path.write_text(
                canonical_json(public_manifest) + "\n", encoding="utf-8"
            )
            manifest_path.chmod(0o444)
            rewrite_public_bundle_hashes(published)
            with self.assertRaises(ControllerError):
                local_envoy_module.verify_presenter_bundle(published)

    def test_public_boundary_recursively_rejects_sensitive_strings_and_contexts(self):
        local_envoy_module._reject_public_secrets(
            {
                "safe_logical_uris": [
                    "spiffe://kil.local/workload/demo",
                    "docker.io/library/python@sha256:" + HEX_A,
                    "colima_profile_socket",
                ]
            }
        )
        sensitive = (
            "/Users/example/private",
            "/home/example/private",
            "C:\\Users\\example\\private",
            "HOME=/Users/example\nPATH=/usr/bin",
            "-----BEGIN PRIVATE KEY-----",
            "ghp_" + ("a" * 36),
            "AKIA" + ("A" * 16),
            "Bearer do-not-publish",
            "eyJhbGciOiJFZERTQSJ9.e30.signature",
            "v3b1-lab-credential",
        )
        for token in sensitive:
            with self.subTest(token=token):
                with self.assertRaises(ControllerError):
                    local_envoy_module._reject_public_secrets(
                        {"outer": [{"nested": token}]}
                    )
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaises(ControllerError):
                        published_presenter_bundle(
                            Path(directory), global_context=token
                        )
        for context in ("", "x" * 4097, "personal\n", "personal\r", "\ud800"):
            with self.subTest(context=repr(context)), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ControllerError):
                    published_presenter_bundle(
                        Path(directory), global_context=context
                    )

    def test_view_scans_every_nested_public_manifest_string(self):
        with tempfile.TemporaryDirectory() as directory:
            published = published_presenter_bundle(Path(directory))
            manifest_path = published / "manifest.json"
            public_manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
            public_manifest["verified_tool_identities"]["docker"][
                "version_output"
            ] += " Bearer nested-private-token"
            manifest_path.chmod(0o600)
            manifest_path.write_text(
                canonical_json(public_manifest) + "\n", encoding="utf-8"
            )
            manifest_path.chmod(0o444)
            rewrite_public_bundle_hashes(published)

            with self.assertRaisesRegex(ControllerError, "secret|sensitive|private"):
                local_envoy_module.verify_presenter_bundle(published)

    def test_source_attestations_require_nine_distinct_closed_container_ids(self):
        value, requests, decisions, envoy, targets = JoinContractTest().all_records()
        joins = join_evidence(value, requests, decisions, envoy, targets)
        deeply_nested = []
        for _ in range(10_000):
            deeply_nested = [deeply_nested]
        malformed = (
            None,
            [None, None, None],
            [[], {}, {}],
            [{"track": "\ud800"}, {}, {}],
            deeply_nested,
        )
        for index, candidate in enumerate(malformed):
            with self.subTest(candidate_index=index):
                with self.assertRaises(ControllerError):
                    local_envoy_module._validate_source_attestations(
                        candidate, completed=True
                    )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provisional = write_evidence_bundle(
                root / "private",
                value,
                requests=requests,
                decisions=decisions,
                envoy=envoy,
                targets=targets,
                joins=joins,
            )
            source_attestations = presenter_source_attestations(
                provisional, envoy, targets
            )
            source_attestations[0]["container_ids"]["target"] = (
                source_attestations[0]["container_ids"]["authz"]
            )
            with self.assertRaisesRegex(ControllerError, "container IDs.*distinct"):
                finalize_publication(
                    provisional,
                    root / "public",
                    value,
                    source_attestations=source_attestations,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative_bundle_attestation(
                        provisional
                    ),
                )

        with tempfile.TemporaryDirectory() as directory:
            published = published_presenter_bundle(Path(directory))
            manifest_path = published / "manifest.json"
            public_manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
            sources = public_manifest["source_attestations"]
            sources[1]["container_ids"]["authz"] = sources[0][
                "container_ids"
            ]["authz"]
            manifest_path.chmod(0o600)
            manifest_path.write_text(
                canonical_json(public_manifest) + "\n", encoding="utf-8"
            )
            manifest_path.chmod(0o444)
            rewrite_public_bundle_hashes(published)
            with self.assertRaisesRegex(ControllerError, "container IDs.*distinct"):
                local_envoy_module.verify_presenter_bundle(published)

    def test_view_totalizes_malformed_source_attestation_shapes(self):
        candidates = (
            "scalar",
            [],
            [[], {}, {}],
            "\ud800",
        )
        for candidate in candidates:
            with self.subTest(candidate=repr(candidate)), tempfile.TemporaryDirectory() as directory:
                published = published_presenter_bundle(Path(directory))
                manifest_path = published / "manifest.json"
                public_manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
                public_manifest["source_attestations"] = candidate
                manifest_path.chmod(0o600)
                manifest_path.write_text(
                    json.dumps(
                        public_manifest,
                        ensure_ascii=True,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                manifest_path.chmod(0o444)
                local_envoy_module._write_sums(published)

                with self.assertRaises(ControllerError):
                    local_envoy_module.verify_presenter_bundle(published)
                with self.assertRaises(SystemExit) as caught:
                    local_envoy_module.main(
                        ["view", "--bundle", str(published)]
                    )
                self.assertTrue(
                    str(caught.exception).startswith("v3b1-local-envoy:")
                )

    def test_view_recomputes_safe_content_run_and_source_identity(self):
        mutations = ("source_commit", "content_identity", "run_id")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                published = published_presenter_bundle(Path(directory))
                manifest_path = published / "manifest.json"
                public_manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
                if mutation == "source_commit":
                    public_manifest["source_commit"] = "e" * 40
                elif mutation == "content_identity":
                    public_manifest["content_identity"]["source_commit"] = "e" * 40
                    content_digest = sha256(
                        canonical_json(
                            public_manifest["content_identity"]
                        ).encode("utf-8")
                    ).hexdigest()
                    public_manifest["content_identity_sha256"] = content_digest
                    public_manifest["run_id"] = f"v3b1-{content_digest}"
                else:
                    public_manifest["run_id"] = f"v3b1-{HEX_A}"
                decisions = [
                    json.loads(line)
                    for line in (published / "decisions.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ]
                joins = [
                    json.loads(line)
                    for line in (published / "joins.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ]
                summary = local_envoy_module._public_summary(
                    public_manifest
                ).encode("utf-8")
                rewrites = [(published / "summary.md", summary)]
                if mutation == "source_commit":
                    rewrites.append(
                        (
                            published / "live.html",
                            local_envoy_module._render_live_html(
                                local_envoy_module._presenter_model(
                                    public_manifest, decisions, joins
                                )
                            ),
                        )
                    )
                for path, payload in rewrites:
                    path.chmod(0o600)
                    path.write_bytes(payload)
                    path.chmod(0o444)
                manifest_path.chmod(0o600)
                manifest_path.write_text(
                    canonical_json(public_manifest) + "\n", encoding="utf-8"
                )
                manifest_path.chmod(0o444)
                rewrite_public_bundle_hashes(published)

                with self.assertRaisesRegex(
                    ControllerError, "content identity|run identity|source commit"
                ):
                    local_envoy_module.verify_presenter_bundle(published)

    def test_view_rederives_every_public_record_after_repaired_hashes(self):
        empty_relatives = (
            "requests.jsonl",
            "decisions.jsonl",
            "envoy.jsonl",
            "targets.jsonl",
            "joins.jsonl",
            "raw/decisions/credential_policy_baseline.jsonl",
            "raw/decisions/signed_state_only.jsonl",
            "raw/decisions/signed_plus_local_reduce.jsonl",
        )
        for relative in empty_relatives:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                published = published_presenter_bundle(Path(directory))
                path = published / relative
                path.chmod(0o600)
                path.write_bytes(b"")
                path.chmod(0o444)
                rewrite_public_bundle_hashes(published)

                with self.assertRaises(ControllerError):
                    local_envoy_module.verify_presenter_bundle(published)

    def test_view_rejects_repaired_cross_binding_and_identity_substitutions(self):
        for mutation in (
            "upstream_attacker",
            "source_commit",
            "cross_track_order",
            "digest_substitution",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                published = published_presenter_bundle(Path(directory))

                def records(relative):
                    return [
                        json.loads(line)
                        for line in (published / relative)
                        .read_text(encoding="utf-8")
                        .splitlines()
                    ]

                def replace_records(relative, values):
                    path = published / relative
                    path.chmod(0o600)
                    path.write_bytes(
                        b"".join(
                            (canonical_json(value) + "\n").encode("utf-8")
                            for value in values
                        )
                    )
                    path.chmod(0o444)

                if mutation == "upstream_attacker":
                    envoy = records("envoy.jsonl")
                    joins = records("joins.jsonl")
                    envoy[0]["upstream_host"] = "203.0.113.9:8080"
                    joins[0]["upstream_host"] = "203.0.113.9:8080"
                    replace_records("envoy.jsonl", envoy)
                    replace_records("joins.jsonl", joins)
                    manifest_path = published / "manifest.json"
                    value = json.loads(
                        manifest_path.read_text(encoding="utf-8")
                    )
                    track_envoy = [
                        item
                        for item in envoy
                        if item["track"]
                        == LiveTrack.CREDENTIAL_POLICY_BASELINE.value
                    ]
                    value["source_attestations"][0]["raw_envoy_sha256"] = (
                        sha256(
                            b"".join(
                                (canonical_json(item) + "\n").encode("utf-8")
                                for item in track_envoy
                            )
                        ).hexdigest()
                    )
                    manifest_path.chmod(0o600)
                    manifest_path.write_text(
                        canonical_json(value) + "\n", encoding="utf-8"
                    )
                    manifest_path.chmod(0o444)
                elif mutation == "source_commit":
                    manifest_path = published / "manifest.json"
                    value = json.loads(manifest_path.read_text(encoding="utf-8"))
                    old_commit = value["source_commit"]
                    value["source_commit"] = "e" * 40
                    manifest_path.chmod(0o600)
                    manifest_path.write_text(
                        canonical_json(value) + "\n", encoding="utf-8"
                    )
                    manifest_path.chmod(0o444)
                    live = published / "live.html"
                    live.chmod(0o600)
                    live.write_bytes(
                        live.read_bytes().replace(
                            old_commit.encode("ascii"), b"e" * 40
                        )
                    )
                    live.chmod(0o444)
                elif mutation == "cross_track_order":
                    replace_records(
                        "requests.jsonl", list(reversed(records("requests.jsonl")))
                    )
                else:
                    replacement = "9" * 64
                    requests = records("requests.jsonl")
                    decisions = records("decisions.jsonl")
                    envoy = records("envoy.jsonl")
                    targets = records("targets.jsonl")
                    joins = records("joins.jsonl")
                    old_digest = joins[0]["decision_digest"]
                    raw_relative = (
                        "raw/decisions/credential_policy_baseline.jsonl"
                    )
                    raw = records(raw_relative)
                    raw[0]["decision_digest"] = replacement
                    requests[0]["client_decision_digest"] = replacement
                    decisions[0]["decision_digest"] = replacement
                    source = {
                        "schema_version": decisions[0]["source_schema_version"],
                        **{
                            key: item
                            for key, item in decisions[0].items()
                            if key not in {
                                "schema_version",
                                "source_schema_version",
                                "source_record_sha256",
                                "run_id_provenance",
                                "run_id",
                            }
                        },
                    }
                    decisions[0]["source_record_sha256"] = sha256(
                        canonical_json(source).encode("utf-8")
                    ).hexdigest()
                    envoy[0]["decision_digest"] = replacement
                    targets[0]["decision_digest"] = replacement
                    for name in (
                        "decision_digest",
                        "envoy_decision_digest",
                        "client_decision_digest",
                    ):
                        joins[0][name] = replacement
                    replace_records("requests.jsonl", requests)
                    replace_records("decisions.jsonl", decisions)
                    replace_records("envoy.jsonl", envoy)
                    replace_records("targets.jsonl", targets)
                    replace_records("joins.jsonl", joins)
                    replace_records(raw_relative, raw)
                    live = published / "live.html"
                    live.chmod(0o600)
                    live.write_bytes(
                        live.read_bytes().replace(
                            old_digest.encode("ascii"), replacement.encode("ascii")
                        )
                    )
                    live.chmod(0o444)
                rewrite_public_bundle_hashes(
                    published, repair_commitment=mutation != "source_commit"
                )

                with self.assertRaises(ControllerError):
                    local_envoy_module.verify_presenter_bundle(published)

    def test_view_rejects_directory_component_swap_after_enumeration(self):
        for replacement_kind in ("symlink", "directory"):
            with self.subTest(replacement_kind=replacement_kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published = published_presenter_bundle(root)
                decisions = published / "raw/decisions"
                replacement = root / "replacement-decisions"
                shutil.copytree(decisions, replacement)
                original_reader = local_envoy_module._read_stable_public_file_at
                swapped = False

                def swap_component(
                    directory_fd,
                    name,
                    *,
                    maximum_bytes=64 * 1024 * 1024,
                ):
                    nonlocal swapped
                    result = original_reader(
                        directory_fd, name, maximum_bytes=maximum_bytes
                    )
                    if not swapped:
                        swapped = True
                        held = published / "raw/original-decisions"
                        decisions.rename(held)
                        if replacement_kind == "symlink":
                            decisions.symlink_to(replacement, target_is_directory=True)
                        else:
                            shutil.copytree(replacement, decisions)
                    return result

                with mock.patch.object(
                    local_envoy_module,
                    "_read_stable_public_file_at",
                    side_effect=swap_component,
                ):
                    with self.assertRaises(ControllerError):
                        local_envoy_module.verify_presenter_bundle(published)

    def test_view_totalizes_overlong_numeric_source_fields(self):
        for mutation in ("envoy_service_time", "join_upstream_octet"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                published = published_presenter_bundle(Path(directory))
                if mutation == "envoy_service_time":
                    path = published / "envoy.jsonl"
                    envoy = [
                        json.loads(line)
                        for line in path.read_text(encoding="utf-8").splitlines()
                    ]
                    envoy[0]["upstream_service_time"] = "9" * 5000
                    path.chmod(0o600)
                    path.write_bytes(
                        b"".join(
                            (canonical_json(item) + "\n").encode("utf-8")
                            for item in envoy
                        )
                    )
                    path.chmod(0o444)
                    manifest_path = published / "manifest.json"
                    value = json.loads(manifest_path.read_text(encoding="utf-8"))
                    value["source_attestations"][0]["raw_envoy_sha256"] = (
                        sha256(
                            (canonical_json(envoy[0]) + "\n").encode("utf-8")
                        ).hexdigest()
                    )
                    manifest_path.chmod(0o600)
                    manifest_path.write_text(
                        canonical_json(value) + "\n", encoding="utf-8"
                    )
                    manifest_path.chmod(0o444)
                else:
                    path = published / "joins.jsonl"
                    joins = [
                        json.loads(line)
                        for line in path.read_text(encoding="utf-8").splitlines()
                    ]
                    joins[0]["upstream_host"] = f"{'9' * 5000}.0.0.1:8080"
                    path.chmod(0o600)
                    path.write_bytes(
                        b"".join(
                            (canonical_json(item) + "\n").encode("utf-8")
                            for item in joins
                        )
                    )
                    path.chmod(0o444)
                rewrite_public_bundle_hashes(published)

                with self.assertRaises(ControllerError):
                    local_envoy_module.verify_presenter_bundle(published)

    def test_public_manifest_and_final_sha_cover_live_exactly_once(self):
        with tempfile.TemporaryDirectory() as directory:
            published = published_presenter_bundle(Path(directory))
            manifest_value = json.loads(
                (published / "manifest.json").read_text(encoding="utf-8")
            )
            live_digest = sha256((published / "live.html").read_bytes()).hexdigest()
            checksum_lines = (
                published / "SHA256SUMS"
            ).read_text(encoding="ascii").splitlines()

            self.assertEqual(manifest_value["artifact_sha256"]["live.html"], live_digest)
            self.assertEqual(
                [line for line in checksum_lines if line.endswith("  live.html")],
                [f"{live_digest}  live.html"],
            )
            self.assertEqual(
                manifest_value["public_commitment_rule"],
                "sha256_of_canonical_manifest_without_public_commitment_sha256_and_"
                "all_public_file_sha256_except_manifest_and_SHA256SUMS",
            )
            projected = dict(manifest_value)
            projected.pop("public_commitment_sha256")
            committed_files = {
                path.relative_to(published).as_posix(): sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in published.rglob("*")
                if path.is_file()
                and path.name not in {"manifest.json", "SHA256SUMS"}
            }
            expected_commitment = sha256(
                canonical_json(
                    {
                        "schema_version": "kil.v3b1-public-commitment.v1",
                        "manifest": projected,
                        "file_sha256": dict(sorted(committed_files.items())),
                    }
                ).encode("utf-8")
            ).hexdigest()
            self.assertEqual(
                manifest_value["public_commitment_sha256"], expected_commitment
            )
            verify_public_checksums(published)

    def test_view_rejects_untrusted_header_reason_with_repaired_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            published = published_presenter_bundle(Path(directory))
            decisions_path = published / "decisions.jsonl"
            decisions = [
                json.loads(line)
                for line in decisions_path.read_text(encoding="utf-8").splitlines()
            ]
            decisions[0]["untrusted_header_names"] = ["x-kil-mode"]
            source = {
                "schema_version": decisions[0]["source_schema_version"],
                **{
                    key: value
                    for key, value in decisions[0].items()
                    if key not in {
                        "schema_version", "source_schema_version",
                        "source_record_sha256", "run_id_provenance", "run_id",
                    }
                },
            }
            decisions[0]["source_record_sha256"] = sha256(
                canonical_json(source).encode("utf-8")
            ).hexdigest()
            decisions_path.chmod(0o600)
            decisions_path.write_bytes(
                b"".join(
                    (canonical_json(item) + "\n").encode("utf-8")
                    for item in decisions
                )
            )
            decisions_path.chmod(0o444)
            rewrite_public_bundle_hashes(published)

            with self.assertRaisesRegex(ControllerError, "untrusted|normalize"):
                local_envoy_module.verify_presenter_bundle(published)

    def test_view_rejects_wrong_causal_reason_with_repaired_page_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            published = published_presenter_bundle(Path(directory))
            decisions_path = published / "decisions.jsonl"
            decisions = [
                json.loads(line)
                for line in decisions_path.read_text(encoding="utf-8").splitlines()
            ]
            decisions[0]["adapter_reasons"] = ["credential_invalid"]
            source = {
                "schema_version": decisions[0]["source_schema_version"],
                **{
                    key: value
                    for key, value in decisions[0].items()
                    if key
                    not in {
                        "schema_version",
                        "source_schema_version",
                        "source_record_sha256",
                        "run_id_provenance",
                        "run_id",
                    }
                },
            }
            decisions[0]["source_record_sha256"] = sha256(
                canonical_json(source).encode("utf-8")
            ).hexdigest()
            decisions_path.chmod(0o600)
            decisions_path.write_bytes(
                b"".join(
                    (canonical_json(item) + "\n").encode("utf-8")
                    for item in decisions
                )
            )
            decisions_path.chmod(0o444)
            live = published / "live.html"
            live.chmod(0o600)
            live.write_bytes(
                live.read_bytes().replace(
                    b"baseline_permitted", b"credential_invalid"
                )
            )
            live.chmod(0o444)
            rewrite_public_bundle_hashes(published)

            with self.assertRaisesRegex(ControllerError, "causal|normalize"):
                local_envoy_module.verify_presenter_bundle(published)

    def test_presenter_is_durable_before_sha256sums_is_written(self):
        value, requests, decisions, envoy, targets = JoinContractTest().all_records()
        joins = join_evidence(value, requests, decisions, envoy, targets)
        observed = []
        original_write_sums = local_envoy_module._write_sums

        def observe_presenter(output):
            live = output / "live.html"
            observed.append(
                (
                    live.is_file(),
                    stat.S_IMODE(live.stat().st_mode),
                    sha256(live.read_bytes()).hexdigest(),
                )
            )
            return original_write_sums(output)

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            local_envoy_module, "_write_sums", side_effect=observe_presenter
        ):
            output = write_evidence_bundle(
                Path(directory),
                value,
                requests=requests,
                decisions=decisions,
                envoy=envoy,
                targets=targets,
                joins=joins,
            )

        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0][:2], (True, 0o444))
        self.assertRegex(observed[0][2], r"^[a-f0-9]{64}$")

    def test_repaired_checksum_cannot_hide_presenter_change_after_authority(self):
        value, requests, decisions, envoy, targets = JoinContractTest().all_records()
        joins = join_evidence(value, requests, decisions, envoy, targets)
        with tempfile.TemporaryDirectory() as directory:
            output = write_evidence_bundle(
                Path(directory),
                value,
                requests=requests,
                decisions=decisions,
                envoy=envoy,
                targets=targets,
                joins=joins,
            )
            authority = authoritative_bundle_attestation(output)
            live = output / "live.html"
            live.chmod(0o600)
            live.write_bytes(live.read_bytes() + b"<!-- changed -->\n")
            live.chmod(0o444)
            local_envoy_module._write_sums(output)

            with self.assertRaisesRegex(ControllerError, "authoritative.*changed"):
                local_envoy_module._reattest_authoritative_bundle(
                    output, authority
                )

    def test_view_cli_failure_is_closed_and_does_not_echo_private_path_or_content(self):
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / "Users/mistorm/private-bundle"
            private.mkdir(parents=True)
            (private / "secret.txt").write_text("Bearer do-not-echo\n")
            with self.assertRaises(SystemExit) as caught, mock.patch.object(
                local_envoy_module,
                "LocalEnvoyController",
                side_effect=AssertionError("view constructed runtime controller"),
            ):
                local_envoy_module.main(["view", "--bundle", str(private)])

            message = str(caught.exception)
            self.assertIn("v3b1-local-envoy:", message)
            self.assertNotIn(str(private), message)
            self.assertNotIn("mistorm", message)
            self.assertNotIn("Bearer", message)
            self.assertNotIn("do-not-echo", message)

    def test_presenter_escapes_projected_strings_and_rejects_private_tokens(self):
        value, requests, decisions, envoy, targets = JoinContractTest().all_records()
        joins = join_evidence(value, requests, decisions, envoy, targets)
        normalized = local_envoy_module._normalized_decision_records(
            value, decisions
        )
        model = local_envoy_module._presenter_model(value, normalized, joins)
        first = model.tracks[0]
        hostile = local_envoy_module.PresenterModel(
            model.run_id,
            model.request_id,
            model.evidence_scope,
            model.source_commit,
            (
                local_envoy_module.PresenterTrack(
                    first.track,
                    first.outcome,
                    first.http_status,
                    first.target_marker_count,
                    first.forwarded,
                    first.decision_digest,
                    ('<reason data-x="1">&',),
                    first.engine_reasons,
                ),
                *model.tracks[1:],
            ),
            model.complete,
        )

        rendered = local_envoy_module._render_live_html(
            hostile
        ).decode("utf-8")

        self.assertIn("&lt;reason data-x=&quot;1&quot;&gt;&amp;", rendered)
        self.assertNotIn('<reason data-x="1">&', rendered)
        for private_value in (
            "/Users/example/private",
            "/home/example/private",
            "C:\\Users\\example\\private",
            "unix:///private/docker.sock",
            "Bearer private-token",
            "v3b1-lab-credential",
        ):
            with self.subTest(private_value=private_value):
                poisoned = dict(value)
                poisoned["request_id"] = private_value
                with self.assertRaisesRegex(ControllerError, "private material"):
                    local_envoy_module._presenter_model(
                        poisoned, normalized, joins
                    )

    def test_view_rejects_file_replacement_during_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            published = published_presenter_bundle(Path(directory))
            original_reader = local_envoy_module._read_stable_public_file_at
            replaced = False

            def replacing_reader(
                directory_fd,
                name,
                *,
                maximum_bytes=64 * 1024 * 1024,
            ):
                nonlocal replaced
                result = original_reader(
                    directory_fd, name, maximum_bytes=maximum_bytes
                )
                if name == "live.html" and not replaced:
                    replaced = True
                    local_envoy_module._write_file(
                        published / "live.html", result[0], 0o444
                    )
                return result

            with mock.patch.object(
                local_envoy_module,
                "_read_stable_public_file_at",
                side_effect=replacing_reader,
            ):
                with self.assertRaisesRegex(ControllerError, "changed.*snapshot"):
                    local_envoy_module.verify_presenter_bundle(published)

    def test_view_rejects_malformed_overlong_wrong_result_and_digest_jsonl(self):
        for mutation in (
            "malformed",
            "overlong",
            "wrong_result",
            "invalid_digest",
            "digest_mismatch",
            "decision_join_digest_mismatch",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                published = published_presenter_bundle(Path(directory))
                joins_path = published / "joins.jsonl"
                if mutation == "malformed":
                    payload = b"{not-json}\n"
                elif mutation == "overlong":
                    payload = b"[" + (b"0," * 70_000) + b"0]\n"
                else:
                    joins = [
                        json.loads(line)
                        for line in joins_path.read_text(encoding="utf-8").splitlines()
                    ]
                    original_digest = joins[0]["decision_digest"]
                    if mutation == "wrong_result":
                        joins[2]["outcome"] = "permit"
                        joins[2]["http_status"] = 200
                        joins[2]["target_marker_count"] = 1
                    elif mutation == "invalid_digest":
                        joins[0]["decision_digest"] = "not-a-digest"
                        joins[0]["envoy_decision_digest"] = "not-a-digest"
                        joins[0]["client_decision_digest"] = "not-a-digest"
                    elif mutation == "digest_mismatch":
                        joins[0]["decision_digest"] = HEX_A
                    else:
                        joins[0]["decision_digest"] = HEX_A
                        joins[0]["envoy_decision_digest"] = HEX_A
                        joins[0]["client_decision_digest"] = HEX_A
                    payload = b"".join(
                        (canonical_json(item) + "\n").encode("utf-8")
                        for item in joins
                    )
                joins_path.chmod(0o600)
                joins_path.write_bytes(payload)
                joins_path.chmod(0o444)
                if mutation in {
                    "invalid_digest",
                    "digest_mismatch",
                    "decision_join_digest_mismatch",
                }:
                    live = published / "live.html"
                    live.chmod(0o600)
                    live.write_bytes(
                        live.read_bytes().replace(
                            original_digest.encode("ascii"),
                            joins[0]["decision_digest"].encode("ascii"),
                        )
                    )
                    live.chmod(0o444)
                rewrite_public_bundle_hashes(published)

                with self.assertRaises(ControllerError):
                    local_envoy_module.verify_presenter_bundle(published)

    def test_view_rejects_join_track_order_even_with_repaired_public_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            published = published_presenter_bundle(Path(directory))
            joins_path = published / "joins.jsonl"
            joins = joins_path.read_text(encoding="utf-8").splitlines()
            joins_path.chmod(0o600)
            joins_path.write_text("\n".join(reversed(joins)) + "\n", encoding="utf-8")
            joins_path.chmod(0o444)
            rewrite_public_bundle_hashes(published)

            with self.assertRaisesRegex(ControllerError, "track order"):
                local_envoy_module.verify_presenter_bundle(published)

    def test_view_rejects_incomplete_failure_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            published = published_presenter_bundle(
                Path(directory), completed=False
            )

            with self.assertRaisesRegex(ControllerError, "accepted local boundary"):
                local_envoy_module.verify_presenter_bundle(published)

    def test_view_rejects_wrong_scope_promotion_policy_and_claim_exclusions(self):
        mutations = (
            ("evidence_scope", "kind_cluster_validated"),
            ("promotion_status", "promoted"),
            ("evidence_policy", {"inputs": "observed", "outputs": "observed"}),
            ("claim_exclusions", []),
            ("bundle_class", "validated_cluster_boundary"),
            ("run_complete", False),
            ("content_identity_sha256", HEX_A),
            ("run_id", f"v3b1-{HEX_A}"),
            ("teardown", {"status": "pending", "verified_before_publication": False}),
        )
        for field, replacement in mutations:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                published = published_presenter_bundle(Path(directory))
                path = published / "manifest.json"
                value = json.loads(path.read_text(encoding="utf-8"))
                value[field] = replacement
                path.chmod(0o600)
                path.write_text(canonical_json(value) + "\n", encoding="utf-8")
                path.chmod(0o444)
                local_envoy_module._write_sums(published)

                with self.assertRaises(ControllerError):
                    local_envoy_module.verify_presenter_bundle(published)

    def test_view_rejects_missing_extra_symlink_and_checksum_mismatched_presenter(self):
        mutations = ("missing", "extra", "extra_directory", "symlink", "checksum")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published = published_presenter_bundle(root)
                live = published / "live.html"
                if mutation == "missing":
                    live.unlink()
                elif mutation == "extra":
                    (published / "unchecked.txt").write_text("unchecked\n")
                elif mutation == "extra_directory":
                    (published / "unchecked").mkdir()
                elif mutation == "symlink":
                    outside = root / "outside.html"
                    outside.write_bytes(live.read_bytes())
                    live.unlink()
                    live.symlink_to(outside)
                else:
                    live.chmod(0o600)
                    live.write_bytes(live.read_bytes() + b"\n")
                    live.chmod(0o444)

                with self.assertRaises(ControllerError):
                    local_envoy_module.verify_presenter_bundle(published)

    def test_view_rejects_deterministic_outputs_with_repaired_public_hashes(self):
        for relative, original, replacement in (
            ("live.html", b"PERMIT / PERMIT / DENY", b"PERMIT / PERMIT / PERMIT"),
            ("summary.md", b"not_promoted", b"promoted____"),
        ):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                published = published_presenter_bundle(Path(directory))
                path = published / relative
                path.chmod(0o600)
                path.write_bytes(path.read_bytes().replace(original, replacement))
                path.chmod(0o444)
                rewrite_public_bundle_hashes(published)

                with self.assertRaises(ControllerError):
                    local_envoy_module.verify_presenter_bundle(published)

    def test_view_cli_prints_only_verified_path_without_constructing_controller(self):
        with tempfile.TemporaryDirectory() as directory:
            published = published_presenter_bundle(Path(directory))
            stdout = io.StringIO()
            with mock.patch.object(
                local_envoy_module,
                "LocalEnvoyController",
                side_effect=AssertionError("view constructed runtime controller"),
            ), mock.patch.object(local_envoy_module.sys, "stdout", stdout), mock.patch(
                "webbrowser.open",
                side_effect=AssertionError("view opened a browser"),
            ):
                status_code = local_envoy_module.main(
                    ["view", "--bundle", str(published)]
                )

            self.assertEqual(status_code, 0)
            self.assertEqual(
                stdout.getvalue(),
                f"accepted presenter {(published / 'live.html').resolve()}\n",
            )

    def test_view_accepts_only_complete_local_boundary_bundle_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            published = published_presenter_bundle(Path(directory))
            before = {
                path.relative_to(published).as_posix(): (
                    path.read_bytes(), stat.S_IMODE(path.stat().st_mode)
                )
                for path in published.rglob("*")
                if path.is_file()
            }

            presenter = local_envoy_module.verify_presenter_bundle(published)

            self.assertEqual(presenter, (published / "live.html").resolve())
            after = {
                path.relative_to(published).as_posix(): (
                    path.read_bytes(), stat.S_IMODE(path.stat().st_mode)
                )
                for path in published.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)

    def test_teardown_finalization_rerenders_presenter_instead_of_rewriting_it(self):
        value, requests, decisions, envoy, targets = JoinContractTest().all_records()
        joins = join_evidence(value, requests, decisions, envoy, targets)
        with tempfile.TemporaryDirectory() as directory:
            output = write_evidence_bundle(
                Path(directory),
                value,
                requests=requests,
                decisions=decisions,
                envoy=envoy,
                targets=targets,
                joins=joins,
            )
            live = output / "live.html"
            live.chmod(0o600)
            live.write_bytes(live.read_bytes().replace(b"PERMIT / PERMIT / DENY", b"DENY"))
            live.chmod(0o444)

            with self.assertRaisesRegex(ControllerError, "presenter"):
                finalize_teardown_evidence(output, value["run_id"])

    def test_publication_rerenders_presenter_from_public_records_before_rename(self):
        value, requests, decisions, envoy, targets = JoinContractTest().all_records()
        joins = join_evidence(value, requests, decisions, envoy, targets)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provisional = write_evidence_bundle(
                root / "private",
                value,
                requests=requests,
                decisions=decisions,
                envoy=envoy,
                targets=targets,
                joins=joins,
            )
            live = provisional / "live.html"
            live.chmod(0o600)
            live.write_text(
                live.read_text(encoding="utf-8").replace(
                    "PERMIT / PERMIT / DENY", "PERMIT / PERMIT / PERMIT"
                ),
                encoding="utf-8",
            )
            live.chmod(0o444)
            sums = provisional / "SHA256SUMS"
            sums.chmod(0o600)
            local_envoy_module._write_sums(provisional)
            authority = authoritative_bundle_attestation(provisional)

            with self.assertRaisesRegex(ControllerError, "presenter"):
                finalize_publication(
                    provisional,
                    root / "public",
                    value,
                    source_attestations=presenter_source_attestations(
                        provisional, envoy, targets
                    ),
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authority,
                )
            self.assertFalse((root / "public" / value["run_id"]).exists())

    def test_incomplete_bundle_emits_only_nonpresentable_authoritative_page(self):
        value = manifest()
        with tempfile.TemporaryDirectory() as directory:
            output = _prepare_failure_provisional(
                Path(directory), value, reset=True
            )

            text = (output / "live.html").read_text(encoding="utf-8")
            self.assertIn("INCOMPLETE · NOT PRESENTABLE", text)
            self.assertIn("No partial outcome", text)
            self.assertNotIn("PERMIT / PERMIT / DENY", text)
            self.assertNotIn('<article class="track-card">', text)
            authority = authoritative_bundle_attestation(output)
            self.assertEqual(
                authority["file_sha256"]["live.html"],
                sha256((output / "live.html").read_bytes()).hexdigest(),
            )

    def test_live_html_is_authoritative_deterministic_offline_and_claim_bounded(self):
        value, requests, decisions, envoy, targets = JoinContractTest().all_records()
        joins = join_evidence(value, requests, decisions, envoy, targets)
        with tempfile.TemporaryDirectory() as first_directory, tempfile.TemporaryDirectory() as second_directory:
            first = write_evidence_bundle(
                Path(first_directory),
                value,
                requests=requests,
                decisions=decisions,
                envoy=envoy,
                targets=targets,
                joins=joins,
            )
            second = write_evidence_bundle(
                Path(second_directory),
                value,
                requests=list(reversed(requests)),
                decisions=list(reversed(decisions)),
                envoy=list(reversed(envoy)),
                targets=list(reversed(targets)),
                joins=list(reversed(joins)),
            )

            live = (first / "live.html").read_bytes()
            self.assertEqual(live, (second / "live.html").read_bytes())
            self.assertTrue(live.endswith(b"\n"))
            text = live.decode("utf-8")
            self.assertIn("KIL V3B-1 — Local Envoy Boundary", text)
            self.assertIn("OBSERVED · LOCAL ENVOY AUTHORIZATION BOUNDARY", text)
            self.assertIn("INTERMEDIATE · NOT PROMOTED", text)
            self.assertIn("MODELED INPUTS · OBSERVED OUTPUTS", text)
            self.assertIn("DERIVED PRESENTER · JSONL + manifest.json + SHA256SUMS CONTROL", text)
            self.assertIn("PERMIT / PERMIT / DENY", text)
            self.assertIn("1 / 1 / 0", text)
            self.assertIn("default-src &#x27;none&#x27;", text)
            for forbidden in (
                "<script",
                " src=",
                " href=",
                "url(",
                "http://",
                "https://",
                "<img",
                "/Users/",
                "unix:///",
                "Bearer ",
                "v3b1-lab-credential",
                "KIND ORCHESTRATION VALIDATED",
            ):
                self.assertNotIn(forbidden, text)
            sums = (first / "SHA256SUMS").read_text(encoding="ascii")
            self.assertEqual(sums.count("  live.html\n"), 1)
            authority = authoritative_bundle_attestation(first)
            self.assertEqual(
                authority["file_sha256"]["live.html"], sha256(live).hexdigest()
            )

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
                    "live.html",
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
            self.assertEqual(len(sums), 11)
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
                public_manifest["content_identity"],
                value["content_identity"],
            )
            self.assertNotIn("docker_host", canonical_json(
                public_manifest["content_identity"]
            ))
            self.assertNotIn("execution_nonce", public_manifest["content_identity"])
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
            self.assertNotIn(
                "authoritative_bundle_sha256", public_manifest
            )
            self.assertNotIn("private_manifest_sha256", public_manifest)
            self.assertEqual(
                public_manifest["public_commitment_sha256"],
                local_envoy_module._public_commitment_from_output(
                    published, public_manifest
                ),
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
