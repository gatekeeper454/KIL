"""Bounded local IO for exploratory HF work; no orchestration or recovery."""
import fcntl
from hashlib import sha256
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import time

from kil.hf_exploratory_inputs import read_regular, verify_bytes
from kil.v3b1_driver_protocol import parse_result
from kil.v3b2_contracts import TRACKS
from kil.v3b2_controller import CommandResult
from kil.v3b2_journal import Command
from kil.v3b2_profile_state import passwd_home
from kil.v3b2_proofs import canonical

MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_PRIVATE_TOTAL_BYTES = 256 * 1024 * 1024


def capture_process(argv, environment, stdin, timeout, maximum, cwd):
    """Capture a new owned session, retaining only a bounded output prefix."""
    if (type(argv) is not tuple or not argv or any(type(item) is not str or not item for item in argv)
            or type(environment) is not dict or any(type(k) is not str or type(v) is not str for k, v in environment.items())
            or (stdin is not None and type(stdin) is not bytes)
            or type(timeout) is not int or not 0 < timeout <= 900
            or type(maximum) is not int or not 0 < maximum <= MAX_OUTPUT_BYTES
            or not isinstance(cwd, Path) or not cwd.is_absolute()):
        raise ValueError('invalid_capture_parameters')
    process = subprocess.Popen(argv, cwd=cwd, env=environment,
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    selector = selectors.DefaultSelector()
    output = [bytearray(), bytearray()]
    pending = memoryview(stdin or b'')
    deadline = time.monotonic() + timeout
    failure = None
    def kill():
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        for index, stream in enumerate((process.stdout, process.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, index)
        if process.stdin is not None:
            if pending:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, 2)
            else:
                process.stdin.close()
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = -1000
                break
            for key, _ in selector.select(min(0.1, remaining)):
                if key.data == 2:
                    try:
                        count = os.write(key.fd, pending[:65536])
                        pending = pending[count:]
                    except BrokenPipeError:
                        pending = memoryview(b'')
                    except BlockingIOError:
                        continue
                    if not pending:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                else:
                    try:
                        chunk = os.read(key.fd, 65536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    available = maximum - sum(map(len, output))
                    output[key.data].extend(chunk[:available])
                    if len(chunk) > available:
                        failure = -1001
                        break
            if failure is not None:
                break
        if failure is not None:
            kill()
        try:
            process.wait(timeout=2 if failure is not None else max(0, deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            failure = -1000
            kill()
            process.wait(timeout=2)
    finally:
        selector.close()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        if process.poll() is None:
            kill()
            process.wait(timeout=2)
    raw_out, raw_err = map(bytes, output)
    return CommandResult(failure if failure is not None else process.returncode,
        raw_out.decode('utf-8', 'replace'), raw_err.decode('utf-8', 'replace'), raw_out, raw_err)


class BoundedRunner:
    """Dispatch only closed commands, with freshly verified retained tools."""
    def __init__(self, repository, inputs):
        self.repository = repository
        self.inputs = inputs
        self.global_docker_config = os.environ.get('DOCKER_CONFIG', str(passwd_home() / '.docker'))

    def run(self, command):
        if type(command) is not Command:
            raise ValueError('invalid_exploratory_command')
        command.__post_init__()
        environment = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL') if key in os.environ}
        environment['HOME'] = str(passwd_home())
        global_context = command.argv == ('docker', 'context', 'show')
        if global_context:
            environment['DOCKER_CONFIG'] = self.global_docker_config
        environment.update(command.env)
        if command.argv[0] == 'colima' and command.mutating and not command.env:
            raise ValueError('mutating_colima_requires_private_environment')
        if command.argv[0] in ('docker', 'kind') and not global_context:
            environment['TMPDIR'] = str(Path(dict(command.env)['DOCKER_CONFIG']).parent / 'runtime-tmp')
        argv = command.argv
        name = Path(argv[0]).name
        if name in self.inputs.tool_records:
            executable = self.inputs.tools / name
            row = self.inputs.tool_records[name]
            verify_bytes(read_regular(executable, 128 * 1024 * 1024),
                         row['executable_sha256'], row['byte_size'])
            argv = (str(executable), *argv[1:])
        return capture_process(argv, environment, command.stdin, command.timeout_s,
                               MAX_OUTPUT_BYTES, self.repository)


class PrivateStore:
    """Exclusive durable one-shot intent store, never a replay mechanism."""
    def __init__(self, path):
        if not isinstance(path, Path) or not path.is_absolute() or path.resolve() != path:
            raise ValueError('unsafe_private_store_path')
        self.path = path
        self.journal = path / 'journal.jsonl'
        self.total = 0
        self.attempts = []
        self.uncertain = False
        self._lock = None
        self._directory = None
        path.mkdir(mode=0o700)
        try:
            self._directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self._lock = os.open('lock', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
                                 dir_fd=self._directory)
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.record('created', {})
        except BaseException:
            self.close()
            raise

    def close(self):
        if self._lock is not None:
            os.close(self._lock)
            self._lock = None
        if self._directory is not None:
            os.close(self._directory)
            self._directory = None

    def _sync_parent(self):
        os.fsync(self._directory)

    def _bound(self, payload, maximum):
        if self._lock is None:
            raise ValueError('private_store_closed')
        if self.path.resolve(strict=True) != self.path:
            raise ValueError('private_store_reanchored')
        retained = os.fstat(self._directory)
        current = self.path.stat()
        if (retained.st_dev, retained.st_ino) != (current.st_dev, current.st_ino):
            raise ValueError('private_store_reanchored')
        if type(payload) is not bytes or len(payload) > maximum or self.total + len(payload) > MAX_PRIVATE_TOTAL_BYTES:
            raise ValueError('private_store_byte_bound')

    def write(self, name, payload):
        if type(name) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', name) is None:
            raise ValueError('unsafe_private_filename')
        self._bound(payload, MAX_OUTPUT_BYTES)
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
                     dir_fd=self._directory)
        try:
            with os.fdopen(os.dup(fd), 'wb') as stream:
                stream.write(payload)
                stream.flush()
            os.fsync(fd)
        finally:
            os.close(fd)
        self._sync_parent()
        self.total += len(payload)
        return sha256(payload).hexdigest()

    def record(self, event, details):
        payload = canonical({'event': event, 'details': details})
        self._bound(payload, 65536)
        fd = os.open('journal.jsonl', os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600,
                     dir_fd=self._directory)
        try:
            view = memoryview(payload)
            while view:
                count = os.write(fd, view)
                if count <= 0:
                    raise OSError('short_journal_write')
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        self._sync_parent()
        self.total += len(payload)

    def send_once(self, track, instruction, action):
        if self.uncertain or len(self.attempts) >= 3 or track != TRACKS[len(self.attempts)]:
            raise ValueError('request_sequence_or_uncertainty')
        self.uncertain = True
        self.attempts.append(track)
        digest = self.write(track + '.instruction.json', instruction)
        self.record('request_intent', {'track': track, 'instruction_sha256': digest})
        payload = action()
        result_digest = self.write(track + '.attach.stdout', payload)
        records = [parse_result(line + b'\n', expected_track=track) for line in payload.splitlines()]
        if (len(records) not in (1, 2) or (len(records) == 2 and records[0]['schema_version'] != 'kil.v3b1-driver-readiness.v1')
                or records[-1]['schema_version'] != 'kil.v3b1-driver-result.v1' or records[-1]['status'] != 'complete'):
            raise ValueError('request_terminal_uncertain')
        self.record('request_complete', {'track': track, 'result_sha256': result_digest})
        self.uncertain = False
        return records[-1]
