import importlib
import importlib.util
import json
from hashlib import sha256
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from kil.v3b1_driver_protocol import canonical_record
from kil.v3b2_contracts import TRACKS
from kil.v3b2_journal import Command
from kil.hf_exploratory_inputs import ACCEPTED_RUN, ACCEPTED_MANIFEST_SHA256, ExploratoryInputs, verify_bytes


def terminal(track):
    return canonical_record(dict(schema_version='kil.v3b1-driver-result.v1',
        track=track, status='complete', attempt_count=1, retry_performed=False,
        connect_monotonic_ns=1, send_monotonic_ns=2, receive_monotonic_ns=3,
        response_status=200, decision_digest='a' * 64))


class IOTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('kil.hf_exploratory_io'))
        self.io = importlib.import_module('kil.hf_exploratory_io')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def store(self):
        store = self.io.PrivateStore(Path(self.temp.name).resolve() / 'run')
        self.addCleanup(store.close)
        return store

    def accepted_inputs(self, tools=None):
        manifest = (Path.cwd() / 'artifacts/generated/v3b1-local-envoy' / ACCEPTED_RUN / 'manifest.json').read_bytes()
        verify_bytes(manifest, ACCEPTED_MANIFEST_SHA256, len(manifest))
        # Real frozen container; unused readiness fields are inert test placeholders.
        return ExploratoryInputs(None, b'', None, b'', tools or Path(self.temp.name).resolve(),
            json.loads(manifest)['verified_tool_identities'], manifest)

    def test_intent_precedes_action_and_no_repeat(self):
        store = self.store()
        calls = []
        def action():
            self.assertIn(b'request_intent', store.journal.read_bytes())
            calls.append(1)
            return terminal(TRACKS[0])
        self.assertEqual(store.send_once(TRACKS[0], b'instruction\n', action)['status'], 'complete')
        with self.assertRaises(ValueError):
            store.send_once(TRACKS[0], b'instruction\n', action)
        self.assertEqual(calls, [1])

    def test_callback_failure_blocks_next_track(self):
        store = self.store()
        def fail():
            raise RuntimeError('uncertain')
        with self.assertRaises(RuntimeError):
            store.send_once(TRACKS[0], b'instruction\n', fail)
        with self.assertRaises(ValueError):
            store.send_once(TRACKS[1], b'instruction\n', lambda: self.fail('called'))

    def test_private_path_and_exclusive_creation(self):
        store = self.store()
        with self.assertRaises(ValueError):
            store.write('../escape', b'x')
        with self.assertRaises(FileExistsError):
            self.io.PrivateStore(store.path)

    def test_capture_limits_and_timeout(self):
        result = self.io.capture_process((sys.executable, '-c', 'import sys;sys.stdout.write("x"*10000)'),
            {'PATH': os.environ['PATH']}, None, 5, 64, Path.cwd())
        self.assertEqual(result.returncode, -1001)
        self.assertLessEqual(len(result.stdout_bytes) + len(result.stderr_bytes), 64)
        result = self.io.capture_process((sys.executable, '-c', 'import time;time.sleep(5)'),
            {'PATH': os.environ['PATH']}, None, 1, 64, Path.cwd())
        self.assertEqual(result.returncode, -1000)

    def test_closed_store_rejects_writes(self):
        store = self.store()
        store.close()
        with self.assertRaises(ValueError):
            store.write('late', b'x')
        with self.assertRaises(ValueError):
            store.record('late', {})

    def test_capture_rejects_invalid_bounds(self):
        with self.assertRaises(ValueError):
            self.io.capture_process((sys.executable,), {}, None, 0, -1, Path.cwd())

    def test_runner_validates_before_capture(self):
        self.assertTrue(hasattr(self.io, 'BoundedRunner'))
        runner = self.io.BoundedRunner(Path.cwd(), self.accepted_inputs())
        with patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(object())
            command = Command(('docker', 'context', 'show'), 1)
            object.__setattr__(command, 'argv', ('sh', '-c', 'bad'))
            with self.assertRaises(ValueError):
                runner.run(command)
            capture.assert_not_called()

    def test_runner_rejects_executable_drift(self):
        self.assertTrue(hasattr(self.io, 'BoundedRunner'))
        tools = Path(self.temp.name).resolve() / '.tools' / 'bin'
        tools.mkdir(parents=True)
        executable = tools / 'docker'
        executable.write_bytes(b'drift')
        runner = self.io.BoundedRunner(Path.cwd(), self.accepted_inputs(tools))
        with patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(Command((str(executable), '--version'), 1))
            capture.assert_not_called()

    def test_store_rejects_parent_reanchor(self):
        store = self.store()
        moved = store.path.with_name('moved')
        store.path.rename(moved)
        store.path.symlink_to(moved, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            store.write('reanchor', b'x')
        self.assertFalse((moved / 'reanchor').exists())

    def test_malformed_terminal_keeps_uncertainty(self):
        store = self.store()
        with self.assertRaises(ValueError):
            store.send_once(TRACKS[0], b'instruction\n', lambda: b'not-json\n')
        with self.assertRaises(ValueError):
            store.send_once(TRACKS[1], b'instruction\n', lambda: self.fail('called'))

    def test_missing_lf_terminal_latches_uncertainty(self):
        store = self.store()
        with self.assertRaises(ValueError):
            store.send_once(TRACKS[0], b'instruction\n', lambda: terminal(TRACKS[0])[:-1])
        self.assertTrue(store.uncertain)
        with self.assertRaises(ValueError):
            store.send_once(TRACKS[1], b'instruction\n', lambda: self.fail('called'))

    def test_crlf_terminal_latches_uncertainty(self):
        store = self.store()
        with self.assertRaises(ValueError):
            store.send_once(TRACKS[0], b'instruction\n', lambda: terminal(TRACKS[0])[:-1] + b'\r\n')
        self.assertTrue(store.uncertain)
        with self.assertRaises(ValueError):
            store.send_once(TRACKS[1], b'instruction\n', lambda: self.fail('called'))

    def test_runner_rejects_mutable_matching_digest_override(self):
        inputs = self.accepted_inputs()
        runner = self.io.BoundedRunner(Path.cwd(), inputs)
        payload = b'test-owned replacement, never executed'
        (inputs.tools / 'docker').write_bytes(payload)
        inputs.tool_records['docker']['executable_sha256'] = sha256(payload).hexdigest()
        inputs.tool_records['docker']['byte_size'] = len(payload)
        with patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(Command(('docker', 'context', 'show'), 1))
            capture.assert_not_called()

    def test_runner_rejects_missing_records_before_path_fallback(self):
        inputs = self.accepted_inputs()
        inputs.tool_records.clear()
        runner = self.io.BoundedRunner(Path.cwd(), inputs)
        with patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(Command(('docker', 'context', 'show'), 1))
            capture.assert_not_called()

    def test_runner_rejects_substituted_manifest(self):
        inputs = self.accepted_inputs()
        object.__setattr__(inputs, 'manifest_bytes', b'{}\n')
        runner = self.io.BoundedRunner(Path.cwd(), inputs)
        with patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(Command(('colima', 'version'), 1))
            capture.assert_not_called()

    def test_runner_rejects_missing_or_malformed_authority(self):
        for metadata in (None, [], {'docker': {}}, {'docker': 'malformed'}):
            with self.subTest(metadata=metadata):
                inputs = self.accepted_inputs()
                object.__setattr__(inputs, 'tool_records', metadata)
                runner = self.io.BoundedRunner(Path.cwd(), inputs)
                with patch.object(self.io, 'capture_process') as capture:
                    with self.assertRaises(ValueError):
                        runner.run(Command(('docker', 'context', 'show'), 1))
                    capture.assert_not_called()

    def test_runner_reauthenticates_manifest_after_construction(self):
        inputs = self.accepted_inputs()
        runner = self.io.BoundedRunner(Path.cwd(), inputs)
        object.__setattr__(inputs, 'manifest_bytes', inputs.manifest_bytes + b' ')
        with patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(Command(('docker', 'context', 'show'), 1))
            capture.assert_not_called()

    def test_intent_fsync_failure_prevents_action(self):
        store = self.store()
        with patch.object(self.io.os, 'fsync', side_effect=[None, None, OSError('intent disk')]):
            with self.assertRaises(OSError):
                store.send_once(TRACKS[0], b'instruction\n', lambda: self.fail('called'))
        self.assertTrue(store.uncertain)

    def test_streaming_stdin_and_empty_eof(self):
        for payload in (b'', b'payload' * 20000):
            result = self.io.capture_process((sys.executable, '-c', 'import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())'),
                {'PATH': os.environ['PATH']}, payload, 5, 200000, Path.cwd())
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout_bytes, payload)

    def test_three_tracks_and_no_fourth(self):
        store = self.store()
        for track in TRACKS:
            store.send_once(track, b'instruction\n', lambda track=track: terminal(track))
        with self.assertRaises(ValueError):
            store.send_once(TRACKS[0], b'instruction\n', lambda: self.fail('called'))

    def test_constructor_failure_closes_lock(self):
        descriptors = []
        real_open = self.io.os.open
        def opened(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            descriptors.append(fd)
            return fd
        with patch.object(self.io.os, 'open', side_effect=opened), patch.object(self.io.os, 'fsync', side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                self.io.PrivateStore(Path(self.temp.name).resolve() / 'run')
        for fd in descriptors:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_runner_sanitizes_environment_and_version_read(self):
        tools = Path(self.temp.name).resolve() / '.tools' / 'bin'
        tools.mkdir(parents=True)
        payload = b'test-owned identity only'
        (tools / 'docker').write_bytes(payload)
        inputs = self.accepted_inputs(tools)
        real_verify = self.io.verify_bytes
        def dispatch_only_verify(data, digest, size):
            # Manifest authority uses the real check; only dummy binary IO is isolated.
            if digest == ACCEPTED_MANIFEST_SHA256:
                return real_verify(data, digest, size)
            self.assertEqual(data, payload)
            self.assertEqual(digest, inputs.tool_records['docker']['executable_sha256'])
            self.assertEqual(size, inputs.tool_records['docker']['byte_size'])
            return digest
        with patch.dict(os.environ, {'DOCKER_CONFIG': '/global-config', 'HOME': '/untrusted', 'EXTRA_AUTHORITY': 'no'}):
            runner = self.io.BoundedRunner(Path.cwd(), inputs)
            with patch.object(self.io, 'verify_bytes', side_effect=dispatch_only_verify), patch.object(self.io, 'capture_process') as capture:
                runner.run(Command((str(tools / 'docker'), '--version'), 1))
                argv, env, _, _, _, _ = capture.call_args.args
                self.assertEqual(argv[0], str(tools / 'docker'))
                self.assertNotIn('DOCKER_CONFIG', env)
                self.assertNotIn('TMPDIR', env)
                self.assertNotIn('EXTRA_AUTHORITY', env)
                self.assertEqual(env['HOME'], str(self.io.passwd_home()))
                runner.run(Command(('docker', 'context', 'show'), 1))
                self.assertEqual(capture.call_args.args[1]['DOCKER_CONFIG'], '/global-config')

    def test_runner_requires_colima_private_environment(self):
        runner = self.io.BoundedRunner(Path.cwd(), self.accepted_inputs())
        with patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(Command(('colima', 'stop', '--profile', 'kil-v3-lab'), 1, mutating=True))
            capture.assert_not_called()

    def test_capture_aggregate_output_and_nonzero_exit(self):
        result = self.io.capture_process((sys.executable, '-c', 'import sys;sys.stdout.write("x"*40);sys.stdout.flush();sys.stderr.write("y"*40)'),
            {}, None, 5, 64, Path.cwd())
        self.assertEqual(result.returncode, -1001)
        self.assertEqual(len(result.stdout_bytes) + len(result.stderr_bytes), 64)
        result = self.io.capture_process((sys.executable, '-c', 'import sys;sys.exit(7)'),
            {}, b'x' * 200000, 5, 64, Path.cwd())
        self.assertEqual(result.returncode, 7)

    def test_capture_wait_is_bounded_after_output_eof(self):
        result = self.io.capture_process((sys.executable, '-c', 'import os,time;os.close(1);os.close(2);time.sleep(5)'),
            {}, None, 1, 64, Path.cwd())
        self.assertEqual(result.returncode, -1000)

    def test_private_permissions_symlinks_and_quotas(self):
        store = self.store()
        self.assertEqual(store.path.stat().st_mode & 0o777, 0o700)
        store.write('small', b'x')
        self.assertEqual((store.path / 'small').stat().st_mode & 0o777, 0o600)
        (store.path / 'linked').symlink_to(store.path / 'small')
        with self.assertRaises(FileExistsError):
            store.write('linked', b'bad')
        self.assertEqual((store.path / 'small').read_bytes(), b'x')
        with self.assertRaises(ValueError):
            store.write('large', b'x' * (self.io.MAX_OUTPUT_BYTES + 1))
        store.total = self.io.MAX_PRIVATE_TOTAL_BYTES
        with self.assertRaises(ValueError):
            store.write('quota', b'x')
        with self.assertRaises(ValueError):
            store.record('quota', {})
