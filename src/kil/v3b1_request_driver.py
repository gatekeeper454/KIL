"""One-shot retained-connection request driver for the V3B-1 lab."""

from __future__ import annotations

from http.client import HTTPConnection
import sys
import time
from typing import BinaryIO, Callable, Sequence

from .v3b1_driver_protocol import (
    DRIVER_ENDPOINT,
    LINUX_ERRNO_NAMES,
    MAX_INSTRUCTION_BYTES,
    MAX_RESPONSE_BODY_BYTES,
    DriverProtocolError,
    canonical_record,
    parse_instruction,
    parse_result,
    require_sha256,
    require_track,
)


_ENDPOINT_ARGUMENT = "envoy:8080"
_DECISION_DIGEST_HEADER = "x-kil-decision-digest"


def _validated_record(record: dict[str, object], track: str) -> dict[str, object]:
    return parse_result(canonical_record(record), expected_track=track)


def readiness_record(
    track: str,
    connect_monotonic_ns: int,
    ready_monotonic_ns: int,
) -> dict[str, object]:
    """Construct one closed public readiness record."""
    return _validated_record(
        {
            "schema_version": "kil.v3b1-driver-readiness.v1",
            "track": require_track(track),
            "status": "ready",
            "connect_monotonic_ns": connect_monotonic_ns,
            "ready_monotonic_ns": ready_monotonic_ns,
        },
        track,
    )


def read_bounded_single_line(stdin: BinaryIO, limit: int) -> bytes | None:
    """Read one EOF-terminated canonical line within the fixed byte bound."""
    if type(limit) is not int or limit < 1:
        raise DriverProtocolError("driver instruction limit is invalid")
    try:
        payload = stdin.read(limit + 1)
    except (OSError, ValueError, TypeError):
        raise DriverProtocolError("driver instruction read failed") from None
    if payload == b"":
        return None
    if type(payload) is not bytes or len(payload) > limit:
        raise DriverProtocolError("driver instruction exceeds its byte limit")
    if not payload.endswith(b"\n") or payload.count(b"\n") != 1:
        raise DriverProtocolError("driver instruction framing is invalid")
    return payload


def _exception_class(error: BaseException) -> str:
    name = type(error).__name__
    if name in {
        "BrokenPipeError",
        "ConnectionAbortedError",
        "ConnectionRefusedError",
        "ConnectionResetError",
        "TimeoutError",
        "ConnectionError",
        "OSError",
    }:
        return name
    for exception_type in (
        BrokenPipeError,
        ConnectionAbortedError,
        ConnectionRefusedError,
        ConnectionResetError,
        TimeoutError,
        ConnectionError,
        OSError,
    ):
        if isinstance(error, exception_type):
            return exception_type.__name__
    return "OSError"


def _linux_errno(error: BaseException) -> tuple[int | None, str | None]:
    number = getattr(error, "errno", None)
    if type(number) is not int or number not in LINUX_ERRNO_NAMES:
        return None, None
    return number, LINUX_ERRNO_NAMES[number]


def _transport_failure(
    *,
    track: str,
    stage: str,
    error: BaseException,
    connect_monotonic_ns: int,
    send_monotonic_ns: int,
    failure_monotonic_ns: int,
) -> dict[str, object]:
    number, name = _linux_errno(error)
    return _validated_record(
        {
            "schema_version": "kil.v3b1-driver-result.v1",
            "track": track,
            "status": "transport_failure",
            "stage": stage,
            "exception_class": _exception_class(error),
            "errno": number,
            "errno_name": name,
            "connect_monotonic_ns": connect_monotonic_ns,
            "send_monotonic_ns": send_monotonic_ns,
            "failure_monotonic_ns": failure_monotonic_ns,
            "request_bytes_may_have_been_sent": True,
            "attempt_count": 1,
            "retry_performed": False,
        },
        track,
    )


def _closed_response_facts(response: object) -> tuple[int, str]:
    try:
        status = response.status
        digest = response.getheader(_DECISION_DIGEST_HEADER)
        if type(status) is not int or status < 100 or status > 599:
            raise OSError()
        require_sha256(digest)
    except (AttributeError, DriverProtocolError, TypeError, ValueError):
        raise OSError() from None
    return status, digest


def perform_one_request(
    connection: object,
    instruction: dict[str, object],
    monotonic_ns: Callable[[], int],
    *,
    connect_monotonic_ns: int,
) -> dict[str, object]:
    """Send and consume exactly one request on the retained connection."""
    track = require_track(instruction["track"])
    send_monotonic_ns = monotonic_ns()
    try:
        connection.request(
            instruction["method"],
            instruction["path"],
            body=b"",
            headers=instruction["headers"],
        )
    except Exception as error:
        return _transport_failure(
            track=track,
            stage="request_send",
            error=error,
            connect_monotonic_ns=connect_monotonic_ns,
            send_monotonic_ns=send_monotonic_ns,
            failure_monotonic_ns=monotonic_ns(),
        )

    try:
        response = connection.getresponse()
        status, digest = _closed_response_facts(response)
    except Exception as error:
        return _transport_failure(
            track=track,
            stage="response_headers",
            error=error,
            connect_monotonic_ns=connect_monotonic_ns,
            send_monotonic_ns=send_monotonic_ns,
            failure_monotonic_ns=monotonic_ns(),
        )

    try:
        body = response.read(MAX_RESPONSE_BODY_BYTES + 1)
        if type(body) is not bytes or len(body) > MAX_RESPONSE_BODY_BYTES:
            raise OSError()
    except Exception as error:
        return _transport_failure(
            track=track,
            stage="response_body",
            error=error,
            connect_monotonic_ns=connect_monotonic_ns,
            send_monotonic_ns=send_monotonic_ns,
            failure_monotonic_ns=monotonic_ns(),
        )

    receive_monotonic_ns = monotonic_ns()
    return _validated_record(
        {
            "schema_version": "kil.v3b1-driver-result.v1",
            "track": track,
            "status": "complete",
            "connect_monotonic_ns": connect_monotonic_ns,
            "send_monotonic_ns": send_monotonic_ns,
            "receive_monotonic_ns": receive_monotonic_ns,
            "response_status": status,
            "decision_digest": digest,
            "attempt_count": 1,
            "retry_performed": False,
        },
        track,
    )


def execute_driver(
    *,
    track: str,
    stdin: BinaryIO,
    stdout: BinaryIO,
    connection_factory: Callable[..., object] = HTTPConnection,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
) -> int:
    """Run readiness and at most one request without reconnect or retry."""
    try:
        validated_track = require_track(track)
    except DriverProtocolError:
        return 1

    connection: object | None = None
    connect_monotonic_ns = monotonic_ns()
    try:
        connection = connection_factory(
            DRIVER_ENDPOINT["host"],
            DRIVER_ENDPOINT["port"],
            timeout=2.0,
        )
        connection.connect()
        connection.auto_open = 0
        ready_monotonic_ns = monotonic_ns()
        stdout.write(
            canonical_record(
                readiness_record(
                    validated_track,
                    connect_monotonic_ns,
                    ready_monotonic_ns,
                )
            )
        )
        stdout.flush()
        try:
            raw = read_bounded_single_line(stdin, MAX_INSTRUCTION_BYTES)
            if raw is None:
                return 0
            instruction = parse_instruction(raw, expected_track=validated_track)
        except DriverProtocolError:
            return 1
        finally:
            raw = None

        result = perform_one_request(
            connection,
            instruction,
            monotonic_ns,
            connect_monotonic_ns=connect_monotonic_ns,
        )
        instruction = None
        stdout.write(canonical_record(result))
        stdout.flush()
        return 0 if result["status"] == "complete" else 1
    except (DriverProtocolError, OSError, TypeError, ValueError):
        return 1
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def _parse_main_arguments(argv: Sequence[str]) -> str | None:
    if len(argv) != 4:
        return None
    if argv[0] != "--track" or argv[2:] != ["--endpoint", _ENDPOINT_ARGUMENT]:
        return None
    try:
        return require_track(argv[1])
    except DriverProtocolError:
        return None


def main(argv: Sequence[str] | None = None) -> int:
    """Use only the fixed track and endpoint with binary standard streams."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    track = _parse_main_arguments(arguments)
    if track is None:
        return 2
    try:
        return execute_driver(
            track=track,
            stdin=sys.stdin.buffer,
            stdout=sys.stdout.buffer,
        )
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
