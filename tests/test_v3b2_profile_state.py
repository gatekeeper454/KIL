"""Filesystem safety cases use temporary homes, never the real runtime."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SIZE = 60 * 1024**3

# Independent fixture encodings from go-qcow2reader v0.7.1 format packages.
UNSUPPORTED_DISKS = (
    ('qcow2', 0, b'QFI\xfb'),
    ('vmdk-descriptor', 0, b'# Disk DescriptorFile'),
    ('vmdk4', 0, b'KDMV'), ('vmdk3', 0, b'COWD'),
    ('vhdx', 0, b'vhdxfile'), ('vdi', 64, b'\x7f\x10\xda\xbe'),
    ('parallels', 0, b'WithoutFreeSpace'), ('parallels-extended', 0, b'WithouFreSpacExt'),
    ('vpc', 0, b'conectix'), ('asif', 0, b'shdw'),
)


def replace_container_header(path, offset, magic):
    before = path.stat()
    with path.open('r+b') as stream:
        stream.write(b'\0' * 512)
        stream.seek(offset)
        stream.write(magic)
    after = path.stat()
    assert (before.st_dev, before.st_ino, before.st_size) == (after.st_dev, after.st_ino, after.st_size)

SAVED = b'''cpu: 4
disk: 60
memory: 8
arch: aarch64
runtime: docker
modelRunner: docker
hostname: ""
kubernetes:
  enabled: false
  version: v1.35.0+k3s1
  k3sArgs:
    - --disable=traefik
  port: 0
autoActivate: false
network:
  address: false
  mode: shared
  interface: en0
  preferredRoute: false
  dns: null
  dnsHosts: {}
  hostAddresses: false
  gatewayAddress: 192.168.5.2
forwardAgent: false
docker: {}
vmType: vz
portForwarder: ssh
rosetta: false
binfmt: false
nestedVirtualization: false
mountType: virtiofs
mountInotify: false
cpuType: ""
provision: null
sshConfig: false
sshPort: 0
mounts: null
diskImage: ""
forceDiskImage: false
rootDisk: 20
env: {}
'''


def create_profile(paths):
    for path in (paths.profile, paths.instance, paths.disk):
        path.mkdir(parents=True)
    (paths.profile / 'colima.yaml').write_bytes(SAVED)
    (paths.instance / 'colima.yaml').write_bytes(SAVED)
    (paths.instance / 'lima.yaml').write_bytes(b'vmType: vz\n')
    with (paths.instance / 'disk').open('wb') as stream:
        stream.truncate(20 * 1024**3)
    with (paths.disk / 'datadisk').open('wb') as stream:
        stream.truncate(60 * 1024**3)
    (paths.disk / 'in_use_by').symlink_to(paths.instance)


class ProfileStateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / 'home'
        self.home.mkdir()
        self.private = self.root / 'private'
        self.private.mkdir(mode=0o700)

    def tearDown(self):
        self.temp.cleanup()

    def module(self):
        from kil import v3b2_profile_state
        return v3b2_profile_state

    def paths(self):
        module = self.module()
        with patch.object(module.pwd, 'getpwuid', return_value=type('Passwd', (), {'pw_dir': str(self.home)})()):
            return module.ProfilePaths.bind(self.private)

    def test_module_available(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('kil.v3b2_profile_state'))

    def test_passwd_home_and_private_tmp_override_ambient_authority(self):
        with patch.dict(os.environ, {'HOME': '/redirect', 'COLIMA_HOME': '/redirect', 'LIMA_HOME': '/redirect', 'TMPDIR': '/redirect'}):
            paths = self.paths()
        self.assertEqual(paths.profile, self.home / '.colima/kil-v3-lab')
        self.assertEqual(paths.disk, self.home / '.colima/_lima/_disks/colima-kil-v3-lab')
        self.assertEqual(paths.startup, self.private / 'runtime-tmp/colima-kil-v3-lab.yaml')

    def test_every_preexisting_remnant_refuses_preflight(self):
        for field in ('profile', 'instance', 'disk', 'store', 'startup'):
            with self.subTest(field=field):
                paths = self.paths()
                target = getattr(paths, field)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b'orphan')
                with self.assertRaisesRegex(ValueError, 'remnant'):
                    self.module().require_pristine(paths)
                target.unlink()

    def test_symlink_parent_is_not_treated_as_absence(self):
        paths = self.paths()
        (self.home / '.colima').symlink_to(self.root / 'missing', target_is_directory=True)
        with self.assertRaises(ValueError):
            self.module().require_pristine(paths)

    def test_closed_saved_configuration_and_both_hashes(self):
        paths = self.paths()
        create_profile(paths)
        state = self.module().capture(paths)
        binding = self.module().creation_binding(paths.document(), state)
        self.assertEqual(binding['data_disk_size'], 60 * 1024**3)
        self.assertEqual(binding['lock_target'], str(paths.instance))
        self.assertEqual(set(binding['config_sha256']), {'profile', 'instance'})
        self.assertEqual(self.module().parse_saved(SAVED)['mounts'], None)

    def test_all_pinned_nonraw_signatures_refuse_creation_on_both_disks(self):
        paths = self.paths()
        create_profile(paths)
        module = self.module()
        for path in (paths.disk / 'datadisk', paths.instance / 'disk'):
            for name, offset, magic in UNSUPPORTED_DISKS:
                with self.subTest(disk=path.name, format=name):
                    replace_container_header(path, offset, magic)
                    with self.assertRaisesRegex(ValueError, 'non-raw'):
                        module.creation_binding(paths.document(), module.capture(paths))
            replace_container_header(path, 0, b'\0' * 512)

    def test_short_or_unreadable_disk_probe_cannot_default_to_raw(self):
        paths = self.paths()
        create_profile(paths)
        module = self.module()
        original = module.os.read
        for failure in ('short', 'unreadable'):
            with self.subTest(failure=failure):
                def read(fd, maximum):
                    if os.fstat(fd).st_size == SIZE:
                        if failure == 'unreadable':
                            raise OSError('injected read failure')
                        return b'\0' * 3
                    return original(fd, maximum)
                with patch.object(module.os, 'read', side_effect=read):
                    with self.assertRaises(ValueError):
                        module.capture(paths)

    def test_replayed_capture_cannot_claim_raw_with_unsupported_probe(self):
        paths = self.paths()
        create_profile(paths)
        module = self.module()
        observed = module.capture(paths)
        observed['data_disk']['format_probe_hex'] = (b'vhdxfile' + b'\0' * 504).hex()
        with self.assertRaisesRegex(ValueError, 'non-raw'):
            module.creation_binding(paths.document(), observed)

    def test_saved_config_rejects_unsafe_or_ambiguous_values(self):
        module = self.module()
        for payload in (SAVED.replace(b'mounts: null', b'mounts: []'),
                        SAVED.replace(b'cpu: 4', b'cpu: 04'),
                        SAVED + b'cpu: 4\n', SAVED + b'template: false\n',
                        SAVED.replace(b'docker: {}', b'docker: &alias {}'),
                        SAVED.replace(b'provision: null', b'provision: !!seq []'),
                        SAVED.replace(b'sshConfig: false', b'sshConfig: no'),
                        SAVED.replace(b'env: {}', b'env:\n  PATH: /evil')):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    module.parse_saved(payload)

    def test_instance_configuration_must_match_profile(self):
        paths = self.paths()
        create_profile(paths)
        (paths.instance / 'colima.yaml').write_bytes(SAVED.replace(b'memory: 8', b'memory: 9'))
        with self.assertRaises(ValueError):
            self.module().creation_binding(paths.document(), self.module().capture(paths))

    def test_zero_store_cannot_hide_surviving_disk(self):
        paths = self.paths()
        paths.disk.mkdir(parents=True)
        paths.store.parent.mkdir(parents=True)
        paths.store.write_text(json.dumps({'disk_formatted': False, 'disk_runtime': '', 'ramalama_provisioned': False}))
        self.assertFalse(self.module().absent(paths.document(), self.module().capture(paths)))
        paths.disk.rmdir()
        self.assertTrue(self.module().absent(paths.document(), self.module().capture(paths)))

    def test_capture_requires_parent_presence_and_exact_child_membership(self):
        import copy
        paths = self.paths()
        create_profile(paths)
        module = self.module()
        original = module.capture(paths)
        for parent, child, entry in (
                ('profile', 'profile_config', 'colima.yaml'),
                ('instance', 'instance_config', 'colima.yaml'),
                ('instance', 'lima_config', 'lima.yaml'),
                ('instance', 'root_disk', 'disk'),
                ('disk', 'data_disk', 'datadisk'), ('disk', 'lock', 'in_use_by'),
                ('lima', 'instance', 'colima-kil-v3-lab')):
            for mutation in ('parent_absent', 'membership_missing', 'child_absent'):
                with self.subTest(parent=parent, child=child, mutation=mutation):
                    observed = copy.deepcopy(original)
                    if mutation == 'parent_absent':
                        observed[parent] = None
                    elif mutation == 'membership_missing':
                        observed[parent]['entries'].remove(entry)
                    else:
                        observed[child] = None
                    with self.assertRaises(ValueError):
                        module.validate_capture(observed)

    def test_contradictory_children_cannot_prove_absence_or_authorize_orphan(self):
        paths = self.paths()
        create_profile(paths)
        module = self.module()
        observed = module.capture(paths)
        binding = module.creation_binding(paths.document(), observed)
        observed.update(profile=None, instance=None, disk=None)
        with self.assertRaises(ValueError):
            module.absent(paths.document(), observed)
        observed['disk'] = {'device': binding['resources']['disk']['device'], 'inode': binding['resources']['disk']['inode'],
                            'mode': binding['resources']['disk']['mode'], 'entries': ['datadisk']}
        observed['lock'] = None
        observed['lima']['entries'] = ['_disks']
        self.assertFalse(module.orphan_authorized(paths.document(), observed, binding))

    def test_interrupted_startup_artifact_prevents_absence(self):
        paths = self.paths()
        paths.startup.parent.mkdir()
        paths.startup.write_bytes(b'incomplete')
        self.assertFalse(self.module().absent(paths.document(), self.module().capture(paths)))

    def test_orphan_requires_original_disk_and_no_foreign_lock(self):
        paths = self.paths()
        create_profile(paths)
        module = self.module()
        binding = module.creation_binding(paths.document(), module.capture(paths))
        for file in paths.profile.iterdir():
            file.unlink()
        paths.profile.rmdir()
        for file in paths.instance.iterdir():
            file.unlink()
        paths.instance.rmdir()
        lock = paths.disk / 'in_use_by'
        lock.unlink()
        self.assertTrue(module.orphan_authorized(paths.document(), module.capture(paths), binding))
        lock.symlink_to(self.home / '.colima/_lima/foreign')
        self.assertFalse(module.orphan_authorized(paths.document(), module.capture(paths), binding))
        lock.unlink()
        disk = paths.disk / 'datadisk'
        disk.rename(paths.disk / 'old')
        with disk.open('wb') as stream:
            stream.truncate(60 * 1024**3)
        self.assertFalse(module.orphan_authorized(paths.document(), module.capture(paths), binding))

    def test_runner_ignores_ambient_home_and_runtime_homes(self):
        from kil.v3b2_controller import SubprocessCommandRunner
        from kil.v3b2_journal import Command
        import subprocess
        module = self.module()
        paths = self.paths()
        with patch.object(module, 'passwd_home', return_value=self.home), patch.dict(os.environ, {
                'HOME': '/redirect', 'TMPDIR': '/redirect', 'COLIMA_HOME': '/redirect',
                'LIMA_HOME': '/redirect', 'XDG_CONFIG_HOME': '/redirect', 'COLIMA_SAVE_CONFIG': 'false'}):
            runner = SubprocessCommandRunner()
        with patch('kil.v3b2_controller.subprocess.run', return_value=subprocess.CompletedProcess([], 0, b'', b'')) as called:
            runner.run(Command(('colima', 'version'), 30))
        environment = called.call_args.kwargs['env']
        self.assertEqual(environment['HOME'], str(paths.home))
        self.assertTrue(set(environment).isdisjoint({'TMPDIR', 'COLIMA_HOME', 'LIMA_HOME', 'XDG_CONFIG_HOME', 'COLIMA_SAVE_CONFIG'}))

    def test_registry_refuses_inventory_only_profile_start(self):
        from kil.v3b2_proofs import ExpectedContext, RawObservation, canonical, decide
        config = {'name': 'kil-v3-lab', 'arch': 'aarch64', 'cpus': 4,
                  'memory': 8 * 1024**3, 'disk': SIZE, 'runtime': 'docker'}
        context = ExpectedContext('a' * 64, 1, 'profile_start', b'{}\n', canonical({'profile_configuration': config}))
        row = RawObservation('profile_inventory', ('colima', 'list', '--json'), (), 0, canonical([{**config, 'status': 'Running'}]), b'')
        self.assertEqual(decide(context, (row,)).outcome, 'unknown')

    def test_protected_or_replaced_lima_configuration_blocks_cleanup(self):
        paths = self.paths()
        create_profile(paths)
        module = self.module()
        binding = module.creation_binding(paths.document(), module.capture(paths))
        (paths.instance / 'protected').touch()
        with self.assertRaises(ValueError):
            module.unchanged(paths.document(), module.capture(paths), binding, stopped=True)
        (paths.instance / 'protected').unlink()
        (paths.instance / 'lima.yaml').write_bytes(b'malformed: [\n')
        self.assertFalse(module.unchanged(paths.document(), module.capture(paths), binding, stopped=True))

    def test_path_replacement_during_read_is_rejected(self):
        paths = self.paths()
        create_profile(paths)
        module = self.module()
        original_read = os.read
        moved = False
        def replace_directory(fd, maximum):
            nonlocal moved
            payload = original_read(fd, maximum)
            if payload == SAVED and not moved:
                moved = True
                paths.profile.rename(paths.profile.with_name('replaced'))
                paths.profile.mkdir()
                (paths.profile / 'colima.yaml').write_bytes(SAVED)
            return payload
        with patch.object(module.os, 'read', side_effect=replace_directory):
            with self.assertRaises(ValueError):
                module.capture(paths)

    def test_missing_descendant_rechecks_its_existing_parent(self):
        paths = self.paths()
        module = self.module()
        original_open = os.open
        changed = False
        def move_private(name, flags, *args, **kwargs):
            nonlocal changed
            if name == 'runtime-tmp' and not changed:
                changed = True
                self.private.rename(self.private.with_name('old-private'))
                self.private.mkdir()
                raise FileNotFoundError('interrupted observation')
            return original_open(name, flags, *args, **kwargs)
        with patch.object(module.os, 'open', side_effect=move_private):
            with self.assertRaises(ValueError):
                module.require_pristine(paths)

    def test_private_docker_cleanup_accepts_only_owned_validated_context(self):
        from hashlib import sha256
        paths = self.paths()
        config = self.private / 'docker-config'
        name = 'colima-kil-v3-lab'
        metadata = config / 'contexts/meta' / sha256(name.encode()).hexdigest()
        metadata.mkdir(parents=True)
        (metadata / 'meta.json').write_text(json.dumps({'Name': name, 'Metadata': {'Description': 'colima [profile=kil-v3-lab]'},
            'Endpoints': {'docker': {'Host': 'unix://' + str(paths.profile / 'docker.sock'), 'SkipTLSVerify': False}}}))
        (config / 'config.json').write_text('{}')
        self.module().clear_private_docker(paths)
        self.assertFalse(config.exists())
        config.mkdir()
        (config / 'unexpected').write_bytes(b'foreign')
        with self.assertRaises(ValueError):
            self.module().clear_private_docker(paths)
        self.assertEqual((config / 'unexpected').read_bytes(), b'foreign')


class ProfileIntegrationTest(unittest.TestCase):
    def setUp(self):
        from tests.test_v3b2_controller import V3B2ControllerTest
        V3B2ControllerTest.setUp(self)

    def tearDown(self):
        self.temporary.cleanup()

    def started(self):
        from kil.v3b2_journal import colima_start_command
        self.controller.preflight()
        self.controller._journal_pair('profile_start', {'colima_profile': 'kil-v3-lab'},
                                      lambda: self.runner.run(colima_start_command()))

    def stopped(self):
        from kil.v3b2_journal import append_event
        self.started()
        append_event(self.controller.journal_path, 'profile_stop_intent', {'colima_profile': 'kil-v3-lab'})
        self.assertEqual(self.controller.recover()['proof_outcome'], 'complete')

    def test_colima_success_with_remaining_disk_requires_proven_fallback(self):
        from kil.v3b2_journal import append_event
        from kil.v3b2_controller import CommandResult
        self.stopped()
        original = self.runner.run
        paths = self.controller.profile_paths
        def leave_disk(command):
            if command.argv[:2] == ('colima', 'delete'):
                import shutil
                shutil.rmtree(paths.profile)
                shutil.rmtree(paths.instance)
                (paths.disk / 'in_use_by').unlink()
                self.runner.profile_exists = False
                return CommandResult(0, '', '')
            return original(command)
        append_event(self.controller.journal_path, 'profile_delete_intent', {'colima_profile': 'kil-v3-lab'})
        with patch.object(self.runner, 'run', side_effect=leave_disk):
            result = self.controller.recover()
        self.assertEqual(result['proof_outcome'], 'unknown')
        self.assertTrue(paths.disk.exists())
        ran = []
        def fallback(command):
            if command.argv[:3] == ('limactl', 'disk', 'delete'):
                ran.append(command)
                (paths.disk / 'datadisk').unlink()
                paths.disk.rmdir()
                return CommandResult(0, '', '')
            return original(command)
        with patch.object(self.runner, 'run', side_effect=fallback):
            result = self.controller.recover()
        self.assertEqual(result['proof_outcome'], 'complete')
        self.assertEqual(ran[0].argv, ('limactl', 'disk', 'delete', 'colima-kil-v3-lab'))
        self.assertEqual(ran[0].env, (('LIMA_HOME', str(paths.lima)),))

    def test_profile_bindings_replay_and_configuration_drift_blocks_stop(self):
        from kil.v3b2_journal import append_event, load_expected_context
        from kil.v3b2_proofs import decode
        self.started()
        context = load_expected_context(self.controller.journal_path, state_only=True)
        self.assertIn('profile_binding', decode(context.inputs))
        (self.controller.profile_paths.instance / 'colima.yaml').write_bytes(SAVED.replace(b'mounts: null', b'mounts: []'))
        append_event(self.controller.journal_path, 'profile_stop_intent', {'colima_profile': 'kil-v3-lab'})
        count = len(self.runner.commands)
        self.assertEqual(self.controller.recover()['proof_outcome'], 'unknown')
        self.assertFalse(any(row.mutating for row in self.runner.commands[count:]))

    def test_normal_delete_allows_unrelated_profile(self):
        from tests.test_v3b2_controller import foreign
        from kil.v3b2_journal import append_event
        self.runner.profiles = [foreign('unrelated', 'Running')]
        other = self.controller.profile_paths.lima / 'colima-unrelated'
        other.mkdir(parents=True)
        (other / 'protected').touch()
        self.stopped()
        append_event(self.controller.journal_path, 'profile_delete_intent', {'colima_profile': 'kil-v3-lab'})
        self.assertEqual(self.controller.recover()['proof_outcome'], 'complete')
        self.assertTrue((other / 'protected').exists())

    def test_orphan_with_other_instance_or_skipped_delete_stays_manual(self):
        from kil.v3b2_journal import append_event
        from kil.v3b2_controller import CommandResult
        import shutil
        self.stopped()
        paths = self.controller.profile_paths
        shutil.rmtree(paths.profile)
        shutil.rmtree(paths.instance)
        (paths.disk / 'in_use_by').unlink()
        self.runner.profile_exists = False
        other = paths.lima / 'colima-other'
        other.mkdir()
        (other / 'lima.yaml').write_bytes(b'broken: [\n')
        append_event(self.controller.journal_path, 'profile_delete_intent', {'colima_profile': 'kil-v3-lab'})
        count = len(self.runner.commands)
        result = self.controller.recover()
        self.assertEqual(result['proof_outcome'], 'unknown')
        self.assertEqual(result['proof_category'], 'invalid_or_missing_observation')
        self.assertFalse(any(command.mutating for command in self.runner.commands[count:]))
        (other / 'lima.yaml').unlink()
        other.rmdir()
        original = self.runner.run
        def skipped(command):
            if command.argv[:3] == ('limactl', 'disk', 'delete'):
                return CommandResult(0, '', '')
            return original(command)
        with patch.object(self.runner, 'run', side_effect=skipped):
            self.assertEqual(self.controller.recover()['proof_outcome'], 'unknown')
        self.assertTrue(paths.disk.exists())

    def test_fallback_command_cannot_bypass_registry_provenance(self):
        from kil.v3b2_journal import Command
        from kil.v3b2_controller import ControllerError
        self.started()
        command = Command(('limactl', 'disk', 'delete', 'colima-kil-v3-lab'), 300,
                          env=(('LIMA_HOME', str(self.controller.profile_paths.lima)),), mutating=True)
        with self.assertRaises(ControllerError):
            self.controller._observe(command, 'unsafe_fallback')

    def test_post_preflight_remnants_block_start_before_intent_even_after_restart(self):
        from kil.v3b2_controller import ControllerError, V3B2Controller
        from kil.v3b2_journal import load_expected_context, load_journal
        from kil.v3b2_proofs import decode
        self.controller.preflight()
        create_profile(self.controller.profile_paths)
        self.runner.profile_exists = True
        for controller in (self.controller, V3B2Controller(self.paths, self.runner)):
            with self.subTest(restarted=controller is not self.controller):
                count = len(self.runner.commands)
                with self.assertRaises(ControllerError):
                    controller._journal_pair('profile_start', {'colima_profile': 'kil-v3-lab'}, controller._start_profile)
                self.assertFalse(any(command.mutating for command in self.runner.commands[count:]))
                self.assertEqual(load_journal(controller.journal_path)['events'], [])
                self.assertNotIn('profile_binding', decode(load_expected_context(controller.journal_path, state_only=True).inputs))

    def test_post_intent_start_refusal_is_durable_and_never_adopts_existing_state(self):
        from dataclasses import replace
        from kil.v3b2_controller import ControllerError, V3B2Controller
        from kil.v3b2_journal import load_expected_context, load_journal, append_observed_terminal, JournalError
        from kil.v3b2_proofs import canonical, decode, decide
        from kil import v3b2_journal as journal_module
        self.controller.preflight()
        def raced_start():
            create_profile(self.controller.profile_paths)
            self.runner.profile_exists = True
            return self.controller._start_profile()
        count = len(self.runner.commands)
        with self.assertRaises(ControllerError):
            self.controller._journal_pair('profile_start', {'colima_profile': 'kil-v3-lab'}, raced_start)
        self.assertFalse(any(command.mutating for command in self.runner.commands[count:]))
        journal = load_journal(self.controller.journal_path)
        self.assertEqual(journal['profile_start_refused_sequence'], 1)
        self.assertEqual(len(journal['events']), 1)
        self.assertIsNotNone(journal['teardown_from_sequence'])
        resumed = V3B2Controller(self.paths, self.runner)
        recovered = resumed.recover()
        self.assertEqual(recovered['proof_outcome'], 'unknown')
        self.assertEqual(recovered['proof_category'], 'profile_start_dispatch_refused')
        context = load_expected_context(resumed.journal_path)
        inputs = decode(context.inputs)
        self.assertNotIn('profile_binding', inputs)
        self.assertFalse(any(command.mutating for command in self.runner.commands[count:]))
        inputs['profile_start_refused_sequence'] = None
        forged_context = replace(context, inputs=canonical(inputs))
        observations = resumed._collect_observations(context)
        self.assertEqual(decide(forged_context, observations).outcome, 'teardown_only')
        with self.assertRaises(JournalError):
            append_observed_terminal(resumed.journal_path, forged_context, observations)
        for invalid in (True, 0, 2, '1'):
            with self.subTest(invalid=invalid), self.assertRaises(JournalError):
                journal_module._validate_journal({**journal, 'profile_start_refused_sequence': invalid})
        with self.assertRaises(JournalError):
            journal_module._replace_journal(resumed.journal_path, {**journal, 'profile_start_refused_sequence': None})
        with self.assertRaises(JournalError):
            journal_module._validate_journal({**journal, 'teardown_from_sequence': None})

    def test_contradictory_retained_delete_capture_is_rejected_on_write_and_replay(self):
        from dataclasses import replace
        from hashlib import sha256
        from kil.v3b2_journal import append_event, append_observed_terminal, load_expected_context, load_journal
        from kil.v3b2_proofs import canonical, decode, expected_context, observation_bundle, ProofDecision, ProofError, terminal_event
        self.stopped()
        controller = self.controller
        append_event(controller.journal_path, 'profile_delete_intent', {'colima_profile': 'kil-v3-lab'})
        context = load_expected_context(controller.journal_path)
        observations = []
        for observation in controller._collect_observations(context):
            if observation.label == 'profile_inventory':
                observation = replace(observation, stdout=b'[]\n')
            elif observation.label == 'profile_state':
                state = decode(observation.stdout)
                state.update(profile=None, instance=None, disk=None)
                observation = replace(observation, stdout=canonical(state))
            elif observation.label == 'active_paths':
                observation = replace(observation, stdout=canonical({key: None for key in decode(observation.stdout)}))
            observations.append(observation)
        observations = tuple(observations)
        decision = append_observed_terminal(controller.journal_path, context, observations)
        self.assertEqual(decision.outcome, 'unknown')
        forged_decision = ProofDecision('complete', 'profile_and_active_paths_absent')
        proof = observation_bundle(context, observations, forged_decision)
        digest = sha256(proof).hexdigest()
        journal = load_journal(controller.journal_path)
        journal['events'].append(terminal_event(context, forged_decision, digest))
        journal['events'].append({'sequence': len(journal['events']) + 1, 'event': 'profile_absence_proof_intent',
                                  'details': {'colima_profile': 'kil-v3-lab'}})
        def read_proof(sequence, commitment):
            return proof if sequence == context.intent_sequence else (controller.paths.private / f'proof-{sequence}-{commitment}.json').read_bytes()
        with self.assertRaises(ProofError):
            expected_context(controller.expected_inputs_path.read_bytes(), journal, read_proof)

    def test_same_inode_nonraw_metadata_blocks_normal_delete_and_orphan_fallback(self):
        from kil.v3b2_journal import append_event
        import shutil
        self.stopped()
        paths = self.controller.profile_paths
        append_event(self.controller.journal_path, 'profile_delete_intent', {'colima_profile': 'kil-v3-lab'})
        for phase in ('normal', 'orphan'):
            if phase == 'orphan':
                shutil.rmtree(paths.profile)
                shutil.rmtree(paths.instance)
                (paths.disk / 'in_use_by').unlink()
                self.runner.profile_exists = False
            for name, offset, magic in UNSUPPORTED_DISKS:
                with self.subTest(phase=phase, format=name):
                    replace_container_header(paths.disk / 'datadisk', offset, magic)
                    count = len(self.runner.commands)
                    self.assertEqual(self.controller.recover()['proof_outcome'], 'unknown')
                    self.assertFalse(any(command.mutating for command in self.runner.commands[count:]))
                    self.assertTrue(paths.disk.exists())
