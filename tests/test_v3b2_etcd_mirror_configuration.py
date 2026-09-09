"""Literal etcd mirror API-output fixture; no production expected factory use."""
from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import json
import unittest

from tests.test_v3b2_runtime_ownership import fixture as ownership_fixture, encode
from kil.v3b2_runtime_ownership import validate_runtime_ownership

MODULE = 'kil.v3b2_etcd_mirror_configuration'
NODE = 'kil-v3-lab-control-plane'
DEFAULT_IP = '172.18.0.2'


def row(document, kind, name):
    return next(item for item in document['items']
        if item['kind'] == kind and item['metadata']['name'] == name)


def command(ip):
    return ['etcd', f'--advertise-client-urls=https://{ip}:2379',
        '--cert-file=/etc/kubernetes/pki/etcd/server.crt', '--client-cert-auth=true',
        '--data-dir=/var/lib/etcd', '--feature-gates=InitialCorruptCheck=true',
        f'--initial-advertise-peer-urls=https://{ip}:2380',
        f'--initial-cluster={NODE}=https://{ip}:2380',
        '--key-file=/etc/kubernetes/pki/etcd/server.key',
        f'--listen-client-urls=https://127.0.0.1:2379,https://{ip}:2379',
        '--listen-metrics-urls=http://127.0.0.1:2381',
        f'--listen-peer-urls=https://{ip}:2380', f'--name={NODE}',
        '--peer-cert-file=/etc/kubernetes/pki/etcd/peer.crt',
        '--peer-client-cert-auth=true', '--peer-key-file=/etc/kubernetes/pki/etcd/peer.key',
        '--peer-trusted-ca-file=/etc/kubernetes/pki/etcd/ca.crt', '--snapshot-count=10000',
        '--trusted-ca-file=/etc/kubernetes/pki/etcd/ca.crt', '--watch-progress-notify-interval=5s']


def fixture(ip=DEFAULT_IP):
    args = ownership_fixture()
    document = json.loads(args['runtime_objects'])
    node = row(document, 'Node', NODE)
    node['status'] = {'addresses': [
        {'type': 'InternalIP', 'address': ip},
        {'type': 'Hostname', 'address': NODE},
    ]}
    observed = row(document, 'Pod', 'etcd-' + NODE)
    observed['metadata'].update(generation=1, creationTimestamp='2026-09-08T01:00:00Z',
        labels={'component': 'etcd', 'tier': 'control-plane'})
    observed['metadata']['annotations'].update(
        **{'kubernetes.io/config.seen': '2026-09-08T01:00:00.123456789Z',
           'kubeadm.kubernetes.io/etcd.advertise-client-urls': f'https://{ip}:2379'})
    observed['spec'] = {
        'nodeName': NODE, 'hostNetwork': True, 'priorityClassName': 'system-node-critical',
        'priority': 2000001000, 'preemptionPolicy': 'PreemptLowerPriority',
        'securityContext': {'seccompProfile': {'type': 'RuntimeDefault'}},
        'tolerations': [{'operator': 'Exists', 'effect': 'NoExecute'}],
        'volumes': [
            {'name': 'etcd-certs', 'hostPath': {'path': '/etc/kubernetes/pki/etcd', 'type': 'DirectoryOrCreate'}},
            {'name': 'etcd-data', 'hostPath': {'path': '/var/lib/etcd', 'type': 'DirectoryOrCreate'}}],
        'containers': [{'name': 'etcd', 'image': 'registry.k8s.io/etcd:3.6.8-0',
            'imagePullPolicy': 'IfNotPresent', 'command': command(ip),
            'resources': {'requests': {'cpu': '100m', 'memory': '100Mi'}},
            'volumeMounts': [
                {'name': 'etcd-data', 'mountPath': '/var/lib/etcd', 'readOnly': False},
                {'name': 'etcd-certs', 'mountPath': '/etc/kubernetes/pki/etcd', 'readOnly': False}],
            'ports': [{'name': 'probe-port', 'containerPort': 2381, 'hostPort': 2381, 'protocol': 'TCP'}],
            'livenessProbe': {'httpGet': {'host': '127.0.0.1', 'path': '/livez', 'port': 'probe-port', 'scheme': 'HTTP'},
                'initialDelaySeconds': 10, 'timeoutSeconds': 15, 'failureThreshold': 8, 'periodSeconds': 10},
            'readinessProbe': {'httpGet': {'host': '127.0.0.1', 'path': '/readyz', 'port': 'probe-port', 'scheme': 'HTTP'},
                'timeoutSeconds': 15, 'failureThreshold': 3, 'periodSeconds': 1},
            'startupProbe': {'httpGet': {'host': '127.0.0.1', 'path': '/readyz', 'port': 'probe-port', 'scheme': 'HTTP'},
                'initialDelaySeconds': 10, 'timeoutSeconds': 15, 'failureThreshold': 24, 'periodSeconds': 10}}]}
    return args, document


class EtcdMirrorConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'etcd mirror configuration adapter is missing')
        self.module = importlib.import_module(MODULE)

    def ownership(self, document=None):
        args, default = fixture()
        args['runtime_objects'] = encode(default if document is None else document)
        return validate_runtime_ownership(**args)

    def validate(self, document=None):
        return self.module.validate_etcd_mirror_configuration(ownership=self.ownership(document))

    def reject(self, path, value, *, target='pod'):
        _, document = fixture()
        candidate = row(document, 'Pod', 'etcd-' + NODE) if target == 'pod' else row(document, 'Node', NODE)
        for key in path[:-1]: candidate = candidate[key]
        candidate[path[-1]] = value
        dependency = self.ownership(document)
        with self.assertRaises(self.module.EtcdMirrorConfigurationError):
            self.module.validate_etcd_mirror_configuration(ownership=dependency)

    def reject_replay(self, path, value):
        proof = self.validate()
        _, document = fixture()
        candidate = row(document, 'Pod', 'etcd-' + NODE)
        for key in path[:-1]: candidate = candidate[key]
        candidate[path[-1]] = value
        dependency = deepcopy(proof.ownership)
        object.__setattr__(dependency, 'runtime_objects', encode(document))
        with self.assertRaises(self.module.EtcdMirrorConfigurationError):
            replace(proof, ownership=dependency)

    def test_valid_retains_raw_status_binding_and_false_flags(self):
        _, document = fixture()
        row(document, 'Pod', 'etcd-' + NODE)['status'] = {'phase': 'Failed', 'arbitrary': [False, 7]}
        proof = self.validate(document)
        self.assertEqual(proof.ownership.runtime_objects, encode(document))
        self.assertEqual(replace(proof), proof)
        self.assertEqual(len(proof.bindings), 1)
        self.assertEqual(proof.bindings[0].node_internal_ip, DEFAULT_IP)
        self.assertFalse(proof.runtime_contract_complete)
        self.assertFalse(proof.full_application_contract_complete)

    def test_default_serialization_and_factory_isolation(self):
        _, document = fixture()
        spec = row(document, 'Pod', 'etcd-' + NODE)['spec']
        spec.update(dnsPolicy='ClusterFirst', restartPolicy='Always', terminationGracePeriodSeconds=30,
            schedulerName='default-scheduler', enableServiceLinks=True)
        container = spec['containers'][0]
        container.update(terminationMessagePath='/dev/termination-log', terminationMessagePolicy='File')
        for probe in ('livenessProbe', 'readinessProbe', 'startupProbe'): container[probe]['successThreshold'] = 1
        self.validate(document)
        expected = self.module.etcd_mirror_api_spec(DEFAULT_IP)
        expected['containers'][0]['command'].clear()
        self.validate()

    def test_seen_timestamp_exact_producer_format(self):
        valid = ['2024-02-29T23:59:59.000000000Z', '2026-09-08T01:00:00.123456789+05:30',
                 '2026-09-08T01:00:00.123456789-07:00']
        for value in valid:
            _, document = fixture(); row(document, 'Pod', 'etcd-' + NODE)['metadata']['annotations']['kubernetes.io/config.seen'] = value
            self.validate(document)
        invalid = [None, 1, '2026-09-08T01:00:00Z', '2026-09-08T01:00:00.123Z',
            '2026-09-08T01:00:00.1234567890Z', '2025-02-29T01:00:00.123456789Z',
            '2026-09-08T24:00:00.123456789Z', '2026-09-08T01:00:00.123456789+24:00',
            '2026-09-08T01:00:00.123456789+01:60', '2026-09-08T01:00:00.123456789+00:00',
            '2026-09-08T01:00:00.123456789-00:00']
        for value in invalid:
            with self.subTest(value=value): self.reject(('metadata', 'annotations', 'kubernetes.io/config.seen'), value)

    def test_same_source_node_address_and_consistent_change(self):
        self.validate()
        _, changed = fixture('10.20.30.40')
        self.validate(changed)
        _, reserved = fixture('240.0.0.1')
        with self.assertRaises(self.module.EtcdMirrorConfigurationError): self.validate(reserved)
        for value in [None, True, 1, '0172.18.0.2', '127.0.0.1', '0.0.0.0', '169.254.1.1',
                      '224.0.0.1', '240.0.0.1', '::1']:
            with self.subTest(value=value): self.reject(('status', 'addresses', 0, 'address'), value, target='node')
        malformed = [
            [{'type': 'Hostname', 'address': NODE}, {'type': 'InternalIP', 'address': DEFAULT_IP}],
            [{'type': 'ExternalIP', 'address': DEFAULT_IP}, {'type': 'Hostname', 'address': NODE}],
            [{'type': 'InternalIP', 'address': DEFAULT_IP}, {'type': 'Hostname', 'address': 'foreign'}],
            [{'type': 'InternalIP', 'address': DEFAULT_IP}, {'type': 'Hostname', 'address': NODE}, {'type': 'ExternalIP', 'address': '1.1.1.1'}],
            [{'type': 'InternalIP', 'address': DEFAULT_IP, 'extra': 1}, {'type': 'Hostname', 'address': NODE}],
        ]
        for value in malformed:
            with self.subTest(value=value): self.reject(('status', 'addresses'), value, target='node')

    def test_closed_metadata_annotations_owner_and_root(self):
        cases = [(('metadata', 'generation'), True), (('metadata', 'generation'), 2),
            (('metadata', 'creationTimestamp'), 'bad'), (('metadata', 'generateName'), 'etcd-'),
            (('metadata', 'finalizers'), []), (('metadata', 'deletionTimestamp'), None),
            (('metadata', 'labels', 'tier'), 'foreign'), (('metadata', 'labels', 'pod-template-hash'), 'abc'),
            (('metadata', 'annotations', 'foreign'), ''),
            (('metadata', 'annotations', 'cni.projectcalico.org/podIP'), '10.0.0.1/32'),
            (('metadata', 'annotations', 'kubectl.kubernetes.io/last-applied-configuration'), '{}'),
            (('foreign',), {})]
        for path, value in cases:
            with self.subTest(path=path): self.reject(path, value)
        self.reject(('metadata', 'managedFields'), [{}])

    def test_hash_owner_identity_and_advertise_annotation_relations(self):
        for path, value in [(('metadata', 'annotations', 'kubeadm.kubernetes.io/etcd.advertise-client-urls'),
                             'https://10.0.0.1:2379')]:
            with self.subTest(path=path): self.reject(path, value)
        replay_cases = [(('metadata', 'uid'), 'foreign'), (('metadata', 'resourceVersion'), '999'),
            (('metadata', 'ownerReferences', 0, 'uid'), 'foreign'),
            (('metadata', 'ownerReferences', 0, 'controller'), 1),
            (('metadata', 'ownerReferences', 0, 'blockOwnerDeletion'), True),
            (('metadata', 'annotations', 'kubernetes.io/config.hash'), 'f' * 32),
            (('metadata', 'annotations', 'kubernetes.io/config.mirror'), 'f' * 32)]
        for path, value in replay_cases:
            with self.subTest(path=path): self.reject_replay(path, value)

    def test_spec_command_resources_ports_mounts_volumes_and_admission(self):
        cases = [(('hostNetwork',), 1), (('priority',), True),
            (('priorityClassName',), 'foreign'), (('preemptionPolicy',), 'Never'),
            (('securityContext', 'seccompProfile', 'type'), 'Unconfined'),
            (('tolerations',), []), (('tolerations', 0, 'tolerationSeconds'), 300),
            (('serviceAccountName',), 'default'), (('serviceAccount',), 'default'),
            (('automountServiceAccountToken',), False), (('imagePullSecrets',), []), (('initContainers',), []),
            (('volumes', 0, 'hostPath', 'path'), '/foreign'), (('volumes', 1, 'hostPath', 'type'), 'Directory')]
        for path, value in cases:
            with self.subTest(path=path): self.reject(('spec', *path), value)
        self.reject_replay(('spec', 'nodeName'), 'foreign')
        container_cases = [(('image',), 'foreign'), (('imagePullPolicy',), 'Always'), (('env',), []),
            (('args',), []), (('resources', 'requests', 'cpu'), '1'),
            (('resources', 'requests', 'memory'), '1Gi'), (('resources', 'limits'), {}),
            (('ports', 0, 'containerPort'), 1), (('ports', 0, 'hostPort'), 1),
            (('ports', 0, 'protocol'), 'UDP'), (('volumeMounts', 0, 'mountPath'), '/foreign'),
            (('volumeMounts', 1, 'readOnly'), True), (('command', 1), '--advertise-client-urls=https://10.0.0.1:2379')]
        for path, value in container_cases:
            with self.subTest(path=path): self.reject(('spec', 'containers', 0, *path), value)
        _, document = fixture(); current = row(document, 'Pod', 'etcd-' + NODE)['spec']['containers'][0]['command']
        self.reject(('spec', 'containers', 0, 'command'), list(reversed(current)))

    def test_probe_exactness_and_required_fields(self):
        for probe in ('livenessProbe', 'readinessProbe', 'startupProbe'):
            for path, value in [(('httpGet', 'host'), '0.0.0.0'), (('httpGet', 'path'), '/healthz'),
                    (('httpGet', 'port'), 2381), (('httpGet', 'scheme'), 'HTTPS'),
                    (('timeoutSeconds',), 1), (('failureThreshold',), 99), (('periodSeconds',), 99),
                    (('successThreshold',), True)]:
                with self.subTest(probe=probe, path=path):
                    self.reject(('spec', 'containers', 0, probe, *path), value)
        self.reject(('spec', 'containers', 0, 'readinessProbe', 'initialDelaySeconds'), 0)
        for path in [('metadata', 'generation'), ('metadata', 'creationTimestamp'),
                ('metadata', 'annotations', 'kubernetes.io/config.seen'), ('spec', 'priority'),
                ('spec', 'containers', 0, 'ports', 0, 'hostPort')]:
            _, document = fixture(); target = row(document, 'Pod', 'etcd-' + NODE)
            for key in path[:-1]: target = target[key]
            del target[path[-1]]
            with self.subTest(path=path), self.assertRaises(self.module.EtcdMirrorConfigurationError):
                self.validate(document)

    def test_constructor_exact_types_forgery_and_same_source_reconstruction(self):
        proof = self.validate()
        for flag in ('runtime_contract_complete', 'full_application_contract_complete'):
            for value in (True, 0, None):
                with self.assertRaises(self.module.EtcdMirrorConfigurationError): replace(proof, **{flag: value})
        for field, value in [('namespace', 'default'), ('pod_name', 'foreign'), ('pod_uid', None),
                ('pod_resource_version', True), ('config_hash', 'x'), ('node_internal_ip', True)]:
            with self.assertRaises(self.module.EtcdMirrorConfigurationError): replace(proof.bindings[0], **{field: value})
        for field, value in [('pod_uid', 'foreign'), ('pod_resource_version', '999'),
                ('config_hash', 'f' * 32), ('node_internal_ip', '10.0.0.1')]:
            binding = replace(proof.bindings[0], **{field: value})
            with self.assertRaises(self.module.EtcdMirrorConfigurationError): replace(proof, bindings=(binding,))
        class SubBinding(type(proof.bindings[0])): pass
        sub = SubBinding(**{f: getattr(proof.bindings[0], f) for f in proof.bindings[0].__dataclass_fields__})
        for value in ([], (), (sub,), proof.bindings * 2):
            with self.assertRaises(self.module.EtcdMirrorConfigurationError): replace(proof, bindings=value)
        class SubOwnership(type(proof.ownership)): pass
        forged = SubOwnership(**{f: getattr(proof.ownership, f) for f in proof.ownership.__dataclass_fields__})
        for value in (None, forged):
            with self.assertRaises(self.module.EtcdMirrorConfigurationError): replace(proof, ownership=value)
        dependency = deepcopy(proof.ownership)
        _, document = fixture(); row(document, 'Node', NODE)['status']['addresses'][0]['address'] = '10.0.0.1'
        object.__setattr__(dependency, 'runtime_objects', encode(document))
        with self.assertRaises(self.module.EtcdMirrorConfigurationError): replace(proof, ownership=dependency)
        object.__setattr__(dependency, 'runtime_objects', b'{}')
        with self.assertRaises(self.module.EtcdMirrorConfigurationError): replace(proof, ownership=dependency)


if __name__ == '__main__': unittest.main()
