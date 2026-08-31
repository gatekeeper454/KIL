"""Bounded host-side transport for attached V3B-1 request drivers."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import queue
import selectors
import subprocess
import threading
from typing import BinaryIO, Callable, Mapping, Protocol, Sequence

from kil.v3b1_driver_protocol import MAX_RESULT_BYTES


class DriverTransportError(RuntimeError):
    """Closed driver-control failure that never retains process output."""

    def __init__(self, category: str) -> None:
        super().__init__(f"driver transport failed: {category}")
        self.category = category


class DriverProcess(Protocol):
    stdin: BinaryIO
    stdout: BinaryIO
    stderr: BinaryIO

    def poll(self) -> int | None: ...

    def wait(self, timeout: float) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


class DriverProcessFactory(Protocol):
    def start(self, command: Sequence[str]) -> DriverProcess: ...


class SubprocessDriverProcessFactory:
    """Start exact argv vectors with binary standard-stream pipes."""

    def __init__(
        self,
        *,
        cwd: Path,
        env: Mapping[str, str],
    ) -> None:
        self.cwd = cwd
        self.env = dict(env)

    def start(self, command: Sequence[str]) -> DriverProcess:
        argv = list(command)
        if not argv or any(type(part) is not str or not part for part in argv):
            raise DriverTransportError("invalid_command")
        try:
            process = subprocess.Popen(
                argv,
                cwd=self.cwd,
                env=self.env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                text=False,
                shell=False,
            )
        except (OSError, ValueError):
            raise DriverTransportError("process_start") from None
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise DriverTransportError("pipe_unavailable")
        return process


@dataclass(slots=True)
class DriverSession:
    track: str
    full_id: str
    process: DriverProcess
    pending_stdout: bytearray = field(default_factory=bytearray)
    read_worker: threading.Thread | None = None
    read_result: queue.Queue[tuple[bytes | None, str | None]] = field(
        default_factory=lambda: queue.Queue(maxsize=1)
    )


@dataclass(frozen=True, slots=True)
class DriverCleanupResult:
    outcome: str
    exit_code: int


def start_attached_driver(
    factory: DriverProcessFactory,
    *,
    docker_binary: str,
    track: str,
    full_id: str,
) -> DriverSession:
    """Start one exact stopped container and retain its attached process."""
    if (
        type(docker_binary) is not str
        or not docker_binary
        or type(track) is not str
        or not track
        or type(full_id) is not str
        or len(full_id) != 64
        or any(character not in "0123456789abcdef" for character in full_id)
    ):
        raise DriverTransportError("invalid_identity")
    command = [
        docker_binary,
        "start",
        "--attach",
        "--interactive",
        full_id,
    ]
    try:
        process = factory.start(command)
    except DriverTransportError:
        raise
    except Exception:
        raise DriverTransportError("process_start") from None
    for name in ("stdin", "stdout", "stderr"):
        if not hasattr(process, name):
            raise DriverTransportError("pipe_unavailable")
    return DriverSession(track=track, full_id=full_id, process=process)


def remaining_seconds(
    deadline_ns: int,
    monotonic_ns: Callable[[], int],
) -> float:
    """Return the positive remainder of one controller-owned deadline."""
    try:
        now = monotonic_ns()
    except Exception:
        raise DriverTransportError("clock_failure") from None
    if type(now) is not int or now < 0 or type(deadline_ns) is not int:
        raise DriverTransportError("clock_failure")
    remaining = deadline_ns - now
    if remaining <= 0:
        raise DriverTransportError("deadline_expired")
    return remaining / 1_000_000_000


def _readline_without_fileno(
    session: DriverSession,
    deadline_ns: int,
    monotonic_ns: Callable[[], int],
) -> bytes:
    """Bound a protocol-conforming stream without relying on ``fileno``."""

    def read_once() -> None:
        try:
            payload = session.process.stdout.readline(MAX_RESULT_BYTES + 1)
        except Exception:
            result: tuple[bytes | None, str | None] = (None, "stdout_read")
        else:
            result = (
                (payload, None)
                if type(payload) is bytes
                else (None, "stdout_read")
            )
        try:
            session.read_result.put_nowait(result)
        except queue.Full:
            return

    worker = threading.Thread(
        target=read_once,
        name=f"kil-v3b1-driver-read-{session.track}",
        daemon=True,
    )
    session.read_worker = worker
    worker.start()
    while True:
        timeout = min(remaining_seconds(deadline_ns, monotonic_ns), 0.01)
        try:
            payload, category = session.read_result.get(timeout=timeout)
        except queue.Empty:
            continue
        worker.join(timeout=0)
        session.read_worker = None
        if category is not None or payload is None:
            raise DriverTransportError(category or "stdout_read")
        return payload


def _readline_with_selector(
    session: DriverSession,
    deadline_ns: int,
    monotonic_ns: Callable[[], int],
) -> bytes:
    stream = session.process.stdout
    try:
        descriptor = stream.fileno()
    except (AttributeError, OSError, ValueError):
        return _readline_without_fileno(session, deadline_ns, monotonic_ns)
    if type(descriptor) is not int or descriptor < 0:
        raise DriverTransportError("stdout_read")
    selector = selectors.DefaultSelector()
    try:
        selector.register(descriptor, selectors.EVENT_READ)
        while b"\n" not in session.pending_stdout:
            timeout = remaining_seconds(deadline_ns, monotonic_ns)
            if not selector.select(timeout):
                raise DriverTransportError("deadline_expired")
            try:
                chunk = os.read(
                    descriptor,
                    MAX_RESULT_BYTES + 1 - len(session.pending_stdout),
                )
            except OSError:
                raise DriverTransportError("stdout_read") from None
            if not chunk:
                raise DriverTransportError("stdout_eof")
            session.pending_stdout.extend(chunk)
            if len(session.pending_stdout) > MAX_RESULT_BYTES:
                raise DriverTransportError("stdout_oversize")
    finally:
        selector.close()
    newline = session.pending_stdout.index(0x0A) + 1
    payload = bytes(session.pending_stdout[:newline])
    del session.pending_stdout[:newline]
    return payload


def read_readiness_record(
    session: DriverSession,
    *,
    deadline_ns: int,
    monotonic_ns: Callable[[], int],
) -> bytes:
    """Read one bounded readiness line under the shared session deadline."""
    remaining_seconds(deadline_ns, monotonic_ns)
    payload = _readline_with_selector(session, deadline_ns, monotonic_ns)
    remaining_seconds(deadline_ns, monotonic_ns)
    if (
        not payload
        or len(payload) > MAX_RESULT_BYTES
        or not payload.endswith(b"\n")
        or payload.count(b"\n") != 1
    ):
        raise DriverTransportError("readiness_framing")
    return payload


def close_instruction_stream(session: DriverSession) -> None:
    """Deliver the sole pre-instruction cancellation signal: stdin EOF."""
    try:
        session.process.stdin.close()
    except Exception:
        raise DriverTransportError("stdin_close") from None
    if not getattr(session.process.stdin, "closed", False):
        raise DriverTransportError("stdin_close_ambiguous")


def _read_remainder(stream: BinaryIO, limit: int) -> bytes:
    try:
        payload = stream.read(limit + 1)
    except Exception:
        raise DriverTransportError("pipe_read") from None
    if type(payload) is not bytes or len(payload) > limit:
        raise DriverTransportError("pipe_oversize")
    return payload


def attest_cancelled_exit(
    session: DriverSession,
    *,
    deadline_ns: int,
    monotonic_ns: Callable[[], int],
) -> int:
    """Require exact EOF, empty stderr, and the fixed successful exit status."""
    timeout = remaining_seconds(deadline_ns, monotonic_ns)
    try:
        returncode = session.process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        raise DriverTransportError("process_wait_timeout") from None
    except Exception:
        raise DriverTransportError("process_wait") from None
    remaining_seconds(deadline_ns, monotonic_ns)
    try:
        polled = session.process.poll()
    except Exception:
        raise DriverTransportError("process_poll") from None
    if (
        type(returncode) is not int
        or type(polled) is not int
        or polled != returncode
    ):
        raise DriverTransportError("termination_ambiguous")
    stdout = bytes(session.pending_stdout)
    session.pending_stdout.clear()
    stdout += _read_remainder(session.process.stdout, MAX_RESULT_BYTES - len(stdout))
    stderr = _read_remainder(session.process.stderr, MAX_RESULT_BYTES)
    if stdout:
        raise DriverTransportError("extra_stdout")
    if stderr:
        raise DriverTransportError("stderr_present")
    if returncode != 0:
        raise DriverTransportError("nonzero_exit")
    return returncode


def cleanup_driver_process(
    session: DriverSession,
    *,
    deadline_ns: int,
    monotonic_ns: Callable[[], int],
) -> DriverCleanupResult:
    """Terminate, kill if necessary, and reap one failed attached process."""
    try:
        if not getattr(session.process.stdin, "closed", False):
            session.process.stdin.close()
    except Exception:
        pass
    try:
        initial = session.process.poll()
    except Exception:
        initial = None
    outcome = "already_exited"
    if type(initial) is not int:
        outcome = "terminated"
        try:
            session.process.terminate()
        except Exception:
            outcome = "killed"
            try:
                session.process.kill()
            except Exception:
                raise DriverTransportError("cleanup_kill") from None
    try:
        returncode = session.process.wait(
            timeout=min(1.0, remaining_seconds(deadline_ns, monotonic_ns))
        )
    except (subprocess.TimeoutExpired, DriverTransportError):
        outcome = "killed"
        try:
            session.process.kill()
            returncode = session.process.wait(
                timeout=remaining_seconds(deadline_ns, monotonic_ns)
            )
        except subprocess.TimeoutExpired:
            raise DriverTransportError("cleanup_wait_timeout") from None
        except DriverTransportError:
            raise
        except Exception:
            raise DriverTransportError("cleanup_wait") from None
    except Exception:
        outcome = "killed"
        try:
            session.process.kill()
            returncode = session.process.wait(
                timeout=remaining_seconds(deadline_ns, monotonic_ns)
            )
        except subprocess.TimeoutExpired:
            raise DriverTransportError("cleanup_wait_timeout") from None
        except DriverTransportError:
            raise
        except Exception:
            raise DriverTransportError("cleanup_wait") from None
    try:
        polled = session.process.poll()
    except Exception:
        raise DriverTransportError("cleanup_poll") from None
    if type(returncode) is not int or type(polled) is not int or polled != returncode:
        raise DriverTransportError("cleanup_ambiguous")
    for stream in (session.process.stdout, session.process.stderr):
        try:
            stream.close()
        except Exception:
            raise DriverTransportError("cleanup_pipe_close") from None
    worker = session.read_worker
    if worker is not None:
        worker.join(timeout=remaining_seconds(deadline_ns, monotonic_ns))
        if worker.is_alive():
            raise DriverTransportError("cleanup_read_worker")
        session.read_worker = None
    return DriverCleanupResult(outcome=outcome, exit_code=returncode)
