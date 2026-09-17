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
        self.compact = tempfile.TemporaryDirectory(prefix='k', dir='/private/tmp')
        self.addCleanup(self.compact.cleanup)
        self.registry = Path(self.compact.name).resolve() / 'k'
        self.selector_original = self.runtime._registry_parent
        selector = patch.object(self.runtime, '_registry_parent', return_value=self.registry, create=True)
        selector.start()
        self.addCleanup(selector.stop)
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
        self.assertEqual(authority.path, self.registry / ('r' + self.digest[:16]))
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

    def test_compact_locator_has_full_receipt_identity_and_durable_binding(self):
        import json
        from kil.v3b2_proofs import canonical
        authority = self.authority()
        self.assertEqual(authority.path, self.registry / ('r' + self.digest[:16]))
        projection = authority.path / '.colima/_lima/colima-kil-v3-lab/ssh.sock.1234567890123456'
        self.assertLess(len(os.fsencode(projection)), 104)
        marker = {'schema': 'kil.hf-exploratory-runtime-registry.v1',
                  'uid': os.geteuid(), 'runtime_parent': str(self.registry)}
        self.assertEqual((self.registry / 'registry.json').read_bytes(), canonical(marker))
        row = authority.path.stat()
        binding = {'schema': 'kil.hf-exploratory-runtime-binding.v1', 'uid': os.geteuid(),
                   'run_digest': self.digest, 'run_id': 'v3b2-' + self.digest,
                   'receipt_path': str(self.store.path), 'registry_path': str(self.registry),
                   'runtime_path': str(authority.path), 'runtime_identity': {
                       'device': row.st_dev, 'inode': row.st_ino, 'mode': row.st_mode, 'uid': row.st_uid}}
        payload = (self.store.path / 'runtime-binding.json').read_bytes()
        self.assertEqual(json.loads(payload), binding)
        self.assertEqual(payload, canonical(binding))
        authority.guard()

    def test_existing_unmarked_registry_is_not_repaired(self):
        self.registry.mkdir(mode=0o700)
        with self.assertRaises(ValueError):
            self.authority()
        self.assertEqual(list(self.registry.iterdir()), [])

    def test_receipt_name_substitution_during_walk_refuses_before_allocation(self):
        real_open = os.open
        moved = self.store.path.with_name('moved-receipt')
        def replaced_open(name, *args, **kwargs):
            fd = real_open(name, *args, **kwargs)
            if name == self.store.path.name:
                self.store.path.rename(moved)
                self.store.path.mkdir(mode=0o700)
            return fd
        with patch.object(self.runtime.os, 'open', side_effect=replaced_open):
            with self.assertRaises(ValueError):
                self.authority()
        self.assertFalse(self.registry.exists())

    def test_duplicate_auth_descriptor_substitution_is_refused(self):
        authority = self.authority()
        original = authority._marker
        duplicate = os.dup(original[2])
        try:
            object.__setattr__(authority, '_marker', (*original[:2], duplicate, *original[3:]))
            with self.assertRaises(ValueError):
                authority.guard()
        finally:
            object.__setattr__(authority, '_marker', original)
            os.close(duplicate)

    def second_store(self, digest):
        store = PrivateStore(self.parent / ('hf-exploratory-' + digest))
        self.addCleanup(store.close)
        return store

    def test_prefix_collision_preserves_first_root_and_refuses_second_binding(self):
        first = self.authority()
        digest = self.digest[:16] + 'b' * 48
        store = self.second_store(digest)
        before = sorted(path.name for path in self.registry.iterdir())
        with self.assertRaises(ValueError):
            self.runtime.RuntimeAuthority.create(store, digest)
        self.assertEqual(sorted(path.name for path in self.registry.iterdir()), before)
        self.assertFalse((store.path / 'runtime-binding.json').exists())
        first.guard()

    def test_marked_registry_reuse_keeps_marker_and_separate_full_bindings(self):
        first = self.authority()
        marker = (self.registry / 'registry.json').read_bytes()
        digest = 'b' * 64
        store = self.second_store(digest)
        second = self.runtime.RuntimeAuthority.create(store, digest)
        self.addCleanup(second.close)
        self.assertNotEqual(first.path, second.path)
        self.assertEqual(second.path, self.registry / ('r' + digest[:16]))
        self.assertEqual((self.registry / 'registry.json').read_bytes(), marker)
        self.assertNotEqual((self.store.path / 'runtime-binding.json').read_bytes(),
                            (store.path / 'runtime-binding.json').read_bytes())
        first.guard()
        second.guard()

    def test_socket_projection_byte_boundary_103_allowed_104_refused(self):
        suffix = '.colima/_lima/colima-kil-v3-lab/ssh.sock.1234567890123456'
        width = 103 - len(os.fsencode(self.registry.parent / ('r' + self.digest[:16]) / suffix)) - 1
        short = self.registry.with_name('k' * width)
        long = self.registry.with_name('k' * (width + 1))
        self.assertEqual(len(os.fsencode(short / ('r' + self.digest[:16]) / suffix)), 103)
        self.assertEqual(len(os.fsencode(long / ('r' + self.digest[:16]) / suffix)), 104)
        with patch.object(self.runtime, '_registry_parent', return_value=long):
            with self.assertRaises(ValueError):
                self.authority()
        self.assertFalse(long.exists())
        with patch.object(self.runtime, '_registry_parent', return_value=short):
            authority = self.authority()
            authority.guard()
            with patch.object(self.runtime, '_registry_parent', return_value=long):
                with self.assertRaises(ValueError):
                    authority.guard()

    def test_selector_uses_actual_passwd_home_not_environment(self):
        from kil.v3b2_profile_state import passwd_home
        # Temporarily stop only this fixture patch to inspect the pure selector.
        production = self.selector_original
        with patch.dict(os.environ, {'HOME': '/private/tmp/foreign', 'TMPDIR': '/private/tmp/foreign'}):
            self.assertEqual(production(), passwd_home() / '.kil-hf')

    def test_selector_refuses_noncanonical_passwd_home(self):
        home = Path(self.compact.name).resolve()
        alias = home / 'home-alias'
        alias.symlink_to(home, target_is_directory=True)
        for path in (alias, home / '..' / home.name, Path('/'), Path('relative')):
            with self.subTest(path=path), patch.object(self.runtime, 'passwd_home', return_value=path):
                with self.assertRaises(ValueError):
                    self.selector_original()
        self.assertFalse(self.registry.exists())

    def test_uid_mismatch_refuses_create_before_allocation_and_live_guard(self):
        with patch.object(self.runtime.os, 'getuid', return_value=os.geteuid() + 1):
            with self.assertRaises(ValueError):
                self.authority()
        self.assertFalse(self.registry.exists())
        authority = self.authority()
        with patch.object(self.runtime.os, 'getuid', return_value=os.geteuid() + 1):
            with self.assertRaises(ValueError):
                authority.guard()

    def test_registry_and_receipt_ancestries_are_both_live_guards(self):
        authority = self.authority()
        for path in (self.registry, Path(self.compact.name).resolve(), self.store.path):
            moved = path.with_name(path.name + '-moved')
            with self.subTest(path=path):
                path.rename(moved)
                try:
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
                authority.guard()

    def test_auth_files_refuse_real_types_bytes_identity_links_and_mode_drift(self):
        import json
        from kil.v3b2_proofs import canonical
        authority = self.authority()
        for path in (self.registry / 'registry.json', self.store.path / 'runtime-binding.json'):
            payload = path.read_bytes()
            document = json.loads(payload)
            replacements = [b'not json', b'x' * 8193, payload.rstrip(b'\n'),
                            canonical({**document, 'uid': True}),
                            canonical({**document, 'uid': str(os.geteuid())}),
                            canonical({**document, 'extra': 1}),
                            canonical({key: value for key, value in document.items() if key != 'uid'})]
            if 'run_digest' in document:
                replacements.extend((canonical({**document, 'run_digest': 'b' * 64}),
                    canonical({**document, 'run_id': 'v3b2-' + self.digest[:16]}),
                    canonical({**document, 'runtime_identity': {**document['runtime_identity'], 'inode': True}})))
            for changed in replacements:
                with self.subTest(path=path, payload=changed[:70]):
                    path.write_bytes(changed)
                    with self.assertRaises(ValueError):
                        authority.guard()
            path.write_bytes(payload)
            # Restoring bytes cannot restore retained mtime/ctime identity.
            with self.assertRaises(ValueError):
                authority.guard()

    def test_marker_name_replacement_same_bytes_is_refused(self):
        authority = self.authority()
        marker = self.registry / 'registry.json'
        payload = marker.read_bytes()
        marker.rename(self.registry / 'old-marker')
        marker.write_bytes(payload)
        marker.chmod(0o600)
        with self.assertRaises(ValueError):
            self.runtime.ExploratoryColimaCommand(Command(('colima', 'version'), 1), authority)

    def test_marker_foreign_uid_field_refuses_exact_adapter(self):
        import json
        from kil.v3b2_proofs import canonical
        authority = self.authority()
        marker = self.registry / 'registry.json'
        document = json.loads(marker.read_bytes())
        document['foreign_uid'] = document.pop('uid')
        marker.write_bytes(canonical(document))
        with self.assertRaises(ValueError):
            self.runtime.ExploratoryColimaCommand(Command(('colima', 'version'), 1), authority)

    def test_binding_written_with_foreign_types_never_returns_authority(self):
        import json
        from kil.v3b2_proofs import canonical
        real_write = PrivateStore.write
        for index, case in enumerate(('uid-bool', 'uid-string', 'extra', 'missing', 'identity-bool',
                                      'full-digest', 'receipt', 'registry', 'root', 'noncanonical')):
            digest = format(index + 1, '064x')
            store = self.second_store(digest)
            with self.subTest(case=case), tempfile.TemporaryDirectory(prefix='k', dir='/private/tmp') as fixture:
                registry = Path(fixture).resolve() / 'k'
                def replaced_write(candidate, name, payload):
                    if name == 'runtime-binding.json':
                        document = json.loads(payload)
                        if case == 'uid-bool':
                            document['uid'] = True
                        elif case == 'uid-string':
                            document['uid'] = str(document['uid'])
                        elif case == 'extra':
                            document['extra'] = 1
                        elif case == 'missing':
                            del document['run_id']
                        elif case == 'identity-bool':
                            document['runtime_identity']['inode'] = True
                        elif case == 'full-digest':
                            document['run_digest'] = digest[:16]
                        elif case == 'receipt':
                            document['receipt_path'] = str(self.store.path)
                        elif case == 'registry':
                            document['registry_path'] = '/private/tmp/foreign'
                        elif case == 'root':
                            document['runtime_path'] = str(registry / 'rffffffffffffffff')
                        payload = canonical(document)
                        if case == 'noncanonical':
                            payload += b' '
                    return real_write(candidate, name, payload)
                with patch.object(self.runtime, '_registry_parent', return_value=registry), \
                        patch.object(PrivateStore, 'write', new=replaced_write):
                    with self.assertRaises(ValueError):
                        self.runtime.RuntimeAuthority.create(store, digest)
                self.assertTrue((store.path / 'runtime-binding.json').is_file())
                self.assertTrue((registry / ('r' + digest[:16]) / 'runtime-tmp').is_dir())

    def test_binding_name_replacement_same_bytes_is_refused(self):
        authority = self.authority()
        binding = self.store.path / 'runtime-binding.json'
        payload = binding.read_bytes()
        binding.rename(self.store.path / 'old-binding')
        binding.write_bytes(payload)
        binding.chmod(0o600)
        with self.assertRaises(ValueError):
            authority.guard()

    def test_auth_files_hardlink_and_mode_drift_are_refused(self):
        authority = self.authority()
        for path in (self.registry / 'registry.json', self.store.path / 'runtime-binding.json'):
            with self.subTest(path=path):
                path.chmod(0o400)
                with self.assertRaises(ValueError):
                    authority.guard()
                path.chmod(0o600)
                link = path.with_name(path.name + '-hardlink')
                os.link(path, link)
                with self.assertRaises(ValueError):
                    authority.guard()
                self.assertEqual(path.stat().st_nlink, 2)

    def test_binding_read_cannot_leave_earlier_marker_substituted(self):
        authority = self.authority()
        real_read = os.read
        marker = self.registry / 'registry.json'
        replaced = []
        def replacing_read(fd, count):
            payload = real_read(fd, count)
            if fd == authority._binding[2] and not replaced:
                replaced.append(True)
                original = marker.read_bytes()
                marker.rename(self.registry / 'old-marker')
                marker.write_bytes(original)
                marker.chmod(0o600)
            return payload
        with patch.object(self.runtime.os, 'read', side_effect=replacing_read):
            with self.assertRaises(ValueError):
                authority.guard()

    def test_complete_auth_read_handles_real_short_reads(self):
        authority = self.authority()
        real_read = os.read
        with patch.object(self.runtime.os, 'read', side_effect=lambda fd, count: real_read(fd, min(count, 3))):
            authority.guard()

    def test_guard_refuses_substituted_digest_store_handles_and_layout(self):
        authority = self.authority()
        for name, changed in (('_digest', self.digest[:16] + 'b' * 48),
                               ('_store', object()), ('_store_fd', authority._root_fd),
                               ('_root_fd', authority._store_fd), ('_closed', 0),
                               ('_anchors', tuple(reversed(authority._anchors))),
                               ('_descriptors', tuple(reversed(authority._descriptors)))):
            original = getattr(authority, name)
            with self.subTest(name=name):
                object.__setattr__(authority, name, changed)
                try:
                    with self.assertRaises(ValueError):
                        authority.guard()
                finally:
                    object.__setattr__(authority, name, original)
        authority.guard()

    def test_guard_refuses_same_numeric_but_foreign_handle_types(self):
        authority = self.authority()
        for name in ('_root_fd', '_store_fd', '_lock_fd'):
            original = getattr(authority, name)
            with self.subTest(name=name):
                object.__setattr__(authority, name, float(original))
                try:
                    with self.assertRaises(ValueError):
                        authority.guard()
                finally:
                    object.__setattr__(authority, name, original)

    def test_guard_refuses_same_numeric_but_foreign_lock_identity_type(self):
        authority = self.authority()
        original = authority._lock_identity
        object.__setattr__(authority, '_lock_identity', (float(original[0]), *original[1:]))
        try:
            with self.assertRaises(ValueError):
                authority.guard()
        finally:
            object.__setattr__(authority, '_lock_identity', original)

    def test_failed_binding_persistence_closes_fds_and_leaves_bootstrap(self):
        opened = []
        real_open, real_write = os.open, PrivateStore.write
        def tracked_open(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            opened.append(fd)
            return fd
        def failed_write(store, name, payload):
            if name == 'runtime-binding.json':
                real_write(store, name, payload)
                raise OSError('injected after binding persistence')
            return real_write(store, name, payload)
        with patch.object(self.runtime.os, 'open', side_effect=tracked_open), \
                patch.object(PrivateStore, 'write', new=failed_write):
            with self.assertRaises(ValueError):
                self.authority()
        for fd in set(opened):
            with self.assertRaises(OSError):
                os.fstat(fd)
        self.assertTrue((self.registry / 'registry.json').is_file())
        self.assertTrue((self.registry / ('r' + self.digest[:16]) / 'runtime-tmp').is_dir())
        self.assertTrue((self.store.path / 'runtime-binding.json').is_file())
        self.store.write('still-live', b'ok')

    def test_failed_marker_bootstrap_is_not_repaired_on_retry(self):
        with patch.object(self.runtime.os, 'write', return_value=0):
            with self.assertRaises(ValueError):
                self.authority()
        marker = self.registry / 'registry.json'
        self.assertEqual(marker.read_bytes(), b'')
        self.assertEqual(sorted(path.name for path in self.registry.iterdir()), ['registry.json'])
        with self.assertRaises(ValueError):
            self.authority()
        self.assertEqual(marker.read_bytes(), b'')
        self.assertFalse((self.registry / ('r' + self.digest[:16])).exists())

    def test_unsafe_existing_registry_and_marker_refuse_without_repair_or_run(self):
        from kil.v3b2_proofs import canonical
        cases = ('unmarked', 'registry-file', 'registry-link', 'registry-mode',
                 'marker-directory', 'marker-link', 'marker-fifo', 'marker-hardlink',
                 'marker-mode', 'marker-empty', 'marker-oversize', 'marker-foreign-uid',
                 'marker-bool-uid', 'marker-extra', 'marker-missing', 'marker-noncanonical')
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory(prefix='k', dir='/private/tmp') as fixture:
                registry = Path(fixture).resolve() / 'k'
                if case == 'registry-file':
                    registry.write_bytes(b'preserved')
                    registry.chmod(0o600)
                elif case == 'registry-link':
                    registry.symlink_to(self.store.path, target_is_directory=True)
                else:
                    registry.mkdir(mode=0o700)
                    marker = registry / 'registry.json'
                    document = {'schema': 'kil.hf-exploratory-runtime-registry.v1',
                                'uid': os.geteuid(), 'runtime_parent': str(registry)}
                    if case == 'registry-mode':
                        registry.chmod(0o755)
                    elif case == 'marker-directory':
                        marker.mkdir(mode=0o700)
                    elif case == 'marker-link':
                        marker.symlink_to(self.store.path / 'lock')
                    elif case == 'marker-fifo':
                        os.mkfifo(marker, mode=0o600)
                    elif case != 'unmarked':
                        if case == 'marker-foreign-uid':
                            document['uid'] += 1
                        elif case == 'marker-bool-uid':
                            document['uid'] = True
                        elif case == 'marker-extra':
                            document['extra'] = 0
                        elif case == 'marker-missing':
                            del document['uid']
                        payload = (b'' if case == 'marker-empty' else
                                   b'x' * 8193 if case == 'marker-oversize' else
                                   canonical(document) + b' ' if case == 'marker-noncanonical' else
                                   canonical(document))
                        marker.write_bytes(payload)
                        marker.chmod(0o400 if case == 'marker-mode' else 0o600)
                        if case == 'marker-hardlink':
                            os.link(marker, registry / 'hardlink')
                before = os.lstat(registry)
                roster = sorted(path.name for path in registry.iterdir()) if registry.is_dir() and not registry.is_symlink() else None
                with patch.object(self.runtime, '_registry_parent', return_value=registry):
                    with self.assertRaises(ValueError):
                        self.authority()
                after = os.lstat(registry)
                self.assertEqual((before.st_dev, before.st_ino, before.st_mode),
                                 (after.st_dev, after.st_ino, after.st_mode))
                if roster is not None:
                    self.assertEqual(sorted(path.name for path in registry.iterdir()), roster)
                    self.assertNotIn('r' + self.digest[:16], roster)
                self.assertFalse((self.store.path / 'runtime-binding.json').exists())

    def test_auth_file_descriptors_are_readonly_nonblocking_and_close_once(self):
        import fcntl
        authority = self.authority()
        owned = authority._descriptors
        for record in (authority._marker, authority._binding):
            flags = fcntl.fcntl(record[2], fcntl.F_GETFL)
            self.assertEqual(flags & os.O_ACCMODE, os.O_RDONLY)
            self.assertTrue(flags & os.O_NONBLOCK)
        real_close = os.close
        closed = []
        def tracked_close(fd):
            closed.append(fd)
            real_close(fd)
        with patch.object(self.runtime.os, 'close', side_effect=tracked_close):
            authority.close()
            authority.close()
        self.assertEqual(closed, list(reversed(owned)))
        for fd in owned:
            with self.assertRaises(OSError):
                os.fstat(fd)
        self.assertTrue((self.registry / 'registry.json').is_file())
        self.assertTrue((self.store.path / 'runtime-binding.json').is_file())

    def test_marker_bootstrap_fsync_failure_closes_all_fds_preserves_partial_marker(self):
        opened = []
        real_open, real_fsync = os.open, os.fsync
        writer = []
        def tracked_open(name, *args, **kwargs):
            fd = real_open(name, *args, **kwargs)
            opened.append(fd)
            if name == 'registry.json':
                writer.append(fd)
            return fd
        def failed_fsync(fd):
            if fd in writer:
                raise OSError('injected marker fsync failure')
            real_fsync(fd)
        with patch.object(self.runtime.os, 'open', side_effect=tracked_open), \
                patch.object(self.runtime.os, 'fsync', side_effect=failed_fsync):
            with self.assertRaises(ValueError):
                self.authority()
        for fd in set(opened):
            with self.assertRaises(OSError):
                os.fstat(fd)
        self.assertTrue((self.registry / 'registry.json').is_file())
        self.assertFalse((self.registry / ('r' + self.digest[:16])).exists())

    def test_ordinary_ancestor_roster_changes_are_not_immutable(self):
        authority = self.authority()
        (Path(self.compact.name).resolve() / 'ordinary-sibling').write_bytes(b'new')
        (self.parent.parent / 'ordinary-sibling').mkdir()
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
        self.assertFalse(self.registry.exists())

    def test_create_rejects_nonprivate_store_before_runtime_creation(self):
        self.store.path.chmod(0o755)
        with self.assertRaises(ValueError):
            self.authority()
        self.assertFalse(self.registry.exists())
        self.assertTrue((self.store.path / 'lock').exists())

    def test_create_rejects_nonprivate_or_hardlinked_lock_before_runtime_creation(self):
        lock = self.store.path / 'lock'
        lock.chmod(0o400)
        with self.assertRaises(ValueError):
            self.authority()
        self.assertFalse(self.registry.exists())
        lock.chmod(0o600)
        os.link(lock, self.store.path / 'lock-hardlink')
        with self.assertRaises(ValueError):
            self.authority()
        self.assertFalse(self.registry.exists())
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
        first = self.authority()
        path = first.path
        marker = path / 'marker'
        marker.write_bytes(b'preserved')
        with self.assertRaises((ValueError, OSError)):
            self.authority()
        self.assertEqual(marker.read_bytes(), b'preserved')
        moved = path.with_name('preserved-runtime')
        path.rename(moved)
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
            with self.assertRaises(ValueError) as failure:
                self.authority()
        self.assertEqual(str(failure.exception.__cause__), 'injected mkdir failure')
        for fd in set(opened):
            with self.assertRaises(OSError):
                os.fstat(fd)
        path = self.registry / ('r' + self.digest[:16])
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
            with self.assertRaises(ValueError):
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
        self.assertFalse(self.registry.exists())
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
