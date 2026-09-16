import importlib
import importlib.util
from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from kil.hf_exploratory_io import PrivateStore
from kil.v3b2_journal import Command, COLIMA_START_ARGV


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('kil.hf_exploratory_runtime'),
                             'isolated runtime authority is missing')
        self.runtime = importlib.import_module('kil.hf_exploratory_runtime')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name).resolve() / '.tools' / 'hf-exploratory-private'
        self.parent.mkdir(parents=True, mode=0o700)
        self.digest = 'a' * 64
        self.store = PrivateStore(self.parent / ('hf-exploratory-' + self.digest))
        self.addCleanup(self.store.close)

    def authority(self):
        authority = self.runtime.RuntimeAuthority.create(self.store, self.digest)
        self.addCleanup(authority.close)
        return authority

    def test_fresh_derived_private_runtime(self):
        authority = self.authority()
        self.assertEqual(authority.path, self.parent / ('hf-exploratory-runtime-' + self.digest))
        self.assertEqual(authority.colima, authority.path / '.colima')
        self.assertEqual(authority.lima, authority.colima / '_lima')
        self.assertEqual(authority.docker_config, authority.path / 'docker-config')
        self.assertEqual(authority.tmp, authority.path / 'runtime-tmp')
        self.assertEqual(authority.kubeconfig, authority.path / 'kubeconfig')
        self.assertEqual(authority.kind_config, authority.path / 'kind-config.yaml')
        for path in (authority.path, authority.colima, authority.lima,
                     authority.docker_config, authority.tmp):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
            self.assertEqual(path.stat().st_uid, os.geteuid())
        authority.guard()

    def test_guard_refuses_missing_replaced_symlink_and_mode_changed_homes(self):
        authority = self.authority()
        for path in (authority.lima, authority.colima, authority.docker_config,
                     authority.tmp, authority.path, self.parent, self.parent.parent):
            moved = path.with_name(path.name + '-moved')
            with self.subTest(path=path):
                path.rename(moved)
                try:
                    with self.assertRaises(ValueError):
                        authority.guard()
                    path.mkdir(mode=0o700)
                    with self.assertRaises(ValueError):
                        authority.guard()
                    path.rmdir()
                    path.symlink_to(moved, target_is_directory=True)
                    with self.assertRaises(ValueError):
                        authority.guard()
                    path.unlink()
                finally:
                    moved.rename(path)
                old_mode = stat.S_IMODE(path.stat().st_mode)
                path.chmod(0o755 if old_mode == 0o700 else 0o700)
                try:
                    with self.assertRaises(ValueError):
                        authority.guard()
                finally:
                    path.chmod(old_mode)
                authority.guard()

    def test_guard_refuses_substituted_namespace_and_closed_store(self):
        authority = self.authority()
        original = authority.path
        object.__setattr__(authority, 'path', self.parent / 'foreign')
        with self.assertRaises(ValueError):
            authority.guard()
        object.__setattr__(authority, 'path', original)
        self.store.close()
        with self.assertRaises(ValueError):
            authority.guard()

    def test_close_is_idempotent_descriptors_only(self):
        authority = self.authority()
        authority.close()
        authority.close()
        with self.assertRaises(ValueError):
            authority.guard()
        self.assertTrue(authority.lima.is_dir())

    def test_authority_constructor_and_uninitialized_forgery_are_closed(self):
        with self.assertRaises(ValueError):
            self.runtime.RuntimeAuthority()
        forged = object.__new__(self.runtime.RuntimeAuthority)
        with self.assertRaises(ValueError):
            forged.guard()

    def test_control_is_exclusive_bounded_private_and_guarded(self):
        authority = self.authority()
        self.assertTrue(hasattr(authority, 'write_control'), 'exclusive runtime control is missing')
        payload = b'x' * 65536
        authority.write_control('kind-config.yaml', payload)
        self.assertEqual(authority.kind_config.read_bytes(), payload)
        self.assertEqual(stat.S_IMODE(authority.kind_config.stat().st_mode), 0o600)
        with self.assertRaises(FileExistsError):
            authority.write_control('kind-config.yaml', b'replacement')
        for name, value in [('kubeconfig', b'x'), ('../kind-config.yaml', b'x'),
                            ('kind-config.yaml', b'x' * 65537), ('kind-config.yaml', 'x')]:
            with self.subTest(name=name, value_type=type(value)):
                with self.assertRaises(ValueError):
                    authority.write_control(name, value)
        authority.close()
        with self.assertRaises(ValueError):
            authority.write_control('kind-config.yaml', b'x')
        self.assertEqual(authority.kind_config.read_bytes(), payload)

    def test_control_refuses_symlink_and_stale_root(self):
        authority = self.authority()
        self.assertTrue(hasattr(authority, 'write_control'), 'exclusive runtime control is missing')
        external = self.parent / 'external'
        external.write_bytes(b'unchanged')
        authority.kind_config.symlink_to(external)
        with self.assertRaises(FileExistsError):
            authority.write_control('kind-config.yaml', b'bad')
        self.assertEqual(external.read_bytes(), b'unchanged')
        authority.kind_config.unlink()
        authority.path.rename(authority.path.with_name('moved'))
        authority.path.mkdir(mode=0o700)
        with self.assertRaises(ValueError):
            authority.write_control('kind-config.yaml', b'bad')
        self.assertFalse(authority.kind_config.exists())

    def adapter(self, command, authority):
        self.assertTrue(hasattr(self.runtime, 'ExploratoryColimaCommand'), 'finite Colima adapter is missing')
        return self.runtime.ExploratoryColimaCommand(command, authority)

    def test_adapter_exact_derived_environment_and_strict_properties(self):
        authority = self.authority()
        for argv, mutating in [(('colima', 'version'), False), (COLIMA_START_ARGV, True),
                               (('colima', 'stop', '--profile', 'kil-v3-lab'), True),
                               (('colima', 'delete', '--profile', 'kil-v3-lab', '--force', '--data'), True),
                               (('colima', 'status', '--profile', 'kil-v3-lab'), False),
                               (('colima', 'list', '--json'), False)]:
            command = Command(argv, 45, mutating=mutating)
            adapter = self.adapter(command, authority)
            self.assertEqual(adapter.argv, command.argv)
            self.assertEqual(adapter.timeout_s, 45)
            self.assertEqual(adapter.mutating, mutating)
            self.assertIsNone(adapter.stdin)
            self.assertEqual(adapter.env, (('COLIMA_HOME', str(authority.colima)),
                ('LIMA_HOME', str(authority.lima)), ('DOCKER_CONFIG', str(authority.docker_config)),
                ('TMPDIR', str(authority.tmp))))

    def test_adapter_refuses_foreign_environment_other_family_and_subclasses(self):
        authority = self.authority()
        class SubCommand(Command):
            pass
        class SubAuthority(self.runtime.RuntimeAuthority):
            pass
        commands = [Command(('colima', 'version'), 1,
                       env=(('DOCKER_CONFIG', '/private/tmp/foreign/docker-config'),
                            ('TMPDIR', '/private/tmp/foreign/runtime-tmp'))),
                    Command(('docker', 'context', 'show'), 1),
                    SubCommand(('colima', 'version'), 1), object()]
        for command in commands:
            with self.subTest(command_type=type(command)):
                with self.assertRaises(ValueError):
                    self.adapter(command, authority)
        with self.assertRaises(ValueError):
            self.adapter(Command(('colima', 'version'), 1), object.__new__(SubAuthority))

    def test_adapter_freshly_checks_grammar_and_runtime_authority(self):
        authority = self.authority()
        command = Command(('colima', 'version'), 1)
        adapter = self.adapter(command, authority)
        for field, bad in [('argv', ('colima', 'start', '--profile', 'foreign')),
                           ('timeout_s', True), ('stdin', b'foreign'), ('mutating', True),
                           ('env', (('COLIMA_HOME', '/private/tmp/foreign'),))]:
            original = getattr(command, field)
            object.__setattr__(command, field, bad)
            try:
                with self.assertRaises(ValueError):
                    adapter.__post_init__()
            finally:
                object.__setattr__(command, field, original)
        original = authority.path
        object.__setattr__(authority, 'path', self.parent / 'foreign')
        try:
            with self.assertRaises(ValueError):
                adapter.__post_init__()
            with self.assertRaises(ValueError):
                _ = adapter.env
        finally:
            object.__setattr__(authority, 'path', original)
        authority.colima.rename(authority.path / 'old-colima')
        with self.assertRaises(ValueError):
            adapter.__post_init__()

    def test_store_lock_name_replacement_invalidates_authority(self):
        authority = self.authority()
        lock = self.store.path / 'lock'
        lock.rename(self.store.path / 'original-lock')
        lock.write_bytes(b'new')
        lock.chmod(0o600)
        with self.assertRaises(ValueError):
            authority.guard()

    def test_create_checks_named_lock_before_creating_runtime(self):
        lock = self.store.path / 'lock'
        lock.rename(self.store.path / 'original-lock')
        lock.write_bytes(b'new')
        lock.chmod(0o600)
        with self.assertRaises(ValueError):
            self.authority()
        self.assertFalse((self.parent / ('hf-exploratory-runtime-' + self.digest)).exists())

    def test_create_rejects_nonprivate_store_before_runtime_creation(self):
        self.store.path.chmod(0o755)
        with self.assertRaises(ValueError):
            self.authority()
        self.assertFalse((self.parent / ('hf-exploratory-runtime-' + self.digest)).exists())
        self.assertTrue((self.store.path / 'lock').exists())

    def test_create_rejects_nonprivate_or_hardlinked_lock_before_runtime_creation(self):
        lock = self.store.path / 'lock'
        lock.chmod(0o400)
        with self.assertRaises(ValueError):
            self.authority()
        self.assertFalse((self.parent / ('hf-exploratory-runtime-' + self.digest)).exists())
        lock.chmod(0o600)
        os.link(lock, self.store.path / 'lock-hardlink')
        with self.assertRaises(ValueError):
            self.authority()
        self.assertFalse((self.parent / ('hf-exploratory-runtime-' + self.digest)).exists())
        self.assertEqual(lock.stat().st_nlink, 2)

    def test_guard_rejects_new_receipt_lock_hardlink(self):
        authority = self.authority()
        os.link(self.store.path / 'lock', self.store.path / 'lock-hardlink')
        with self.assertRaises(ValueError):
            authority.guard()

    def test_uninitialized_adapter_is_rejected_as_invalid(self):
        self.assertTrue(hasattr(self.runtime, 'ExploratoryColimaCommand'))
        forged = object.__new__(self.runtime.ExploratoryColimaCommand)
        with self.assertRaises(ValueError):
            forged.__post_init__()

    def test_create_rejects_bad_digest_wrong_store_closed_and_nonprivate_parent(self):
        for digest in ['', 'a' * 63, 'A' * 64, 'a' * 65, 7, 'b' * 64]:
            with self.subTest(digest=digest):
                with self.assertRaises(ValueError):
                    self.runtime.RuntimeAuthority.create(self.store, digest)
        for store in [object(), self.parent]:
            with self.assertRaises(ValueError):
                self.runtime.RuntimeAuthority.create(store, self.digest)
        wrong = PrivateStore(self.parent / 'wrong-name')
        self.addCleanup(wrong.close)
        with self.assertRaises(ValueError):
            self.runtime.RuntimeAuthority.create(wrong, self.digest)
        wrong_parent = PrivateStore(Path(self.temp.name).resolve() / ('hf-exploratory-' + self.digest))
        self.addCleanup(wrong_parent.close)
        with self.assertRaises(ValueError):
            self.runtime.RuntimeAuthority.create(wrong_parent, self.digest)
        self.parent.chmod(0o755)
        with self.assertRaises(ValueError):
            self.authority()
        self.parent.chmod(0o700)
        with patch.object(self.runtime.os, 'geteuid', return_value=os.geteuid() + 1):
            with self.assertRaises(ValueError):
                self.authority()
        self.store.close()
        with self.assertRaises(ValueError):
            self.authority()

    def test_create_rejects_replaced_or_symlinked_live_store_and_ancestor(self):
        for path in (self.store.path, self.parent.parent):
            moved = path.with_name(path.name + '-moved')
            path.rename(moved)
            try:
                path.mkdir(mode=0o700)
                with self.assertRaises((ValueError, OSError)):
                    self.authority()
                path.rmdir()
                path.symlink_to(moved, target_is_directory=True)
                with self.assertRaises(ValueError):
                    self.authority()
                path.unlink()
            finally:
                moved.rename(path)

    def test_preexisting_runtime_is_never_adopted_or_deleted(self):
        path = self.parent / ('hf-exploratory-runtime-' + self.digest)
        path.mkdir(mode=0o700)
        marker = path / 'marker'
        marker.write_bytes(b'preserved')
        with self.assertRaises((ValueError, OSError)):
            self.authority()
        self.assertEqual(marker.read_bytes(), b'preserved')
        marker.unlink()
        path.rmdir()
        path.symlink_to(self.store.path, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            self.authority()
        self.assertTrue(path.is_symlink())

    def test_construction_failure_closes_all_opened_fds_and_leaves_partial_tree(self):
        opened = []
        real_open, real_mkdir = os.open, os.mkdir
        def tracked_open(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            opened.append(fd)
            return fd
        def fail_mkdir(name, *args, **kwargs):
            if name == '_lima':
                raise OSError('injected mkdir failure')
            return real_mkdir(name, *args, **kwargs)
        with patch.object(self.runtime.os, 'open', side_effect=tracked_open), \
                patch.object(self.runtime.os, 'mkdir', side_effect=fail_mkdir):
            with self.assertRaises(OSError) as failure:
                self.authority()
        self.assertEqual(str(failure.exception), 'injected mkdir failure')
        for fd in set(opened):
            with self.assertRaises(OSError):
                os.fstat(fd)
        path = self.parent / ('hf-exploratory-runtime-' + self.digest)
        self.assertTrue((path / '.colima').is_dir())
        self.assertFalse((path / '.colima' / '_lima').exists())
        with self.assertRaises((ValueError, OSError)):
            self.authority()
        self.store.write('still-live', b'ok')

    def test_identity_read_failure_also_closes_just_opened_fd(self):
        opened, failing = [], []
        real_open, real_fstat = os.open, os.fstat
        def tracked_open(name, *args, **kwargs):
            fd = real_open(name, *args, **kwargs)
            opened.append(fd)
            if name == '.colima':
                failing.append(fd)
            return fd
        def fail_fstat(fd):
            if fd in failing:
                raise OSError('injected identity failure')
            return real_fstat(fd)
        with patch.object(self.runtime.os, 'open', side_effect=tracked_open), \
                patch.object(self.runtime.os, 'fstat', side_effect=fail_fstat):
            with self.assertRaises(OSError):
                self.authority()
        for fd in set(opened):
            with self.assertRaises(OSError):
                real_fstat(fd)

    def test_first_ancestor_identity_failure_closes_every_opened_fd_without_deletion(self):
        opened, failing = [], []
        real_open, real_fstat = os.open, os.fstat
        first_ancestor = self.store.path.parts[1]
        marker = self.store.path / 'preserved'
        marker.write_bytes(b'keep')
        def tracked_open(name, *args, **kwargs):
            fd = real_open(name, *args, **kwargs)
            opened.append(fd)
            if name == first_ancestor:
                failing.append(fd)
            return fd
        def fail_fstat(fd):
            if fd in failing:
                raise OSError('injected first ancestor identity failure')
            return real_fstat(fd)
        # Capture the actual construction path, including any called helper.
        with patch.object(self.runtime.os, 'open', side_effect=tracked_open), \
                patch.object(self.runtime.os, 'fstat', side_effect=fail_fstat):
            with self.assertRaises((ValueError, OSError)):
                self.authority()
        leaked = []
        for fd in set(opened):
            try:
                real_fstat(fd)
            except OSError:
                continue
            leaked.append(fd)
            os.close(fd)
        self.assertEqual(marker.read_bytes(), b'keep')
        self.assertFalse((self.parent / ('hf-exploratory-runtime-' + self.digest)).exists())
        self.assertEqual(leaked, [], 'construction leaked first ancestor descriptor')

    def test_control_empty_payload_full_short_writes_and_fsync_failure_close_fd(self):
        authority = self.authority()
        real_write = os.write
        with patch.object(self.runtime.os, 'write', side_effect=lambda fd, payload: real_write(fd, payload[:2])):
            authority.write_control('kind-config.yaml', b'seven!!')
        self.assertEqual(authority.kind_config.read_bytes(), b'seven!!')
        authority.kind_config.unlink()
        authority.write_control('kind-config.yaml', b'')
        self.assertEqual(authority.kind_config.read_bytes(), b'')
        authority.kind_config.unlink()
        opened = []
        real_open = os.open
        def tracked_open(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            opened.append(fd)
            return fd
        with patch.object(self.runtime.os, 'open', side_effect=tracked_open), \
                patch.object(self.runtime.os, 'fsync', side_effect=OSError('injected fsync failure')):
            with self.assertRaisesRegex(OSError, 'injected fsync failure'):
                authority.write_control('kind-config.yaml', b'preserved')
        for fd in opened:
            with self.assertRaises(OSError):
                os.fstat(fd)
        self.assertEqual(authority.kind_config.read_bytes(), b'preserved')

    def test_control_exact_mode_is_not_filtered_by_restrictive_umask(self):
        authority = self.authority()
        previous = os.umask(0o200)
        try:
            authority.write_control('kind-config.yaml', b'private')
        finally:
            os.umask(previous)
        row = authority.kind_config.stat()
        self.assertTrue(stat.S_ISREG(row.st_mode))
        self.assertEqual(stat.S_IMODE(row.st_mode), 0o600)
        self.assertEqual(row.st_uid, os.geteuid())
        self.assertEqual(row.st_nlink, 1)
        self.assertEqual(authority.kind_config.read_bytes(), b'private')

    def test_control_permission_failure_closes_fd_and_preserves_exclusive_file(self):
        authority = self.authority()
        opened = []
        real_open = os.open
        def tracked_open(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            opened.append(fd)
            return fd
        with patch.object(self.runtime.os, 'open', side_effect=tracked_open), \
                patch.object(self.runtime.os, 'fchmod', side_effect=OSError('injected fchmod failure')):
            with self.assertRaisesRegex(OSError, 'injected fchmod failure'):
                authority.write_control('kind-config.yaml', b'not-written')
        for fd in opened:
            with self.assertRaises(OSError):
                os.fstat(fd)
        self.assertEqual(authority.kind_config.read_bytes(), b'')
        with self.assertRaises(FileExistsError):
            authority.write_control('kind-config.yaml', b'no-overwrite')

    def test_control_rejects_hardlink_added_during_permission_enforcement(self):
        authority = self.authority()
        real_fchmod = os.fchmod
        def linked_fchmod(fd, mode):
            real_fchmod(fd, mode)
            os.link(authority.kind_config, authority.path / 'control-hardlink')
        with patch.object(self.runtime.os, 'fchmod', side_effect=linked_fchmod):
            with self.assertRaises(ValueError):
                authority.write_control('kind-config.yaml', b'not-written')
        self.assertEqual(authority.kind_config.read_bytes(), b'')
        self.assertEqual(authority.kind_config.stat().st_nlink, 2)

    def test_zero_control_write_closes_fd_and_does_not_remove_file(self):
        authority = self.authority()
        with patch.object(self.runtime.os, 'write', return_value=0):
            with self.assertRaisesRegex(OSError, 'short_runtime_control_write'):
                authority.write_control('kind-config.yaml', b'payload')
        self.assertEqual(authority.kind_config.read_bytes(), b'')
        with self.assertRaises(FileExistsError):
            authority.write_control('kind-config.yaml', b'payload')

    def test_authority_and_adapter_are_frozen_and_exact_type_only(self):
        authority = self.authority()
        adapter = self.adapter(Command(('colima', 'version'), 1), authority)
        with self.assertRaises(FrozenInstanceError):
            authority.path = self.parent / 'foreign'
        with self.assertRaises(FrozenInstanceError):
            adapter.command = object()
        class SubAuthority(self.runtime.RuntimeAuthority):
            pass
        class SubAdapter(self.runtime.ExploratoryColimaCommand):
            pass
        with self.assertRaises(ValueError):
            SubAuthority.create(self.store, self.digest)
        with self.assertRaises(ValueError):
            SubAdapter(Command(('colima', 'version'), 1), authority)
        object.__setattr__(adapter, 'command', object())
        with self.assertRaises(ValueError):
            adapter.__post_init__()


if __name__ == '__main__':
    unittest.main()
