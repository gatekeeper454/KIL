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


def node():
    return [{'Id': 'b' * 64, 'Name': '/kil-v3-lab-control-plane',
             'Config': {'Labels': {'io.x-k8s.kind.cluster': 'kil-v3-lab',
                                   'io.x-k8s.kind.role': 'control-plane'}}, 'State': {'Running': True}}]


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('kil.hf_exploratory_native'),
                             'native exploratory module is missing')
        self.native = importlib.import_module('kil.hf_exploratory_native')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / 'home'
        self.home.mkdir()
        self.store = PrivateStore(self.root / 'run')
        self.addCleanup(self.store.close)
        from tests.test_v3b2_driver_pod_configuration import PROFILE, WORKLOAD
        self.inputs = SimpleNamespace(profile=PROFILE, workload=WORKLOAD,
            profile_bytes=b'profile', manifest_bytes=b'manifest', archive=b'archive',
            tools=self.root / '.tools/bin', tool_records={})
        self.runner = Mock()
        self.runner.run.return_value = CommandResult(0, 'out', '', b'out', b'')
        with patch.object(self.native.ProfilePaths, 'bind', return_value=self.native.ProfilePaths(self.home, self.store.path)):
            self.life = self.native.ExploratoryLifecycle(self.root, self.inputs, self.store,
                                                       self.runner, COMMIT, 'rehearsal')

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
        self.runner.run.side_effect = OSError('uncertain')
        with patch.object(self.life, 'guard_profile'), patch.object(self.life, 'endpoint_rows', return_value=[]):
            for _ in range(2):
                with self.assertRaises((OSError, ValueError)):
                    self.life.observe(kind_create_command(self.life.identity))
        self.assertEqual(self.runner.run.call_count, 1)
        self.assertTrue(self.life.cluster_attempted)

    def test_other_mutation_commitment_replay_is_refused(self):
        from kil.v3b2_manifests import render_objects
        namespaces=[row for row in json.loads(render_objects(self.inputs.profile,self.inputs.workload))['items'] if row['kind']=='Namespace']
        command = kubectl_apply_command(self.life.identity, canonical({'apiVersion':'v1','kind':'List','items':namespaces}))
        with patch.object(self.life, 'guard_cluster'):
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
        from tests.test_v3b2_profile_state import create_profile
        create_profile(self.life.paths)
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
            self.assertEqual((self.store.path/name).stat().st_mode & 0o777, 0o700)

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
                   b'colima version 0.10.3\ngit commit: abc1234\n', b'limactl version 2.2.0\n']
        with patch.object(self.native.platform, 'system', return_value='Darwin'), patch.object(self.native.platform, 'machine', return_value='arm64'), patch.object(self.life, 'observe', side_effect=[CommandResult(0,p.decode(),'',p,b'') for p in outputs]):
            self.life.verify_versions()
        self.assertEqual(self.life.environment['docker_daemon_version'], 'UNOBSERVED')
        with patch.object(self.native.platform, 'system', return_value='Linux'):
            with self.assertRaises(ValueError): self.life.verify_versions()

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
        from tests.test_v3b2_profile_state import create_profile
        from kil.v3b2_manifests import WorkloadIdentity
        accepted = {row.role:row for row in self.native.ACCEPTED_IMAGES}
        self.inputs.workload = WorkloadIdentity('v3b2-'+'1'*64,accepted['kil'].target_digest,accepted['envoy'].requested_image)
        self.inputs.tools.mkdir(parents=True)
        self.inputs.tool_records = {name:{'version_output':'fixture-'+name} for name in ['docker','kind','kubectl']}
        self.life.repository = Path(__file__).resolve().parents[1]
        self.life.runner.global_docker_config = str(self.home/'.docker')
        identity = replace(self.life.identity,node_container_id='b'*64,cluster_incarnation_uid='cluster-uid')
        args = generated_fixture(profile=self.inputs.profile,workload=self.inputs.workload,owned_identity=identity)
        runtime = json.loads(args['runtime_objects'])
        drivers = driver_fixture(profile=self.inputs.profile,workload=self.inputs.workload,owned_identity=identity)['pods']
        runtime['items'] = [row for row in runtime['items'] if not(row['kind']=='Pod' and row['metadata']['name']=='driver')] + drivers
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
        self.life.paths.lima.mkdir(parents=True); (self.life.paths.lima/'_disks').mkdir()
        self.state = {'profile':False,'cluster':False,'attached':[],'drained':[],'requests':{},'calls':[]}
        services = service_fixture(profile=self.inputs.profile,workload=self.inputs.workload)[3]
        service_map = {(row['metadata']['namespace'],row['metadata']['name']):row for row in services}
        def result(payload=b'',rc=0,stderr=b''):
            return CommandResult(rc,payload.decode('utf-8','replace'),stderr.decode('utf-8','replace'),payload,stderr)
        def dispatch(command):
            self.state['calls'].append(command)
            argv = command.argv; executable = Path(argv[0]).name
            if argv[0].startswith('/'):
                return result(('fixture-'+executable+'\n').encode())
            if argv==('colima','version'): return result(b'colima version 0.10.3\ngit commit: abc1234\n')
            if argv==('limactl','--version'): return result(b'limactl version 2.2.0\n')
            if argv==('docker','context','show'): return result(b'fixture-global\n')
            if argv==('colima','list','--json'):
                rows = [] if not self.state['profile'] else [{'name':'kil-v3-lab','status':'Stopped' if self.life.profile_stopped else 'Running',
                    'arch':'aarch64','runtime':'docker','cpus':4,'memory':8*1024**3,'disk':60*1024**3}]
                return result(b''.join(canonical(row) for row in rows))
            if executable=='colima' and argv[1]=='start':
                create_profile(self.life.paths); self.state['profile']=True; return result()
            if executable=='colima' and argv[1]=='stop':
                (self.life.paths.disk/'in_use_by').unlink(); return result()
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
        commands=[replace(self.native.colima_start_command(),env=self.life.colima_env),
                  Command(('colima','stop','--profile','kil-v3-lab'),10,env=self.life.colima_env,mutating=True),
                  Command(('colima','delete','--profile','kil-v3-lab','--force','--data'),10,env=self.life.colima_env,mutating=True)]
        self.runner.run.side_effect=OSError('uncertain')
        self.life.profile_stopped=True
        with patch.object(self.native,'check_source'), patch.object(self.life,'require_foreign_preserved'), patch.object(self.life,'guard_profile'):
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
            return SimpleNamespace(execute=lambda:{'status':'complete','owned_teardown':True})
        with patch.object(self.cli,'check_source') as source, patch.object(self.cli,'verify_inputs',return_value=SimpleNamespace()) as inputs, patch.object(self.cli,'BoundedRunner'), patch.object(self.cli,'ExploratoryLifecycle',side_effect=lifecycle):
            with redirect_stdout(io.StringIO()): self.assertEqual(self.cli.main(self.argv, repository=self.root),0)
        self.assertEqual([mode for _,mode in seen],['rehearsal','action'])
        self.assertNotEqual(seen[0][0],seen[1][0]); self.assertEqual(inputs.call_count,2)
        self.assertGreaterEqual(source.call_count,3)


if __name__ == '__main__':
    unittest.main()
