import json
from io import BytesIO
from pathlib import Path
import traceback
import unittest
from unittest.mock import patch

from kil.canonical import canonical_json
import kil.v3b1_driver_protocol as driver_protocol
import kil.v3b1_request_driver as request_driver
from kil.v3b1_driver_protocol import (
    DriverProtocolError,
    canonical_record,
    driver_definition,
    parse_instruction,
    parse_result,
)
from kil.v3b1_request_driver import execute_driver


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

    def test_private_instruction_errors_retain_no_secret_input(self):
        sentinel = "PRIVATE_CREDENTIAL_SENTINEL_7f3a"
        rejected = (
            (
                '{"PRIVATE_CREDENTIAL_SENTINEL_7f3a":1,'
                '"PRIVATE_CREDENTIAL_SENTINEL_7f3a":2}\n'
            ).encode("ascii"),
            ('{"authorization":"' + sentinel + '"\n').encode("ascii"),
            (
                '{"authorization":"'
                + sentinel
                + '","oversized_integer":'
                + "1" * 5000
                + "}\n"
            ).encode("ascii"),
            ('{"authorization":"' + sentinel + '"} \n').encode("ascii"),
            ('{"authorization":"' + sentinel).encode("ascii") + b"\xff\n",
        )

        for payload in rejected:
            with self.subTest(payload_size=len(payload)):
                try:
                    parse_instruction(payload, expected_track="signed_state_only")
                except DriverProtocolError as error:
                    rendered = "".join(
                        traceback.TracebackException.from_exception(error).format()
                    )
                    self.assertNotIn(sentinel, str(error))
                    self.assertNotIn(sentinel, repr(error))
                    self.assertNotIn(sentinel, rendered)
                    self.assertIsNone(error.__cause__)
                    self.assertIsNone(error.__context__)
                else:
                    self.fail("private malformed instruction was accepted")

    def test_instruction_headers_reject_retry_identity_and_demo_value_drift(self):
        base = private_instruction()
        changed_headers = (
            {"x-envoy-max-retries": "9"},
            {"x-envoy-hedge-on-per-try-timeout": "true"},
            {"authorization": "Bearer "},
            {"authorization": "bearer synthetic-v3b1-credential"},
            {"authorization": "Bearer token with-space"},
            {"authorization": "Bearer " + "A" * 4097},
            {"authorization": "Bearer crédential"},
            {"authorization": "Bearer synthetic\x7fcredential"},
            {"x-kil-run-id": "v3b1-" + "A" * 64},
            {"x-kil-run-id": "v3b1-" + "1" * 63},
            {"x-kil-run-id": "/tmp/private-run-id"},
            {"x-kil-run-id": "Bearer private-run-credential"},
            {"x-request-id": "other-request"},
            {"x-request-id": "/tmp/private-request-id"},
            {"x-request-id": "KIL_PRIVATE=credential"},
            {"x-request-id": "v3b1-central-requesté"},
            {"x-kil-decision-digest": "e" * 64},
            {"x-kil-issuer": "https://other.invalid"},
            {"x-kil-issuer": "https://attacker.invalid\x1f"},
            {"x-kil-local-evidence": '{"divergence":"1"}'},
            {"x-kil-mode": "signed_state_only"},
            {"x-kil-track": "signed_state_only"},
            {
                "x-kil-verified-subject":
                    "spiffe://attacker.invalid/other-workload"
            },
            {"x-kil-q-state": base["headers"]["x-kil-q-state"] + "\x7f"},
            {"x-kil-q-state": base["headers"]["x-kil-q-state"] + "é"},
        )

        for changed in changed_headers:
            with self.subTest(changed=changed), self.assertRaises(
                DriverProtocolError
            ):
                parse_instruction(
                    private_bytes(
                        {**base, "headers": {**base["headers"], **changed}}
                    ),
                    expected_track="signed_state_only",
                )

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
        self.assertEqual(
            driver_protocol.LINUX_ERRNO_NAMES[104], "ECONNRESET"
        )
        self.assertEqual(
            driver_protocol.LINUX_ERRNO_NAMES[111], "ECONNREFUSED"
        )
        with self.assertRaises(TypeError):
            driver_protocol.LINUX_ERRNO_NAMES[104] = "ECONNREFUSED"
        for number, name in (
            (5, "EIO"),
            (104, "ECONNRESET"),
            (111, "ECONNREFUSED"),
        ):
            with self.subTest(number=number, name=name):
                valid = {**transport, "errno": number, "errno_name": name}
                self.assertEqual(
                    parse_result(
                        canonical_record(valid),
                        expected_track="signed_state_only",
                    ),
                    valid,
                )
        rejected = (
            {**transport, "stage": "connect"},
            {**transport, "errno": 104, "errno_name": "ECONNREFUSED"},
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


class _Clock:
    def __init__(self, *values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


class _Response:
    def __init__(
        self,
        *,
        status=200,
        decision_digest=HEX_A,
        body=b"",
        header_error=None,
        body_error=None,
    ):
        self.status = status
        self.decision_digest = decision_digest
        self.body = body
        self.header_error = header_error
        self.body_error = body_error
        self.header_names = []
        self.read_sizes = []

    def getheader(self, name):
        self.header_names.append(name)
        if self.header_error is not None:
            raise self.header_error
        if name.lower() == "x-kil-decision-digest":
            return self.decision_digest
        return None

    def read(self, size=-1):
        self.read_sizes.append(size)
        if self.body_error is not None:
            raise self.body_error
        return self.body[:size]


class _Connection:
    def __init__(self, response=None, *, request_error=None, response_error=None):
        self.response = _Response() if response is None else response
        self.request_error = request_error
        self.response_error = response_error
        self.connect_count = 0
        self.close_count = 0
        self.requests = []
        self.getresponse_count = 0
        self.auto_open = 1

    def connect(self):
        self.connect_count += 1

    def request(self, method, path, body=None, headers=None):
        self.requests.append((method, path, body, dict(headers or {})))
        if self.request_error is not None:
            raise self.request_error

    def getresponse(self):
        self.getresponse_count += 1
        if self.response_error is not None:
            raise self.response_error
        return self.response

    def close(self):
        self.close_count += 1


class _Factory:
    def __init__(self, connection):
        self.connection = connection
        self.calls = []

    def __call__(self, host, port, *, timeout):
        self.calls.append((host, port, timeout))
        return self.connection


class _Output(BytesIO):
    def __init__(self):
        super().__init__()
        self.flush_count = 0

    def flush(self):
        self.flush_count += 1
        return super().flush()


class _ReadGuard(BytesIO):
    def __init__(self, payload, output):
        super().__init__(payload)
        self.output = output
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        records = self.output.getvalue().splitlines(keepends=True)
        if len(records) != 1:
            raise AssertionError("stdin was read before the single readiness record")
        if self.output.flush_count != 1:
            raise AssertionError("readiness was not flushed before stdin was read")
        parse_result(records[0], expected_track="signed_state_only")
        return super().read(size)


class RequestDriverTest(unittest.TestCase):
    def run_driver(
        self,
        payload,
        *,
        connection=None,
        clock_values=(10, 20, 30, 40),
        guarded_input=False,
    ):
        output = _Output()
        stdin = (
            _ReadGuard(payload, output)
            if guarded_input
            else BytesIO(payload)
        )
        connection = _Connection() if connection is None else connection
        factory = _Factory(connection)
        exit_code = execute_driver(
            track="signed_state_only",
            stdin=stdin,
            stdout=output,
            connection_factory=factory,
            monotonic_ns=_Clock(*clock_values),
        )
        return exit_code, output.getvalue(), stdin, connection, factory

    def parsed_output(self, payload):
        records = payload.splitlines(keepends=True)
        return [
            parse_result(record, expected_track="signed_state_only")
            for record in records
        ]

    def test_readiness_precedes_first_stdin_read_and_eof_cancels_silently(self):
        exit_code, output, stdin, connection, factory = self.run_driver(
            b"", clock_values=(10, 20), guarded_input=True
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            self.parsed_output(output),
            [
                {
                    "schema_version": "kil.v3b1-driver-readiness.v1",
                    "track": "signed_state_only",
                    "status": "ready",
                    "connect_monotonic_ns": 10,
                    "ready_monotonic_ns": 20,
                }
            ],
        )
        self.assertEqual(stdin.read_sizes, [driver_protocol.MAX_INSTRUCTION_BYTES + 1])
        self.assertEqual(output.count(b"\n"), 1)
        self.assertEqual(factory.calls, [("envoy", 8080, 2.0)])
        self.assertEqual(connection.connect_count, 1)
        self.assertEqual(connection.requests, [])
        self.assertEqual(connection.getresponse_count, 0)
        self.assertEqual(connection.close_count, 1)

    def test_valid_instruction_reuses_retained_connection_once_and_emits_success(self):
        instruction = private_instruction()
        response = _Response(status=200, decision_digest=HEX_A, body=b"private-body")
        connection = _Connection(response)

        exit_code, output, _, connection, factory = self.run_driver(
            private_bytes(instruction),
            connection=connection,
            guarded_input=True,
        )

        self.assertEqual(exit_code, 0)
        records = self.parsed_output(output)
        self.assertEqual(len(records), 2)
        self.assertEqual(
            records[1],
            {
                "schema_version": "kil.v3b1-driver-result.v1",
                "track": "signed_state_only",
                "status": "complete",
                "connect_monotonic_ns": 10,
                "send_monotonic_ns": 30,
                "receive_monotonic_ns": 40,
                "response_status": 200,
                "decision_digest": HEX_A,
                "attempt_count": 1,
                "retry_performed": False,
            },
        )
        self.assertEqual(factory.calls, [("envoy", 8080, 2.0)])
        self.assertEqual(connection.connect_count, 1)
        self.assertEqual(connection.auto_open, 0)
        self.assertEqual(
            connection.requests,
            [("POST", "/consequential/admin", b"", instruction["headers"])],
        )
        self.assertEqual(connection.getresponse_count, 1)
        self.assertEqual(response.header_names, ["x-kil-decision-digest"])
        self.assertEqual(
            response.read_sizes,
            [driver_protocol.MAX_RESPONSE_BODY_BYTES + 1],
        )
        self.assertEqual(connection.close_count, 1)
        self.assertNotIn(b"private-body", output)
        self.assertNotIn(instruction["headers"]["authorization"].encode(), output)
        self.assertNotIn(instruction["headers"]["x-kil-q-state"].encode(), output)

    def test_oversize_response_body_is_terminal_and_never_echoed(self):
        sentinel = b"PRIVATE_RESPONSE_SENTINEL"
        response = _Response(
            body=b"x" * driver_protocol.MAX_RESPONSE_BODY_BYTES + sentinel
        )
        connection = _Connection(response)

        exit_code, output, _, connection, factory = self.run_driver(
            private_bytes(private_instruction()), connection=connection
        )

        self.assertEqual(exit_code, 1)
        result = self.parsed_output(output)[1]
        self.assertEqual(result["status"], "transport_failure")
        self.assertEqual(result["stage"], "response_body")
        self.assertEqual(result["exception_class"], "OSError")
        self.assertEqual(result["errno"], None)
        self.assertEqual(result["errno_name"], None)
        self.assertTrue(result["request_bytes_may_have_been_sent"])
        self.assertEqual(result["attempt_count"], 1)
        self.assertFalse(result["retry_performed"])
        self.assertEqual(
            response.read_sizes,
            [driver_protocol.MAX_RESPONSE_BODY_BYTES + 1],
        )
        self.assertNotIn(sentinel, output)
        self.assertEqual(len(factory.calls), 1)
        self.assertEqual(connection.connect_count, 1)
        self.assertEqual(len(connection.requests), 1)
        self.assertEqual(connection.getresponse_count, 1)
        self.assertEqual(connection.close_count, 1)

    def test_unapproved_response_header_value_is_closed_and_never_echoed(self):
        sentinel = "PRIVATE_RESPONSE_HEADER_SENTINEL"
        connection = _Connection(_Response(decision_digest=sentinel))

        exit_code, output, _, connection, factory = self.run_driver(
            private_bytes(private_instruction()), connection=connection
        )

        self.assertEqual(exit_code, 1)
        result = self.parsed_output(output)[1]
        self.assertEqual(result["status"], "transport_failure")
        self.assertEqual(result["stage"], "response_headers")
        self.assertEqual(result["exception_class"], "OSError")
        self.assertNotIn(sentinel.encode(), output)
        self.assertEqual(len(factory.calls), 1)
        self.assertEqual(connection.connect_count, 1)
        self.assertEqual(len(connection.requests), 1)
        self.assertEqual(connection.getresponse_count, 1)
        self.assertEqual(connection.close_count, 1)

    def test_closed_instruction_rejections_send_no_http_and_emit_no_result(self):
        base = private_instruction()
        canonical = private_bytes(base)
        duplicate = canonical.replace(
            b'{"body_byte_count":0,',
            b'{"body_byte_count":0,"body_byte_count":0,',
            1,
        )
        changed = (
            ("duplicate", duplicate),
            ("unknown", private_bytes({**base, "unknown": True})),
            ("trailing", canonical + b"\n"),
            ("noncanonical", (json.dumps(base) + "\n").encode()),
            ("wrong-track", private_bytes({**base, "track": "signed_plus_local_reduce"})),
            ("wrong-path", private_bytes({**base, "path": "/other"})),
            ("wrong-method", private_bytes({**base, "method": "GET"})),
            ("body", private_bytes({**base, "body_byte_count": 1})),
            (
                "header",
                private_bytes(
                    {**base, "headers": {**base["headers"], "x-extra": "value"}}
                ),
            ),
            ("missing-newline", canonical[:-1]),
            ("oversize", b"x" * (driver_protocol.MAX_INSTRUCTION_BYTES + 1)),
        )

        for name, payload in changed:
            with self.subTest(name=name):
                exit_code, output, _, connection, factory = self.run_driver(
                    payload, clock_values=(10, 20)
                )
                self.assertEqual(exit_code, 1)
                self.assertEqual(len(self.parsed_output(output)), 1)
                self.assertEqual(len(factory.calls), 1)
                self.assertEqual(connection.connect_count, 1)
                self.assertEqual(connection.requests, [])
                self.assertEqual(connection.getresponse_count, 0)
                self.assertEqual(connection.close_count, 1)

    def test_transport_failures_are_closed_secret_free_and_never_retried(self):
        cases = (
            (
                "request_send",
                _Connection(request_error=ConnectionResetError(104, "PRIVATE send")),
                "ConnectionResetError",
                104,
                "ECONNRESET",
            ),
            (
                "response_headers",
                _Connection(response_error=TimeoutError(110, "PRIVATE headers")),
                "TimeoutError",
                110,
                "ETIMEDOUT",
            ),
            (
                "response_body",
                _Connection(
                    _Response(body_error=BrokenPipeError(32, "PRIVATE body"))
                ),
                "BrokenPipeError",
                32,
                "EPIPE",
            ),
        )

        for stage, connection, exception_class, number, name in cases:
            with self.subTest(stage=stage):
                exit_code, output, _, connection, factory = self.run_driver(
                    private_bytes(private_instruction()),
                    connection=connection,
                )
                self.assertEqual(exit_code, 1)
                result = self.parsed_output(output)[1]
                self.assertEqual(result["status"], "transport_failure")
                self.assertEqual(result["stage"], stage)
                self.assertEqual(result["exception_class"], exception_class)
                self.assertEqual(result["errno"], number)
                self.assertEqual(result["errno_name"], name)
                self.assertTrue(result["request_bytes_may_have_been_sent"])
                self.assertEqual(result["attempt_count"], 1)
                self.assertFalse(result["retry_performed"])
                self.assertNotIn(b"PRIVATE", output)
                self.assertEqual(len(factory.calls), 1)
                self.assertEqual(connection.connect_count, 1)
                self.assertEqual(len(connection.requests), 1)
                self.assertLessEqual(connection.getresponse_count, 1)
                self.assertEqual(connection.close_count, 1)

    def test_main_accepts_only_fixed_arguments_and_uses_binary_streams_silently(self):
        class StandardStream:
            def __init__(self):
                self.buffer = BytesIO()

        standard_input = StandardStream()
        standard_output = StandardStream()
        standard_error = StandardStream()
        calls = []

        def fake_execute_driver(**kwargs):
            calls.append(kwargs)
            return 0

        with (
            patch.object(request_driver.sys, "stdin", standard_input),
            patch.object(request_driver.sys, "stdout", standard_output),
            patch.object(request_driver.sys, "stderr", standard_error),
            patch.object(request_driver, "execute_driver", fake_execute_driver),
        ):
            self.assertEqual(
                request_driver.main(
                    [
                        "--track",
                        "signed_state_only",
                        "--endpoint",
                        "envoy:8080",
                    ]
                ),
                0,
            )
            for rejected in (
                [],
                ["--track", "other", "--endpoint", "envoy:8080"],
                ["--track", "signed_state_only"],
                ["--track", "signed_state_only", "--endpoint", "localhost:8080"],
                ["--endpoint", "envoy:8080", "--track", "signed_state_only"],
                ["--track", "signed_state_only", "--endpoint", "envoy:8080", "extra"],
            ):
                with self.subTest(rejected=rejected):
                    self.assertEqual(request_driver.main(rejected), 2)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["track"], "signed_state_only")
        self.assertIs(calls[0]["stdin"], standard_input.buffer)
        self.assertIs(calls[0]["stdout"], standard_output.buffer)
        self.assertEqual(standard_error.buffer.getvalue(), b"")

        def failing_execute_driver(**kwargs):
            raise RuntimeError("PRIVATE main failure")

        with (
            patch.object(request_driver.sys, "stdin", standard_input),
            patch.object(request_driver.sys, "stdout", standard_output),
            patch.object(request_driver.sys, "stderr", standard_error),
            patch.object(request_driver, "execute_driver", failing_execute_driver),
        ):
            self.assertEqual(
                request_driver.main(
                    [
                        "--track",
                        "signed_state_only",
                        "--endpoint",
                        "envoy:8080",
                    ]
                ),
                1,
            )
        self.assertEqual(standard_error.buffer.getvalue(), b"")


if __name__ == "__main__":
    unittest.main()
