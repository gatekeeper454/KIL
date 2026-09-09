"""Literal observed admission fixture independent of production expectations."""
from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import unittest

from tests.test_v3b2_kube_proxy_revision import fixture as revision_fixture
from tests.test_v3b2_runtime_ownership import encode
from kil.v3b2_runtime_ownership import validate_runtime_ownership
from kil.v3b2_kube_proxy_parent_configuration import validate_kube_proxy_parent_configuration
from kil.v3b2_kube_proxy_revision import validate_kube_proxy_revision

MODULE = 'kil.v3b2_kube_proxy_pod_configuration'


def pod(document):
    return next(r for r in document['items'] if r['kind'] == 'Pod'
        and r['metadata'].get('ownerReferences', [{}])[0].get('name') == 'kube-proxy')


def fixture():
    args, document = revision_fixture()
    observed = pod(document)
    node = observed['spec']['nodeName']
    observed['metadata'].update(generation=1, creationTimestamp='2026-09-08T01:00:00Z',
        generateName='kube-proxy-', labels={'k8s-app': 'kube-proxy', 'controller-revision-hash': 'abc123'})
    observed['metadata']['ownerReferences'][0].update(blockOwnerDeletion=True)
    observed['spec'] = {
        'nodeName': node, 'hostNetwork': True, 'priorityClassName': 'system-node-critical',
        'priority': 2000001000, 'preemptionPolicy': 'PreemptLowerPriority',
        'serviceAccountName': 'kube-proxy', 'nodeSelector': {'kubernetes.io/os': 'linux'},
        'affinity': {'nodeAffinity': {'requiredDuringSchedulingIgnoredDuringExecution': {
            'nodeSelectorTerms': [{'matchFields': [{'key': 'metadata.name', 'operator': 'In', 'values': [node]}]}]}}},
        'tolerations': [{'operator': 'Exists'},
            {'key': 'node.kubernetes.io/not-ready', 'operator': 'Exists', 'effect': 'NoExecute'},
            {'key': 'node.kubernetes.io/unreachable', 'operator': 'Exists', 'effect': 'NoExecute'},
            {'key': 'node.kubernetes.io/disk-pressure', 'operator': 'Exists', 'effect': 'NoSchedule'},
            {'key': 'node.kubernetes.io/memory-pressure', 'operator': 'Exists', 'effect': 'NoSchedule'},
            {'key': 'node.kubernetes.io/pid-pressure', 'operator': 'Exists', 'effect': 'NoSchedule'},
            {'key': 'node.kubernetes.io/unschedulable', 'operator': 'Exists', 'effect': 'NoSchedule'},
            {'key': 'node.kubernetes.io/network-unavailable', 'operator': 'Exists', 'effect': 'NoSchedule'}],
        'containers': [{'name': 'kube-proxy', 'image': 'registry.k8s.io/kube-proxy:v1.36.1',
            'imagePullPolicy': 'IfNotPresent', 'securityContext': {'privileged': True},
            'command': ['/usr/local/bin/kube-proxy', '--config=/var/lib/kube-proxy/config.conf', '--hostname-override=$(NODE_NAME)'],
            'env': [{'name': 'NODE_NAME', 'valueFrom': {'fieldRef': {'fieldPath': 'spec.nodeName'}}}],
            'volumeMounts': [{'name': 'kube-proxy', 'mountPath': '/var/lib/kube-proxy'},
                {'name': 'xtables-lock', 'mountPath': '/run/xtables.lock'},
                {'name': 'lib-modules', 'mountPath': '/lib/modules', 'readOnly': True},
                {'name': 'kube-api-access-bc245', 'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount', 'readOnly': True}]}],
        'volumes': [{'name': 'kube-proxy', 'configMap': {'name': 'kube-proxy'}},
            {'name': 'xtables-lock', 'hostPath': {'path': '/run/xtables.lock', 'type': 'FileOrCreate'}},
            {'name': 'lib-modules', 'hostPath': {'path': '/lib/modules'}},
            {'name': 'kube-api-access-bc245', 'projected': {'defaultMode': 420, 'sources': [
                {'serviceAccountToken': {'path': 'token', 'expirationSeconds': 3607}},
                {'configMap': {'name': 'kube-root-ca.crt', 'items': [{'key': 'ca.crt', 'path': 'ca.crt'}]}},
                {'downwardAPI': {'items': [{'path': 'namespace', 'fieldRef': {'apiVersion': 'v1', 'fieldPath': 'metadata.namespace'}}]}}]}}]}
    return args, document


class KubeProxyPodConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'kube-proxy Pod configuration adapter is missing')
        self.module = importlib.import_module(MODULE)

    def revision(self, document=None):
        args, default = fixture()
        args['runtime_objects'] = encode(default if document is None else document)
        return validate_kube_proxy_revision(parent=validate_kube_proxy_parent_configuration(
            ownership=validate_runtime_ownership(**args)))

    def validate(self, document=None):
        return self.module.validate_kube_proxy_pod_configuration(revision=self.revision(document))

    def reject(self, path, value):
        _, document = fixture()
        target = pod(document)
        for key in path[:-1]: target = target[key]
        target[path[-1]] = value
        dependency = self.revision(document)
        with self.assertRaises(self.module.KubeProxyPodConfigurationError):
            self.module.validate_kube_proxy_pod_configuration(revision=dependency)

    def test_complete_configuration_and_uninterpreted_status_retained(self):
        _, document = fixture()
        pod(document)['status'] = {'phase': 'Pending', 'uncertified': [False]}
        revision = self.revision(document)
        proof = self.module.validate_kube_proxy_pod_configuration(revision=revision)
        self.assertIs(proof.revision, revision)
        self.assertEqual(proof.revision.parent.ownership.runtime_objects, encode(document))
        self.assertEqual(proof.bindings[0].token_volume_name, 'kube-api-access-bc245')
        self.assertEqual(proof.bindings[0].pod_uid, revision.bindings[0].pod_uid)
        self.assertFalse(proof.runtime_contract_complete)
        self.assertFalse(proof.full_application_contract_complete)
        self.assertEqual(replace(proof), proof)

    def test_explicit_default_serialization_and_managed_fields(self):
        _, document = fixture()
        spec = pod(document)['spec']
        spec.update(serviceAccount='kube-proxy', dnsPolicy='ClusterFirst', restartPolicy='Always',
            securityContext={}, terminationGracePeriodSeconds=30, schedulerName='default-scheduler', enableServiceLinks=True)
        spec['volumes'][0]['configMap']['defaultMode'] = 420
        spec['volumes'][2]['hostPath']['type'] = ''
        container = spec['containers'][0]
        container.update(resources={}, terminationMessagePath='/dev/termination-log', terminationMessagePolicy='File')
        container['volumeMounts'][1]['readOnly'] = False
        container['env'][0]['valueFrom']['fieldRef']['apiVersion'] = 'v1'
        pod(document)['metadata']['managedFields'] = [{'manager': 'controller', 'operation': 'Update',
            'apiVersion': 'v1', 'fieldsType': 'FieldsV1', 'fieldsV1': {'f:spec': {}}}]
        self.validate(document)

    def test_closed_metadata_and_root(self):
        for path, value in [(('foreign',), {}), (('metadata', 'generation'), True),
                (('metadata', 'generation'), 2), (('metadata', 'generateName'), 'foreign-'),
                (('metadata', 'creationTimestamp'), 'bad'), (('metadata', 'finalizers'), []),
                (('metadata', 'deletionTimestamp'), None), (('metadata', 'managedFields'), [{}]),
                (('metadata', 'labels', 'extra'), 'value')]:
            with self.subTest(path=path): self.reject(path, value)
        for annotation in ({}, {'cni.projectcalico.org/podIP': '1.2.3.4'}, {'kubectl.kubernetes.io/last-applied-configuration': '{}'}):
            with self.subTest(annotation=annotation): self.reject(('metadata', 'annotations'), annotation)

    def test_scheduling_and_tolerations(self):
        for path, value in [(('priority',), True), (('priority',), 2000000000),
                (('preemptionPolicy',), 'Never'), (('priorityClassName',), 'system-cluster-critical'),
                (('affinity',), {}), (('terminationGracePeriodSeconds',), 0),
                (('tolerations', 1, 'tolerationSeconds'), 300), (('tolerations', 7, 'effect'), 'NoExecute'),
                (('nodeSelector',), {}), (('hostNetwork',), 1), (('automountServiceAccountToken',), True),
                (('imagePullSecrets',), []), (('serviceAccountName',), 'default')]:
            with self.subTest(path=path): self.reject(('spec', *path), value)
        _, document = fixture()
        for key in ('tolerations', 'volumes'):
            with self.subTest(key=key): self.reject(('spec', key), list(reversed(pod(document)['spec'][key])))

    def test_token_projection_and_mount(self):
        prefix = ('spec', 'volumes', 3)
        for path, value in [(('name',), 'kube-api-access-aaaaa'),
                (('projected', 'defaultMode'), 421),
                (('projected', 'sources', 0, 'serviceAccountToken', 'expirationSeconds'), 3600),
                (('projected', 'sources', 0, 'serviceAccountToken', 'audience'), 'foreign'),
                (('projected', 'sources', 0, 'serviceAccountToken', 'path'), 'foreign'),
                (('projected', 'sources', 1, 'configMap', 'name'), 'foreign'),
                (('projected', 'sources', 2, 'downwardAPI', 'items', 0, 'fieldRef', 'fieldPath'), 'spec.nodeName')]:
            with self.subTest(path=path): self.reject((*prefix, *path), value)
        for key, value in [('name', 'foreign'), ('readOnly', False), ('mountPath', '/foreign')]:
            self.reject(('spec', 'containers', 0, 'volumeMounts', 3, key), value)
        _, document = fixture()
        self.reject((*prefix, 'projected', 'sources'), list(reversed(pod(document)['spec']['volumes'][3]['projected']['sources'])))

    def test_consistent_token_rename_and_exact_affinity(self):
        _, document = fixture()
        spec = pod(document)['spec']
        spec['volumes'][3]['name'] = 'kube-api-access-zz245'
        spec['containers'][0]['volumeMounts'][3]['name'] = 'kube-api-access-zz245'
        self.assertEqual(self.validate(document).bindings[0].token_volume_name, 'kube-api-access-zz245')
        prefix = ('spec', 'affinity', 'nodeAffinity', 'requiredDuringSchedulingIgnoredDuringExecution', 'nodeSelectorTerms', 0)
        for path, value in [(('matchFields', 0, 'key'), 'spec.nodeName'),
                (('matchFields', 0, 'operator'), 'NotIn'), (('matchFields', 0, 'values'), ['foreign']),
                (('matchExpressions',), [])]:
            with self.subTest(path=path): self.reject((*prefix, *path), value)

    def test_source_containers_volumes_and_privileges(self):
        for path, value in [(('image',), 'foreign'), (('command', 1), '--config=/foreign'),
                (('command', 2), '--hostname-override=expanded'), (('securityContext', 'privileged'), 1),
                (('env', 0, 'valueFrom', 'fieldRef', 'fieldPath'), 'metadata.name'),
                (('resources',), {'requests': {'cpu': '1'}}), (('livenessProbe',), {}),
                (('ports',), []), (('args',), []), (('volumeMounts', 1, 'readOnly'), True),
                (('volumeMounts', 2, 'readOnly'), False)]:
            with self.subTest(path=path): self.reject(('spec', 'containers', 0, *path), value)
        self.reject(('spec', 'initContainers'), [])
        self.reject(('spec', 'volumes', 1, 'hostPath', 'path'), '/foreign')
        self.reject(('spec', 'volumes', 0, 'configMap', 'name'), 'foreign')
        _, document = fixture()
        container = pod(document)['spec']['containers'][0]
        for key in ('command', 'volumeMounts'):
            self.reject(('spec', 'containers', 0, key), list(reversed(container[key])))
        self.reject(('spec', 'containers', 0, 'env'), container['env'] + [{'name': 'HTTP_PROXY', 'value': 'http://proxy.invalid'}])
        self.reject(('spec', 'containers'), [container, deepcopy(container)])

    def test_required_metadata_and_admission_fields(self):
        for path in [('metadata', 'creationTimestamp'), ('metadata', 'generation'), ('metadata', 'generateName'),
                ('spec', 'priority'), ('spec', 'preemptionPolicy'), ('spec', 'affinity')]:
            _, document = fixture()
            target = pod(document)
            for key in path[:-1]: target = target[key]
            del target[path[-1]]
            dependency = self.revision(document)
            with self.subTest(path=path), self.assertRaises(self.module.KubeProxyPodConfigurationError):
                self.module.validate_kube_proxy_pod_configuration(revision=dependency)

    def test_binding_types_flags_and_reconstruction(self):
        proof = self.validate()
        for flag in ('runtime_contract_complete', 'full_application_contract_complete'):
            for value in (True, 0, None):
                with self.assertRaises(self.module.KubeProxyPodConfigurationError): replace(proof, **{flag: value})
        for field, value in [('namespace', 'default'), ('pod_name', 'foreign'), ('pod_uid', None),
                ('pod_resource_version', True), ('token_volume_name', 'kube-api-access-aaaaa')]:
            with self.assertRaises(self.module.KubeProxyPodConfigurationError): replace(proof.bindings[0], **{field: value})
        for field, value in [('pod_uid', 'foreign'), ('pod_resource_version', '999'), ('token_volume_name', 'kube-api-access-zz245')]:
            binding = replace(proof.bindings[0], **{field: value})
            with self.assertRaises(self.module.KubeProxyPodConfigurationError): replace(proof, bindings=(binding,))
        class SubBinding(type(proof.bindings[0])): pass
        binding = SubBinding(**{f: getattr(proof.bindings[0], f) for f in proof.bindings[0].__dataclass_fields__})
        for bindings in ([], (), (binding,), (proof.bindings[0], proof.bindings[0])):
            with self.assertRaises(self.module.KubeProxyPodConfigurationError): replace(proof, bindings=bindings)
        class SubRevision(type(proof.revision)): pass
        dependency = SubRevision(**{f: getattr(proof.revision, f) for f in proof.revision.__dataclass_fields__})
        for dependency in (None, dependency):
            with self.assertRaises(self.module.KubeProxyPodConfigurationError): replace(proof, revision=dependency)
        dependency = deepcopy(proof.revision)
        object.__setattr__(dependency.parent.ownership, 'runtime_objects', b'{}')
        with self.assertRaises(self.module.KubeProxyPodConfigurationError): replace(proof, revision=dependency)

    def test_reconstruction_rejects_owned_node_owner_and_revision_drift(self):
        proof = self.validate()
        for path, value in [(('metadata', 'ownerReferences', 0, 'blockOwnerDeletion'), False),
                (('metadata', 'ownerReferences', 0, 'foreign'), True),
                (('metadata', 'ownerReferences', 0, 'uid'), 'foreign'),
                (('metadata', 'labels', 'controller-revision-hash'), 'foreign'),
                (('spec', 'nodeName'), 'foreign')]:
            _, document = fixture()
            target = pod(document)
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            dependency = deepcopy(proof.revision)
            object.__setattr__(dependency.parent.ownership, 'runtime_objects', encode(document))
            with self.subTest(path=path), self.assertRaises(self.module.KubeProxyPodConfigurationError):
                replace(proof, revision=dependency)


if __name__ == '__main__': unittest.main()
