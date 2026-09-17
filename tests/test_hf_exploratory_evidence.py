import importlib
import importlib.util
from hashlib import sha256
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kil.hf_exploratory_io import PrivateStore
from kil.hf_exploratory_runtime import RuntimeAuthority
from kil.v3b2_proofs import canonical


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('kil.hf_exploratory_evidence'),
                             'immutable runtime snapshot component is missing')
        self.evidence = importlib.import_module('kil.hf_exploratory_evidence')
        from kil import hf_exploratory_runtime as runtime_module
        compact = tempfile.TemporaryDirectory(prefix='k', dir='/private/tmp')
        self.addCleanup(compact.cleanup)
        self.registry = Path(compact.name).resolve() / 'k'
        selector = patch.object(runtime_module, '_registry_parent', return_value=self.registry, create=True)
        selector.start()
        self.addCleanup(selector.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        parent = Path(self.temp.name).resolve() / '.tools' / 'hf-exploratory-private'
        parent.mkdir(parents=True, mode=0o700)
        self.store = PrivateStore(parent / ('hf-exploratory-' + 'a' * 64))
        self.addCleanup(self.store.close)
        self.authority = RuntimeAuthority.create(self.store, 'a' * 64)
        self.addCleanup(self.authority.close)

    def populate(self):
        # Temporary observations only; these are not native compatibility fixtures.
        paths = [self.authority.kind_config, self.authority.kubeconfig,
                 self.authority.colima / 'kil-v3-lab' / 'colima.yaml',
                 self.authority.lima / 'colima-kil-v3-lab' / 'colima.yaml',
                 self.authority.lima / 'colima-kil-v3-lab' / 'lima.yaml',
                 self.authority.docker_config / 'config.json',
                 self.authority.docker_config / 'contexts' / 'meta' /
                 sha256(b'colima-kil-v3-lab').hexdigest() / 'meta.json']
        for index, path in enumerate(paths):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'temporary observation \xff\r\n' + str(index).encode())
        return paths

    def test_snapshot_retains_original_bytes_full_hashes_and_provenance(self):
        paths = self.populate()
        original = {str(path): path.read_bytes() for path in paths}
        ledger = self.evidence.snapshot_runtime(self.store, self.authority)
        self.assertEqual(ledger['schema'], 'kil.hf-exploratory-runtime-observations.v1')
        self.assertIs(ledger['observed_only'], True)
        self.assertEqual(ledger['runtime_path'], str(self.authority.path))
        self.assertEqual(ledger['receipt_path'], str(self.store.path))
        self.assertEqual(len(ledger['files']), 7)
        for row in ledger['files']:
            raw = original[row['runtime_path']]
            self.assertEqual(row['presence'], 'present')
            self.assertEqual(row['raw_sha256'], sha256(raw).hexdigest())
            self.assertEqual(row['byte_count'], len(raw))
            self.assertEqual((self.store.path / row['retained_file']).read_bytes(), raw)
            self.assertEqual(set(row['identity']), {'device', 'inode', 'mode'})
        self.assertEqual((self.store.path / 'runtime-observations.json').read_bytes(), canonical(ledger))
        saved = {path: sha256(path.read_bytes()).hexdigest() for path in self.store.path.iterdir()}
        paths[-1].unlink()
        self.assertEqual(saved, {path: sha256(path.read_bytes()).hexdigest() for path in self.store.path.iterdir()})

    def test_absent_observations_do_not_synthesize_native_files(self):
        ledger = self.evidence.snapshot_runtime(self.store, self.authority)
        for row in ledger['files']:
            self.assertEqual(row['presence'], 'absent')
            for key in ('identity', 'raw_sha256', 'byte_count', 'retained_file'):
                self.assertIsNone(row[key])
        self.assertFalse(self.authority.kind_config.exists())
        self.assertEqual(set(path.name for path in self.store.path.iterdir()),
                         {'lock', 'journal.jsonl', 'runtime-binding.json', 'runtime-observations.json'})

    def test_snapshots_are_one_shot_and_preserve_existing_bytes(self):
        self.populate()
        self.evidence.snapshot_runtime(self.store, self.authority)
        saved = {path: path.read_bytes() for path in self.store.path.iterdir()}
        with self.assertRaises(FileExistsError):
            self.evidence.snapshot_runtime(self.store, self.authority)
        self.assertEqual(saved, {path: path.read_bytes() for path in self.store.path.iterdir()})

    def test_repeat_after_absent_snapshot_cannot_add_new_raw_observations(self):
        self.evidence.snapshot_runtime(self.store, self.authority)
        saved = {path: path.read_bytes() for path in self.store.path.iterdir()}
        self.populate()
        with self.assertRaises(FileExistsError):
            self.evidence.snapshot_runtime(self.store, self.authority)
        self.assertEqual(saved, {path: path.read_bytes() for path in self.store.path.iterdir()})

    def test_snapshot_rejects_symlink_oversize_hardlink_and_directory(self):
        path = self.authority.kind_config
        target = self.authority.tmp / 'target'
        target.write_bytes(b'untouched')
        for kind in ('symlink', 'oversize', 'hardlink', 'directory'):
            with self.subTest(kind=kind):
                if kind == 'symlink':
                    path.symlink_to(target)
                elif kind == 'oversize':
                    path.write_bytes(b'x' * 65537)
                elif kind == 'hardlink':
                    os.link(target, path)
                else:
                    path.mkdir()
                try:
                    with self.assertRaises(ValueError):
                        self.evidence.snapshot_runtime(self.store, self.authority)
                    self.assertFalse((self.store.path / 'runtime-observations.json').exists())
                    self.assertEqual(target.read_bytes(), b'untouched')
                finally:
                    path.rmdir() if kind == 'directory' else path.unlink()

    def test_closed_and_foreign_authorities_and_nonexact_types_refuse(self):
        class SubStore(PrivateStore):
            pass
        class SubAuthority(RuntimeAuthority):
            pass
        for store, authority in [(object(), self.authority), (self.store, object()),
                                 (object.__new__(SubStore), self.authority),
                                 (self.store, object.__new__(SubAuthority))]:
            with self.subTest(store=type(store), authority=type(authority)):
                with self.assertRaises(ValueError):
                    self.evidence.snapshot_runtime(store, authority)
        foreign = PrivateStore(self.store.path.with_name('foreign'))
        self.addCleanup(foreign.close)
        with self.assertRaises(ValueError):
            self.evidence.snapshot_runtime(foreign, self.authority)
        self.authority.close()
        with self.assertRaises(ValueError):
            self.evidence.snapshot_runtime(self.store, self.authority)
        with self.assertRaises(ValueError):
            self.evidence.observe_runtime_leftovers(self.authority)

    def test_changed_second_capture_refuses_before_any_retention(self):
        self.populate()
        real_read = self.evidence._read
        calls = []
        def read(path, **kwargs):
            calls.append(path)
            if len(calls) == 8:
                path.rename(path.with_name('original'))
                path.write_bytes(b'replaced during second capture')
            return real_read(path, **kwargs)
        with patch.object(self.evidence, '_read', side_effect=read):
            with self.assertRaises(ValueError):
                self.evidence.snapshot_runtime(self.store, self.authority)
        self.assertEqual(set(path.name for path in self.store.path.iterdir()),
                         {'lock', 'journal.jsonl', 'runtime-binding.json'})

    def test_persistence_failure_propagates_and_keeps_partial(self):
        self.populate()
        with patch('kil.hf_exploratory_io.os.fsync', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.evidence.snapshot_runtime(self.store, self.authority)
        self.assertTrue((self.store.path / 'runtime-kind-config.yaml').exists())
        self.assertFalse((self.store.path / 'runtime-observations.json').exists())

    def test_leftovers_are_partial_named_directories_only_and_do_not_delete(self):
        self.populate()
        unknown = self.authority.tmp / 'unknown'
        unknown.mkdir()
        (unknown / 'unread').symlink_to('/does-not-exist')
        result = self.evidence.observe_runtime_leftovers(self.authority)
        self.assertIs(result['partial'], True)
        self.assertEqual(result['scope'], 'named namespace directories only')
        self.assertEqual(set(row['runtime_path'] for row in result['directories']),
                         {str(path) for path in (self.authority.path, self.authority.colima,
                                                self.authority.lima, self.authority.docker_config,
                                                self.authority.tmp)})
        self.assertTrue((unknown / 'unread').is_symlink())
        for row in result['directories']:
            self.assertIn('entries', row['observation'])

    def test_leftovers_reject_nonexact_authority_and_stale_namespace(self):
        with self.assertRaises(ValueError):
            self.evidence.observe_runtime_leftovers(self.authority.path)
        self.authority.tmp.rename(self.authority.path / 'old-tmp')
        self.authority.tmp.mkdir(mode=0o700)
        with self.assertRaises(ValueError):
            self.evidence.observe_runtime_leftovers(self.authority)

    def test_leftovers_reject_changed_second_observation(self):
        real_read = self.evidence._read
        calls = []
        def read(path, **kwargs):
            calls.append(path)
            if len(calls) == 6:
                (self.authority.tmp / 'appeared').write_bytes(b'x')
            return real_read(path, **kwargs)
        with patch.object(self.evidence, '_read', side_effect=read):
            with self.assertRaises(ValueError):
                self.evidence.observe_runtime_leftovers(self.authority)

    def test_leftovers_enforces_per_directory_bound(self):
        for index in range(4097):
            (self.authority.tmp / str(index)).touch()
        with self.assertRaises(ValueError):
            self.evidence.observe_runtime_leftovers(self.authority)
