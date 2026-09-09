"""Independent literal admission additions to the independent parent fixture."""
from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import unittest

from kil.v3b2_coredns_parent_configuration import validate_coredns_parent_configuration
from kil.v3b2_runtime_ownership import validate_runtime_ownership
from tests.test_v3b2_coredns_parent_configuration import fixture as parent_fixture, row
from tests.test_v3b2_runtime_ownership import encode

MODULE = 'kil.v3b2_coredns_pod_configuration'
CNI = 'cni.projectcalico.org/'


def pods(document):
    return sorted((r for r in document['items'] if r['kind'] == 'Pod'
        and r['metadata']['name'].startswith('coredns-')), key=lambda r: r['metadata']['name'])


def fixture():
    args, document = parent_fixture()
    template = row(document, 'Deployment')['spec']['template']
    for pod in pods(document):
        metadata = pod['metadata']
        metadata.update(generation=1, creationTimestamp='2026-09-08T01:00:00Z',
            generateName=metadata['ownerReferences'][0]['name'] + '-')
        metadata['labels']['k8s-app'] = 'kube-dns'
        metadata['ownerReferences'][0]['blockOwnerDeletion'] = True
        pod['spec'] = spec = deepcopy(template['spec'])
        spec.update(priority=2000000000, preemptionPolicy='PreemptLowerPriority')
        spec['tolerations'] += [{'key': 'node.kubernetes.io/not-ready', 'operator': 'Exists',
            'effect': 'NoExecute', 'tolerationSeconds': 300}, {'key': 'node.kubernetes.io/unreachable',
            'operator': 'Exists', 'effect': 'NoExecute', 'tolerationSeconds': 300}]
        spec['volumes'].append({'name': 'kube-api-access-bcdfg', 'projected': {'defaultMode': 420, 'sources': [
            {'serviceAccountToken': {'path': 'token', 'expirationSeconds': 3607}},
            {'configMap': {'name': 'kube-root-ca.crt', 'items': [{'key': 'ca.crt', 'path': 'ca.crt'}]}},
            {'downwardAPI': {'items': [{'path': 'namespace', 'fieldRef': {
                'apiVersion': 'v1', 'fieldPath': 'metadata.namespace'}}]}}]}})
        spec['containers'][0]['volumeMounts'].append({'name': 'kube-api-access-bcdfg', 'readOnly': True,
            'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount'})
    return args, document


class CoreDNSPodConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'CoreDNS Pod adapter is missing')
        self.module = importlib.import_module(MODULE)

    def parent(self, document=None):
        args, default = fixture()
        args['runtime_objects'] = encode(default if document is None else document)
        return validate_coredns_parent_configuration(ownership=validate_runtime_ownership(**args))

    def validate(self, document=None):
        return self.module.validate_coredns_pod_configuration(parent=self.parent(document))

    def test_two_pods_same_token_name_raw_status_and_exact_parent_retained(self):
        _, document = fixture()
        pods(document)[0]['status'] = {'arbitrary': ['retained'], 'podIP': 'not interpreted'}
        pods(document)[1]['metadata']['resourceVersion'] = '12345'
        parent = self.parent(document)
        proof = self.module.validate_coredns_pod_configuration(parent=parent)
        self.assertIs(proof.parent, parent)
        self.assertEqual(proof.parent.ownership.runtime_objects, encode(document))
        self.assertEqual([b.name for b in proof.bindings], [p['metadata']['name'] for p in pods(document)])
        self.assertEqual([b.token_volume_name for b in proof.bindings], ['kube-api-access-bcdfg'] * 2)
        self.assertFalse(proof.runtime_contract_complete)
        self.assertFalse(proof.full_application_contract_complete)
        self.assertEqual(replace(proof), proof)

    def test_scheduled_serialized_defaults_and_empty_annotations(self):
        _, document = fixture()
        for pod in pods(document):
            pod['metadata']['annotations'] = {}
            pod['metadata']['managedFields'] = [{'manager': 'kubelet', 'operation': 'Update', 'apiVersion': 'v1',
                'fieldsType': 'FieldsV1', 'fieldsV1': {'f:spec': {}}}]
            spec = pod['spec']
            spec.update(nodeName='kil-v3-lab-control-plane', serviceAccount='coredns', enableServiceLinks=True,
                restartPolicy='Always', securityContext={}, terminationGracePeriodSeconds=30, schedulerName='default-scheduler')
            spec['volumes'][0]['configMap']['defaultMode'] = 420
            container = spec['containers'][0]
            container.update(terminationMessagePath='/dev/termination-log', terminationMessagePolicy='File')
            container['livenessProbe']['periodSeconds'] = 10
            container['readinessProbe'].update(timeoutSeconds=1, periodSeconds=10, successThreshold=1, failureThreshold=3)
        self.validate(document)

    def test_configuration_drift_fails_after_parent_passes(self):
        changes = [(('priority',), True), (('priority',), 0), (('priorityClassName',), 'system-node-critical'),
            (('preemptionPolicy',), 'Never'), (('resources',), {}), (('dnsPolicy',), 'ClusterFirst'),
            (('automountServiceAccountToken',), True), (('imagePullSecrets',), []), (('initContainers',), []),
            (('containers', 0, 'resources', 'requests', 'memory'), '170Mi'),
            (('containers', 0, 'resources', 'requests', 'cpu'), '200m'),
            (('containers', 0, 'resources', 'limits', 'memory'), '171Mi'),
            (('containers', 0, 'securityContext', 'allowPrivilegeEscalation'), True),
            (('containers', 0, 'ports', 4, 'containerPort'), 8182),
            (('containers', 0, 'livenessProbe', 'httpGet', 'scheme'), 'HTTPS'),
            (('containers', 0, 'readinessProbe', 'periodSeconds'), 11), (('affinity',), {}),
            (('tolerations', 1, 'operator'), 'Equal'), (('tolerations', 2, 'tolerationSeconds'), 301),
            (('volumes', 1, 'name'), 'kube-api-access-abcde'),
            (('volumes', 1, 'projected', 'defaultMode'), True),
            (('volumes', 1, 'projected', 'sources', 0, 'serviceAccountToken', 'expirationSeconds'), 3600),
            (('volumes', 1, 'projected', 'sources', 0, 'serviceAccountToken', 'audience'), 'extra'),
            (('containers', 0, 'volumeMounts', 1, 'name'), 'kube-api-access-zzzzz'), (('nodeName',), 'foreign')]
        for path, value in changes:
            _, document = fixture()
            target = pods(document)[1]['spec']
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path):
                parent = self.parent(document)
                with self.assertRaises(self.module.CoreDNSPodConfigurationError):
                    self.module.validate_coredns_pod_configuration(parent=parent)

    def test_order_count_and_memory_pressure_are_closed(self):
        for path in [('volumes',), ('containers', 0, 'volumeMounts'), ('containers', 0, 'ports'),
                     ('volumes', 1, 'projected', 'sources'), ('tolerations',), ('containers',)]:
            for action in ('reverse', 'extra', 'missing'):
                _, document = fixture()
                target = pods(document)[0]['spec']
                for key in path: target = target[key]
                if action == 'reverse':
                    if len(target) == 1: continue
                    target.reverse()
                elif action == 'extra': target.append(deepcopy(target[0]))
                else: target.pop()
                with self.subTest(path=path, action=action), self.assertRaises(self.module.CoreDNSPodConfigurationError):
                    self.validate(document)
        _, document = fixture()
        pods(document)[0]['spec']['tolerations'].append({'key': 'node.kubernetes.io/memory-pressure',
            'operator': 'Exists', 'effect': 'NoSchedule'})
        with self.assertRaises(self.module.CoreDNSPodConfigurationError): self.validate(document)

    def test_metadata_closed(self):
        for key, value in [('generation', True), ('generation', 2), ('creationTimestamp', 'bad'),
            ('generateName', 'foreign-'), ('labels', {'pod-template-hash': 'abcde'}),
            ('finalizers', []), ('deletionTimestamp', None), ('managedFields', [{}]),
            ('annotations', {'foreign': 'value'}), ('annotations', {'kubectl.kubernetes.io/last-applied-configuration': '{}'})]:
            _, document = fixture()
            pods(document)[0]['metadata'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.validate(document)
        for key in ('generation', 'creationTimestamp', 'generateName', 'labels'):
            _, document = fixture()
            del pods(document)[0]['metadata'][key]
            with self.subTest(missing=key), self.assertRaises(ValueError): self.validate(document)
        _, document = fixture()
        pods(document)[0]['metadata']['ownerReferences'][0]['blockOwnerDeletion'] = False
        with self.assertRaises(ValueError): self.validate(document)
        _, document = fixture()
        pods(document)[0]['extra'] = {}
        with self.assertRaises(self.module.CoreDNSPodConfigurationError): self.validate(document)

    def test_cni_pairs_scheduling_and_cross_pod_collisions(self):
        args, base = fixture()
        for index, pod in enumerate(pods(base)):
            pod['spec']['nodeName'] = 'kil-v3-lab-control-plane'
            pod['metadata']['annotations'] = {CNI+'podIP': f'10.244.0.{10+index}/32',
                CNI+'podIPs': f'10.244.0.{10+index}/32', CNI+'containerID': str(index+1)*64}
        self.validate(base)
        for case in ('ip-collision', 'sandbox-collision', 'node-collision', 'no-node', 'partial', 'mismatch', 'outside', 'bad-sandbox'):
            document = deepcopy(base)
            first, second = pods(document)
            annotations = second['metadata']['annotations']
            if case == 'ip-collision':
                for key in ('podIP', 'podIPs'): annotations[CNI+key] = first['metadata']['annotations'][CNI+key]
            elif case == 'sandbox-collision': annotations[CNI+'containerID'] = '1'*64
            elif case == 'node-collision': annotations[CNI+'containerID'] = args['owned_identity'].node_container_id
            elif case == 'no-node': del second['spec']['nodeName']
            elif case == 'partial': del annotations[CNI+'podIPs']
            elif case == 'mismatch': annotations[CNI+'podIPs'] = '10.244.0.99/32'
            elif case == 'outside': annotations.update({CNI+'podIP': '192.0.2.1/32', CNI+'podIPs': '192.0.2.1/32'})
            else: annotations[CNI+'containerID'] = 'X'*64
            with self.subTest(case=case), self.assertRaises(self.module.CoreDNSPodConfigurationError): self.validate(document)
        for pod in pods(base): del pod['metadata']['annotations'][CNI+'containerID']
        self.validate(base)

    def test_constructor_exact_types_reconstruction_and_flags(self):
        proof = self.validate()
        for flag in ('runtime_contract_complete', 'full_application_contract_complete'):
            for value in (True, 0, None):
                with self.assertRaises(self.module.CoreDNSPodConfigurationError): replace(proof, **{flag: value})
        for field in ('uid', 'resource_version', 'token_volume_name'):
            value = 'kube-api-access-zzzzz' if field == 'token_volume_name' else '999'
            binding = replace(proof.bindings[0], **{field: value})
            with self.assertRaises(self.module.CoreDNSPodConfigurationError): replace(proof, bindings=(binding, proof.bindings[1]))
        class SubBinding(type(proof.bindings[0])): pass
        binding = SubBinding(**{f: getattr(proof.bindings[0], f) for f in proof.bindings[0].__dataclass_fields__})
        for bindings in (list(proof.bindings), (), tuple(reversed(proof.bindings)), (binding, proof.bindings[1])):
            with self.assertRaises(self.module.CoreDNSPodConfigurationError): replace(proof, bindings=bindings)
        class SubParent(type(proof.parent)): pass
        parent = SubParent(**{f: getattr(proof.parent, f) for f in proof.parent.__dataclass_fields__})
        forged = deepcopy(proof.parent)
        object.__setattr__(forged.ownership, 'runtime_objects', b'{}')
        for parent in (None, parent, forged):
            with self.assertRaises(self.module.CoreDNSPodConfigurationError): replace(proof, parent=parent)


if __name__ == '__main__': unittest.main()
