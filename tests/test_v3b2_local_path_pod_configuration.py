"""Independent Kind parent literal plus explicit, ordered admission additions."""
from copy import deepcopy
from dataclasses import replace, FrozenInstanceError
import importlib
import importlib.util
import unittest

from kil.v3b2_local_path_parent_configuration import validate_local_path_parent_configuration
from kil.v3b2_runtime_ownership import validate_runtime_ownership, RuntimeOwnershipError
from tests.test_v3b2_local_path_parent_configuration import fixture as parent_fixture, row
from tests.test_v3b2_runtime_ownership import encode

MODULE = 'kil.v3b2_local_path_pod_configuration'
CNI = 'cni.projectcalico.org/'


def pod(document):
    return next(r for r in document['items'] if r['kind'] == 'Pod'
        and r['metadata']['name'].startswith('local-path-provisioner-'))


def fixture():
    args, document = parent_fixture()
    candidate = pod(document)
    metadata = candidate['metadata']
    metadata.update(generation=1, creationTimestamp='2026-09-08T01:00:00Z',
        generateName=metadata['ownerReferences'][0]['name'] + '-')
    metadata['labels']['app'] = 'local-path-provisioner'
    metadata['ownerReferences'][0]['blockOwnerDeletion'] = True
    candidate['spec'] = spec = deepcopy(row(document, 'Deployment')['spec']['template']['spec'])
    spec.update(priority=0, preemptionPolicy='PreemptLowerPriority')
    spec['tolerations'] += [
        {'key': 'node.kubernetes.io/not-ready', 'operator': 'Exists', 'effect': 'NoExecute', 'tolerationSeconds': 300},
        {'key': 'node.kubernetes.io/unreachable', 'operator': 'Exists', 'effect': 'NoExecute', 'tolerationSeconds': 300}]
    spec['volumes'].append({'name': 'kube-api-access-bcdfg', 'projected': {'defaultMode': 420, 'sources': [
        {'serviceAccountToken': {'path': 'token', 'expirationSeconds': 3607}},
        {'configMap': {'name': 'kube-root-ca.crt', 'items': [{'key': 'ca.crt', 'path': 'ca.crt'}]}},
        {'downwardAPI': {'items': [{'path': 'namespace', 'fieldRef': {
            'apiVersion': 'v1', 'fieldPath': 'metadata.namespace'}}]}}]}})
    spec['containers'][0]['volumeMounts'].append({'name': 'kube-api-access-bcdfg', 'readOnly': True,
        'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount'})
    return args, document


class LocalPathPodConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'local-path Pod adapter is missing')
        self.module = importlib.import_module(MODULE)

    def parent(self, document=None):
        args, default = fixture()
        args['runtime_objects'] = encode(default if document is None else document)
        return validate_local_path_parent_configuration(ownership=validate_runtime_ownership(**args))

    def validate(self, document=None):
        return self.module.validate_local_path_pod_configuration(parent=self.parent(document))

    def test_unscheduled_retains_exact_parent_raw_status_and_binding(self):
        _, document = fixture()
        candidate = pod(document)
        candidate['status'] = {'arbitrary': ['retained'], 'podIP': 'uninterpreted'}
        candidate['metadata']['resourceVersion'] = '12345'
        parent = self.parent(document)
        proof = self.module.validate_local_path_pod_configuration(parent=parent)
        self.assertIs(proof.parent, parent)
        self.assertEqual(proof.parent.ownership.runtime_objects, encode(document))
        binding, = proof.bindings
        self.assertEqual((binding.namespace, binding.name, binding.uid, binding.resource_version, binding.token_volume_name),
            ('local-path-storage', candidate['metadata']['name'], candidate['metadata']['uid'], '12345', 'kube-api-access-bcdfg'))
        self.assertFalse(proof.runtime_contract_complete)
        self.assertFalse(proof.full_application_contract_complete)
        self.assertEqual(replace(proof), proof)

    def test_scheduled_serialized_defaults_empty_annotations_and_managed_fields(self):
        _, document = fixture()
        candidate = pod(document)
        candidate['metadata']['annotations'] = {}
        candidate['metadata']['managedFields'] = [{'manager': 'kubelet', 'operation': 'Update', 'apiVersion': 'v1',
            'fieldsType': 'FieldsV1', 'fieldsV1': {'f:spec': {}}}]
        spec = candidate['spec']
        spec.update(nodeName='kil-v3-lab-control-plane', serviceAccount='local-path-provisioner-service-account',
            enableServiceLinks=True, restartPolicy='Always', dnsPolicy='ClusterFirst', securityContext={},
            terminationGracePeriodSeconds=30, schedulerName='default-scheduler')
        spec['volumes'][0]['configMap']['defaultMode'] = 420
        container = spec['containers'][0]
        container.update(resources={}, terminationMessagePath='/dev/termination-log', terminationMessagePolicy='File')
        container['volumeMounts'][0]['readOnly'] = False
        container['env'][0]['valueFrom']['fieldRef']['apiVersion'] = 'v1'
        self.validate(document)

    def test_pod_only_drift_rejected_after_parent_acceptance(self):
        container = ('spec', 'containers', 0)
        token = ('spec', 'volumes', 1, 'projected')
        mutations = [
            (('foreign',), {}), (('metadata', 'generation'), True), (('metadata', 'generation'), 2),
            (('metadata', 'creationTimestamp'), 'invalid'), (('metadata', 'generateName'), 'foreign-'),
            (('metadata', 'labels', 'foreign'), 'value'), (('metadata', 'labels', 'app'), 'foreign'),
            (('metadata', 'finalizers'), []), (('metadata', 'deletionTimestamp'), None),
            (('metadata', 'managedFields'), [{}]), (('metadata', 'annotations'), {'foreign': 'value'}),
            (('metadata', 'annotations'), {'kubectl.kubernetes.io/last-applied-configuration': '{}'}),
            (('spec', 'priority'), True), (('spec', 'priority'), 1),
            (('spec', 'priorityClassName'), ''), (('spec', 'priorityClassName'), 'system-cluster-critical'),
            (('spec', 'preemptionPolicy'), 'Never'), (('spec', 'nodeName'), 'foreign'),
            (('spec', 'imagePullSecrets'), []), (('spec', 'automountServiceAccountToken'), True),
            (('spec', 'initContainers'), []), (('spec', 'enableServiceLinks'), False),
            (('spec', 'serviceAccountName'), 'foreign'), (('spec', 'nodeSelector'), {}),
            (('spec', 'tolerations', 0, 'operator'), 'Exists'),
            (('spec', 'tolerations', 2, 'tolerationSeconds'), 301),
            ((*container, 'command', 4), 'foreign'), ((*container, 'command', 6), '/etc/config/wrong'),
            ((*container, 'image'), 'foreign'), ((*container, 'env', 1, 'value'), '/etc/config'),
            ((*container, 'env', 0, 'valueFrom', 'fieldRef', 'fieldPath'), 'metadata.name'),
            ((*container, 'volumeMounts', 0, 'mountPath'), '/etc/config'),
            ((*container, 'volumeMounts', 0, 'readOnly'), True),
            ((*container, 'volumeMounts', 1, 'readOnly'), False),
            ((*container, 'volumeMounts', 1, 'mountPath'), '/foreign'),
            ((*container, 'volumeMounts', 1, 'name'), 'kube-api-access-zzzzz'),
            ((*container, 'resources'), {'requests': {'cpu': '1'}}),
            ((*container, 'securityContext'), {}), ((*container, 'ports'), []),
            ((*container, 'readinessProbe'), {'exec': {'command': ['true']}}),
            (('spec', 'volumes', 0, 'configMap', 'name'), 'foreign'),
            ((*token, 'defaultMode'), 400),
            ((*token, 'sources', 0, 'serviceAccountToken', 'expirationSeconds'), 3600),
            ((*token, 'sources', 0, 'serviceAccountToken', 'audience'), 'foreign'),
            ((*token, 'sources', 1, 'configMap', 'name'), 'foreign'),
            ((*token, 'sources', 2, 'downwardAPI', 'items', 0, 'fieldRef', 'fieldPath'), 'metadata.name')]
        for path, value in mutations:
            _, document = fixture()
            target = pod(document)
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path, value=value):
                parent = self.parent(document)
                with self.assertRaises(self.module.LocalPathPodConfigurationError):
                    self.module.validate_local_path_pod_configuration(parent=parent)

    def test_missing_fields_order_counts_and_token_name(self):
        paths = [('metadata', 'generation'), ('metadata', 'creationTimestamp'), ('metadata', 'generateName'),
            ('spec', 'priority'), ('spec', 'preemptionPolicy'),
            ('spec', 'containers', 0, 'volumeMounts', 1, 'readOnly'),
            ('spec', 'volumes', 1, 'projected', 'defaultMode'),
            ('spec', 'volumes', 1, 'projected', 'sources', 0, 'serviceAccountToken', 'expirationSeconds')]
        for path in paths:
            _, document = fixture()
            target = pod(document)
            for key in path[:-1]: target = target[key]
            del target[path[-1]]
            with self.subTest(path=path), self.assertRaises(self.module.LocalPathPodConfigurationError): self.validate(document)
        for path in [('tolerations',), ('containers', 0, 'env'), ('containers', 0, 'command'),
            ('containers', 0, 'volumeMounts'), ('volumes',), ('volumes', 1, 'projected', 'sources')]:
            for operation in ('reverse', 'pop', 'append'):
                _, document = fixture()
                target = pod(document)['spec']
                for key in path: target = target[key]
                if operation == 'append': target.append(deepcopy(target[0]))
                else: getattr(target, operation)()
                with self.subTest(path=path, operation=operation), self.assertRaises(self.module.LocalPathPodConfigurationError): self.validate(document)
        for name in ('kube-api-access-abcde', 'kube-api-access-bcdf', 'kube-api-access-bcdfgg', 'other-bcdfg', '', True):
            _, document = fixture()
            pod(document)['spec']['volumes'][1]['name'] = name
            pod(document)['spec']['containers'][0]['volumeMounts'][1]['name'] = name
            with self.subTest(name=name), self.assertRaises(self.module.LocalPathPodConfigurationError): self.validate(document)
        _, document = fixture()
        pod(document)['spec']['tolerations'].append({'key': 'node.kubernetes.io/memory-pressure', 'operator': 'Exists', 'effect': 'NoSchedule'})
        with self.assertRaises(self.module.LocalPathPodConfigurationError): self.validate(document)

    def test_cni_pair_optional_sandbox_and_no_status_join(self):
        for sandbox in (None, 'b' * 64):
            _, document = fixture()
            candidate = pod(document)
            candidate['spec']['nodeName'] = 'kil-v3-lab-control-plane'
            candidate['metadata']['annotations'] = {CNI + 'podIP': '10.244.0.12/32', CNI + 'podIPs': '10.244.0.12/32'}
            if sandbox: candidate['metadata']['annotations'][CNI + 'containerID'] = sandbox
            candidate['status'] = {'podIP': '10.99.0.1'}
            self.validate(document)

    def test_cni_partial_malformed_mismatched_and_node_collision(self):
        variants = [{CNI + 'podIP': '10.244.0.12/32'}, {CNI + 'containerID': 'b' * 64},
            {CNI + 'podIP': '', CNI + 'podIPs': ''}]
        pair = {CNI + 'podIP': '10.244.0.12/32', CNI + 'podIPs': '10.244.0.12/32'}
        variants += [dict(pair, **{CNI + 'podIPs': '10.244.0.13/32'}), dict(pair, foreign='x')]
        variants += [{CNI + 'podIP': value, CNI + 'podIPs': value} for value in
            ('10.244.0.12/24', '10.0.0.12/32', '010.244.0.12/32', '::1/32')]
        collision = self.parent().ownership.owned_identity.node_container_id
        variants += [dict(pair, **{CNI + 'containerID': value}) for value in ('', 'B' * 64, collision)]
        for annotations in variants:
            _, document = fixture()
            pod(document)['spec']['nodeName'] = 'kil-v3-lab-control-plane'
            pod(document)['metadata']['annotations'] = annotations
            with self.subTest(annotations=annotations), self.assertRaises(self.module.LocalPathPodConfigurationError): self.validate(document)
        for node in (None, 'foreign'):
            _, document = fixture()
            if node: pod(document)['spec']['nodeName'] = node
            pod(document)['metadata']['annotations'] = pair
            with self.subTest(node=node), self.assertRaises(self.module.LocalPathPodConfigurationError): self.validate(document)

    def test_owner_hash_and_identity_rejected(self):
        for path, value in [(('ownerReferences', 0, 'controller'), False),
            (('ownerReferences', 0, 'blockOwnerDeletion'), False), (('ownerReferences', 0, 'foreign'), True),
            (('ownerReferences', 0, 'uid'), 'foreign'), (('labels', 'pod-template-hash'), 'foreign'),
            (('uid',), ''), (('resourceVersion',), True), (('namespace',), 'foreign')]:
            _, document = fixture()
            target = pod(document)['metadata']
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises((RuntimeOwnershipError, self.module.LocalPathPodConfigurationError)):
                self.validate(document)
        _, document = fixture()
        del pod(document)['metadata']['ownerReferences'][0]['blockOwnerDeletion']
        with self.assertRaises(RuntimeOwnershipError): self.parent(document)

    def test_constructor_recomputes_exact_types_and_false_flags(self):
        proof = self.validate()
        error = self.module.LocalPathPodConfigurationError
        for flag in ('runtime_contract_complete', 'full_application_contract_complete'):
            for value in (True, 0, None):
                with self.subTest(flag=flag, value=value), self.assertRaises(error): replace(proof, **{flag: value})
        for field, value in [('uid', 'different'), ('resource_version', '123'), ('token_volume_name', 'kube-api-access-zzzzz'),
            ('name', 'local-path-provisioner-different')]:
            binding = replace(proof.bindings[0], **{field: value})
            with self.subTest(field=field), self.assertRaises(error): replace(proof, bindings=(binding,))
        for field in ('namespace', 'name', 'uid', 'resource_version', 'token_volume_name'):
            for value in ('', None, True, 1):
                with self.subTest(field=field, value=value), self.assertRaises(error): replace(proof.bindings[0], **{field: value})
        class SubBinding(type(proof.bindings[0])): pass
        binding = SubBinding(**{f: getattr(proof.bindings[0], f) for f in proof.bindings[0].__dataclass_fields__})
        for bindings in ([], (), proof.bindings * 2, (binding,)):
            with self.assertRaises(error): replace(proof, bindings=bindings)
        class SubParent(type(proof.parent)): pass
        parent = SubParent(**{f: getattr(proof.parent, f) for f in proof.parent.__dataclass_fields__})
        forged = deepcopy(proof.parent)
        object.__setattr__(forged.ownership, 'runtime_objects', b'{}')
        for parent in (None, parent, forged):
            with self.assertRaises(error): replace(proof, parent=parent)
        forged_binding = deepcopy(proof.bindings[0])
        object.__setattr__(forged_binding, 'uid', True)
        with self.assertRaises(error): replace(proof, bindings=(forged_binding,))
        with self.assertRaises(FrozenInstanceError): proof.bindings[0].uid = 'foreign'
        with self.assertRaises(TypeError): self.module.validate_local_path_pod_configuration(parent=proof.parent, expected=[])


if __name__ == '__main__': unittest.main()
