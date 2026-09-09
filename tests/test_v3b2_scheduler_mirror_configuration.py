"""Literal API-output fixture, independent of the verifier's expected factory."""
from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import json
import unittest

from tests.test_v3b2_runtime_ownership import fixture as ownership_fixture, encode
from kil.v3b2_runtime_ownership import validate_runtime_ownership

MODULE = 'kil.v3b2_scheduler_mirror_configuration'


def pod(document):
    return next(row for row in document['items'] if row['kind'] == 'Pod'
        and row['metadata']['name'] == 'kube-scheduler-kil-v3-lab-control-plane')


def fixture():
    args = ownership_fixture()
    document = json.loads(args['runtime_objects'])
    observed = pod(document)
    observed['metadata'].update(generation=1, creationTimestamp='2026-09-08T01:00:00Z',
        labels={'component': 'kube-scheduler', 'tier': 'control-plane'})
    observed['metadata']['annotations']['kubernetes.io/config.seen'] = '2026-09-08T01:00:00.123456789Z'
    observed['spec'] = {
        'nodeName': 'kil-v3-lab-control-plane', 'hostNetwork': True,
        'priorityClassName': 'system-node-critical', 'priority': 2000001000,
        'preemptionPolicy': 'PreemptLowerPriority',
        'securityContext': {'seccompProfile': {'type': 'RuntimeDefault'}},
        'tolerations': [{'operator': 'Exists', 'effect': 'NoExecute'}],
        'volumes': [{'name': 'kubeconfig', 'hostPath': {
            'path': '/etc/kubernetes/scheduler.conf', 'type': 'FileOrCreate'}}],
        'containers': [{'name': 'kube-scheduler',
            'image': 'registry.k8s.io/kube-scheduler:v1.36.1', 'imagePullPolicy': 'IfNotPresent',
            'command': ['kube-scheduler', '--authentication-kubeconfig=/etc/kubernetes/scheduler.conf',
                '--authorization-kubeconfig=/etc/kubernetes/scheduler.conf', '--bind-address=127.0.0.1',
                '--kubeconfig=/etc/kubernetes/scheduler.conf', '--leader-elect=true'],
            'resources': {'requests': {'cpu': '100m'}},
            'volumeMounts': [{'name': 'kubeconfig', 'mountPath': '/etc/kubernetes/scheduler.conf', 'readOnly': True}],
            'ports': [{'name': 'probe-port', 'containerPort': 10259, 'hostPort': 10259, 'protocol': 'TCP'}],
            'livenessProbe': {'httpGet': {'host': '127.0.0.1', 'path': '/livez', 'port': 'probe-port', 'scheme': 'HTTPS'},
                'initialDelaySeconds': 10, 'timeoutSeconds': 15, 'failureThreshold': 8, 'periodSeconds': 10},
            'readinessProbe': {'httpGet': {'host': '127.0.0.1', 'path': '/readyz', 'port': 'probe-port', 'scheme': 'HTTPS'},
                'timeoutSeconds': 15, 'failureThreshold': 3, 'periodSeconds': 1},
            'startupProbe': {'httpGet': {'host': '127.0.0.1', 'path': '/livez', 'port': 'probe-port', 'scheme': 'HTTPS'},
                'initialDelaySeconds': 10, 'timeoutSeconds': 15, 'failureThreshold': 24, 'periodSeconds': 10}}]}
    return args, document


class SchedulerMirrorConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'scheduler mirror configuration adapter is missing')
        self.module = importlib.import_module(MODULE)

    def ownership(self, document=None):
        args, default = fixture()
        args['runtime_objects'] = encode(default if document is None else document)
        return validate_runtime_ownership(**args)

    def validate(self, document=None):
        return self.module.validate_scheduler_mirror_configuration(ownership=self.ownership(document))

    def reject(self, path, value):
        _, document = fixture()
        target = pod(document)
        for key in path[:-1]: target = target[key]
        target[path[-1]] = value
        # Ordinary configuration drift must remain valid ownership evidence.
        dependency = self.ownership(document)
        with self.assertRaises(self.module.SchedulerMirrorConfigurationError):
            self.module.validate_scheduler_mirror_configuration(ownership=dependency)

    def test_valid_retained_raw_status_and_flags(self):
        _, document = fixture()
        pod(document)['status'] = {'phase': 'Failed', 'uninterpreted': [False, 123]}
        proof = self.validate(document)
        self.assertEqual(proof.ownership.runtime_objects, encode(document))
        self.assertEqual(replace(proof), proof)
        self.assertEqual(len(proof.bindings), 1)
        self.assertFalse(proof.runtime_contract_complete)
        self.assertFalse(proof.full_application_contract_complete)

    def test_seen_timestamp_producer_format(self):
        for value in ['2024-02-29T23:59:59.000000000Z', '2026-09-08T01:00:00.123456789+05:30',
                '2026-09-08T01:00:00.123456789-07:00']:
            _, document = fixture()
            pod(document)['metadata']['annotations']['kubernetes.io/config.seen'] = value
            self.validate(document)
        for value in [None, 1, '2026-09-08T01:00:00Z', '2026-09-08T01:00:00.123Z',
                '2026-09-08T01:00:00.1234567890Z', '2025-02-29T01:00:00.123456789Z',
                '2026-09-08T24:00:00.123456789Z', '2026-09-08T01:00:00.123456789+24:00',
                '2026-09-08T01:00:00.123456789+01:60', '2026-09-08T01:00:00.123456789+00:00',
                '2026-09-08T01:00:00.123456789-00:00']:
            with self.subTest(value=value): self.reject(('metadata', 'annotations', 'kubernetes.io/config.seen'), value)

    def test_closed_metadata_and_root(self):
        for path, value in [(('metadata', 'generation'), True), (('metadata', 'generation'), 2),
                (('metadata', 'creationTimestamp'), 'bad'), (('metadata', 'generateName'), 'kube-scheduler-'),
                (('metadata', 'finalizers'), []), (('metadata', 'deletionTimestamp'), None),
                (('metadata', 'labels', 'tier'), 'foreign'), (('metadata', 'labels', 'pod-template-hash'), 'abc'),
                (('metadata', 'annotations', 'cni.projectcalico.org/podIP'), '10.0.0.1/32'),
                (('metadata', 'annotations', 'kubectl.kubernetes.io/last-applied-configuration'), '{}'),
                (('metadata', 'annotations', 'foreign'), ''), (('foreign',), {}),
                (('metadata', 'managedFields'), [{}])]:
            with self.subTest(path=path): self.reject(path, value)

    def test_spec_admission_and_extra_fields(self):
        for path, value in [(('hostNetwork',), 1), (('priority',), True), (('priority',), 1),
                (('priorityClassName',), 'foreign'), (('preemptionPolicy',), 'Never'),
                (('securityContext', 'seccompProfile', 'type'), 'Unconfined'),
                (('securityContext', 'runAsUser'), 1000), (('tolerations', 0, 'tolerationSeconds'), 300),
                (('tolerations',), []), (('serviceAccountName',), 'default'), (('serviceAccount',), 'default'),
                (('imagePullSecrets',), []), (('automountServiceAccountToken',), False), (('initContainers',), []),
                (('volumes', 0, 'hostPath', 'type'), 'File'), (('volumes', 0, 'hostPath', 'path'), '/foreign')]:
            with self.subTest(path=path): self.reject(('spec', *path), value)

    def test_container_and_probe_configuration(self):
        for path, value in [(('image',), 'foreign'), (('imagePullPolicy',), 'Always'), (('args',), []),
                (('env',), []), (('securityContext',), {}), (('resources', 'requests', 'cpu'), '1'),
                (('resources', 'limits'), {}), (('volumeMounts', 0, 'readOnly'), 1),
                (('volumeMounts', 0, 'mountPath'), '/foreign'), (('ports', 0, 'hostPort'), 1),
                (('ports', 0, 'containerPort'), 1), (('ports', 0, 'protocol'), 'UDP'),
                (('command', 5), '--leader-elect=false')]:
            with self.subTest(path=path): self.reject(('spec', 'containers', 0, *path), value)
        for probe in ('livenessProbe', 'readinessProbe', 'startupProbe'):
            for path, value in [(('httpGet', 'host'), '0.0.0.0'), (('httpGet', 'path'), '/healthz'),
                    (('httpGet', 'port'), 10259), (('httpGet', 'scheme'), 'HTTP'),
                    (('timeoutSeconds',), 1), (('failureThreshold',), 99), (('periodSeconds',), 99),
                    (('successThreshold',), True)]:
                with self.subTest(probe=probe, path=path): self.reject(('spec', 'containers', 0, probe, *path), value)
        self.reject(('spec', 'containers', 0, 'readinessProbe', 'initialDelaySeconds'), 0)
        _, document = fixture()
        command = pod(document)['spec']['containers'][0]['command']
        self.reject(('spec', 'containers', 0, 'command'), list(reversed(command)))

    def test_required_fields(self):
        for path in [('metadata', 'generation'), ('metadata', 'creationTimestamp'),
                ('metadata', 'annotations', 'kubernetes.io/config.seen'), ('spec', 'priority'),
                ('spec', 'containers', 0, 'ports', 0, 'hostPort')]:
            _, document = fixture()
            target = pod(document)
            for key in path[:-1]: target = target[key]
            del target[path[-1]]
            with self.subTest(path=path), self.assertRaises(self.module.SchedulerMirrorConfigurationError):
                self.module.validate_scheduler_mirror_configuration(ownership=self.ownership(document))

    def test_default_serialization_and_factory_isolation(self):
        _, document = fixture()
        spec = pod(document)['spec']
        spec.update(dnsPolicy='ClusterFirst', restartPolicy='Always', terminationGracePeriodSeconds=30,
            schedulerName='default-scheduler', enableServiceLinks=True)
        container = spec['containers'][0]
        container.update(terminationMessagePath='/dev/termination-log', terminationMessagePolicy='File')
        for probe in ('livenessProbe', 'readinessProbe', 'startupProbe'): container[probe]['successThreshold'] = 1
        self.validate(document)
        expected = self.module.scheduler_mirror_api_spec()
        expected['containers'][0]['command'].clear()
        self.validate()

    def test_constructor_exact_types_flags_and_bindings(self):
        proof = self.validate()
        for flag in ('runtime_contract_complete', 'full_application_contract_complete'):
            for value in (True, 0, None):
                with self.assertRaises(self.module.SchedulerMirrorConfigurationError): replace(proof, **{flag: value})
        for field, value in [('namespace', 'default'), ('pod_name', 'foreign'), ('pod_uid', None),
                ('pod_resource_version', True), ('config_hash', 'a')]:
            with self.assertRaises(self.module.SchedulerMirrorConfigurationError): replace(proof.bindings[0], **{field: value})
        for field, value in [('pod_uid', 'foreign'), ('pod_resource_version', '999'), ('config_hash', 'f' * 32)]:
            binding = replace(proof.bindings[0], **{field: value})
            with self.assertRaises(self.module.SchedulerMirrorConfigurationError): replace(proof, bindings=(binding,))
        class SubBinding(type(proof.bindings[0])): pass
        binding = SubBinding(**{f: getattr(proof.bindings[0], f) for f in proof.bindings[0].__dataclass_fields__})
        for value in ([], (), (binding,), proof.bindings * 2):
            with self.assertRaises(self.module.SchedulerMirrorConfigurationError): replace(proof, bindings=value)
        class SubOwnership(type(proof.ownership)): pass
        dependency = SubOwnership(**{f: getattr(proof.ownership, f) for f in proof.ownership.__dataclass_fields__})
        for value in (None, dependency):
            with self.assertRaises(self.module.SchedulerMirrorConfigurationError): replace(proof, ownership=value)

    def test_replay_reconstructs_ownership_before_candidate_comparison(self):
        proof = self.validate()
        for path, value in [(('metadata', 'uid'), 'foreign'), (('metadata', 'resourceVersion'), '999'),
                (('metadata', 'ownerReferences', 0, 'uid'), 'foreign'),
                (('metadata', 'ownerReferences', 0, 'blockOwnerDeletion'), True),
                (('metadata', 'annotations', 'kubernetes.io/config.hash'), 'f' * 32),
                (('metadata', 'annotations', 'kubernetes.io/config.mirror'), 'f' * 32),
                (('metadata', 'labels', 'component'), 'foreign'), (('spec', 'nodeName'), 'foreign')]:
            _, document = fixture()
            target = pod(document)
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            dependency = deepcopy(proof.ownership)
            object.__setattr__(dependency, 'runtime_objects', encode(document))
            with self.subTest(path=path), self.assertRaises(self.module.SchedulerMirrorConfigurationError):
                replace(proof, ownership=dependency)
        dependency = deepcopy(proof.ownership)
        object.__setattr__(dependency, 'runtime_objects', b'{}')
        with self.assertRaises(self.module.SchedulerMirrorConfigurationError): replace(proof, ownership=dependency)


if __name__ == '__main__': unittest.main()
