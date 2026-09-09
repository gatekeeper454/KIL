"""Independent literal CoreDNS output fixture; no expected factory builds it."""
from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import json
import unittest

from kil.v3b2_runtime_ownership import validate_runtime_ownership, RuntimeOwnershipError
from tests.test_v3b2_runtime_ownership import fixture as ownership_fixture, encode

MODULE = 'kil.v3b2_coredns_parent_configuration'


def fixture():
    args = ownership_fixture()
    document = json.loads(args['runtime_objects'])
    deployment = next(r for r in document['items'] if r['kind'] == 'Deployment' and r['metadata']['name'] == 'coredns')
    deployment['metadata'].update(labels={'k8s-app': 'kube-dns'}, generation=1,
        creationTimestamp='2026-09-08T01:00:00Z')
    deployment['spec'] = {
        'replicas': 2, 'strategy': {'type': 'RollingUpdate', 'rollingUpdate': {'maxUnavailable': 1, 'maxSurge': '25%'}},
        'selector': {'matchLabels': {'k8s-app': 'kube-dns'}},
        'template': {'metadata': {'labels': {'k8s-app': 'kube-dns'}}, 'spec': {
            'priorityClassName': 'system-cluster-critical', 'serviceAccountName': 'coredns',
            'affinity': {'podAntiAffinity': {'preferredDuringSchedulingIgnoredDuringExecution': [{
                'weight': 100, 'podAffinityTerm': {'labelSelector': {'matchExpressions': [{
                    'key': 'k8s-app', 'operator': 'In', 'values': ['kube-dns']}]},
                    'topologyKey': 'kubernetes.io/hostname'}}]}},
            'tolerations': [{'key': 'CriticalAddonsOnly', 'operator': 'Exists'},
                {'key': 'node-role.kubernetes.io/control-plane', 'effect': 'NoSchedule'}],
            'nodeSelector': {'kubernetes.io/os': 'linux'}, 'dnsPolicy': 'Default',
            'containers': [{'name': 'coredns', 'image': 'registry.k8s.io/coredns/coredns:v1.14.2',
                'imagePullPolicy': 'IfNotPresent',
                'resources': {'limits': {'memory': '170Mi'}, 'requests': {'cpu': '100m', 'memory': '70Mi'}},
                'args': ['-conf', '/etc/coredns/Corefile'],
                'volumeMounts': [{'name': 'config-volume', 'mountPath': '/etc/coredns', 'readOnly': True}],
                'ports': [{'containerPort': 53, 'name': 'dns', 'protocol': 'UDP'},
                    {'containerPort': 53, 'name': 'dns-tcp', 'protocol': 'TCP'},
                    {'containerPort': 9153, 'name': 'metrics', 'protocol': 'TCP'},
                    {'containerPort': 8080, 'name': 'liveness-probe', 'protocol': 'TCP'},
                    {'containerPort': 8181, 'name': 'readiness-probe', 'protocol': 'TCP'}],
                'livenessProbe': {'httpGet': {'path': '/health', 'port': 'liveness-probe', 'scheme': 'HTTP'},
                    'initialDelaySeconds': 60, 'timeoutSeconds': 5, 'successThreshold': 1, 'failureThreshold': 5},
                'readinessProbe': {'httpGet': {'path': '/ready', 'port': 'readiness-probe', 'scheme': 'HTTP'}},
                'securityContext': {'allowPrivilegeEscalation': False,
                    'capabilities': {'add': ['NET_BIND_SERVICE'], 'drop': ['ALL']}, 'readOnlyRootFilesystem': True}}],
            'volumes': [{'name': 'config-volume', 'configMap': {'name': 'coredns',
                'items': [{'key': 'Corefile', 'path': 'Corefile'}]}}]}}}
    document['items'].append({'apiVersion': 'v1', 'kind': 'ServiceAccount', 'metadata': {
        'name': 'coredns', 'namespace': 'kube-system', 'uid': 'coredns-sa', 'resourceVersion': '100',
        'creationTimestamp': '2026-09-08T01:00:00Z'}})
    return args, document


def row(document, kind):
    return next(r for r in document['items'] if r['kind'] == kind and r['metadata']['name'] == 'coredns')


class CoreDNSParentConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'CoreDNS parent configuration adapter is missing')
        self.module = importlib.import_module(MODULE)

    def ownership(self, document=None):
        args, default = fixture()
        args['runtime_objects'] = encode(default if document is None else document)
        return validate_runtime_ownership(**args)

    def validate(self, document=None):
        return self.module.validate_coredns_parent_configuration(ownership=self.ownership(document))

    def test_complete_parent_config_preserves_full_raw_and_chain(self):
        _, document = fixture()
        row(document, 'Deployment')['status'] = {'readyReplicas': 0, 'unreviewed': ['retained']}
        row(document, 'ServiceAccount')['status'] = {'arbitrary': False}
        proof = self.validate(document)
        self.assertEqual(proof.ownership.runtime_objects, encode(document))
        relation = next(b for b in proof.ownership.deployment_ownership.bindings if b.deployment_name == 'coredns')
        self.assertEqual(len(relation.pods), 2)
        self.assertEqual(proof.bindings[0].deployment_uid, row(document, 'Deployment')['metadata']['uid'])
        self.assertEqual(proof.bindings[0].service_account_uid, 'coredns-sa')
        self.assertFalse(proof.runtime_contract_complete)
        self.assertFalse(proof.full_application_contract_complete)
        self.assertEqual(replace(proof), proof)

    def test_factory_is_fresh_independent_literal(self):
        first = self.module.coredns_parent_objects()
        second = self.module.coredns_parent_objects()
        self.assertEqual(first, second)
        first[0]['spec']['template']['spec']['containers'][0]['image'] = 'poison'
        first[1]['metadata']['labels'] = {'poison': 'yes'}
        self.assertEqual(second, self.module.coredns_parent_objects())
        self.validate()

    def test_independently_serialized_reviewed_defaults(self):
        _, document = fixture()
        spec = row(document, 'Deployment')['spec']
        spec.update(revisionHistoryLimit=10, progressDeadlineSeconds=600)
        spec['template']['metadata']['creationTimestamp'] = None
        pod = spec['template']['spec']
        pod.update(serviceAccount='coredns', restartPolicy='Always', securityContext={},
            terminationGracePeriodSeconds=30, schedulerName='default-scheduler')
        pod['volumes'][0]['configMap']['defaultMode'] = 420
        container = pod['containers'][0]
        container.update(terminationMessagePath='/dev/termination-log', terminationMessagePolicy='File')
        container['livenessProbe']['periodSeconds'] = 10
        container['readinessProbe'].update(timeoutSeconds=1, periodSeconds=10, successThreshold=1, failureThreshold=3)
        self.validate(document)

    def test_config_drift_fails_after_ownership_passes(self):
        mutations = [
            (('spec', 'strategy', 'rollingUpdate', 'maxSurge'), 25),
            (('spec', 'strategy', 'rollingUpdate', 'maxUnavailable'), True),
            (('spec', 'template', 'spec', 'containers', 0, 'image'), 'foreign'),
            (('spec', 'template', 'spec', 'containers', 0, 'resources', 'limits', 'memory'), '171Mi'),
            (('spec', 'template', 'spec', 'containers', 0, 'ports', 0, 'containerPort'), 54),
            (('spec', 'template', 'spec', 'containers', 0, 'readinessProbe', 'httpGet', 'path'), '/wrong'),
            (('spec', 'template', 'spec', 'affinity'), {}),
            (('spec', 'template', 'spec', 'tolerations'), []),
            (('spec', 'template', 'metadata', 'labels'), {'k8s-app': 'foreign'}),
            (('spec', 'template', 'spec', 'enableServiceLinks'), True),
            (('spec', 'foreign'), 1), (('foreign',), {}),
            (('metadata', 'generation'), 2), (('metadata', 'generation'), True),
            (('metadata', 'finalizers'), []), (('metadata', 'ownerReferences'), []),
            (('metadata', 'deletionTimestamp'), None),
            (('metadata', 'annotations', 'foreign'), 'value'),
        ]
        for path, value in mutations:
            _, document = fixture()
            target = row(document, 'Deployment')
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path, value=value):
                ownership = self.ownership(document)
                with self.assertRaises(self.module.CoreDNSParentConfigurationError):
                    self.module.validate_coredns_parent_configuration(ownership=ownership)

    def test_missing_required_metadata_and_maxsurge_fail(self):
        for path in [('metadata', 'generation'), ('metadata', 'creationTimestamp'), ('metadata', 'labels'),
                     ('spec', 'strategy', 'rollingUpdate', 'maxSurge')]:
            _, document = fixture()
            target = row(document, 'Deployment')
            for key in path[:-1]: target = target[key]
            del target[path[-1]]
            with self.subTest(path=path), self.assertRaises(self.module.CoreDNSParentConfigurationError): self.validate(document)

    def test_service_account_complete_configuration(self):
        for key, value in [('automountServiceAccountToken', False), ('secrets', []), ('imagePullSecrets', []), ('spec', {})]:
            _, document = fixture()
            row(document, 'ServiceAccount')[key] = value
            with self.subTest(key=key), self.assertRaises(self.module.CoreDNSParentConfigurationError): self.validate(document)
        for key, value in [('labels', {}), ('ownerReferences', []), ('finalizers', []), ('creationTimestamp', 'invalid')]:
            _, document = fixture()
            row(document, 'ServiceAccount')['metadata'][key] = value
            with self.subTest(key=key), self.assertRaises(self.module.CoreDNSParentConfigurationError): self.validate(document)
        _, document = fixture()
        document['items'].remove(row(document, 'ServiceAccount'))
        with self.assertRaises(self.module.CoreDNSParentConfigurationError): self.validate(document)

    def test_reviewed_annotations_managed_fields_and_metadata_validation(self):
        _, document = fixture()
        for kind in ('Deployment', 'ServiceAccount'):
            metadata = row(document, kind)['metadata']
            metadata.setdefault('annotations', {})['kubectl.kubernetes.io/last-applied-configuration'] = '{}'
            metadata['managedFields'] = [{'manager': 'kubeadm', 'operation': 'Update', 'apiVersion': 'v1',
                'fieldsType': 'FieldsV1', 'fieldsV1': {'f:metadata': {}}, 'time': '2026-09-08T01:00:00Z'}]
        self.validate(document)
        for kind, field, value in [('Deployment', 'managedFields', [{}]),
                                  ('ServiceAccount', 'managedFields', [{}]),
                                  ('ServiceAccount', 'annotations', {'foreign': 'value'}),
                                  ('Deployment', 'creationTimestamp', 'invalid')]:
            _, document = fixture()
            row(document, kind)['metadata'][field] = value
            with self.subTest(kind=kind, field=field), self.assertRaises(self.module.CoreDNSParentConfigurationError):
                self.validate(document)
        _, document = fixture()
        del row(document, 'ServiceAccount')['metadata']['creationTimestamp']
        with self.assertRaises(self.module.CoreDNSParentConfigurationError): self.validate(document)

    def test_ordered_ports_and_unreviewed_toleration_default_rejected(self):
        for change in ('ports', 'operator'):
            _, document = fixture()
            pod = row(document, 'Deployment')['spec']['template']['spec']
            if change == 'ports': pod['containers'][0]['ports'].reverse()
            else: pod['tolerations'][1]['operator'] = 'Equal'
            with self.subTest(change=change), self.assertRaises(self.module.CoreDNSParentConfigurationError): self.validate(document)

    def test_no_caller_expected_override_and_no_pod_configuration_claim(self):
        _, document = fixture()
        pod = next(r for r in document['items'] if r['kind'] == 'Pod'
            and r['metadata']['name'].startswith('coredns-'))
        pod['spec'] = {'unreviewed': 'full Pod configuration belongs to next proof'}
        proof = self.validate(document)
        self.assertIn(b'full Pod configuration belongs', proof.ownership.runtime_objects)
        with self.assertRaises(TypeError):
            self.module.validate_coredns_parent_configuration(ownership=proof.ownership, expected=[])

    def test_replicas_duplicate_account_and_missing_owner_rejected_by_dependency(self):
        for count in (True, 1, 3):
            _, document = fixture()
            row(document, 'Deployment')['spec']['replicas'] = count
            with self.assertRaises(RuntimeOwnershipError): self.ownership(document)
        _, document = fixture()
        document['items'].append(deepcopy(row(document, 'ServiceAccount')))
        with self.assertRaises(RuntimeOwnershipError): self.ownership(document)
        _, document = fixture()
        next(r for r in document['items'] if r['kind'] == 'ReplicaSet')['metadata'].pop('ownerReferences')
        with self.assertRaises(RuntimeOwnershipError): self.ownership(document)

    def test_constructor_reconstructs_bindings_and_strict_flags(self):
        proof = self.validate()
        for value in (True, 0, None):
            for flag in ('runtime_contract_complete', 'full_application_contract_complete'):
                with self.assertRaises(self.module.CoreDNSParentConfigurationError): replace(proof, **{flag: value})
        for field in ('deployment_uid', 'deployment_resource_version', 'service_account_uid', 'service_account_resource_version'):
            binding = replace(proof.bindings[0], **{field: '999'})
            with self.subTest(field=field), self.assertRaises(self.module.CoreDNSParentConfigurationError): replace(proof, bindings=(binding,))
        forged = deepcopy(proof.ownership)
        object.__setattr__(forged, 'runtime_objects', b'{}')
        for owner in (None, forged):
            with self.assertRaises(self.module.CoreDNSParentConfigurationError): replace(proof, ownership=owner)
        class SubOwnership(type(proof.ownership)): pass
        owner = SubOwnership(**{f: getattr(proof.ownership, f) for f in proof.ownership.__dataclass_fields__})
        with self.assertRaises(self.module.CoreDNSParentConfigurationError): replace(proof, ownership=owner)
        class SubBinding(type(proof.bindings[0])): pass
        binding = SubBinding(**{f: getattr(proof.bindings[0], f) for f in proof.bindings[0].__dataclass_fields__})
        for bindings in ([proof.bindings[0]], (), (binding,)):
            with self.assertRaises(self.module.CoreDNSParentConfigurationError): replace(proof, bindings=bindings)


if __name__ == '__main__': unittest.main()
