import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/hf_recovery_parent_permissions.py'
SOURCE = 'a' * 40
APPROVAL = 'fixture-only permission test'

def load_tool():
    if not TOOL.is_file():
        raise AssertionError('fixed permission tool is missing')
    spec = importlib.util.spec_from_file_location('hf_permission_fixture', TOOL)
    if spec is None or spec.loader is None:
        raise AssertionError('fixed permission tool is not loadable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class Fixture(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()
        self.temp = tempfile.TemporaryDirectory(prefix='kil-mode-', dir='/private/tmp')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.tools = self.root / '.tools'
        self.target = self.tools / 'hf-recovery-private'
        self.lock_parent = self.tools / 'hf-exploratory-private'
        self.tools.mkdir(mode=0o700)
        self.target.mkdir(mode=0o755)
        self.target.chmod(0o755)
        self.lock_parent.mkdir(mode=0o700)
        self.lock = self.lock_parent / 'profile.lock'
        self.lock.write_bytes(b'cooperating fixture lock\n')
        self.lock.chmod(0o600)
        self.receipt = self.target / 'retained'
        self.receipt.mkdir(mode=0o700)
        self.payload = self.receipt / 'outcome.json'
        self.seal = self.receipt / 'SHA256SUMS'
        self.payload.write_bytes(b'{"historical":true}\n')
        self.seal.write_bytes(b'exact historical seal\n')
        self.payload.chmod(0o600)
        self.seal.chmod(0o600)
        self.original_payload = self.payload.read_bytes()
        self.original_seal = self.seal.read_bytes()
        self.original_modes = [stat.S_IMODE(p.stat().st_mode) for p in (self.receipt, self.payload, self.seal)]
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in {'REPOSITORY': self.root, 'TARGET': self.target, 'UID': os.geteuid(), 'TOOLS_PIN': (self.tools.stat().st_dev, self.tools.stat().st_ino), 'TARGET_PIN': (self.target.stat().st_dev, self.target.stat().st_ino)}.items():
            self.stack.enter_context(patch.object(self.tool, name, value))
    def unchanged_receipts(self):
        self.assertEqual(self.payload.read_bytes(), self.original_payload)
        self.assertEqual(self.seal.read_bytes(), self.original_seal)
        self.assertEqual([stat.S_IMODE(p.stat().st_mode) for p in (self.receipt, self.payload, self.seal)], self.original_modes)
    def run_fixture(self, *, source=None, account=None):
        with patch.object(self.tool, '_source', side_effect=source), patch.object(self.tool, '_account', side_effect=account):
            return self.tool._run(SOURCE, APPROVAL)
    def assert_refused(self, result):
        self.assertEqual(result['outcome'], 'preflight_refused')
        self.assertEqual(result['fchmod_attempts'], 0)
        self.assertFalse(result['preservation'])
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o755)

class AncestryTests(Fixture):
    def test_real_named_fd_ancestry_and_all_descriptors_close(self):
        dirs = self.tool._Directories()
        self.addCleanup(dirs.close)
        fd = dirs.directory(self.target)
        dirs.guard()
        self.assertEqual(os.fstat(fd).st_ino, self.target.stat().st_ino)
        descriptors = [record[1] for record in dirs.records.values()]
        self.assertEqual(dirs.close(), [])
        self.assertEqual(dirs.close(), [])
        for descriptor in descriptors:
            with self.assertRaises(OSError): os.fstat(descriptor)
        with self.assertRaises(ValueError): dirs.guard()
        self.unchanged_receipts()
    def test_real_ancestor_reanchor_and_symlink_refuse(self):
        dirs = self.tool._Directories()
        self.addCleanup(dirs.close)
        dirs.directory(self.target)
        moved = self.root / 'moved-tools'
        self.tools.rename(moved)
        self.tools.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(ValueError): dirs.guard()
        fresh = self.tool._Directories()
        self.addCleanup(fresh.close)
        with self.assertRaises(OSError): fresh.directory(self.target)
    def test_target_replacement_or_mode_change_is_not_adopted(self):
        dirs = self.tool._Directories()
        self.addCleanup(dirs.close)
        dirs.directory(self.target)
        self.target.chmod(0o700)
        with self.assertRaises(ValueError): dirs.guard()
        self.target.chmod(0o755)
        self.target.rename(self.tools / 'original-target')
        self.target.mkdir(mode=0o755)
        with self.assertRaises(ValueError): dirs.guard()
    def test_after_guard_rejects_unapproved_initial_target_modes(self):
        for initial_mode in (0o705, 0o777, 0o700):
            self.target.chmod(initial_mode)
            dirs = self.tool._Directories()
            try:
                dirs.directory(self.target)
                self.target.chmod(0o700)
                with self.assertRaises(ValueError): dirs.guard(after=True)
            finally:
                dirs.close()

    def test_after_guard_allows_only_captured_755_to_700(self):
        self.target.chmod(0o755)
        dirs = self.tool._Directories()
        try:
            dirs.directory(self.target)
            captured = {path: record[2] for path, record in dirs.records.items()}
            self.target.chmod(0o700)
            dirs.guard(after=True)
            self.assertEqual(captured, {path: record[2] for path, record in dirs.records.items()})
        finally:
            dirs.close()

class ProofTests(Fixture):
    def proof(self):
        proof = self.tool._Proof()
        self.addCleanup(proof.close)
        proof.bind()
        return proof
    def test_existing_lock_and_equal_observations_without_child_reads(self):
        original_pread = os.pread
        reads = []
        def read(fd, maximum, offset):
            reads.append(os.fstat(fd).st_ino)
            return original_pread(fd, maximum, offset)
        with patch.object(self.tool.os, 'pread', side_effect=read):
            proof = self.proof()
            proof.observe()
            proof.metadata()
        self.assertTrue(reads)
        self.assertEqual(set(reads), {self.lock.stat().st_ino})
        self.assertEqual(len(proof.children), 1)
        self.unchanged_receipts()
    def test_missing_lock_refuses_and_does_not_create_it(self):
        self.lock.unlink()
        proof = self.tool._Proof()
        self.addCleanup(proof.close)
        with self.assertRaises(FileNotFoundError): proof.bind()
        self.assertFalse(self.lock.exists())
    def test_busy_lock_refuses_using_real_flock(self):
        import fcntl
        fd = os.open(self.lock, os.O_RDONLY | os.O_NOFOLLOW)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        proof = self.tool._Proof()
        self.addCleanup(proof.close)
        with self.assertRaises(BlockingIOError): proof.bind()
    def test_wrong_pins_owner_and_initial_modes_refuse(self):
        cases = [dict(TARGET_PIN=(0, 0)), dict(TOOLS_PIN=(0, 0)), dict(UID=os.geteuid() + 1)]
        for changes in cases:
            with self.subTest(changes=changes), ExitStack() as stack:
                for name, value in changes.items(): stack.enter_context(patch.object(self.tool, name, value))
                proof = self.tool._Proof()
                try:
                    with self.assertRaises(ValueError): proof.bind()
                finally: proof.close()
        for mode in (0o700, 0o750, 0o777, 0o1755):
            with self.subTest(mode=mode):
                self.target.chmod(mode)
                proof = self.tool._Proof()
                try:
                    with self.assertRaises(ValueError): proof.bind()
                finally: proof.close()
    def test_lock_metadata_bytes_and_replacement_are_not_adopted(self):
        proof = self.proof()
        self.lock.write_bytes(b'changed cooperating lock\n')
        with self.assertRaises(ValueError): proof.observe()
        self.lock.rename(self.lock_parent / 'old-lock')
        self.lock.write_bytes(b'cooperating fixture lock\n')
        self.lock.chmod(0o600)
        with self.assertRaises(ValueError): proof.metadata()
    def test_children_drift_refuses_without_descendant_interpretation(self):
        proof = self.proof()
        self.receipt.chmod(0o755)
        with self.assertRaises(ValueError): proof.observe()
        other = self.tools / 'outside'
        other.write_bytes(b'never opened by proof')
        (self.target / 'pointer').symlink_to(other)
        with self.assertRaises(ValueError): proof.observe()
    def test_256_names_pass_and_257_or_oversized_name_refuse(self):
        for index in range(255): (self.target / ('n' + str(index))).mkdir(mode=0o700)
        proof = self.tool._Proof()
        try:
            proof.bind()
            self.assertEqual(len(proof.children), 256)
        finally:
            proof.close()
        (self.target / 'n255').mkdir(mode=0o700)
        fresh = self.tool._Proof()
        try:
            with self.assertRaisesRegex(ValueError, 'permission_children_bound_or_name'):
                fresh.bind()
        finally:
            fresh.close()
        (self.target / 'n255').rmdir()
        for index in range(255): (self.target / ('n' + str(index))).rmdir()
        (self.target / ('x' * 129)).mkdir(mode=0o700)
        fresh = self.tool._Proof()
        try:
            with self.assertRaisesRegex(ValueError, 'permission_children_bound_or_name'):
                fresh.bind()
        finally:
            fresh.close()

    def test_post_metadata_requires_validated_baseline(self):
        proof = self.proof()
        os.fchmod(proof.target, 0o700)
        os.utime(self.target, ns=(self.target.stat().st_atime_ns, proof.before[7] + 1000000000))
        for method in ('metadata', 'observe'):
            with self.subTest(method=method):
                with self.assertRaisesRegex(ValueError, 'permission_post_baseline_unavailable'):
                    getattr(proof, method)(after=True)

    def test_validated_post_transition_preserves_commitments(self):
        proof = self.proof()
        try:
            os.fchmod(proof.target, 0o700)
            proof.bind_post()
            proof.metadata(after=True)
            proof.observe(after=True)
            self.assertEqual(len(proof.children), 1)
            self.unchanged_receipts()
        finally:
            proof.close()

class AttemptTests(Fixture):
    def test_one_real_fchmod_then_reentry_refuses_without_rollback(self):
        fd = os.open(self.target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.addCleanup(os.close, fd)
        original = os.fchmod
        calls = []
        def change(descriptor, mode):
            calls.append((descriptor, mode))
            return original(descriptor, mode)
        attempt = self.tool._Attempt()
        with patch.object(self.tool.os, 'fchmod', side_effect=change):
            attempt.enter(fd)
            with self.assertRaises(ValueError): attempt.enter(fd)
        self.assertEqual(calls, [(fd, 0o700)])
        self.assertEqual(attempt.attempts, 1)
        self.assertTrue(attempt.returned)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o700)
        self.unchanged_receipts()

    def test_raised_result_after_real_change_stays_consumed_uncertain(self):
        fd = os.open(self.target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.addCleanup(os.close, fd)
        original = os.fchmod
        def lost(descriptor, mode):
            original(descriptor, mode)
            raise OSError('lost syscall result')
        attempt = self.tool._Attempt()
        with patch.object(self.tool.os, 'fchmod', side_effect=lost) as change:
            with self.assertRaises(OSError): attempt.enter(fd)
            with self.assertRaises(ValueError): attempt.enter(fd)
        self.assertEqual(change.call_count, 1)
        self.assertEqual(attempt.attempts, 1)
        self.assertFalse(attempt.returned)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o700)

    def test_error_count_and_utf8_bounds_never_discard_failure_into_success(self):
        errors = self.tool._Errors()
        for index in range(17): errors.add(OSError('failure ' + str(index)))
        self.assertEqual(len(errors.rows), 16)
        self.assertTrue(errors.overflow)
        long = self.tool._Errors()
        long.add(ValueError('é' * 4097))
        self.assertTrue(long.overflow)
        self.assertLessEqual(len(long.rows[0]['message'].encode('utf-8')), 4096)
        long.add(ValueError('\udcff'))
        self.assertTrue(long.rows)

class ProcedureTests(Fixture):
    def test_confirmed_records_complete_observation_and_closes_every_descriptor(self):
        inode = self.target.stat().st_ino
        original_close = self.tool._close_fd
        closed = []
        def close(fd):
            original_close(fd)
            closed.append(fd)
        with patch.object(self.tool, '_close_fd', side_effect=close):
            result = self.run_fixture()
        self.assertEqual(result['outcome'], 'mode_change_confirmed')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertEqual(result['syscall_certainty'], 'returned')
        self.assertEqual(result['observed_pre_mode'], '0755')
        self.assertEqual(result['observed_post_mode'], '0700')
        self.assertTrue(result['preservation'])
        self.assertTrue(all(result['preservation_checks'].values()))
        self.assertEqual(self.target.stat().st_ino, inode)
        self.assertEqual(result['reviewed_source'], SOURCE)
        self.assertEqual(result['execution_approval'], APPROVAL)
        self.assertTrue(closed)
        for fd in closed:
            with self.assertRaises(OSError): os.fstat(fd)
        self.unchanged_receipts()

    def test_each_preflight_source_or_account_failure_refuses_before_syscall(self):
        for selected in (1, 3):
            with self.subTest(kind='source', selected=selected):
                calls = []
                def source(_):
                    calls.append('source')
                    if len(calls) == selected:
                        raise ValueError('selected source check')
                with patch.object(self.tool.os, 'fchmod', wraps=os.fchmod) as fchmod:
                    self.assert_refused(self.run_fixture(source=source))
                self.assertEqual(len(calls), selected)
                self.assertEqual(fchmod.call_count, 0)
            self.target.chmod(0o755)
            with self.subTest(kind='account', selected=selected):
                calls = []
                def account():
                    calls.append('account')
                    if len(calls) == selected:
                        raise ValueError('selected account check')
                with patch.object(self.tool.os, 'fchmod', wraps=os.fchmod) as fchmod:
                    self.assert_refused(self.run_fixture(account=account))
                self.assertEqual(len(calls), selected)
                self.assertEqual(fchmod.call_count, 0)
            self.target.chmod(0o755)

    def test_target_replacement_during_final_preflight_is_refused(self):
        def source(_):
            if source.calls == 2:
                self.target.rename(self.tools / 'old-target')
                self.target.mkdir(mode=0o755)
                self.target.chmod(0o755)
            source.calls += 1
        source.calls = 0
        with patch.object(self.tool.os, 'fchmod', wraps=os.fchmod) as fchmod:
            result = self.run_fixture(source=source)
        self.assert_refused(result)
        self.assertEqual(fchmod.call_count, 0)

    def test_lost_syscall_result_is_uncertain_even_when_mode_changed(self):
        original = os.fchmod
        def lost(fd, mode):
            original(fd, mode)
            raise OSError('lost syscall result')
        with patch.object(self.tool.os, 'fchmod', side_effect=lost) as fchmod:
            result = self.run_fixture()
        self.assertEqual(fchmod.call_count, 1)
        self.assertEqual(result['outcome'], 'mutation_uncertain')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertEqual(result['syscall_certainty'], 'uncertain')
        self.assertEqual(result['observed_post_mode'], '0700')
        self.assertFalse(result['preservation'])
        self.unchanged_receipts()

    def test_fsync_failure_after_return_is_inconclusive(self):
        with patch.object(self.tool.os, 'fsync', side_effect=OSError('fsync failed')):
            result = self.run_fixture()
        self.assertEqual(result['outcome'], 'postverification_inconclusive')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertEqual(result['syscall_certainty'], 'returned')
        self.assertEqual(result['observed_post_mode'], '0700')
        self.assertFalse(result['preservation'])

    def test_post_observation_and_metadata_failures_are_inconclusive(self):
        for name in ('observe', 'metadata'):
            with self.subTest(name=name):
                original = getattr(self.tool._Proof, name)
                def injected(proof, *args, **kwargs):
                    result = original(proof, *args, **kwargs)
                    if kwargs.get('after'):
                        raise OSError('post ' + name + ' failure')
                    return result
                with patch.object(self.tool._Proof, name, new=injected):
                    result = self.run_fixture()
                self.assertEqual(result['outcome'], 'postverification_inconclusive')
                self.assertEqual(result['fchmod_attempts'], 1)
                self.assertEqual(result['syscall_certainty'], 'returned')
                self.assertEqual(result['observed_post_mode'], '0700')
                self.assertFalse(result['preservation'])
                self.unchanged_receipts()
            self.target.chmod(0o755)

    def test_late_teardown_error_does_not_hide_lost_syscall_result(self):
        original_close = self.tool._close_fd
        released = []
        def late_close(fd):
            original_close(fd)
            released.append(fd)
            raise OSError('late close after actual release')
        original_fchmod = os.fchmod
        def lost(fd, mode):
            original_fchmod(fd, mode)
            raise ValueError('original lost result')
        with patch.object(self.tool, '_close_fd', side_effect=late_close), patch.object(self.tool.os, 'fchmod', side_effect=lost):
            result = self.run_fixture()
        self.assertEqual(result['outcome'], 'mutation_uncertain')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertEqual(result['syscall_certainty'], 'uncertain')
        self.assertEqual(result['errors'][0]['message'], 'original lost result')
        self.assertTrue(any('late close' in row['message'] for row in result['errors']))
        for fd in released:
            with self.assertRaises(OSError): os.fstat(fd)

    def test_final_source_failure_is_inconclusive_after_returned_change(self):
        calls = []
        def source(_):
            calls.append(None)
            if len(calls) == 4:
                raise ValueError('last source check')
        result = self.run_fixture(source=source)
        self.assertEqual(result['outcome'], 'postverification_inconclusive')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertEqual(result['syscall_certainty'], 'returned')
        self.assertEqual(result['observed_post_mode'], '0700')

    def test_child_metadata_drift_after_change_is_inconclusive(self):
        original = os.fchmod
        def drift(fd, mode):
            original(fd, mode)
            self.receipt.chmod(0o755)
        with patch.object(self.tool.os, 'fchmod', side_effect=drift):
            result = self.run_fixture()
        self.assertEqual(result['outcome'], 'postverification_inconclusive')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertEqual(result['syscall_certainty'], 'returned')
        self.assertFalse(result['preservation'])

    def test_success_never_uses_creation_or_mutation_helpers_other_than_fchmod(self):
        forbidden = ('mkdir', 'write', 'unlink', 'rename', 'chmod', 'chown')
        with ExitStack() as stack:
            for name in forbidden:
                stack.enter_context(patch.object(self.tool.os, name, side_effect=AssertionError('forbidden ' + name)))
            stack.enter_context(patch.object(subprocess, 'Popen', side_effect=AssertionError('forbidden subprocess')))
            result = self.run_fixture()
        self.assertEqual(result['outcome'], 'mode_change_confirmed')
        self.unchanged_receipts()

class CLITests(unittest.TestCase):
    def test_import_has_no_target_or_source_access(self):
        load_tool()
        spec = importlib.util.spec_from_file_location('hf_permission_import_only', TOOL)
        module = importlib.util.module_from_spec(spec)
        with patch.object(os, 'open', side_effect=AssertionError('no open during import')), patch.object(os, 'stat', side_effect=AssertionError('no stat during import')):
            spec.loader.exec_module(module)

    def test_invalid_arguments_reject_before_source_account_or_open(self):
        tool = load_tool()
        cases = [
            [],
            ['--reviewed-source', SOURCE, '--execution-approval', APPROVAL],
            ['--reviewed', SOURCE],
            ['--reviewed-source', SOURCE, '--execution-approval', APPROVAL, '--target', '/private/tmp/other', '--execute-approved-mode-change'],
            ['--reviewed-source', 'HEAD', '--execution-approval', APPROVAL, '--execute-approved-mode-change'],
            ['--reviewed-source', SOURCE.upper(), '--execution-approval', APPROVAL, '--execute-approved-mode-change'],
            ['--reviewed-source', SOURCE, '--execution-approval', '   ', '--execute-approved-mode-change'],
            ['--reviewed-source', SOURCE, '--execution-approval', 'x' * 4097, '--execute-approved-mode-change'],
            ['--reviewed-source', SOURCE, '--execution-approval', '\udcff', '--execute-approved-mode-change'],
        ]
        for argv in cases:
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()):
                with patch.object(tool, '_source', side_effect=AssertionError('source')), patch.object(tool, '_account', side_effect=AssertionError('account')), patch.object(tool.os, 'open', side_effect=AssertionError('open')):
                    with self.assertRaises(SystemExit) as exit_value:
                        tool.main(argv)
            self.assertEqual(exit_value.exception.code, 2)

    def test_canonical_stdout_and_exit_status_follow_outcome(self):
        tool = load_tool()
        for outcome in ('mode_change_confirmed', 'preflight_refused', 'mutation_uncertain', 'postverification_inconclusive'):
            with self.subTest(outcome=outcome):
                attempts = 0 if outcome == 'preflight_refused' else 1
                document = {'outcome': outcome, 'fchmod_attempts': attempts, 'nested': {'count': attempts}}
                stdout = io.StringIO()
                with patch.object(tool, '_run', return_value=document), redirect_stdout(stdout):
                    status = tool.main(['--reviewed-source', SOURCE, '--execution-approval', APPROVAL, '--execute-approved-mode-change'])
                expected = tool._canonical(document)
                self.assertEqual(stdout.getvalue(), expected.decode('utf-8'))
                self.assertLessEqual(len(expected), tool.MAXIMUM)
                self.assertEqual(status, 0 if outcome == 'mode_change_confirmed' else 1)
                self.assertEqual(json.loads(stdout.getvalue())['fchmod_attempts'], attempts)


class AdversarialTests(Fixture):
    def test_missing_file_and_symlink_targets_are_not_created_followed_or_adopted(self):
        original = self.tools / 'retained-original'
        self.target.rename(original)
        try:
            for kind in ('missing', 'file', 'symlink'):
                with self.subTest(kind=kind):
                    if kind == 'file':
                        self.target.write_bytes(b'not a directory')
                    elif kind == 'symlink':
                        self.target.symlink_to(original, target_is_directory=True)
                    result = self.run_fixture()
                    self.assertEqual(result['outcome'], 'preflight_refused')
                    self.assertEqual(result['fchmod_attempts'], 0)
                    self.assertFalse(result['preservation'])
                    if kind == 'missing':
                        self.assertFalse(self.target.exists())
                    elif kind == 'file':
                        self.assertTrue(self.target.is_file())
                        self.target.unlink()
                    else:
                        self.assertTrue(self.target.is_symlink())
                        self.target.unlink()
        finally:
            if not self.target.exists() and not self.target.is_symlink():
                original.rename(self.target)

    def test_missing_lock_parent_is_not_created(self):
        self.lock.unlink()
        self.lock_parent.rmdir()
        result = self.run_fixture()
        self.assert_refused(result)
        self.assertEqual(result['fchmod_attempts'], 0)
        self.assertFalse(self.lock_parent.exists())

    def test_lock_symlink_hardlink_wrong_mode_and_oversize_refuse(self):
        payload = b'cooperating fixture lock\n'
        other = self.lock_parent / 'other'
        for kind in ('symlink', 'hardlink', 'mode', 'size'):
            with self.subTest(kind=kind):
                if self.lock.is_symlink() or self.lock.exists():
                    self.lock.unlink()
                if other.is_symlink() or other.exists():
                    other.unlink()
                self.lock.write_bytes(payload)
                self.lock.chmod(0o600)
                if kind == 'symlink':
                    self.lock.rename(other)
                    self.lock.symlink_to(other)
                elif kind == 'hardlink':
                    os.link(self.lock, other)
                elif kind == 'mode':
                    self.lock.chmod(0o644)
                else:
                    self.lock.write_bytes(b'x' * (self.tool.MAXIMUM + 1))
                result = self.run_fixture()
                self.assert_refused(result)
                self.assertEqual(result['fchmod_attempts'], 0)
                if self.lock.is_symlink() or self.lock.exists():
                    self.lock.unlink()
                if other.is_symlink() or other.exists():
                    other.unlink()
                self.lock.write_bytes(payload)
                self.lock.chmod(0o600)

    def test_final_metadata_after_last_content_read_does_not_adopt_replaced_lock(self):
        original_read = self.tool._Proof._read_lock
        reads = []
        old_lock = self.lock_parent / 'old-lock'

        def read(proof, *args, **kwargs):
            payload = original_read(proof, *args, **kwargs)
            if not kwargs.get('after'):
                reads.append(len(reads) + 1)
                if len(reads) == 2:
                    self.lock.rename(old_lock)
                    self.lock.write_bytes(b'cooperating fixture lock\n')
                    self.lock.chmod(0o600)
            return payload

        with patch.object(self.tool._Proof, '_read_lock', new=read):
            result = self.run_fixture()
        self.assertEqual(reads, [1, 2])
        self.assert_refused(result)
        self.assertEqual(result['fchmod_attempts'], 0)
        self.assertTrue(old_lock.exists())
        self.assertTrue(self.lock.exists())

    def test_initial_roster_instability_and_enumeration_fault_refuse(self):
        original_children = self.tool._Proof._children
        calls = []
        new_child = self.target / 'new-child'

        def unstable(proof, *args, **kwargs):
            result = original_children(proof, *args, **kwargs)
            calls.append(result)
            if len(calls) == 1:
                new_child.mkdir(mode=0o700)
            return result

        with patch.object(self.tool._Proof, '_children', new=unstable):
            result = self.run_fixture()
        self.assertEqual(len(calls), 2)
        self.assert_refused(result)
        self.assertEqual(result['fchmod_attempts'], 0)
        new_child.rmdir()

        with patch.object(self.tool.os, 'scandir', side_effect=OSError('enumeration failed')):
            result = self.run_fixture()
        self.assert_refused(result)
        self.assertEqual(result['fchmod_attempts'], 0)

    def test_final_post_source_io_target_replacement_is_inconclusive(self):
        calls = []
        changed = self.tools / 'changed-after-post'

        def source(_):
            calls.append(None)
            if len(calls) == 4:
                self.target.rename(changed)
                self.target.mkdir(mode=0o700)

        result = self.run_fixture(source=source)
        self.assertEqual(len(calls), 4)
        self.assertEqual(result['outcome'], 'postverification_inconclusive')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertEqual(result['syscall_certainty'], 'returned')
        self.assertEqual(result['observed_post_mode'], '0700')
        self.assertEqual(stat.S_IMODE(changed.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o700)
        self.assertFalse(result['preservation'])

    def test_teardown_only_failure_after_success_is_inconclusive_and_releases_all_fds(self):
        original_close = self.tool._close_fd
        released = []

        def late_close(fd):
            original_close(fd)
            released.append(fd)
            raise ValueError('late release proof error')

        with patch.object(self.tool, '_close_fd', side_effect=late_close):
            result = self.run_fixture()
        self.assertEqual(result['outcome'], 'postverification_inconclusive')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertEqual(result['syscall_certainty'], 'returned')
        self.assertEqual(result['observed_post_mode'], '0700')
        self.assertFalse(result['preservation'])
        self.assertFalse(result['preservation_checks']['teardown'])
        self.assertTrue(any(row['message'] == 'late release proof error' for row in result['errors']))
        self.assertTrue(released)
        for fd in released:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_fchmod_failure_before_change_is_uncertain_without_retry(self):
        with patch.object(self.tool.os, 'fchmod', side_effect=OSError('syscall refused')) as fchmod:
            result = self.run_fixture()
        self.assertEqual(fchmod.call_count, 1)
        self.assertEqual(result['outcome'], 'mutation_uncertain')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertEqual(result['syscall_certainty'], 'uncertain')
        self.assertEqual(result['observed_post_mode'], '0755')
        self.assertFalse(result['preservation'])
        self.unchanged_receipts()

    def test_known_child_metadata_drift_at_pre_and_post_source_checks(self):
        for fail_at in (3, 4):
            with self.subTest(fail_at=fail_at):
                self.target.chmod(0o755)
                self.receipt.chmod(0o700)
                calls = []

                def source(_):
                    calls.append(None)
                    if len(calls) == fail_at:
                        self.receipt.chmod(0o755)

                result = self.run_fixture(source=source)
                self.assertEqual(len(calls), fail_at)
                if fail_at == 3:
                    self.assertEqual(result['outcome'], 'preflight_refused')
                    self.assertEqual(result['fchmod_attempts'], 0)
                else:
                    self.assertEqual(result['outcome'], 'postverification_inconclusive')
                    self.assertEqual(result['fchmod_attempts'], 1)
                    self.assertEqual(result['syscall_certainty'], 'returned')
                    self.assertEqual(result['observed_post_mode'], '0700')
                self.assertFalse(result['preservation'])

    def test_equal_roster_direct_child_symlink_is_allowed_without_following_or_reading(self):
        outside = self.root / 'outside-payload'
        outside_payload = b'not a receipt and must not be read'
        outside.write_bytes(outside_payload)
        pointer = self.target / 'pointer'
        pointer.symlink_to(outside)
        original_open = self.tool.os.open
        opened = []

        def record_open(path, flags, *args, **kwargs):
            opened.append((path, flags))
            return original_open(path, flags, *args, **kwargs)

        with patch.object(self.tool.os, 'open', side_effect=record_open):
            result = self.run_fixture()
        self.assertEqual(result['outcome'], 'mode_change_confirmed')
        self.assertTrue(opened)
        forbidden = os.O_CREAT | os.O_TRUNC | os.O_WRONLY | os.O_RDWR
        for path, flags in opened:
            path_text = os.fsdecode(path)
            self.assertEqual(flags & forbidden, 0)
            self.assertNotEqual(Path(path_text), pointer)
            self.assertNotEqual(Path(path_text), outside)
            self.assertNotEqual(Path(path_text).name, 'pointer')
            self.assertNotIn(Path(path_text).name, {'retained', 'outcome.json', 'SHA256SUMS'})
        self.assertEqual(outside.read_bytes(), outside_payload)
        self.unchanged_receipts()

    def test_utf8_name_byte_bound_refuses_and_exact_maximum_lock_passes(self):
        long_name = self.target / ('é' * 65)
        long_name.mkdir(mode=0o700)
        result = self.run_fixture()
        self.assert_refused(result)
        self.assertEqual(result['fchmod_attempts'], 0)
        long_name.rmdir()

        self.lock.write_bytes(b'x' * self.tool.MAXIMUM)
        self.lock.chmod(0o600)
        result = self.run_fixture()
        self.assertEqual(result['outcome'], 'mode_change_confirmed')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertEqual(self.lock.stat().st_size, self.tool.MAXIMUM)
        self.unchanged_receipts()

    def test_account_helper_rejects_uid_euid_and_home_mismatches(self):
        cases = (
            {'getuid': self.tool.UID + 1},
            {'geteuid': self.tool.UID + 1},
            {'pw': SimpleNamespace(pw_dir='/private/tmp/not-home')},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                with patch.object(self.tool.os, 'getuid', return_value=changes.get('getuid', self.tool.UID)), \
                     patch.object(self.tool.os, 'geteuid', return_value=changes.get('geteuid', self.tool.UID)), \
                     patch.object(self.tool.pwd, 'getpwuid', return_value=changes.get('pw', SimpleNamespace(pw_dir=str(self.tool.HOME)))):
                    with self.assertRaises(ValueError):
                        self.tool._account()

    def test_final_closure_event_order_has_no_content_or_enumeration_after_last_source_io(self):
        events = []
        source_calls = []
        original_metadata = self.tool._Proof.metadata
        original_pread = self.tool.os.pread
        original_scandir = self.tool.os.scandir
        original_fchmod = self.tool.os.fchmod

        def metadata(proof, *args, **kwargs):
            result = original_metadata(proof, *args, **kwargs)
            events.append('metadata_after' if kwargs.get('after') else 'metadata_before')
            return result

        def pread(*args, **kwargs):
            events.append('content')
            return original_pread(*args, **kwargs)

        def scandir(*args, **kwargs):
            events.append('enumeration')
            return original_scandir(*args, **kwargs)

        def source(_):
            source_calls.append(None)
            events.append('source')

        def fchmod(fd, mode):
            self.assertEqual(len(source_calls), 3)
            self.assertEqual(events[-1], 'metadata_before')
            third_source = [index for index, event in enumerate(events) if event == 'source'][2]
            between = events[third_source + 1:]
            self.assertNotIn('content', between)
            self.assertNotIn('enumeration', between)
            events.append('syscall')
            return original_fchmod(fd, mode)

        with patch.object(self.tool._Proof, 'metadata', new=metadata), \
             patch.object(self.tool.os, 'pread', side_effect=pread), \
             patch.object(self.tool.os, 'scandir', side_effect=scandir), \
             patch.object(self.tool.os, 'fchmod', side_effect=fchmod):
            result = self.run_fixture(source=source)
        self.assertEqual(result['outcome'], 'mode_change_confirmed')
        self.assertEqual(len(source_calls), 4)
        self.assertEqual(events[-2:], ['source', 'metadata_after'])
