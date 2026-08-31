from dataclasses import FrozenInstanceError
from contextlib import ExitStack
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
import threading
import unittest
from unittest import mock

import tools.v3b1_local_envoy as local_envoy_module

from kil.canonical import canonical_json
from kil.live_authz import LiveTrack
from kil.v3b_preflight import V3BProfile
from tools.v3b1_harness_contract import (
    ContractError,
    DRIVER_TOPOLOGY_SCHEMA_VERSION,
    DriverLifecycleRecord,
    DockerInventory,
    IntegrationContractFixture,
    RequestFailureProvenance,
    SCHEMA_VERSION,
    SourceCollectionStatus,
    load_integration_contract,
    normalize_transport_exception,
    parse_inventory_rows,
)
from tools.v3b1_driver_transport import (
    DriverTransportError,
    SubprocessDriverProcessFactory,
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

    def test_driver_topology_inventory_is_bounded_to_fifteen_containers_and_six_networks(self):
        tracks = (
            "credential-policy-baseline",
            "signed-state-only",
            "signed-plus-local-reduce",
        )
        container_names = [
            f"kil-v3b1-{role}-{track}-{index:012x}"
            for index, (track, role) in enumerate(
                (
                    (track, role)
                    for track in tracks
                    for role in ("authz", "target", "envoy", "driver", "validate")
                ),
                start=1,
            )
        ]
        network_names = [
            f"kil-v3b1-{segment}-{track}-{index:012x}"
            for index, (track, segment) in enumerate(
                (
                    (track, segment)
                    for track in tracks
                    for segment in ("backend", "frontend")
                ),
                start=1,
            )
        ]

        def rows(names):
            return "".join(
                canonical_json({"id": f"{index:064x}", "name": name}) + "\n"
                for index, name in enumerate(names, start=1)
            )

        self.assertEqual(
            len(
                parse_inventory_rows(
                    rows(container_names),
                    "container",
                    schema_version=DRIVER_TOPOLOGY_SCHEMA_VERSION,
                ).entries
            ),
            15,
        )
        self.assertEqual(
            len(
                parse_inventory_rows(
                    rows(network_names),
                    "network",
                    schema_version=DRIVER_TOPOLOGY_SCHEMA_VERSION,
                ).entries
            ),
            6,
        )
        with self.assertRaisesRegex(ContractError, "cardinality|maximum|bounded"):
            parse_inventory_rows(
                rows(
                    [
                        *container_names,
                        "kil-v3b1-driver-signed-state-only-ffffffffffff",
                    ]
                ),
                "container",
                schema_version=DRIVER_TOPOLOGY_SCHEMA_VERSION,
            )
        with self.assertRaisesRegex(ContractError, "cardinality|maximum|bounded"):
            parse_inventory_rows(
                rows(
                    [
                        *network_names,
                        "kil-v3b1-frontend-signed-state-only-ffffffffffff",
                    ]
                ),
                "network",
                schema_version=DRIVER_TOPOLOGY_SCHEMA_VERSION,
            )

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
                "cycle-5-driver-start-reconstructed-lifecycle",
                "cycle-5-driver-readiness-reconstructed-lifecycle",
                "cycle-5-driver-cancel-reconstructed-lifecycle",
                "cycle-5-diagnostic-only-reconstructed-lifecycle",
            },
        )
        lifecycle = [
            case.record
            for case in fixture.cases
            if case.record_type == "driver_lifecycle"
        ]
        self.assertEqual(len(lifecycle), 4)
        self.assertTrue(all(isinstance(item, DriverLifecycleRecord) for item in lifecycle))
        self.assertEqual(
            {item.event for item in lifecycle},
            {
                "driver_start_complete",
                "driver_readiness_complete",
                "readiness_cancel_complete",
                "readiness_diagnostic_complete",
            },
        )

    def test_recovery_proofs_remain_private_without_public_schema_expansion(self):
        # Recovery authority and final topology-absence proof are private journal
        # facts.  They must not silently widen the frozen public harness schema.
        self.assertEqual(SCHEMA_VERSION, "kil.v3b1-integration-contract.v1")
        self.assertEqual(
            DRIVER_TOPOLOGY_SCHEMA_VERSION,
            "kil.v3b1-integration-contract.v2",
        )
        expected_record_types = {
            self.FIXTURE: {
                "docker_inventory",
                "request_failure",
                "source_collection",
            },
            self.DRIVER_FIXTURE: {"docker_inventory", "driver_lifecycle"},
        }
        for path, expected in expected_record_types.items():
            value = json.loads(path.read_text())
            self.assertEqual(
                {case["record_type"] for case in value["cases"]}, expected
            )
            self.assertNotIn("topology_absence_attested", canonical_json(value))

    def test_driver_lifecycle_transcripts_are_v2_only_closed_and_secret_free(self):
        value = json.loads(self.DRIVER_FIXTURE.read_text())
        lifecycle_case = next(
            case for case in value["cases"]
            if case["record_type"] == "driver_lifecycle"
        )
        with tempfile.TemporaryDirectory(dir=self.DRIVER_FIXTURE.parent) as directory:
            path = Path(directory) / "fixture.json"
            legacy = {
                "schema_version": "kil.v3b1-integration-contract.v1",
                "cases": [lifecycle_case],
            }
            path.write_text(canonical_json(legacy) + "\n")
            with self.assertRaisesRegex(ContractError, "v2|schema|record type"):
                load_integration_contract(path)

            for mutation in (
                {"stderr": "private output"},
                {"driver_id": "d" * 12},
                {"track": "unexpected"},
            ):
                changed = json.loads(json.dumps(value))
                selected = next(
                    case for case in changed["cases"]
                    if case["record_type"] == "driver_lifecycle"
                    and case["record"]["event"] == "driver_start_complete"
                )
                selected["record"]["details"].update(mutation)
                path.write_text(canonical_json(changed) + "\n")
                with self.assertRaises(ContractError):
                    load_integration_contract(path)

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


class _DriverStateRunner(FakeRunner):
    STATE_FORMAT = "{{.Id}} {{.State.Running}} {{.State.Status}}"

    def __init__(self, states):
        super().__init__()
        self.states = dict(states)

    def run(self, argv, **kwargs):
        command = list(argv)
        self.calls.append(
            (
                command,
                kwargs.get("cwd"),
                kwargs.get("input_text"),
                kwargs.get("env"),
                kwargs.get("timeout_s", 30),
            )
        )
        if "inspect" in command and self.STATE_FORMAT in command:
            full_id = command[-1]
            state = self.states[full_id]
            if state == "malformed":
                return CommandResult(0, "ambiguous private state\n", "")
            running = state is True
            status = "running" if running else "exited"
            return CommandResult(
                0,
                f"{full_id} {'true' if running else 'false'} {status}\n",
                "",
            )
        if "stop" in command:
            self.states[command[-1]] = False
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
        driver_bootstrap_sha256=HEX_A,
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
    result = {
        "attempt_count": 1,
        "connect_monotonic_ns": 5,
        "decision_digest": client_digest,
        "receive_monotonic_ns": 20,
        "response_status": 403 if denied else 200,
        "retry_performed": False,
        "schema_version": "kil.v3b1-driver-result.v1",
        "send_monotonic_ns": 10,
        "status": "complete",
        "track": track.value,
    }
    definition_sha256 = next(
        item["sha256"]
        for item in run_manifest["content_identity"]["driver_definition_sha256"]
        if item["track"] == track.value
    )
    driver_full_id = {
        LiveTrack.CREDENTIAL_POLICY_BASELINE: "d" * 64,
        LiveTrack.SIGNED_STATE_ONLY: "e" * 64,
        LiveTrack.SIGNED_PLUS_LOCAL_REDUCE: "f" * 64,
    }[track]
    value = {
        "schema_version": "kil.v3b1-request.v2",
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
        "request_transport": "in_network_request_driver",
        "driver_role": "request_driver",
        "driver_full_id": driver_full_id,
        "driver_image_id": run_manifest["kil_image_id"],
        "driver_definition_sha256": definition_sha256,
        "driver_result_sha256": sha256(
            (canonical_json(result) + "\n").encode("utf-8")
        ).hexdigest(),
    }
    value.update(changes)
    return value


def driver_results_for_requests(requests):
    """Reconstruct deterministic test-only raw driver sources from v2 requests."""
    results = {}
    for request in requests:
        track = LiveTrack(request["track"])
        result = {
            "attempt_count": 1,
            "connect_monotonic_ns": 5,
            "decision_digest": request["client_decision_digest"],
            "receive_monotonic_ns": request["receive_monotonic_ns"],
            "response_status": request["client_response_status"],
            "retry_performed": False,
            "schema_version": "kil.v3b1-driver-result.v1",
            "send_monotonic_ns": request["send_monotonic_ns"],
            "status": "complete",
            "track": track.value,
        }
        results[track] = (canonical_json(result) + "\n").encode("utf-8")
    return results


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
    def test_network_connect_transition_is_closed_full_id_and_intent_precedes_complete(self):
        details = {
            "container_id": HEX_A,
            "container_name": "kil-v3b1-envoy-signed-state-only-aaaaaaaaaaaa",
            "network_id": HEX_B,
            "network_name": "kil-v3b1-frontend-signed-state-only-aaaaaaaaaaaa",
            "alias": "envoy",
        }
        local_envoy_module._validate_lifecycle_event_details(
            "network_connect_intent", details
        )
        with self.assertRaisesRegex(ControllerError, "connect|fields|identity"):
            local_envoy_module._validate_lifecycle_event_details(
                "network_connect_intent",
                {**details, "container_id": "a" * 12},
            )
        requests = {
            track.value: {"status": "not_attempted", "intent_id": None}
            for track in LiveTrack
        }
        creation_events = [
            {
                "sequence": 1,
                "event": "container_create_intent",
                "details": {"name": details["container_name"]},
            },
            {
                "sequence": 2,
                "event": "container_create_complete",
                "details": {
                    "name": details["container_name"],
                    "id": details["container_id"],
                },
            },
            {
                "sequence": 3,
                "event": "network_create_intent",
                "details": {"name": details["network_name"]},
            },
            {
                "sequence": 4,
                "event": "network_create_complete",
                "details": {
                    "name": details["network_name"],
                    "id": details["network_id"],
                },
            },
        ]
        with self.assertRaisesRegex(ControllerError, "connect|intent"):
            local_envoy_module._validate_lifecycle_history(
                [
                    *creation_events,
                    {
                        "sequence": 5,
                        "event": "network_connect_complete",
                        "details": details,
                    },
                ],
                requests,
            )
        local_envoy_module._validate_lifecycle_history(
            [
                *creation_events,
                {
                    "sequence": 5,
                    "event": "network_connect_intent",
                    "details": details,
                },
                {
                    "sequence": 6,
                    "event": "network_connect_complete",
                    "details": details,
                },
            ],
            requests,
        )

        command = local_envoy_module._network_connect_command(
            ["/locked/docker", "--host", "unix:///private.sock"],
            details,
        )
        self.assertEqual(
            command,
            [
                "/locked/docker",
                "--host",
                "unix:///private.sock",
                "network",
                "connect",
                "--alias",
                "envoy",
                HEX_B,
                HEX_A,
            ],
        )
        self.assertNotIn(details["network_name"], command)
        self.assertNotIn(details["container_name"], command)

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
        network_name = "kil-v3b1-backend-credential-policy-baseline-aaaaaaaaaaaa"
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
            "name": "kil-v3b1-backend-credential-policy-baseline-bbbbbbbbbbbb",
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
            for item in bound["network_objects"]:
                journal_event(
                    controller.journal_path,
                    "network_create_intent",
                    {"name": item["name"]},
                )
                journal_event(
                    controller.journal_path,
                    "network_create_complete",
                    {"id": item["id"], "name": item["name"]},
                )
            for item in bound["objects"]:
                journal_event(
                    controller.journal_path,
                    "container_create_intent",
                    {"name": item["name"]},
                )
                journal_event(
                    controller.journal_path,
                    "container_create_complete",
                    {"id": item["id"], "name": item["name"]},
                )
            for track in LiveTrack:
                track_value = next(
                    item
                    for item in value["tracks"]
                    if item["track"] == track.value
                )
                envoy = next(
                    item
                    for item in bound["objects"]
                    if item["name"] == track_value["envoy_container"]
                )
                frontend = next(
                    item
                    for item in bound["network_objects"]
                    if item["name"] == track_value["frontend_network"]
                )
                details = {
                    "container_id": envoy["id"],
                    "container_name": envoy["name"],
                    "network_id": frontend["id"],
                    "network_name": frontend["name"],
                    "alias": "envoy",
                }
                journal_event(
                    controller.journal_path,
                    "network_connect_intent",
                    details,
                )
                journal_event(
                    controller.journal_path,
                    "network_connect_complete",
                    details,
                )
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
                    schema_version="kil.v3b1-integration-contract.v2",
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
                        schema_version="kil.v3b1-integration-contract.v2",
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

            self.assertEqual(len(recovered["objects"]), 11)
            self.assertNotIn(identity["id"], {item["id"] for item in recovered["objects"]})
            self.assertEqual(
                [
                    event["event"]
                    for event in recovered_journal["events"]
                    if event["event"].startswith("container_remove_")
                ],
                ["container_remove_intent", "container_remove_complete"],
            )

    def test_container_stop_history_is_creation_bound_exact_and_totalized(self):
        name = "kil-v3b1-envoy-credential-policy-baseline-bbbbbbbbbbbb"
        identity = {"id": HEX_B, "name": name, "role": "envoy"}
        creation = [
            {"event": "container_create_intent", "details": {"name": name}},
            {
                "event": "container_create_complete",
                "details": {"id": HEX_B, "name": name},
            },
        ]
        intent = {"event": "container_stop_intent", "details": identity}
        completion = {
            "event": "container_stop_complete",
            "details": {"id": HEX_B, "name": name},
        }

        self.assertEqual(
            local_envoy_module._container_stop_transition(creation, identity),
            "unstarted",
        )
        self.assertEqual(
            local_envoy_module._container_stop_transition(
                [*creation, intent], identity
            ),
            "pending",
        )
        self.assertEqual(
            local_envoy_module._container_stop_transition(
                [*creation, intent, completion], identity
            ),
            "complete",
        )

        invalid_histories = (
            [intent],
            [*creation, completion],
            [*creation, intent, intent],
            [
                creation[0],
                {
                    "event": "container_create_complete",
                    "details": {"id": HEX_C, "name": name},
                },
            ],
            [
                *creation,
                {
                    "event": "container_stop_intent",
                    "details": {**identity, "id": HEX_C},
                },
            ],
            [
                *creation,
                {
                    "event": "container_stop_intent",
                    "details": {
                        **identity,
                        "name": name.replace("envoy", "authz"),
                    },
                },
            ],
            [
                *creation,
                {
                    "event": "container_stop_intent",
                    "details": {**identity, "role": "authz"},
                },
            ],
        )
        for history in invalid_histories:
            with self.subTest(history=history):
                with self.assertRaises(ControllerError):
                    local_envoy_module._container_stop_transition(history, identity)

        with self.assertRaises(ControllerError):
            local_envoy_module._container_stop_transition(
                creation, {**identity, "role": []}
            )
        with self.assertRaises(ControllerError):
            local_envoy_module._validate_lifecycle_event_details(
                "container_stop_intent", {**identity, "role": []}
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
                    schema_version="kil.v3b1-integration-contract.v2",
                )
                empty_networks = parse_inventory_rows(
                    "",
                    "network",
                    schema_version="kil.v3b1-integration-contract.v2",
                )

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
                    schema_version="kil.v3b1-integration-contract.v2",
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
                            parse_inventory_rows(
                                "",
                                "container",
                                schema_version=(
                                    "kil.v3b1-integration-contract.v2"
                                ),
                            )
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

    def test_partial_up_envoy_attachment_recovery_is_journal_phase_exact(self):
        scenarios = (
            ("no_intent_backend", "unstarted", "backend", "running", True),
            ("no_intent_dual", "unstarted", "dual", "running", False),
            ("pending_before_effect", "pending", "backend", "running", True),
            ("pending_after_effect", "pending", "dual", "running", True),
            ("pending_wrong_alias", "pending", "wrong_alias", "running", False),
            ("pending_cross_id", "pending", "cross_id", "running", False),
            ("complete_dual", "complete", "dual", "running", True),
            ("complete_backend", "complete", "backend", "running", False),
            ("complete_stopped", "complete", "stopped", "exited", True),
            (
                "complete_stopped_stale_endpoint",
                "complete",
                "stopped_stale",
                "exited",
                False,
            ),
        )
        for track_index, track in enumerate(LiveTrack):
            for scenario, phase, observed_shape, runtime_state, accepted in scenarios:
                with (
                    self.subTest(
                        track=track.value,
                        scenario=scenario,
                    ),
                    tempfile.TemporaryDirectory() as directory,
                ):
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
                    value = manifest(
                        docker_host=controller.docker_host,
                        execution_nonce=HEX_A,
                    )
                    materialize_run_inputs(root, value)
                    track_value = next(
                        item
                        for item in value["tracks"]
                        if item["track"] == track.value
                    )
                    container_id = str(track_index + 1) * 64
                    backend_id = chr(ord("a") + track_index) * 64
                    frontend_id = chr(ord("d") + track_index) * 64
                    cross_id = "f" * 64 if frontend_id != "f" * 64 else "9" * 64
                    envoy_name = track_value["envoy_container"]
                    backend_name = track_value["backend_network"]
                    frontend_name = track_value["frontend_network"]
                    runtime_labels = {
                        "kil.v3b1.managed": "true",
                        "kil.v3b1.run-id": value["run_id"],
                        "kil.v3b1.role": "envoy",
                        "kil.v3b1.track": track.value,
                    }
                    network_labels = {
                        "kil.v3b1.managed": "true",
                        "kil.v3b1.run-id": value["run_id"],
                        "kil.v3b1.track": track.value,
                    }
                    immutable_labels = {
                        "org.opencontainers.image.version": "22.04"
                    }
                    dual_homed = observed_shape in {
                        "dual", "wrong_alias", "cross_id", "stopped",
                        "stopped_stale",
                    }
                    stale_endpoint = observed_shape == "stopped_stale"
                    aliases = (
                        ["not-envoy", container_id[:12]]
                        if observed_shape == "wrong_alias"
                        else ["envoy", container_id[:12]]
                    )
                    raw_networks = {
                        backend_name: {
                            "Aliases": [envoy_name, container_id[:12]]
                        }
                    }
                    if dual_homed:
                        raw_networks[frontend_name] = {"Aliases": aliases}
                    config_path = (
                        _runtime_root(root, value) / track.value / "envoy.json"
                    )
                    container_raw = {
                        "Id": container_id,
                        "Name": f"/{envoy_name}",
                        "Image": value["envoy_image_id"],
                        "Config": {
                            "Image": value["envoy_image_digest"],
                            "Labels": {**immutable_labels, **runtime_labels},
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
                            "OpenStdin": False,
                            "Tty": False,
                        },
                        "HostConfig": {
                            "Privileged": False,
                            "NetworkMode": backend_name,
                            "PidMode": "",
                            "IpcMode": "private",
                            "UTSMode": "",
                            "UsernsMode": "",
                            "CgroupnsMode": "private",
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
                                "Config": {
                                    "max-file": "1",
                                    "max-size": "1m",
                                },
                            },
                            "Tmpfs": {
                                "/tmp": (
                                    "rw,noexec,nosuid,nodev,size=16777216,"
                                    "uid=65532,gid=65532,mode=448"
                                )
                            },
                            "PortBindings": {},
                        },
                        "State": {
                            "Running": runtime_state == "running",
                            "Status": runtime_state,
                        },
                        "NetworkSettings": {
                            "Networks": raw_networks,
                            "Ports": None if runtime_state == "running" else {},
                        },
                        "Mounts": [
                            {
                                "Source": str(config_path.resolve()),
                                "Destination": "/etc/envoy/envoy.json",
                                "RW": False,
                            }
                        ],
                    }
                    image_raw = {
                        "Os": "linux",
                        "Architecture": "arm64",
                        "Config": {
                            "Env": ["PATH=/usr/local/bin"],
                            "Labels": immutable_labels,
                        },
                    }

                    def endpoint(name):
                        return {
                            "Name": name,
                            "EndpointID": "e" * 64,
                            "MacAddress": "02:42:ac:12:00:02",
                            "IPv4Address": "172.18.0.2/16",
                            "IPv6Address": "",
                        }

                    network_raw = {
                        backend_id: {
                            "Id": backend_id,
                            "Name": backend_name,
                            "Driver": "bridge",
                            "Internal": True,
                            "Labels": network_labels,
                            "Containers": (
                                {container_id: endpoint(envoy_name)}
                                if runtime_state == "running" or stale_endpoint
                                else {}
                            ),
                        },
                        frontend_id: {
                            "Id": frontend_id,
                            "Name": frontend_name,
                            "Driver": "bridge",
                            "Internal": True,
                            "Labels": network_labels,
                            "Containers": (
                                {
                                    (
                                        cross_id
                                        if observed_shape == "cross_id"
                                        else container_id
                                    ): endpoint(envoy_name)
                                }
                                if dual_homed
                                and (runtime_state == "running" or stale_endpoint)
                                else {}
                            ),
                        },
                    }

                    class AttachmentRunner(FakeRunner):
                        def run(self, argv, **kwargs):
                            self.calls.append((list(argv), kwargs))
                            if argv[5:7] == ["image", "inspect"]:
                                return CommandResult(
                                    0, canonical_json(image_raw) + "\n", ""
                                )
                            if argv[5:7] == ["network", "inspect"]:
                                return CommandResult(
                                    0,
                                    canonical_json(network_raw[argv[-1]]) + "\n",
                                    "",
                                )
                            if argv[5] == "inspect":
                                return CommandResult(
                                    0, canonical_json(container_raw) + "\n", ""
                                )
                            raise AssertionError(f"unexpected command: {argv}")

                    controller.runner = AttachmentRunner()
                    private_manifest = (
                        controller.private_root / "manifests/run.json"
                    )
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
                    for kind, name, object_id in (
                        ("network", backend_name, backend_id),
                        ("network", frontend_name, frontend_id),
                        ("container", envoy_name, container_id),
                    ):
                        journal_event(
                            controller.journal_path,
                            f"{kind}_create_intent",
                            {"name": name},
                        )
                        journal_event(
                            controller.journal_path,
                            f"{kind}_create_complete",
                            {"name": name, "id": object_id},
                        )
                    connect_details = {
                        "container_id": container_id,
                        "container_name": envoy_name,
                        "network_id": frontend_id,
                        "network_name": frontend_name,
                        "alias": "envoy",
                    }
                    if phase in {"pending", "complete"}:
                        journal_event(
                            controller.journal_path,
                            "network_connect_intent",
                            connect_details,
                        )
                    if phase == "complete":
                        journal_event(
                            controller.journal_path,
                            "network_connect_complete",
                            connect_details,
                        )
                    containers = parse_inventory_rows(
                        canonical_json(
                            {"id": container_id, "name": envoy_name}
                        )
                        + "\n",
                        "container",
                        schema_version=DRIVER_TOPOLOGY_SCHEMA_VERSION,
                    )
                    networks = parse_inventory_rows(
                        "".join(
                            canonical_json({"id": object_id, "name": name})
                            + "\n"
                            for object_id, name in (
                                (backend_id, backend_name),
                                (frontend_id, frontend_name),
                            )
                        ),
                        "network",
                        schema_version=DRIVER_TOPOLOGY_SCHEMA_VERSION,
                    )
                    with mock.patch.object(
                        controller,
                        "_docker_inventory",
                        side_effect=lambda kind: (
                            containers if kind == "container" else networks
                        ),
                    ):
                        if accepted:
                            recovered, _, _ = controller._load_for_down()
                            attachment = recovered["envoy_attachments"][track.value]
                            self.assertEqual(attachment["phase"], phase)
                            self.assertEqual(
                                attachment["container_id"], container_id
                            )
                            self.assertEqual(
                                attachment["network_id"], frontend_id
                            )
                        else:
                            with self.assertRaisesRegex(
                                ControllerError,
                                "attachment|alias|membership|network",
                            ):
                                controller._load_for_down()

    def test_created_driver_uses_only_realized_frontend_membership(self):
        value = manifest()
        track = LiveTrack.CREDENTIAL_POLICY_BASELINE
        track_value = next(
            item for item in value["tracks"] if item["track"] == track.value
        )
        envoy_id = "1" * 64
        driver_id = "2" * 64
        frontend_id = "3" * 64
        objects = [
            {
                "id": envoy_id,
                "name": track_value["envoy_container"],
                "role": "envoy",
                "track": track.value,
                "runtime_attestation": {"state": "running"},
            },
            {
                "id": driver_id,
                "name": track_value["driver_container"],
                "role": "driver",
                "track": track.value,
                "runtime_attestation": {"state": "created"},
            },
        ]
        attachment = {
            "track": track.value,
            "phase": "complete",
            "container_id": envoy_id,
            "container_name": track_value["envoy_container"],
            "network_id": frontend_id,
            "network_name": track_value["frontend_network"],
            "alias": "envoy",
        }
        envoy_member = {
            envoy_id: {
                "name": track_value["envoy_container"],
                "role": "envoy",
            }
        }

        self.assertEqual(
            local_envoy_module._network_member_identity_options(
                objects,
                value,
                track.value,
                "frontend",
                attachment,
            ),
            (envoy_member,),
        )

        attachment["phase"] = "pending"
        self.assertEqual(
            local_envoy_module._network_member_identity_options(
                objects,
                value,
                track.value,
                "frontend",
                attachment,
            ),
            ({}, envoy_member),
        )

        attachment["phase"] = "complete"
        realized_members = {
            **envoy_member,
            driver_id: {
                "name": track_value["driver_container"],
                "role": "driver",
            },
        }
        objects[1]["runtime_attestation"]["state"] = "running"
        self.assertEqual(
            local_envoy_module._network_member_identity_options(
                objects,
                value,
                track.value,
                "frontend",
                attachment,
            ),
            (realized_members,),
        )

        for state in ("created", "exited", "dead"):
            with self.subTest(unrealized_state=state):
                objects[1]["runtime_attestation"]["state"] = state
                self.assertEqual(
                    local_envoy_module._network_member_identity_options(
                        objects,
                        value,
                        track.value,
                        "frontend",
                        attachment,
                    ),
                    (envoy_member,),
                )

        for state in (None, "paused", True, [], {}):
            with self.subTest(invalid_state=state):
                objects[1]["runtime_attestation"]["state"] = state
                with self.assertRaisesRegex(
                    ControllerError, "frontend driver state is invalid"
                ):
                    local_envoy_module._network_member_identity_options(
                        objects,
                        value,
                        track.value,
                        "frontend",
                        attachment,
                    )

    def test_stopped_services_are_owned_without_physical_network_endpoints(self):
        value = manifest()
        track = LiveTrack.CREDENTIAL_POLICY_BASELINE
        track_value = next(
            item for item in value["tracks"] if item["track"] == track.value
        )
        ids = {
            "authz": "4" * 64,
            "target": "5" * 64,
            "envoy": "6" * 64,
            "driver": "7" * 64,
        }
        objects = [
            {
                "id": ids[role],
                "name": track_value[f"{role}_container"],
                "role": role,
                "track": track.value,
                "runtime_attestation": {
                    "state": (
                        "exited"
                        if role == "envoy"
                        else "created"
                        if role == "driver"
                        else "running"
                    )
                },
            }
            for role in ("authz", "target", "envoy", "driver")
        ]
        attachment = {
            "track": track.value,
            "phase": "complete",
            "container_id": ids["envoy"],
            "container_name": track_value["envoy_container"],
            "network_id": "8" * 64,
            "network_name": track_value["frontend_network"],
            "alias": "envoy",
        }
        backend_members = {
            ids[role]: {
                "name": track_value[f"{role}_container"],
                "role": role,
            }
            for role in ("authz", "target")
        }

        self.assertEqual(
            local_envoy_module._network_member_identity_options(
                objects,
                value,
                track.value,
                "backend",
                attachment,
            ),
            (backend_members,),
        )
        self.assertEqual(
            local_envoy_module._network_member_identity_options(
                objects,
                value,
                track.value,
                "frontend",
                attachment,
            ),
            ({},),
        )

        next(item for item in objects if item["role"] == "target")[
            "runtime_attestation"
        ]["state"] = "dead"
        self.assertEqual(
            local_envoy_module._network_member_identity_options(
                objects,
                value,
                track.value,
                "backend",
                attachment,
            ),
            ({
                ids["authz"]: {
                    "name": track_value["authz_container"],
                    "role": "authz",
                },
            },),
        )

        next(item for item in objects if item["role"] == "envoy")[
            "runtime_attestation"
        ]["state"] = "running"
        self.assertEqual(
            local_envoy_module._network_member_identity_options(
                objects,
                value,
                track.value,
                "frontend",
                attachment,
            ),
            ({
                ids["envoy"]: {
                    "name": track_value["envoy_container"],
                    "role": "envoy",
                },
            },),
        )

        next(item for item in objects if item["role"] == "envoy")[
            "runtime_attestation"
        ]["state"] = "paused"
        for segment in ("backend", "frontend"):
            with self.subTest(invalid_segment_state=segment):
                with self.assertRaisesRegex(
                    ControllerError, "network member state is invalid"
                ):
                    local_envoy_module._network_member_identity_options(
                        objects,
                        value,
                        track.value,
                        segment,
                        attachment,
                    )

    def test_reverify_uses_fresh_driver_state_for_frontend_membership(self):
        value = manifest()
        track = LiveTrack.CREDENTIAL_POLICY_BASELINE
        track_value = next(
            item for item in value["tracks"] if item["track"] == track.value
        )
        envoy_id = "4" * 64
        driver_id = "5" * 64
        frontend_id = "6" * 64
        envoy = {
            "id": envoy_id,
            "name": track_value["envoy_container"],
            "role": "envoy",
            "track": track.value,
            "runtime_attestation": {"state": "running"},
        }
        recorded_driver = {
            "id": driver_id,
            "name": track_value["driver_container"],
            "role": "driver",
            "track": track.value,
            "runtime_attestation": {"state": "created"},
        }
        current_driver = {
            **recorded_driver,
            "runtime_attestation": {"state": "exited"},
        }
        network = {
            "id": frontend_id,
            "name": track_value["frontend_network"],
            "track": track.value,
            "segment": "frontend",
        }
        state = {
            "manifest": value,
            "objects": [envoy, recorded_driver],
            "network_objects": [network],
        }
        attachments = {
            item.value: {
                "track": item.value,
                "phase": "complete",
                "container_id": (
                    envoy_id if item is track else str(item.value)[0] * 64
                ),
                "container_name": next(
                    track_item["envoy_container"]
                    for track_item in value["tracks"]
                    if track_item["track"] == item.value
                ),
                "network_id": (
                    frontend_id if item is track else "9" * 64
                ),
                "network_name": next(
                    track_item["frontend_network"]
                    for track_item in value["tracks"]
                    if track_item["track"] == item.value
                ),
                "alias": "envoy",
            }
            for item in LiveTrack
        }
        controller = LocalEnvoyController(
            ROOT,
            FakeRunner(),
            home=Path("/Users/lab"),
            port_probe=lambda port: False,
            tool_verifier=lambda: TOOL_IDENTITIES,
        )

        def inspect_container(_identifier, _manifest, role, _track, **_kwargs):
            return current_driver if role == "driver" else envoy

        inspect_network = mock.Mock(return_value=network)
        with (
            mock.patch.object(
                local_envoy_module,
                "load_bound_active_state",
                return_value=state,
            ),
            mock.patch.object(
                local_envoy_module,
                "load_lifecycle_journal",
                return_value={"events": []},
            ),
            mock.patch.object(
                local_envoy_module,
                "_envoy_attachment_expectations",
                return_value=attachments,
            ),
            mock.patch.object(
                local_envoy_module,
                "_driver_recovery_authority",
                return_value={"phase": "complete", "request_eligible": True},
            ),
            mock.patch.object(
                local_envoy_module,
                "_container_attestation_matches",
                return_value=True,
            ),
            mock.patch.object(
                controller,
                "_inspect_container",
                side_effect=inspect_container,
            ),
            mock.patch.object(
                controller,
                "_inspect_network",
                inspect_network,
            ),
        ):
            controller._load_and_reverify()

        self.assertEqual(
            inspect_network.call_args.kwargs["expected_members"],
            {
                envoy_id: {
                    "name": track_value["envoy_container"],
                    "role": "envoy",
                },
            },
        )

    def test_cli_exposes_only_the_seven_approved_subcommands(self):
        parser = make_parser()

        for name in ("preflight", "up", "readiness", "run", "collect", "down"):
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
                "src/kil/v3b1_driver_protocol.py",
                "src/kil/v3b1_request_driver.py",
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

        self.assertEqual(value["schema_version"], "kil.v3b1-manifest.v2")
        self.assertRegex(value["run_id"], r"^v3b1-[a-f0-9]{64}$")
        identity = value["content_identity"]
        self.assertEqual(
            identity["schema_version"], "kil.v3b1-content-identity.v3"
        )
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
        self.assertEqual(len(value["segment_definitions"]), 6)
        self.assertEqual(len(value["driver_definitions"]), 3)
        self.assertEqual(len(identity["segment_definitions"]), 6)
        self.assertEqual(len(identity["driver_definition_sha256"]), 3)
        self.assertEqual(
            {item["segment"] for item in value["segment_definitions"]},
            {"frontend", "backend"},
        )
        self.assertTrue(
            all(item["internal"] is True for item in value["segment_definitions"])
        )
        self.assertTrue(
            all(
                item["endpoint"] == {"host": "envoy", "port": 8080}
                for item in value["driver_definitions"]
            )
        )
        frontend_sha = {
            item["track"]: sha256(
                (canonical_json(item) + "\n").encode("utf-8")
            ).hexdigest()
            for item in value["segment_definitions"]
            if item["segment"] == "frontend"
        }
        self.assertEqual(
            [item["frontend_segment_sha256"] for item in value["driver_definitions"]],
            [frontend_sha[track.value] for track in LiveTrack],
        )
        self.assertEqual(
            identity["driver_definition_sha256"],
            [
                {
                    "track": item["track"],
                    "sha256": sha256(
                        (canonical_json(item) + "\n").encode("utf-8")
                    ).hexdigest(),
                }
                for item in value["driver_definitions"]
            ],
        )
        definition_bytes = canonical_json(
            {
                "segments": value["segment_definitions"],
                "drivers": value["driver_definitions"],
            }
        )
        self.assertNotIn(value["run_id"], definition_bytes)
        self.assertNotIn(value["content_identity_sha256"][:12], definition_bytes)
        self.assertNotIn("gateway_port", canonical_json(identity))
        self.assertNotIn("container_name", canonical_json(identity))
        self.assertNotIn("run_id", canonical_json(identity))
        self.assertEqual(len(value["containers"]), 12)
        self.assertEqual(len(value["networks"]), 6)
        self.assertEqual(
            {(item["track"], item["role"]) for item in value["containers"]},
            {(track.value, role) for track in LiveTrack for role in (
                "authz", "target", "envoy", "driver"
            )},
        )
        self.assertEqual(
            {(item["track"], item["segment"]) for item in value["networks"]},
            {(track.value, segment) for track in LiveTrack for segment in (
                "frontend", "backend"
            )},
        )
        different = create_run_manifest(
            PROFILE,
            profile_sha256=HEX_A,
            python_image_digest=PYTHON_DIGEST,
            envoy_image_digest=ENVOY_DIGEST,
            kil_image_id=KIL_IMAGE_ID,
            kil_archive_sha256=HEX_A,
            driver_bootstrap_sha256=HEX_A,
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
                driver_bootstrap_sha256=HEX_A,
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
                driver_bootstrap_sha256=HEX_A,
                docker_host="unix:///socket",
            )

    def test_runtime_names_labels_and_full_ids_do_not_change_content_digest(self):
        value = manifest()
        digest = value["content_identity_sha256"]
        coherently_regenerated = json.loads(json.dumps(value))
        projection = local_envoy_module._manifest_runtime_projection(
            identity_sha256=digest,
            kil_image_id=value["kil_image_id"],
            envoy_image_digest=value["envoy_image_digest"],
            driver_definition_sha256=(
                value["content_identity"]["driver_definition_sha256"]
            ),
        )
        coherently_regenerated["tracks"] = projection["tracks"]
        coherently_regenerated["containers"] = projection["containers"]
        coherently_regenerated["networks"] = projection["networks"]
        local_envoy_module._validate_manifest(coherently_regenerated)
        external_attestation = {
            "container_full_ids": ["9" * 64],
            "labels": {"kil.v3b1.runtime": "changed"},
        }

        self.assertEqual(
            digest,
            sha256(
                canonical_json(coherently_regenerated["content_identity"]).encode(
                    "utf-8"
                )
            ).hexdigest(),
        )
        self.assertNotIn("runtime_attestations", coherently_regenerated)
        self.assertNotIn(
            "9" * 64, canonical_json(coherently_regenerated["content_identity"])
        )
        self.assertEqual(external_attestation["container_full_ids"], ["9" * 64])

        incoherent = json.loads(json.dumps(value))
        incoherent["containers"][0]["name"] = "kil-v3b1-authz-runtime-only"
        with self.assertRaises(ControllerError):
            local_envoy_module._validate_manifest(incoherent)

    def test_manifest_runtime_projection_rejects_detached_or_mismatched_bindings(self):
        value = manifest()
        cases = {}

        detached_authz = json.loads(json.dumps(value))
        detached_authz["tracks"][0]["authz_container"] = (
            detached_authz["tracks"][1]["authz_container"]
        )
        cases["detached-authz"] = detached_authz

        wrong_image = json.loads(json.dumps(value))
        next(
            item for item in wrong_image["containers"]
            if item["role"] == "authz"
        )["image"] = ENVOY_DIGEST
        cases["role-image"] = wrong_image

        wrong_envoy_image = json.loads(json.dumps(value))
        next(
            item for item in wrong_envoy_image["containers"]
            if item["role"] == "envoy"
        )["image"] = value["kil_image_id"]
        cases["envoy-image"] = wrong_envoy_image

        wrong_driver_image = json.loads(json.dumps(value))
        next(
            item for item in wrong_driver_image["containers"]
            if item["role"] == "driver"
        )["image"] = ENVOY_DIGEST
        cases["driver-image"] = wrong_driver_image

        wrong_path = json.loads(json.dumps(value))
        wrong_path["tracks"][0]["decision_source"] = "detached/decisions.jsonl"
        cases["source-path"] = wrong_path

        wrong_target_path = json.loads(json.dumps(value))
        wrong_target_path["tracks"][0]["target_source"] = (
            "detached/target-markers.jsonl"
        )
        cases["target-source-path"] = wrong_target_path

        wrong_envoy_path = json.loads(json.dumps(value))
        wrong_envoy_path["tracks"][0]["envoy_source"] = (
            "detached/envoy-access.jsonl"
        )
        cases["envoy-source-path"] = wrong_envoy_path

        wrong_driver_reference = json.loads(json.dumps(value))
        wrong_driver_reference["tracks"][0]["driver_definition_sha256"] = HEX_A
        cases["driver-definition-reference"] = wrong_driver_reference

        wrong_container_reference = json.loads(json.dumps(value))
        next(
            item for item in wrong_container_reference["containers"]
            if item["role"] == "driver"
        )["command_definition_sha256"] = HEX_A
        cases["driver-command-reference"] = wrong_container_reference

        wrong_suffix = json.loads(json.dumps(value))
        wrong_suffix["containers"][0]["name"] = (
            wrong_suffix["containers"][0]["name"][:-12] + "f" * 12
        )
        cases["name-suffix"] = wrong_suffix

        wrong_network_suffix = json.loads(json.dumps(value))
        wrong_network_suffix["networks"][0]["name"] = (
            wrong_network_suffix["networks"][0]["name"][:-12] + "f" * 12
        )
        cases["network-name-suffix"] = wrong_network_suffix

        detached_network = json.loads(json.dumps(value))
        detached_network["tracks"][0]["frontend_network"] = (
            detached_network["tracks"][1]["frontend_network"]
        )
        cases["detached-frontend-network"] = detached_network

        duplicate_container = json.loads(json.dumps(value))
        duplicate_container["containers"][1] = dict(
            duplicate_container["containers"][0]
        )
        cases["duplicate-container"] = duplicate_container

        duplicate_network = json.loads(json.dumps(value))
        duplicate_network["networks"][1] = dict(duplicate_network["networks"][0])
        cases["duplicate-network"] = duplicate_network

        missing_container = json.loads(json.dumps(value))
        missing_container["containers"].pop()
        cases["missing-container"] = missing_container

        extra_container = json.loads(json.dumps(value))
        extra_container["containers"].append(dict(extra_container["containers"][0]))
        cases["extra-container"] = extra_container

        missing_network = json.loads(json.dumps(value))
        missing_network["networks"].pop()
        cases["missing-network"] = missing_network

        extra_network = json.loads(json.dumps(value))
        extra_network["networks"].append(dict(extra_network["networks"][0]))
        cases["extra-network"] = extra_network

        for label, changed in cases.items():
            with self.subTest(label=label), self.assertRaises(ControllerError):
                local_envoy_module._validate_manifest(changed)

    def test_private_manifest_dispatch_rejects_hybrid_schema_shapes(self):
        value = manifest()
        for missing in ("segment_definitions", "driver_definitions"):
            with self.subTest(missing=missing):
                changed = json.loads(json.dumps(value))
                del changed[missing]
                with self.assertRaisesRegex(ControllerError, "closed"):
                    local_envoy_module._validate_manifest(changed)

        for missing in (
            "driver_endpoint",
            "segment_definitions",
            "driver_definition_sha256",
        ):
            with self.subTest(identity_missing=missing):
                changed = json.loads(json.dumps(value))
                del changed["content_identity"][missing]
                with self.assertRaises(ControllerError):
                    local_envoy_module._validate_manifest(changed)

        legacy_tagged = json.loads(json.dumps(value))
        legacy_tagged["schema_version"] = "kil.v3b1-manifest.v1"
        with self.assertRaises(ControllerError):
            local_envoy_module._validate_manifest(legacy_tagged)

    def test_public_v1_dispatch_rejects_driver_identity_fields(self):
        fixture_root = ROOT / "tests/fixtures/v3b1-public-bundle-v1"
        bundle = next(path for path in fixture_root.iterdir() if path.is_dir())
        public = json.loads((bundle / "manifest.json").read_text())
        payloads = {
            path.relative_to(bundle).as_posix(): path.read_bytes()
            for path in bundle.rglob("*")
            if path.is_file()
        }
        public["content_identity"]["segment_definitions"] = []

        with self.assertRaises(ControllerError):
            local_envoy_module._validate_public_manifest(public, payloads)

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

    def test_runtime_is_six_internal_segments_with_nine_services_and_three_stopped_drivers(self):
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
            self.assertEqual(len(network_commands), 6)
            self.assertTrue(all("--internal" in command for command in network_commands))
            self.assertTrue(all("bridge" in command for command in network_commands))
            self.assertEqual(
                [command[-1] for command in network_commands],
                [
                    item["name"]
                    for segment in ("backend", "frontend")
                    for item in value["networks"]
                    if item["segment"] == segment
                ],
            )
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
            managed_container_commands = [
                command
                for command in commands
                if any(
                    part.startswith("kil.v3b1.role=") for part in command
                )
            ]
            self.assertEqual(len(managed_container_commands), 15)
            self.assertTrue(
                all(
                    "--cgroupns=private" in command
                    for command in managed_container_commands
                )
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
                self.assertEqual(
                    command[command.index("--entrypoint") + 1], "python"
                )
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
            self.assertEqual(len(gateways), 3)
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
                    {track["backend_network"]},
                )

            drivers = [command for command in commands if "create" in command]
            drivers = [
                command
                for command in drivers
                if "kil.v3b1.role=driver" in command
            ]
            self.assertEqual(len(drivers), 3)
            for command in drivers:
                name = command[command.index("--name") + 1]
                track = next(
                    item for item in value["tracks"]
                    if item["driver_container"] == name
                )
                self.assertIn("--interactive", command)
                self.assertNotIn("--tty", command)
                self.assertIn("--no-healthcheck", command)
                self.assertNotIn("--mount", command)
                self.assertNotIn("--publish", command)
                self.assertNotIn("-p", command)
                self.assertEqual(
                    command[command.index("--network") + 1],
                    track["frontend_network"],
                )
                self.assertNotIn(track["backend_network"], command)
                self.assertEqual(
                    command[command.index("--entrypoint") + 1], "python"
                )
                self.assertEqual(
                    command[-7:],
                    [
                        KIL_IMAGE_ID,
                        "-m",
                        "kil.v3b1_request_driver",
                        "--track",
                        track["track"],
                        "--endpoint",
                        "envoy:8080",
                    ],
                )

            forbidden_parts = {"--publish", "-p", "18080", "18081", "18082"}
            for command in commands:
                self.assertTrue(forbidden_parts.isdisjoint(command))
                self.assertFalse(
                    any("127.0.0.1:18" in part for part in command),
                    command,
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
            self.assertEqual(
                loaded["schema_version"], "kil.v3b1-active-state.v2"
            )

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
            validator_objects = [
                {
                    "id": character * 64,
                    "name": (
                        f"kil-v3b1-validate-{track.value.replace('_', '-')}-"
                        f"{str(value['content_identity_sha256'])[:12]}"
                    ),
                    "role": "validator",
                    "track": track.value,
                    "labels": {
                        "kil.v3b1.managed": "true",
                        "kil.v3b1.run-id": value["run_id"],
                        "kil.v3b1.role": "validator",
                        "kil.v3b1.track": track.value,
                    },
                    "image_id": value["envoy_image_id"],
                    "image_reference": value["envoy_image_digest"],
                    "runtime_attestation": {
                        "privileged": False,
                        "network_mode": "none",
                        "pid_mode": "",
                        "ipc_mode": "",
                        "uts_mode": "",
                        "userns_mode": "",
                        "cgroupns_mode": "private",
                        "state": "exited",
                        "entrypoint": ["/usr/local/bin/envoy"],
                        "command": [
                            "--mode",
                            "validate",
                            "--config-path",
                            "/etc/envoy/envoy.json",
                            "--disable-hot-restart",
                            "--concurrency",
                            "1",
                        ],
                        "mounts": [
                            {
                                "source": f"/private/{track.value}/envoy.json",
                                "destination": "/etc/envoy/envoy.json",
                                "rw": False,
                            }
                        ],
                        "networks": {},
                        "port_bindings": {},
                        "published_ports": None,
                    },
                }
                for track, character in zip(
                    LiveTrack, ("d", "e", "f"), strict=True
                )
            ]
            driver_authorities = {
                item["track"]: {
                    **local_envoy_module._driver_recovery_authority(
                        [], str(item["track"]), str(item["id"])
                    ),
                    "driver_id": item["id"],
                    "track": item["track"],
                    "observed_state": "created",
                }
                for item in state["objects"]
                if item["role"] == "driver"
            }

            commands = teardown_commands(
                state,
                validator_objects=validator_objects,
                driver_authorities=driver_authorities,
                docker_binary=Path("/locked/docker"),
            )

            removed = [command[-1] for command in commands if "rm" in command and "network" not in command]
            expected_order = [
                item["id"]
                for role in ("driver", "envoy", "authz", "target")
                for item in state["objects"]
                if item["role"] == role
            ] + [item["id"] for item in validator_objects]
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
            driver_ids = {
                item["id"]
                for item in state["objects"]
                if item["role"] == "driver"
            }
            self.assertFalse(
                any(
                    command[-1] in driver_ids and "stop" in command
                    for command in commands
                )
            )
            network_removes = [command for command in commands if "network" in command and "rm" in command]
            self.assertEqual(len(network_removes), 6)
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
                teardown_commands(
                    unowned,
                    validator_objects=validator_objects,
                    driver_authorities=driver_authorities,
                    docker_binary=Path("/locked/docker"),
                )

            forged_validators = json.loads(json.dumps(validator_objects))
            forged_validators[0]["name"] = validator_objects[1]["name"]
            with self.assertRaisesRegex(
                ControllerError, "validator|identity|teardown"
            ):
                teardown_commands(
                    state,
                    validator_objects=forged_validators,
                    driver_authorities=driver_authorities,
                    docker_binary=Path("/locked/docker"),
                )

            ambiguous_authorities = json.loads(json.dumps(driver_authorities))
            selected_track = LiveTrack.CREDENTIAL_POLICY_BASELINE.value
            ambiguous_authorities[selected_track].update(
                {
                    "phase": "ambiguous",
                    "allowed_states": ["created", "dead", "exited", "running"],
                    "request_eligible": False,
                    "terminal_source": None,
                    "observed_state": "created",
                }
            )
            with self.assertRaisesRegex(ControllerError, "driver|phase|quies"):
                teardown_commands(
                    state,
                    validator_objects=validator_objects,
                    driver_authorities=ambiguous_authorities,
                    docker_binary=Path("/locked/docker"),
                )

    def test_driver_attestation_comparison_is_phase_scoped_not_globally_relaxed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            state_path = root / "active.json"
            value = manifest(docker_host="unix:///tmp/kil.sock")
            manifest_path.write_text(canonical_json(value) + "\n")
            persist_active_state(state_path, manifest_path, value)
            state = load_bound_active_state(state_path)
            recorded = next(
                item for item in state["objects"] if item["role"] == "driver"
            )
            self.assertFalse(
                local_envoy_module._container_attestation_matches(
                    recorded,
                    recorded,
                    allow_stopped=True,
                    allowed_driver_states={"exited"},
                )
            )

            for observed_state in ("running", "exited", "dead"):
                current = json.loads(json.dumps(recorded))
                current["runtime_attestation"]["state"] = observed_state
                self.assertFalse(
                    local_envoy_module._container_attestation_matches(
                        recorded, current, allow_stopped=True
                    )
                )
                self.assertTrue(
                    local_envoy_module._container_attestation_matches(
                        recorded,
                        current,
                        allow_stopped=True,
                        allowed_driver_states={observed_state},
                    )
                )
                self.assertFalse(
                    local_envoy_module._container_attestation_matches(
                        recorded,
                        current,
                        allow_stopped=True,
                        allowed_driver_states={"created"},
                    )
                )

            mutations = (
                ("full_id", lambda value: value.__setitem__("id", HEX_A)),
                ("name", lambda value: value.__setitem__("name", "replacement")),
                (
                    "image_reference",
                    lambda value: value.__setitem__(
                        "image_reference", f"sha256:{HEX_A}"
                    ),
                ),
                (
                    "command",
                    lambda value: value["runtime_attestation"].__setitem__(
                        "command", ["unexpected"]
                    ),
                ),
                (
                    "labels",
                    lambda value: value.__setitem__("labels", {}),
                ),
                (
                    "hardening",
                    lambda value: value["runtime_attestation"].__setitem__(
                        "privileged", True
                    ),
                ),
                (
                    "stdin",
                    lambda value: value["runtime_attestation"].__setitem__(
                        "stdin_open", False
                    ),
                ),
                (
                    "network_aliases",
                    lambda value: value["runtime_attestation"].__setitem__(
                        "network_aliases", {}
                    ),
                ),
                (
                    "ports",
                    lambda value: value["runtime_attestation"].__setitem__(
                        "port_bindings", {"80/tcp": [{"HostPort": "80"}]}
                    ),
                ),
                (
                    "mounts",
                    lambda value: value["runtime_attestation"].__setitem__(
                        "mounts", [{"source": "/tmp", "destination": "/mnt"}]
                    ),
                ),
                (
                    "environment",
                    lambda value: value["runtime_attestation"].__setitem__(
                        "environment", ["PATH=/unexpected"]
                    ),
                ),
            )
            for label, mutate in mutations:
                with self.subTest(mutation=label):
                    current = json.loads(json.dumps(recorded))
                    current["runtime_attestation"]["state"] = "exited"
                    mutate(current)
                    self.assertFalse(
                        local_envoy_module._container_attestation_matches(
                            recorded,
                            current,
                            allow_stopped=True,
                            allowed_driver_states={"exited"},
                        )
                    )

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


class _DriverInput(io.BytesIO):
    def __init__(self, owner, events):
        super().__init__()
        self.owner = owner
        self.events = events

    def write(self, payload):
        self.events.append(("stdin_write", self.owner.full_id, bytes(payload)))
        self.owner.clock.advance(self.owner.advance_write_ns)
        if self.owner.write_error is not None:
            raise self.owner.write_error
        if self.owner.partial_write is not None:
            count = min(self.owner.partial_write, len(payload))
            super().write(payload[:count])
            return count
        return super().write(payload)

    def close(self):
        if not self.closed:
            self.events.append(("stdin_close", self.owner.full_id))
        if self.owner.stdin_close_error:
            self.owner.stdin_close_error = False
            raise OSError("private stdin close failure")
        super().close()


class _DriverOutput(io.BytesIO):
    def __init__(self, owner, payload, events, factory, clock, advance_ns):
        super().__init__(payload)
        self.owner = owner
        self.events = events
        self.factory = factory
        self.clock = clock
        self.advance_ns = advance_ns

    def readline(self, size=-1):
        self.events.append(("stdout_readline", self.owner.full_id, size))
        if len(self.factory.processes) != 3:
            raise AssertionError("readiness was consumed before all drivers started")
        self.clock.advance(self.advance_ns)
        return super().readline(size)

    def read(self, size=-1):
        self.events.append(("stdout_read", self.owner.full_id, size))
        return super().read(size)

    def close(self):
        if self.owner.stdout_close_error:
            self.owner.stdout_close_error = False
            raise OSError("private close failure")
        super().close()


class _BlockingDriverOutput(_DriverOutput):
    def __init__(self, owner, payload, events, factory, clock, advance_ns):
        super().__init__(owner, payload, events, factory, clock, advance_ns)
        self.release = threading.Event()
        self.read_started = threading.Event()

    def fileno(self):
        raise io.UnsupportedOperation("no descriptor")

    def readline(self, size=-1):
        self.events.append(("stdout_readline_blocking", self.owner.full_id, size))
        if len(self.factory.processes) != 3:
            raise AssertionError("readiness was consumed before all drivers started")
        self.read_started.set()
        self.clock.advance(self.advance_ns)
        self.release.wait()
        if self.closed:
            return b""
        return super().readline(size)

    def close(self):
        self.release.set()
        super().close()


class _DriverProcess:
    def __init__(
        self,
        *,
        full_id,
        payload,
        events,
        factory,
        clock,
        advance_ns=0,
        returncode=0,
        stderr=b"",
        wait_error=None,
        blocking_stdout=False,
        terminate_exits=True,
        stdout_close_error=False,
        write_error=None,
        partial_write=None,
        poll_result=None,
        advance_write_ns=0,
        stdin_close_error=False,
    ):
        self.full_id = full_id
        self.events = events
        self.returncode = returncode
        self.wait_error = wait_error
        self.terminate_exits = terminate_exits
        self.stdout_close_error = stdout_close_error
        self.write_error = write_error
        self.partial_write = partial_write
        self.poll_result = poll_result
        self.advance_write_ns = advance_write_ns
        self.stdin_close_error = stdin_close_error
        self.clock = clock
        self.exited = False
        self.terminated = False
        self.killed = False
        self.reaped = False
        self.stdin = _DriverInput(self, events)
        output_type = _BlockingDriverOutput if blocking_stdout else _DriverOutput
        self.stdout = output_type(
            self, payload, events, factory, clock, advance_ns
        )
        self.stderr = io.BytesIO(stderr)

    def poll(self):
        if not self.exited:
            return None
        return self.returncode if self.poll_result is None else self.poll_result

    def wait(self, timeout):
        self.events.append(("wait", self.full_id, timeout))
        if self.exited:
            self.reaped = True
            return self.returncode
        if self.wait_error is not None:
            raise self.wait_error
        self.exited = True
        self.reaped = True
        return self.returncode

    def terminate(self):
        self.events.append(("terminate", self.full_id))
        self.terminated = True
        if self.terminate_exits:
            self.exited = True
            if isinstance(self.stdout, _BlockingDriverOutput):
                self.stdout.release.set()

    def kill(self):
        self.events.append(("kill", self.full_id))
        self.killed = True
        self.exited = True
        if isinstance(self.stdout, _BlockingDriverOutput):
            self.stdout.release.set()


class _DriverProcessFactory:
    def __init__(self, behaviors, *, events, clock):
        self.behaviors = dict(behaviors)
        self.events = events
        self.clock = clock
        self.processes = []
        self.all_started = threading.Event()

    def start(self, command):
        argv = list(command)
        full_id = argv[-1]
        self.events.append(("start", argv))
        behavior = dict(self.behaviors[full_id])
        behavior.pop("container_running", None)
        start_error = behavior.pop("start_error", None)
        if start_error is not None:
            raise start_error
        process = _DriverProcess(
            full_id=full_id,
            events=self.events,
            factory=self,
            clock=self.clock,
            **behavior,
        )
        self.processes.append(process)
        if len(self.processes) == len(self.behaviors):
            self.all_started.set()
        return process


class DriverReadinessTest(unittest.TestCase):
    def make_controller(self, directory, behavior_changes=None):
        root = Path(directory) / "repo"
        profile_path = root / "deploy/kind/v3b-profile.json"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_bytes((ROOT / "deploy/kind/v3b-profile.json").read_bytes())
        events = []
        clock = _RunClock()
        value = manifest(docker_host=f"unix://{Path(directory)}/docker.sock")

        class ReadinessOnlyController(LocalEnvoyController):
            def _load_and_reverify(self):
                return self.bound_state, self.bound_manifest

        controller = ReadinessOnlyController(
            root,
            FakeRunner(),
            home=Path(directory) / "home",
            port_probe=lambda port: False,
            tool_verifier=lambda: TOOL_IDENTITIES,
            monotonic_ns=clock.monotonic_ns,
        )
        controller._prepare_private_roots()
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
        persist_active_state(controller.state_path, private_manifest, value)
        controller.bound_state = load_bound_active_state(controller.state_path)
        controller.bound_manifest = value
        drivers = {
            item["track"]: item
            for item in controller.bound_state["objects"]
            if item["role"] == "driver"
        }
        changes = behavior_changes or {}
        behaviors = {}
        for track in LiveTrack:
            record = {
                "schema_version": "kil.v3b1-driver-readiness.v1",
                "track": track.value,
                "status": "ready",
                "connect_monotonic_ns": 10,
                "ready_monotonic_ns": 20,
            }
            behavior = {"payload": (canonical_json(record) + "\n").encode()}
            behavior.update(changes.get(track.value, {}))
            behaviors[drivers[track.value]["id"]] = behavior
        factory = _DriverProcessFactory(behaviors, events=events, clock=clock)
        controller.driver_process_factory = factory
        controller.runner = _DriverStateRunner(
            {
                full_id: behavior.get("container_running", False)
                for full_id, behavior in behaviors.items()
            }
        )
        return controller, factory, clock, drivers, events

    def test_constructor_injects_driver_factory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            profile_path = root / "deploy/kind/v3b-profile.json"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )
            factory = object()

            controller = LocalEnvoyController(
                root,
                FakeRunner(),
                home=Path(directory) / "home",
                port_probe=lambda port: False,
                tool_verifier=lambda: TOOL_IDENTITIES,
                driver_process_factory=factory,
            )

            self.assertIs(controller.driver_process_factory, factory)

    def test_subprocess_factory_uses_binary_pipes_without_shell(self):
        fake_process = mock.Mock(
            stdin=io.BytesIO(), stdout=io.BytesIO(), stderr=io.BytesIO()
        )
        factory = SubprocessDriverProcessFactory(
            cwd=ROOT,
            env={"PATH": "/locked"},
        )
        command = ["/locked/docker", "start", "--attach", "--interactive", HEX_A]

        with mock.patch(
            "tools.v3b1_driver_transport.subprocess.Popen",
            return_value=fake_process,
        ) as popen:
            self.assertIs(factory.start(command), fake_process)

        popen.assert_called_once_with(
            command,
            cwd=ROOT,
            env={"PATH": "/locked"},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            text=False,
            shell=False,
        )

    def test_factory_is_injected_and_exact_attached_commands_start_before_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, drivers, events = self.make_controller(directory)

            controller.readiness()

            expected = [
                [
                    str(controller.docker_binary),
                    "start",
                    "--attach",
                    "--interactive",
                    drivers[track.value]["id"],
                ]
                for track in LiveTrack
            ]
            self.assertEqual(
                [event[1] for event in events if event[0] == "start"], expected
            )
            first_read = next(
                index for index, event in enumerate(events)
                if event[0] == "stdout_readline"
            )
            self.assertEqual(
                [event[0] for event in events[:first_read]].count("start"), 3
            )
            self.assertIs(controller.driver_process_factory, factory)

    def test_readiness_only_closes_all_inputs_before_wait_and_records_closed_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, drivers, events = self.make_controller(directory)

            result = controller.readiness()

            first_wait = next(index for index, event in enumerate(events) if event[0] == "wait")
            self.assertEqual(
                [event[0] for event in events[:first_wait]].count("stdin_close"), 3
            )
            self.assertTrue(all(process.stdin.closed for process in factory.processes))
            self.assertTrue(all(process.exited for process in factory.processes))
            self.assertEqual(result["status"], "diagnostic_only")
            journal = load_lifecycle_journal(controller.journal_path)
            self.assertEqual(
                {record["status"] for record in journal["requests"].values()},
                {"not_attempted"},
            )
            starts = [
                event for event in journal["events"]
                if event["event"] in {"driver_start_intent", "driver_start_complete"}
            ]
            ready = [
                event for event in journal["events"]
                if event["event"] == "driver_readiness_complete"
            ]
            cancels = [
                event for event in journal["events"]
                if event["event"] == "readiness_cancel_complete"
            ]
            self.assertEqual(len(starts), 6)
            self.assertEqual(len(ready), 3)
            self.assertEqual(len(cancels), 3)
            nonce = result["readiness_nonce"]
            for event in [*starts, *ready, *cancels]:
                details = event["details"]
                self.assertEqual(details["readiness_nonce"], nonce)
                self.assertEqual(details["driver_id"], drivers[details["track"]]["id"])
            self.assertTrue(
                any(
                    event["event"] == "readiness_diagnostic_complete"
                    and event["details"] == {
                        "readiness_nonce": nonce,
                        "lifecycle_mode": "diagnostic_only",
                    }
                    for event in journal["events"]
                )
            )
            with self.assertRaisesRegex(ControllerError, "diagnostic|down"):
                controller.run()
            with self.assertRaisesRegex(ControllerError, "diagnostic|down"):
                journal_event(
                    controller.journal_path,
                    "readiness_session_started",
                    {"readiness_nonce": HEX_C},
                )

    def test_one_common_deadline_bounds_all_reads_and_cancellation_waits(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, _, _, _, events = self.make_controller(
                directory,
                {
                    "credential_policy_baseline": {"advance_ns": 4_000_000_000},
                    "signed_state_only": {"advance_ns": 5_000_000_000},
                    "signed_plus_local_reduce": {"advance_ns": 6_000_000_000},
                },
            )

            controller.readiness()

            waits = [event[2] for event in events if event[0] == "wait"]
            self.assertEqual(len(waits), 3)
            self.assertTrue(all(0 < timeout <= 15.0 for timeout in waits))
            self.assertEqual(waits, sorted(waits, reverse=True))

    def test_malformed_extra_wrong_track_nonzero_stderr_and_ambiguous_exit_poison(self):
        wrong = {
            "schema_version": "kil.v3b1-driver-readiness.v1",
            "track": "signed_state_only",
            "status": "ready",
            "connect_monotonic_ns": 1,
            "ready_monotonic_ns": 2,
        }
        cases = {
            "malformed": {"payload": b"not-json\n"},
            "deadline": {"advance_ns": 31_000_000_000},
            "extra": {
                "payload": (
                    b'{"connect_monotonic_ns":1,"ready_monotonic_ns":2,'
                    b'"schema_version":"kil.v3b1-driver-readiness.v1",'
                    b'"status":"ready","track":"credential_policy_baseline"}\n'
                    b"{}\n"
                )
            },
            "wrong_track": {"payload": (canonical_json(wrong) + "\n").encode()},
            "nonzero": {"returncode": 7},
            "stderr": {"stderr": b"private process diagnostic"},
            "ambiguous": {"wait_error": subprocess.TimeoutExpired("docker", 1)},
        }
        for name, change in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                controller, factory, _, _, events = self.make_controller(
                    directory, {"credential_policy_baseline": change}
                )

                with self.assertRaises((ControllerError, DriverTransportError)):
                    controller.readiness()

                journal = load_lifecycle_journal(controller.journal_path)
                self.assertEqual(
                    {record["status"] for record in journal["requests"].values()},
                    {"not_attempted"},
                )
                self.assertTrue(controller.readiness_poison_path.is_file())
                raw = controller.journal_path.read_text()
                self.assertNotIn("private process diagnostic", raw)
                self.assertNotIn("not-json", raw)
                self.assertFalse(any(event[0] == "request" for event in events))
                self.assertEqual(len(factory.processes), 3)
                self.assertTrue(all(process.exited for process in factory.processes))
                self.assertTrue(all(process.reaped for process in factory.processes))
                self.assertTrue(all(process.stdin.closed for process in factory.processes))
                self.assertTrue(all(process.stdout.closed for process in factory.processes))
                self.assertTrue(all(process.stderr.closed for process in factory.processes))
                cancel_completes = [
                    item["details"]["driver_id"]
                    for item in journal["events"]
                    if item["event"] == "readiness_cancel_complete"
                ]
                self.assertEqual(len(cancel_completes), len(set(cancel_completes)))
                if name in {"extra", "nonzero", "stderr", "ambiguous"}:
                    failed_id = next(
                        item["details"]["driver_id"]
                        for item in journal["events"]
                        if item["event"] == "driver_readiness_failed"
                    )
                    self.assertFalse(
                        any(
                            item["event"] == "readiness_cancel_complete"
                            and item["details"]["driver_id"] == failed_id
                            for item in journal["events"]
                        )
                    )

    def test_only_exact_ready_schema_can_complete_readiness(self):
        success = {
            "attempt_count": 1,
            "connect_monotonic_ns": 1,
            "decision_digest": HEX_A,
            "receive_monotonic_ns": 3,
            "response_status": 200,
            "retry_performed": False,
            "schema_version": "kil.v3b1-driver-result.v1",
            "send_monotonic_ns": 2,
            "status": "complete",
            "track": LiveTrack.CREDENTIAL_POLICY_BASELINE.value,
        }
        transport_failure = {
            "attempt_count": 1,
            "connect_monotonic_ns": 1,
            "errno": 111,
            "errno_name": "ECONNREFUSED",
            "exception_class": "ConnectionRefusedError",
            "failure_monotonic_ns": 3,
            "request_bytes_may_have_been_sent": False,
            "retry_performed": False,
            "schema_version": "kil.v3b1-driver-result.v1",
            "send_monotonic_ns": 2,
            "stage": "request_send",
            "status": "transport_failure",
            "track": LiveTrack.CREDENTIAL_POLICY_BASELINE.value,
        }
        control_failure = {
            "attempt_count": 1,
            "failure_monotonic_ns": 3,
            "request_bytes_may_have_been_sent": False,
            "retry_performed": False,
            "schema_version": "kil.v3b1-driver-result.v1",
            "stage": "instruction_write",
            "status": "driver_control_failure",
            "track": LiveTrack.CREDENTIAL_POLICY_BASELINE.value,
        }
        readiness_extra = {
            "connect_monotonic_ns": 1,
            "ready_monotonic_ns": 2,
            "schema_version": "kil.v3b1-driver-readiness.v1",
            "status": "ready",
            "track": LiveTrack.CREDENTIAL_POLICY_BASELINE.value,
            "unexpected": False,
        }
        cases = {
            "success": (canonical_json(success) + "\n").encode(),
            "transport_failure": (
                canonical_json(transport_failure) + "\n"
            ).encode(),
            "driver_control_failure": (
                canonical_json(control_failure) + "\n"
            ).encode(),
            "malformed": b"not-json\n",
            "extra": (canonical_json(readiness_extra) + "\n").encode(),
        }
        for name, payload in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                controller, _, _, drivers, _ = self.make_controller(
                    directory,
                    {"credential_policy_baseline": {"payload": payload}},
                )

                with self.assertRaisesRegex(ControllerError, "failed closed"):
                    controller.readiness()

                journal = load_lifecycle_journal(controller.journal_path)
                failed_id = drivers[LiveTrack.CREDENTIAL_POLICY_BASELINE.value]["id"]
                self.assertFalse(
                    any(
                        item["event"] == "driver_readiness_complete"
                        and item["details"]["driver_id"] == failed_id
                        for item in journal["events"]
                    )
                )
                self.assertFalse(
                    any(
                        item["event"] == "readiness_diagnostic_complete"
                        for item in journal["events"]
                    )
                )

    def test_non_fileno_blocking_read_uses_common_deadline_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, _, _ = self.make_controller(
                directory,
                {
                    "credential_policy_baseline": {
                        "blocking_stdout": True,
                        "advance_ns": 31_000_000_000,
                    }
                },
            )
            result = []

            def invoke_readiness():
                try:
                    controller.readiness()
                except BaseException as error:
                    result.append(error)

            worker = threading.Thread(target=invoke_readiness, daemon=True)
            worker.start()
            self.assertTrue(factory.all_started.wait(5))
            blocking = next(
                process.stdout
                for process in factory.processes
                if isinstance(process.stdout, _BlockingDriverOutput)
            )
            self.assertTrue(blocking.read_started.wait(5))
            worker.join(5)
            completed_under_deadline = not worker.is_alive()
            if worker.is_alive():
                for process in factory.processes:
                    process.kill()
                    process.stdout.close()
                worker.join(5)

            self.assertTrue(completed_under_deadline)
            self.assertEqual(len(result), 1)
            self.assertIsInstance(result[0], ControllerError)
            self.assertTrue(all(process.exited for process in factory.processes))
            self.assertTrue(all(process.reaped for process in factory.processes))
            self.assertFalse(
                any(
                    thread.is_alive()
                    and thread.name.startswith("kil-v3b1-driver-read-")
                    for thread in threading.enumerate()
                )
            )

    def test_failed_cancel_uses_exact_id_stop_then_terminate_kill_and_reap(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, drivers, _ = self.make_controller(
                directory,
                {
                    "credential_policy_baseline": {
                        "wait_error": subprocess.TimeoutExpired("docker", 1),
                        "terminate_exits": False,
                        "container_running": True,
                    }
                },
            )

            with self.assertRaisesRegex(ControllerError, "failed closed"):
                controller.readiness()

            failed = factory.processes[0]
            self.assertTrue(failed.terminated)
            self.assertTrue(failed.killed)
            self.assertTrue(failed.exited)
            self.assertTrue(failed.reaped)
            failed_id = drivers[LiveTrack.CREDENTIAL_POLICY_BASELINE.value]["id"]
            stop_commands = [
                call[0]
                for call in controller.runner.calls
                if "stop" in call[0]
            ]
            self.assertEqual(
                stop_commands,
                [controller.docker_command("stop", "--timeout", "1", failed_id)],
            )
            journal = load_lifecycle_journal(controller.journal_path)
            cleanup = next(
                item for item in journal["events"]
                if item["event"] == "driver_cleanup_complete"
            )
            self.assertEqual(
                cleanup["details"],
                {
                    "readiness_nonce": cleanup["details"]["readiness_nonce"],
                    "track": LiveTrack.CREDENTIAL_POLICY_BASELINE.value,
                    "driver_id": failed_id,
                    "outcome": "killed",
                    "exit_code": 0,
                },
            )
            self.assertFalse(
                any(
                    item["event"] == "readiness_cancel_complete"
                    and item["details"]["driver_id"] == failed_id
                    for item in journal["events"]
                )
            )
            with self.assertRaisesRegex(ControllerError, "poison|down"):
                controller.readiness()

    def test_cleanup_failure_is_closed_explicit_and_process_is_still_reaped(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, drivers, _ = self.make_controller(
                directory,
                {
                    "credential_policy_baseline": {
                        "payload": b"not-json\n",
                        "stdout_close_error": True,
                    }
                },
            )

            with self.assertRaisesRegex(ControllerError, "failed closed"):
                controller.readiness()

            journal = load_lifecycle_journal(controller.journal_path)
            failed_id = drivers[LiveTrack.CREDENTIAL_POLICY_BASELINE.value]["id"]
            cleanup_failure = next(
                item for item in journal["events"]
                if item["event"] == "driver_cleanup_failed"
                and item["details"]["driver_id"] == failed_id
            )
            self.assertEqual(
                cleanup_failure["details"]["category"], "cleanup_pipe_close"
            )
            self.assertEqual(
                set(cleanup_failure["details"]),
                {"readiness_nonce", "track", "driver_id", "category"},
            )
            self.assertTrue(all(process.exited for process in factory.processes))
            self.assertTrue(all(process.reaped for process in factory.processes))
            raw = controller.journal_path.read_text()
            self.assertNotIn("private close failure", raw)

    def test_terminal_failure_write_cannot_prevent_independent_poison(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, _, _ = self.make_controller(
                directory,
                {"credential_policy_baseline": {"payload": b"not-json\n"}},
            )
            real_journal_event = local_envoy_module.journal_event
            failed_once = False

            def fail_terminal(path, event, details):
                nonlocal failed_once
                if not failed_once and event == "driver_readiness_failed":
                    failed_once = True
                    raise ControllerError("private terminal persistence failure")
                return real_journal_event(path, event, details)

            with mock.patch(
                "tools.v3b1_local_envoy.journal_event", side_effect=fail_terminal
            ):
                with self.assertRaisesRegex(ControllerError, "failed closed"):
                    controller.readiness()

            self.assertTrue(controller.readiness_poison_path.is_file())
            self.assertTrue(all(process.reaped for process in factory.processes))
            with self.assertRaisesRegex(ControllerError, "poison|down|incomplete"):
                controller.readiness()
            self.assertNotIn(
                "private terminal persistence failure",
                controller.journal_path.read_text(),
            )

    def test_cleanup_event_write_failure_still_reaps_and_preserves_primary(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, drivers, _ = self.make_controller(
                directory,
                {
                    "credential_policy_baseline": {
                        "advance_ns": 31_000_000_000,
                    }
                },
            )
            real_journal_event = local_envoy_module.journal_event
            failed_once = False

            def fail_cleanup_intent(path, event, details):
                nonlocal failed_once
                if (
                    not failed_once
                    and event == "driver_cleanup_intent"
                    and details["track"]
                    == LiveTrack.CREDENTIAL_POLICY_BASELINE.value
                ):
                    failed_once = True
                    raise ControllerError("private cleanup persistence failure")
                return real_journal_event(path, event, details)

            with mock.patch(
                "tools.v3b1_local_envoy.journal_event",
                side_effect=fail_cleanup_intent,
            ):
                with self.assertRaisesRegex(ControllerError, "failed closed"):
                    controller.readiness()

            self.assertTrue(all(process.exited for process in factory.processes))
            self.assertTrue(all(process.reaped for process in factory.processes))
            journal = load_lifecycle_journal(controller.journal_path)
            failure = next(
                item for item in journal["events"]
                if item["event"] == "driver_readiness_failed"
            )
            self.assertEqual(
                failure["details"]["driver_id"],
                drivers[LiveTrack.CREDENTIAL_POLICY_BASELINE.value]["id"],
            )
            self.assertEqual(failure["details"]["stage"], "readiness_record")
            self.assertEqual(failure["details"]["category"], "deadline_expired")
            self.assertTrue(controller.readiness_poison_path.is_file())

    def test_poison_write_failure_is_aggregated_without_losing_primary(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, _, _, drivers, _ = self.make_controller(
                directory,
                {"credential_policy_baseline": {"payload": b"not-json\n"}},
            )
            real_write = local_envoy_module._write_file

            def fail_poison(path, payload, mode):
                if Path(path) == controller.readiness_poison_path:
                    raise ControllerError("private poison persistence failure")
                return real_write(path, payload, mode)

            with mock.patch(
                "tools.v3b1_local_envoy._write_file", side_effect=fail_poison
            ):
                with self.assertRaisesRegex(ControllerError, "failed closed"):
                    controller.readiness()

            journal = load_lifecycle_journal(controller.journal_path)
            failure = next(
                item for item in journal["events"]
                if item["event"] == "driver_readiness_failed"
            )
            self.assertEqual(
                failure["details"]["driver_id"],
                drivers[LiveTrack.CREDENTIAL_POLICY_BASELINE.value]["id"],
            )
            self.assertEqual(failure["details"]["stage"], "readiness_record")
            with self.assertRaisesRegex(ControllerError, "poison|down|incomplete"):
                controller.readiness()

    def test_incomplete_prior_session_rejects_replay_without_poison_or_driver_event(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, _, _ = self.make_controller(directory)
            journal_event(
                controller.journal_path,
                "readiness_session_started",
                {"readiness_nonce": HEX_B},
            )

            with self.assertRaisesRegex(ControllerError, "incomplete|down|readiness"):
                controller.readiness()

            self.assertEqual(factory.processes, [])

    def test_aggregate_persistence_failure_uses_controller_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, _, _, _, _ = self.make_controller(directory)
            real_journal_event = local_envoy_module.journal_event
            failed_once = False

            def fail_readiness_set(path, event, details):
                nonlocal failed_once
                if not failed_once and event == "driver_readiness_set_complete":
                    failed_once = True
                    raise ControllerError("private aggregate persistence failure")
                return real_journal_event(path, event, details)

            with mock.patch(
                "tools.v3b1_local_envoy.journal_event",
                side_effect=fail_readiness_set,
            ):
                with self.assertRaisesRegex(ControllerError, "failed closed"):
                    controller.readiness()

            journal = load_lifecycle_journal(controller.journal_path)
            failure = next(
                item for item in journal["events"]
                if item["event"] == "driver_readiness_failed"
            )
            self.assertEqual(
                failure["details"],
                {
                    "readiness_nonce": failure["details"]["readiness_nonce"],
                    "scope": "controller",
                    "track": None,
                    "driver_id": None,
                    "category": "controller_persistence",
                    "stage": "readiness_set_complete",
                },
            )

    def test_container_state_not_client_poll_controls_exact_id_stop(self):
        cases = {
            "client_exited_container_running": {
                "change": {
                    "payload": b"not-json\n",
                    "container_running": True,
                },
                "expect_stop": True,
            },
            "client_running_container_stopped": {
                "change": {
                    "wait_error": subprocess.TimeoutExpired("docker", 1),
                    "terminate_exits": False,
                    "container_running": False,
                },
                "expect_stop": False,
            },
        }
        for name, case in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                controller, factory, _, drivers, _ = self.make_controller(
                    directory,
                    {"credential_policy_baseline": case["change"]},
                )

                with self.assertRaisesRegex(ControllerError, "failed closed"):
                    controller.readiness()

                failed_id = drivers[LiveTrack.CREDENTIAL_POLICY_BASELINE.value]["id"]
                stops = [
                    call[0]
                    for call in controller.runner.calls
                    if "stop" in call[0]
                ]
                self.assertEqual(bool(stops), case["expect_stop"])
                if stops:
                    self.assertEqual(stops[0][-1], failed_id)
                driver_ids = {item["id"] for item in drivers.values()}
                for call in controller.runner.calls:
                    if "inspect" in call[0] or "stop" in call[0]:
                        self.assertIn(call[0][-1], driver_ids)
                self.assertTrue(all(process.reaped for process in factory.processes))

    def test_ambiguous_container_state_is_sanitized_cleanup_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, drivers, _ = self.make_controller(
                directory,
                {
                    "credential_policy_baseline": {
                        "payload": b"not-json\n",
                        "container_running": "malformed",
                    }
                },
            )

            with self.assertRaisesRegex(ControllerError, "failed closed"):
                controller.readiness()

            failed_id = drivers[LiveTrack.CREDENTIAL_POLICY_BASELINE.value]["id"]
            journal = load_lifecycle_journal(controller.journal_path)
            cleanup_failure = next(
                item for item in journal["events"]
                if item["event"] == "driver_cleanup_failed"
                and item["details"]["driver_id"] == failed_id
            )
            self.assertEqual(
                cleanup_failure["details"]["category"], "container_inspect"
            )
            self.assertNotIn("ambiguous private state", controller.journal_path.read_text())
            self.assertTrue(all(process.reaped for process in factory.processes))

    def test_later_driver_start_failures_retain_exact_primary_attribution(self):
        for failed_track in (
            LiveTrack.SIGNED_STATE_ONLY,
            LiveTrack.SIGNED_PLUS_LOCAL_REDUCE,
        ):
            with self.subTest(track=failed_track.value), tempfile.TemporaryDirectory() as directory:
                controller, factory, _, drivers, _ = self.make_controller(
                    directory,
                    {
                        failed_track.value: {
                            "start_error": DriverTransportError("process_start")
                        }
                    },
                )

                with self.assertRaisesRegex(ControllerError, "failed closed"):
                    controller.readiness()

                journal = load_lifecycle_journal(controller.journal_path)
                failure = next(
                    item for item in journal["events"]
                    if item["event"] == "driver_readiness_failed"
                )
                self.assertEqual(
                    failure["details"],
                    {
                        "readiness_nonce": failure["details"]["readiness_nonce"],
                        "scope": "driver",
                        "track": failed_track.value,
                        "driver_id": drivers[failed_track.value]["id"],
                        "category": "process_start",
                        "stage": "process_start",
                    },
                )
                self.assertTrue(all(process.exited for process in factory.processes))
                self.assertTrue(all(process.reaped for process in factory.processes))

    def test_later_start_record_failures_retain_exact_primary_attribution(self):
        for failed_track in (
            LiveTrack.SIGNED_STATE_ONLY,
            LiveTrack.SIGNED_PLUS_LOCAL_REDUCE,
        ):
            for failed_event in ("driver_start_intent", "driver_start_complete"):
                with self.subTest(
                    track=failed_track.value, event=failed_event
                ), tempfile.TemporaryDirectory() as directory:
                    controller, factory, _, drivers, _ = self.make_controller(directory)
                    real_journal_event = local_envoy_module.journal_event
                    failed_once = False

                    def fail_target_record(path, event, details):
                        nonlocal failed_once
                        if (
                            not failed_once
                            and event == failed_event
                            and details["track"] == failed_track.value
                        ):
                            failed_once = True
                            raise ControllerError("injected durable start record failure")
                        return real_journal_event(path, event, details)

                    with mock.patch(
                        "tools.v3b1_local_envoy.journal_event",
                        side_effect=fail_target_record,
                    ):
                        with self.assertRaisesRegex(ControllerError, "failed closed"):
                            controller.readiness()

                    journal = load_lifecycle_journal(controller.journal_path)
                    failure = next(
                        item for item in journal["events"]
                        if item["event"] == "driver_readiness_failed"
                    )
                    self.assertEqual(
                        failure["details"]["track"], failed_track.value
                    )
                    self.assertEqual(
                        failure["details"]["driver_id"],
                        drivers[failed_track.value]["id"],
                    )
                    self.assertEqual(
                        failure["details"]["stage"],
                        failed_event.removeprefix("driver_"),
                    )
                    self.assertTrue(
                        all(process.exited for process in factory.processes)
                    )
                    self.assertTrue(
                        all(process.reaped for process in factory.processes)
                    )

    def test_diagnostic_post_session_oserrors_fail_closed_without_raw_text(self):
        baseline = LiveTrack.CREDENTIAL_POLICY_BASELINE.value
        for name in ("readiness_persistence", "deadline_creation"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                controller, factory, _, drivers, events = self.make_controller(directory)
                real_journal_event = local_envoy_module.journal_event
                failed_once = False

                def fail_readiness_persistence(path, event, details):
                    nonlocal failed_once
                    if (
                        name == "readiness_persistence"
                        and not failed_once
                        and event == "driver_readiness_complete"
                        and details.get("track") == baseline
                    ):
                        failed_once = True
                        raise OSError("PRIVATE diagnostic persistence failure")
                    return real_journal_event(path, event, details)

                with ExitStack() as stack:
                    stack.enter_context(
                        mock.patch(
                            "tools.v3b1_local_envoy.journal_event",
                            side_effect=fail_readiness_persistence,
                        )
                    )
                    if name == "deadline_creation":
                        stack.enter_context(
                            mock.patch.object(
                                controller,
                                "_monotonic_now",
                                side_effect=OSError(
                                    "PRIVATE diagnostic deadline failure"
                                ),
                            )
                        )
                    with self.assertRaisesRegex(ControllerError, "failed closed|down"):
                        controller.readiness()

                journal = load_lifecycle_journal(controller.journal_path)
                self.assertEqual(
                    {request["status"] for request in journal["requests"].values()},
                    {"not_attempted"},
                )
                self.assertTrue(controller.readiness_poison_path.is_file())
                failure = next(
                    event for event in journal["events"]
                    if event["event"] == "driver_readiness_failed"
                )["details"]
                if name == "readiness_persistence":
                    self.assertEqual(
                        failure,
                        {
                            "readiness_nonce": failure["readiness_nonce"],
                            "scope": "driver",
                            "track": baseline,
                            "driver_id": drivers[baseline]["id"],
                            "category": "controller_persistence",
                            "stage": "readiness_complete",
                        },
                    )
                else:
                    self.assertEqual(
                        failure,
                        {
                            "readiness_nonce": failure["readiness_nonce"],
                            "scope": "controller",
                            "track": None,
                            "driver_id": None,
                            "category": "clock_failure",
                            "stage": "readiness_deadline",
                        },
                    )
                self.assertTrue(all(process.stdin.closed for process in factory.processes))
                self.assertTrue(all(process.exited for process in factory.processes))
                self.assertTrue(all(process.reaped for process in factory.processes))
                raw = controller.journal_path.read_text()
                self.assertNotIn("PRIVATE diagnostic persistence failure", raw)
                self.assertNotIn("PRIVATE diagnostic deadline failure", raw)
                starts = len([event for event in events if event[0] == "start"])
                with self.assertRaisesRegex(ControllerError, "poison|incomplete|down"):
                    controller.readiness()
                self.assertEqual(
                    len([event for event in events if event[0] == "start"]), starts
                )

    def test_cli_exposes_readiness_subcommand(self):
        self.assertEqual(make_parser().parse_args(["readiness"]).command, "readiness")

    def test_driver_lifecycle_events_reject_extra_private_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, _, _, drivers, _ = self.make_controller(directory)
            track = LiveTrack.CREDENTIAL_POLICY_BASELINE.value

            with self.assertRaisesRegex(ControllerError, "fields.*closed"):
                journal_event(
                    controller.journal_path,
                    "driver_start_intent",
                    {
                        "readiness_nonce": HEX_B,
                        "track": track,
                        "driver_id": drivers[track]["id"],
                        "stderr": "private output",
                    },
                )
            with self.assertRaisesRegex(ControllerError, "fields.*closed"):
                journal_event(
                    controller.journal_path,
                    "driver_cleanup_failed",
                    {
                        "readiness_nonce": HEX_B,
                        "track": track,
                        "driver_id": drivers[track]["id"],
                        "category": "cleanup_wait",
                        "stderr": "private output",
                    },
                )


class DriverRequestSequencingTest(unittest.TestCase):
    @staticmethod
    def success_result(track):
        status = 403 if track is LiveTrack.SIGNED_PLUS_LOCAL_REDUCE else 200
        digest = {
            LiveTrack.CREDENTIAL_POLICY_BASELINE: "1" * 64,
            LiveTrack.SIGNED_STATE_ONLY: "2" * 64,
            LiveTrack.SIGNED_PLUS_LOCAL_REDUCE: "3" * 64,
        }[track]
        return {
            "attempt_count": 1,
            "connect_monotonic_ns": 10,
            "decision_digest": digest,
            "receive_monotonic_ns": 30,
            "response_status": status,
            "retry_performed": False,
            "schema_version": "kil.v3b1-driver-result.v1",
            "send_monotonic_ns": 20,
            "status": "complete",
            "track": track.value,
        }

    @staticmethod
    def transport_failure(
        track,
        *,
        errno_number=104,
        errno_name="ECONNRESET",
        request_bytes_may_have_been_sent=True,
    ):
        return {
            "attempt_count": 1,
            "connect_monotonic_ns": 10,
            "errno": errno_number,
            "errno_name": errno_name,
            "exception_class": "ConnectionResetError",
            "failure_monotonic_ns": 30,
            "request_bytes_may_have_been_sent": request_bytes_may_have_been_sent,
            "retry_performed": False,
            "schema_version": "kil.v3b1-driver-result.v1",
            "send_monotonic_ns": 20,
            "stage": "response_headers",
            "status": "transport_failure",
            "track": track.value,
        }

    def make_controller(
        self, directory, behavior_changes=None, *, real_collect=False
    ):
        root = Path(directory) / "repo"
        profile_path = root / "deploy/kind/v3b-profile.json"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_bytes((ROOT / "deploy/kind/v3b-profile.json").read_bytes())
        events = []
        clock = _RunClock()
        value = manifest(docker_host=f"unix://{Path(directory)}/docker.sock")

        class RunOnlyController(LocalEnvoyController):
            def _load_and_reverify(self):
                return self.bound_state, self.bound_manifest

            def collect(self):
                self.run_events.append(("collect",))
                return self.root / "collected"

        class CollectHandoffController(LocalEnvoyController):
            def _load_and_reverify(self):
                return self.bound_state, self.bound_manifest

            def _copy_sources(self, state, manifest_value, collection_epoch):
                return self.collect_sources

        controller_class = CollectHandoffController if real_collect else RunOnlyController
        controller = controller_class(
            root,
            FakeRunner(),
            home=Path(directory) / "home",
            port_probe=lambda port: False,
            tool_verifier=lambda: TOOL_IDENTITIES,
            monotonic_ns=clock.monotonic_ns,
        )
        controller._prepare_private_roots()
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
        persist_active_state(controller.state_path, private_manifest, value)
        controller.bound_state = load_bound_active_state(controller.state_path)
        controller.bound_manifest = value
        controller.run_events = events
        _, _, decisions, envoy, targets = JoinContractTest().all_records()
        controller.collect_sources = (
            {
                track: b"".join(
                    (canonical_json(record) + "\n").encode()
                    for record in decisions
                    if record["track"] == track.value
                )
                for track in LiveTrack
            },
            envoy,
            targets,
        )
        drivers = {
            item["track"]: item
            for item in controller.bound_state["objects"]
            if item["role"] == "driver"
        }
        changes = behavior_changes or {}
        behaviors = {}
        raw_results = {}
        for track in LiveTrack:
            readiness = {
                "schema_version": "kil.v3b1-driver-readiness.v1",
                "track": track.value,
                "status": "ready",
                "connect_monotonic_ns": 1,
                "ready_monotonic_ns": 2,
            }
            result = self.success_result(track)
            raw_result = (canonical_json(result) + "\n").encode()
            raw_results[track] = raw_result
            readiness_payload = (canonical_json(readiness) + "\n").encode()
            behavior = {
                "payload": (
                    readiness_payload
                    if behavior_changes
                    and track is not LiveTrack.CREDENTIAL_POLICY_BASELINE
                    else readiness_payload + raw_result
                ),
            }
            behavior.update(changes.get(track.value, {}))
            behaviors[drivers[track.value]["id"]] = behavior
        factory = _DriverProcessFactory(behaviors, events=events, clock=clock)
        controller.driver_process_factory = factory
        controller.runner = _DriverStateRunner(
            {
                full_id: behavior.get("container_running", False)
                for full_id, behavior in behaviors.items()
            }
        )
        return controller, factory, drivers, events, raw_results

    @staticmethod
    def event_positions(journal, event_name, track=None):
        return [
            index
            for index, event in enumerate(journal["events"])
            if event["event"] == event_name
            and (track is None or event["details"].get("track") == track.value)
        ]

    def test_all_ready_then_one_exact_instruction_and_result_per_fixed_track(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, drivers, events, raw_results = self.make_controller(directory)

            output = controller.run()

            self.assertEqual(output, controller.root / "collected")
            writes = [event for event in events if event[0] == "stdin_write"]
            self.assertEqual(
                [event[1] for event in writes],
                [drivers[track.value]["id"] for track in LiveTrack],
            )
            first_write = events.index(writes[0])
            self.assertEqual(
                len([event for event in events[:first_write] if event[0] == "stdout_readline"]),
                3,
            )
            q_states = []
            for track, event in zip(LiveTrack, writes, strict=True):
                instruction = json.loads(event[2])
                self.assertEqual(instruction["track"], track.value)
                self.assertEqual(
                    instruction["headers"]["authorization"],
                    "Bearer v3b1-lab-credential",
                )
                if track is LiveTrack.CREDENTIAL_POLICY_BASELINE:
                    self.assertNotIn("x-kil-q-state", instruction["headers"])
                else:
                    q_states.append(instruction["headers"]["x-kil-q-state"])
                process = next(item for item in factory.processes if item.full_id == event[1])
                self.assertEqual(process.stdin.getvalue() if not process.stdin.closed else event[2], event[2])
                self.assertTrue(process.stdin.closed)
                raw_path = (
                    controller.private_root
                    / "driver-results"
                    / str(controller.bound_manifest["run_id"])
                    / f"{track.value}.json"
                )
                self.assertEqual(raw_path.read_bytes(), raw_results[track])
                self.assertEqual(stat.S_IMODE(raw_path.stat().st_mode), 0o600)

            journal = load_lifecycle_journal(controller.journal_path)
            ready_set = self.event_positions(journal, "driver_readiness_set_complete")[0]
            for track in LiveTrack:
                ordered = [
                    self.event_positions(journal, name, track)[0]
                    for name in (
                        "request_send_intent",
                        "driver_instruction_write_intent",
                        "driver_result_persisted",
                        "request_record_persisted",
                        "request_send_complete",
                    )
                ]
                self.assertLess(ready_set, ordered[0])
                self.assertEqual(ordered, sorted(ordered))

            request_path = _runtime_root(controller.root, controller.bound_manifest) / "requests.jsonl"
            records = [json.loads(line) for line in request_path.read_text().splitlines()]
            self.assertEqual([record["track"] for record in records], [track.value for track in LiveTrack])
            self.assertTrue(all(record["schema_version"] == "kil.v3b1-request.v2" for record in records))
            self.assertEqual(
                [record["driver_result_sha256"] for record in records],
                [sha256(raw_results[track]).hexdigest() for track in LiveTrack],
            )
            serialized = controller.journal_path.read_text()
            self.assertNotIn("Bearer v3b1-lab-credential", serialized)
            for q_state in q_states:
                self.assertNotIn(q_state, serialized)
                self.assertNotIn(q_state, request_path.read_text())
            self.assertFalse(any("authorization" in " ".join(event[1]) for event in events if event[0] == "start"))

    def test_real_run_collect_handoff_binds_three_exact_driver_results(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, _, _, _, raw_results = self.make_controller(
                directory, real_collect=True
            )

            output = controller.run()

            requests = [
                json.loads(line)
                for line in (output / "requests.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            by_track = {record["track"]: record for record in requests}
            for track in LiveTrack:
                relative = f"raw/drivers/{track.value}.json"
                payload = (output / relative).read_bytes()
                self.assertEqual(payload, raw_results[track])
                self.assertEqual(
                    by_track[track.value]["driver_result_sha256"],
                    sha256(payload).hexdigest(),
                )
                self.assertEqual(
                    payload,
                    (canonical_json(json.loads(payload)) + "\n").encode(),
                )
            self.assertEqual(
                authoritative_bundle_attestation(output)["schema_version"],
                "kil.v3b1-authoritative-bundle.v2",
            )

    def test_dangling_private_driver_result_symlink_is_never_uncommanded(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, _, _, _, _ = self.make_controller(directory)
            raw_root = (
                controller.private_root
                / "driver-results"
                / controller.bound_manifest["run_id"]
            )
            raw_root.mkdir(parents=True)
            path = raw_root / "credential_policy_baseline.json"
            path.symlink_to(raw_root / "missing-driver-result.json")

            with self.assertRaisesRegex(ControllerError, "unsafe|symbolic"):
                controller._private_driver_result_sources(
                    controller.bound_manifest
                )

    def test_post_intent_failures_are_terminal_cancel_later_drivers_and_never_retry(self):
        baseline = LiveTrack.CREDENTIAL_POLICY_BASELINE.value
        valid_result = (canonical_json(self.success_result(LiveTrack.CREDENTIAL_POLICY_BASELINE)) + "\n").encode()
        readiness = (
            canonical_json(
                {
                    "schema_version": "kil.v3b1-driver-readiness.v1",
                    "track": baseline,
                    "status": "ready",
                    "connect_monotonic_ns": 1,
                    "ready_monotonic_ns": 2,
                }
            )
            + "\n"
        ).encode()
        transport = (canonical_json(self.transport_failure(LiveTrack.CREDENTIAL_POLICY_BASELINE)) + "\n").encode()
        cases = {
            "partial_write": {"partial_write": 1},
            "broken_stdin": {"write_error": BrokenPipeError(errno.EPIPE, "private token")},
            "invalid_result": {"payload": readiness + b"not-json\n"},
            "missing_result": {"payload": readiness},
            "extra_stdout": {"payload": readiness + valid_result + b"{}\n"},
            "nonzero_exit": {"returncode": 7},
            "timeout": {"wait_error": subprocess.TimeoutExpired("private", 1)},
            "driver_transport_failure": {"payload": readiness + transport, "returncode": 1},
        }
        for name, change in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                controller, factory, drivers, events, _ = self.make_controller(
                    directory, {baseline: change}
                )

                with self.assertRaisesRegex(ControllerError, "failed|terminal|teardown"):
                    controller.run()

                journal = load_lifecycle_journal(controller.journal_path)
                self.assertEqual(journal["requests"][baseline]["status"], "failed")
                self.assertEqual(
                    [journal["requests"][track.value]["status"] for track in tuple(LiveTrack)[1:]],
                    ["not_attempted", "not_attempted"],
                )
                failures = self.event_positions(
                    journal, "request_send_failed", LiveTrack.CREDENTIAL_POLICY_BASELINE
                )
                self.assertEqual(len(failures), 1)
                provenance = journal["events"][failures[0]]["details"]["provenance"]
                self.assertTrue(provenance["request_bytes_may_have_been_sent"])
                self.assertFalse(provenance["retry_performed"])
                self.assertEqual(provenance["attempt_count"], 1)
                later_ids = {drivers[track.value]["id"] for track in tuple(LiveTrack)[1:]}
                later_writes = [
                    event for event in events
                    if event[0] == "stdin_write" and event[1] in later_ids
                ]
                self.assertEqual(later_writes, [])
                later_processes = [item for item in factory.processes if item.full_id in later_ids]
                self.assertTrue(all(item.stdin.closed for item in later_processes))
                self.assertTrue(all(item.exited and item.reaped for item in later_processes))
                self.assertEqual(len([event for event in events if event[0] == "start"]), 3)
                self.assertFalse(any(event[0] == "collect" for event in events))
                raw = controller.journal_path.read_text()
                self.assertNotIn("private token", raw)

    def test_host_request_helpers_and_direct_http_request_path_are_absent(self):
        source = (ROOT / "tools/v3b1_local_envoy.py").read_text()
        self.assertNotIn("def _connect_ready_gateways", source)
        self.assertNotIn("def _reset_request_timeouts", source)
        self.assertNotIn("connection.request(", source)
        self.assertNotIn("connection_factory", source)

    def test_later_cancellation_failure_does_not_skip_remaining_ready_driver(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, drivers, events, _ = self.make_controller(
                directory,
                {
                    LiveTrack.CREDENTIAL_POLICY_BASELINE.value: {
                        "partial_write": 1,
                    },
                    LiveTrack.SIGNED_STATE_ONLY.value: {"returncode": 7},
                },
            )

            with self.assertRaisesRegex(ControllerError, "terminal|teardown"):
                controller.run()

            later_ids = {
                drivers[track.value]["id"] for track in tuple(LiveTrack)[1:]
            }
            later_processes = [
                process for process in factory.processes
                if process.full_id in later_ids
            ]
            self.assertTrue(all(process.stdin.closed for process in later_processes))
            self.assertEqual(
                {
                    event[1] for event in events
                    if event[0] == "stdin_close" and event[1] in later_ids
                },
                later_ids,
            )

    def test_expired_request_deadline_uses_fresh_structured_later_cleanup(self):
        baseline = LiveTrack.CREDENTIAL_POLICY_BASELINE.value
        signed = LiveTrack.SIGNED_STATE_ONLY.value
        local = LiveTrack.SIGNED_PLUS_LOCAL_REDUCE.value
        cases = {
            "wait_failure": {
                "wait_error": subprocess.TimeoutExpired("private", 1),
                "terminate_exits": False,
                "expected": "driver_cleanup_complete",
            },
            "pipe_failure": {
                "stdin_close_error": True,
                "expected": "driver_cleanup_complete",
            },
            "cleanup_failure": {
                "wait_error": subprocess.TimeoutExpired("private", 1),
                "terminate_exits": False,
                "stdout_close_error": True,
                "expected": "driver_cleanup_failed",
            },
        }
        for name, signed_case in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                signed_change = dict(signed_case)
                expected_event = signed_change.pop("expected")
                controller, factory, drivers, events, _ = self.make_controller(
                    directory,
                    {
                        baseline: {
                            "partial_write": 1,
                            "advance_write_ns": 31_000_000_000,
                        },
                        signed: signed_change,
                    },
                )

                with self.assertRaisesRegex(ControllerError, "terminal|teardown"):
                    controller.run()

                journal = load_lifecycle_journal(controller.journal_path)
                self.assertTrue(controller.readiness_poison_path.is_file())
                self.assertEqual(
                    [journal["requests"][track]["status"] for track in (signed, local)],
                    ["not_attempted", "not_attempted"],
                )
                later_ids = {drivers[signed]["id"], drivers[local]["id"]}
                self.assertEqual(
                    {
                        event[1] for event in events
                        if event[0] == "stdin_close" and event[1] in later_ids
                    },
                    later_ids,
                )
                self.assertTrue(all(process.exited for process in factory.processes[1:]))
                self.assertTrue(all(process.reaped for process in factory.processes[1:]))
                terminal_by_id = {
                    event["details"]["driver_id"]: event["event"]
                    for event in journal["events"]
                    if event["event"] in {
                        "readiness_cancel_complete",
                        "driver_cleanup_complete",
                        "driver_cleanup_failed",
                    }
                    and event["details"]["driver_id"] in later_ids
                }
                self.assertEqual(
                    terminal_by_id[drivers[signed]["id"]], expected_event
                )
                self.assertEqual(
                    terminal_by_id[drivers[local]["id"]],
                    "readiness_cancel_complete",
                )
                self.assertEqual(
                    len([event for event in events if event[0] == "start"]), 3
                )
                self.assertNotIn("private stdin close failure", controller.journal_path.read_text())

    def test_run_readiness_failures_use_shared_poisoned_failure_path(self):
        wrong = {
            "schema_version": "kil.v3b1-driver-readiness.v1",
            "track": LiveTrack.SIGNED_STATE_ONLY.value,
            "status": "ready",
            "connect_monotonic_ns": 1,
            "ready_monotonic_ns": 2,
        }
        cases = {
            "malformed": {
                "change": {"payload": b"private malformed readiness\n"},
                "failed_event": None,
            },
            "wrong_track": {
                "change": {"payload": (canonical_json(wrong) + "\n").encode()},
                "failed_event": None,
            },
            "timeout": {
                "change": {"advance_ns": 31_000_000_000},
                "failed_event": None,
            },
            "start": {
                "change": {"start_error": DriverTransportError("process_start")},
                "failed_event": None,
            },
            "persistence": {
                "change": {},
                "failed_event": "driver_readiness_complete",
            },
        }
        baseline = LiveTrack.CREDENTIAL_POLICY_BASELINE.value
        for name, case in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                controller, factory, drivers, events, _ = self.make_controller(
                    directory, {baseline: case["change"]}
                )
                real_journal_event = local_envoy_module.journal_event
                failed_once = False

                def fail_selected_event(path, event, details):
                    nonlocal failed_once
                    if (
                        not failed_once
                        and event == case["failed_event"]
                        and details.get("track") == baseline
                    ):
                        failed_once = True
                        raise ControllerError("private readiness persistence failure")
                    return real_journal_event(path, event, details)

                with mock.patch(
                    "tools.v3b1_local_envoy.journal_event",
                    side_effect=fail_selected_event,
                ):
                    with self.assertRaisesRegex(ControllerError, "readiness|failed closed|down"):
                        controller.run()

                journal = load_lifecycle_journal(controller.journal_path)
                self.assertEqual(
                    {record["status"] for record in journal["requests"].values()},
                    {"not_attempted"},
                )
                self.assertTrue(controller.readiness_poison_path.is_file())
                failure = next(
                    event for event in journal["events"]
                    if event["event"] == "driver_readiness_failed"
                )
                self.assertEqual(failure["details"]["track"], baseline)
                self.assertEqual(
                    failure["details"]["driver_id"],
                    drivers[baseline]["id"],
                )
                if name == "persistence":
                    self.assertEqual(
                        failure["details"]["category"], "controller_persistence"
                    )
                    self.assertEqual(
                        failure["details"]["stage"], "readiness_complete"
                    )
                self.assertTrue(all(process.stdin.closed for process in factory.processes))
                self.assertTrue(all(process.exited for process in factory.processes))
                self.assertTrue(all(process.reaped for process in factory.processes))
                raw = controller.journal_path.read_text()
                self.assertNotIn("private malformed readiness", raw)
                self.assertNotIn("private readiness persistence failure", raw)
                starts = len([event for event in events if event[0] == "start"])
                with self.assertRaisesRegex(ControllerError, "poison|incomplete|down"):
                    controller.run()
                self.assertEqual(
                    len([event for event in events if event[0] == "start"]), starts
                )

    def test_run_post_session_oserrors_fail_closed_without_raw_text(self):
        baseline = LiveTrack.CREDENTIAL_POLICY_BASELINE.value
        for name in ("readiness_persistence", "deadline_creation"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                controller, factory, drivers, events, _ = self.make_controller(directory)
                real_journal_event = local_envoy_module.journal_event
                failed_once = False

                def fail_readiness_persistence(path, event, details):
                    nonlocal failed_once
                    if (
                        name == "readiness_persistence"
                        and not failed_once
                        and event == "driver_readiness_complete"
                        and details.get("track") == baseline
                    ):
                        failed_once = True
                        raise OSError("PRIVATE run persistence failure")
                    return real_journal_event(path, event, details)

                with ExitStack() as stack:
                    stack.enter_context(
                        mock.patch(
                            "tools.v3b1_local_envoy.journal_event",
                            side_effect=fail_readiness_persistence,
                        )
                    )
                    if name == "deadline_creation":
                        stack.enter_context(
                            mock.patch.object(
                                controller,
                                "_monotonic_now",
                                side_effect=OSError("PRIVATE run deadline failure"),
                            )
                        )
                    with self.assertRaisesRegex(ControllerError, "failed closed|down"):
                        controller.run()

                journal = load_lifecycle_journal(controller.journal_path)
                self.assertEqual(
                    {request["status"] for request in journal["requests"].values()},
                    {"not_attempted"},
                )
                self.assertTrue(controller.readiness_poison_path.is_file())
                failure = next(
                    event for event in journal["events"]
                    if event["event"] == "driver_readiness_failed"
                )["details"]
                if name == "readiness_persistence":
                    self.assertEqual(
                        failure,
                        {
                            "readiness_nonce": failure["readiness_nonce"],
                            "scope": "driver",
                            "track": baseline,
                            "driver_id": drivers[baseline]["id"],
                            "category": "controller_persistence",
                            "stage": "readiness_complete",
                        },
                    )
                else:
                    self.assertEqual(
                        failure,
                        {
                            "readiness_nonce": failure["readiness_nonce"],
                            "scope": "controller",
                            "track": None,
                            "driver_id": None,
                            "category": "clock_failure",
                            "stage": "readiness_deadline",
                        },
                    )
                self.assertTrue(all(process.stdin.closed for process in factory.processes))
                self.assertTrue(all(process.exited for process in factory.processes))
                self.assertTrue(all(process.reaped for process in factory.processes))
                raw = controller.journal_path.read_text()
                self.assertNotIn("PRIVATE run persistence failure", raw)
                self.assertNotIn("PRIVATE run deadline failure", raw)
                starts = len([event for event in events if event[0] == "start"])
                with self.assertRaisesRegex(ControllerError, "poison|incomplete|down"):
                    controller.run()
                self.assertEqual(
                    len([event for event in events if event[0] == "start"]), starts
                )

    def test_pre_instruction_failures_cancel_every_uncommanded_driver_and_poison(self):
        cases = {
            "claim_persistence": {
                "patch": "claim",
                "failed_track": LiveTrack.CREDENTIAL_POLICY_BASELINE,
                "expected": ["not_attempted", "not_attempted", "not_attempted"],
            },
            "q_state_issue": {
                "patch": "q_issue",
                "failed_track": LiveTrack.SIGNED_STATE_ONLY,
                "expected": ["completed", "not_attempted", "not_attempted"],
            },
            "q_state_expiry": {
                "patch": "q_expiry",
                "failed_track": LiveTrack.SIGNED_STATE_ONLY,
                "expected": ["completed", "not_attempted", "not_attempted"],
            },
            "instruction_canonicalization": {
                "patch": "instruction",
                "failed_track": LiveTrack.CREDENTIAL_POLICY_BASELINE,
                "expected": ["failed", "not_attempted", "not_attempted"],
            },
        }
        for name, case in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                controller, factory, _, events, _ = self.make_controller(directory)
                with ExitStack() as stack:
                    if case["patch"] == "claim":
                        stack.enter_context(
                            mock.patch(
                                "tools.v3b1_local_envoy.claim_request_attempt",
                                side_effect=ControllerError(
                                    "private claim persistence failure"
                                ),
                            )
                        )
                    elif case["patch"] == "q_issue":
                        stack.enter_context(
                            mock.patch(
                                "tools.v3b1_local_envoy.issue_q_state",
                                side_effect=RuntimeError("private q-state failure"),
                            )
                        )
                    elif case["patch"] == "q_expiry":
                        stack.enter_context(
                            mock.patch(
                                "tools.v3b1_local_envoy.time.time",
                                side_effect=[100, 100, 111],
                            )
                        )
                    else:
                        stack.enter_context(
                            mock.patch(
                                "tools.v3b1_local_envoy.parse_driver_instruction",
                                side_effect=DriverTransportError(
                                    "private_instruction_parser"
                                ),
                            )
                        )
                    with self.assertRaisesRegex(
                        ControllerError,
                        "failed|terminal|expired|teardown|down",
                    ):
                        controller.run()

                journal = load_lifecycle_journal(controller.journal_path)
                self.assertEqual(
                    [journal["requests"][track.value]["status"] for track in LiveTrack],
                    case["expected"],
                )
                self.assertTrue(controller.readiness_poison_path.is_file())
                failed_index = list(LiveTrack).index(case["failed_track"])
                uncommanded_ids = {
                    process.full_id for process in factory.processes[failed_index:]
                }
                self.assertEqual(
                    {
                        event[1] for event in events
                        if event[0] == "stdin_close" and event[1] in uncommanded_ids
                    },
                    uncommanded_ids,
                )
                self.assertTrue(
                    all(
                        process.exited and process.reaped
                        for process in factory.processes[failed_index:]
                    )
                )
                raw = controller.journal_path.read_text()
                for secret in (
                    "private claim persistence failure",
                    "private q-state failure",
                    "private_instruction_parser",
                ):
                    self.assertNotIn(secret, raw)
                starts = len([event for event in events if event[0] == "start"])
                with self.assertRaisesRegex(ControllerError, "poison|incomplete|down"):
                    controller.run()
                self.assertEqual(
                    len([event for event in events if event[0] == "start"]), starts
                )

    def test_q_state_issue_is_after_aggregate_readiness_and_before_bound_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, _, _, events, _ = self.make_controller(directory)
            real_issue = local_envoy_module.issue_q_state
            real_claim = local_envoy_module.claim_request_attempt

            def observed_issue(claims, private_key):
                journal = load_lifecycle_journal(controller.journal_path)
                self.assertTrue(
                    any(
                        event["event"] == "driver_readiness_set_complete"
                        for event in journal["events"]
                    )
                )
                events.append(("q_issue", claims.audience))
                return real_issue(claims, private_key)

            def observed_claim(path, track, *, readiness_nonce):
                events.append(("request_claim", track.value))
                return real_claim(path, track, readiness_nonce=readiness_nonce)

            with mock.patch(
                "tools.v3b1_local_envoy.issue_q_state", side_effect=observed_issue
            ), mock.patch(
                "tools.v3b1_local_envoy.claim_request_attempt",
                side_effect=observed_claim,
            ):
                controller.run()

            for track, audience in (
                (LiveTrack.SIGNED_STATE_ONLY, "kil-v3-signed"),
                (LiveTrack.SIGNED_PLUS_LOCAL_REDUCE, "kil-v3-local"),
            ):
                issue_index = events.index(("q_issue", audience))
                claim_index = events.index(("request_claim", track.value))
                write_index = next(
                    index for index, event in enumerate(events)
                    if event[0] == "stdin_write"
                    and json.loads(event[2])["track"] == track.value
                )
                self.assertEqual(claim_index, issue_index + 1)
                self.assertLess(claim_index, write_index)
                self.assertGreaterEqual(
                    len(
                        [
                            event for event in events[:issue_index]
                            if event[0] == "stdout_readline"
                        ]
                    ),
                    3,
                )

    def test_false_request_send_result_is_normalized_conservatively(self):
        baseline = LiveTrack.CREDENTIAL_POLICY_BASELINE
        result = self.transport_failure(baseline)
        result["stage"] = "request_send"
        result["request_bytes_may_have_been_sent"] = False
        readiness = {
            "schema_version": "kil.v3b1-driver-readiness.v1",
            "track": baseline.value,
            "status": "ready",
            "connect_monotonic_ns": 1,
            "ready_monotonic_ns": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            controller, factory, _, _, _ = self.make_controller(
                directory,
                {
                    baseline.value: {
                        "payload": (
                            canonical_json(readiness)
                            + "\n"
                            + canonical_json(result)
                            + "\n"
                        ).encode(),
                        "returncode": 1,
                    }
                },
            )

            with self.assertRaisesRegex(ControllerError, "transport failure|teardown"):
                controller.run()

            journal = load_lifecycle_journal(controller.journal_path)
            provenance = next(
                event["details"]["provenance"]
                for event in journal["events"]
                if event["event"] == "request_send_failed"
            )
            self.assertTrue(provenance["request_bytes_may_have_been_sent"])
            self.assertFalse(provenance["retry_performed"])
            self.assertTrue(controller.readiness_poison_path.is_file())
            self.assertTrue(all(process.stdin.closed for process in factory.processes[1:]))

    def test_linux_driver_errno_provenance_is_exact_and_raw_result_bound(self):
        baseline = LiveTrack.CREDENTIAL_POLICY_BASELINE
        for number, name in (
            (104, "ECONNRESET"),
            (111, "ECONNREFUSED"),
            (133, "EHWPOISON"),
        ):
            with self.subTest(errno=number), tempfile.TemporaryDirectory() as directory:
                result = self.transport_failure(
                    baseline,
                    errno_number=number,
                    errno_name=name,
                )
                readiness = {
                    "schema_version": "kil.v3b1-driver-readiness.v1",
                    "track": baseline.value,
                    "status": "ready",
                    "connect_monotonic_ns": 1,
                    "ready_monotonic_ns": 2,
                }
                raw_result = (canonical_json(result) + "\n").encode()
                controller, _, drivers, _, _ = self.make_controller(
                    directory,
                    {
                        baseline.value: {
                            "payload": (
                                canonical_json(readiness) + "\n"
                            ).encode()
                            + raw_result,
                            "returncode": 1,
                        }
                    },
                )

                with self.assertRaisesRegex(ControllerError, "terminal|teardown"):
                    controller.run()

                journal = load_lifecycle_journal(controller.journal_path)
                failure = next(
                    event for event in journal["events"]
                    if event["event"] == "request_send_failed"
                )
                provenance = failure["details"]["provenance"]
                definition = next(
                    item for item in controller.bound_manifest["driver_definitions"]
                    if item["track"] == baseline.value
                )
                self.assertEqual(provenance["provenance_source"], "linux_request_driver")
                self.assertEqual((provenance["errno"], provenance["errno_name"]), (number, name))
                self.assertEqual(provenance["track"], baseline.value)
                self.assertEqual(
                    provenance["driver_full_id"], drivers[baseline.value]["id"]
                )
                self.assertEqual(
                    provenance["driver_definition_sha256"],
                    sha256(local_envoy_module.canonical_record(definition)).hexdigest(),
                )
                self.assertEqual(
                    provenance["driver_result_sha256"], sha256(raw_result).hexdigest()
                )
                raw_path = (
                    controller.private_root
                    / "driver-results"
                    / str(controller.bound_manifest["run_id"])
                    / f"{baseline.value}.json"
                )
                self.assertEqual(raw_path.read_bytes(), raw_result)
                self.assertEqual(
                    (provenance["connect_monotonic_ns"], provenance["send_monotonic_ns"], provenance["failure_monotonic_ns"]),
                    (result["connect_monotonic_ns"], result["send_monotonic_ns"], result["failure_monotonic_ns"]),
                )

                bad_errno = dict(provenance)
                bad_errno["errno_name"] = "EIO"
                with self.assertRaisesRegex(ControllerError, "driver.*provenance|errno"):
                    local_envoy_module._validate_driver_transport_provenance(bad_errno)

                rebound_fact = dict(provenance)
                rebound_fact["errno"], rebound_fact["errno_name"] = (
                    (111, "ECONNREFUSED")
                    if number != 111
                    else (104, "ECONNRESET")
                )
                with self.assertRaisesRegex(ControllerError, "driver.*result|binding"):
                    local_envoy_module._validate_driver_transport_provenance(
                        rebound_fact
                    )

                mutated = json.loads(json.dumps(journal))
                mutated_failure = next(
                    event for event in mutated["events"]
                    if event["event"] == "request_send_failed"
                )
                mutated_failure["details"]["provenance"]["driver_result_sha256"] = HEX_C
                with self.assertRaisesRegex(ControllerError, "driver.*binding|result"):
                    local_envoy_module._validate_lifecycle_history(
                        mutated["events"], mutated["requests"]
                    )

    def test_post_result_terminal_anomalies_are_closed_and_cancel_later(self):
        cases = {
            "timeout": (
                {"wait_error": subprocess.TimeoutExpired("private", 1)},
                "process_wait",
            ),
            "wait_error": ({"wait_error": OSError("private wait error")}, "process_wait"),
            "stderr": ({"stderr": b"private post-result stderr"}, "termination"),
            "ambiguous_exit": ({"poll_result": 9}, "termination"),
            "extra_stdout": ({"payload": None}, "termination"),
            "wrong_exit": ({"returncode": 7}, "termination"),
        }
        baseline = LiveTrack.CREDENTIAL_POLICY_BASELINE.value
        for name, (change, expected_stage) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                if name == "extra_stdout":
                    readiness = {
                        "schema_version": "kil.v3b1-driver-readiness.v1",
                        "track": baseline,
                        "status": "ready",
                        "connect_monotonic_ns": 1,
                        "ready_monotonic_ns": 2,
                    }
                    result = self.success_result(
                        LiveTrack.CREDENTIAL_POLICY_BASELINE
                    )
                    change = {
                        "payload": (
                            canonical_json(readiness)
                            + "\n"
                            + canonical_json(result)
                            + "\n{}\n"
                        ).encode()
                    }
                controller, factory, _, _, _ = self.make_controller(
                    directory, {baseline: change}
                )

                with self.assertRaisesRegex(ControllerError, "terminal|teardown"):
                    controller.run()

                journal = load_lifecycle_journal(controller.journal_path)
                failure = next(
                    event for event in journal["events"]
                    if event["event"] == "request_send_failed"
                )
                self.assertEqual(
                    failure["details"]["provenance"]["stage"], expected_stage
                )
                self.assertTrue(
                    failure["details"]["provenance"]
                    ["request_bytes_may_have_been_sent"]
                )
                self.assertTrue(controller.readiness_poison_path.is_file())
                self.assertTrue(all(process.stdin.closed for process in factory.processes[1:]))
                self.assertNotIn(
                    "private post-result stderr", controller.journal_path.read_text()
                )

    def test_post_intent_persistence_failures_use_termination_stage_and_cancel(self):
        cases = (
            "raw_result_file",
            "raw_result_journal",
            "normalized_request_file",
            "normalized_request_journal",
            "request_completion_journal",
        )
        baseline = LiveTrack.CREDENTIAL_POLICY_BASELINE.value
        for name in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                controller, factory, _, _, _ = self.make_controller(directory)
                request_path = (
                    _runtime_root(controller.root, controller.bound_manifest)
                    / "requests.jsonl"
                )
                real_write = local_envoy_module._write_file
                real_journal_event = local_envoy_module.journal_event
                real_persist_journal = local_envoy_module._persist_journal
                failed_once = False

                def fail_selected_write(path, payload, mode):
                    nonlocal failed_once
                    candidate = Path(path)
                    raw_result = "driver-results" in candidate.parts
                    selected = (
                        name == "raw_result_file" and raw_result
                    ) or (
                        name == "normalized_request_file" and candidate == request_path
                    )
                    if not failed_once and selected:
                        failed_once = True
                        raise ControllerError("private file persistence failure")
                    return real_write(path, payload, mode)

                selected_event = {
                    "raw_result_journal": "driver_result_persisted",
                    "normalized_request_journal": "request_record_persisted",
                    "request_completion_journal": "request_send_complete",
                }.get(name)

                def fail_selected_journal(path, event, details):
                    nonlocal failed_once
                    if (
                        not failed_once
                        and selected_event is not None
                        and event == selected_event
                        and details.get("track") == baseline
                    ):
                        failed_once = True
                        raise ControllerError("private journal persistence failure")
                    return real_journal_event(path, event, details)

                def fail_selected_persist(path, value):
                    nonlocal failed_once
                    if (
                        not failed_once
                        and name == "request_completion_journal"
                        and value.get("phase") == "request_send_complete"
                    ):
                        failed_once = True
                        raise ControllerError("private completion persistence failure")
                    return real_persist_journal(path, value)

                with mock.patch(
                    "tools.v3b1_local_envoy._write_file",
                    side_effect=fail_selected_write,
                ), mock.patch(
                    "tools.v3b1_local_envoy.journal_event",
                    side_effect=fail_selected_journal,
                ), mock.patch(
                    "tools.v3b1_local_envoy._persist_journal",
                    side_effect=fail_selected_persist,
                ):
                    with self.assertRaisesRegex(ControllerError, "terminal|teardown"):
                        controller.run()

                journal = load_lifecycle_journal(controller.journal_path)
                self.assertEqual(journal["requests"][baseline]["status"], "failed")
                self.assertEqual(
                    [
                        journal["requests"][track.value]["status"]
                        for track in tuple(LiveTrack)[1:]
                    ],
                    ["not_attempted", "not_attempted"],
                )
                failure = next(
                    event for event in journal["events"]
                    if event["event"] == "request_send_failed"
                )
                self.assertEqual(
                    failure["details"]["provenance"]["stage"], "termination"
                )
                self.assertTrue(
                    failure["details"]["provenance"]
                    ["request_bytes_may_have_been_sent"]
                )
                self.assertTrue(controller.readiness_poison_path.is_file())
                self.assertTrue(all(process.stdin.closed for process in factory.processes[1:]))
                raw = controller.journal_path.read_text()
                self.assertNotIn("private file persistence failure", raw)
                self.assertNotIn("private journal persistence failure", raw)
                self.assertNotIn("private completion persistence failure", raw)

    def test_commanded_failures_publish_bound_control_results_not_empty(self):
        baseline_track = LiveTrack.CREDENTIAL_POLICY_BASELINE
        baseline = baseline_track.value
        readiness = (
            canonical_json(
                {
                    "schema_version": "kil.v3b1-driver-readiness.v1",
                    "track": baseline,
                    "status": "ready",
                    "connect_monotonic_ns": 1,
                    "ready_monotonic_ns": 2,
                }
            )
            + "\n"
        ).encode()
        cases = {
            "instruction_write": {
                "behavior": {"write_error": BrokenPipeError(errno.EPIPE, "private")},
                "expected_stage": "instruction_write",
            },
            "stdout_read": {
                "behavior": {"payload": readiness + b"not-json\n"},
                "expected_stage": "stdout_read",
            },
            "process_wait": {
                "behavior": {
                    "wait_error": subprocess.TimeoutExpired("private", 1)
                },
                "expected_stage": "process_wait",
            },
            "termination": {
                "behavior": {"stderr": b"private post-result stderr"},
                "expected_stage": "termination",
            },
            "persistence": {
                "behavior": {},
                "expected_stage": "termination",
            },
        }
        for name, case in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                controller, _, _, _, _ = self.make_controller(
                    directory, {baseline: case["behavior"]}
                )
                real_write = local_envoy_module._write_file

                def fail_driver_result_writes(path, payload, mode):
                    if name == "persistence" and "driver-results" in Path(path).parts:
                        raise ControllerError("private driver persistence failure")
                    return real_write(path, payload, mode)

                with mock.patch(
                    "tools.v3b1_local_envoy._write_file",
                    side_effect=fail_driver_result_writes,
                ):
                    with self.assertRaisesRegex(
                        ControllerError, "terminal|teardown"
                    ):
                        controller.run()

                journal = load_lifecycle_journal(controller.journal_path)
                failure = next(
                    event
                    for event in journal["events"]
                    if event["event"] == "request_send_failed"
                )
                provenance = failure["details"]["provenance"]
                self.assertEqual(provenance["stage"], case["expected_stage"])
                self.assertEqual(provenance["attempt_count"], 1)
                self.assertFalse(provenance["retry_performed"])

                requests = controller._failure_request_records(
                    controller.bound_manifest
                )
                private_result = (
                    controller.private_root
                    / "driver-results"
                    / controller.bound_manifest["run_id"]
                    / f"{baseline}.json"
                )
                if name == "persistence":
                    self.assertFalse(private_result.exists())
                else:
                    self.assertEqual(
                        stat.S_IMODE(private_result.stat().st_mode), 0o600
                    )
                raw_driver_results = controller._private_driver_result_sources(
                    controller.bound_manifest
                )
                expected_result = {
                    "attempt_count": 1,
                    "failure_monotonic_ns": provenance["failure_monotonic_ns"],
                    "request_bytes_may_have_been_sent": provenance[
                        "request_bytes_may_have_been_sent"
                    ],
                    "retry_performed": False,
                    "schema_version": "kil.v3b1-driver-result.v1",
                    "stage": case["expected_stage"],
                    "status": "driver_control_failure",
                    "track": baseline,
                }
                expected_raw = (canonical_json(expected_result) + "\n").encode()
                self.assertEqual(raw_driver_results[baseline_track], expected_raw)
                self.assertTrue(
                    all(
                        raw_driver_results[track] == b""
                        for track in tuple(LiveTrack)[1:]
                    )
                )
                self.assertEqual(len(requests), 1)
                self.assertEqual(
                    requests[0]["schema_version"],
                    "kil.v3b1-request-failure.v1",
                )
                self.assertEqual(
                    requests[0]["driver_result_sha256"],
                    sha256(expected_raw).hexdigest(),
                )

                root = Path(directory)
                provisional = _prepare_failure_provisional(
                    root / "private-evidence",
                    controller.bound_manifest,
                    requests=requests,
                    raw_driver_results=raw_driver_results,
                    reset=True,
                )
                authority = authoritative_bundle_attestation(provisional)
                published = finalize_publication(
                    provisional,
                    root / "public-evidence",
                    controller.bound_manifest,
                    source_attestations=[],
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=False,
                    authoritative_attestation=authority,
                )
                self.assertEqual(
                    (
                        published
                        / f"raw/drivers/{baseline}.json"
                    ).read_bytes(),
                    expected_raw,
                )
                self.assertEqual(
                    local_envoy_module._verify_failure_presenter_bundle(
                        published
                    ),
                    published.resolve() / "live.html",
                )
                if name == "instruction_write":
                    requests_path = published / "requests.jsonl"
                    mutated = [
                        json.loads(line)
                        for line in requests_path.read_text(
                            encoding="utf-8"
                        ).splitlines()
                    ]
                    mutated[0]["journal_event_sha256"] = HEX_C
                    requests_path.chmod(0o600)
                    requests_path.write_bytes(
                        b"".join(
                            (canonical_json(record) + "\n").encode()
                            for record in mutated
                        )
                    )
                    requests_path.chmod(0o444)
                    rewrite_public_bundle_hashes(published)
                    with self.assertRaisesRegex(
                        ControllerError, "journal binding"
                    ):
                        local_envoy_module._verify_failure_presenter_bundle(
                            published
                        )

    def test_commanded_failure_without_closed_provenance_rejects_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, _, _, _, _ = self.make_controller(directory)
            with mock.patch(
                "tools.v3b1_local_envoy._complete_request_attempt",
                side_effect=ControllerError("private terminal persistence failure"),
            ):
                with self.assertRaisesRegex(ControllerError, "terminal|teardown"):
                    controller.run()

            journal = load_lifecycle_journal(controller.journal_path)
            self.assertEqual(
                journal["requests"][LiveTrack.CREDENTIAL_POLICY_BASELINE.value][
                    "status"
                ],
                "intent_persisted",
            )
            with self.assertRaisesRegex(
                ControllerError, "terminal closed provenance"
            ):
                controller._private_driver_result_sources(
                    controller.bound_manifest
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

    def test_driver_recovery_authority_is_journal_phase_closed(self):
        track = LiveTrack.CREDENTIAL_POLICY_BASELINE.value
        driver_id = HEX_A
        nonce = HEX_B
        start = {
            "sequence": 1,
            "event": "driver_start_intent",
            "details": {
                "readiness_nonce": nonce,
                "track": track,
                "driver_id": driver_id,
            },
        }

        prestart = local_envoy_module._driver_recovery_authority(
            [], track, driver_id
        )
        self.assertEqual(prestart["phase"], "pre_start")
        self.assertEqual(prestart["allowed_states"], ("created",))
        self.assertTrue(prestart["request_eligible"])

        for observed_state in ("created", "running", "exited", "dead"):
            with self.subTest(observed_state=observed_state):
                ambiguous = local_envoy_module._driver_recovery_authority(
                    [start], track, driver_id
                )
                self.assertEqual(ambiguous["phase"], "ambiguous")
                self.assertIn(observed_state, ambiguous["allowed_states"])
                self.assertFalse(ambiguous["request_eligible"])

        synthetic_failure = {
            "sequence": 2,
            "event": "request_send_failed",
            "details": {"track": track, "record_sha256": None},
        }
        still_ambiguous = local_envoy_module._driver_recovery_authority(
            [start, synthetic_failure], track, driver_id
        )
        self.assertEqual(still_ambiguous["phase"], "ambiguous")
        self.assertFalse(still_ambiguous["request_eligible"])

        result = {
            "sequence": 2,
            "event": "driver_result_persisted",
            "details": {
                "readiness_nonce": nonce,
                "track": track,
                "driver_id": driver_id,
                "intent_id": HEX_C,
                "driver_definition_sha256": HEX_A,
                "result_sha256": HEX_B,
            },
        }
        result_without_request_terminal = (
            local_envoy_module._driver_recovery_authority(
                [start, result], track, driver_id
            )
        )
        self.assertEqual(result_without_request_terminal["phase"], "ambiguous")
        self.assertFalse(result_without_request_terminal["request_eligible"])

        terminal = local_envoy_module._driver_recovery_authority(
            [
                start,
                result,
                {
                    "sequence": 3,
                    "event": "request_send_complete",
                    "details": {"track": track, "record_sha256": HEX_C},
                },
            ],
            track,
            driver_id,
        )
        self.assertEqual(terminal["phase"], "trusted_terminal")
        self.assertEqual(terminal["allowed_states"], ("dead", "exited"))
        self.assertTrue(terminal["request_eligible"])

    def test_driver_recovery_authority_rejects_identity_drift_and_duplicate_intent(self):
        track = LiveTrack.SIGNED_STATE_ONLY.value
        base = {
            "readiness_nonce": HEX_B,
            "track": track,
            "driver_id": HEX_A,
        }
        for events in (
            [
                {"sequence": 1, "event": "driver_start_intent", "details": base},
                {
                    "sequence": 2,
                    "event": "driver_start_intent",
                    "details": base,
                },
            ],
            [
                {"sequence": 1, "event": "driver_start_intent", "details": base},
                {
                    "sequence": 2,
                    "event": "readiness_cancel_complete",
                    "details": {
                        **base,
                        "driver_id": HEX_C,
                        "exit_code": 0,
                    },
                },
            ],
            [
                {"sequence": 1, "event": "driver_start_intent", "details": base},
                {
                    "sequence": 2,
                    "event": "driver_result_persisted",
                    "details": {
                        **base,
                        "readiness_nonce": HEX_C,
                        "intent_id": HEX_A,
                        "driver_definition_sha256": HEX_B,
                        "result_sha256": HEX_C,
                    },
                },
            ],
        ):
            with self.subTest(events=events):
                with self.assertRaisesRegex(ControllerError, "driver|identity|intent"):
                    local_envoy_module._driver_recovery_authority(
                        events, track, HEX_A
                    )

    def test_driver_stop_recovery_is_exact_and_idempotent_at_crash_boundaries(self):
        track = LiveTrack.CREDENTIAL_POLICY_BASELINE.value

        for boundary, before_state, after_state, prior_history, stop_count in (
            ("intent_before_stop", "running", "exited", "stop_pending", 1),
            ("physical_stop_before_complete", "exited", "exited", "stop_pending", 0),
            ("cleanup_client_only", "running", "exited", "cleanup_complete", 1),
            ("complete_but_running", "running", "running", "stop_complete", 0),
        ):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "repo"
                profile = root / "deploy/kind/v3b-profile.json"
                profile.parent.mkdir(parents=True)
                profile.write_bytes(
                    (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
                )

                class CrashBoundaryController(LocalEnvoyController):
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, **kwargs)
                        self.commands = []

                    def _execute(self, argv, *, timeout_s, docker=False):
                        self.commands.append(list(argv))
                        return CommandResult(0, "", "")

                    def _inspect_container(
                        self,
                        identifier,
                        manifest_value,
                        role,
                        track_value,
                        *,
                        require_running=True,
                        envoy_attachment=None,
                        allowed_driver_states=None,
                    ):
                        current = json.loads(json.dumps(item))
                        current["runtime_attestation"]["state"] = after_state
                        return current

                controller = CrashBoundaryController(
                    root,
                    FakeRunner(),
                    home=Path(directory) / "home",
                    port_probe=lambda port: False,
                    tool_verifier=lambda: TOOL_IDENTITIES,
                )
                controller._prepare_private_roots()
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
                    "readiness_session_started",
                    {"readiness_nonce": HEX_B},
                )
                identity = {
                    "readiness_nonce": HEX_B,
                    "track": track,
                    "driver_id": HEX_A,
                }
                journal_event(
                    controller.journal_path, "driver_start_intent", identity
                )
                if prior_history.startswith("stop_"):
                    journal_event(
                        controller.journal_path, "driver_stop_intent", identity
                    )
                if prior_history == "stop_complete":
                    journal_event(
                        controller.journal_path,
                        "driver_stop_complete",
                        identity,
                    )
                elif prior_history == "cleanup_complete":
                    journal_event(
                        controller.journal_path,
                        "driver_cleanup_intent",
                        identity,
                    )
                    journal_event(
                        controller.journal_path,
                        "driver_cleanup_complete",
                        {
                            **identity,
                            "outcome": "terminated",
                            "exit_code": -15,
                        },
                    )
                item = {
                    "id": HEX_A,
                    "name": "kil-v3b1-driver-baseline-000000000000",
                    "role": "driver",
                    "track": track,
                    "runtime_attestation": {"state": before_state},
                }

                if prior_history == "stop_complete":
                    with self.assertRaisesRegex(ControllerError, "driver|running"):
                        controller._quiesce_driver_for_teardown(item, manifest())
                else:
                    authority = controller._quiesce_driver_for_teardown(
                        item, manifest()
                    )
                    self.assertEqual(authority["phase"], "teardown_quiesced")
                    events = load_lifecycle_journal(
                        controller.journal_path
                    )["events"]
                    self.assertEqual(
                        sum(
                            event["event"] == "driver_stop_intent"
                            for event in events
                        ),
                        1,
                    )
                    self.assertEqual(
                        sum(
                            event["event"] == "driver_stop_complete"
                            for event in events
                        ),
                        1,
                    )

                stop_commands = [
                    command
                    for command in controller.commands
                    if len(command) > 5 and command[5] == "stop"
                ]
                self.assertEqual(len(stop_commands), stop_count)
                if stop_commands:
                    self.assertEqual(stop_commands[0][-1], HEX_A)
                forbidden = {"start", "restart", "attach", "exec", "create"}
                self.assertFalse(
                    any(forbidden.intersection(command) for command in controller.commands)
                )

    def test_stranded_request_intents_close_conservatively_without_replay(self):
        for instruction_intent, expected_stage, expected_bytes in (
            (False, "instruction_write", False),
            (True, "termination", True),
        ):
            with self.subTest(instruction_intent=instruction_intent), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "repo"
                profile = root / "deploy/kind/v3b-profile.json"
                profile.parent.mkdir(parents=True)
                profile.write_bytes(
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
                    "readiness_session_started",
                    {"readiness_nonce": HEX_B},
                )
                driver_ids = ("d" * 64, "e" * 64, "f" * 64)
                for live_track, driver_id in zip(
                    LiveTrack, driver_ids, strict=True
                ):
                    identity = {
                        "readiness_nonce": HEX_B,
                        "track": live_track.value,
                        "driver_id": driver_id,
                    }
                    journal_event(
                        controller.journal_path,
                        "driver_start_intent",
                        identity,
                    )
                    journal_event(
                        controller.journal_path,
                        "driver_start_complete",
                        identity,
                    )
                    journal_event(
                        controller.journal_path,
                        "driver_readiness_complete",
                        {**identity, "record_sha256": HEX_C},
                    )
                journal_event(
                    controller.journal_path,
                    "driver_readiness_set_complete",
                    {
                        "readiness_nonce": HEX_B,
                        "tracks": [track.value for track in LiveTrack],
                        "complete_monotonic_ns": 1,
                    },
                )
                selected = LiveTrack.CREDENTIAL_POLICY_BASELINE
                intent = claim_request_attempt(
                    controller.journal_path,
                    selected,
                    readiness_nonce=HEX_B,
                )
                if instruction_intent:
                    journal_event(
                        controller.journal_path,
                        "driver_instruction_write_intent",
                        {
                            "readiness_nonce": HEX_B,
                            "track": selected.value,
                            "driver_id": driver_ids[0],
                            "intent_id": intent["intent_id"],
                        },
                    )

                self.assertTrue(
                    controller._close_stranded_request_intents(manifest())
                )
                loaded = load_lifecycle_journal(controller.journal_path)
                self.assertEqual(
                    loaded["requests"][selected.value]["status"], "failed"
                )
                failure = next(
                    event
                    for event in loaded["events"]
                    if event["event"] == "request_send_failed"
                )
                provenance = failure["details"]["provenance"]
                self.assertEqual(provenance["stage"], expected_stage)
                self.assertIs(
                    provenance["request_bytes_may_have_been_sent"],
                    expected_bytes,
                )

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
                        "ports": (18080, 18081, 18082),
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
                        "name": "kil-v3b1-backend-credential-policy-baseline-aaaaaaaaaaaa",
                    }
                elif phase == "container_create":
                    details = {
                        "name": "kil-v3b1-authz-credential-policy-baseline-aaaaaaaaaaaa"
                    }
                elif phase == "container_stop":
                    details = {
                        "id": HEX_A,
                        "name": "kil-v3b1-authz-credential-policy-baseline-aaaaaaaaaaaa",
                        "role": "authz",
                    }
                    journal_event(
                        journal,
                        "container_create_intent",
                        {"name": details["name"]},
                    )
                    journal_event(
                        journal,
                        "container_create_complete",
                        {"id": details["id"], "name": details["name"]},
                    )
                elif phase == "network_create":
                    details = {
                        "name": "kil-v3b1-backend-credential-policy-baseline-aaaaaaaaaaaa"
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
    def _make_complete_down_controller(
        self, directory, *, lifecycle="trusted", suppress_absence=False
    ):
        root = Path(directory) / "repo"
        profile_path = root / "deploy/kind/v3b-profile.json"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_bytes(
            (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
        )

        class CompleteDownController(LocalEnvoyController):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.commands = []
                self.deleted = False
                self.removed_ids = set()
                self.live_objects = {}
                self.validators = {}
                self.networks = {}
                self.payloads = {}
                self.driver_inspections = []
                self.first_envoy_stop_inspection_count = None
                self.bound_manifest = None

            @staticmethod
            def _copy(value):
                return json.loads(json.dumps(value))

            def _remaining_objects(self):
                return [
                    self._copy(item)
                    for identifier, item in self.live_objects.items()
                    if identifier not in self.removed_ids
                ]

            def _remaining_validators(self):
                return [
                    self._copy(item)
                    for identifier, item in self.validators.items()
                    if identifier not in self.removed_ids
                ]

            def _remaining_networks(self):
                return [
                    self._copy(item)
                    for identifier, item in self.networks.items()
                    if identifier not in self.removed_ids
                ]

            def _execute(self, argv, *, timeout_s, docker=False):
                command = list(argv)
                self.commands.append(command)
                if command[:3] == ["colima", "list", "--json"]:
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
                if command[:2] == ["colima", "delete"]:
                    self.deleted = True
                    return CommandResult(0, "", "")
                if "context" in command and "show" in command:
                    return CommandResult(0, "personal\n", "")
                if len(command) > 5 and command[5] == "ps":
                    records = [*self._remaining_objects(), *self._remaining_validators()]
                    return CommandResult(
                        0,
                        "".join(
                            canonical_json({"id": item["id"], "name": item["name"]})
                            + "\n"
                            for item in records
                        ),
                        "",
                    )
                if len(command) > 6 and command[5:7] == ["network", "ls"]:
                    return CommandResult(
                        0,
                        "".join(
                            canonical_json({"id": item["id"], "name": item["name"]})
                            + "\n"
                            for item in self._remaining_networks()
                        ),
                        "",
                    )
                if len(command) > 5 and command[5] == "inspect":
                    identifier = command[-1]
                    item = self.live_objects.get(identifier) or self.validators.get(identifier)
                    running = (
                        item is not None
                        and item["runtime_attestation"]["state"] == "running"
                    )
                    return CommandResult(0, ("true" if running else "false") + "\n", "")
                if len(command) > 5 and command[5] == "stop":
                    identifier = command[-1]
                    item = self.live_objects.get(identifier)
                    if item is None:
                        item = self.validators.get(identifier)
                    if item is None:
                        raise ControllerError("stop identity is unknown")
                    if item.get("role") == "envoy" and self.first_envoy_stop_inspection_count is None:
                        self.first_envoy_stop_inspection_count = len(self.driver_inspections)
                    item["runtime_attestation"]["state"] = "exited"
                    return CommandResult(0, identifier + "\n", "")
                if len(command) > 5 and command[5] == "logs":
                    item = self.live_objects[command[-1]]
                    return CommandResult(
                        0,
                        self.payloads[(item["track"], "envoy_access")].decode(),
                        "",
                    )
                if len(command) > 5 and command[5] == "exec":
                    identifier = command[command.index("exec") + 1]
                    item = self.live_objects[identifier]
                    source = (
                        "authz_decisions" if item["role"] == "authz" else "target_markers"
                    )
                    payload = self.payloads[(item["track"], source)]
                    if "payload_hex" in command[command.index("-c") + 1]:
                        result = {
                            "byte_count": len(payload),
                            "payload_hex": payload.hex(),
                            "sha256": sha256(payload).hexdigest(),
                        }
                    else:
                        result = {
                            "exists": True,
                            "regular_file": True,
                            "byte_count": len(payload),
                            "sha256": sha256(payload).hexdigest(),
                        }
                    return CommandResult(0, canonical_json(result) + "\n", "")
                if len(command) > 5 and command[5] == "cp":
                    source_spec = command[-2]
                    identifier = source_spec.split(":", 1)[0]
                    item = self.live_objects[identifier]
                    source = (
                        "authz_decisions" if item["role"] == "authz" else "target_markers"
                    )
                    Path(command[-1]).write_bytes(
                        self.payloads[(item["track"], source)]
                    )
                    return CommandResult(0, "", "")
                if len(command) > 5 and command[5] == "rm":
                    self.removed_ids.add(command[-1])
                    return CommandResult(0, command[-1] + "\n", "")
                if len(command) > 6 and command[5:7] == ["network", "rm"]:
                    self.removed_ids.add(command[-1])
                    return CommandResult(0, command[-1] + "\n", "")
                return CommandResult(0, "", "")

            def _attest_colima_after_start(self, execution_nonce=None):
                return {"test_attestation": True}

            def _inspect_container(
                self,
                identifier,
                manifest_value,
                role,
                track,
                *,
                require_running=True,
                envoy_attachment=None,
                allowed_driver_states=None,
            ):
                item = self.live_objects.get(identifier)
                if item is None or item["role"] != role or item["track"] != track:
                    raise ControllerError("complete runtime container identity changed")
                if role == "driver":
                    self.driver_inspections.append(identifier)
                    allowed = (
                        {"created"}
                        if allowed_driver_states is None
                        else set(allowed_driver_states)
                    )
                    if item["runtime_attestation"]["state"] not in allowed:
                        raise ControllerError("complete runtime driver state changed")
                return self._copy(item)

            def _inspect_validation_container(self, identifier, manifest_value, track):
                item = self.validators.get(identifier)
                if item is None or item["track"] != track.value:
                    raise ControllerError("complete validator identity changed")
                return self._copy(item)

            def _inspect_network(
                self,
                identifier,
                manifest_value,
                track,
                *,
                segment="backend",
                expected_members=None,
                require_empty_membership=False,
                **kwargs,
            ):
                item = self.networks.get(identifier)
                if item is None or item["track"] != track or item["segment"] != segment:
                    raise ControllerError("complete network identity changed")
                remaining = self._remaining_objects()
                owned = local_envoy_module._network_member_identities(
                    remaining, track, segment
                )
                states = {
                    item["id"]: item["runtime_attestation"]["state"]
                    for item in remaining
                }
                physical = {
                    object_id: identity
                    for object_id, identity in owned.items()
                    if states[object_id] == "running"
                }
                if expected_members != physical or (
                    require_empty_membership and physical
                ):
                    raise ControllerError("complete network membership changed")
                return self._copy(item)

            def _load_for_down(self):
                objects = self._remaining_objects()
                for item in objects:
                    if item["role"] == "driver":
                        events = load_lifecycle_journal(self.journal_path)["events"]
                        authority = local_envoy_module._driver_recovery_authority(
                            events, item["track"], item["id"]
                        )
                        self._inspect_container(
                            item["id"],
                            self.bound_manifest,
                            "driver",
                            item["track"],
                            require_running=False,
                            allowed_driver_states=set(authority["allowed_states"]),
                        )
                state = {
                    "objects": objects,
                    "transient_objects": self._remaining_validators(),
                    "network_objects": self._remaining_networks(),
                    "profile_created": True,
                    "colima_profile": "kil-v3-lab",
                    "docker_host": self.docker_host,
                    "docker_config": str(self.docker_config),
                    "envoy_attachments": local_envoy_module._envoy_attachment_expectations(
                        load_lifecycle_journal(self.journal_path)["events"],
                        self.bound_manifest,
                    ),
                }
                return state, self.bound_manifest, load_lifecycle_journal(self.journal_path)

            if suppress_absence:
                def _attest_complete_topology_absence(self, manifest_value):
                    return None

        controller = CompleteDownController(
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
        controller.bound_manifest = value
        private_manifest = controller.private_root / "manifests/run.json"
        private_manifest.write_text(canonical_json(value) + "\n")
        persist_active_state(controller.state_path, private_manifest, value)
        bound = load_bound_active_state(controller.state_path)
        controller.live_objects = {
            item["id"]: controller._copy(item) for item in bound["objects"]
        }
        controller.networks = {
            item["id"]: controller._copy(item) for item in bound["network_objects"]
        }
        validators = []
        for track, character in zip(LiveTrack, ("d", "e", "f"), strict=True):
            validators.append(
                {
                    "id": character * 64,
                    "name": (
                        f"kil-v3b1-validate-{track.value.replace('_', '-')}-"
                        f"{str(value['content_identity_sha256'])[:12]}"
                    ),
                    "role": "validator",
                    "track": track.value,
                    "labels": local_envoy_module._object_labels(
                        value["run_id"], "validator", track.value
                    ),
                    "image_id": value["envoy_image_id"],
                    "image_reference": value["envoy_image_digest"],
                    "runtime_attestation": {
                        "privileged": False,
                        "network_mode": "none",
                        "pid_mode": "",
                        "ipc_mode": "",
                        "uts_mode": "",
                        "userns_mode": "",
                        "cgroupns_mode": "private",
                        "state": "exited",
                        "entrypoint": ["/usr/local/bin/envoy"],
                        "command": [
                            "--mode", "validate", "--config-path", "/etc/envoy/envoy.json",
                            "--disable-hot-restart", "--concurrency", 1,
                        ],
                        "mounts": [
                            {
                                "source": f"/private/{track.value}/envoy.json",
                                "destination": "/etc/envoy/envoy.json",
                                "rw": False,
                            }
                        ],
                        "networks": {},
                        "port_bindings": {},
                        "published_ports": None,
                    },
                }
            )
        controller.validators = {
            item["id"]: controller._copy(item) for item in validators
        }

        requests = []
        digests = {
            LiveTrack.CREDENTIAL_POLICY_BASELINE: "1" * 64,
            LiveTrack.SIGNED_STATE_ONLY: "2" * 64,
            LiveTrack.SIGNED_PLUS_LOCAL_REDUCE: "3" * 64,
        }
        driver_by_track = {
            item["track"]: item
            for item in controller.live_objects.values()
            if item["role"] == "driver"
        }
        for track in LiveTrack:
            requests.append(
                request_record(
                    value,
                    track,
                    driver_full_id=driver_by_track[track.value]["id"],
                )
            )
            denied = track is LiveTrack.SIGNED_PLUS_LOCAL_REDUCE
            status = 403 if denied else 200
            outcome = "deny" if denied else "permit"
            upstream = "-" if denied else "10.0.0.2:8080"
            controller.payloads[(track.value, "authz_decisions")] = (
                canonical_json(
                    decision_record(
                        value, track, status=status, outcome=outcome, digest=digests[track]
                    )
                )
                + "\n"
            ).encode()
            controller.payloads[(track.value, "envoy_access")] = (
                canonical_json(
                    envoy_record(
                        value, track, status=status, upstream=upstream, digest=digests[track]
                    )
                )
                + "\n"
            ).encode()
            target = (
                [] if denied else [target_record(value, track, digests[track])]
            )
            controller.payloads[(track.value, "target_markers")] = b"".join(
                (canonical_json(item) + "\n").encode() for item in target
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
        journal_event(
            controller.journal_path,
            "preflight_complete",
            {
                "tool_identities": TOOL_IDENTITIES,
                "ports": [18080, 18081, 18082],
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
        _bind_journal_manifest(controller.journal_path, private_manifest, value)
        for item in bound["network_objects"]:
            journal_event(controller.journal_path, "network_create_intent", {"name": item["name"]})
            journal_event(
                controller.journal_path,
                "network_create_complete",
                {"id": item["id"], "name": item["name"]},
            )
        for item in bound["objects"]:
            journal_event(controller.journal_path, "container_create_intent", {"name": item["name"]})
            journal_event(
                controller.journal_path,
                "container_create_complete",
                {"id": item["id"], "name": item["name"]},
            )
        for item in validators:
            identity = {"id": item["id"], "name": item["name"]}
            journal_event(controller.journal_path, "validator_create_intent", {"name": item["name"]})
            journal_event(controller.journal_path, "validator_create_complete", identity)
            journal_event(controller.journal_path, "config_validate_intent", identity)
            journal_event(controller.journal_path, "config_validate_complete", identity)
        for track in LiveTrack:
            track_value = local_envoy_module._track_manifest(value, track)
            envoy = next(
                item
                for item in bound["objects"]
                if item["track"] == track.value and item["role"] == "envoy"
            )
            frontend = next(
                item
                for item in bound["network_objects"]
                if item["track"] == track.value and item["segment"] == "frontend"
            )
            details = {
                "container_id": envoy["id"],
                "container_name": track_value["envoy_container"],
                "network_id": frontend["id"],
                "network_name": track_value["frontend_network"],
                "alias": "envoy",
            }
            journal_event(controller.journal_path, "network_connect_intent", details)
            journal_event(controller.journal_path, "network_connect_complete", details)
        journal_event(
            controller.journal_path,
            "up_complete",
            {
                "state_path": str(controller.state_path),
                "state_sha256": sha256(controller.state_path.read_bytes()).hexdigest(),
            },
        )

        journal_event(
            controller.journal_path,
            "readiness_session_started",
            {"readiness_nonce": HEX_B},
        )
        if lifecycle == "trusted":
            raw_results = driver_results_for_requests(requests)
            for track in LiveTrack:
                driver = driver_by_track[track.value]
                identity = {
                    "readiness_nonce": HEX_B,
                    "track": track.value,
                    "driver_id": driver["id"],
                }
                journal_event(controller.journal_path, "driver_start_intent", identity)
                journal_event(controller.journal_path, "driver_start_complete", identity)
                journal_event(
                    controller.journal_path,
                    "driver_readiness_complete",
                    {**identity, "record_sha256": HEX_C},
                )
                driver["runtime_attestation"]["state"] = "exited"
            journal_event(
                controller.journal_path,
                "driver_readiness_set_complete",
                {
                    "readiness_nonce": HEX_B,
                    "tracks": [track.value for track in LiveTrack],
                    "complete_monotonic_ns": 1,
                },
            )
            request_path = _runtime_root(root, value) / "requests.jsonl"
            request_path.parent.mkdir(parents=True, exist_ok=True)
            request_path.write_bytes(
                b"".join((canonical_json(record) + "\n").encode() for record in requests)
            )
            result_root = controller.private_root / "driver-results" / value["run_id"]
            result_root.mkdir(parents=True)
            for track, request in zip(LiveTrack, requests, strict=True):
                driver = driver_by_track[track.value]
                intent = claim_request_attempt(
                    controller.journal_path, track, readiness_nonce=HEX_B
                )
                identity = {
                    "readiness_nonce": HEX_B,
                    "track": track.value,
                    "driver_id": driver["id"],
                    "intent_id": intent["intent_id"],
                }
                journal_event(
                    controller.journal_path, "driver_instruction_write_intent", identity
                )
                definition = next(
                    item for item in value["driver_definitions"] if item["track"] == track.value
                )
                payload = raw_results[track]
                journal_event(
                    controller.journal_path,
                    "driver_result_persisted",
                    {
                        **identity,
                        "driver_definition_sha256": sha256(
                            (canonical_json(definition) + "\n").encode()
                        ).hexdigest(),
                        "result_sha256": sha256(payload).hexdigest(),
                    },
                )
                path = result_root / f"{track.value}.json"
                path.write_bytes(payload)
                path.chmod(0o600)
                record_sha = sha256((canonical_json(request) + "\n").encode()).hexdigest()
                journal_event(
                    controller.journal_path,
                    "request_record_persisted",
                    {
                        "track": track.value,
                        "intent_id": intent["intent_id"],
                        "record_sha256": record_sha,
                    },
                )
                _complete_request_attempt(
                    controller.journal_path,
                    track,
                    success=True,
                    record_sha256=record_sha,
                )
        else:
            for track in LiveTrack:
                driver = driver_by_track[track.value]
                journal_event(
                    controller.journal_path,
                    "driver_start_intent",
                    {
                        "readiness_nonce": HEX_B,
                        "track": track.value,
                        "driver_id": driver["id"],
                    },
                )
                driver["runtime_attestation"]["state"] = "running"
            controller.payloads = {key: b"" for key in controller.payloads}

        return controller, value, bound, validators

    def test_complete_down_orders_driver_proof_freeze_15_by_6_absence_and_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, value, bound, validators = self._make_complete_down_controller(
                directory
            )
            published = controller.down()

            archived = load_lifecycle_journal(
                controller._private_completed_root()
                / f"{value['run_id']}.journal.json"
            )
            events = archived["events"]
            first_envoy_stop = min(
                event["sequence"]
                for event in events
                if event["event"] == "container_stop_intent"
                and event["details"]["role"] == "envoy"
            )
            first_source = min(
                event["sequence"]
                for event in events
                if event["event"] == "source_collection_intent"
            )
            driver_terminals = [
                event
                for event in events
                if event["event"] == "driver_result_persisted"
            ]
            self.assertEqual(len(driver_terminals), 3)
            self.assertLess(max(event["sequence"] for event in driver_terminals), first_envoy_stop)
            self.assertLess(max(event["sequence"] for event in driver_terminals), first_source)
            self.assertEqual(controller.first_envoy_stop_inspection_count, 3)
            self.assertEqual(len(set(controller.driver_inspections[:3])), 3)

            removal_ids = [
                command[-1]
                for command in controller.commands
                if len(command) > 5 and command[5] == "rm"
            ]
            expected_removals = [
                item["id"]
                for role in ("driver", "envoy", "authz", "target")
                for item in bound["objects"]
                if item["role"] == role
            ] + [item["id"] for item in validators]
            self.assertEqual(removal_ids, expected_removals)
            network_removals = [
                command[-1]
                for command in controller.commands
                if len(command) > 6 and command[5:7] == ["network", "rm"]
            ]
            self.assertEqual(
                network_removals, [item["id"] for item in bound["network_objects"]]
            )
            absence = next(
                event for event in events if event["event"] == "topology_absence_attested"
            )
            publication = next(
                event for event in events if event["event"] == "publication_intent"
            )
            self.assertLess(absence["sequence"], publication["sequence"])
            self.assertEqual(absence["details"]["container_count"], 15)
            self.assertEqual(absence["details"]["network_count"], 6)
            container_identities = [
                {"id": item["id"], "name": item["name"]}
                for item in [*bound["objects"], *validators]
            ]
            network_identities = [
                {"id": item["id"], "name": item["name"]}
                for item in bound["network_objects"]
            ]
            self.assertEqual(
                absence["details"]["container_identity_sha256"],
                sha256(
                    canonical_json(
                        sorted(container_identities, key=lambda item: (item["name"], item["id"]))
                    ).encode()
                ).hexdigest(),
            )
            self.assertEqual(
                absence["details"]["network_identity_sha256"],
                sha256(
                    canonical_json(
                        sorted(network_identities, key=lambda item: (item["name"], item["id"]))
                    ).encode()
                ).hexdigest(),
            )
            self.assertTrue(json.loads((published / "manifest.json").read_text())["run_complete"])

    def test_complete_down_retries_driver_stop_and_absence_crash_boundaries(self):
        for crash_stage in ("driver_stop_complete", "topology_absence_attested"):
            lifecycle = "ambiguous" if crash_stage == "driver_stop_complete" else "trusted"
            with self.subTest(crash_stage=crash_stage), tempfile.TemporaryDirectory() as directory:
                controller, value, _, _ = self._make_complete_down_controller(
                    directory, lifecycle=lifecycle
                )
                original_event = journal_event
                crashed = False

                def crash_once(path, event, details):
                    nonlocal crashed
                    if event == crash_stage and not crashed:
                        crashed = True
                        if event == "topology_absence_attested":
                            original_event(path, event, details)
                        raise ControllerError(f"injected {crash_stage} crash")
                    return original_event(path, event, details)

                with mock.patch(
                    "tools.v3b1_local_envoy.journal_event", side_effect=crash_once
                ):
                    with self.assertRaisesRegex(ControllerError, "injected"):
                        controller.down()
                interrupted = load_lifecycle_journal(controller.journal_path)
                self.assertFalse(
                    any(event["event"] == "publication_intent" for event in interrupted["events"])
                )

                published = controller.down()
                archived = load_lifecycle_journal(
                    controller._private_completed_root()
                    / f"{value['run_id']}.journal.json"
                )
                if crash_stage == "driver_stop_complete":
                    stop_intents = [
                        event
                        for event in archived["events"]
                        if event["event"] == "driver_stop_intent"
                    ]
                    stop_completes = [
                        event
                        for event in archived["events"]
                        if event["event"] == "driver_stop_complete"
                    ]
                    self.assertEqual(len(stop_intents), 3)
                    self.assertEqual(len(stop_completes), 3)
                    driver_ids = {event["details"]["driver_id"] for event in stop_intents}
                    stop_commands = [
                        command
                        for command in controller.commands
                        if len(command) > 5
                        and command[5] == "stop"
                        and command[-1] in driver_ids
                    ]
                    self.assertEqual(len(stop_commands), 3)
                else:
                    self.assertEqual(
                        len(
                            [
                                event
                                for event in archived["events"]
                                if event["event"] == "topology_absence_attested"
                            ]
                        ),
                        1,
                    )
                self.assertFalse(
                    json.loads((published / "manifest.json").read_text()).get(
                        "promotion_status"
                    )
                    == "pending"
                )

    def test_complete_publication_requires_durable_15_by_6_absence_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, value, _, _ = self._make_complete_down_controller(
                directory, suppress_absence=True
            )
            with self.assertRaisesRegex(
                ControllerError, "topology|absence|publication"
            ):
                controller.down()
            journal = load_lifecycle_journal(controller.journal_path)
            self.assertFalse(
                any(event["event"] == "publication_intent" for event in journal["events"])
            )
            with self.assertRaisesRegex(
                ControllerError, "topology|absence|publication"
            ):
                controller.down()
            journal = load_lifecycle_journal(controller.journal_path)
            self.assertFalse(
                any(event["event"] == "publication_intent" for event in journal["events"])
            )
            self.assertFalse(
                (controller.evidence_root / str(value["run_id"])).exists()
            )
            self.assertTrue(controller.journal_path.exists())
            self.assertTrue(controller.state_path.exists())

    def test_post_delete_renamed_publication_requires_exact_15_by_6_absence_proof(self):
        class PublicationCrash(BaseException):
            pass

        for mutation in ("missing", "mismatched"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                controller, value, _, _ = self._make_complete_down_controller(
                    directory
                )

                def crash_after_rename(stage, _path):
                    if stage == "after_atomic_rename":
                        raise PublicationCrash()

                controller.publication_fault = crash_after_rename
                with self.assertRaises(PublicationCrash):
                    controller.down()
                controller.publication_fault = None
                published = controller.evidence_root / str(value["run_id"])
                self.assertTrue(published.is_dir())

                journal = load_lifecycle_journal(controller.journal_path)
                absence = next(
                    event
                    for event in journal["events"]
                    if event["event"] == "topology_absence_attested"
                )
                if mutation == "missing":
                    journal["events"].remove(absence)
                    for sequence, event in enumerate(journal["events"], start=1):
                        event["sequence"] = sequence
                else:
                    absence["details"]["container_identity_sha256"] = "0" * 64
                _persist_journal(controller.journal_path, journal)

                with self.assertRaisesRegex(
                    ControllerError, "topology|absence|publication"
                ):
                    controller.down()

                retained = load_lifecycle_journal(controller.journal_path)
                self.assertFalse(
                    any(
                        event["event"] == "publication_complete"
                        for event in retained["events"]
                    )
                )
                self.assertTrue(controller.journal_path.exists())
                self.assertTrue(controller.state_path.exists())
                self.assertTrue(published.is_dir())

    def test_post_delete_retry_reconstructs_15_by_6_proof_after_state_unlink_crash(self):
        class CleanupCrash(BaseException):
            pass

        with tempfile.TemporaryDirectory() as directory:
            controller, value, _, _ = self._make_complete_down_controller(directory)
            original_rename = os.rename
            crashed = False

            def crash_between_state_unlink_and_journal_archive(source, destination, *args, **kwargs):
                nonlocal crashed
                if Path(source) == controller.journal_path and not crashed:
                    crashed = True
                    self.assertFalse(controller.state_path.exists())
                    raise CleanupCrash()
                return original_rename(source, destination, *args, **kwargs)

            with mock.patch(
                "tools.v3b1_local_envoy.os.rename",
                side_effect=crash_between_state_unlink_and_journal_archive,
            ), self.assertRaises(CleanupCrash):
                controller.down()

            published = controller.evidence_root / str(value["run_id"])
            self.assertTrue(published.is_dir())
            self.assertTrue(controller.journal_path.exists())
            self.assertFalse(controller.state_path.exists())

            recovered = controller.down()

            self.assertEqual(recovered, published)
            self.assertFalse(controller.journal_path.exists())
            self.assertFalse(controller.state_path.exists())
            archived = load_lifecycle_journal(
                controller._private_completed_root()
                / f"{value['run_id']}.journal.json"
            )
            self.assertEqual(
                len(
                    [
                        event
                        for event in archived["events"]
                        if event["event"] == "topology_absence_attested"
                    ]
                ),
                1,
            )
            self.assertEqual(
                len(
                    [
                        event
                        for event in archived["events"]
                        if event["event"] == "publication_complete"
                    ]
                ),
                1,
            )
            self.assertTrue(
                json.loads((published / "manifest.json").read_text())["run_complete"]
            )

    def test_real_partial_up_driver_survivor_is_exact_nonpromotable_and_never_restarted(self):
        def make_controller(directory, *, mutation=None, replacement=False, started=False):
            root = Path(directory) / "repo"
            profile_path = root / "deploy/kind/v3b-profile.json"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )

            class PartialDriverController(LocalEnvoyController):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.commands = []
                    self.removed_ids = set()
                    self.deleted = False
                    self.expected_driver = None
                    self.live_driver = None
                    self.frontend = None
                    self.member_attestations = []

                def _execute(self, argv, *, timeout_s, docker=False):
                    command = list(argv)
                    self.commands.append(command)
                    if command[:3] == ["colima", "list", "--json"]:
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
                    if command[:2] == ["colima", "delete"]:
                        self.deleted = True
                        return CommandResult(0, "", "")
                    if "context" in command and "show" in command:
                        return CommandResult(0, "personal\n", "")
                    if len(command) > 5 and command[5] == "ps":
                        if self.expected_driver["id"] in self.removed_ids:
                            return CommandResult(0, "", "")
                        object_id = (
                            HEX_C if replacement else self.expected_driver["id"]
                        )
                        return CommandResult(
                            0,
                            canonical_json(
                                {
                                    "id": object_id,
                                    "name": self.expected_driver["name"],
                                }
                            )
                            + "\n",
                            "",
                        )
                    if len(command) > 6 and command[5:7] == ["network", "ls"]:
                        if self.frontend["id"] in self.removed_ids:
                            return CommandResult(0, "", "")
                        return CommandResult(
                            0,
                            canonical_json(
                                {"id": self.frontend["id"], "name": self.frontend["name"]}
                            )
                            + "\n",
                            "",
                        )
                    if len(command) > 5 and command[5] == "rm":
                        self.removed_ids.add(command[-1])
                        return CommandResult(0, command[-1] + "\n", "")
                    if len(command) > 6 and command[5:7] == ["network", "rm"]:
                        self.removed_ids.add(command[-1])
                        return CommandResult(0, command[-1] + "\n", "")
                    return CommandResult(0, "", "")

                def _attest_colima_after_start(self, execution_nonce=None):
                    return {"test_attestation": True}

                def _inspect_container(
                    self,
                    identifier,
                    manifest_value,
                    role,
                    track,
                    *,
                    require_running=True,
                    envoy_attachment=None,
                    allowed_driver_states=None,
                ):
                    if identifier != self.expected_driver["id"] or role != "driver":
                        raise ControllerError("partial driver identity changed")
                    allowed = (
                        {"created"}
                        if allowed_driver_states is None
                        else set(allowed_driver_states)
                    )
                    if not local_envoy_module._container_attestation_matches(
                        self.expected_driver,
                        self.live_driver,
                        allow_stopped=True,
                        allowed_driver_states=allowed,
                    ):
                        raise ControllerError("partial driver immutable attestation changed")
                    return json.loads(json.dumps(self.live_driver))

                def _inspect_network(
                    self,
                    identifier,
                    manifest_value,
                    track,
                    *,
                    segment="backend",
                    expected_members=None,
                    **kwargs,
                ):
                    if (
                        identifier != self.frontend["id"]
                        or segment != "frontend"
                        or track != self.expected_driver["track"]
                    ):
                        raise ControllerError("partial frontend identity changed")
                    expected = (
                        {}
                        if (
                            self.expected_driver["id"] in self.removed_ids
                            or self.live_driver["runtime_attestation"]["state"]
                            == "created"
                        )
                        else {
                            self.expected_driver["id"]: {
                                "name": self.expected_driver["name"],
                                "role": "driver",
                            }
                        }
                    )
                    if expected_members != expected:
                        raise ControllerError("partial frontend membership changed")
                    self.member_attestations.append(json.loads(json.dumps(expected)))
                    return json.loads(json.dumps(self.frontend))

            controller = PartialDriverController(
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
            fixture_state = controller.private_root / "fixture-state.json"
            persist_active_state(fixture_state, private_manifest, value)
            complete = load_bound_active_state(fixture_state)
            driver = next(
                item
                for item in complete["objects"]
                if item["role"] == "driver"
                and item["track"] == LiveTrack.CREDENTIAL_POLICY_BASELINE.value
            )
            frontend = next(
                item
                for item in complete["network_objects"]
                if item["segment"] == "frontend"
                and item["track"] == driver["track"]
            )
            controller.expected_driver = json.loads(json.dumps(driver))
            controller.live_driver = json.loads(json.dumps(driver))
            controller.frontend = json.loads(json.dumps(frontend))
            if mutation is not None:
                mutation(controller.live_driver)

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
                    "ports": [18080, 18081, 18082],
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
            for kind, item in (("network", frontend), ("container", driver)):
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
            if started:
                journal_event(
                    controller.journal_path,
                    "readiness_session_started",
                    {"readiness_nonce": HEX_B},
                )
                journal_event(
                    controller.journal_path,
                    "driver_start_intent",
                    {
                        "readiness_nonce": HEX_B,
                        "track": driver["track"],
                        "driver_id": driver["id"],
                    },
                )
            return controller, value, driver, frontend

        for started in (False, True):
            with self.subTest(started=started), tempfile.TemporaryDirectory() as directory:
                controller, value, driver, frontend = make_controller(
                    directory, started=started
                )
                published = controller.down()

                self.assertTrue(controller.deleted)
                self.assertEqual(
                    controller.removed_ids, {driver["id"], frontend["id"]}
                )
                self.assertEqual(
                    controller.member_attestations,
                    [{}, {}, {}],
                )
                public_manifest = json.loads(
                    (published / "manifest.json").read_text()
                )
                self.assertFalse(public_manifest["run_complete"])
                self.assertEqual(
                    public_manifest["promotion_status"], "not_promoted"
                )
                archived = load_lifecycle_journal(
                    controller._private_completed_root()
                    / f"{value['run_id']}.journal.json"
                )
                rejection = next(
                    event
                    for event in archived["events"]
                    if event["event"] == "partial_up_evidence_rejected"
                )
                self.assertFalse(rejection["details"]["promotable"])
                if started:
                    stop_complete = next(
                        event
                        for event in archived["events"]
                        if event["event"] == "driver_stop_complete"
                    )
                    start = next(
                        event
                        for event in archived["events"]
                        if event["event"] == "driver_start_intent"
                    )
                    self.assertGreater(stop_complete["sequence"], start["sequence"])
                    self.assertFalse(
                        any(
                            event["sequence"] > start["sequence"]
                            and event["event"]
                            in {
                                "driver_start_intent",
                                "driver_start_complete",
                                "driver_instruction_write_intent",
                                "network_connect_intent",
                                "container_create_intent",
                            }
                            for event in archived["events"]
                        )
                    )
                    forbidden_verbs = {"start", "restart", "attach", "exec", "create"}
                    self.assertFalse(
                        any(
                            forbidden_verbs.intersection(command)
                            for command in controller.commands
                        )
                    )

        mutations = (
            ("id", lambda value: value.__setitem__("id", HEX_C)),
            ("image", lambda value: value.__setitem__("image_id", KIL_IMAGE_ID.replace("c", "b"))),
            ("labels", lambda value: value.__setitem__("labels", {})),
            ("command", lambda value: value["runtime_attestation"].__setitem__("command", ["unexpected"])),
            ("state", lambda value: value["runtime_attestation"].__setitem__("state", "running")),
            ("aliases", lambda value: value["runtime_attestation"].__setitem__("network_aliases", {})),
            ("hardening", lambda value: value["runtime_attestation"].__setitem__("privileged", True)),
            ("stdin", lambda value: value["runtime_attestation"].__setitem__("stdin_open", False)),
            ("tty", lambda value: value["runtime_attestation"].__setitem__("tty", True)),
        )
        for label, mutation in mutations:
            with self.subTest(mutation=label), tempfile.TemporaryDirectory() as directory:
                controller, _, driver, _ = make_controller(
                    directory, mutation=mutation
                )
                with self.assertRaisesRegex(
                    ControllerError, "driver|attestation|identity"
                ):
                    controller._load_for_down()
                self.assertNotIn(driver["id"], controller.removed_ids)

        with self.subTest(mutation="same_name_replacement"), tempfile.TemporaryDirectory() as directory:
            controller, _, driver, _ = make_controller(directory, replacement=True)
            with self.assertRaisesRegex(ControllerError, "identity"):
                controller._load_for_down()
            self.assertNotIn(HEX_C, controller.removed_ids)

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
                        "ports": [18080, 18081, 18082],
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
                        "ports": [18080, 18081, 18082],
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
                        "ports": [18080, 18081, 18082],
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
                for item in objects:
                    journal_event(
                        controller.journal_path,
                        "container_create_intent",
                        {"name": item["name"]},
                    )
                    journal_event(
                        controller.journal_path,
                        "container_create_complete",
                        {"id": item["id"], "name": item["name"]},
                    )
                for item in transients:
                    journal_event(
                        controller.journal_path,
                        "validator_create_intent",
                        {"name": item["name"]},
                    )
                    journal_event(
                        controller.journal_path,
                        "validator_create_complete",
                        {"id": item["id"], "name": item["name"]},
                    )
                for item in networks:
                    journal_event(
                        controller.journal_path,
                        "network_create_intent",
                        {"name": item["name"]},
                    )
                    journal_event(
                        controller.journal_path,
                        "network_create_complete",
                        {"id": item["id"], "name": item["name"]},
                    )

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
                envoy_attachment=None,
                allowed_driver_states=None,
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
            driver_root = (
                controller.private_root / "driver-results" / value["run_id"]
            )
            driver_root.mkdir(parents=True, exist_ok=True)
            for track, payload in driver_results_for_requests(requests).items():
                path = driver_root / f"{track.value}.json"
                path.write_bytes(payload)
                path.chmod(0o600)
        persist_active_state(controller.state_path, private_manifest, value)
        controller.bound_state = load_bound_active_state(controller.state_path)
        for item in controller.bound_state["objects"]:
            creation_prefix = (
                "validator" if item["role"] == "validator" else "container"
            )
            journal_event(
                controller.journal_path,
                f"{creation_prefix}_create_intent",
                {"name": item["name"]},
            )
            journal_event(
                controller.journal_path,
                f"{creation_prefix}_create_complete",
                {"id": item["id"], "name": item["name"]},
            )
        controller.running = {
            item["id"]
            for item in controller.bound_state["objects"]
            if item["role"] != "driver"
        }
        controller.alive = {
            item["id"] for item in controller.bound_state["objects"]
        }
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
                    raw_driver_results=driver_results_for_requests(requests),
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
                        self.envoy_attachment_phases = []
                        self.frontend_attachment_phases = []

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

                    def _inspect_container(
                        self,
                        identifier,
                        manifest_value,
                        role,
                        track,
                        *,
                        require_running=True,
                        envoy_attachment=None,
                        allowed_driver_states=None,
                    ):
                        if role == "envoy":
                            self.envoy_attachment_phases.append(
                                envoy_attachment["phase"]
                            )
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
                        segment="backend",
                        expected_members=None,
                        require_complete_membership=True,
                        require_empty_membership=False,
                        allowed_member_options=None,
                        envoy_attachment=None,
                    ):
                        if segment == "frontend":
                            self.frontend_attachment_phases.append(
                                envoy_attachment["phase"]
                            )
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
                for item in controller.bound_state["network_objects"]:
                    journal_event(
                        controller.journal_path,
                        "network_create_intent",
                        {"name": item["name"]},
                    )
                    journal_event(
                        controller.journal_path,
                        "network_create_complete",
                        {"id": item["id"], "name": item["name"]},
                    )
                for item in controller.bound_state["objects"]:
                    journal_event(
                        controller.journal_path,
                        "container_create_intent",
                        {"name": item["name"]},
                    )
                    journal_event(
                        controller.journal_path,
                        "container_create_complete",
                        {"id": item["id"], "name": item["name"]},
                    )
                for track in LiveTrack:
                    track_value = local_envoy_module._track_manifest(value, track)
                    envoy = next(
                        item
                        for item in controller.bound_state["objects"]
                        if item["track"] == track.value
                        and item["role"] == "envoy"
                    )
                    frontend = next(
                        item
                        for item in controller.bound_state["network_objects"]
                        if item["track"] == track.value
                        and item["segment"] == "frontend"
                    )
                    attachment = {
                        "container_id": envoy["id"],
                        "container_name": track_value["envoy_container"],
                        "network_id": frontend["id"],
                        "network_name": track_value["frontend_network"],
                        "alias": "envoy",
                    }
                    journal_event(
                        controller.journal_path,
                        "network_connect_intent",
                        attachment,
                    )
                    journal_event(
                        controller.journal_path,
                        "network_connect_complete",
                        attachment,
                    )
                requests = [request_record(value, track) for track in LiveTrack]
                controller.request_records = requests
                if failure != "no_run":
                    driver_root = (
                        controller.private_root
                        / "driver-results"
                        / value["run_id"]
                    )
                    driver_root.mkdir(parents=True, exist_ok=True)
                    for track, payload in driver_results_for_requests(
                        requests
                    ).items():
                        path = driver_root / f"{track.value}.json"
                        path.write_bytes(payload)
                        path.chmod(0o600)
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
                    20,
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
                    20,
                )
                public_manifest = json.loads(
                    (published / "manifest.json").read_text()
                )
                self.assertFalse(public_manifest["run_complete"])
                self.assertIn("failure", public_manifest["bundle_class"])
                self.assertEqual(
                    controller.envoy_attachment_phases,
                    ["complete"] * 9,
                )
                self.assertEqual(
                    controller.frontend_attachment_phases,
                    ["complete"] * 6,
                )
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
                raw_driver_results=driver_results_for_requests(requests),
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
                controller.provisional_root,
                value,
                raw_driver_results={track: b"" for track in LiveTrack},
                reset=True,
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
    def test_healthcheck_classification_accepts_closed_disabled_shapes(self):
        image_healthcheck = {
            "Test": ["CMD", "python", "-c", "raise SystemExit(0)"],
            "Interval": 10_000_000_000,
            "Timeout": 3_000_000_000,
            "StartPeriod": 5_000_000_000,
            "Retries": 3,
        }
        expanded_disabled = {
            **image_healthcheck,
            "Test": ["NONE"],
        }

        self.assertEqual(
            local_envoy_module._classify_inspected_healthcheck(
                expanded_disabled, image_healthcheck
            ),
            "disabled",
        )
        self.assertIsNone(
            local_envoy_module._classify_inspected_healthcheck(
                None, image_healthcheck
            )
        )
        self.assertEqual(
            local_envoy_module._classify_inspected_healthcheck(
                image_healthcheck, image_healthcheck
            ),
            "configured",
        )

    def test_healthcheck_classification_rejects_open_or_unbound_disabled_shapes(self):
        image_healthcheck = {
            "Test": ["CMD", "python", "-c", "raise SystemExit(0)"],
            "Interval": 10_000_000_000,
            "Timeout": 3_000_000_000,
            "StartPeriod": 5_000_000_000,
            "Retries": 3,
        }
        expanded_disabled = {
            **image_healthcheck,
            "Test": ["NONE"],
        }
        rejected = []

        missing = dict(expanded_disabled)
        missing.pop("Timeout")
        rejected.append(missing)

        extra = dict(expanded_disabled)
        extra["StartInterval"] = 1_000_000_000
        rejected.append(extra)

        changed = dict(expanded_disabled)
        changed["Interval"] = 9_000_000_000
        rejected.append(changed)

        changed_retries = dict(expanded_disabled)
        changed_retries["Retries"] = 4
        rejected.append(changed_retries)

        wrong_type = dict(expanded_disabled)
        wrong_type["Retries"] = True
        rejected.append(wrong_type)

        non_none = dict(expanded_disabled)
        non_none["Test"] = ["CMD", "false"]
        rejected.append(non_none)

        malformed_images = [
            None,
            {key: value for key, value in image_healthcheck.items() if key != "Timeout"},
            {**image_healthcheck, "Retries": True},
            {**image_healthcheck, "Test": ["NONE"]},
            {**image_healthcheck, "Unexpected": 1},
        ]

        for immutable in (image_healthcheck, None):
            with self.subTest(singleton_immutable=immutable):
                self.assertEqual(
                    local_envoy_module._classify_inspected_healthcheck(
                        {"Test": ["NONE"]}, immutable
                    ),
                    "configured",
                )

        for actual in rejected:
            with self.subTest(actual=actual):
                self.assertEqual(
                    local_envoy_module._classify_inspected_healthcheck(
                        actual, image_healthcheck
                    ),
                    "configured",
                )
        for immutable in malformed_images:
            with self.subTest(immutable=immutable):
                self.assertEqual(
                    local_envoy_module._classify_inspected_healthcheck(
                        expanded_disabled, immutable
                    ),
                    "configured",
                )

    def test_controlled_stop_comparison_allows_only_service_state_transition(self):
        value = manifest()
        service = local_envoy_module._synthetic_state_object(
            value,
            next(item for item in value["containers"] if item["role"] == "envoy"),
        )
        stopped = json.loads(json.dumps(service))
        stopped["runtime_attestation"]["state"] = "exited"
        self.assertTrue(
            local_envoy_module._container_attestation_matches(
                service, stopped, allow_stopped=True
            )
        )
        self.assertFalse(
            local_envoy_module._container_attestation_matches(
                service, stopped, allow_stopped=False
            )
        )
        tampered = json.loads(json.dumps(stopped))
        tampered["runtime_attestation"]["networks"] = []
        self.assertFalse(
            local_envoy_module._container_attestation_matches(
                service, tampered, allow_stopped=True
            )
        )
        driver = local_envoy_module._synthetic_state_object(
            value,
            next(item for item in value["containers"] if item["role"] == "driver"),
        )
        started_driver = json.loads(json.dumps(driver))
        started_driver["runtime_attestation"]["state"] = "running"
        self.assertFalse(
            local_envoy_module._container_attestation_matches(
                driver, started_driver, allow_stopped=True
            )
        )

    def test_controlled_stop_comparison_totalizes_only_unbound_exposed_port_collapse(self):
        value = manifest()
        running = local_envoy_module._synthetic_state_object(
            value,
            next(item for item in value["containers"] if item["role"] == "envoy"),
        )
        running["runtime_attestation"]["published_ports"] = {
            "10000/tcp": None,
        }
        stopped = json.loads(json.dumps(running))
        stopped["runtime_attestation"]["state"] = "exited"
        stopped["runtime_attestation"]["published_ports"] = {}

        self.assertTrue(
            local_envoy_module._container_attestation_matches(
                running, stopped, allow_stopped=True
            )
        )
        self.assertFalse(
            local_envoy_module._container_attestation_matches(
                running, stopped, allow_stopped=False
            )
        )
        for role, port in (
            ("authz", "8080/tcp"),
            ("target", "8080/tcp"),
            ("envoy", "10000/tcp"),
        ):
            with self.subTest(accepted_role=role):
                service = local_envoy_module._synthetic_state_object(
                    value,
                    next(
                        item
                        for item in value["containers"]
                        if item["role"] == role
                    ),
                )
                service["runtime_attestation"]["published_ports"] = {
                    port: None,
                }
                service_stopped = json.loads(json.dumps(service))
                service_stopped["runtime_attestation"]["state"] = "exited"
                service_stopped["runtime_attestation"]["published_ports"] = {}
                self.assertTrue(
                    local_envoy_module._container_attestation_matches(
                        service, service_stopped, allow_stopped=True
                    )
                )

        still_running = json.loads(json.dumps(stopped))
        still_running["runtime_attestation"]["state"] = "running"
        bound_before_stop = json.loads(json.dumps(running))
        bound_before_stop["runtime_attestation"]["published_ports"] = {
            "10000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18080"}],
        }
        wrong_recorded_port = json.loads(json.dumps(running))
        wrong_recorded_port["runtime_attestation"]["published_ports"] = {
            "10001/tcp": None,
        }
        unknown_role = json.loads(json.dumps(running))
        unknown_role["role"] = "unknown"
        unknown_role["runtime_attestation"]["published_ports"] = None
        unknown_role_stopped = json.loads(json.dumps(unknown_role))
        unknown_role_stopped["runtime_attestation"]["state"] = "exited"
        unknown_role_stopped["runtime_attestation"]["published_ports"] = {}
        missing_role = json.loads(json.dumps(unknown_role))
        missing_role.pop("role")
        missing_role_stopped = json.loads(json.dumps(unknown_role_stopped))
        missing_role_stopped.pop("role")
        unhashable_role = json.loads(json.dumps(unknown_role))
        unhashable_role["role"] = ["authz"]
        unhashable_role_stopped = json.loads(json.dumps(unknown_role_stopped))
        unhashable_role_stopped["role"] = ["authz"]
        altered_after_stop = json.loads(json.dumps(stopped))
        altered_after_stop["runtime_attestation"]["published_ports"] = {
            "10001/tcp": None,
        }
        unrelated_change = json.loads(json.dumps(stopped))
        unrelated_change["runtime_attestation"]["networks"] = []
        for name, recorded, current in (
            ("still_running", running, still_running),
            ("bound_before_stop", bound_before_stop, stopped),
            ("wrong_recorded_port", wrong_recorded_port, stopped),
            ("unknown_role", unknown_role, unknown_role_stopped),
            ("missing_role", missing_role, missing_role_stopped),
            ("unhashable_role", unhashable_role, unhashable_role_stopped),
            ("altered_after_stop", running, altered_after_stop),
            ("unrelated_change", running, unrelated_change),
        ):
            with self.subTest(name=name):
                self.assertFalse(
                    local_envoy_module._container_attestation_matches(
                        recorded, current, allow_stopped=True
                    )
                )

    def test_exact_stop_attests_the_closed_docker_exposed_port_transition(self):
        value = manifest()
        running = local_envoy_module._synthetic_state_object(
            value,
            next(item for item in value["containers"] if item["role"] == "envoy"),
        )
        running["runtime_attestation"]["published_ports"] = {
            "10000/tcp": None,
        }
        stopped = json.loads(json.dumps(running))
        stopped["runtime_attestation"]["state"] = "exited"
        stopped["runtime_attestation"]["published_ports"] = {}

        class StopController:
            journal_path = Path("/ignored/journal.json")

            def __init__(self, after):
                self.inspections = iter((running, after))
                self.running_states = iter(("true\n", "false\n"))
                self.commands = []

            @staticmethod
            def docker_command(*parts):
                return list(parts)

            def _inspect_container(self, *args, **kwargs):
                return next(self.inspections)

            def _execute(self, argv, *, timeout_s, docker=False):
                command = list(argv)
                self.commands.append(command)
                if command[0] == "inspect":
                    return CommandResult(0, next(self.running_states), "")
                if command[0] == "stop":
                    return CommandResult(0, running["id"] + "\n", "")
                raise AssertionError(f"unexpected exact-stop command: {command}")

        events = []
        controller = StopController(stopped)
        creation_history = [
            {
                "event": "container_create_intent",
                "details": {"name": running["name"]},
            },
            {
                "event": "container_create_complete",
                "details": {"id": running["id"], "name": running["name"]},
            },
        ]
        with mock.patch.object(
            local_envoy_module,
            "load_lifecycle_journal",
            return_value={"events": creation_history},
        ), mock.patch.object(
            local_envoy_module,
            "journal_event",
            side_effect=lambda path, event, details: events.append((event, details)),
        ):
            LocalEnvoyController._stop_and_attest_container(
                controller,
                running,
                value,
                envoy_attachment={},
            )
        self.assertEqual(
            [event for event, _ in events],
            ["container_stop_intent", "container_stop_complete"],
        )
        self.assertEqual(
            [command[0] for command in controller.commands],
            ["inspect", "stop", "inspect"],
        )

        changed = json.loads(json.dumps(stopped))
        changed["runtime_attestation"]["networks"] = []
        rejected_events = []
        rejected = StopController(changed)
        with mock.patch.object(
            local_envoy_module,
            "load_lifecycle_journal",
            return_value={"events": creation_history},
        ), mock.patch.object(
            local_envoy_module,
            "journal_event",
            side_effect=lambda path, event, details: rejected_events.append(
                (event, details)
            ),
        ):
            with self.assertRaisesRegex(
                ControllerError, "container changed after exact stop"
            ):
                LocalEnvoyController._stop_and_attest_container(
                    rejected,
                    running,
                    value,
                    envoy_attachment={},
                )
        self.assertEqual(
            [event for event, _ in rejected_events],
            ["container_stop_intent"],
        )

    def test_exact_stop_completes_a_pending_intent_for_an_already_stopped_container(self):
        value = manifest()
        running = local_envoy_module._synthetic_state_object(
            value,
            next(item for item in value["containers"] if item["role"] == "envoy"),
        )
        running["runtime_attestation"]["published_ports"] = {"10000/tcp": None}
        stopped = json.loads(json.dumps(running))
        stopped["runtime_attestation"]["state"] = "exited"
        stopped["runtime_attestation"]["published_ports"] = {}
        history = [
            {
                "event": "container_create_intent",
                "details": {"name": running["name"]},
            },
            {
                "event": "container_create_complete",
                "details": {"id": running["id"], "name": running["name"]},
            },
            {
                "event": "container_stop_intent",
                "details": {
                    "id": running["id"],
                    "name": running["name"],
                    "role": running["role"],
                },
            },
        ]

        class PendingStopController:
            journal_path = Path("/ignored/journal.json")

            def __init__(self):
                self.commands = []

            @staticmethod
            def docker_command(*parts):
                return list(parts)

            def _inspect_container(self, *args, **kwargs):
                return stopped

            def _execute(self, argv, *, timeout_s, docker=False):
                command = list(argv)
                self.commands.append(command)
                if command[0] == "inspect":
                    return CommandResult(0, "false\n", "")
                raise AssertionError(f"unexpected recovery command: {command}")

        events = []
        controller = PendingStopController()
        with mock.patch.object(
            local_envoy_module,
            "load_lifecycle_journal",
            return_value={"events": history},
        ), mock.patch.object(
            local_envoy_module,
            "journal_event",
            side_effect=lambda path, event, details: events.append((event, details)),
        ):
            LocalEnvoyController._stop_and_attest_container(
                controller,
                running,
                value,
                envoy_attachment={},
            )

        self.assertEqual([event for event, _ in events], ["container_stop_complete"])
        self.assertEqual(controller.commands, [[
            "inspect", "--format", "{{.State.Running}}", running["id"]
        ]])

    def test_exact_stop_replay_matrix_is_idempotent_at_crash_boundaries(self):
        value = manifest()
        running = local_envoy_module._synthetic_state_object(
            value,
            next(item for item in value["containers"] if item["role"] == "envoy"),
        )
        running["runtime_attestation"]["published_ports"] = {"10000/tcp": None}
        stopped = json.loads(json.dumps(running))
        stopped["runtime_attestation"]["state"] = "exited"
        stopped["runtime_attestation"]["published_ports"] = {}
        creation = [
            {
                "event": "container_create_intent",
                "details": {"name": running["name"]},
            },
            {
                "event": "container_create_complete",
                "details": {"id": running["id"], "name": running["name"]},
            },
        ]
        intent = {
            "event": "container_stop_intent",
            "details": {
                "id": running["id"],
                "name": running["name"],
                "role": running["role"],
            },
        }
        completion = {
            "event": "container_stop_complete",
            "details": {"id": running["id"], "name": running["name"]},
        }

        class ReplayStopController:
            journal_path = Path("/ignored/journal.json")

            def __init__(self, initial):
                self.current = json.loads(json.dumps(initial))
                self.commands = []

            @staticmethod
            def docker_command(*parts):
                return list(parts)

            def _inspect_container(self, *args, **kwargs):
                return json.loads(json.dumps(self.current))

            def _execute(self, argv, *, timeout_s, docker=False):
                command = list(argv)
                self.commands.append(command)
                if command[0] == "inspect":
                    is_running = self.current["runtime_attestation"]["state"] == "running"
                    return CommandResult(0, ("true" if is_running else "false") + "\n", "")
                if command[0] == "stop":
                    self.current = json.loads(json.dumps(stopped))
                    return CommandResult(0, running["id"] + "\n", "")
                raise AssertionError(f"unexpected replay command: {command}")

        scenarios = (
            ("unstarted_running", creation, running, False, [
                "container_stop_intent", "container_stop_complete"
            ], 1),
            ("pending_running", [*creation, intent], running, False, [
                "container_stop_complete"
            ], 1),
            ("pending_stopped", [*creation, intent], stopped, False, [
                "container_stop_complete"
            ], 0),
            ("complete_stopped", [*creation, intent, completion], stopped, False, [], 0),
            ("complete_running", [*creation, intent, completion], running, True, [], 0),
        )
        for name, history, initial, rejected, expected_events, stop_count in scenarios:
            with self.subTest(name=name):
                emitted = []
                controller = ReplayStopController(initial)
                with mock.patch.object(
                    local_envoy_module,
                    "load_lifecycle_journal",
                    return_value={"events": history},
                ), mock.patch.object(
                    local_envoy_module,
                    "journal_event",
                    side_effect=lambda path, event, details: emitted.append(
                        (event, details)
                    ),
                ):
                    if rejected:
                        with self.assertRaisesRegex(
                            ControllerError, "completed container stop is running"
                        ):
                            LocalEnvoyController._stop_and_attest_container(
                                controller,
                                running,
                                value,
                                envoy_attachment={},
                            )
                    else:
                        LocalEnvoyController._stop_and_attest_container(
                            controller,
                            running,
                            value,
                            envoy_attachment={},
                        )
                self.assertEqual(
                    [event for event, _ in emitted], expected_events
                )
                self.assertEqual(
                    sum(command[0] == "stop" for command in controller.commands),
                    stop_count,
                )

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
                "src/kil/v3b1_driver_protocol.py",
                "src/kil/v3b1_request_driver.py",
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
            "networks": ["kil-v3b1-network-track"],
            "config_path": "/private/authz.json",
            "config_sha256": HEX_A,
            "gateway_port": None,
            "required_aliases": {
                "kil-v3b1-network-track": ["kil-v3b1-authz-track"]
            },
            "driver_definition": None,
            "required_state": "running",
            "primary_network": "kil-v3b1-network-track",
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
            "networks": expected["networks"],
            "network_aliases": {
                expected["networks"][0]: [expected["name"], "9" * 12]
            },
            "port_bindings": {},
            "published_ports": None,
            "platform": "linux/arm64",
            "entrypoint": ["python"],
            "command": [
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
            "state": "running",
            "stdin_open": False,
            "tty": False,
            "healthcheck": None,
            "privileged": False,
            "network_mode": expected["primary_network"],
            "pid_mode": "",
            "ipc_mode": "",
            "uts_mode": "",
            "userns_mode": "",
            "cgroupns_mode": "private",
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
        for field, value in (
            ("privileged", True),
            ("network_mode", "host"),
            ("pid_mode", "host"),
            ("ipc_mode", "host"),
            ("uts_mode", "host"),
            ("userns_mode", "host"),
            ("cgroupns_mode", "host"),
        ):
            with self.subTest(field=field, value=value):
                broken = dict(actual)
                broken[field] = value
                with self.assertRaisesRegex(
                    ControllerError, "privileged|network|namespace|mode"
                ):
                    validate_container_attestation(broken, expected)
        for field in (
            "privileged",
            "network_mode",
            "pid_mode",
            "ipc_mode",
            "uts_mode",
            "userns_mode",
            "cgroupns_mode",
        ):
            with self.subTest(missing=field):
                broken = dict(actual)
                del broken[field]
                with self.assertRaisesRegex(ControllerError, "closed|fields"):
                    validate_container_attestation(broken, expected)
            with self.subTest(wrong_type=field):
                broken = dict(actual)
                broken[field] = None
                with self.assertRaisesRegex(
                    ControllerError, "privileged|network|namespace|mode"
                ):
                    validate_container_attestation(broken, expected)
        unknown = dict(actual)
        unknown["namespace_escape"] = False
        with self.assertRaisesRegex(ControllerError, "closed|fields"):
            validate_container_attestation(unknown, expected)
        for aliases in (
            [expected["name"], "9" * 12, "envoy"],
            [expected["name"], "9" * 12, "cross-role"],
            [expected["name"], expected["name"]],
        ):
            with self.subTest(aliases=aliases):
                broken = json.loads(json.dumps(actual))
                broken["network_aliases"][expected["primary_network"]] = aliases
                with self.assertRaisesRegex(ControllerError, "alias"):
                    validate_container_attestation(broken, expected)

    def test_running_envoy_is_dual_homed_with_fixed_frontend_alias_and_no_publication(self):
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
            attachment = {
                "track": track.value,
                "phase": "complete",
                "container_id": "9" * 64,
                "container_name": track_value["envoy_container"],
                "network_id": "8" * 64,
                "network_name": track_value["frontend_network"],
                "alias": "envoy",
            }

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
                        "Privileged": False,
                        "NetworkMode": track_value["backend_network"],
                        "PidMode": "",
                        "IpcMode": "private",
                        "UTSMode": "",
                        "UsernsMode": "",
                        "CgroupnsMode": "private",
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
                        "PortBindings": {},
                    },
                    "State": {"Running": True, "Status": "running"},
                    "NetworkSettings": {
                        "Networks": {
                            track_value["backend_network"]: {
                                "Aliases": [
                                    track_value["envoy_container"],
                                    "9" * 12,
                                ]
                            },
                            track_value["frontend_network"]: {
                                "Aliases": [
                                    "envoy",
                                    track_value["envoy_container"],
                                    "9" * 12,
                                ]
                            },
                        },
                        "Ports": None,
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

            def inspect_envoy():
                return controller._inspect_container(
                    "9" * 64,
                    value,
                    "envoy",
                    track.value,
                    envoy_attachment=attachment,
                )

            controller.runner = FakeRunner(inspections())
            inspected = inspect_envoy()
            self.assertEqual(inspected["labels"], runtime_labels)
            self.assertEqual(
                inspected["runtime_attestation"]["networks"],
                sorted(
                    [
                        track_value["backend_network"],
                        track_value["frontend_network"],
                    ]
                ),
            )
            self.assertIn(
                "envoy",
                inspected["runtime_attestation"]["network_aliases"][
                    track_value["frontend_network"]
                ],
            )
            self.assertEqual(
                inspected["runtime_attestation"]["port_bindings"], {}
            )
            self.assertIsNone(
                inspected["runtime_attestation"]["published_ports"]
            )
            self.assertFalse(
                inspected["runtime_attestation"]["privileged"]
            )
            self.assertEqual(
                inspected["runtime_attestation"]["network_mode"],
                track_value["backend_network"],
            )
            self.assertEqual(
                {
                    inspected["runtime_attestation"][field]
                    for field in (
                        "pid_mode",
                        "ipc_mode",
                        "uts_mode",
                        "userns_mode",
                    )
                },
                {""},
            )

            conflict_labels = {
                **immutable_labels,
                "kil.v3b1.role": "image-owned-conflict",
            }
            controller.runner = FakeRunner(inspections(image_labels=conflict_labels))
            with self.assertRaisesRegex(ControllerError, "label.*conflict"):
                inspect_envoy()

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
                        inspect_envoy()

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
                inspect_envoy()

            published = inspections()[0]
            raw = json.loads(published.stdout)
            raw["NetworkSettings"]["Ports"] = {
                "8080/tcp": [
                    {"HostIp": "127.0.0.1", "HostPort": "18080"}
                ]
            }
            controller.runner = FakeRunner(
                [
                    CommandResult(0, canonical_json(raw) + "\n", ""),
                    inspections()[1],
                ]
            )
            with self.assertRaisesRegex(ControllerError, "public|port"):
                inspect_envoy()

            for field, mutated_value in (
                ("Privileged", True),
                ("NetworkMode", track_value["frontend_network"]),
                ("PidMode", "host"),
                ("IpcMode", "host"),
                ("UTSMode", "host"),
                ("UsernsMode", "host"),
                ("CgroupnsMode", "host"),
            ):
                with self.subTest(field=field, value=mutated_value):
                    broken = json.loads(inspections()[0].stdout)
                    broken["HostConfig"][field] = mutated_value
                    controller.runner = FakeRunner(
                        [
                            CommandResult(
                                0, canonical_json(broken) + "\n", ""
                            ),
                            inspections()[1],
                        ]
                    )
                    with self.assertRaisesRegex(
                        ControllerError, "privileged|network|namespace|mode"
                    ):
                        inspect_envoy()
            for field in (
                "Privileged",
                "NetworkMode",
                "PidMode",
                "IpcMode",
                "UTSMode",
                "UsernsMode",
                "CgroupnsMode",
            ):
                with self.subTest(missing=field):
                    broken = json.loads(inspections()[0].stdout)
                    del broken["HostConfig"][field]
                    controller.runner = FakeRunner(
                        [
                            CommandResult(
                                0, canonical_json(broken) + "\n", ""
                            ),
                            inspections()[1],
                        ]
                    )
                    with self.assertRaisesRegex(
                        ControllerError, "required fields|missing"
                    ):
                        inspect_envoy()
                with self.subTest(wrong_type=field):
                    broken = json.loads(inspections()[0].stdout)
                    broken["HostConfig"][field] = None
                    controller.runner = FakeRunner(
                        [
                            CommandResult(
                                0, canonical_json(broken) + "\n", ""
                            ),
                            inspections()[1],
                        ]
                    )
                    with self.assertRaisesRegex(
                        ControllerError, "privileged|network|namespace|mode"
                    ):
                        inspect_envoy()
            reserved_backend_alias = json.loads(inspections()[0].stdout)
            reserved_backend_alias["NetworkSettings"]["Networks"][
                track_value["backend_network"]
            ]["Aliases"].append("envoy")
            controller.runner = FakeRunner(
                [
                    CommandResult(
                        0, canonical_json(reserved_backend_alias) + "\n", ""
                    ),
                    inspections()[1],
                ]
            )
            with self.assertRaisesRegex(ControllerError, "alias"):
                inspect_envoy()

            for label, mutate in (
                ("mounts", lambda item: item.__setitem__("Mounts", [None])),
                ("status", lambda item: item["State"].pop("Status")),
                (
                    "entrypoint_falsey",
                    lambda item: item["Config"].__setitem__("Entrypoint", []),
                ),
                (
                    "entrypoint_wrong_type",
                    lambda item: item["Config"].__setitem__("Entrypoint", None),
                ),
                ("cmd_falsey", lambda item: item["Config"].__setitem__("Cmd", [])),
                ("cmd_wrong_type", lambda item: item["Config"].__setitem__("Cmd", None)),
                (
                    "aliases",
                    lambda item: item["NetworkSettings"]["Networks"][
                        track_value["backend_network"]
                    ].__setitem__("Aliases", {}),
                ),
                (
                    "networks",
                    lambda item: item["NetworkSettings"].__setitem__(
                        "Networks", []
                    ),
                ),
                (
                    "ports",
                    lambda item: item["NetworkSettings"].pop("Ports"),
                ),
                ("host", lambda item: item.__setitem__("HostConfig", [])),
            ):
                with self.subTest(malformed=label):
                    broken = json.loads(inspections()[0].stdout)
                    mutate(broken)
                    controller.runner = FakeRunner(
                        [
                            CommandResult(
                                0, canonical_json(broken) + "\n", ""
                            ),
                            inspections()[1],
                        ]
                    )
                    with self.assertRaisesRegex(
                        ControllerError,
                        "inspection|required|mount|state|process|network|port|alias",
                    ):
                        inspect_envoy()

    def test_stopped_driver_attests_created_state_exact_command_and_frontend_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            profile_path = root / "deploy/kind/v3b-profile.json"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )
            value = manifest()
            track = LiveTrack.SIGNED_STATE_ONLY
            track_value = next(
                item for item in value["tracks"] if item["track"] == track.value
            )
            name = track_value["driver_container"]
            runtime_labels = {
                "kil.v3b1.managed": "true",
                "kil.v3b1.run-id": value["run_id"],
                "kil.v3b1.role": "driver",
                "kil.v3b1.track": track.value,
            }
            immutable_labels = {"org.opencontainers.image.version": "3.12"}
            raw = {
                "Id": "7" * 64,
                "Name": f"/{name}",
                "Image": value["kil_image_id"],
                "Config": {
                    "Image": value["kil_image_id"],
                    "Labels": {**immutable_labels, **runtime_labels},
                    "User": "65532:65532",
                    "StopTimeout": 10,
                    "Entrypoint": ["python"],
                    "Cmd": [
                        "-m",
                        "kil.v3b1_request_driver",
                        "--track",
                        track.value,
                        "--endpoint",
                        "envoy:8080",
                    ],
                    "Env": ["PATH=/usr/local/bin"],
                    "OpenStdin": True,
                    "Tty": False,
                    "Healthcheck": {
                        "Test": ["NONE"],
                        "Interval": 10_000_000_000,
                        "Timeout": 3_000_000_000,
                        "StartPeriod": 5_000_000_000,
                        "Retries": 3,
                    },
                },
                "HostConfig": {
                    "Privileged": False,
                    "NetworkMode": track_value["frontend_network"],
                    "PidMode": "",
                    "IpcMode": "private",
                    "UTSMode": "",
                    "UsernsMode": "",
                    "CgroupnsMode": "private",
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
                    "PortBindings": {},
                },
                "State": {"Running": False, "Status": "created"},
                "NetworkSettings": {
                    "Networks": {
                        track_value["frontend_network"]: {
                            "Aliases": [name, "7" * 12]
                        }
                    },
                    "Ports": {},
                },
                "Mounts": [],
            }
            image = {
                "Os": "linux",
                "Architecture": "arm64",
                "Config": {
                    "Env": ["PATH=/usr/local/bin"],
                    "Labels": immutable_labels,
                    "Healthcheck": {
                        "Test": ["CMD", "python", "-c", "raise SystemExit(0)"],
                        "Interval": 10_000_000_000,
                        "Timeout": 3_000_000_000,
                        "StartPeriod": 5_000_000_000,
                        "Retries": 3,
                    },
                },
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

            inspected = controller._inspect_container(
                "7" * 64,
                value,
                "driver",
                track.value,
                require_running=False,
            )

            runtime = inspected["runtime_attestation"]
            self.assertEqual(runtime["state"], "created")
            self.assertTrue(runtime["stdin_open"])
            self.assertFalse(runtime["tty"])
            self.assertEqual(runtime["healthcheck"], "disabled")
            self.assertEqual(runtime["mounts"], [])
            self.assertEqual(runtime["networks"], [track_value["frontend_network"]])
            self.assertNotIn(track_value["backend_network"], runtime["networks"])
            self.assertFalse(runtime["privileged"])
            self.assertEqual(
                runtime["network_mode"], track_value["frontend_network"]
            )
            self.assertEqual(
                {
                    runtime[field]
                    for field in (
                        "pid_mode",
                        "ipc_mode",
                        "uts_mode",
                        "userns_mode",
                    )
                },
                {""},
            )

            for immutable_healthcheck in (image["Config"]["Healthcheck"], None):
                broken = json.loads(json.dumps(raw))
                broken["Config"]["Healthcheck"] = {"Test": ["NONE"]}
                broken_image = json.loads(json.dumps(image))
                if immutable_healthcheck is None:
                    broken_image["Config"].pop("Healthcheck")
                controller.runner = FakeRunner(
                    [
                        CommandResult(0, canonical_json(broken) + "\n", ""),
                        CommandResult(
                            0, canonical_json(broken_image) + "\n", ""
                        ),
                    ]
                )
                with self.subTest(singleton_immutable=immutable_healthcheck):
                    with self.assertRaisesRegex(
                        ControllerError, "health|driver"
                    ):
                        controller._inspect_container(
                            "7" * 64,
                            value,
                            "driver",
                            track.value,
                            require_running=False,
                        )

            for mutation, message in (
                (("OpenStdin", False), "stdin|driver"),
                (("Tty", True), "TTY|tty|driver"),
                (("Healthcheck", None), "health|driver"),
            ):
                broken = json.loads(json.dumps(raw))
                broken["Config"][mutation[0]] = mutation[1]
                controller.runner = FakeRunner(
                    [
                        CommandResult(0, canonical_json(broken) + "\n", ""),
                        CommandResult(0, canonical_json(image) + "\n", ""),
                    ]
                )
                with self.assertRaisesRegex(ControllerError, message):
                    controller._inspect_container(
                        "7" * 64,
                        value,
                        "driver",
                        track.value,
                        require_running=False,
                    )

            for field, mutated_value in (
                ("Privileged", True),
                ("NetworkMode", "host"),
                ("PidMode", "host"),
                ("IpcMode", "host"),
                ("UTSMode", "host"),
                ("UsernsMode", "host"),
                ("CgroupnsMode", "host"),
            ):
                with self.subTest(field=field, value=mutated_value):
                    broken = json.loads(json.dumps(raw))
                    broken["HostConfig"][field] = mutated_value
                    controller.runner = FakeRunner(
                        [
                            CommandResult(
                                0, canonical_json(broken) + "\n", ""
                            ),
                            CommandResult(
                                0, canonical_json(image) + "\n", ""
                            ),
                        ]
                    )
                    with self.assertRaisesRegex(
                        ControllerError, "privileged|network|namespace|mode"
                    ):
                        controller._inspect_container(
                            "7" * 64,
                            value,
                            "driver",
                            track.value,
                            require_running=False,
                        )
            for field in (
                "Privileged",
                "NetworkMode",
                "PidMode",
                "IpcMode",
                "UTSMode",
                "UsernsMode",
                "CgroupnsMode",
            ):
                with self.subTest(missing=field):
                    broken = json.loads(json.dumps(raw))
                    del broken["HostConfig"][field]
                    controller.runner = FakeRunner(
                        [
                            CommandResult(
                                0, canonical_json(broken) + "\n", ""
                            ),
                            CommandResult(
                                0, canonical_json(image) + "\n", ""
                            ),
                        ]
                    )
                    with self.assertRaisesRegex(
                        ControllerError, "required fields|missing"
                    ):
                        controller._inspect_container(
                            "7" * 64,
                            value,
                            "driver",
                            track.value,
                            require_running=False,
                        )
                with self.subTest(wrong_type=field):
                    broken = json.loads(json.dumps(raw))
                    broken["HostConfig"][field] = None
                    controller.runner = FakeRunner(
                        [
                            CommandResult(
                                0, canonical_json(broken) + "\n", ""
                            ),
                            CommandResult(
                                0, canonical_json(image) + "\n", ""
                            ),
                        ]
                    )
                    with self.assertRaisesRegex(
                        ControllerError, "privileged|network|namespace|mode"
                    ):
                        controller._inspect_container(
                            "7" * 64,
                            value,
                            "driver",
                            track.value,
                            require_running=False,
                        )
            reserved_driver_alias = json.loads(json.dumps(raw))
            reserved_driver_alias["NetworkSettings"]["Networks"][
                track_value["frontend_network"]
            ]["Aliases"].append("envoy")
            controller.runner = FakeRunner(
                [
                    CommandResult(
                        0, canonical_json(reserved_driver_alias) + "\n", ""
                    ),
                    CommandResult(0, canonical_json(image) + "\n", ""),
                ]
            )
            with self.assertRaisesRegex(ControllerError, "alias"):
                controller._inspect_container(
                    "7" * 64,
                    value,
                    "driver",
                    track.value,
                    require_running=False,
                )

            for label, mutate in (
                ("mounts", lambda item: item.__setitem__("Mounts", [None])),
                ("status", lambda item: item["State"].pop("Status")),
                (
                    "entrypoint_falsey",
                    lambda item: item["Config"].__setitem__("Entrypoint", []),
                ),
                (
                    "entrypoint_wrong_type",
                    lambda item: item["Config"].__setitem__("Entrypoint", None),
                ),
                ("cmd_falsey", lambda item: item["Config"].__setitem__("Cmd", [])),
                ("cmd_wrong_type", lambda item: item["Config"].__setitem__("Cmd", None)),
                (
                    "aliases",
                    lambda item: item["NetworkSettings"]["Networks"][
                        track_value["frontend_network"]
                    ].__setitem__("Aliases", {}),
                ),
                (
                    "networks",
                    lambda item: item["NetworkSettings"].__setitem__(
                        "Networks", []
                    ),
                ),
                (
                    "ports",
                    lambda item: item["NetworkSettings"].pop("Ports"),
                ),
                ("host", lambda item: item.__setitem__("HostConfig", [])),
            ):
                with self.subTest(malformed=label):
                    broken = json.loads(json.dumps(raw))
                    mutate(broken)
                    controller.runner = FakeRunner(
                        [
                            CommandResult(
                                0, canonical_json(broken) + "\n", ""
                            ),
                            CommandResult(
                                0, canonical_json(image) + "\n", ""
                            ),
                        ]
                    )
                    with self.assertRaisesRegex(
                        ControllerError,
                        "inspection|required|mount|state|process|network|port|alias",
                    ):
                        controller._inspect_container(
                            "7" * 64,
                            value,
                            "driver",
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
                    "Privileged": False,
                    "ReadonlyRootfs": True,
                    "AutoRemove": False,
                    "CapDrop": ["ALL"],
                    "SecurityOpt": ["no-new-privileges"],
                    "NetworkMode": "none",
                    "PidMode": "",
                    "IpcMode": "private",
                    "UTSMode": "",
                    "UsernsMode": "",
                    "CgroupnsMode": "private",
                    "PortBindings": {},
                },
                "State": {"Running": False, "Status": "exited"},
                "NetworkSettings": {
                    "Networks": {
                        "none": {
                            "IPAMConfig": None,
                            "Links": None,
                            "Aliases": None,
                            "DriverOpts": None,
                            "GwPriority": 0,
                            "NetworkID": (
                                "f39fddd12311f9f3a107c2a3186c82dc"
                                "587baf09fbffc1cf39d99b261dbf077a"
                            ),
                            "EndpointID": "",
                            "Gateway": "",
                            "IPAddress": "",
                            "MacAddress": "",
                            "IPPrefixLen": 0,
                            "IPv6Gateway": "",
                            "GlobalIPv6Address": "",
                            "GlobalIPv6PrefixLen": 0,
                            "DNSNames": None,
                        }
                    },
                    "Ports": None,
                },
                "Mounts": [
                    {
                        "Source": "/private/envoy.json",
                        "Destination": "/etc/envoy/envoy.json",
                        "RW": False,
                    }
                ],
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
            self.assertEqual(
                inspected["runtime_attestation"],
                {
                    "privileged": False,
                    "network_mode": "none",
                    "pid_mode": "",
                    "ipc_mode": "",
                    "uts_mode": "",
                    "userns_mode": "",
                    "cgroupns_mode": "private",
                    "state": "exited",
                    "entrypoint": ["/usr/local/bin/envoy"],
                    "command": raw["Config"]["Cmd"],
                    "mounts": [
                        {
                            "source": "/private/envoy.json",
                            "destination": "/etc/envoy/envoy.json",
                            "rw": False,
                        }
                    ],
                    "networks": {},
                    "port_bindings": {},
                    "published_ports": None,
                },
            )

            none_network = raw["NetworkSettings"]["Networks"]["none"]
            missing_network_id = dict(none_network)
            del missing_network_id["NetworkID"]
            for label, invalid_networks in (
                ("record_wrong_type", {"none": []}),
                ("wrong_network_name", {"custom": dict(none_network)}),
                (
                    "additional_network",
                    {"none": dict(none_network), "custom": {}},
                ),
                (
                    "unexpected_endpoint_field",
                    {"none": {**none_network, "Unexpected": None}},
                ),
                ("missing_network_id", {"none": missing_network_id}),
                (
                    "malformed_network_id",
                    {"none": {**none_network, "NetworkID": "not-hex"}},
                ),
                (
                    "endpoint_id",
                    {"none": {**none_network, "EndpointID": "e" * 64}},
                ),
                (
                    "gateway",
                    {"none": {**none_network, "Gateway": "172.18.0.1"}},
                ),
                (
                    "ip_address",
                    {"none": {**none_network, "IPAddress": "172.18.0.2"}},
                ),
                (
                    "mac_address",
                    {"none": {**none_network, "MacAddress": "02:42:ac:12:00:02"}},
                ),
                (
                    "ipv6_address",
                    {
                        "none": {
                            **none_network,
                            "GlobalIPv6Address": "fd00::2",
                        }
                    },
                ),
                (
                    "aliases",
                    {"none": {**none_network, "Aliases": ["validator"]}},
                ),
                (
                    "links",
                    {"none": {**none_network, "Links": ["service"]}},
                ),
                (
                    "dns_names",
                    {"none": {**none_network, "DNSNames": ["validator"]}},
                ),
                (
                    "ipam",
                    {"none": {**none_network, "IPAMConfig": {}}},
                ),
                (
                    "driver_options",
                    {"none": {**none_network, "DriverOpts": {}}},
                ),
                (
                    "boolean_priority",
                    {"none": {**none_network, "GwPriority": False}},
                ),
                (
                    "ipv4_prefix",
                    {"none": {**none_network, "IPPrefixLen": 24}},
                ),
                (
                    "ipv6_prefix",
                    {"none": {**none_network, "GlobalIPv6PrefixLen": 64}},
                ),
            ):
                with self.subTest(invalid_none_network=label):
                    broken = json.loads(json.dumps(raw))
                    broken["NetworkSettings"]["Networks"] = invalid_networks
                    controller.runner = FakeRunner(
                        [
                            CommandResult(
                                0, canonical_json(broken) + "\n", ""
                            ),
                            CommandResult(
                                0, canonical_json(image) + "\n", ""
                            ),
                        ]
                    )
                    with self.assertRaisesRegex(
                        ControllerError, "validator|inspection|fields|shape"
                    ):
                        controller._inspect_validation_container(
                            "8" * 64, value, track
                        )

            for field, mutated_value in (
                ("Privileged", True),
                ("NetworkMode", "host"),
                ("PidMode", "host"),
                ("IpcMode", "host"),
                ("UTSMode", "host"),
                ("UsernsMode", "host"),
                ("CgroupnsMode", "host"),
            ):
                with self.subTest(field=field, value=mutated_value):
                    broken = json.loads(json.dumps(raw))
                    broken["HostConfig"][field] = mutated_value
                    controller.runner = FakeRunner(
                        [
                            CommandResult(
                                0, canonical_json(broken) + "\n", ""
                            ),
                            CommandResult(
                                0, canonical_json(image) + "\n", ""
                            ),
                        ]
                    )
                    with self.assertRaisesRegex(
                        ControllerError, "validator|sandbox|namespace|mode"
                    ):
                        controller._inspect_validation_container(
                            "8" * 64, value, track
                        )

            for field in (
                "Privileged",
                "NetworkMode",
                "PidMode",
                "IpcMode",
                "UTSMode",
                "UsernsMode",
                "CgroupnsMode",
            ):
                with self.subTest(missing=field):
                    broken = json.loads(json.dumps(raw))
                    del broken["HostConfig"][field]
                    controller.runner = FakeRunner(
                        [
                            CommandResult(
                                0, canonical_json(broken) + "\n", ""
                            ),
                            CommandResult(
                                0, canonical_json(image) + "\n", ""
                            ),
                        ]
                    )
                    with self.assertRaisesRegex(
                        ControllerError, "validator|fields|sandbox"
                    ):
                        controller._inspect_validation_container(
                            "8" * 64, value, track
                        )
                with self.subTest(wrong_type=field):
                    broken = json.loads(json.dumps(raw))
                    broken["HostConfig"][field] = None
                    controller.runner = FakeRunner(
                        [
                            CommandResult(
                                0, canonical_json(broken) + "\n", ""
                            ),
                            CommandResult(
                                0, canonical_json(image) + "\n", ""
                            ),
                        ]
                    )
                    with self.assertRaisesRegex(
                        ControllerError, "validator|sandbox|namespace|mode"
                    ):
                        controller._inspect_validation_container(
                            "8" * 64, value, track
                        )

            for label, mutate in (
                ("mounts", lambda item: item.__setitem__("Mounts", [None])),
                ("status", lambda item: item["State"].pop("Status")),
                (
                    "entrypoint_falsey",
                    lambda item: item["Config"].__setitem__("Entrypoint", []),
                ),
                (
                    "entrypoint_wrong_type",
                    lambda item: item["Config"].__setitem__("Entrypoint", None),
                ),
                ("cmd_falsey", lambda item: item["Config"].__setitem__("Cmd", [])),
                ("cmd_wrong_type", lambda item: item["Config"].__setitem__("Cmd", None)),
                (
                    "networks",
                    lambda item: item["NetworkSettings"].__setitem__(
                        "Networks", []
                    ),
                ),
                (
                    "ports",
                    lambda item: item["NetworkSettings"].pop("Ports"),
                ),
                ("host", lambda item: item.__setitem__("HostConfig", [])),
            ):
                with self.subTest(malformed=label):
                    broken = json.loads(json.dumps(raw))
                    mutate(broken)
                    controller.runner = FakeRunner(
                        [
                            CommandResult(
                                0, canonical_json(broken) + "\n", ""
                            ),
                            CommandResult(
                                0, canonical_json(image) + "\n", ""
                            ),
                        ]
                    )
                    with self.assertRaisesRegex(
                        ControllerError, "validator|inspection|fields|shape"
                    ):
                        controller._inspect_validation_container(
                            "8" * 64, value, track
                        )

    def test_network_inspection_closes_backend_and_frontend_membership(self):
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
            backend_expected = {
                f"{index}" * 64: {"name": name, "role": role}
                for index, (name, role) in enumerate(
                    zip(member_names, ("authz", "target", "envoy"), strict=True),
                    start=1,
                )
            }

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
                "Name": track_value["backend_network"],
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
                "a" * 64,
                value,
                track.value,
                segment="backend",
                expected_members=backend_expected,
            )

            self.assertEqual(inspected["name"], track_value["backend_network"])
            self.assertEqual(inspected["segment"], "backend")
            self.assertEqual(len(runner.calls), 1)
            self.assertIn("{{json .}}", runner.calls[0][0])

            duplicate_id_payload = canonical_json(network).replace(
                '"Containers":{',
                (
                    '"Containers":{'
                    f'"{"1" * 64}":{canonical_json(member(member_names[0]))},'
                ),
                1,
            )
            controller.runner = FakeRunner(
                [CommandResult(0, duplicate_id_payload + "\n", "")]
            )
            with self.assertRaisesRegex(
                ControllerError, "closed JSON|duplicate"
            ):
                controller._inspect_network(
                    "a" * 64,
                    value,
                    track.value,
                    segment="backend",
                    expected_members=backend_expected,
                )

            partial = {**network, "Containers": {
                "1" * 64: member(member_names[0])
            }}
            controller.runner = NetworkRunner(partial)
            controller._inspect_network(
                "a" * 64,
                value,
                track.value,
                segment="backend",
                expected_members={
                    "1" * 64: backend_expected["1" * 64]
                },
                require_complete_membership=False,
            )
            controller.runner = NetworkRunner(partial)
            with self.assertRaisesRegex(ControllerError, "membership"):
                controller._inspect_network(
                    "a" * 64,
                    value,
                    track.value,
                    segment="backend",
                    expected_members={
                        "1" * 64: backend_expected["1" * 64]
                    },
                    require_complete_membership=False,
                    require_empty_membership=True,
                )
            controller.runner = NetworkRunner({**network, "Containers": {}})
            controller._inspect_network(
                "a" * 64,
                value,
                track.value,
                segment="backend",
                expected_members={},
                require_complete_membership=False,
                require_empty_membership=True,
            )

            frontend_members = [
                track_value["driver_container"],
                track_value["envoy_container"],
            ]
            frontend = {
                **network,
                "Id": "b" * 64,
                "Name": track_value["frontend_network"],
                "Containers": {
                    f"{index + 4}" * 64: member(name)
                    for index, name in enumerate(frontend_members)
                },
            }
            frontend_expected = {
                f"{index + 4}" * 64: {"name": name, "role": role}
                for index, (name, role) in enumerate(
                    zip(frontend_members, ("driver", "envoy"), strict=True)
                )
            }
            frontend_attachment = {
                "track": track.value,
                "phase": "complete",
                "container_id": "5" * 64,
                "container_name": track_value["envoy_container"],
                "network_id": "b" * 64,
                "network_name": track_value["frontend_network"],
                "alias": "envoy",
            }
            controller.runner = NetworkRunner(frontend)
            inspected_frontend = controller._inspect_network(
                "b" * 64,
                value,
                track.value,
                segment="frontend",
                expected_members=frontend_expected,
                envoy_attachment=frontend_attachment,
            )
            self.assertEqual(inspected_frontend["segment"], "frontend")

            created_options = local_envoy_module._network_member_identity_options(
                [
                    {
                        "id": "4" * 64,
                        "name": track_value["driver_container"],
                        "role": "driver",
                        "track": track.value,
                        "runtime_attestation": {"state": "created"},
                    },
                    {
                        "id": "5" * 64,
                        "name": track_value["envoy_container"],
                        "role": "envoy",
                        "track": track.value,
                        "runtime_attestation": {"state": "running"},
                    },
                ],
                value,
                track.value,
                "frontend",
                frontend_attachment,
            )
            self.assertEqual(
                created_options,
                (
                    {
                        "5" * 64: {
                            "name": track_value["envoy_container"],
                            "role": "envoy",
                        }
                    },
                ),
            )
            created_frontend = {
                **frontend,
                "Containers": {
                    "5" * 64: member(track_value["envoy_container"])
                },
            }
            controller.runner = NetworkRunner(created_frontend)
            controller._inspect_network(
                "b" * 64,
                value,
                track.value,
                segment="frontend",
                expected_members=created_options[0],
                allowed_member_options=created_options,
                envoy_attachment=frontend_attachment,
            )
            controller.runner = NetworkRunner(frontend)
            with self.assertRaisesRegex(ControllerError, "membership"):
                controller._inspect_network(
                    "b" * 64,
                    value,
                    track.value,
                    segment="frontend",
                    expected_members=created_options[0],
                    allowed_member_options=created_options,
                    envoy_attachment=frontend_attachment,
                )

            bypass = {
                **frontend,
                "Containers": {
                    **frontend["Containers"],
                    "f" * 64: member(track_value["target_container"]),
                },
            }
            controller.runner = NetworkRunner(bypass)
            with self.assertRaisesRegex(ControllerError, "membership|frontend"):
                controller._inspect_network(
                    "b" * 64,
                    value,
                    track.value,
                    segment="frontend",
                    expected_members=frontend_expected,
                    envoy_attachment=frontend_attachment,
                )

            for label, containers in (
                (
                    "wrong_id_right_name",
                    {
                        **network["Containers"],
                        "1" * 64: None,
                        "f" * 64: member(member_names[0]),
                    },
                ),
                (
                    "cross_track_forged_name",
                    {
                        "1" * 64: member(member_names[1]),
                        "2" * 64: member(member_names[0]),
                        "3" * 64: member(member_names[2]),
                    },
                ),
                (
                    "duplicate_name",
                    {
                        **network["Containers"],
                        "f" * 64: member(member_names[0]),
                    },
                ),
                (
                    "missing_member",
                    {
                        "1" * 64: network["Containers"]["1" * 64],
                        "2" * 64: network["Containers"]["2" * 64],
                    },
                ),
                (
                    "extra_member",
                    {
                        **network["Containers"],
                        "f" * 64: member("kil-v3b1-attacker"),
                    },
                ),
            ):
                with self.subTest(member_identity=label):
                    candidate = {
                        key: item
                        for key, item in containers.items()
                        if item is not None
                    }
                    controller.runner = NetworkRunner(
                        {**network, "Containers": candidate}
                    )
                    with self.assertRaisesRegex(
                        ControllerError, "identity|membership|duplicate"
                    ):
                        controller._inspect_network(
                            "a" * 64,
                            value,
                            track.value,
                            segment="backend",
                            expected_members=backend_expected,
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
                            segment="backend",
                            expected_members=backend_expected,
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
    raw_driver_results = driver_results_for_requests(requests)
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
            raw_driver_results=raw_driver_results,
        )
        source_attestations = presenter_source_attestations(
            provisional, envoy, targets
        )
    else:
        provisional = _prepare_failure_provisional(
            root / "private",
            value,
            raw_driver_results={track: b"" for track in LiveTrack},
            reset=True,
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
            raw_driver_results=driver_results_for_requests(requests),
        )
        source_attestations = presenter_source_attestations(
            provisional, envoy, targets
        )
    else:
        provisional = _prepare_failure_provisional(
            controller.provisional_root,
            value,
            raw_driver_results={track: b"" for track in LiveTrack},
            reset=True,
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

    def test_v2_bundle_binds_exact_canonical_driver_results_everywhere(self):
        value, requests, decisions, envoy, targets = JoinContractTest().all_records()
        raw_driver_results = driver_results_for_requests(requests)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provisional = write_evidence_bundle(
                root / "private",
                value,
                requests=requests,
                decisions=decisions,
                envoy=envoy,
                targets=targets,
                joins=join_evidence(value, requests, decisions, envoy, targets),
                raw_driver_results=raw_driver_results,
            )
            authority = authoritative_bundle_attestation(provisional)
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
                authoritative_attestation=authority,
            )
            public_manifest = json.loads(
                (published / "manifest.json").read_text(encoding="utf-8")
            )
            sums = {
                relative: digest
                for digest, relative in (
                    line.split("  ", 1)
                    for line in (published / "SHA256SUMS")
                    .read_text(encoding="ascii")
                    .splitlines()
                )
            }
            by_track = {item["track"]: item for item in requests}
            for track in LiveTrack:
                relative = f"raw/drivers/{track.value}.json"
                payload = (published / relative).read_bytes()
                self.assertEqual(payload, raw_driver_results[track])
                self.assertTrue(payload.endswith(b"\n"))
                self.assertEqual(
                    payload,
                    (canonical_json(json.loads(payload)) + "\n").encode("utf-8"),
                )
                digest = sha256(payload).hexdigest()
                self.assertEqual(
                    by_track[track.value]["driver_result_sha256"], digest
                )
                self.assertEqual(sums[relative], digest)
                self.assertEqual(public_manifest["artifact_sha256"][relative], digest)
                self.assertEqual(authority["file_sha256"][relative], digest)
            self.assertEqual(
                local_envoy_module.verify_presenter_bundle(published),
                (published / "live.html").resolve(),
            )

    def test_v1_rejects_driver_files_and_v2_requires_all_three(self):
        fixture_root = ROOT / "tests/fixtures/v3b1-public-bundle-v1"
        legacy = next(path for path in fixture_root.iterdir() if path.is_dir())
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "legacy"
            shutil.copytree(legacy, copied)
            drivers = copied / "raw/drivers"
            drivers.mkdir()
            (drivers / "credential_policy_baseline.json").write_text("{}\n")
            with self.assertRaisesRegex(ControllerError, "artifact set|closed"):
                local_envoy_module.verify_presenter_bundle(copied)

        with tempfile.TemporaryDirectory() as directory:
            published = published_presenter_bundle(Path(directory))
            missing = published / "raw/drivers/signed_state_only.json"
            missing.chmod(0o600)
            missing.unlink()
            with self.assertRaisesRegex(ControllerError, "missing|closed|artifact"):
                local_envoy_module.verify_presenter_bundle(published)

    def test_private_bundle_writers_reject_symlinked_ancestry_before_writes(self):
        value, requests, decisions, envoy, targets = JoinContractTest().all_records()
        raw_driver_results = driver_results_for_requests(requests)
        cases = (
            ("accepted", "root"),
            ("accepted", "run"),
            ("failure", "run"),
            ("failure", "raw"),
            ("failure", "decisions"),
            ("failure", "drivers"),
            ("resume", "run"),
            ("resume", "raw"),
            ("resume", "decisions"),
            ("resume", "drivers"),
        )
        for mode, component in cases:
            with (
                self.subTest(mode=mode, component=component),
                tempfile.TemporaryDirectory() as directory,
            ):
                base = Path(directory)
                outside = base / "outside"
                outside.mkdir()
                evidence_root = base / "evidence"
                if component == "root":
                    evidence_root.symlink_to(outside, target_is_directory=True)
                else:
                    evidence_root.mkdir()
                    output = evidence_root / value["run_id"]
                    if component == "run":
                        output.symlink_to(outside, target_is_directory=True)
                    else:
                        output.mkdir()
                        raw = output / "raw"
                        if component == "raw":
                            raw.symlink_to(outside, target_is_directory=True)
                        else:
                            raw.mkdir()
                            if component == "decisions":
                                (raw / "decisions").symlink_to(
                                    outside, target_is_directory=True
                                )
                            else:
                                (raw / "decisions").mkdir()
                                (raw / "drivers").symlink_to(
                                    outside, target_is_directory=True
                                )

                with self.assertRaisesRegex(
                    ControllerError, "unsafe|symbolic|contained|directory"
                ):
                    if mode == "failure":
                        _prepare_failure_provisional(
                            evidence_root,
                            value,
                            raw_driver_results={
                                track: b"" for track in LiveTrack
                            },
                            reset=True,
                        )
                    else:
                        write_evidence_bundle(
                            evidence_root,
                            value,
                            requests=requests,
                            decisions=decisions,
                            envoy=envoy,
                            targets=targets,
                            joins=join_evidence(
                                value,
                                requests,
                                decisions,
                                envoy,
                                targets,
                            ),
                            raw_driver_results=raw_driver_results,
                            resume_attested=mode == "resume",
                        )
                self.assertEqual(list(outside.iterdir()), [])

    def test_private_bundle_transactions_reject_post_prepare_directory_swaps(self):
        value, requests, decisions, envoy, targets = JoinContractTest().all_records()
        raw_driver_results = driver_results_for_requests(requests)
        cases = (
            ("accepted", "raw"),
            ("accepted", "drivers"),
            ("failure", "raw"),
            ("failure", "drivers"),
            ("resume", "raw"),
            ("resume", "drivers"),
        )
        for mode, component in cases:
            with (
                self.subTest(mode=mode, component=component),
                tempfile.TemporaryDirectory() as directory,
            ):
                base = Path(directory)
                evidence_root = base / "evidence"
                outside = base / "outside"
                outside.mkdir()
                if mode == "resume":
                    seeded = write_evidence_bundle(
                        evidence_root,
                        value,
                        requests=requests,
                        decisions=decisions,
                        envoy=envoy,
                        targets=targets,
                        joins=join_evidence(
                            value,
                            requests,
                            decisions,
                            envoy,
                            targets,
                        ),
                        raw_driver_results=raw_driver_results,
                    )
                    self.assertTrue(any(seeded.iterdir()))
                stages: list[str] = []

                def swap_after_prepare(stage: str, output: Path) -> None:
                    stages.append(stage)
                    self.assertEqual(stage, "after_prepare")
                    victim = output / "raw"
                    if component == "drivers":
                        victim /= "drivers"
                    held = base / f"held-{mode}-{component}"
                    victim.rename(held)
                    victim.symlink_to(outside, target_is_directory=True)

                with self.assertRaisesRegex(
                    ControllerError, "changed|identity|unsafe|directory"
                ):
                    if mode == "failure":
                        _prepare_failure_provisional(
                            evidence_root,
                            value,
                            requests=requests,
                            raw_decisions={
                                track: b"".join(
                                    (canonical_json(record) + "\n").encode("utf-8")
                                    for record in decisions
                                    if record["track"] == track.value
                                )
                                for track in LiveTrack
                            },
                            raw_driver_results=raw_driver_results,
                            envoy=envoy,
                            targets=targets,
                            reset=True,
                            private_evidence_fault=swap_after_prepare,
                        )
                    else:
                        write_evidence_bundle(
                            evidence_root,
                            value,
                            requests=requests,
                            decisions=decisions,
                            envoy=envoy,
                            targets=targets,
                            joins=join_evidence(
                                value,
                                requests,
                                decisions,
                                envoy,
                                targets,
                            ),
                            raw_driver_results=raw_driver_results,
                            resume_attested=mode == "resume",
                            private_evidence_fault=swap_after_prepare,
                        )
                self.assertEqual(stages, ["after_prepare"])
                self.assertEqual(list(outside.iterdir()), [])

    def test_v2_verifier_reconstructs_driver_bytes_and_rejects_repaired_join_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            published = published_presenter_bundle(Path(directory))
            driver_path = (
                published / "raw/drivers/credential_policy_baseline.json"
            )
            result = json.loads(driver_path.read_text(encoding="utf-8"))
            result["decision_digest"] = "9" * 64
            payload = (canonical_json(result) + "\n").encode("utf-8")
            driver_path.chmod(0o600)
            driver_path.write_bytes(payload)
            driver_path.chmod(0o444)
            requests_path = published / "requests.jsonl"
            requests = [
                json.loads(line)
                for line in requests_path.read_text(encoding="utf-8").splitlines()
            ]
            requests[0]["driver_result_sha256"] = sha256(payload).hexdigest()
            requests_path.chmod(0o600)
            requests_path.write_bytes(
                b"".join(
                    (canonical_json(item) + "\n").encode("utf-8")
                    for item in requests
                )
            )
            requests_path.chmod(0o444)
            rewrite_public_bundle_hashes(published)

            with self.assertRaisesRegex(
                ControllerError, "driver|decision|projection|join"
            ):
                local_envoy_module.verify_presenter_bundle(published)

    def test_v2_verifier_rejects_noncanonical_duplicate_and_sensitive_driver_bytes(self):
        for mutation in ("noncanonical", "duplicate", "sensitive"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                published = published_presenter_bundle(Path(directory))
                driver_path = (
                    published / "raw/drivers/credential_policy_baseline.json"
                )
                original = driver_path.read_bytes()
                if mutation == "noncanonical":
                    payload = b" " + original
                elif mutation == "duplicate":
                    payload = original.replace(
                        b'{"attempt_count":1,',
                        b'{"attempt_count":1,"attempt_count":1,',
                        1,
                    )
                else:
                    payload = original[:-2] + (
                        b',"exception_message":"Bearer do-not-publish"}\n'
                    )
                driver_path.chmod(0o600)
                driver_path.write_bytes(payload)
                driver_path.chmod(0o444)
                requests_path = published / "requests.jsonl"
                requests = [
                    json.loads(line)
                    for line in requests_path.read_text(encoding="utf-8").splitlines()
                ]
                requests[0]["driver_result_sha256"] = sha256(payload).hexdigest()
                requests_path.chmod(0o600)
                requests_path.write_bytes(
                    b"".join(
                        (canonical_json(item) + "\n").encode("utf-8")
                        for item in requests
                    )
                )
                requests_path.chmod(0o444)
                rewrite_public_bundle_hashes(published)

                with self.assertRaisesRegex(
                    ControllerError, "driver result|canonical|public evidence"
                ):
                    local_envoy_module.verify_presenter_bundle(published)

    def test_v2_presenter_explains_driver_boundary_without_active_content(self):
        with tempfile.TemporaryDirectory() as directory:
            published = published_presenter_bundle(Path(directory))
            text = (published / "live.html").read_text(encoding="utf-8")
            for statement in (
                "request driver -&gt; Envoy -&gt; authorization -&gt; target or withhold",
                "No host publication",
                "The driver is a laboratory transport witness, not KIL enforcement",
                "Evidence scope: local_envoy_boundary",
            ):
                self.assertIn(statement, text)
            for forbidden in ("<script", " src=", " href=", "url(", "http://", "https://"):
                self.assertNotIn(forbidden, text)

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

    def test_legacy_v1_write_finalize_verify_preserves_exact_generation(self):
        fixture_root = ROOT / "tests/fixtures/v3b1-public-bundle-v1"
        fixture = next(path for path in fixture_root.iterdir() if path.is_dir())
        frozen_manifest = json.loads(
            (fixture / "manifest.json").read_text(encoding="utf-8")
        )
        identity = frozen_manifest["content_identity"]
        networks = [
            {
                "track": track.value,
                "name": f"kil-v3b1-network-{index}",
            }
            for index, track in enumerate(LiveTrack)
        ]
        containers = []
        tracks = []
        for index, track in enumerate(LiveTrack):
            names = {
                role: f"kil-v3b1-{role}-{index}"
                for role in ("authz", "target", "envoy")
            }
            containers.extend(
                {
                    "name": names[role],
                    "role": role,
                    "track": track.value,
                    "image": (
                        frozen_manifest["immutable_images"]["envoy_digest"]
                        if role == "envoy"
                        else frozen_manifest["immutable_images"]["kil_image_id"]
                    ),
                }
                for role in ("authz", "target", "envoy")
            )
            tracks.append(
                {
                    "track": track.value,
                    "gateway_port": 18080 + index,
                    "authz_container": names["authz"],
                    "target_container": names["target"],
                    "envoy_container": names["envoy"],
                    "network": networks[index]["name"],
                    "decision_source": "/evidence/decisions.jsonl",
                    "target_source": "/evidence/targets.jsonl",
                    "envoy_source": "/evidence/access.jsonl",
                }
            )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_manifest = {
                "schema_version": "kil.v3b1-manifest.v1",
                "evidence_scope": "local_envoy_boundary",
                "content_identity_sha256": frozen_manifest[
                    "content_identity_sha256"
                ],
                "content_identity": identity,
                "run_id": frozen_manifest["run_id"],
                "request_id": frozen_manifest["request_id"],
                "colima_profile": "kil-v3-lab",
                "docker_host": f"unix://{root}/docker.sock",
                "execution_nonce": "0" * 64,
                "platform": frozen_manifest["platform"],
                "source_commit": frozen_manifest["source_commit"],
                "python_image_digest": frozen_manifest["immutable_images"][
                    "python"
                ],
                "envoy_image_digest": frozen_manifest["immutable_images"][
                    "envoy_digest"
                ],
                "envoy_image_id": frozen_manifest["immutable_images"][
                    "envoy_image_id"
                ],
                "kil_image_id": frozen_manifest["immutable_images"][
                    "kil_image_id"
                ],
                "kil_archive_sha256": frozen_manifest["immutable_images"][
                    "kil_archive_sha256"
                ],
                "networks": networks,
                "tracks": tracks,
                "containers": containers,
                "teardown": {
                    "status": "pending",
                    "containers_removed": False,
                    "network_removed": False,
                    "profile_deleted": False,
                },
            }
            local_envoy_module._validate_manifest(private_manifest)
            requests = [
                json.loads(line)
                for line in (fixture / "requests.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            raw_driverless_decisions = {
                track: (
                    fixture / f"raw/decisions/{track.value}.jsonl"
                ).read_bytes()
                for track in LiveTrack
            }
            decisions = [
                json.loads(raw_driverless_decisions[track])
                for track in LiveTrack
            ]
            envoy = [
                json.loads(line)
                for line in (fixture / "envoy.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            targets = [
                json.loads(line)
                for line in (fixture / "targets.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            joins = [
                json.loads(line)
                for line in (fixture / "joins.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            provisional = write_evidence_bundle(
                root / "private",
                private_manifest,
                requests=requests,
                decisions=decisions,
                envoy=envoy,
                targets=targets,
                joins=joins,
                raw_decisions=raw_driverless_decisions,
            )
            frozen_inventory = {
                path.relative_to(fixture).as_posix()
                for path in fixture.rglob("*")
                if path.is_file()
            }
            provisional_inventory = {
                path.relative_to(provisional).as_posix()
                for path in provisional.rglob("*")
                if path.is_file()
            }
            self.assertEqual(provisional_inventory, frozen_inventory)
            self.assertNotIn(
                "raw/drivers/credential_policy_baseline.json",
                provisional_inventory,
            )
            self.assertEqual(
                (provisional / "live.html").read_bytes(),
                (fixture / "live.html").read_bytes(),
            )
            authority = authoritative_bundle_attestation(provisional)
            self.assertEqual(
                authority["schema_version"],
                "kil.v3b1-authoritative-bundle.v1",
            )
            published = finalize_publication(
                provisional,
                root / "public",
                private_manifest,
                source_attestations=frozen_manifest["source_attestations"],
                tool_identities=frozen_manifest["verified_tool_identities"],
                engine_provenance=frozen_manifest[
                    "docker_engine_provenance"
                ],
                global_context_before="personal",
                global_context_after="personal",
                completed=True,
                authoritative_attestation=authority,
            )
            published_inventory = {
                path.relative_to(published).as_posix()
                for path in published.rglob("*")
                if path.is_file()
            }
            self.assertEqual(published_inventory, frozen_inventory)
            self.assertEqual(
                (published / "live.html").read_bytes(),
                (fixture / "live.html").read_bytes(),
            )
            self.assertEqual(
                json.loads((published / "manifest.json").read_text())["schema_version"],
                "kil.v3b1-public-manifest.v1",
            )
            self.assertEqual(
                local_envoy_module.verify_presenter_bundle(published),
                published.resolve() / "live.html",
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
                raw_driver_results=driver_results_for_requests(requests),
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
                root / "private",
                value,
                raw_driver_results={track: b"" for track in LiveTrack},
                reset=True,
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
                    raw_driver_results=driver_results_for_requests(requests),
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
                raw_driver_results=driver_results_for_requests(requests),
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
                        "schema_version": "kil.v3b1-public-commitment.v2",
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
        original_write_sums = local_envoy_module._write_and_verify_private_sums

        def observe_presenter(transaction, schema_version):
            live = os.stat(
                "live.html",
                dir_fd=transaction.run_fd,
                follow_symlinks=False,
            )
            observed.append(
                (
                    stat.S_ISREG(live.st_mode),
                    stat.S_IMODE(live.st_mode),
                    sha256(
                        local_envoy_module._read_private_file_at(
                            transaction.run_fd, "live.html"
                        )
                    ).hexdigest(),
                )
            )
            return original_write_sums(transaction, schema_version)

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            local_envoy_module,
            "_write_and_verify_private_sums",
            side_effect=observe_presenter,
        ):
            output = write_evidence_bundle(
                Path(directory),
                value,
                requests=requests,
                decisions=decisions,
                envoy=envoy,
                targets=targets,
                joins=joins,
                raw_driver_results=driver_results_for_requests(requests),
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
                raw_driver_results=driver_results_for_requests(requests),
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
                raw_driver_results=driver_results_for_requests(requests),
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
                raw_driver_results=driver_results_for_requests(requests),
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
                Path(directory),
                value,
                raw_driver_results={track: b"" for track in LiveTrack},
                reset=True,
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
                raw_driver_results=driver_results_for_requests(requests),
            )
            second = write_evidence_bundle(
                Path(second_directory),
                value,
                requests=list(reversed(requests)),
                decisions=list(reversed(decisions)),
                envoy=list(reversed(envoy)),
                targets=list(reversed(targets)),
                joins=list(reversed(joins)),
                raw_driver_results=driver_results_for_requests(requests),
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
                raw_driver_results=driver_results_for_requests(requests),
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
                    raw_driver_results=driver_results_for_requests(requests),
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
            self.assertEqual(len(sums), 14)
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
                raw_driver_results=driver_results_for_requests(requests),
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
                raw_driver_results=driver_results_for_requests(requests),
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
                raw_driver_results=driver_results_for_requests(requests[:1])
                | {
                    track: b""
                    for track in LiveTrack
                    if track is not LiveTrack.CREDENTIAL_POLICY_BASELINE
                },
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
