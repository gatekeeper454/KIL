import importlib
import importlib.util
import copy
from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kil.hf_exploratory_io import PrivateStore
from kil.hf_exploratory_runtime import RuntimeAuthority, ExploratoryColimaCommand
from kil.v3b2_journal import Command
from kil import v3b2_profile_state as strict

FIXTURES = Path(__file__).parent / 'fixtures'
PROFILE_HASH = '5b4a547ad13cda67870cdb821fbb140940562626c28ef6fb1228191675dc79e9'
INSTANCE_HASH = '37dff309a27985cf3a007517133c66a436fb578a5d14fd6df0c9ababeb7503de'
ALIAS = b'  dnsHosts:\n    host.docker.internal: host.lima.internal\n'


class ExploratoryProfileTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('kil.hf_exploratory_profile'),
                             'exploratory native configuration binding is missing')
        self.module = importlib.import_module('kil.hf_exploratory_profile')
        from kil import hf_exploratory_runtime as runtime_module
        self.compact = tempfile.TemporaryDirectory(prefix='k', dir='/private/tmp')
        self.addCleanup(self.compact.cleanup)
        self.registry = Path(self.compact.name).resolve() / 'k'
        selector = patch.object(runtime_module, '_registry_parent', return_value=self.registry, create=True)
        selector.start()
        self.addCleanup(selector.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.runtime = self.root / '.tools' / 'hf-exploratory-private' / ('hf-exploratory-runtime-' + 'a' * 64)
        self.paths = self.module.ProfilePaths(strict.passwd_home(), self.runtime)
        self.profile = (FIXTURES / 'hf-colima-0.10.3-profile.yaml').read_bytes()
        self.instance = (FIXTURES / 'hf-colima-0.10.3-instance.yaml').read_bytes()

    def create(self):
        for path in (self.paths.profile, self.paths.instance, self.paths.disk):
            path.mkdir(parents=True)
        (self.paths.profile / 'colima.yaml').write_bytes(self.profile)
        (self.paths.instance / 'colima.yaml').write_bytes(self.instance)
        (self.paths.instance / 'lima.yaml').write_bytes(b'# retained native Lima bytes\nvmType: vz\n')
        for path, size in ((self.paths.disk / 'datadisk', 60 * 1024**3),
                           (self.paths.instance / 'disk', 20 * 1024**3)):
            with path.open('wb') as stream:
                stream.truncate(size)
        (self.paths.disk / 'in_use_by').symlink_to(self.paths.instance)
        return self.module.capture(self.paths)

    def binding(self, observed):
        return self.module.creation_binding(self.paths.document(), observed)

    def test_native_binding_module_exists(self):
        self.assertTrue(callable(self.module.creation_binding))
        self.assertIs(self.module.capture, strict.capture)
        self.assertIs(self.module.validate_capture, strict.validate_capture)
        self.assertIs(self.module.validate_binding, strict.validate_binding)

    def test_guard_capture_restarts_entire_observation_after_metadata_race(self):
        observed = self.create()
        error = strict.ProfileStateError('profile file changed during observation')
        with patch.object(self.module, 'capture', side_effect=[error] * 4 + [observed]) as read:
            self.assertIs(self.module.capture_for_guard(self.paths), observed)
        self.assertEqual(read.call_count, 5)
        self.assertEqual(read.call_args_list, [((self.paths,), {})] * 5)

    def test_guard_capture_exhausts_and_never_retries_other_errors(self):
        error = strict.ProfileStateError('profile file changed during observation')
        with patch.object(self.module, 'capture', side_effect=error) as read:
            with self.assertRaisesRegex(strict.ProfileStateError, '^profile file changed during observation$'):
                self.module.capture_for_guard(self.paths)
        self.assertEqual(read.call_count, 5)
        for message in ('profile footprint changed during observation', 'profile symlink is forbidden',
                        'profile file entry changed during observation', 'profile file size changed'):
            with patch.object(self.module, 'capture', side_effect=strict.ProfileStateError(message)) as read:
                with self.assertRaisesRegex(strict.ProfileStateError, message):
                    self.module.capture_for_guard(self.paths)
            self.assertEqual(read.call_count, 1)

    def test_guard_retry_does_not_adopt_changed_binding(self):
        observed = self.create()
        binding = self.binding(observed)
        changed = copy.deepcopy(observed)
        changed['lima_config']['hex'] += b'# changed configuration\n'.hex()
        error = strict.ProfileStateError('profile file changed during observation')
        with patch.object(self.module, 'capture', side_effect=[error, changed]):
            latest = self.module.capture_for_guard(self.paths)
        self.assertFalse(self.module.unchanged(self.paths.document(), latest, binding))

    def test_independent_full_native_fixtures_and_original_hashes(self):
        self.assertEqual(sha256(self.profile).hexdigest(), PROFILE_HASH)
        self.assertEqual(sha256(self.instance).hexdigest(), INSTANCE_HASH)
        self.assertGreater(len(self.profile), 8000)
        observed = self.create()
        binding = self.binding(observed)
        self.assertEqual(binding['config_sha256'], {'profile': PROFILE_HASH, 'instance': INSTANCE_HASH})
        self.assertEqual(binding['lima_config_sha256'], sha256(bytes.fromhex(observed['lima_config']['hex'])).hexdigest())
        self.assertEqual(set(binding['resources']), {'profile', 'instance', 'disk', 'profile_config', 'instance_config', 'data_disk', 'root_disk', 'lima_config'})
        self.assertEqual(binding['lock_target'], str(self.paths.instance))
        self.assertEqual(binding['data_disk_size'], 60 * 1024**3)
        self.assertEqual(binding['data_disk_format'], 'raw')
        strict.validate_binding(binding)

    def test_paths_are_private_native_namespace_not_passwd_home(self):
        p = self.paths
        self.assertEqual(p.document(), {'home': str(strict.passwd_home()), 'runtime': str(self.runtime)})
        for name, expected in {'colima': self.runtime / '.colima', 'lima': self.runtime / '.colima/_lima',
                               'profile': self.runtime / '.colima/kil-v3-lab',
                               'instance': self.runtime / '.colima/_lima/colima-kil-v3-lab',
                               'disk': self.runtime / '.colima/_lima/_disks/colima-kil-v3-lab',
                               'store': self.runtime / '.colima/_store/colima-kil-v3-lab.json',
                               'private': self.runtime, 'tmp': self.runtime / 'runtime-tmp',
                               'startup': self.runtime / 'runtime-tmp/colima-kil-v3-lab.yaml'}.items():
            self.assertEqual(getattr(p, name), expected)
        with self.assertRaises(FrozenInstanceError):
            p.runtime = self.root

    def test_bind_exact_live_authority_uses_actual_passwd_home(self):
        parent = self.runtime.parent
        parent.mkdir(parents=True, mode=0o700)
        store = PrivateStore(parent / ('hf-exploratory-' + 'a' * 64))
        self.addCleanup(store.close)
        authority = RuntimeAuthority.create(store, 'a' * 64)
        self.addCleanup(authority.close)
        with patch.dict(os.environ, {'HOME': str(self.root / 'fake')}):
            p = self.module.ProfilePaths.bind(authority)
        self.assertEqual(p.home, strict.passwd_home())
        self.assertEqual(p.runtime, authority.path)
        adapter = ExploratoryColimaCommand(Command(('colima', 'status', '--profile', 'kil-v3-lab'), 30), authority)
        self.assertIn(('COLIMA_HOME', str(p.colima)), adapter.env)
        self.assertIn(('LIMA_HOME', str(p.lima)), adapter.env)
        for value in (authority.path, object(), None):
            with self.assertRaises(ValueError):
                self.module.ProfilePaths.bind(value)
        authority.close()
        with self.assertRaises(ValueError):
            self.module.ProfilePaths.bind(authority)

    def test_pure_paths_reject_noncanonical_or_foreign_runtime(self):
        for home, runtime in ((Path('/'), self.runtime), (Path('relative'), self.runtime),
                              (Path('/a/../b'), self.runtime), (str(self.root), self.runtime),
                              (self.root, Path('/')), (self.root, Path('relative')),
                              (self.root, self.runtime.with_name('hf-exploratory-runtime-' + 'A' * 64)),
                              (self.root, self.runtime.with_name('hf-exploratory-runtime-' + 'a' * 63)),
                              (self.root, self.root / self.runtime.name),
                              (self.root, self.runtime / '..' / self.runtime.name)):
            with self.subTest(home=home, runtime=runtime), self.assertRaises(ValueError):
                self.module.ProfilePaths(home, runtime)

    def test_pure_compact_paths_roundtrip_and_reject_foreign_parent(self):
        runtime = self.registry / ('r' + 'a' * 16)
        paths = self.module.ProfilePaths(strict.passwd_home(), runtime)
        self.assertEqual(self.module._paths(paths.document()), paths)
        with self.assertRaises(ValueError):
            self.module.ProfilePaths(strict.passwd_home(), self.root / runtime.name)

    def test_generated_instance_alias_and_strict_profile_remain_distinct(self):
        result = self.module.parse_saved_instance(self.instance)
        self.assertEqual(result['network']['dnsHosts'], {'host.docker.internal': 'host.lima.internal'})
        self.assertEqual(strict.parse_saved(self.profile)['network']['dnsHosts'], {})
        with self.assertRaises(ValueError):
            strict.parse_saved(self.instance)

    def test_instance_rejects_missing_wrong_extra_duplicate_or_ambiguous_alias(self):
        payloads = (self.profile, b'', self.instance.replace(ALIAS, b'  dnsHosts: {}\n'),
                    self.instance.replace(b'host.lima.internal\n', b'wrong.internal\n'),
                    self.instance.replace(ALIAS, ALIAS + b'    other.internal: host.lima.internal\n'),
                    self.instance.replace(ALIAS, ALIAS + b'    host.docker.internal: host.lima.internal\n'),
                    self.instance.replace(ALIAS, ALIAS + ALIAS),
                    self.instance.replace(ALIAS, b'  dnsHosts: &alias\n    host.docker.internal: host.lima.internal\n'),
                    self.instance.replace(ALIAS, b'  dnsHosts: !!map\n    host.docker.internal: host.lima.internal\n'),
                    self.instance.replace(ALIAS, ALIAS.replace(b'    host', b'   host')),
                    self.instance.replace(b'mounts: null', b'mounts: []'),
                    self.instance + b'unknown: false\n', self.instance + b'cpu: 4\n',
                    self.instance.replace(b'cpu: 4', b'cpu: 04'),
                    self.instance.replace(b'cpu: 4', b'cpu: 5'), b'#' * (strict.MAX_CONFIG + 1))
        for payload in payloads:
            with self.subTest(payload=payload[-150:]), self.assertRaises(ValueError):
                self.module.parse_saved_instance(payload)
        for payload in (self.instance.decode(), bytearray(self.instance), None):
            with self.assertRaises(ValueError):
                self.module.parse_saved_instance(payload)

    def test_creation_refuses_generated_profile_and_ungenerated_instance(self):
        observed = self.create()
        for key, payload in (('profile_config', self.instance), ('instance_config', self.profile)):
            changed = copy.deepcopy(observed)
            changed[key]['hex'] = payload.hex()
            with self.assertRaises(ValueError):
                self.binding(changed)

    def test_protected_startup_foreign_lock_and_disk_capacity_refused(self):
        observed = self.create()
        for key, field, value in (('lock', 'target', str(self.paths.home / '.colima/_lima/colima-kil-v3-lab')),
                                  ('data_disk', 'size', 59 * 1024**3), ('root_disk', 'size', 19 * 1024**3),
                                  ('data_disk', 'format', 'qcow2'), ('root_disk', 'format_probe_hex', (b'QFI\xfb' + bytes(508)).hex())):
            changed = copy.deepcopy(observed)
            changed[key][field] = value
            with self.subTest(key=key, field=field), self.assertRaises(ValueError):
                self.binding(changed)
        (self.paths.instance / 'protected').write_bytes(b'')
        with self.assertRaises(ValueError):
            self.binding(self.module.capture(self.paths))
        (self.paths.instance / 'protected').unlink()
        self.paths.startup.parent.mkdir(parents=True)
        self.paths.startup.write_bytes(b'')
        with self.assertRaises(ValueError):
            self.binding(self.module.capture(self.paths))

    def test_all_concrete_identities_and_original_bytes_are_recomputed(self):
        observed = self.create()
        binding = self.binding(observed)
        self.assertTrue(self.module.unchanged(self.paths.document(), observed, binding))
        for key in binding['resources']:
            changed = copy.deepcopy(observed)
            changed[key]['inode'] += 1
            self.assertFalse(self.module.unchanged(self.paths.document(), changed, binding))
        for key in ('profile_config', 'instance_config', 'lima_config'):
            changed = copy.deepcopy(observed)
            changed[key]['hex'] += b'# byte drift\n'.hex()
            self.assertFalse(self.module.unchanged(self.paths.document(), changed, binding))

    def test_stopped_missing_lock_is_internal_only_and_other_drift_refused(self):
        observed = self.create()
        binding = self.binding(observed)
        (self.paths.disk / 'in_use_by').unlink()
        stopped = self.module.capture(self.paths)
        before = copy.deepcopy(stopped)
        self.assertTrue(self.module.unchanged(self.paths.document(), stopped, binding, stopped=True))
        self.assertEqual(stopped, before)
        with self.assertRaises(ValueError):
            self.module.unchanged(self.paths.document(), stopped, binding)
        stopped['root_disk']['size'] -= 1
        with self.assertRaises(ValueError):
            self.module.unchanged(self.paths.document(), stopped, binding, stopped=True)

    def test_unchanged_validates_binding_schema_before_comparison(self):
        observed = self.create()
        binding = self.binding(observed)
        for value in (None, {}, {**binding, 'unexpected': False}, {**binding, 'data_disk_size': 0}):
            with self.assertRaises(ValueError):
                self.module.unchanged(self.paths.document(), observed, value)

    def test_all_validators_are_pure_and_do_not_invent_home(self):
        observed = self.create()
        binding = self.binding(observed)
        with patch('os.open', side_effect=AssertionError('filesystem access')), \
                patch('os.stat', side_effect=AssertionError('filesystem access')), \
                patch('os.fstat', side_effect=AssertionError('filesystem access')), \
                patch.object(Path, 'open', side_effect=AssertionError('filesystem access')), \
                patch.object(Path, 'resolve', side_effect=AssertionError('filesystem access')), \
                patch.object(self.module, 'actual_passwd_home', side_effect=AssertionError('passwd access')), \
                patch.object(strict, 'creation_binding', side_effect=AssertionError('invented-home shortcut')):
            self.module.ProfilePaths(self.paths.home, self.runtime)
            self.module.parse_saved_instance(self.instance)
            self.assertEqual(self.binding(observed), binding)
            self.assertTrue(self.module.unchanged(self.paths.document(), observed, binding))
            self.assertFalse(self.module.absent(self.paths.document(), observed))

    def test_exact_document_decoder_rejects_extra_missing_nonstring_and_legacy_fields(self):
        observed = self.create()
        document = self.paths.document()
        for invalid in (None, {}, {'home': document['home'], 'private': document['runtime']},
                        {**document, 'runtime_home': True}, {**document, 'home': self.paths.home},
                        {**document, 'runtime': None}):
            for validator in (self.module.creation_binding, self.module.absent):
                with self.subTest(document=invalid), self.assertRaises(ValueError):
                    validator(invalid, observed)

    def test_document_decoder_refuses_silently_normalized_path_strings(self):
        observed = self.create()
        document = self.paths.document()
        for key in ('home', 'runtime'):
            for value in (document[key] + '/', document[key] + '/.',
                          document[key].replace('/', '//', 1)):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    self.module.creation_binding({**document, key: value}, observed)

    def test_absence_requires_closed_capture_and_exact_reset_store(self):
        observed = self.module.capture(self.paths)
        self.assertTrue(self.module.absent(self.paths.document(), observed))
        self.paths.store.parent.mkdir(parents=True)
        reset = {'disk_formatted': False, 'disk_runtime': '', 'ramalama_provisioned': False}
        for value, expected in ((reset, True), ({**reset, 'disk_formatted': 0}, False),
                                ({**reset, 'extra': False}, False), ({**reset, 'disk_runtime': 'docker'}, False)):
            self.paths.store.write_text(json.dumps(value))
            self.assertEqual(self.module.absent(self.paths.document(), self.module.capture(self.paths)), expected)
        self.paths.store.write_bytes(b'{"disk_formatted":false,"disk_formatted":false,"disk_runtime":"","ramalama_provisioned":false}')
        with self.assertRaises(ValueError):
            self.module.absent(self.paths.document(), self.module.capture(self.paths))
        self.paths.store.unlink()
        self.paths.startup.parent.mkdir(parents=True)
        self.paths.startup.write_bytes(b'')
        self.assertFalse(self.module.absent(self.paths.document(), self.module.capture(self.paths)))

    def test_absence_refuses_surviving_profile_instance_or_disk(self):
        for key in ('profile', 'instance', 'disk'):
            path = getattr(self.paths, key)
            path.mkdir(parents=True)
            self.assertFalse(self.module.absent(self.paths.document(), self.module.capture(self.paths)))
            path.rmdir()

    def test_reused_collector_refuses_symlink_and_inconsistent_capture(self):
        observed = self.create()
        target = self.paths.profile / 'colima.yaml'
        target.unlink()
        target.symlink_to(FIXTURES / 'hf-colima-0.10.3-profile.yaml')
        with self.assertRaises(ValueError):
            self.module.capture(self.paths)
        for changed in ({**observed, 'extra': None}, {**observed, 'profile': None}):
            with self.assertRaises(ValueError):
                self.binding(changed)
