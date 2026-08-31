"""Closed protocol contracts for the V3B-1 in-network request driver."""

from __future__ import annotations

from base64 import urlsafe_b64decode
from copy import deepcopy
import errno as errno_module
import json
import re

from .canonical import canonical_json


TRACKS = (
    "credential_policy_baseline",
    "signed_state_only",
    "signed_plus_local_reduce",
)
DRIVER_ENDPOINT = {"host": "envoy", "port": 8080}
MAX_INSTRUCTION_BYTES = 32 * 1024
MAX_RESULT_BYTES = 8 * 1024
MAX_RESPONSE_BODY_BYTES = 4096
DRIVER_RUNTIME_POLICY = {
    "user": "65532:65532",
    "read_only": True,
    "no_new_privileges": True,
    "cap_drop": ["ALL"],
    "nano_cpus": 500_000_000,
    "memory": 268_435_456,
    "memory_swap": 268_435_456,
    "pids_limit": 128,
    "restart": "no",
    "stop_timeout": 10,
    "log_driver": "json-file",
    "log_options": {"max-file": "1", "max-size": "1m"},
    "tmpfs": {
        "/tmp": (
            "rw,noexec,nosuid,nodev,size=16m,uid=65532,gid=65532,mode=0700"
        )
    },
    "stdin_open": True,
    "tty": False,
    "healthcheck": "disabled",
    "mounts": [],
    "ports": {},
}

_HEX = re.compile(r"^[a-f0-9]{64}$")
_IMAGE_ID = re.compile(r"^sha256:[a-f0-9]{64}$")
_ENVIRONMENT_VALUE = re.compile(r"^[A-Z_][A-Z0-9_]*=.*$")
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
_PRIVATE_KEY_BLOCK = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----")
_GITHUB_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_])(?:ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,})"
    r"(?![A-Za-z0-9_])"
)
_AWS_ACCESS_KEY = re.compile(
    r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"
)
_BEARER_TOKEN = re.compile(r"(?i)(?:^|\s)bearer\s+\S+")
_COMPACT_JWS_CANDIDATE = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
    r"(?![A-Za-z0-9_-])"
)
_FORBIDDEN_PUBLIC_KEYS = {
    "access_key",
    "api_key",
    "authorization",
    "credential",
    "credentials",
    "docker_config",
    "docker_host",
    "env",
    "environ",
    "environment",
    "exception_message",
    "jws",
    "message",
    "password",
    "private_key",
    "private_path",
    "q_state",
    "raw_exception_message",
    "raw_message",
    "refresh_token",
    "secret",
    "signed_state",
    "socket_path",
    "stderr",
    "stdout",
    "token",
}
_BASE_INSTRUCTION_HEADERS = {
    "authorization",
    "x-envoy-hedge-on-per-try-timeout",
    "x-envoy-max-retries",
    "x-kil-decision-digest",
    "x-kil-issuer",
    "x-kil-local-evidence",
    "x-kil-mode",
    "x-kil-run-id",
    "x-kil-track",
    "x-kil-verified-subject",
    "x-request-id",
}
_SIGNED_INSTRUCTION_HEADER = "x-kil-q-state"
_TRANSPORT_STAGES = {"request_send", "response_headers", "response_body"}
_DRIVER_CONTROL_STAGES = {
    "instruction_write",
    "stdout_read",
    "process_wait",
    "termination",
}
_EXCEPTION_CLASSES = {
    "OSError",
    "TimeoutError",
    "ConnectionError",
    "BrokenPipeError",
    "ConnectionAbortedError",
    "ConnectionRefusedError",
    "ConnectionResetError",
}
_MAX_MONOTONIC_NS = (1 << 63) - 1


class DriverProtocolError(ValueError):
    """Raised when a driver record is not bounded, closed, and canonical."""


def _require_fields(
    value: object,
    expected: set[str],
    label: str,
) -> dict[str, object]:
    if type(value) is not dict or set(value) != expected:
        raise DriverProtocolError(f"{label} fields are not closed")
    return value


def require_track(value: object) -> str:
    if type(value) is not str or value not in TRACKS:
        raise DriverProtocolError("driver track is invalid")
    return value


def require_sha256(value: object) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise DriverProtocolError("driver SHA-256 is invalid")
    return value


def require_image_id(value: object) -> str:
    if type(value) is not str or _IMAGE_ID.fullmatch(value) is None:
        raise DriverProtocolError("driver image ID is invalid")
    return value


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DriverProtocolError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _decode_json(text: str) -> object:
    return json.loads(text, object_pairs_hook=_closed_object)


def _looks_like_compact_jws(value: str) -> bool:
    parts = value.split(".")
    if len(parts) != 3 or any(
        not part or re.fullmatch(r"[A-Za-z0-9_-]+", part) is None
        for part in parts
    ):
        return False
    try:
        header = urlsafe_b64decode(parts[0] + "=" * (-len(parts[0]) % 4))
        decoded = _decode_json(header.decode("utf-8"))
    except (DriverProtocolError, ValueError, UnicodeError):
        return False
    return isinstance(decoded, dict) and bool({"alg", "typ"}.intersection(decoded))


def _contains_compact_jws(value: str) -> bool:
    return any(
        _looks_like_compact_jws(match.group(0))
        for match in _COMPACT_JWS_CANDIDATE.finditer(value)
    )


def _reject_sensitive_material(value: object) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise DriverProtocolError("public record keys must be strings")
            normalized = key.lower().replace("-", "_")
            if normalized in _FORBIDDEN_PUBLIC_KEYS:
                raise DriverProtocolError("public record contains a sensitive field")
            _reject_sensitive_material(key)
            _reject_sensitive_material(item)
        return
    if type(value) in (list, tuple):
        for item in value:
            _reject_sensitive_material(item)
        return
    if type(value) is not str:
        return
    try:
        value.encode("utf-8")
    except UnicodeError as error:
        raise DriverProtocolError("public record contains invalid Unicode") from error
    if (
        value.startswith(("~/", "~\\", "unix://"))
        or (value.startswith("/") and value != "/tmp")
        or _WINDOWS_ABSOLUTE.match(value) is not None
        or value.startswith(("/Users/", "/home/", "/private/", "/var/tmp/"))
        or value.startswith("/tmp/")
        or re.search(r"(?i)[A-Z]:[\\/]Users[\\/]", value) is not None
    ):
        raise DriverProtocolError("public record contains a private or socket path")
    if any(
        _ENVIRONMENT_VALUE.fullmatch(line) is not None
        for line in value.splitlines()
    ):
        raise DriverProtocolError("public record contains environment material")
    if (
        _PRIVATE_KEY_BLOCK.search(value) is not None
        or _GITHUB_TOKEN.search(value) is not None
        or _AWS_ACCESS_KEY.search(value) is not None
        or _BEARER_TOKEN.search(value) is not None
        or _contains_compact_jws(value)
    ):
        raise DriverProtocolError("public record contains credential material")


def reject_sensitive_material(value: object) -> None:
    """Reject private material without retaining it in the public error."""
    try:
        _reject_sensitive_material(value)
    except DriverProtocolError:
        raise
    except (AttributeError, TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise DriverProtocolError("public record sensitive-material scan failed") from error


def canonical_record(value: object) -> bytes:
    """Serialize one protocol record as canonical UTF-8 plus one newline."""
    try:
        return (canonical_json(value) + "\n").encode("utf-8")
    except DriverProtocolError:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise DriverProtocolError("public record canonicalization failed") from error


def driver_definition(
    *,
    track: str,
    image_id: str,
    bootstrap_sha256: str,
    frontend_segment_sha256: str,
) -> dict[str, object]:
    """Return the non-circular immutable definition for one request driver."""
    value = {
        "schema_version": "kil.v3b1-driver-definition.v1",
        "role": "request_driver",
        "track": require_track(track),
        "image_id": require_image_id(image_id),
        "bootstrap_sha256": require_sha256(bootstrap_sha256),
        "frontend_segment_sha256": require_sha256(frontend_segment_sha256),
        "endpoint": dict(DRIVER_ENDPOINT),
        "runtime_policy": deepcopy(DRIVER_RUNTIME_POLICY),
    }
    reject_sensitive_material(value)
    return value


def _load_record(payload: object, limit: int, label: str) -> dict[str, object]:
    if type(payload) is not bytes or not payload or len(payload) > limit:
        raise DriverProtocolError(f"{label} is not bounded bytes")
    try:
        text = payload.decode("utf-8")
        value = _decode_json(text)
        canonical = (canonical_json(value) + "\n").encode("utf-8")
    except DriverProtocolError:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise DriverProtocolError(f"{label} is not closed JSON") from error
    if payload != canonical:
        raise DriverProtocolError(f"{label} is not canonical JSON")
    if type(value) is not dict:
        raise DriverProtocolError(f"{label} must be a JSON object")
    return value


def _require_header_value(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or len(value.encode("utf-8")) > 16 * 1024
        or any(character in value for character in ("\r", "\n", "\0"))
    ):
        raise DriverProtocolError("driver instruction header value is invalid")
    return value


def parse_instruction(
    payload: bytes,
    *,
    expected_track: str,
) -> dict[str, object]:
    """Parse one private credential-bearing instruction without public scanning."""
    expected = require_track(expected_track)
    value = _load_record(payload, MAX_INSTRUCTION_BYTES, "driver instruction")
    record = _require_fields(
        value,
        {
            "body_byte_count",
            "headers",
            "method",
            "path",
            "schema_version",
            "track",
        },
        "driver instruction",
    )
    track = require_track(record["track"])
    if (
        record["schema_version"] != "kil.v3b1-driver-instruction.v1"
        or track != expected
        or record["method"] != "POST"
        or record["path"] != "/consequential/admin"
        or type(record["body_byte_count"]) is not int
        or record["body_byte_count"] != 0
    ):
        raise DriverProtocolError("driver instruction request facts are invalid")
    headers = record["headers"]
    if type(headers) is not dict:
        raise DriverProtocolError("driver instruction headers are invalid")
    expected_headers = set(_BASE_INSTRUCTION_HEADERS)
    if track != "credential_policy_baseline":
        expected_headers.add(_SIGNED_INSTRUCTION_HEADER)
    if set(headers) != expected_headers:
        raise DriverProtocolError("driver instruction headers are not closed")
    for key, item in headers.items():
        if type(key) is not str:
            raise DriverProtocolError("driver instruction header name is invalid")
        _require_header_value(item)
    if not str(headers["authorization"]).lower().startswith("bearer "):
        raise DriverProtocolError("driver instruction authorization is invalid")
    if track != "credential_policy_baseline" and not _looks_like_compact_jws(
        str(headers[_SIGNED_INSTRUCTION_HEADER])
    ):
        raise DriverProtocolError("driver instruction Q-state is invalid")
    return record


def _require_monotonic(value: object, label: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_MONOTONIC_NS:
        raise DriverProtocolError(f"{label} is invalid")
    return value


def _require_one_attempt(record: dict[str, object]) -> None:
    if (
        type(record["attempt_count"]) is not int
        or record["attempt_count"] != 1
        or record["retry_performed"] is not False
    ):
        raise DriverProtocolError("driver result must record one attempt and no retry")


def _validate_readiness(value: dict[str, object]) -> None:
    record = _require_fields(
        value,
        {
            "connect_monotonic_ns",
            "ready_monotonic_ns",
            "schema_version",
            "status",
            "track",
        },
        "driver readiness",
    )
    connect = _require_monotonic(
        record["connect_monotonic_ns"], "driver readiness connect time"
    )
    ready = _require_monotonic(
        record["ready_monotonic_ns"], "driver readiness ready time"
    )
    if record["status"] != "ready" or connect > ready:
        raise DriverProtocolError("driver readiness facts are invalid")


def _validate_success(value: dict[str, object]) -> None:
    record = _require_fields(
        value,
        {
            "attempt_count",
            "connect_monotonic_ns",
            "decision_digest",
            "receive_monotonic_ns",
            "response_status",
            "retry_performed",
            "schema_version",
            "send_monotonic_ns",
            "status",
            "track",
        },
        "driver success result",
    )
    connect = _require_monotonic(
        record["connect_monotonic_ns"], "driver result connect time"
    )
    send = _require_monotonic(record["send_monotonic_ns"], "driver result send time")
    receive = _require_monotonic(
        record["receive_monotonic_ns"], "driver result receive time"
    )
    response_status = record["response_status"]
    if (
        type(response_status) is not int
        or response_status < 100
        or response_status > 599
        or connect > send
        or send > receive
    ):
        raise DriverProtocolError("driver success result facts are invalid")
    require_sha256(record["decision_digest"])
    _require_one_attempt(record)


def _validate_transport_failure(value: dict[str, object]) -> None:
    record = _require_fields(
        value,
        {
            "attempt_count",
            "connect_monotonic_ns",
            "errno",
            "errno_name",
            "exception_class",
            "failure_monotonic_ns",
            "request_bytes_may_have_been_sent",
            "retry_performed",
            "schema_version",
            "send_monotonic_ns",
            "stage",
            "status",
            "track",
        },
        "driver transport-failure result",
    )
    if record["stage"] not in _TRANSPORT_STAGES:
        raise DriverProtocolError("driver transport-failure stage is invalid")
    if record["exception_class"] not in _EXCEPTION_CLASSES:
        raise DriverProtocolError("driver transport exception class is invalid")
    number = record["errno"]
    name = record["errno_name"]
    if (number is None) != (name is None):
        raise DriverProtocolError("driver transport errno fields are inconsistent")
    if number is not None and (
        type(number) is not int
        or number < 0
        or type(name) is not str
        or errno_module.errorcode.get(number) != name
    ):
        raise DriverProtocolError("driver transport errno is invalid")
    connect = _require_monotonic(
        record["connect_monotonic_ns"], "driver failure connect time"
    )
    send = _require_monotonic(record["send_monotonic_ns"], "driver failure send time")
    failure = _require_monotonic(
        record["failure_monotonic_ns"], "driver failure time"
    )
    may_have_sent = record["request_bytes_may_have_been_sent"]
    if (
        type(may_have_sent) is not bool
        or connect > send
        or send > failure
        or (record["stage"] != "request_send" and not may_have_sent)
    ):
        raise DriverProtocolError("driver transport-failure facts are invalid")
    _require_one_attempt(record)


def _validate_driver_control_failure(value: dict[str, object]) -> None:
    record = _require_fields(
        value,
        {
            "attempt_count",
            "failure_monotonic_ns",
            "request_bytes_may_have_been_sent",
            "retry_performed",
            "schema_version",
            "stage",
            "status",
            "track",
        },
        "driver-control failure result",
    )
    may_have_sent = record["request_bytes_may_have_been_sent"]
    if (
        record["stage"] not in _DRIVER_CONTROL_STAGES
        or type(may_have_sent) is not bool
        or (record["stage"] != "instruction_write" and not may_have_sent)
    ):
        raise DriverProtocolError("driver-control failure facts are invalid")
    _require_monotonic(record["failure_monotonic_ns"], "driver-control failure time")
    _require_one_attempt(record)


def parse_result(
    payload: bytes,
    *,
    expected_track: str,
) -> dict[str, object]:
    """Parse one canonical public readiness, result, or control-failure record."""
    expected = require_track(expected_track)
    value = _load_record(payload, MAX_RESULT_BYTES, "driver result")
    reject_sensitive_material(value)
    if value.get("track") != expected:
        raise DriverProtocolError("driver result track does not match")
    require_track(value.get("track"))
    schema = value.get("schema_version")
    status = value.get("status")
    if schema == "kil.v3b1-driver-readiness.v1":
        _validate_readiness(value)
    elif schema != "kil.v3b1-driver-result.v1":
        raise DriverProtocolError("driver result schema is invalid")
    elif status == "complete":
        _validate_success(value)
    elif status == "transport_failure":
        _validate_transport_failure(value)
    elif status == "driver_control_failure":
        _validate_driver_control_failure(value)
    else:
        raise DriverProtocolError("driver result status is invalid")
    return value
