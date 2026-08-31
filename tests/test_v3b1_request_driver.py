import json
from pathlib import Path
import unittest

from kil.canonical import canonical_json
from kil.v3b1_driver_protocol import (
    DriverProtocolError,
    canonical_record,
    driver_definition,
    parse_instruction,
    parse_result,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/v3b1-request-driver-protocol.json"
HEX_A = "a" * 64


def private_instruction(*, track="signed_state_only"):
    headers = {
        "authorization": "Bearer " + "synthetic-v3b1-credential",
        "x-envoy-hedge-on-per-try-timeout": "false",
        "x-envoy-max-retries": "0",
        "x-kil-decision-digest": "f" * 64,
        "x-kil-issuer": "https://attacker.invalid",
        "x-kil-local-evidence": '{"divergence":"0"}',
        "x-kil-mode": "credential_policy_baseline",
        "x-kil-run-id": "v3b1-" + "1" * 64,
        "x-kil-track": "client-selected-track",
        "x-kil-verified-subject": "spiffe://attacker.invalid/workload",
        "x-request-id": "v3b1-central-request",
    }
    if track != "credential_policy_baseline":
        headers["x-kil-q-state"] = ".".join(
            (
                "eyJhbGciOiJFZERTQSJ9",
                "eyJzdWIiOiJ3b3JrbG9hZCJ9",
                "c2lnbmF0dXJl",
            )
        )
    return {
        "schema_version": "kil.v3b1-driver-instruction.v1",
        "track": track,
        "method": "POST",
        "path": "/consequential/admin",
        "headers": headers,
        "body_byte_count": 0,
    }


def private_bytes(value):
    return (canonical_json(value) + "\n").encode("utf-8")


class DriverProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_bytes = FIXTURE.read_bytes()
        cls.fixture = json.loads(cls.fixture_bytes)

    def test_fixture_is_canonical_synthetic_protocol_evidence(self):
        self.assertEqual(
            self.fixture_bytes,
            (canonical_json(self.fixture) + "\n").encode("utf-8"),
        )
        self.assertEqual(
            self.fixture["fixture_class"],
            "deterministic_synthetic_protocol_contract",
        )

    def test_driver_definition_is_fixed_non_circular_and_canonical(self):
        definition = driver_definition(
            track="signed_state_only",
            image_id="sha256:" + "1" * 64,
            bootstrap_sha256="2" * 64,
            frontend_segment_sha256="3" * 64,
        )

        self.assertEqual(definition, self.fixture["driver_definition"])
        self.assertEqual(definition["endpoint"], {"host": "envoy", "port": 8080})
        for forbidden in (
            "container_name",
            "run_id",
            "label",
            "container_id",
            "full_id",
        ):
            self.assertNotIn(forbidden, definition)
        self.assertEqual(
            canonical_record(definition),
            canonical_record(dict(reversed(list(definition.items())))),
        )
        self.assertTrue(canonical_record(definition).endswith(b"\n"))
        self.assertEqual(canonical_record(definition).count(b"\n"), 1)

    def test_driver_definition_rejects_invalid_track_and_digests(self):
        valid = {
            "track": "signed_state_only",
            "image_id": "sha256:" + "1" * 64,
            "bootstrap_sha256": "2" * 64,
            "frontend_segment_sha256": "3" * 64,
        }
        for changed in (
            {"track": "other"},
            {"track": True},
            {"image_id": "1" * 64},
            {"image_id": "sha256:" + "A" * 64},
            {"bootstrap_sha256": "2" * 63},
            {"frontend_segment_sha256": "3" * 65},
        ):
            with self.subTest(changed=changed), self.assertRaises(DriverProtocolError):
                driver_definition(**{**valid, **changed})

    def test_canonical_record_frames_the_private_instruction_for_its_closed_parser(self):
        value = private_instruction()
        payload = canonical_record(value)
        self.assertEqual(payload, private_bytes(value))
        self.assertEqual(
            parse_instruction(payload, expected_track="signed_state_only"),
            value,
        )

    def test_public_result_recursively_rejects_sensitive_material(self):
        compact_jws = ".".join(
            ("eyJhbGciOiJFZERTQSJ9", "eyJzdWIiOiJ4In0", "c2ln")
        )
        success = self.fixture["success_result"]
        rejected_fields = (
            ("nested", {"authorization": "redacted"}),
            ("q-state", "redacted"),
            ("credentials", ["redacted"]),
            ("nested", [{"exception_message": "connection refused"}]),
            ("stdout", "anything"),
            ("stderr", "anything"),
            ("socket_path", "/tmp/private.sock"),
            ("value", compact_jws),
            ("value", "gh" + "p_" + "A" * 36),
            ("value", "AK" + "IA" + "A" * 16),
            ("value", "-----BEGIN " + "PRIVATE KEY-----"),
            ("value", "KIL_PRIVATE=redacted"),
            ("value", "/Users/example/private/evidence"),
            ("value", "/var/run/private.sock"),
            ("value", "unix:///private/runtime.sock"),
        )
        for field, value in rejected_fields:
            with self.subTest(field=field, value=value), self.assertRaises(
                DriverProtocolError
            ):
                parse_result(
                    private_bytes({**success, field: value}),
                    expected_track="signed_state_only",
                )

    def test_parse_instruction_accepts_only_the_private_closed_contract(self):
        value = private_instruction()

        self.assertEqual(
            parse_instruction(private_bytes(value), expected_track="signed_state_only"),
            value,
        )
        baseline = private_instruction(track="credential_policy_baseline")
        self.assertEqual(
            parse_instruction(
                private_bytes(baseline),
                expected_track="credential_policy_baseline",
            ),
            baseline,
        )

    def test_parse_instruction_rejects_unknown_fields_headers_and_request_shape(self):
        base = private_instruction()
        changed_values = (
            {**base, "endpoint": {"host": "localhost", "port": 8080}},
            {**base, "track": "credential_policy_baseline"},
            {**base, "method": "GET"},
            {**base, "path": "/other"},
            {**base, "body_byte_count": 1},
            {**base, "headers": {**base["headers"], "x-extra": "value"}},
            {
                **base,
                "headers": {
                    key: value
                    for key, value in base["headers"].items()
                    if key != "authorization"
                },
            },
            {**base, "headers": {**base["headers"], "authorization": "bad\nvalue"}},
        )
        for changed in changed_values:
            with self.subTest(changed=changed), self.assertRaises(DriverProtocolError):
                parse_instruction(
                    private_bytes(changed), expected_track="signed_state_only"
                )

    def test_parse_instruction_rejects_duplicate_noncanonical_trailing_and_oversize(self):
        payload = private_bytes(private_instruction())
        duplicate = payload.replace(
            b'{"body_byte_count":0,',
            b'{"body_byte_count":0,"body_byte_count":0,',
            1,
        )
        noncanonical = (json.dumps(private_instruction()) + "\n").encode("utf-8")
        for rejected in (
            duplicate,
            noncanonical,
            payload + b"\n",
            payload + payload,
            b" " * (32 * 1024 + 1),
            payload[:-1],
            b"\xff\n",
        ):
            with self.subTest(size=len(rejected)), self.assertRaises(DriverProtocolError):
                parse_instruction(rejected, expected_track="signed_state_only")

    def test_parse_result_accepts_exact_readiness_success_and_failures(self):
        for name in (
            "readiness",
            "success_result",
            "transport_failure_result",
            "driver_control_failure_result",
        ):
            with self.subTest(name=name):
                value = self.fixture[name]
                self.assertEqual(
                    parse_result(
                        canonical_record(value), expected_track="signed_state_only"
                    ),
                    value,
                )

    def test_parse_result_rejects_nonclosed_invalid_and_sensitive_records(self):
        success = self.fixture["success_result"]
        rejected_values = (
            {**success, "endpoint": {"host": "localhost", "port": 8080}},
            {**success, "track": "other"},
            {**success, "response_status": 99},
            {**success, "decision_digest": "A" * 64},
            {**success, "attempt_count": 2},
            {**success, "attempt_count": True},
            {**success, "retry_performed": True},
            {**success, "receive_monotonic_ns": 1},
            {**success, "authorization": "redacted"},
            {**success, "exception_message": "connection reset by peer"},
        )
        for value in rejected_values:
            with self.subTest(value=value), self.assertRaises(DriverProtocolError):
                parse_result(canonical_record(value), expected_track="signed_state_only")

        payload = canonical_record(success)
        duplicate = payload.replace(
            b'"status":"complete"',
            b'"status":"complete","status":"complete"',
            1,
        )
        for rejected in (
            duplicate,
            (json.dumps(success) + "\n").encode("utf-8"),
            payload + b"\n",
            b" " * (8 * 1024 + 1),
            payload[:-1],
        ):
            with self.subTest(size=len(rejected)), self.assertRaises(DriverProtocolError):
                parse_result(rejected, expected_track="signed_state_only")

    def test_transport_and_driver_control_failures_are_exact_and_ordered(self):
        transport = self.fixture["transport_failure_result"]
        control = self.fixture["driver_control_failure_result"]
        rejected = (
            {**transport, "stage": "connect"},
            {**transport, "errno": 111, "errno_name": "ECONNRESET"},
            {**transport, "request_bytes_may_have_been_sent": False},
            {**transport, "failure_monotonic_ns": 1},
            {**control, "stage": "socket_open"},
            {**control, "request_bytes_may_have_been_sent": False},
            {**control, "attempt_count": 0},
        )
        for value in rejected:
            with self.subTest(value=value), self.assertRaises(DriverProtocolError):
                parse_result(canonical_record(value), expected_track="signed_state_only")


if __name__ == "__main__":
    unittest.main()
