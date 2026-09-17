"""Test-owned native lifecycle doubles; never native evidence or tool execution."""
import importlib.util
import importlib
import io
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import os
import shutil
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from kil.hf_exploratory_io import PrivateStore
from kil.v3b2_controller import CommandResult
from kil.v3b2_journal import Command, kind_create_command, kind_delete_command, kubectl_apply_command
from kil.v3b2_contracts import TRACKS
from kil.v3b2_proofs import canonical

COMMIT = 'a' * 40
COLIMA_VERSION_OUTPUT = b'colima version v0.10.3\ngit commit: 00f6c297e92a82c04a4ab507db0a61435650d7e8\n'


class RuntimeCompositionTests(unittest.TestCase):
    def setUp(self):
        from kil import hf_exploratory_runtime as runtime_module
        compact = tempfile.TemporaryDirectory(prefix='k', dir='/private/tmp')
        self.addCleanup(compact.cleanup)
        self.registry = Path(compact.name).resolve() / 'k'
        selector = patch.object(runtime_module, '_registry_parent', return_value=self.registry, create=True)
        selector.start()
        self.addCleanup(selector.stop)

    def test_constructor_derives_runtime_separate_from_receipt_and_default_home(self):
        from kil import hf_exploratory_native as native
        from tests.test_v3b2_driver_pod_configuration import PROFILE, WORKLOAD
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            home = root / 'home'; home.mkdir()
            parent = root / '.tools/hf-exploratory-private'; parent.mkdir(parents=True, mode=0o700)
            store = PrivateStore(parent / ('hf-exploratory-' + '1' * 64))
            try:
                inputs = SimpleNamespace(profile=PROFILE, workload=WORKLOAD)
                with patch('kil.hf_exploratory_profile.actual_passwd_home', return_value=home):
                    life = native.ExploratoryLifecycle(root, inputs, store, Mock(), COMMIT, 'rehearsal')
                try:
                    self.assertNotEqual(life.paths.colima, home / '.colima', 'native controls still use default home')
                    self.assertEqual(life.runtime.path, self.registry / ('r' + '1' * 16))
                    self.assertEqual(life.identity.kubeconfig, str(life.runtime.kubeconfig))
                    self.assertFalse((store.path / 'runtime-tmp').exists())
                finally:
                    life.close()
            finally:
                store.close()


def node():
    return [{'Id': 'b' * 64, 'Name': '/kil-v3-lab-control-plane',
             'Config': {'Labels': {'io.x-k8s.kind.cluster': 'kil-v3-lab',
                                   'io.x-k8s.kind.role': 'control-plane'}}, 'State': {'Running': True}}]


def create_native_profile(paths):
    from tests.test_v3b2_profile_state import create_profile
    create_profile(paths)
    fixtures = Path(__file__).parent / 'fixtures'
    for key, name in [('profile', 'profile'), ('instance', 'instance')]:
        (getattr(paths, key) / 'colima.yaml').write_bytes(
            (fixtures / ('hf-colima-0.10.3-' + name + '.yaml')).read_bytes())


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('kil.hf_exploratory_native'),
                             'native exploratory module is missing')
        self.native = importlib.import_module('kil.hf_exploratory_native')
        from kil import hf_exploratory_runtime as runtime_module
        compact = tempfile.TemporaryDirectory(prefix='k', dir='/private/tmp')
        self.addCleanup(compact.cleanup)
        self.registry = Path(compact.name).resolve() / 'k'
        selector = patch.object(runtime_module, '_registry_parent', return_value=self.registry, create=True)
        selector.start()
        self.addCleanup(selector.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / 'home'
        self.home.mkdir()
        private = self.root / '.tools/hf-exploratory-private'
        private.mkdir(parents=True, mode=0o700)
        self.store = PrivateStore(private / ('hf-exploratory-' + '1' * 64))
        self.addCleanup(self.store.close)
        from tests.test_v3b2_driver_pod_configuration import PROFILE, WORKLOAD
        self.inputs = SimpleNamespace(profile=PROFILE, workload=WORKLOAD,
            profile_bytes=b'profile', manifest_bytes=b'manifest', archive=b'archive',
            tools=self.root / '.tools/bin', tool_records={})
        self.runner = Mock()
        self.runner.global_docker_config = str(self.home / '.docker')
        self.runner.run.return_value = CommandResult(0, 'out', '', b'out', b'')
        with patch('kil.hf_exploratory_profile.actual_passwd_home', return_value=self.home):
            self.life = self.native.ExploratoryLifecycle(self.root, self.inputs, self.store,
                                                       self.runner, COMMIT, 'rehearsal')
        self.addCleanup(self.life.close)

    def test_read_dispatch_rechecks_runtime_namespace_before_intent(self):
        journal = self.store.journal.read_bytes()
        self.life.runtime.tmp.rename(self.life.runtime.tmp.with_name('old-tmp'))
        self.life.runtime.tmp.mkdir(mode=0o700)
        with self.assertRaises(ValueError): self.life.observe(Command(('colima', 'version'), 10))
        self.runner.run.assert_not_called()
        self.assertEqual(self.store.journal.read_bytes(), journal)

    def test_scoped_colima_uses_adapter_and_foreign_environment_is_not_stripped(self):
        from kil.hf_exploratory_runtime import ExploratoryColimaCommand
        self.life.observe(Command(('colima', 'version'), 10))
        command = self.runner.run.call_args.args[0]
        self.assertIs(type(command), ExploratoryColimaCommand)
        self.assertEqual(command.env, self.life.colima_env)
        self.runner.run.reset_mock()
        with self.assertRaises(ValueError):
            self.life.observe(Command(('colima', 'version'), 10,
                                      env=(('DOCKER_CONFIG', '/tmp/foreign'), ('TMPDIR', '/tmp/foreign'))))
        self.runner.run.assert_not_called()

    def test_bind_node_exact_and_rejects_replacements(self):
        self.assertEqual(self.native.bind_node(node()), 'b' * 64)
        bad = [[], node() * 2]
        for path, value in [('Id', 'B' * 64), ('Name', '/other')]:
            changed = node(); changed[0][path] = value; bad.append(changed)
        for value in [False, 1, 'true']:
            changed = node(); changed[0]['State']['Running'] = value; bad.append(changed)
        for key in ['io.x-k8s.kind.cluster', 'io.x-k8s.kind.role']:
            changed = node(); changed[0]['Config']['Labels'][key] = 'other'; bad.append(changed)
        for candidate in bad:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                self.native.bind_node(candidate)

    def test_same_incarnation_ignores_only_resource_version(self):
        identity = dict(namespace='ns', pod='pod', role='envoy', uid='uid', container_id='cid',
                        requested_image='desired', runtime_image='actual', image_ref='ref', resource_version='1')
        self.native.same_incarnation(identity, {**identity, 'resource_version': '2'})
        for key in identity.keys() - {'resource_version'}:
            with self.assertRaises(ValueError):
                self.native.same_incarnation(identity, {**identity, key: 'other'})
        with self.assertRaises(ValueError): self.native.same_incarnation({}, {})

    def test_command_receipt_intent_precedes_dispatch_and_retains_failure(self):
        self.runner.run.side_effect = lambda command: (
            self.assertEqual(json.loads(self.store.journal.read_bytes().splitlines()[-1])['event'], 'command_intent')
            or CommandResult(7, 'prefix', 'error', b'prefix', b'error'))
        with self.assertRaises(ValueError):
            self.life.observe(Command(('colima', 'version'), 10))
        self.assertEqual((self.store.path / 'command-0001.stdout').read_bytes(), b'prefix')
        self.assertEqual((self.store.path / 'command-0001.stderr').read_bytes(), b'error')
        rows = [json.loads(line) for line in self.store.journal.read_bytes().splitlines()]
        self.assertEqual(rows[-1]['details']['returncode'], 7)

    def test_failed_intent_and_invalid_grammar_never_dispatch(self):
        with patch.object(self.store, 'record', side_effect=OSError('intent fsync failed')):
            with self.assertRaises(OSError):
                self.life.observe(Command(('colima', 'version'), 10))
        self.runner.run.assert_not_called()
        invalid = Command(('colima', 'version'), 10)
        object.__setattr__(invalid, 'argv', ('kubectl', 'delete', 'all'))
        with self.assertRaises(ValueError):
            self.life.observe(invalid)
        self.runner.run.assert_not_called()

    def test_kind_delete_guard_failure_does_not_latch_or_dispatch(self):
        self.life.cluster_attempted = True
        with patch.object(self.life, 'guard_cluster', side_effect=ValueError('changed')):
            with self.assertRaises(ValueError):
                self.life.observe(kind_delete_command(self.life.identity))
        self.assertFalse(self.life.cluster_delete_attempted)
        self.runner.run.assert_not_called()

    def test_kind_create_attempt_not_replayed_after_dispatch_failure(self):
        self.life.profile_binding = {'bound': True}
        self.life.repository = Path(__file__).resolve().parents[1]
        self.life.prepare()
        self.runner.run.side_effect = OSError('uncertain')
        with patch.object(self.life, 'guard_profile'), patch.object(self.life, 'endpoint_rows', return_value=[]), patch.object(self.life, 'require_foreign_preserved'):
            for _ in range(2):
                with self.assertRaises((OSError, ValueError)):
                    self.life.observe(kind_create_command(self.life.identity))
        self.assertEqual(self.runner.run.call_count, 1)
        self.assertTrue(self.life.cluster_attempted)

    def test_other_mutation_commitment_replay_is_refused(self):
        from kil.v3b2_manifests import render_objects
        namespaces=[row for row in json.loads(render_objects(self.inputs.profile,self.inputs.workload))['items'] if row['kind']=='Namespace']
        command = kubectl_apply_command(self.life.identity, canonical({'apiVersion':'v1','kind':'List','items':namespaces}))
        with patch.object(self.life, 'guard_cluster'), patch.object(self.life, 'require_foreign_preserved'):
            self.life.observe(command)
            with self.assertRaises(ValueError):
                self.life.observe(command)
        self.assertEqual(self.runner.run.call_count, 1)

    def test_constructor_modes_and_run_digest_are_bound(self):
        self.assertEqual(self.life.run_digest, self.inputs.workload.run_id.removeprefix('v3b2-'))
        with self.assertRaises(ValueError):
            self.native.ExploratoryLifecycle(self.root, self.inputs, self.store, self.runner, COMMIT, 'resume')

    def test_docker_roster_rejects_cr_or_partial_records(self):
        for payload in [b'{"ID":"'+b'b'*64+b'","Names":"node"}\r\n', b'{}', b'\n']:
            self.runner.run.return_value = CommandResult(0, payload.decode(), '', payload, b'')
            with self.assertRaises(ValueError): self.life.endpoint_rows()

    def test_false_profile_unchanged_is_not_ignored(self):
        self.life.profile_binding = {'bound':True}
        with patch.object(self.native, 'capture', return_value={}), patch.object(self.native, 'unchanged', return_value=False):
            with self.assertRaises(ValueError): self.life.guard_profile()

    def test_valid_profile_directory_replacement_false_cannot_authorize_mutation(self):
        create_native_profile(self.life.paths)
        self.life.profile_binding=self.native.creation_binding(self.life.paths.document(),self.native.capture(self.life.paths))
        original=self.life.paths.profile.with_name('retained-original-profile')
        self.life.paths.profile.rename(original); self.life.paths.profile.mkdir()
        (self.life.paths.profile/'colima.yaml').write_bytes((original/'colima.yaml').read_bytes())
        self.assertFalse(self.native.unchanged(self.life.paths.document(),self.native.capture(self.life.paths),self.life.profile_binding))
        with self.assertRaises(ValueError): self.life.guard_profile()
        with self.assertRaises(ValueError): self.life.observe(kind_create_command(self.life.identity))
        self.runner.run.assert_not_called(); self.assertFalse(self.life.cluster_attempted)

    def test_readiness_read_timeout_cannot_overrun_remaining_deadline(self):
        with patch.object(self.native.time,'monotonic',side_effect=[100,100,108.2,108.5]):
            self.life.read_until(lambda deadline:self.life.observe(Command(('colima','version'),10)),seconds=10)
        self.assertEqual(self.runner.run.call_args.args[0].timeout_s,1)

    def install_pods(self):
        from kil.v3b2_manifests import render_objects
        self.pods = {}
        for track_index, track in enumerate(TRACKS):
            for role_index, role in enumerate(self.native.ROLES):
                namespace = self.native.NAMESPACES[track]
                desired = json.loads(render_objects(self.inputs.profile, self.inputs.workload))['items']
                if role == 'driver':
                    pod = deepcopy(next(row for row in desired if row['kind'] == 'Pod' and row['metadata']['namespace'] == namespace))
                else:
                    deployment = next(row for row in desired if row['kind'] == 'Deployment' and row['metadata']['namespace'] == namespace and row['metadata']['name'] == role)
                    pod = dict(apiVersion='v1', kind='Pod', **deepcopy(deployment['spec']['template']))
                    pod['metadata'].update(name=role + '-test', namespace=namespace)
                image = pod['spec']['containers'][0]['image']
                image_role = 'envoy' if role == 'envoy' else 'kil'
                self.life.aliases[image_role] = SimpleNamespace(runtime_image=image, image_ref='sha256:' + 'd' * 64)
                pod['metadata'].update(uid=f'{track}-{role}', resourceVersion='1')
                pod['spec']['nodeName'] = 'kil-v3-lab-control-plane'
                pod['status'] = {'phase':'Running', 'podIP':f'10.244.{track_index}.{role_index + 2}',
                    'containerStatuses':[{'name':role, 'image':image, 'imageID':'sha256:'+'d'*64,
                        'restartCount':0, 'containerID':'containerd://' + str(role_index + 1) * 64,
                        'ready':True, 'state':{'running':{}}}]}
                self.pods[(track, role)] = pod
                self.life.anchors[(track, role)] = self.life.bind_application_pod(pod, track, role)
                if role != 'driver':
                    self.life.endpoints[(track, role)] = {'addresses':[pod['status']['podIP']], 'target_uid':pod['metadata']['uid']}
        return self.pods

    def test_all_four_preinstruction_pods_are_rebound(self):
        self.assertTrue(hasattr(self.life, 'require_current_track'), 'track rebinding missing')
        self.install_pods()
        with patch.object(self.life, 'read_pod', side_effect=lambda track, role, **kw: self.pods[(track, role)]), patch.object(self.life, 'read_endpoint', side_effect=lambda track, role: self.life.endpoints[(track, role)]):
            self.life.require_current_track(TRACKS[0])
            for role in self.native.ROLES:
                old = self.pods[(TRACKS[0], role)]['metadata']['uid']
                self.pods[(TRACKS[0], role)]['metadata']['uid'] = 'replacement'
                with self.assertRaises(ValueError):
                    self.life.require_current_track(TRACKS[0])
                self.pods[(TRACKS[0], role)]['metadata']['uid'] = old

    def test_rehearsal_attaches_empty_eof_without_instruction_intent(self):
        self.assertTrue(hasattr(self.life, 'instruction_phase'), 'instruction phase missing')
        self.install_pods()
        with patch.object(self.native, 'check_source'), patch.object(self.life, 'guard_cluster'), patch.object(self.life, 'require_current_track'), patch.object(self.life, 'require_current_driver'), patch.object(self.life, 'require_complete_driver'), patch.object(self.life, 'freeze_all'), patch.object(self.life, 'capture_all'), patch.object(self.life, 'observe', return_value=CommandResult(0, '', '', b'', b'')) as observed, patch.object(self.native.case, 'instruction', side_effect=AssertionError('rehearsal must not issue instruction')):
            self.life.instruction_phase()
        self.assertEqual([call.args[0].stdin for call in observed.call_args_list], [b'', b'', b''])
        self.assertEqual(self.store.attempts, [])

    def test_first_uncertain_action_blocks_later_tracks(self):
        self.assertTrue(hasattr(self.life, 'instruction_phase'), 'instruction phase missing')
        self.life.mode = 'action'
        self.install_pods()
        with patch.object(self.native, 'check_source'), patch.object(self.life, 'guard_cluster'), patch.object(self.life, 'require_current_track'), patch.object(self.life, 'require_current_driver'), patch.object(self.life, 'observe', side_effect=OSError('first uncertain attach')) as observed:
            with self.assertRaises(OSError):
                self.life.instruction_phase()
        self.assertEqual(self.store.attempts, [TRACKS[0]])
        self.assertTrue(self.store.uncertain)
        self.assertEqual(observed.call_count, 1)

    def test_source_replacement_resource_version_and_truncation_refuse_capture(self):
        self.assertTrue(hasattr(self.life, 'capture_track'), 'capture missing')
        self.install_pods()
        self.life.mode = 'action'
        from tests.test_v3b2_evidence import producer_records
        sources = producer_records(TRACKS[2], self.inputs.workload.run_id)
        for mutation in ['uid', 'rv', 'truncated']:
            fresh_store = PrivateStore(self.root / mutation)
            self.addCleanup(fresh_store.close)
            self.life.store = fresh_store
            reads = {}
            def pod_read(track, role, **kwargs):
                pod = deepcopy(self.pods[(track, role)])
                if role == 'driver':
                    pod['status']['phase'] = 'Succeeded'
                    pod['status']['containerStatuses'][0]['state'] = {'terminated':{'exitCode':0}}
                reads[role] = reads.get(role, 0) + 1
                if role == 'target' and reads[role] > 1 and mutation != 'truncated':
                    pod['metadata']['uid' if mutation == 'uid' else 'resourceVersion'] = 'changed'
                return pod
            def source_read(track, role):
                if role == 'target' and mutation == 'truncated': return b'x' * 1048576
                return b''.join(canonical(row) for row in sources['decision' if role == 'authz' else role])
            with patch.object(self.life, 'read_pod', side_effect=pod_read), patch.object(self.life, 'read_source', side_effect=source_read):
                with self.assertRaises(ValueError): self.life.capture_track(TRACKS[2], final=True)
            self.assertNotIn(TRACKS[2], self.life.results)

    def test_permit_wrong_target_upstream_rejected(self):
        self.assertTrue(hasattr(self.life, 'capture_track'), 'capture missing')
        self.install_pods(); self.life.mode = 'action'
        from tests.test_v3b2_evidence import producer_records
        sources = producer_records(TRACKS[0], self.inputs.workload.run_id)
        def pod_read(track, role, **kwargs):
            pod = deepcopy(self.pods[(track, role)])
            if role == 'driver':
                pod['status']['phase']='Succeeded'; pod['status']['containerStatuses'][0]['state']={'terminated':{'exitCode':0}}
            return pod
        with patch.object(self.life, 'read_pod', side_effect=pod_read), patch.object(self.life, 'read_source', side_effect=lambda track, role: b''.join(canonical(row) for row in sources['decision' if role == 'authz' else role])):
            with self.assertRaisesRegex(ValueError, 'upstream'):
                self.life.capture_track(TRACKS[0], final=True)

    def test_quiescence_failure_never_marks_frozen_or_retries_drain(self):
        self.assertTrue(hasattr(self.life, 'freeze_track'), 'freeze missing')
        self.install_pods()
        with patch.object(self.life, 'current_pod', return_value=self.life.anchors[(TRACKS[0], 'envoy')]), patch.object(self.life, 'observe', side_effect=ValueError('drain failed')) as observed:
            for _ in range(2):
                with self.assertRaises(ValueError): self.life.freeze_track(TRACKS[0])
        self.assertNotIn(TRACKS[0], self.life.frozen)
        self.assertEqual(observed.call_count, 1)

    def test_unbound_profile_or_cluster_never_deleted(self):
        self.assertTrue(hasattr(self.life, 'cleanup'), 'cleanup missing')
        self.life.profile_attempted = True
        with patch.object(self.life, 'observe') as observed:
            self.life.cleanup()
        observed.assert_not_called(); self.assertTrue(self.life.manual_recovery)
        self.life.profile_binding = {'bound':True}; self.life.cluster_attempted = True
        with patch.object(self.life, 'observe') as observed:
            self.life.cleanup()
        observed.assert_not_called()

    def test_changed_cluster_blocks_kind_and_profile_cleanup(self):
        self.assertTrue(hasattr(self.life, 'cleanup'), 'cleanup missing')
        self.life.profile_attempted = self.life.cluster_attempted = True
        self.life.profile_binding = {'bound':True}
        self.life.identity = replace(self.life.identity, node_container_id='b'*64, cluster_incarnation_uid='uid')
        with patch.object(self.life, 'guard_cluster', side_effect=ValueError('replaced')), patch.object(self.life, 'runner') as runner:
            self.life.cleanup()
        runner.run.assert_not_called(); self.assertTrue(self.life.manual_recovery)

    def test_reset_store_exact_owned_zero_remnant_only(self):
        self.assertTrue(hasattr(self.life, 'clear_owned_reset_store'), 'owned reset cleanup missing')
        self.life.started_pristine = True; self.life.profile_binding = {'bound':True}
        self.life.profile_delete_completed = True
        self.life.paths.store.parent.mkdir(parents=True)
        reset = b'{"disk_formatted":false,"disk_runtime":"","ramalama_provisioned":false}\n'
        self.life.paths.store.write_bytes(reset)
        observed = self.native.capture(self.life.paths)
        self.life.clear_owned_reset_store(observed)
        self.assertFalse(self.life.paths.store.exists())
        for flag in ['started_pristine', 'profile_binding', 'profile_delete_completed']:
            self.life.paths.store.write_bytes(reset)
            observed = self.native.capture(self.life.paths)
            old = getattr(self.life, flag); setattr(self.life, flag, None if flag == 'profile_binding' else False)
            with self.assertRaises(ValueError): self.life.clear_owned_reset_store(observed)
            self.assertTrue(self.life.paths.store.exists()); setattr(self.life, flag, old)
            self.life.paths.store.unlink()
        for value in [b'{"disk_formatted":true}\n', b'changed']:
            self.life.paths.store.write_bytes(value)
            with self.assertRaises(ValueError): self.life.clear_owned_reset_store(self.native.capture(self.life.paths))
            self.life.paths.store.unlink()
        self.life.paths.store.write_bytes(reset); observed = self.native.capture(self.life.paths)
        self.life.paths.store.write_bytes(b'changed')
        with self.assertRaises(ValueError): self.life.clear_owned_reset_store(observed)
        self.life.paths.store.unlink(); self.life.paths.store.symlink_to(self.root / 'absent')
        with self.assertRaises(ValueError): self.life.clear_owned_reset_store(observed)

    def test_source_check_wrong_or_dirty_is_bounded_and_request_free(self):
        with patch.object(self.native, 'capture_process', return_value=CommandResult(0, COMMIT+'\n', '', (COMMIT+'\n').encode(), b'')) as captured:
            with self.assertRaises(ValueError): self.native.check_source(self.root, COMMIT)
        self.assertEqual(captured.call_count, 2)
        self.assertEqual(captured.call_args_list[0].args[0], ('git','rev-parse','HEAD'))
        with patch.object(self.native, 'capture_process') as captured:
            with self.assertRaises(ValueError): self.native.check_source(self.root, 'A'*40)
        captured.assert_not_called()

    def test_prepare_pins_node_and_calico_and_partitions_objects(self):
        self.assertTrue(hasattr(self.life, 'prepare'), 'pure setup preparation missing')
        repository = Path(__file__).resolve().parents[1]
        self.life.repository = repository
        self.life.prepare()
        kind_config = json.loads((self.store.path / 'kind-config.yaml').read_bytes())
        self.assertEqual(kind_config['nodes'][0]['image'], self.inputs.profile.kind_node_image)
        self.assertEqual(len(kind_config['nodes']), 1)
        calico = (self.store.path / 'calico-v3.32.0.yaml').read_bytes()
        self.assertEqual(sha256(calico).hexdigest(), self.inputs.profile.calico_manifest_sha256)
        self.assertEqual([len(rows) for rows in self.life.groups], [3,15,39,3])
        for name in ['docker-config','runtime-tmp']:
            self.assertFalse((self.store.path/name).exists())
            self.assertEqual((self.life.runtime.path/name).stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.life.runtime.kind_config.read_bytes(),(self.store.path/'kind-config.yaml').read_bytes())

    def test_global_fingerprint_retains_absence_and_detects_config_change(self):
        self.assertTrue(hasattr(self.life, 'kubeconfig_fingerprint'), 'kubeconfig fingerprint missing')
        with patch.dict(os.environ, {}, clear=True):
            first = self.life.kubeconfig_fingerprint()
            self.assertFalse(first['files'][0]['present'])
            self.assertFalse((self.home/'.kube').exists())
            (self.home/'.kube').mkdir(); (self.home/'.kube/config').write_bytes(b'original')
            second = self.life.kubeconfig_fingerprint()
            (self.home/'.kube/config').write_bytes(b'changed')
            self.assertNotEqual(second, self.life.kubeconfig_fingerprint())
        with patch.dict(os.environ, {'KUBECONFIG':str(self.home/'.kube/config')+'::relative'}):
            with self.assertRaises(ValueError): self.life.kubeconfig_fingerprint()

    def test_foreign_context_change_is_not_preserved(self):
        self.assertTrue(hasattr(self.life, 'require_foreign_preserved'), 'foreign state guard missing')
        self.life.original_foreign = {'context':'original'}
        with patch.object(self.life, 'foreign_snapshot', return_value={'context':'changed'}):
            with self.assertRaises(ValueError): self.life.require_foreign_preserved()

    def test_execute_capture_failure_runs_cleanup_and_private_report(self):
        self.assertTrue(hasattr(self.life, 'execute'), 'execute missing')
        with patch.object(self.life, 'setup'), patch.object(self.life, 'instruction_phase', side_effect=ValueError('incomplete source')), patch.object(self.life, 'cleanup') as cleaned:
            report = self.life.execute()
        cleaned.assert_called_once()
        self.assertEqual(report['status'], 'inconclusive')
        self.assertFalse(report['platform_image_provenance_verified'])
        self.assertFalse(report['full_kind_calico_acceptance'])
        self.assertEqual(report['request_intent_count'], 0)
        self.assertTrue((self.store.path/'report.json').is_file())
        self.assertIn('report.json', (self.store.path/'SHA256SUMS').read_text())

    def test_setup_requires_clean_source_before_private_preparation(self):
        self.assertTrue(hasattr(self.life, 'setup'), 'setup missing')
        with patch.object(self.native, 'check_source', side_effect=ValueError('dirty')), patch.object(self.life, 'prepare') as prepared:
            with self.assertRaises(ValueError): self.life.setup()
        prepared.assert_not_called(); self.runner.run.assert_not_called()

    def test_native_versions_compare_accepted_output_and_exact_host_pins(self):
        self.assertTrue(hasattr(self.life, 'verify_versions'), 'version gate missing')
        self.inputs.tool_records = {name:{'version_output':'accepted-'+name} for name in ['docker','kind','kubectl']}
        outputs = [b'accepted-docker\n', b'accepted-kind\n', b'accepted-kubectl\n',
                   COLIMA_VERSION_OUTPUT, b'limactl version 2.2.0\n']
        with patch.object(self.native.platform, 'system', return_value='Darwin'), patch.object(self.native.platform, 'machine', return_value='arm64'), patch.object(self.life, 'observe', side_effect=[CommandResult(0,p.decode(),'',p,b'') for p in outputs]):
            self.life.verify_versions()
        self.assertEqual(self.life.environment['docker_daemon_version'], 'UNOBSERVED')
        with patch.object(self.native.platform, 'system', return_value='Linux'):
            with self.assertRaises(ValueError): self.life.verify_versions()

    def test_actual_colima_v_prefix_same_pin_retains_observed_versions(self):
        state=self.full_fake_runner(); failure=None
        with patch.object(self.native.platform,'system',return_value='Darwin'),patch.object(self.native.platform,'machine',return_value='arm64'):
            try: self.life.verify_versions()
            except ValueError as error: failure=str(error)
        receipts=[path.read_bytes() for path in self.store.path.glob('command-*.stdout')]
        self.assertEqual(len(COLIMA_VERSION_OUTPUT),76); self.assertIn(COLIMA_VERSION_OUTPUT,receipts)
        self.assertEqual(len(state['calls']),5); self.assertTrue(all(not command.mutating for command in state['calls']))
        self.assertFalse(self.life.profile_attempted); self.assertFalse(self.life.cluster_attempted)
        self.assertEqual(self.store.attempts,[])
        self.assertIsNone(failure,'approved Colima pin with native v prefix was refused: '+str(failure))
        self.assertEqual(self.life.environment['observed_tool_versions']['colima'],COLIMA_VERSION_OUTPUT.decode().strip())
        self.assertEqual(self.life.environment['observed_tool_versions']['lima'],'limactl version 2.2.0')
        self.assertEqual(self.life.environment['docker_daemon_version'],'UNOBSERVED')

    def test_colima_version_nearby_pins_extra_text_and_crlf_refused_before_mutation(self):
        state=self.full_fake_runner(); original=self.runner.run.side_effect
        bad_outputs=[COLIMA_VERSION_OUTPUT.replace(b'v0.10.3',value) for value in
            [b'v0.10.4',b'v0.10.30',b'0.10.3',b'vv0.10.3']]
        bad_outputs += [COLIMA_VERSION_OUTPUT+b'extra\n',COLIMA_VERSION_OUTPUT.replace(b'\n',b'\r\n'),
            COLIMA_VERSION_OUTPUT.replace(b'git commit:',b'wrong extra:'),COLIMA_VERSION_OUTPUT[:-1]]
        for payload in bad_outputs:
            def version(command):
                if command.argv==('colima','version'):
                    state['calls'].append(command)
                    return CommandResult(0,payload.decode(),'',payload,b'')
                return original(command)
            self.runner.run.side_effect=version
            with patch.object(self.native.platform,'system',return_value='Darwin'),patch.object(self.native.platform,'machine',return_value='arm64'),self.assertRaisesRegex(ValueError,'colima_lima_versions_not_pinned'):
                self.life.verify_versions()
        self.assertTrue(all(not command.mutating for command in state['calls']))
        self.assertFalse(self.life.profile_attempted); self.assertFalse(self.life.cluster_attempted)
        self.assertEqual(self.store.attempts,[])

    def test_driver_incarnation_drift_is_permanent_not_read_retry(self):
        self.install_pods()
        replaced = deepcopy(self.pods[(TRACKS[0],'driver')]); replaced['metadata']['uid']='other'
        with patch.object(self.life, 'read_pod', return_value=replaced) as read, patch.object(self.native.time, 'sleep'):
            with self.assertRaises(ValueError): self.life.require_complete_driver(TRACKS[0])
        self.assertEqual(read.call_count, 1)

    def test_drain_true_must_not_accept_integer_one(self):
        self.install_pods()
        with patch.object(self.life, 'current_pod', return_value=self.life.anchors[(TRACKS[0],'envoy')]), patch.object(self.life, 'observe', return_value=CommandResult(0,'{"drain_requested":1}\n','',b'{"drain_requested":1}\n',b'')) as observed, patch.object(self.native.time,'sleep'):
            with self.assertRaisesRegex(ValueError, 'drain'): self.life.freeze_track(TRACKS[0])
        self.assertEqual(observed.call_count, 1)

    def test_quiescence_active_gauge_unknown_fields_refused(self):
        self.install_pods()
        drain = canonical({'drain_requested':True})
        stats = canonical({'listener_refused':True, 'stats':[{'name':name,'value':0,'unknown':1} for name in self.native.ACTIVE_GAUGES]})
        with patch.object(self.life, 'current_pod', return_value=self.life.anchors[(TRACKS[0],'envoy')]), patch.object(self.life,'observe', side_effect=[CommandResult(0,drain.decode(),'',drain,b'')]+[CommandResult(0,stats.decode(),'',stats,b'')]*20), patch.object(self.native.time,'sleep'):
            with self.assertRaises(ValueError): self.life.freeze_track(TRACKS[0])
        self.assertNotIn(TRACKS[0], self.life.frozen)

    def test_retained_nested_files_are_bounded_and_checksummed_without_symlinks(self):
        self.assertTrue(hasattr(self.life,'retained_checksums'), 'recursive retained-file verifier missing')
        nested = self.store.path/'docker-config'; nested.mkdir(mode=0o700)
        (nested/'config.json').write_bytes(b'{}\n')
        sums = self.life.retained_checksums()
        self.assertIn('docker-config/config.json', sums)
        self.assertEqual(sums['docker-config/config.json'],sha256(b'{}\n').hexdigest())
        (nested/'redirect').symlink_to(nested/'config.json')
        with self.assertRaises(ValueError): self.life.retained_checksums()
        (nested/'redirect').unlink()
        with (nested/'oversized').open('wb') as stream: stream.truncate(8*1024*1024+1)
        with self.assertRaises(ValueError): self.life.retained_checksums()

    def test_owned_deleted_but_foreign_changed_is_not_manual_owned_recovery(self):
        self.life.profile_attempted=True; self.life.profile_binding={'bound':True}
        def mutation(command, **kwargs):
            if command.argv[1]=='delete': self.life.profile_delete_completed=True
            return CommandResult(0,'','',b'',b'')
        with patch.object(self.life,'observe',side_effect=mutation), patch.object(self.life,'guard_profile'), patch.object(self.native,'capture',return_value={}), patch.object(self.native,'absent',return_value=True), patch.object(self.life,'clear_owned_reset_store'), patch.object(self.life,'require_foreign_preserved',side_effect=ValueError('global context changed')):
            self.life.cleanup()
        self.assertFalse(self.life.owned_teardown); self.assertFalse(self.life.manual_recovery)

    def full_fake_runner(self):
        """Candidate full-source fixtures, only under this test's temporary home."""
        from tests.test_v3b2_generated_kil_pod_configuration import fixture as generated_fixture
        from tests.test_v3b2_driver_pod_configuration import fixture as driver_fixture
        from tests.test_v3b2_service_bindings import fixture as service_fixture
        from tests.test_v3b2_evidence import producer_records
        from kil.v3b2_manifests import WorkloadIdentity
        accepted = {row.role:row for row in self.native.ACCEPTED_IMAGES}
        self.inputs.workload = WorkloadIdentity('v3b2-'+'1'*64,accepted['kil'].target_digest,accepted['envoy'].requested_image)
        self.inputs.tools.mkdir(parents=True, exist_ok=True)
        self.inputs.tool_records = {name:{'version_output':'fixture-'+name} for name in ['docker','kind','kubectl']}
        self.life.repository = Path(__file__).resolve().parents[1]
        self.life.runner.global_docker_config = str(self.home/'.docker')
        identity = replace(self.life.identity,node_container_id='b'*64,cluster_incarnation_uid='cluster-uid')
        args = generated_fixture(profile=self.inputs.profile,workload=self.inputs.workload,owned_identity=identity)
        runtime = json.loads(args['runtime_objects'])
        drivers = driver_fixture(profile=self.inputs.profile,workload=self.inputs.workload,owned_identity=identity)['pods']
        runtime['items'] = [row for row in runtime['items'] if not(row['kind']=='Pod' and row['metadata']['name']=='driver')] + drivers
        deployments = {(row['metadata']['namespace'],row['metadata']['name']):row
            for row in runtime['items'] if row['kind']=='Deployment'
            and row['metadata'].get('namespace') in self.native.NAMESPACES.values()}
        for row in deployments.values(): row['metadata']['generation']=1
        pods = {}
        for index,row in enumerate(runtime['items']):
            if row['kind']=='Node':
                row['status']={'nodeInfo':{'operatingSystem':'linux','osImage':'fixture-linux','kernelVersion':'fixture-kernel','containerRuntimeVersion':'containerd://fixture'}}
            if row['kind']!='Pod': continue
            row.setdefault('spec',{}).setdefault('containers',[])
            if row['metadata'].get('namespace') not in self.native.NAMESPACES.values(): continue
            role = row['metadata']['labels']['kil.dev/role']; track = row['metadata']['labels']['kil.dev/track']
            image = accepted['envoy' if role=='envoy' else 'kil']
            runtime_image = image.config_digest if role=='envoy' else image.requested_image
            image_ref = image.requested_image if role=='envoy' else 'kil.local/kil-v3b2@'+image.target_digest
            row['spec']['nodeName']='kil-v3-lab-control-plane'
            row['status']={'phase':'Running','podIP':f'10.244.0.{index+2}',
                'containerStatuses':[{'name':role,'image':runtime_image,'imageID':image_ref,
                    'restartCount':0,'containerID':'containerd://'+format(index+1,'064x'),'ready':True,'state':{'running':{}}}]}
            pods[(track,role)] = row
        self.pods = pods
        self.life.paths.lima.mkdir(parents=True, exist_ok=True)
        self.state = {'profile':False,'stopped':False,'cluster':False,'attached':[],'drained':[],'requests':{},'calls':[]}
        services = service_fixture(profile=self.inputs.profile,workload=self.inputs.workload)[3]
        service_map = {(row['metadata']['namespace'],row['metadata']['name']):row for row in services}
        def result(payload=b'',rc=0,stderr=b''):
            return CommandResult(rc,payload.decode('utf-8','replace'),stderr.decode('utf-8','replace'),payload,stderr)
        def dispatch(command):
            self.state['calls'].append(command)
            argv = command.argv; executable = Path(argv[0]).name
            if argv[0].startswith('/'):
                return result(('fixture-'+executable+'\n').encode())
            if argv==('colima','version'): return result(COLIMA_VERSION_OUTPUT)
            if argv==('limactl','--version'): return result(b'limactl version 2.2.0\n')
            if argv==('docker','context','show'): return result(b'fixture-global\n')
            if argv==('colima','list','--json'):
                rows = getattr(self, 'default_rows', []) if not command.env else ([] if not self.state['profile'] else [{'name':'kil-v3-lab','status':'Stopped' if self.state['stopped'] else 'Running',
                    'arch':'aarch64','runtime':'docker','cpus':4,'memory':8*1024**3,'disk':60*1024**3}])
                return result(b''.join(canonical(row) for row in rows))
            if executable=='colima' and argv[1]=='start':
                create_native_profile(self.life.paths); self.state['profile']=True; return result()
            if executable=='colima' and argv[1]=='stop':
                (self.life.paths.disk/'in_use_by').unlink(); self.state['stopped']=True; return result()
            if executable=='colima' and argv[1]=='delete':
                for target in [self.life.paths.profile,self.life.paths.instance,self.life.paths.disk]: shutil.rmtree(target)
                self.life.paths.store.parent.mkdir(parents=True,exist_ok=True)
                self.life.paths.store.write_bytes(b'{"disk_formatted":false,"disk_runtime":"","ramalama_provisioned":false}\n')
                self.state['profile']=False; return result()
            if argv==self.native.CLUSTER_INVENTORY_ARGV:
                return result(canonical({'ID':'b'*64,'Names':'kil-v3-lab-control-plane'}) if self.state['cluster'] else b'')
            if argv==('docker','inspect','kil-v3-lab-control-plane'):
                return result(canonical(node())) if self.state['cluster'] else result(rc=1,stderr=b'no node')
            if executable=='kind' and argv[1]=='create': self.state['cluster']=True; return result()
            if executable=='kind' and argv[1]=='delete': self.state['cluster']=False; return result()
            if executable=='kind' and argv[1]=='load': return result()
            if executable=='docker' and argv[1] in ['load','tag','pull']: return result()
            if executable=='docker' and argv[1:3]==('image','inspect'):
                image = next(row for row in accepted.values() if row.requested_image==argv[3])
                return result(canonical([{'Id':image.config_digest,'RepoTags':[image.requested_image] if image.role=='kil' else [],
                                         'RepoDigests':[image.requested_image] if image.role=='envoy' else []}]))
            if executable=='docker' and 'crictl' in argv[3]:
                image = next(row for row in accepted.values() if row.requested_image==argv[-1])
                return result(canonical({'status':{'id':image.config_digest,'repoTags':[image.requested_image] if image.role=='kil' else [],
                    'repoDigests':['kil.local/kil-v3b2@'+image.target_digest] if image.role=='kil' else [image.requested_image],
                    'size':'1048576','username':'','pinned':False}}))
            if executable=='docker' and 'ctr' in argv[3]:
                lines = ['REF TYPE DIGEST STATUS SIZE UNPACKED']
                for image in accepted.values():
                    aliases = [image.requested_image] + (['kil.local/kil-v3b2@'+image.target_digest] if image.role=='kil' else [])
                    media = 'application/vnd.oci.image.'+('manifest' if image.role=='kil' else 'index')+'.v1+json'
                    lines.extend(f'{alias} {media} {image.target_digest} complete (4/4) 1.0 MiB true' for alias in aliases)
                return result(('\n'.join(lines)+'\n').encode())
            arguments = argv[3:]
            if arguments==('get','namespace','kube-system','--output','json'):
                return result(canonical({'apiVersion':'v1','kind':'Namespace','metadata':{'name':'kube-system','uid':'cluster-uid'}})) if self.state['cluster'] else result(rc=1,stderr=b'connection refused')
            if arguments[:2]==('apply','-f'): return result()
            if arguments[:2]==('get','--filename'):
                desired = json.loads(command.stdin)['items']; applied=[]
                for index,row in enumerate(desired):
                    if row['kind']=='Service': row=deepcopy(service_map[(row['metadata']['namespace'],row['metadata']['name'])])
                    else: row['metadata'].update(uid=f'applied-{index}',resourceVersion='1')
                    if row['kind']=='Deployment':
                        actual=deployments[(row['metadata']['namespace'],row['metadata']['name'])]
                        row['metadata'].update(uid=actual['metadata']['uid'],generation=actual['metadata']['generation'])
                        row['status']={'observedGeneration':1,'replicas':1,'readyReplicas':1,'availableReplicas':1,
                            'conditions':[{'type':'Available','status':'True','reason':'MinimumReplicasAvailable'}]}
                    applied.append(row)
                return result(canonical({'apiVersion':'v1','kind':'List','items':applied}))
            if arguments[:2] in [('get','daemonset'),('get','deployment')]:
                kind = 'DaemonSet' if arguments[1]=='daemonset' else 'Deployment'
                pins = dict(self.inputs.profile.calico_images)
                name = arguments[2]
                projected = {'apiVersion':'apps/v1','kind':kind,'metadata':{'name':name,'namespace':'kube-system','uid':'calico-'+kind,'resourceVersion':'1'},
                    'spec':{'containers':[{'name':name,'image':pins['node' if kind=='DaemonSet' else 'kube_controllers']}],
                            'initContainers':[{'name':n,'image':pins['node' if n=='ebpf-bootstrap' else 'cni']} for n in ['upgrade-ipam','install-cni','ebpf-bootstrap']] if kind=='DaemonSet' else []},
                    'status':{'desiredNumberScheduled':1,'numberReady':1} if kind=='DaemonSet' else {'replicas':1,'readyReplicas':1}}
                projected['metadata']['managedFields']=[{'manager':'kubectl'}]
                projected['spec']={'selector':{'matchLabels':{'k8s-app':name}},'template':{'metadata':{'labels':{'k8s-app':name}},'spec':projected['spec']}}
                for row in projected['spec']['template']['spec']['containers']:
                    row.update(imagePullPolicy='IfNotPresent',resources={},env=[{'name':'NATIVE_EXTRA','value':'retained'}])
                if kind=='Deployment': projected['spec']['template']['spec'].pop('initContainers')
                projected['status']['observedGeneration']=1
                return result(json.dumps(projected,indent=2).encode()+b'\n')
            if arguments and arguments[0]=='wait': return result()
            if arguments[:2]==('get','endpointslices'):
                namespace = arguments[3]; role=arguments[5].split('=')[1]
                track=next(track for track,ns in self.native.NAMESPACES.items() if ns==namespace); pod=pods[(track,role)]
                return result(canonical({'apiVersion':'discovery.k8s.io/v1','kind':'EndpointSlice','metadata':{'name':role+'-slice','namespace':namespace,'labels':{'kubernetes.io/service-name':role}},
                    'addressType':'IPv4','ports':[{'name':'http','protocol':'TCP','port':8080}],
                    'endpoints':[{'addresses':[pod['status']['podIP']],'conditions':{'ready':True},'targetRef':{'kind':'Pod','name':pod['metadata']['name'],'namespace':namespace,'uid':pod['metadata']['uid']}}]}))
            if arguments[:2]==('get','pod'):
                namespace=arguments[4]; name=arguments[2]
                return result(canonical(next(pod for pod in pods.values() if pod['metadata']['namespace']==namespace and pod['metadata']['name']==name)))
            if arguments and arguments[0]=='get' and '--all-namespaces' in arguments: return result(canonical(runtime))
            if arguments and arguments[0]=='attach':
                namespace=arguments[3]; track=next(track for track,ns in self.native.NAMESPACES.items() if ns==namespace)
                self.state['attached'].append((track,command.stdin))
                if command.stdin: self.state['requests'][track]=True
                pod=pods[(track,'driver')]; pod['metadata']['resourceVersion']='2'; pod['status']['phase']='Succeeded'; pod['status']['containerStatuses'][0]['state']={'terminated':{'exitCode':0}}
                source=producer_records(track,self.inputs.workload.run_id,request_free=not bool(command.stdin))
                return result(b''.join(canonical(row) for row in source['driver']))
            if arguments and arguments[0]=='exec' and arguments[-2]=='-pceu':
                from kil.v3b2_envoy_quiescence import ENVOY_DRAIN_SCRIPT
                if arguments[-1]==ENVOY_DRAIN_SCRIPT:
                    self.state['drained'].append(arguments[1]); return result(canonical({'drain_requested':True}))
                return result(canonical({'listener_refused':True,'stats':[{'name':name,'value':0} for name in self.native.ACTIVE_GAUGES]}))
            if arguments and arguments[0] in ('logs','exec'):
                namespace=arguments[3]; name=arguments[1][4:]
                track,role=next(key for key,pod in pods.items() if pod['metadata']['namespace']==namespace and pod['metadata']['name']==name)
                sources=producer_records(track,self.inputs.workload.run_id,request_free=not self.state['requests'].get(track))
                if self.state['requests'].get(track) and sources['envoy'][0]['response_code']=='200': sources['envoy'][0]['upstream_host']=pods[(track,'target')]['status']['podIP']+':8080'
                return result(b''.join(canonical(row) for row in sources['decision' if role=='authz' else role]))
            raise AssertionError('unexpected fake native command: '+repr(argv))
        self.life.runner.run.side_effect=dispatch
        return self.state

    def test_fake_full_rehearsal_setup_capture_and_exact_teardown(self):
        state=self.full_fake_runner()
        with patch.object(self.native,'check_source'), patch.object(self.native.platform,'system',return_value='Darwin'), patch.object(self.native.platform,'machine',return_value='arm64'), patch.object(self.native.time,'sleep'):
            report=self.life.execute()
        self.assertEqual(report['status'],'complete',report['error'])
        self.assertTrue(report['owned_teardown']); self.assertEqual(report['request_intent_count'],0)
        self.assertEqual([payload for _,payload in state['attached']],[b'',b'',b''])
        self.assertEqual(len(state['drained']),3); self.assertFalse(state['cluster']); self.assertFalse(state['profile'])
        self.assertFalse(self.life.paths.store.exists())
        synopsis=(self.store.path/'synopsis.md').read_text()
        for phrase in ['pod_ip','requested_image','runtime_image','image_ref','Input commitments','Requested profile resources','Actual creation-bound profile']:
            self.assertIn(phrase,synopsis)
        self.assertIn('requested',report['profile_resources'])

    def test_fake_full_action_records_observed_join_then_next_track(self):
        self.life.mode='action'; state=self.full_fake_runner()
        with patch.object(self.native,'check_source'), patch.object(self.native.platform,'system',return_value='Darwin'), patch.object(self.native.platform,'machine',return_value='arm64'), patch.object(self.native.time,'sleep'):
            report=self.life.execute()
        self.assertEqual(report['status'],'complete',report['error'])
        self.assertEqual(report['request_intent_count'],3)
        self.assertEqual([row['observed'] for row in report['joined_results']],[['permit',200,1],['permit',200,1],['deny',403,0]])
        self.assertEqual([track for track,_ in state['attached']],list(TRACKS))
        self.assertEqual(len(state['drained']),3)
        self.assertEqual(len(self.life.deployment_bindings),9)
        for filename in ('applied-objects.json','runtime-ready-source.json'):
            actual=json.loads((self.store.path/filename).read_bytes())
            for row in actual['items']:
                if row['kind']=='Deployment' and row['metadata'].get('namespace') in self.native.NAMESPACES.values():
                    metadata=row['metadata']; track=next(track for track,ns in self.native.NAMESPACES.items() if ns==metadata['namespace'])
                    self.assertEqual((metadata['uid'],metadata['generation']),self.life.deployment_bindings[(track,metadata['name'])])
        rows=[json.loads(line) for line in self.store.journal.read_bytes().splitlines()]
        first_final_target=next(index for index,row in enumerate(rows) if row['event']=='source_capture' and row['details']['track']==TRACKS[0] and row['details']['role']=='target' and 'final' in row['details']['file'])
        second_request=next(index for index,row in enumerate(rows) if row['event']=='request_intent' and row['details']['track']==TRACKS[1])
        self.assertLess(first_final_target,second_request)

    def test_bound_kind_creation_failure_reports_reached_binding_gate(self):
        self.full_fake_runner(); original=self.life.runner.run.side_effect
        def failed_create(command):
            result=original(command)
            if command.argv[:3]==('kind','create','cluster'):
                return CommandResult(3,'','creation failed',b'',b'creation failed')
            return result
        self.life.runner.run.side_effect=failed_create
        with patch.object(self.native,'check_source'), patch.object(self.native.platform,'system',return_value='Darwin'), patch.object(self.native.platform,'machine',return_value='arm64'), patch.object(self.native.time,'sleep'):
            report=self.life.execute()
        self.assertEqual(report['reached_gate'],'inconclusive_at_cluster_bound')
        self.assertTrue(report['owned_teardown']); self.assertEqual(report['request_intent_count'],0)

    def full_replacement_failure(self, changed):
        self.life.mode='action'; state=self.full_fake_runner(); original=self.life.runner.run.side_effect
        def replaced(command):
            if state['attached'] and changed=='node' and command.argv==('docker','inspect','kil-v3-lab-control-plane'):
                replacement=node(); replacement[0]['Id']='c'*64; raw=canonical(replacement)
                return CommandResult(0,raw.decode(),'',raw,b'')
            if state['attached'] and changed=='uid' and command.argv[3:]==('get','namespace','kube-system','--output','json'):
                raw=canonical({'apiVersion':'v1','kind':'Namespace','metadata':{'name':'kube-system','uid':'other'}})
                return CommandResult(0,raw.decode(),'',raw,b'')
            result=original(command)
            if changed=='profile' and command.argv[3:5]==('attach','pod/driver'):
                (self.life.paths.profile/'colima.yaml').write_bytes(b'changed')
            return result
        self.life.runner.run.side_effect=replaced
        with patch.object(self.native,'check_source'), patch.object(self.native.platform,'system',return_value='Darwin'), patch.object(self.native.platform,'machine',return_value='arm64'), patch.object(self.native.time,'sleep'):
            report=self.life.execute()
        self.assertEqual(report['status'],'inconclusive'); self.assertTrue(report['manual_recovery'])
        self.assertEqual(report['request_intent_count'],1)
        self.assertFalse(any(command.argv[:3]==('kind','delete','cluster') or command.argv[:2] in [('colima','stop'),('colima','delete')] for command in state['calls']))

    def test_node_replacement_never_deletes_cluster_or_profile(self): self.full_replacement_failure('node')

    def test_cluster_uid_replacement_never_deletes_cluster_or_profile(self): self.full_replacement_failure('uid')

    def test_profile_replacement_never_deletes_cluster_or_profile(self): self.full_replacement_failure('profile')

    def test_unexpected_complete_tuple_is_observed_without_mutation_retry(self):
        self.life.mode='action'
        from tests import test_v3b2_evidence as evidence
        original=evidence.producer_records
        def unexpected(track,run_id,**kwargs):
            rows=original(track,run_id,**kwargs)
            if track==TRACKS[0] and not kwargs.get('request_free',False):
                rows['driver'][1]['response_status']=403
                rows['decision'][0].update(outcome='deny',http_status=403,adapter_reasons=['unverified'],engine_reasons=['expired'])
                rows['envoy'][0].update(response_code='403',upstream_host='-',upstream_service_time='-')
                rows['target']=[]
            return rows
        with patch.object(evidence,'producer_records',side_effect=unexpected): state=self.full_fake_runner()
        with patch.object(self.native,'check_source'), patch.object(self.native.platform,'system',return_value='Darwin'), patch.object(self.native.platform,'machine',return_value='arm64'), patch.object(self.native.time,'sleep'):
            report=self.life.execute()
        self.assertEqual(report['status'],'complete',report['error'])
        self.assertEqual(report['joined_results'][0]['observed'],['deny',403,0])
        self.assertEqual(report['joined_results'][0]['classification'],'unexpected')
        self.assertEqual(report['joined_results'][0]['engine_reasons'],['expired'])
        self.assertEqual(report['request_intent_count'],3); self.assertEqual(len(state['attached']),3)

    def test_each_colima_mutation_failed_attempt_is_not_replayed(self):
        commands=[self.native.colima_start_command(),
                  Command(('colima','stop','--profile','kil-v3-lab'),10,mutating=True),
                  Command(('colima','delete','--profile','kil-v3-lab','--force','--data'),10,mutating=True)]
        self.runner.run.side_effect=OSError('uncertain')
        self.life.profile_stopped=True
        with patch.object(self.native,'check_source'), patch.object(self.life,'require_foreign_preserved'), patch.object(self.life,'guard_profile'), patch.object(self.life,'private_inventory'):
            for command in commands:
                for _ in range(2):
                    with self.assertRaises((OSError,ValueError)): self.life.observe(command)
        self.assertEqual(self.runner.run.call_count,3)

    def test_negative_timeout_receipt_is_never_success(self):
        self.runner.run.return_value=CommandResult(-1000,'prefix','diagnostic',b'prefix',b'diagnostic')
        with self.assertRaises(ValueError): self.life.observe(Command(('colima','version'),10))
        self.assertEqual((self.store.path/'command-0001.stdout').read_bytes(),b'prefix')

    def test_mutation_cannot_substitute_endpoint_kubeconfig_or_private_colima_env(self):
        substituted=[replace(kind_create_command(self.life.identity),env=(('DOCKER_CONFIG','/tmp/other/docker-config'),('DOCKER_HOST','unix:///tmp/other/kil-v3-lab/docker.sock'))),
            replace(self.native.colima_start_command(),env=(('DOCKER_CONFIG','/tmp/other/docker-config'),('TMPDIR','/tmp/other/runtime-tmp'))),
            kubectl_apply_command(replace(self.life.identity,kubeconfig='/tmp/other/kubeconfig'),canonical({'apiVersion':'v1','kind':'List','items':[]})),
            Command(('limactl','disk','delete','colima-kil-v3-lab'),10,env=(('LIMA_HOME','/tmp/other/.colima/_lima'),),mutating=True)]
        with patch.object(self.native,'check_source'),patch.object(self.life,'guard_cluster'),patch.object(self.life,'guard_profile'),patch.object(self.life,'endpoint_rows',return_value=[]),patch.object(self.life,'require_foreign_preserved'):
            for command in substituted:
                with self.assertRaises(ValueError): self.life.observe(command)
        self.runner.run.assert_not_called(); self.assertFalse(self.life.profile_attempted); self.assertFalse(self.life.cluster_attempted)

    def test_dispatch_exception_still_reports_actual_attempt_gate(self):
        self.full_fake_runner(); original=self.life.runner.run.side_effect
        def start_error(command):
            if command.argv==self.native.colima_start_command().argv: raise OSError('ambiguous start')
            return original(command)
        self.life.runner.run.side_effect=start_error
        with patch.object(self.native,'check_source'), patch.object(self.native.platform,'system',return_value='Darwin'), patch.object(self.native.platform,'machine',return_value='arm64'):
            report=self.life.execute()
        self.assertEqual(report['reached_gate'],'inconclusive_at_profile_start_attempted')
        self.assertTrue(report['manual_recovery']); self.assertEqual(report['request_intent_count'],0)

    def test_kind_attempt_unbound_never_stops_or_deletes_vm(self):
        state=self.full_fake_runner(); original=self.life.runner.run.side_effect
        def creation_error(command):
            if command.argv[:3]==('kind','create','cluster'):
                state['calls'].append(command); return CommandResult(5,'','uncertain create',b'',b'uncertain create')
            return original(command)
        self.life.runner.run.side_effect=creation_error
        with patch.object(self.native,'check_source'), patch.object(self.native.platform,'system',return_value='Darwin'), patch.object(self.native.platform,'machine',return_value='arm64'):
            report=self.life.execute()
        self.assertEqual(report['status'],'inconclusive'); self.assertTrue(report['manual_recovery'])
        self.assertFalse(any(command.argv[:2] in [('colima','stop'),('colima','delete')] or command.argv[:3]==('kind','delete','cluster') for command in state['calls']))

    def test_closed_raw_pod_delete_is_outside_exploratory_mutation_table(self):
        command=Command(('kubectl','--kubeconfig',self.life.identity.kubeconfig,'delete','--raw',
                         '/api/v1/namespaces/kil-v3-baseline/pods/driver','-f','-'),10,
                        stdin=canonical({'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':'test-driver'}}),mutating=True)
        with patch.object(self.life,'guard_cluster'):
            with self.assertRaises(ValueError): self.life.observe(command)
        self.runner.run.assert_not_called()

    def test_rehearsal_nonempty_and_action_nondurable_attach_are_refused(self):
        payload=self.native.case.instruction(TRACKS[0],self.life.run_digest,100)
        command=self.native.kubectl_attach_command(self.life.identity,'kil-v3-baseline',payload)
        with patch.object(self.life,'guard_cluster'):
            with self.assertRaises(ValueError): self.life.observe(command)
            self.life.mode='action'
            with self.assertRaises(ValueError): self.life.observe(command)
        self.runner.run.assert_not_called()

    def test_retained_native_oversize_reports_inconclusive_not_partial_sums(self):
        nested=self.store.path/'runtime-tmp'; nested.mkdir(mode=0o700)
        with (nested/'large-scratch').open('wb') as stream: stream.truncate(8*1024*1024+1)
        with patch.object(self.life,'setup'),patch.object(self.life,'instruction_phase'),patch.object(self.life,'cleanup'):
            report=self.life.execute()
        self.assertEqual(report['status'],'inconclusive'); self.assertIn('bounded',report['retained_files_error'])
        self.assertFalse((self.store.path/'SHA256SUMS').exists())

    def execute_fake(self):
        with patch.object(self.native,'check_source'),patch.object(self.native.platform,'system',return_value='Darwin'),patch.object(self.native.platform,'machine',return_value='arm64'),patch.object(self.native.time,'sleep'):
            return self.life.execute()

    def test_same_named_default_stopped_lab_is_foreign_and_byte_inode_preserved(self):
        from tests.test_v3b2_profile_state import create_profile
        self.full_fake_runner()
        create_profile(self.life.default_paths)
        self.default_rows = [{'name':'kil-v3-lab','status':'Stopped','arch':'aarch64',
                             'runtime':'docker','cpus':4,'memory':8*1024**3,'disk':60*1024**3}]
        original = self.native.capture(self.life.default_paths)
        report = self.execute_fake()
        self.assertEqual(report['status'], 'complete', report['error'])
        self.assertTrue(report['owned_teardown'])
        self.assertEqual(report['foreign_global_original']['foreign_profiles'], self.default_rows)
        self.assertEqual(self.native.capture(self.life.default_paths), original)
        self.assertNotEqual(self.life.paths.profile, self.life.default_paths.profile)
        from kil.hf_exploratory_runtime import ExploratoryColimaCommand
        for command in self.state['calls']:
            if command.argv[0]=='colima':
                if type(command) is Command:
                    self.assertEqual(command.argv,('colima','list','--json'))
                    self.assertEqual(command.env,())
                else:
                    self.assertIs(type(command),ExploratoryColimaCommand)
                    self.assertEqual(command.env,self.life.colima_env)
            if command.argv[0] in ('docker','kind') and command.argv!=('docker','context','show'):
                self.assertEqual(command.env,self.life.docker_env)
            if command.argv[0]=='kubectl':
                self.assertEqual(command.argv[1:3],('--kubeconfig',str(self.life.runtime.kubeconfig)))
            if command.argv[:2]==('kind','create'):
                self.assertIn(str(self.life.runtime.kind_config),command.argv)
                self.assertNotIn(str(self.store.path/'kind-config.yaml'),command.argv)

    def test_private_extra_profile_roster_denies_start_before_latch(self):
        self.full_fake_runner()
        (self.life.paths.lima / 'colima-foreign').mkdir()
        report = self.execute_fake()
        self.assertEqual(report['status'], 'inconclusive')
        self.assertFalse(self.life.profile_attempted)
        self.assertFalse(any(command.mutating for command in self.state['calls']))

    def test_default_network_and_docker_config_changes_are_not_preserved(self):
        self.full_fake_runner()
        networks = self.life.default_paths.lima / '_config/networks.yaml'
        networks.parent.mkdir(parents=True); networks.write_bytes(b'network-original')
        docker = self.home / '.docker/config.json'
        docker.parent.mkdir(); docker.write_bytes(b'{"original":true}')
        self.life.original_foreign = self.life.foreign_snapshot()
        for path in [networks, docker]:
            self.life.original_foreign = self.life.foreign_snapshot()
            before = path.read_bytes()
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError): self.life.require_foreign_preserved()
            path.write_bytes(before)

    def test_kind_runtime_control_stale_refuses_before_create_attempt(self):
        self.full_fake_runner()
        self.life.prepare()
        original = (self.store.path / 'kind-config.yaml').read_bytes()
        self.life.runtime.kind_config.write_bytes(b'changed')
        with patch.object(self.life, 'guard_profile'), patch.object(self.life, 'endpoint_rows', return_value=[]):
            with self.assertRaises(ValueError): self.life.observe(kind_create_command(self.life.identity))
        self.assertFalse(self.life.cluster_attempted)
        self.assertFalse(any(command.mutating for command in self.state['calls']))
        self.assertEqual((self.store.path / 'kind-config.yaml').read_bytes(), original)

    def test_runtime_snapshot_precedes_first_teardown_and_receipt_sums_survive_context_removal(self):
        self.full_fake_runner()
        context = self.life.runtime.docker_config / 'contexts/meta' / sha256(b'colima-kil-v3-lab').hexdigest() / 'meta.json'
        context.parent.mkdir(parents=True); context.write_bytes(b'original-native-context')
        boundary = self.runner.run.side_effect
        def dispatch(command):
            if command.mutating and command.argv[:2] in [('kind','delete'), ('colima','stop')]:
                self.assertEqual((self.store.path / 'runtime-docker-context-meta.json').read_bytes(), b'original-native-context')
                self.assertTrue((self.store.path / 'runtime-observations.json').exists())
            if command.argv[:2] == ('colima','stop'): context.unlink()
            return boundary(command)
        self.runner.run.side_effect = dispatch
        with patch.object(self.native,'snapshot_runtime',wraps=self.native.snapshot_runtime) as snapshot:
            report = self.execute_fake()
        self.assertEqual(snapshot.call_count,1)
        self.assertEqual(report['status'], 'complete', report['error'])
        for line in (self.store.path / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ', 1)
            self.assertEqual(sha256((self.store.path / name).read_bytes()).hexdigest(), digest)
        ledger = json.loads((self.store.path / 'runtime-observations.json').read_bytes())
        self.assertEqual(next(row for row in ledger['files'] if row['runtime_path'] == str(self.life.runtime.kubeconfig))['presence'], 'absent')

    def test_snapshot_persistence_failure_denies_all_teardown_and_preserves_partial(self):
        self.full_fake_runner()
        write = self.store.write
        def failing(name, payload):
            if name == 'runtime-observations.json': raise OSError('snapshot persist failed')
            return write(name, payload)
        with patch.object(self.store, 'write', side_effect=failing): report = self.execute_fake()
        self.assertEqual(report['status'], 'inconclusive')
        self.assertTrue(report['manual_recovery'])
        self.assertFalse(any(command.argv[:2] in [('kind','delete'), ('colima','stop'), ('colima','delete')] for command in self.state['calls']))
        self.assertTrue((self.store.path / 'runtime-kind-config.yaml').exists())
        self.assertIsNotNone(report['runtime_leftovers'])
        partial = (self.store.path / 'runtime-kind-config.yaml').read_bytes()
        self.life.cleanup()
        self.assertEqual((self.store.path / 'runtime-kind-config.yaml').read_bytes(),partial)
        self.assertIn('no_retry',self.life.error)

    def test_default_network_directory_is_not_a_configuration_commitment(self):
        self.full_fake_runner()
        networks = self.life.default_paths.lima / '_config/networks.yaml'
        networks.mkdir(parents=True)
        with self.assertRaises(ValueError): self.life.foreign_snapshot()

    def test_unknown_private_profile_directory_cannot_authorize_start(self):
        self.full_fake_runner()
        (self.life.paths.colima / 'foreign-profile').mkdir()
        report = self.execute_fake()
        self.assertEqual(report['status'], 'inconclusive')
        self.assertFalse(self.life.profile_attempted)
        self.assertFalse(any(command.mutating for command in self.state['calls']))

    def test_foreign_guard_failure_does_not_latch_kind_attempt(self):
        self.full_fake_runner()
        self.life.prepare()
        with patch.object(self.life,'guard_profile'), patch.object(self.life,'endpoint_rows',return_value=[]), patch.object(self.life,'require_foreign_preserved',side_effect=ValueError('foreign drift')):
            with self.assertRaises(ValueError): self.life.observe(kind_create_command(self.life.identity))
        self.assertFalse(self.life.cluster_attempted)
        self.assertFalse(any(command.mutating for command in self.state['calls']))

    def test_private_reserved_roster_and_native_network_inode_reset_are_allowed(self):
        self.full_fake_runner()
        networks = self.life.paths.lima / '_networks'
        networks.mkdir()
        original = networks.stat().st_ino
        boundary = self.runner.run.side_effect
        def dispatch(command):
            if command.argv[:2] == ('colima','start'):
                networks.rename(networks.with_name('_original-networks'))
                networks.mkdir()
                networks.with_name('_original-networks').rmdir()
            return boundary(command)
        self.runner.run.side_effect = dispatch
        report = self.execute_fake()
        self.assertEqual(report['status'], 'complete', report['error'])
        self.assertNotEqual(networks.stat().st_ino, original)
        self.assertTrue(report['owned_teardown'])

    def test_default_network_reset_after_start_refuses_all_later_mutations(self):
        self.full_fake_runner()
        networks = self.life.default_paths.lima / '_config/networks.yaml'
        networks.parent.mkdir(parents=True); networks.write_bytes(b'original-default-networks')
        boundary = self.runner.run.side_effect
        def dispatch(command):
            result = boundary(command)
            if command.argv[:2] == ('colima','start'):
                networks.rename(networks.with_name('original.yaml'))
                networks.write_bytes(b'original-default-networks')
            return result
        self.runner.run.side_effect = dispatch
        report = self.execute_fake()
        self.assertEqual(report['status'], 'inconclusive')
        self.assertTrue(report['manual_recovery'])
        mutations = [command for command in self.state['calls'] if command.mutating]
        self.assertEqual([command.argv[:2] for command in mutations],[('colima','start')])

    def test_foreign_read_mid_observation_substitutions_are_detected(self):
        self.full_fake_runner()
        docker = self.home / '.docker/config.json'
        docker.parent.mkdir(); docker.write_bytes(b'original')
        boundary = self.runner.run.side_effect
        def dispatch(command):
            if command.argv == ('docker','context','show'):
                docker.rename(docker.with_name('retained-original.json')); docker.write_bytes(b'original')
            return boundary(command)
        self.runner.run.side_effect = dispatch
        with self.assertRaises(ValueError): self.life.foreign_snapshot()

    def test_inherited_kubeconfig_retains_eight_mib_budget_and_identity(self):
        path = self.home / 'inherited-kubeconfig'; path.write_bytes(b'x' * 70000)
        with patch.dict(os.environ,{'KUBECONFIG':str(path)}):
            first = self.life.kubeconfig_fingerprint()
            self.assertEqual(first['files'][0]['byte_count'],70000)
            path.rename(path.with_name('retained-original-kubeconfig')); path.write_bytes(b'x' * 70000)
            self.assertNotEqual(self.life.kubeconfig_fingerprint(),first)

    def test_constructor_bind_exception_releases_every_runtime_descriptor(self):
        self.life.close(); self.store.close()
        parent = self.store.path.parent
        store = PrivateStore(parent / ('hf-exploratory-' + '2' * 64))
        self.addCleanup(store.close)
        inputs = SimpleNamespace(workload=SimpleNamespace(run_id='v3b2-'+'2'*64))
        before = len(os.listdir('/dev/fd'))
        with patch.object(self.native.ProfilePaths,'bind',side_effect=ValueError('late bind failure')):
            with self.assertRaises(ValueError):
                self.native.ExploratoryLifecycle(self.root,inputs,store,self.runner,COMMIT,'rehearsal')
        self.assertEqual(len(os.listdir('/dev/fd')),before)

    def test_unbound_partial_setup_snapshots_observations_without_adoption(self):
        self.full_fake_runner()
        boundary = self.runner.run.side_effect
        def dispatch(command):
            result = boundary(command)
            if command.argv[:2] == ('colima','start'):
                (self.life.paths.instance / 'colima.yaml').write_bytes(b'unknown-native-configuration')
            return result
        self.runner.run.side_effect = dispatch
        report = self.execute_fake()
        self.assertEqual(report['status'],'inconclusive')
        self.assertTrue(report['manual_recovery'])
        self.assertEqual((self.store.path/'runtime-instance-colima.yaml').read_bytes(),b'unknown-native-configuration')
        self.assertFalse(any(command.argv[:2] in [('kind','delete'),('colima','stop'),('colima','delete')] for command in self.state['calls']))

    def test_ordinary_read_namespace_drift_during_intent_never_dispatches(self):
        record = self.store.record
        def drift(event, details):
            record(event, details)
            if event == 'command_intent':
                self.life.runtime.tmp.rename(self.life.runtime.tmp.with_name('retained-tmp'))
                self.life.runtime.tmp.mkdir(mode=0o700)
        with patch.object(self.store,'record',side_effect=drift):
            with self.assertRaises(ValueError): self.life.observe(Command(('limactl','--version'),10))
        self.runner.run.assert_not_called()
        self.assertEqual(json.loads(self.store.journal.read_bytes().splitlines()[-1])['event'],'command_intent')

    def test_missing_symlink_and_replaced_namespace_reject_version_dispatch(self):
        path = self.life.runtime.tmp
        retained = path.with_name('retained-runtime-tmp')
        for kind in ['missing','symlink','replaced']:
            with self.subTest(kind=kind):
                path.rename(retained)
                if kind=='symlink': path.symlink_to(retained,target_is_directory=True)
                if kind=='replaced': path.mkdir(mode=0o700)
                try:
                    with self.assertRaises(ValueError): self.life.observe(Command(('colima','version'),10))
                    self.runner.run.assert_not_called()
                finally:
                    if kind=='symlink': path.unlink()
                    if kind=='replaced': path.rmdir()
                    retained.rename(path)

    def test_foreign_adapter_and_subclass_are_refused_before_runner(self):
        from kil.hf_exploratory_runtime import RuntimeAuthority, ExploratoryColimaCommand
        store = PrivateStore(self.store.path.parent/('hf-exploratory-'+'2'*64))
        self.addCleanup(store.close)
        authority = RuntimeAuthority.create(store,'2'*64); self.addCleanup(authority.close)
        with self.assertRaises(ValueError):
            self.life.observe(ExploratoryColimaCommand(Command(('colima','version'),10),authority))
        class DerivedCommand(Command): pass
        with self.assertRaises(ValueError): self.life.observe(DerivedCommand(('colima','version'),10))
        self.runner.run.assert_not_called()

    def test_real_lifecycle_kind_control_substitution_refuses_create_not_owned_cleanup(self):
        self.full_fake_runner()
        boundary = self.runner.run.side_effect
        def dispatch(command):
            result = boundary(command)
            if command.argv[:2]==('colima','start'):
                original = self.life.runtime.kind_config
                original.rename(original.with_name('retained-original-kind-config'))
                original.write_bytes((self.store.path/'kind-config.yaml').read_bytes())
            return result
        self.runner.run.side_effect = dispatch
        report = self.execute_fake()
        self.assertEqual(report['status'],'inconclusive')
        self.assertIn('kind_runtime_control_changed',report['error'])
        self.assertFalse(self.life.cluster_attempted)
        self.assertFalse(any(command.argv[:2]==('kind','create') for command in self.state['calls']))
        self.assertTrue(report['owned_teardown'])
        config = json.loads((self.store.path/'kind-config.yaml').read_bytes())
        self.assertEqual(config['nodes'],[{'role':'control-plane','image':self.inputs.profile.kind_node_image}])

    def test_private_incomplete_roster_after_start_preserves_manual_owned_vm(self):
        self.full_fake_runner()
        boundary = self.runner.run.side_effect
        def dispatch(command):
            result = boundary(command)
            if command.argv[:2]==('colima','start'):
                (self.life.paths.lima/'colima-extra').mkdir()
            return result
        self.runner.run.side_effect=dispatch
        report = self.execute_fake()
        self.assertEqual(report['status'],'inconclusive')
        self.assertTrue(report['manual_recovery'])
        self.assertEqual([command.argv[:2] for command in self.state['calls'] if command.mutating],[('colima','start')])
        self.assertTrue(self.life.paths.instance.exists())

    def test_snapshot_capture_failure_blocks_teardown_with_bounded_leftovers(self):
        self.full_fake_runner()
        boundary = self.runner.run.side_effect
        def dispatch(command):
            result = boundary(command)
            if command.argv[:2]==('colima','start'):
                (self.life.runtime.docker_config/'config.json').symlink_to(self.home/'foreign-config.json')
            return result
        self.runner.run.side_effect=dispatch
        report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive')
        self.assertTrue(report['manual_recovery'])
        self.assertIn('runtime snapshot',report['error'])
        self.assertFalse(any(command.argv[:2] in [('kind','delete'),('colima','stop'),('colima','delete')] for command in self.state['calls']))
        self.assertIsNone(report['runtime_observations'])
        self.assertIsNotNone(report['runtime_leftovers'])

    def test_namespace_drift_after_native_cleanup_reports_unknown_not_absence(self):
        self.full_fake_runner()
        boundary=self.runner.run.side_effect
        def dispatch(command):
            result=boundary(command)
            if command.argv[:2]==('colima','delete'):
                self.life.runtime.tmp.rename(self.life.runtime.tmp.with_name('retained-original-tmp'))
                self.life.runtime.tmp.mkdir(mode=0o700)
            return result
        self.runner.run.side_effect=dispatch
        report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive')
        self.assertIsNone(report['runtime_leftovers'])
        self.assertIsNotNone(report['runtime_leftovers_error'])
        self.assertIn('runtime leftovers unknown',report['error'])
        self.assertFalse(report['filesystem_fully_removed'])

    def test_start_namespace_drift_during_durable_intent_is_known_no_handoff(self):
        self.full_fake_runner()
        record = self.store.record
        def drift(event, details):
            record(event, details)
            if event=='command_intent' and details['argv'][:2]==['colima','start']:
                self.life.runtime.tmp.rename(self.life.runtime.tmp.with_name('retained-original-tmp'))
                self.life.runtime.tmp.mkdir(mode=0o700)
        with patch.object(self.store,'record',side_effect=drift): report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive')
        self.assertEqual([command for command in self.state['calls'] if command.mutating],[])
        self.assertFalse(self.life.profile_attempted)
        self.assertFalse(self.life.started_pristine)
        self.assertFalse(report['manual_recovery'])

    def test_kind_control_drift_during_durable_intent_is_known_no_create_handoff(self):
        self.full_fake_runner()
        record = self.store.record
        original = []
        def drift(event, details):
            record(event, details)
            if event=='command_intent' and details['argv'][:2]==['kind','create']:
                original.append((self.store.path/'kind-config.yaml').read_bytes())
                self.life.runtime.kind_config.write_bytes(b'changed-during-create-intent')
        with patch.object(self.store,'record',side_effect=drift): report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive')
        self.assertFalse(any(command.argv[:2]==('kind','create') for command in self.state['calls']))
        self.assertFalse(self.life.cluster_attempted)
        self.assertEqual((self.store.path/'kind-config.yaml').read_bytes(),original[0])
        self.assertTrue(report['owned_teardown'])
        self.assertFalse(report['manual_recovery'])

    def test_kind_namespace_drift_during_durable_intent_does_not_latch_create(self):
        self.full_fake_runner()
        record = self.store.record
        def drift(event, details):
            record(event, details)
            if event=='command_intent' and details['argv'][:2]==['kind','create']:
                self.life.runtime.tmp.rename(self.life.runtime.tmp.with_name('retained-original-tmp'))
                self.life.runtime.tmp.mkdir(mode=0o700)
        with patch.object(self.store,'record',side_effect=drift): report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive')
        self.assertFalse(any(command.argv[:2]==('kind','create') for command in self.state['calls']))
        self.assertFalse(self.life.cluster_attempted)
        self.assertTrue(self.life.profile_attempted)
        self.assertTrue(report['manual_recovery'])

    def test_valid_start_command_substitution_during_intent_never_authorizes_delete(self):
        self.full_fake_runner()
        command = self.native.colima_start_command()
        record = self.store.record
        def substitute(event, details):
            record(event, details)
            if event=='command_intent' and details['argv'][:2]==['colima','start']:
                object.__setattr__(command,'argv',('colima','delete','--profile','kil-v3-lab','--force','--data'))
        with patch.object(self.native,'colima_start_command',return_value=command), patch.object(self.store,'record',side_effect=substitute): report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive')
        self.assertEqual([row for row in self.state['calls'] if row.mutating],[])
        self.assertFalse(self.life.profile_attempted)
        self.assertFalse(self.life.profile_delete_attempted)
        self.assertFalse(report['manual_recovery'])

    def test_valid_start_command_substitution_during_nested_authorization_is_refused(self):
        self.full_fake_runner()
        command = self.native.colima_start_command()
        record = self.store.record
        changed = []
        scoped_reads = []
        def substitute(event, details):
            record(event, details)
            if event=='command_intent' and details['argv']==['colima','list','--json'] and details['env']:
                scoped_reads.append(True)
                if len(scoped_reads)==2 and not changed:
                    changed.append(True)
                    object.__setattr__(command,'argv',('colima','delete','--profile','kil-v3-lab','--force','--data'))
        with patch.object(self.native,'colima_start_command',return_value=command), patch.object(self.store,'record',side_effect=substitute): report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive')
        self.assertEqual([row for row in self.state['calls'] if row.mutating],[])
        self.assertFalse(self.life.profile_attempted)
        self.assertFalse(self.life.profile_delete_attempted)
        intents=[json.loads(line)['details'] for line in self.store.journal.read_bytes().splitlines()
                 if json.loads(line)['event']=='command_intent']
        self.assertFalse(any(row['mutating'] for row in intents))

    def test_valid_ordinary_kind_command_substitution_during_intent_is_refused(self):
        self.full_fake_runner()
        command = kind_create_command(self.life.identity)
        record = self.store.record
        def substitute(event, details):
            record(event, details)
            if event=='command_intent' and details['argv'][:2]==['kind','create']:
                object.__setattr__(command,'argv',kind_delete_command(self.life.identity).argv)
        with patch.object(self.native,'kind_create_command',return_value=command), patch.object(self.store,'record',side_effect=substitute): report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive')
        self.assertFalse(any(row.argv[:2] in [('kind','create'),('kind','delete')] for row in self.state['calls']))
        self.assertFalse(self.life.cluster_attempted)
        self.assertFalse(self.life.cluster_delete_attempted)
        self.assertTrue(report['owned_teardown'])

    def test_read_until_never_retries_command_schema_or_identity_error(self):
        for error_type in [ValueError,KeyError,TypeError]:
            operation=Mock(side_effect=[error_type('permanent'),True])
            with patch.object(self.native.time,'sleep'),self.assertRaises(error_type):
                self.life.read_until(operation)
            self.assertEqual(operation.call_count,1)

    def test_calico_nonzero_read_permanently_blocks_all_eof(self):
        state=self.full_fake_runner(); original=self.runner.run.side_effect; failed=False
        def once(command):
            nonlocal failed
            if command.argv[3:5]==('get','daemonset') and not failed:
                failed=True; state['calls'].append(command)
                return CommandResult(3,'','failed Calico read',b'',b'failed Calico read')
            return original(command)
        self.runner.run.side_effect=once; report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive'); self.assertEqual(state['attached'],[])
        self.assertTrue(report['owned_teardown'])

    def test_ready_authz_uid_replacement_is_not_adopted_on_inventory_retry(self):
        state=self.full_fake_runner(); original=self.runner.run.side_effect; changed=False
        authz=self.pods[(TRACKS[0],'authz')]
        def once(command):
            nonlocal changed
            result=original(command)
            if command.argv[3:6]==('get','pod',authz['metadata']['name']) and not changed:
                changed=True; replacement=deepcopy(authz); replacement['metadata']['uid']='ready-replacement'
                raw=canonical(replacement); return CommandResult(0,raw.decode(),'',raw,b'')
            return result
        self.runner.run.side_effect=once; report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive'); self.assertEqual(state['attached'],[])
        self.assertEqual(self.life.anchors[(TRACKS[0],'authz')]['uid'],authz['metadata']['uid'])

    def test_container_creating_uid_latch_refuses_later_ready_replacement(self):
        from kil.v3b2_proofs import RUNTIME_RESOURCES
        state=self.full_fake_runner(); original=self.runner.run.side_effect; wide=0
        def pending_then_replacement(command):
            nonlocal wide
            result=original(command)
            if command.argv[3:5]==('get',RUNTIME_RESOURCES):
                wide+=1; doc=json.loads(result.stdout_bytes)
                driver=next(row for row in doc['items'] if row['kind']=='Pod' and row['metadata'].get('namespace')=='kil-v3-baseline' and row['metadata']['name']=='driver')
                if wide==1:
                    driver['status']['phase']='Pending'; status=driver['status']['containerStatuses'][0]
                    status.update(ready=False,image=driver['spec']['containers'][0]['image'],imageID='',containerID='',state={'waiting':{'reason':'ContainerCreating'}})
                else: driver['metadata']['uid']='later-ready-replacement'
                raw=canonical(doc); return CommandResult(0,raw.decode(),'',raw,b'')
            return result
        self.runner.run.side_effect=pending_then_replacement; report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive'); self.assertEqual(state['attached'],[])
        self.assertEqual(wide,2)

    def test_container_creating_same_uid_eventually_becomes_ready(self):
        from kil.v3b2_proofs import RUNTIME_RESOURCES
        state=self.full_fake_runner(); original=self.runner.run.side_effect; wide=0
        def pending_once(command):
            nonlocal wide
            result=original(command)
            if command.argv[3:5]==('get',RUNTIME_RESOURCES):
                wide+=1
                if wide==1:
                    doc=json.loads(result.stdout_bytes)
                    driver=next(row for row in doc['items'] if row['kind']=='Pod' and row['metadata'].get('namespace')=='kil-v3-baseline' and row['metadata']['name']=='driver')
                    driver['status']['phase']='Pending'; status=driver['status']['containerStatuses'][0]
                    status.update(ready=False,image=driver['spec']['containers'][0]['image'],imageID='',containerID='',state={'waiting':{'reason':'ContainerCreating'}})
                    raw=canonical(doc); return CommandResult(0,raw.decode(),'',raw,b'')
            return result
        self.runner.run.side_effect=pending_once; report=self.execute_fake()
        self.assertEqual(report['status'],'complete'); self.assertEqual(len(state['attached']),3)
        self.assertEqual(wide,2)

    def test_setup_readiness_budget_deadline_survives_between_phases(self):
        self.assertTrue(hasattr(self.native,'SetupReadinessBudget'),'shared setup budget missing')
        clock=[100.0]
        with patch.object(self.native.time,'monotonic',side_effect=lambda:clock[0]):
            budget=self.native.SetupReadinessBudget()
            self.life.read_until(lambda deadline:deadline,budget=budget)
            clock[0]=401.0
            later=Mock()
            with self.assertRaises(ValueError): self.life.read_until(later,budget=budget)
        later.assert_not_called(); self.assertIsNone(self.life._read_deadline)

    def test_setup_readiness_budget_shared_sixty_attempts(self):
        self.assertTrue(hasattr(self.native,'SetupReadinessBudget'),'shared setup budget missing')
        with patch.object(self.native.time,'sleep'):
            budget=self.native.SetupReadinessBudget()
            first=Mock(side_effect=[self.native.ReadPending('valid pending')]*58+[True])
            self.life.read_until(first,budget=budget)
            self.life.read_until(lambda deadline:True,budget=budget)
            later=Mock()
            with self.assertRaises(ValueError): self.life.read_until(later,budget=budget)
        self.assertEqual(first.call_count,59); later.assert_not_called()

    def test_full_setup_shares_one_budget_across_three_phases(self):
        self.full_fake_runner(); original=self.life.read_until; budgets=[]
        def read(operation,**options):
            if options.get('seconds',300)==300: budgets.append(options.get('budget'))
            return original(operation,**options)
        with patch.object(self.life,'read_until',side_effect=read): report=self.execute_fake()
        self.assertEqual(report['status'],'complete'); self.assertEqual(len(budgets),3)
        self.assertIsNotNone(budgets[0]); self.assertTrue(all(value is budgets[0] for value in budgets))

    def test_native_nested_calico_projection_retains_raw_and_closed_readiness(self):
        self.full_fake_runner(); report=self.execute_fake()
        self.assertEqual(report['status'],'complete')
        projections=list(self.store.path.glob('calico-readiness-projection-*.json'))
        self.assertEqual(len(projections),2)
        from kil.v3b2_inventory import parse_calico_runtime_workload
        for path in projections:
            raw=path.read_bytes(); doc=json.loads(raw)
            parse_calico_runtime_workload(raw,doc['kind'])
            self.assertEqual(set(doc['spec']),{'containers','initContainers'})
            self.assertEqual(set(doc['metadata']),{'namespace','name','uid','resourceVersion'})
        native_receipts=[path.read_bytes() for path in self.store.path.glob('command-*.stdout')]
        self.assertTrue(any(b'NATIVE_EXTRA' in raw and b'"template"' in raw for raw in native_receipts))
        self.assertFalse(report['platform_image_provenance_verified'])

    def test_native_calico_valid_pending_counts_retry_but_wrong_image_does_not(self):
        state=self.full_fake_runner(); original=self.runner.run.side_effect; reads=0
        def pending_once(command):
            nonlocal reads
            result=original(command)
            if command.argv[3:5]==('get','daemonset'):
                reads+=1
                if reads==1:
                    doc=json.loads(result.stdout_bytes); doc['status']['numberReady']=0
                    raw=canonical(doc); return CommandResult(0,raw.decode(),'',raw,b'')
            return result
        self.runner.run.side_effect=pending_once; report=self.execute_fake()
        self.assertEqual(report['status'],'complete'); self.assertEqual(reads,2)

    def test_native_calico_wrong_image_pending_counts_hard_stop(self):
        state=self.full_fake_runner(); original=self.runner.run.side_effect; reads=0
        def wrong_image(command):
            nonlocal reads
            result=original(command)
            if command.argv[3:5]==('get','daemonset'):
                reads+=1; doc=json.loads(result.stdout_bytes); doc['status']['numberReady']=0
                doc['spec']['template']['spec']['containers'][0]['image']='unverified:latest'
                raw=canonical(doc); return CommandResult(0,raw.decode(),'',raw,b'')
            return result
        self.runner.run.side_effect=wrong_image; report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive'); self.assertEqual(reads,1); self.assertEqual(state['attached'],[])

    def test_application_known_pending_json_before_wait_then_ready(self):
        state=self.full_fake_runner(); original=self.runner.run.side_effect; reads=0
        def pending_once(command):
            nonlocal reads
            result=original(command)
            if command.argv[3:5]==('get','--filename'):
                desired=json.loads(command.stdin)['items']
                if len(desired)==1 and desired[0]['kind']=='Deployment':
                    reads+=1
                    if reads==1:
                        doc=json.loads(result.stdout_bytes); row=doc['items'][0]
                        row['status'].update(readyReplicas=0,availableReplicas=0)
                        row['status']['conditions'][0]['status']='False'
                        raw=canonical(doc); return CommandResult(0,raw.decode(),'',raw,b'')
            return result
        self.runner.run.side_effect=pending_once; report=self.execute_fake()
        self.assertEqual(report['status'],'complete'); self.assertEqual(reads,10)
        self.assertEqual(sum(command.argv[3:4]==('wait',) for command in state['calls']),9)

    def test_application_wait_failure_is_permanent(self):
        state=self.full_fake_runner(); original=self.runner.run.side_effect
        def fail_wait(command):
            if command.argv[3:4]==('wait',):
                state['calls'].append(command)
                return CommandResult(1,'','timed out waiting for the condition',b'',b'timed out waiting for the condition')
            return original(command)
        self.runner.run.side_effect=fail_wait; report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive'); self.assertEqual(state['attached'],[])
        self.assertEqual(sum(command.argv[3:4]==('wait',) for command in state['calls']),1)

    def test_calico_pending_uid_replacement_hard_stop(self):
        state=self.full_fake_runner(); original=self.runner.run.side_effect; reads=0
        def replacement(command):
            nonlocal reads
            result=original(command)
            if command.argv[3:5]==('get','daemonset'):
                reads+=1; doc=json.loads(result.stdout_bytes)
                if reads==1: doc['status']['numberReady']=0
                else: doc['metadata']['uid']='replacement-calico'
                raw=canonical(doc); return CommandResult(0,raw.decode(),'',raw,b'')
            return result
        self.runner.run.side_effect=replacement; report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive'); self.assertEqual(reads,2); self.assertEqual(state['attached'],[])

    def test_native_calico_malformed_counts_identity_inventory_never_pending(self):
        self.full_fake_runner()
        command=self.native.kubectl_calico_workload_command(self.life.identity,'DaemonSet')
        doc=json.loads(self.runner.run.side_effect(command).stdout_bytes)
        mutations=[lambda row:row['metadata'].update(uid=''),
            lambda row:row['metadata'].pop('resourceVersion'),
            lambda row:row['status'].update(numberReady=True),
            lambda row:row['status'].update(desiredNumberScheduled=0,numberReady=1),
            lambda row:row['status'].pop('numberReady'),
            lambda row:row['spec']['template']['spec']['containers'].append(deepcopy(row['spec']['template']['spec']['containers'][0])),
            lambda row:row['spec']['template']['spec'].update(initContainers=[]),
            lambda row:row['spec'].update(template=[])]
        for mutate in mutations:
            changed=deepcopy(doc); mutate(changed)
            try: self.native.calico_readiness_projection(canonical(changed),'DaemonSet')
            except (ValueError,KeyError,TypeError) as error:
                self.assertNotIsInstance(error,self.native.ReadPending)
            else: self.fail('malformed native Calico projection accepted')

    def test_endpoint_initial_binding_is_not_overwritten(self):
        self.install_pods(); pod=self.pods[(TRACKS[0],'authz')]
        def endpoint(uid):
            return canonical({'apiVersion':'discovery.k8s.io/v1','kind':'EndpointSlice',
                'metadata':{'name':'authz-slice','namespace':'kil-v3-baseline','labels':{'kubernetes.io/service-name':'authz'}},
                'addressType':'IPv4','ports':[{'name':'http','protocol':'TCP','port':8080}],
                'endpoints':[{'addresses':['10.244.0.2'],'conditions':{'ready':True},
                'targetRef':{'kind':'Pod','name':pod['metadata']['name'],'namespace':'kil-v3-baseline','uid':uid}}]})
        raws=[endpoint('initial'),endpoint('replacement')]
        self.runner.run.side_effect=[CommandResult(0,raw.decode(),'',raw,b'') for raw in raws]
        self.life.read_endpoint(TRACKS[0],'authz')
        with self.assertRaises(ValueError): self.life.read_endpoint(TRACKS[0],'authz')
        self.assertEqual(self.life.endpoint_bindings[(TRACKS[0],'authz')]['target_uid'],'initial')

    def test_native_calico_deployment_omitted_zero_counts_then_ready(self):
        self.full_fake_runner(); original=self.runner.run.side_effect; reads=0
        def omitted_once(command):
            nonlocal reads
            result=original(command)
            if command.argv[3:5]==('get','deployment'):
                reads+=1
                if reads==1:
                    doc=json.loads(result.stdout_bytes); doc['status']={}
                    raw=canonical(doc); return CommandResult(0,raw.decode(),'',raw,b'')
            return result
        self.runner.run.side_effect=omitted_once; report=self.execute_fake()
        self.assertEqual(report['status'],'complete'); self.assertEqual(reads,2)
        projections=[json.loads(path.read_bytes()) for path in self.store.path.glob('calico-readiness-projection-*.json')]
        self.assertTrue(any(row['kind']=='Deployment' and row['status']=={} for row in projections))

    def test_native_application_deployment_omitted_zero_startup_then_ready(self):
        self.full_fake_runner(); original=self.runner.run.side_effect; reads=0
        def omitted_once(command):
            nonlocal reads
            result=original(command)
            if command.argv[3:5]==('get','--filename'):
                desired=json.loads(command.stdin)['items']
                if len(desired)==1 and desired[0]['kind']=='Deployment':
                    reads+=1
                    if reads==1:
                        doc=json.loads(result.stdout_bytes); doc['items'][0]['status']={}
                        raw=canonical(doc); return CommandResult(0,raw.decode(),'',raw,b'')
            return result
        self.runner.run.side_effect=omitted_once; report=self.execute_fake()
        self.assertEqual(report['status'],'complete'); self.assertEqual(reads,10)

    def test_application_present_bad_count_and_pending_uid_replacement_hard_stop(self):
        self.full_fake_runner(); self.life.prepare()
        desired=next(row for row in self.life.groups[2] if row['kind']=='Deployment')
        raw=self.runner.run.side_effect(self.native.Command(('kubectl','--kubeconfig',self.life.identity.kubeconfig,
            'get','--filename','-','--output','json'),10,stdin=self.life.object_list([desired]))).stdout_bytes
        doc=json.loads(raw); track=next(track for track,ns in self.native.NAMESPACES.items() if ns==desired['metadata']['namespace']); role=desired['metadata']['name']
        bad=deepcopy(doc); bad['items'][0]['status']['readyReplicas']=True
        with patch.object(self.life,'applied_read',return_value=canonical(bad)),self.assertRaises(ValueError):
            self.life.require_deployment_available(track,role)
        pending=deepcopy(doc); pending['items'][0]['status']={}
        with patch.object(self.life,'applied_read',return_value=canonical(pending)),self.assertRaises(self.native.ReadPending):
            self.life.require_deployment_available(track,role)
        replacement=deepcopy(doc); replacement['items'][0]['metadata']['uid']='replacement'
        with patch.object(self.life,'applied_read',return_value=canonical(replacement)),self.assertRaises(ValueError):
            self.life.require_deployment_available(track,role)

    def test_full_setup_elapsed_policy_apply_consumes_global_deadline(self):
        state=self.full_fake_runner(); original=self.runner.run.side_effect; clock=[100.0]
        def elapsed_apply(command):
            result=original(command)
            if command.argv[3:5]==('apply','-f') and command.stdin:
                desired=json.loads(command.stdin)['items']
                if desired and desired[0]['kind']=='Namespace': clock[0]=401.0
            return result
        self.runner.run.side_effect=elapsed_apply
        with patch.object(self.native.time,'monotonic',side_effect=lambda:clock[0]): report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive'); self.assertEqual(state['attached'],[])
        self.assertEqual(sum(command.argv[3:4]==('wait',) for command in state['calls']),0)
        self.assertTrue(report['owned_teardown'])

    def test_known_active_quiescence_gauge_retries_only_read(self):
        state=self.full_fake_runner(); original=self.runner.run.side_effect; stats=0
        def active_once(command):
            nonlocal stats
            result=original(command)
            if command.argv[3:4]==('exec',) and b'listener_refused' in result.stdout_bytes:
                stats+=1
                if stats==1:
                    doc=json.loads(result.stdout_bytes); doc['stats'][0]['value']=1
                    raw=canonical(doc); return CommandResult(0,raw.decode(),'',raw,b'')
            return result
        self.runner.run.side_effect=active_once; report=self.execute_fake()
        self.assertEqual(report['status'],'complete'); self.assertEqual(stats,4)
        self.assertEqual(len(state['drained']),3)

    def test_pending_driver_does_not_hide_other_initial_container_identity(self):
        from kil.v3b2_proofs import RUNTIME_RESOURCES
        state=self.full_fake_runner(); original=self.runner.run.side_effect; wide=0
        authz=self.pods[(TRACKS[0],'authz')]; initial=authz['status']['containerStatuses'][0]['containerID']
        def drift_after_pending(command):
            nonlocal wide
            if command.argv[3:5]==('get',RUNTIME_RESOURCES):
                wide+=1
                if wide==2: authz['status']['containerStatuses'][0]['containerID']='containerd://'+'e'*64
            result=original(command)
            if command.argv[3:5]==('get',RUNTIME_RESOURCES) and wide==1:
                doc=json.loads(result.stdout_bytes)
                driver=next(row for row in doc['items'] if row['kind']=='Pod' and row['metadata'].get('namespace')=='kil-v3-baseline' and row['metadata']['name']=='driver')
                driver['status']['phase']='Pending'; status=driver['status']['containerStatuses'][0]
                status.update(ready=False,image=driver['spec']['containers'][0]['image'],imageID='',containerID='',state={'waiting':{'reason':'ContainerCreating'}})
                raw=canonical(doc); return CommandResult(0,raw.decode(),'',raw,b'')
            return result
        self.runner.run.side_effect=drift_after_pending; report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive'); self.assertEqual(state['attached'],[])
        self.assertEqual(self.life.anchors[(TRACKS[0],'authz')]['container_id'],initial)

    def test_action_coherent_wide_deployment_uid_replacement_stops_before_intent(self):
        from kil.v3b2_proofs import RUNTIME_RESOURCES
        self.life.mode='action'; state=self.full_fake_runner(); original=self.runner.run.side_effect; wide=0
        def replacement(command):
            nonlocal wide
            result=original(command)
            if command.argv[3:5]==('get',RUNTIME_RESOURCES):
                wide+=1; doc=json.loads(result.stdout_bytes)
                deployment=next(row for row in doc['items'] if row['kind']=='Deployment'
                    and row['metadata'].get('namespace')=='kil-v3-baseline' and row['metadata']['name']=='authz')
                old_uid=deployment['metadata']['uid']; deployment['metadata']['uid']='replacement-deployment'
                for row in doc['items']:
                    if row['kind']=='ReplicaSet':
                        for owner in row['metadata'].get('ownerReferences',[]):
                            if owner['uid']==old_uid: owner['uid']='replacement-deployment'
                raw=canonical(doc); return CommandResult(0,raw.decode(),'',raw,b'')
            return result
        self.runner.run.side_effect=replacement; report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive'); self.assertEqual(report['request_intent_count'],0)
        self.assertEqual(state['attached'],[]); self.assertEqual(report['joined_results'],[])
        self.assertEqual(wide,1); self.assertTrue(report['owned_teardown'])

    def test_action_applied_deployment_uid_replacement_stops_before_intent(self):
        self.life.mode='action'; state=self.full_fake_runner(); original=self.runner.run.side_effect
        def replacement(command):
            result=original(command)
            if command.argv[3:5]==('get','--filename'):
                desired=json.loads(command.stdin)['items']
                if len(desired)>1 and any(row['kind']=='Deployment' for row in desired):
                    doc=json.loads(result.stdout_bytes)
                    deployment=next(row for row in doc['items'] if row['kind']=='Deployment')
                    deployment['metadata']['uid']='replacement-applied-deployment'
                    raw=canonical(doc); return CommandResult(0,raw.decode(),'',raw,b'')
            return result
        self.runner.run.side_effect=replacement; report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive'); self.assertEqual(report['request_intent_count'],0)
        self.assertEqual(state['attached'],[]); self.assertTrue(report['owned_teardown'])

    def test_action_wide_deployment_generation_drift_stops_before_intent(self):
        from kil.v3b2_proofs import RUNTIME_RESOURCES
        self.life.mode='action'; state=self.full_fake_runner(); original=self.runner.run.side_effect
        def replacement(command):
            result=original(command)
            if command.argv[3:5]==('get',RUNTIME_RESOURCES):
                doc=json.loads(result.stdout_bytes)
                deployment=next(row for row in doc['items'] if row['kind']=='Deployment'
                    and row['metadata'].get('namespace') in self.native.NAMESPACES.values())
                deployment['metadata']['generation']=2
                raw=canonical(doc); return CommandResult(0,raw.decode(),'',raw,b'')
            return result
        self.runner.run.side_effect=replacement; report=self.execute_fake()
        self.assertEqual(report['status'],'inconclusive'); self.assertEqual(report['request_intent_count'],0)
        self.assertEqual(state['attached'],[]); self.assertTrue(report['owned_teardown'])

    def test_deployment_continuity_checks_all_nine_and_rejects_missing_bad_identity(self):
        self.assertTrue(hasattr(self.life,'require_deployment_continuity'),'continuity check missing')
        items=[]
        for track in TRACKS:
            for role in ('authz','envoy','target'):
                uid=track+'-'+role; self.life.deployment_bindings[(track,role)]=(uid,1)
                items.append({'apiVersion':'apps/v1','kind':'Deployment','metadata':{
                    'namespace':self.native.NAMESPACES[track],'name':role,'uid':uid,'generation':1}})
        document={'apiVersion':'v1','kind':'List','items':items}
        self.life.require_deployment_continuity(canonical(document))
        for index in range(9):
            for field,value in [('uid','replacement'),('generation',2),('generation',True),('generation','1'),('uid',''),('uid',True)]:
                changed=deepcopy(document); changed['items'][index]['metadata'][field]=value
                with self.assertRaises(ValueError): self.life.require_deployment_continuity(canonical(changed))
        for field in ('uid','generation'):
            changed=deepcopy(document); changed['items'][-1]['metadata'].pop(field)
            with self.assertRaises(ValueError): self.life.require_deployment_continuity(canonical(changed))
        for items in [document['items'][:-1],document['items']+[deepcopy(document['items'][0])]]:
            with self.assertRaises(ValueError):
                self.life.require_deployment_continuity(canonical({'apiVersion':'v1','kind':'List','items':items}))


class MissingIntegrationTests(unittest.TestCase):
    def test_native_integration_exists(self):
        self.assertIsNotNone(importlib.util.find_spec('kil.hf_exploratory_native'),
                             'native exploratory module is missing')

    def test_cli_integration_exists(self):
        self.assertTrue((Path(__file__).resolve().parents[1] / 'tools/hf_exploratory_kind.py').is_file(),
                        'native exploratory CLI is missing')


class CLITests(unittest.TestCase):
    def setUp(self):
        cli_path = Path(__file__).resolve().parents[1]/'tools/hf_exploratory_kind.py'
        self.assertTrue(cli_path.is_file(), 'native exploratory CLI is missing')
        spec = importlib.util.spec_from_file_location('hf_exploratory_kind_tests', cli_path)
        self.cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.cli)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.argv = ['--reviewed-source',COMMIT,'--tools',str(self.root/'.tools/bin'),
                     '--kil-archive',str(self.root/'archive')]

    def test_dirty_source_checked_before_any_private_path(self):
        with patch.object(self.cli,'check_source',side_effect=ValueError('dirty')):
            with self.assertRaises(ValueError): self.cli.main(self.argv, repository=self.root)
        self.assertFalse((self.root/'.tools').exists())

    def test_invalid_flags_or_relative_inputs_never_create_private_path(self):
        for extra in [['--resume'], ['--action-only'], ['--retry'], ['--provenance-override']]:
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit): self.cli.main(self.argv+extra, repository=self.root)
        relative = list(self.argv); relative[3]='relative'
        with self.assertRaises(ValueError): self.cli.main(relative, repository=self.root)
        self.assertFalse((self.root/'.tools').exists())

    def test_lock_conflict_and_parent_replacement_fail_with_fd_cleanup(self):
        with self.cli.LabLock(self.root) as lock:
            before = len(os.listdir('/dev/fd'))
            with self.assertRaises(BlockingIOError):
                with self.cli.LabLock(self.root): pass
            self.assertEqual(len(os.listdir('/dev/fd')), before)
            lock.path.rename(lock.path.with_name('retained-original'))
            lock.path.mkdir(mode=0o700)
            with self.assertRaises(ValueError): lock.guard()

    def test_private_parent_creation_is_durable_and_preserves_tools_mode(self):
        (self.root/'.tools').mkdir(mode=0o755)
        original = (self.root/'.tools').stat().st_mode & 0o777
        with patch.object(self.cli.os,'fsync',wraps=os.fsync) as synced:
            with self.cli.LabLock(self.root) as lock:
                self.assertEqual(lock.path.stat().st_mode & 0o777, 0o700)
                self.assertEqual((lock.path/'profile.lock').stat().st_mode & 0o777, 0o600)
                self.assertGreaterEqual(synced.call_count, 2)
        self.assertEqual((self.root/'.tools').stat().st_mode & 0o777, original)

    def test_unready_rehearsal_or_inexact_teardown_never_creates_action(self):
        for report in [{'status':'inconclusive','owned_teardown':True}, {'status':'complete','owned_teardown':False}, {'status':'complete','owned_teardown':1}]:
            with patch.object(self.cli,'check_source'), patch.object(self.cli,'verify_inputs',return_value=SimpleNamespace()) as inputs, patch.object(self.cli,'BoundedRunner'), patch.object(self.cli,'ExploratoryLifecycle') as lifecycle:
                lifecycle.return_value.execute.return_value = report
                with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit): self.cli.main(self.argv, repository=self.root)
            self.assertEqual(inputs.call_count,1); self.assertEqual(lifecycle.call_count,1)

    def test_two_fresh_modes_rebind_inputs_under_one_lock(self):
        seen = []
        def lifecycle(repo, inputs, store, runner, commit, mode):
            seen.append((store.path, mode))
            return SimpleNamespace(execute=lambda:{'status':'complete','owned_teardown':True}, close=lambda:None)
        with patch.object(self.cli,'check_source') as source, patch.object(self.cli,'verify_inputs',return_value=SimpleNamespace()) as inputs, patch.object(self.cli,'BoundedRunner'), patch.object(self.cli,'ExploratoryLifecycle',side_effect=lifecycle):
            with redirect_stdout(io.StringIO()): self.assertEqual(self.cli.main(self.argv, repository=self.root),0)
        self.assertEqual([mode for _,mode in seen],['rehearsal','action'])
        self.assertNotEqual(seen[0][0],seen[1][0]); self.assertEqual(inputs.call_count,2)
        self.assertGreaterEqual(source.call_count,3)

    def test_execution_and_close_failures_still_close_lifecycle_before_store(self):
        events = []
        def execute():
            events.append('execute'); raise OSError('execution failed')
        def close():
            events.append('lifecycle-close'); raise OSError('close failed')
        original = self.cli.PrivateStore.close
        def store_close(store):
            events.append('store-close'); original(store)
        with patch.object(self.cli,'check_source'), patch.object(self.cli,'verify_inputs',return_value=SimpleNamespace()), patch.object(self.cli,'BoundedRunner'), patch.object(self.cli,'ExploratoryLifecycle',return_value=SimpleNamespace(execute=execute,close=close)), patch.object(self.cli.PrivateStore,'close',store_close):
            with self.assertRaises(OSError): self.cli.main(self.argv,repository=self.root)
        self.assertEqual(events,['execute','lifecycle-close','store-close'])


if __name__ == '__main__':
    unittest.main()
