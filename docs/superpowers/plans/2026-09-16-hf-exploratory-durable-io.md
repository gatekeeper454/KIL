# Exploratory HF durable IO Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide bounded command capture and durable one-shot request intent for the approved exploratory lifecycle.

**Architecture:** This second independently testable unit contains no lab orchestration. It consumes verified inputs, validates the existing closed Command grammar, rechecks executable bytes, sanitizes inherited execution authority and retains bounded process outputs. A private exclusive store persists exact instruction bytes and request intent before execution and permanently latches an uncertain request against all subsequent instructions.

**Tech Stack:** Python 3.12 selectors/subprocess/fcntl/fsync, existing Command and driver protocol, unittest.

---

Approved design: docs/superpowers/specs/2026-09-16-hf-exploratory-kind-calico-design.md. Preserve strict production code and platform-image audit stop. No native lab command or download in this unit. Native lifecycle follows separate review. Existing linked worktree is retained.

## Task 1: Bounded process boundary and exclusive store

Files: create src/kil/hf_exploratory_io.py and tests/test_hf_exploratory_io.py. Dependency: kil.hf_exploratory_inputs, implemented under the first plan. No existing production-file edit.

- [ ] Write these tests first:

```python
import importlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from kil.v3b1_driver_protocol import canonical_record
from kil.v3b2_contracts import TRACKS


def terminal(track):
    return canonical_record({
        'schema_version': 'kil.v3b1-driver-result.v1', 'track': track,
        'status': 'complete', 'attempt_count': 1, 'retry_performed': False,
        'connect_monotonic_ns': 1, 'send_monotonic_ns': 2,
        'receive_monotonic_ns': 3, 'response_status': 200,
        'decision_digest': 'a' * 64,
    })


class ExploratoryIOTest(unittest.TestCase):
    def setUp(self):
        name = 'kil.hf_exploratory_io'
        self.assertIsNotNone(importlib.util.find_spec(name), 'exploratory IO missing')
        self.module = importlib.import_module(name)

    def test_intent_precedes_action_and_track_never_repeats(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.module.PrivateStore(Path(directory).resolve() / 'run')
            observed = []
            def action():
                observed.append(store.journal.read_bytes())
                return terminal(TRACKS[0])
            store.send_once(TRACKS[0], b'instruction\n', action)
            self.assertIn(b'request_intent', observed[0])
            with self.assertRaises(ValueError):
                store.send_once(TRACKS[0], b'instruction\n', action)
            self.assertEqual(len(observed), 1)
            store.close()

    def test_uncertain_request_prevents_later_track(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.module.PrivateStore(Path(directory).resolve() / 'run')
            def fail():
                raise RuntimeError('uncertain')
            with self.assertRaises(RuntimeError):
                store.send_once(TRACKS[0], b'instruction\n', fail)
            with self.assertRaises(ValueError):
                store.send_once(TRACKS[1], b'instruction\n', lambda: terminal(TRACKS[1]))
            store.close()

    def test_store_refuses_existing_directory_and_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'run'
            store = self.module.PrivateStore(path)
            with self.assertRaises(ValueError):
                store.write('../escape', b'x')
            with self.assertRaises(FileExistsError):
                self.module.PrivateStore(path)
            store.close()

    def test_bounded_capture_retains_overflow_prefix_and_timeout(self):
        capture = self.module.capture_process
        env = {'PATH': os.environ.get('PATH', '')}
        row = capture((sys.executable, '-c', 'import sys; sys.stdout.write("x"*10000)'),
                      env, None, 5, 64, Path.cwd())
        self.assertEqual(row.returncode, -1001)
        self.assertLessEqual(len(row.stdout_bytes) + len(row.stderr_bytes), 64)
        row = capture((sys.executable, '-c', 'import time; time.sleep(5)'),
                      env, None, 1, 64, Path.cwd())
        self.assertEqual(row.returncode, -1000)


if __name__ == '__main__':
    unittest.main()
```

- [ ] Run RED:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' -m unittest tests.test_hf_exploratory_io -v
```

Expected: four missing-module assertion failures. These test processes are harmless local children, not Colima/Docker/Kind/kubectl.

- [ ] Implement this complete unit:

```python
"""Bounded IO and nonreplayable intent for private exploratory HF runs."""
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


def _kill_owned_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def capture_process(argv, environment, stdin, timeout, maximum, cwd):
    process = subprocess.Popen(argv, cwd=cwd, env=environment,
                               stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    selector = selectors.DefaultSelector()
    buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    pending = memoryview(b'' if stdin is None else stdin)
    deadline = time.monotonic() + timeout
    failure = None
    try:
        for stream, name in ((process.stdout, 'stdout'), (process.stderr, 'stderr')):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        if process.stdin is not None:
            if pending:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, 'stdin')
            else:
                process.stdin.close()
        while selector.get_map():
            if time.monotonic() >= deadline:
                failure = -1000
                break
            for key, event in selector.select(min(0.1, max(0, deadline - time.monotonic()))):
                if key.data == 'stdin':
                    try:
                        written = os.write(key.fd, pending[:65536])
                        pending = pending[written:]
                    except BrokenPipeError:
                        pending = memoryview(b'')
                    if not pending:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                else:
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    remaining = maximum - sum(len(value) for value in buffers.values())
                    buffers[key.data].extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        failure = -1001
                        break
            if failure is not None:
                break
        if failure is not None:
            _kill_owned_group(process)
        process.wait(timeout=2 if failure is not None else max(0.1, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        failure = -1000
        _kill_owned_group(process)
        process.wait(timeout=2)
    finally:
        selector.close()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        if process.poll() is None:
            _kill_owned_group(process)
            process.wait(timeout=2)
    out, err = bytes(buffers['stdout']), bytes(buffers['stderr'])
    return CommandResult(process.returncode if failure is None else failure,
                         out.decode('utf-8', errors='replace'), err.decode('utf-8', errors='replace'), out, err)


class BoundedRunner:
    def __init__(self, repository, inputs):
        self.repository, self.inputs = repository, inputs
        self.global_docker_config = os.environ.get('DOCKER_CONFIG', str(passwd_home() / '.docker'))

    def run(self, command):
        if type(command) is not Command:
            raise ValueError('invalid_exploratory_command')
        command.__post_init__()
        env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL') if key in os.environ}
        env['HOME'] = str(passwd_home())
        if command.argv == ('docker', 'context', 'show'):
            env['DOCKER_CONFIG'] = self.global_docker_config
        env.update(dict(command.env))
        if command.argv[0] == 'colima' and command.mutating and not command.env:
            raise ValueError('missing_private_colima_environment')
        if command.argv[0] in {'docker', 'kind'} and command.argv != ('docker', 'context', 'show'):
            env['TMPDIR'] = str(Path(dict(command.env)['DOCKER_CONFIG']).parent / 'runtime-tmp')
        argv = command.argv
        name = Path(argv[0]).name
        if name in self.inputs.tool_records:
            binary = self.inputs.tools / name
            row = self.inputs.tool_records[name]
            verify_bytes(read_regular(binary, 128 * 1024 * 1024), row['executable_sha256'], row['byte_size'])
            argv = (str(binary), *argv[1:])
        return capture_process(argv, env, command.stdin, command.timeout_s,
                               MAX_OUTPUT_BYTES, self.repository)


class PrivateStore:
    def __init__(self, path):
        if not isinstance(path, Path) or not path.is_absolute() or path.resolve() != path:
            raise ValueError('invalid_private_store')
        path.mkdir(mode=0o700)
        self.path, self.journal = path, path / 'journal.jsonl'
        self.total = 0
        self.attempts, self.uncertain = [], False
        self.lock = os.open(path / 'lock', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.record('created', {})

    def close(self):
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None

    def write(self, name, payload):
        if (type(name) is not str or re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,127}', name) is None
                or type(payload) is not bytes or len(payload) > MAX_OUTPUT_BYTES
                or self.total + len(payload) > MAX_PRIVATE_TOTAL_BYTES):
            raise ValueError('private_evidence_path_or_bound')
        fd = os.open(self.path / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(os.dup(fd), 'wb') as stream:
                stream.write(payload)
                stream.flush()
            os.fsync(fd)
        finally:
            os.close(fd)
        parent = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        self.total += len(payload)
        return sha256(payload).hexdigest()

    def record(self, event, details):
        payload = canonical({'event': event, 'details': details})
        if len(payload) > 65536 or self.total + len(payload) > MAX_PRIVATE_TOTAL_BYTES:
            raise ValueError('private_journal_bound')
        fd = os.open(self.journal, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        try:
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError('short_journal_write')
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        parent = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        self.total += len(payload)

    def send_once(self, track, instruction, action):
        if self.uncertain or len(self.attempts) >= 3 or track != TRACKS[len(self.attempts)]:
            raise ValueError('request_sequence_or_uncertainty')
        self.uncertain = True
        self.attempts.append(track)
        digest = self.write(track + '.instruction.json', instruction)
        self.record('request_intent', {'track': track, 'instruction_sha256': digest})
        payload = action()
        self.write(track + '.attach.stdout', payload)
        records = [parse_result(line + b'\n', expected_track=track) for line in payload.splitlines()]
        if (len(records) not in (1, 2)
                or len(records) == 2 and records[0]['schema_version'] != 'kil.v3b1-driver-readiness.v1'
                or records[-1]['schema_version'] != 'kil.v3b1-driver-result.v1'
                or records[-1].get('status') != 'complete'):
            raise ValueError('request_terminal_uncertain')
        self.record('request_complete', {'track': track, 'result_sha256': sha256(payload).hexdigest()})
        self.uncertain = False
        return records[-1]
```

- [ ] Run GREEN using the same unittest command; expected four tests pass. Add tests for malformed terminals, intent fsync failure preventing action, output stdin streaming, command-grammar rejection and executable drift before the corresponding fixes.
- [ ] Specification review then independent quality review; no native lifecycle invocation. Correct any identified race, bounds or resource leak through tests first.
- [ ] Commit only module, tests and required lineage/readers after fresh tests and diff checks. Suggested message: feat: add bounded exploratory HF command and intent IO.

## Limits and handoff

Per-command output is 8 MiB aggregate, marked incomplete by -1001 on overflow and -1000 on timeout; neither is successful. Existing Command limits each invocation to at most 900 seconds and stdin to its operation-specific bound. Private retained aggregate is 256 MiB. Application ledgers use their smaller 1 MiB capture bound at the later evidence unit. No unlimited retries or inferred completion. The lifecycle must create an exact private run destination, hold a profile-scoped lock, journal mutations before dispatch, bind native profile/node/cluster incarnations, and stop cleanup if identities cannot be established. It must not invoke requests from recovery. A request-free rehearsal sends empty EOF cancellation, not an instruction through send_once.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
