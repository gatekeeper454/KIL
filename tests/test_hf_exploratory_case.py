import importlib
import importlib.util
import unittest
from copy import deepcopy
from hashlib import sha256

from kil.v3b2_contracts import TRACKS
from kil.v3b1_driver_protocol import parse_instruction


class PureCaseTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('kil.hf_exploratory_case'))
        self.case = importlib.import_module('kil.hf_exploratory_case')

    def test_instruction(self):
        for track in TRACKS:
            row = parse_instruction(self.case.instruction(track, 'a' * 64, 100), expected_track=track)
            self.assertEqual((row['method'], row['path'], row['body_byte_count']), ('POST', '/consequential/admin', 0))
            self.assertEqual(row['headers']['authorization'], 'Bearer v3b1-lab-credential')
            self.assertEqual(row['headers']['x-envoy-max-retries'], '0')
            self.assertEqual(row['headers']['x-kil-run-id'], 'v3b1-' + 'a' * 64)
            self.assertEqual('x-kil-q-state' in row['headers'], track != TRACKS[0])
        for args in [('foreign', 'a' * 64, 100), (TRACKS[0], 'A' * 64, 100), (TRACKS[0], 'a' * 64, True)]:
            with self.assertRaises(ValueError):
                self.case.instruction(*args)

    def test_records(self):
        self.assertEqual(self.case.records(b''), [])
        self.assertEqual(self.case.records(b'{"x":1}\n'), [{'x': 1}])
        for payload in [b'{}', b'{}\n{}\n', b'[]\n', b'{"x":1,"x":2}\n', b'plaintext\n', b'a' * 1048576, b'\n']:
            with self.assertRaises(ValueError):
                self.case.records(payload)

    def test_frozen_source(self):
        identity = {'uid': 'pod1', 'container_id': 'containerd://' + 'a' * 64, 'resource_version': '1'}
        payload = b'{"x":1}\n'
        result = self.case.frozen_source(identity, dict(identity), payload, payload)
        self.assertEqual(result, {'identity': identity, 'byte_count': len(payload), 'sha256': sha256(payload).hexdigest(), 'records': [{'x': 1}]})
        for key in identity:
            after = {**identity, key: 'changed'}
            with self.assertRaises(ValueError):
                self.case.frozen_source(identity, after, payload, payload)
        with self.assertRaises(ValueError):
            self.case.frozen_source(identity, identity, payload, b'')

    def test_records_rejects_cr_framing(self):
        for payload in [b'{"x":1}\r{"x":2}\n', b'{}\r\n']:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.case.records(payload)

    def test_frozen_source_requires_complete_identity(self):
        complete = {'uid': 'pod1', 'container_id': 'containerd://' + 'a' * 64, 'resource_version': '1'}
        invalid = [{}]
        for key in complete:
            invalid.append({field: value for field, value in complete.items() if field != key})
            for value in ['', None, 1]:
                invalid.append({**complete, key: value})
        for identity in invalid:
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                self.case.frozen_source(identity, dict(identity), b'{}\n', b'{}\n')
            for before, after in [(identity, complete), (complete, identity)]:
                with self.assertRaises(ValueError):
                    self.case.frozen_source(before, after, b'{}\n', b'{}\n')

    def test_binding(self):
        self.assertTrue(hasattr(self.case, 'bind_pod'))
        args = dict(track=TRACKS[0], role='driver', run_id='v3b2-' + 'a' * 64,
                    requested_image='kil.local/kil-v3b2:sha256-' + 'b' * 64,
                    runtime_image='kil.local/kil-v3b2:sha256-' + 'b' * 64, image_ref='sha256:' + 'c' * 64)
        pod = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': 'driver', 'namespace': 'kil-v3-baseline',
            'uid': 'pod1', 'resourceVersion': '1', 'annotations': {'kil.dev/run-id': args['run_id']},
            'labels': {'kil.dev/track': TRACKS[0], 'kil.dev/role': 'driver', 'kil.dev/managed': 'v3b2'}},
            'spec': {'automountServiceAccountToken': False, 'containers': [{'name': 'driver', 'image': args['requested_image'],
            'imagePullPolicy': 'Never', 'securityContext': {'allowPrivilegeEscalation': False,
            'readOnlyRootFilesystem': True, 'runAsNonRoot': True, 'runAsUser': 65532, 'capabilities': {'drop': ['ALL']}}}]},
            'status': {'phase': 'Running', 'containerStatuses': [{'name': 'driver', 'image': args['runtime_image'],
            'imageID': args['image_ref'], 'ready': True, 'restartCount': 0, 'containerID': 'containerd://' + 'd' * 64,
            'state': {'running': {}}}]}}
        self.assertEqual(self.case.bind_pod(pod, **args)['image_ref'], args['image_ref'])
        with self.assertRaises(ValueError):
            self.case.bind_pod(pod, **{**args, 'image_ref': 'sha256:' + 'b' * 64})
        mutations = [(['metadata', 'namespace'], 'foreign'), (['metadata', 'deletionTimestamp'], 'now'),
            (['metadata', 'annotations', 'kil.dev/run-id'], 'foreign'), (['metadata', 'uid'], ''),
            (['spec', 'containers', 0, 'image'], 'foreign'), (['spec', 'hostNetwork'], True),
            (['spec', 'containers', 0, 'securityContext', 'privileged'], True),
            (['status', 'containerStatuses', 0, 'image'], 'foreign'),
            (['status', 'containerStatuses', 0, 'imageID'], 'sha256:' + 'b' * 64),
            (['status', 'containerStatuses', 0, 'restartCount'], 1),
            (['status', 'containerStatuses', 0, 'ready'], False),
            (['status', 'containerStatuses', 0, 'containerID'], 'containerd://bad')]
        for path, value in mutations:
            changed = deepcopy(pod)
            cursor = changed
            for key in path[:-1]:
                cursor = cursor[key]
            cursor[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.case.bind_pod(changed, **args)
        changed = deepcopy(pod)
        changed['spec']['containers'].append(deepcopy(changed['spec']['containers'][0]))
        with self.assertRaises(ValueError):
            self.case.bind_pod(changed, **args)
        for changed in [{}, {'apiVersion': 'v1', 'kind': 'Pod'}]:
            with self.assertRaises(ValueError):
                self.case.bind_pod(changed, **args)
        drained = deepcopy(pod)
        drained['status']['containerStatuses'][0]['ready'] = False
        self.case.bind_pod(drained, **args, require_ready=False)
        for ready in [0, None, 'false']:
            invalid = deepcopy(drained)
            invalid['status']['containerStatuses'][0]['ready'] = ready
            with self.assertRaises(ValueError):
                self.case.bind_pod(invalid, **args, require_ready=False)
        completed = deepcopy(drained)
        completed['status']['phase'] = 'Succeeded'
        completed['status']['containerStatuses'][0]['state'] = {'terminated': {'exitCode': 0}}
        self.case.bind_pod(completed, **args, completed=True)
        with self.assertRaises(ValueError):
            self.case.bind_pod(completed, **args, require_ready=False)
        for exit_code in [False, 1, '0']:
            completed['status']['containerStatuses'][0]['state']['terminated']['exitCode'] = exit_code
            with self.assertRaises(ValueError):
                self.case.bind_pod(completed, **args, completed=True)
        with self.assertRaises(ValueError):
            self.case.bind_pod(pod, **args, completed=0)

    def test_exact_service_upstream_join_requires_explicit_binding(self):
        from tests.test_v3b2_evidence import producer_records
        run='v3b2-'+'a'*64
        sources=producer_records(TRACKS[0],run)
        sources['envoy'][0]['upstream_host']='10.96.61.43:8080'
        before=deepcopy(sources)
        result=self.case.join(sources,track=TRACKS[0],run_id=run,request_free=False,service_upstream_host='10.96.61.43:8080')
        self.assertEqual(result['observed'],['permit',200,1])
        self.assertEqual(sources,before)
        for bound in (None,'10.96.61.44:8080','10.244.0.8:8080','127.0.0.1:8080','10.96.61.43:80','10.96.0.0:8080','10.96.0.1:8080','10.96.0.10:8080','10.96.255.255:8080',True):
            with self.subTest(bound=bound),self.assertRaises(ValueError):
                self.case.join(sources,track=TRACKS[0],run_id=run,request_free=False,service_upstream_host=bound)

    def test_join(self):
        self.assertTrue(hasattr(self.case, 'join'))
        from tests.test_v3b2_evidence import producer_records
        run = 'v3b2-' + 'a' * 64
        for track, expected in zip(TRACKS, [('permit', 200, 1), ('permit', 200, 1), ('deny', 403, 0)]):
            sources = producer_records(track, run)
            sources['decision'][0]['adapter_reasons'] = ['unverified']
            sources['decision'][0]['engine_reasons'] = ['expired']
            sources['decision'][0]['untrusted_header_names'] = ['x-kil-track']
            result = self.case.join(sources, track=track, run_id=run, request_free=False)
            self.assertEqual(result['observed'], list(expected))
            self.assertEqual(result['classification'], 'expected')
            for key in ['adapter_reasons', 'engine_reasons', 'untrusted_header_names']:
                self.assertEqual(result[key], sources['decision'][0][key])
            self.assertEqual(self.case.join(producer_records(track, run, request_free=True), track=track, run_id=run, request_free=True), {'track': track, 'request_free': True})
        denied = producer_records(TRACKS[2], run)
        for key in ['driver', 'decision', 'envoy']:
            changed = deepcopy(denied)
            changed[key] = []
            with self.assertRaises(ValueError):
                self.case.join(changed, track=TRACKS[2], run_id=run, request_free=False)
        permit = producer_records(TRACKS[0], run)
        permit['target'] = [{}]
        with self.assertRaises(ValueError):
            self.case.join(permit, track=TRACKS[0], run_id=run, request_free=False)
        unexpected = producer_records(TRACKS[0], run)
        unexpected['driver'][1]['response_status'] = 403
        unexpected['decision'][0].update(outcome='deny', http_status=403)
        unexpected['envoy'][0].update(response_code='403', upstream_host='-', upstream_service_time='-')
        unexpected['target'] = []
        result = self.case.join(unexpected, track=TRACKS[0], run_id=run, request_free=False)
        self.assertEqual(result['observed'], ['deny', 403, 0])
        self.assertEqual(result['classification'], 'unexpected')
        for request_free in [True, 0]:
            with self.assertRaises(ValueError):
                self.case.join(unexpected, track=TRACKS[0], run_id=run, request_free=request_free)

    def test_join_rejects_incomplete_and_foreign_evidence(self):
        from tests.test_v3b2_evidence import producer_records
        run = 'v3b2-' + 'a' * 64
        for kind in ['driver', 'decision', 'envoy', 'target']:
            sources = producer_records(TRACKS[0], run)
            sources[kind] = []
            with self.assertRaises(ValueError):
                self.case.join(sources, track=TRACKS[0], run_id=run, request_free=False)
        sources = producer_records(TRACKS[0], run)
        sources['envoy'][0]['decision_digest'] = 'f' * 64
        with self.assertRaises(ValueError):
            self.case.join(sources, track=TRACKS[0], run_id=run, request_free=False)
        with self.assertRaises(ValueError):
            self.case.join(producer_records(TRACKS[0], run), track=TRACKS[0], run_id='v3b2-' + 'b' * 64, request_free=False)
        with self.assertRaises(ValueError):
            self.case.join(producer_records(TRACKS[0], run, request_free=True), track=TRACKS[0], run_id=run, request_free=False)
