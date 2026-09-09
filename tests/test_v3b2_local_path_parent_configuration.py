"""Independent local-path output literals, without production factory/defaults."""
from copy import deepcopy
from dataclasses import replace, FrozenInstanceError
import importlib
import importlib.util
import json
import unittest

from kil.v3b2_runtime_ownership import validate_runtime_ownership, RuntimeOwnershipError
from tests.test_v3b2_runtime_ownership import fixture as ownership_fixture, encode

MODULE = 'kil.v3b2_local_path_parent_configuration'


def row(document, kind):
    name = 'local-path-provisioner' if kind == 'Deployment' else 'local-path-provisioner-service-account'
    return next(r for r in document['items'] if r['kind'] == kind and r['metadata']['name'] == name)


def fixture():
    args = ownership_fixture()
    document = json.loads(args['runtime_objects'])
    deployment = row(document, 'Deployment')
    deployment['metadata'].update(generation=1, creationTimestamp='2026-09-08T01:00:00Z')
    deployment['spec'] = {
        'replicas': 1,
        'strategy': {'type': 'RollingUpdate', 'rollingUpdate': {'maxUnavailable': '25%', 'maxSurge': '25%'}},
        'selector': {'matchLabels': {'app': 'local-path-provisioner'}},
        'template': {'metadata': {'labels': {'app': 'local-path-provisioner'}}, 'spec': {
            'nodeSelector': {'kubernetes.io/os': 'linux'},
            'tolerations': [
                {'key': 'node-role.kubernetes.io/control-plane', 'operator': 'Equal', 'effect': 'NoSchedule'},
                {'key': 'node-role.kubernetes.io/master', 'operator': 'Equal', 'effect': 'NoSchedule'}],
            'serviceAccountName': 'local-path-provisioner-service-account',
            'containers': [{'name': 'local-path-provisioner',
                'image': 'docker.io/kindest/local-path-provisioner:v20260521-9fb22683',
                'imagePullPolicy': 'IfNotPresent',
                'command': ['local-path-provisioner', '--debug', 'start', '--helper-image',
                    'docker.io/kindest/local-path-helper:v20260131-7181c60a', '--config', '/etc/config/config.json'],
                'volumeMounts': [{'name': 'config-volume', 'mountPath': '/etc/config/'}],
                'env': [{'name': 'POD_NAMESPACE', 'valueFrom': {'fieldRef': {'fieldPath': 'metadata.namespace'}}},
                    {'name': 'CONFIG_MOUNT_PATH', 'value': '/etc/config/'}]}],
            'volumes': [{'name': 'config-volume', 'configMap': {'name': 'local-path-config'}}]}}}
    document['items'].append({'apiVersion': 'v1', 'kind': 'ServiceAccount', 'metadata': {
        'name': 'local-path-provisioner-service-account', 'namespace': 'local-path-storage',
        'uid': 'localpath-sa', 'resourceVersion': '100', 'creationTimestamp': '2026-09-08T01:00:00Z'}})
    return args, document


class LocalPathParentConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'local-path parent configuration adapter is missing')
        self.module = importlib.import_module(MODULE)

    def ownership(self, document=None):
        args, default = fixture()
        args['runtime_objects'] = encode(default if document is None else document)
        return validate_runtime_ownership(**args)

    def validate(self, document=None):
        return self.module.validate_local_path_parent_configuration(ownership=self.ownership(document))

    def test_preserves_exact_raw_ownership_and_same_source_parent_identity(self):
        _, document = fixture()
        for kind in ('Deployment', 'ServiceAccount'):
            row(document, kind)['status'] = {'arbitrary': ['retained'], 'readyReplicas': 0}
        row(document, 'Deployment')['metadata']['resourceVersion'] = '101'
        owner = self.ownership(document)
        proof = self.module.validate_local_path_parent_configuration(ownership=owner)
        self.assertIs(proof.ownership, owner)
        self.assertEqual(proof.ownership.runtime_objects, encode(document))
        binding = proof.bindings[0]
        self.assertEqual((binding.namespace, binding.deployment_name), ('local-path-storage', 'local-path-provisioner'))
        self.assertEqual(binding.deployment_uid, row(document, 'Deployment')['metadata']['uid'])
        self.assertEqual(binding.deployment_resource_version, '101')
        self.assertEqual(binding.service_account_uid, 'localpath-sa')
        self.assertEqual(binding.service_account_resource_version, '100')
        relation = next(b for b in owner.deployment_ownership.bindings if b.deployment_name == binding.deployment_name)
        self.assertEqual(len(relation.pods), 1)
        self.assertFalse(proof.runtime_contract_complete)
        self.assertFalse(proof.full_application_contract_complete)
        self.assertEqual(replace(proof), proof)

    def test_factory_is_fresh_and_has_no_root_labels(self):
        first = self.module.local_path_parent_objects()
        second = self.module.local_path_parent_objects()
        self.assertEqual([r['kind'] for r in first], ['Deployment', 'ServiceAccount'])
        self.assertEqual(first[0]['metadata'], {'name': 'local-path-provisioner', 'namespace': 'local-path-storage'})
        first[0]['spec']['template']['spec']['containers'][0]['command'].append('poison')
        first[1]['metadata']['labels'] = {'poison': 'yes'}
        self.assertEqual(second, self.module.local_path_parent_objects())
        self.validate()

    def test_independently_serialized_reviewed_defaults(self):
        _, document = fixture()
        spec = row(document, 'Deployment')['spec']
        spec.update(revisionHistoryLimit=10, progressDeadlineSeconds=600)
        spec['template']['metadata']['creationTimestamp'] = None
        pod = spec['template']['spec']
        pod.update(serviceAccount='local-path-provisioner-service-account', restartPolicy='Always',
            dnsPolicy='ClusterFirst', securityContext={}, terminationGracePeriodSeconds=30, schedulerName='default-scheduler')
        pod['volumes'][0]['configMap']['defaultMode'] = 420
        container = pod['containers'][0]
        container.update(resources={}, terminationMessagePath='/dev/termination-log', terminationMessagePolicy='File')
        container['env'][0]['valueFrom']['fieldRef']['apiVersion'] = 'v1'
        container['volumeMounts'][0]['readOnly'] = False
        self.validate(document)

    def test_configuration_drift_rejected_after_ownership_passes(self):
        base = ('spec', 'template', 'spec')
        container = (*base, 'containers', 0)
        mutations = [
            (('metadata', 'labels'), {}), (('metadata', 'labels'), {'app': 'local-path-provisioner'}),
            (('metadata', 'generation'), True), (('metadata', 'generation'), 2),
            (('metadata', 'creationTimestamp'), 'invalid'), (('metadata', 'finalizers'), []),
            (('metadata', 'ownerReferences'), []), (('metadata', 'deletionTimestamp'), None),
            (('metadata', 'annotations', 'foreign'), 'value'), (('foreign',), {}),
            (('spec', 'strategy', 'rollingUpdate', 'maxUnavailable'), 25),
            (('spec', 'strategy', 'rollingUpdate', 'maxSurge'), 25),
            (('spec', 'strategy', 'type'), 'Recreate'),
            (('spec', 'selector', 'matchLabels'), {'app': 'foreign'}),
            (('spec', 'template', 'metadata', 'labels'), {'app': 'foreign'}),
            ((*base, 'priority'), 0), ((*base, 'priorityClassName'), 'system-cluster-critical'),
            ((*base, 'enableServiceLinks'), True), ((*base, 'serviceAccountName'), 'foreign'),
            ((*base, 'nodeSelector'), {}), ((*base, 'tolerations', 0, 'operator'), 'Exists'),
            ((*container, 'image'), 'foreign'), ((*container, 'imagePullPolicy'), 'Always'),
            ((*container, 'command', 4), 'docker.io/kindest/local-path-helper:foreign'),
            ((*container, 'command', 6), '/etc/config/foreign.json'),
            ((*container, 'env', 1, 'value'), '/etc/config'),
            ((*container, 'env', 0, 'valueFrom', 'fieldRef', 'fieldPath'), 'metadata.name'),
            ((*container, 'volumeMounts', 0, 'mountPath'), '/etc/config'),
            ((*container, 'volumeMounts', 0, 'readOnly'), True),
            ((*container, 'resources'), {'requests': {'cpu': '1'}}),
            ((*container, 'ports'), []), ((*container, 'securityContext'), {}),
            ((*base, 'volumes', 0, 'configMap', 'name'), 'foreign')]
        for path, value in mutations:
            _, document = fixture()
            target = row(document, 'Deployment')
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path, value=value):
                owner = self.ownership(document)
                with self.assertRaises(self.module.LocalPathParentConfigurationError):
                    self.module.validate_local_path_parent_configuration(ownership=owner)

    def test_ordered_lists_and_missing_fields(self):
        for path in [('tolerations',), ('containers', 0, 'env'), ('containers', 0, 'command')]:
            _, document = fixture()
            target = row(document, 'Deployment')['spec']['template']['spec']
            for key in path: target = target[key]
            target.reverse()
            with self.subTest(path=path), self.assertRaises(self.module.LocalPathParentConfigurationError): self.validate(document)
        for path in [('metadata', 'generation'), ('metadata', 'creationTimestamp'),
                     ('spec', 'strategy'), ('spec', 'strategy', 'rollingUpdate', 'maxUnavailable'),
                     ('spec', 'strategy', 'rollingUpdate', 'maxSurge'),
                     ('spec', 'template', 'spec', 'tolerations', 0, 'operator')]:
            _, document = fixture()
            target = row(document, 'Deployment')
            for key in path[:-1]: target = target[key]
            del target[path[-1]]
            with self.subTest(path=path), self.assertRaises(self.module.LocalPathParentConfigurationError): self.validate(document)

    def test_service_account_extras_missing_and_duplicate_objects(self):
        for key, value in [('automountServiceAccountToken', False), ('imagePullSecrets', []), ('secrets', []), ('spec', {})]:
            _, document = fixture()
            row(document, 'ServiceAccount')[key] = value
            with self.subTest(key=key), self.assertRaises(self.module.LocalPathParentConfigurationError): self.validate(document)
        for key, value in [('labels', {}), ('ownerReferences', []), ('finalizers', []), ('creationTimestamp', 'invalid')]:
            _, document = fixture()
            row(document, 'ServiceAccount')['metadata'][key] = value
            with self.subTest(key=key), self.assertRaises(self.module.LocalPathParentConfigurationError): self.validate(document)
        _, document = fixture()
        document['items'].remove(row(document, 'ServiceAccount'))
        with self.assertRaises(self.module.LocalPathParentConfigurationError): self.validate(document)
        _, document = fixture()
        document['items'].remove(row(document, 'Deployment'))
        with self.assertRaises(RuntimeOwnershipError): self.ownership(document)
        _, document = fixture()
        document['items'].append(deepcopy(row(document, 'ServiceAccount')))
        with self.assertRaises(RuntimeOwnershipError): self.ownership(document)

    def test_shared_metadata_rules(self):
        _, document = fixture()
        for kind in ('Deployment', 'ServiceAccount'):
            metadata = row(document, kind)['metadata']
            metadata.setdefault('annotations', {})['kubectl.kubernetes.io/last-applied-configuration'] = '{}'
            metadata['managedFields'] = [{'manager': 'kubectl', 'operation': 'Apply', 'apiVersion': 'v1',
                'fieldsType': 'FieldsV1', 'fieldsV1': {'f:metadata': {}}, 'time': '2026-09-08T01:00:00Z'}]
        self.validate(document)
        for kind in ('Deployment', 'ServiceAccount'):
            for key, value in [('managedFields', [{}]), ('annotations', {'foreign': 'value'})]:
                _, document = fixture()
                row(document, kind)['metadata'][key] = value
                with self.subTest(kind=kind, key=key), self.assertRaises((self.module.LocalPathParentConfigurationError, RuntimeOwnershipError)):
                    self.validate(document)
        _, document = fixture()
        del row(document, 'ServiceAccount')['metadata']['creationTimestamp']
        with self.assertRaises(self.module.LocalPathParentConfigurationError): self.validate(document)

    def test_template_cannot_supply_authority_and_full_pod_is_outside_scope(self):
        _, document = fixture()
        pod = next(r for r in document['items'] if r['kind'] == 'Pod' and r['metadata']['name'].startswith('local-path-provisioner-'))
        pod['spec'] = {'unreviewed': 'full Pod configuration belongs to a later proof'}
        proof = self.validate(document)
        self.assertIn(b'full Pod configuration belongs', proof.ownership.runtime_objects)
        with self.assertRaises(TypeError): self.module.validate_local_path_parent_configuration(ownership=proof.ownership, expected=[])

    def test_constructor_exact_types_reconstruction_and_flags(self):
        proof = self.validate()
        error = self.module.LocalPathParentConfigurationError
        for value in (True, 0, None):
            for flag in ('runtime_contract_complete', 'full_application_contract_complete'):
                with self.subTest(flag=flag, value=value), self.assertRaises(error): replace(proof, **{flag: value})
        for field in ('deployment_uid', 'deployment_resource_version', 'service_account_uid', 'service_account_resource_version'):
            binding = replace(proof.bindings[0], **{field: '999'})
            with self.subTest(field=field), self.assertRaises(error): replace(proof, bindings=(binding,))
            for value in (None, 1, True, ''):
                with self.subTest(field=field, value=value), self.assertRaises(error): replace(proof.bindings[0], **{field: value})
        for field in ('namespace', 'deployment_name'):
            with self.assertRaises(error): replace(proof.bindings[0], **{field: 'foreign'})
        with self.assertRaises(error): replace(proof.bindings[0], service_account_uid=proof.bindings[0].deployment_uid)
        with self.assertRaises(FrozenInstanceError): proof.bindings[0].namespace = 'foreign'
        forged = deepcopy(proof.ownership)
        object.__setattr__(forged, 'runtime_objects', b'{}')
        for owner in (None, forged):
            with self.assertRaises(error): replace(proof, ownership=owner)
        class SubOwnership(type(proof.ownership)): pass
        owner = SubOwnership(**{f: getattr(proof.ownership, f) for f in proof.ownership.__dataclass_fields__})
        with self.assertRaises(error): replace(proof, ownership=owner)
        class SubBinding(type(proof.bindings[0])): pass
        binding = SubBinding(**{f: getattr(proof.bindings[0], f) for f in proof.bindings[0].__dataclass_fields__})
        for bindings in ([proof.bindings[0]], (), (binding,), (proof.bindings[0], proof.bindings[0])):
            with self.assertRaises(error): replace(proof, bindings=bindings)


if __name__ == '__main__': unittest.main()
