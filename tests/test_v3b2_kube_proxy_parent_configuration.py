"""Independent literal kubeadm no-inherited-proxy output; no expected factory."""
from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import json
import unittest

from kil.v3b2_runtime_ownership import validate_runtime_ownership, RuntimeOwnershipError
from tests.test_v3b2_runtime_ownership import fixture as ownership_fixture, encode

MODULE = 'kil.v3b2_kube_proxy_parent_configuration'


def fixture():
    args = ownership_fixture()
    document = json.loads(args['runtime_objects'])
    daemon = row(document, 'DaemonSet')
    daemon['metadata'].update(labels={'k8s-app': 'kube-proxy'}, generation=1,
        creationTimestamp='2026-09-08T01:00:00Z')
    daemon['spec'] = {
        'selector': {'matchLabels': {'k8s-app': 'kube-proxy'}},
        'updateStrategy': {'type': 'RollingUpdate', 'rollingUpdate': {'maxUnavailable': 1, 'maxSurge': 0}},
        'template': {'metadata': {'labels': {'k8s-app': 'kube-proxy'}}, 'spec': {
            'priorityClassName': 'system-node-critical',
            'containers': [{'name': 'kube-proxy', 'image': 'registry.k8s.io/kube-proxy:v1.36.1',
                'imagePullPolicy': 'IfNotPresent',
                'command': ['/usr/local/bin/kube-proxy', '--config=/var/lib/kube-proxy/config.conf',
                    '--hostname-override=$(NODE_NAME)'],
                'securityContext': {'privileged': True},
                'volumeMounts': [{'mountPath': '/var/lib/kube-proxy', 'name': 'kube-proxy'},
                    {'mountPath': '/run/xtables.lock', 'name': 'xtables-lock', 'readOnly': False},
                    {'mountPath': '/lib/modules', 'name': 'lib-modules', 'readOnly': True}],
                'env': [{'name': 'NODE_NAME', 'valueFrom': {'fieldRef': {'fieldPath': 'spec.nodeName'}}}]}],
            'hostNetwork': True, 'serviceAccountName': 'kube-proxy',
            'volumes': [{'name': 'kube-proxy', 'configMap': {'name': 'kube-proxy'}},
                {'name': 'xtables-lock', 'hostPath': {'path': '/run/xtables.lock', 'type': 'FileOrCreate'}},
                {'name': 'lib-modules', 'hostPath': {'path': '/lib/modules'}}],
            'tolerations': [{'operator': 'Exists'}], 'nodeSelector': {'kubernetes.io/os': 'linux'}}}}
    document['items'].append({'apiVersion': 'v1', 'kind': 'ServiceAccount', 'metadata': {
        'name': 'kube-proxy', 'namespace': 'kube-system', 'uid': 'kube-proxy-sa',
        'resourceVersion': '100', 'creationTimestamp': '2026-09-08T01:00:00Z'}})
    return args, document


def row(document, kind):
    return next(r for r in document['items'] if r['kind'] == kind and r['metadata']['name'] == 'kube-proxy')


class KubeProxyParentConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'kube-proxy parent configuration adapter is missing')
        self.module = importlib.import_module(MODULE)

    def ownership(self, document=None):
        args, default = fixture()
        args['runtime_objects'] = encode(default if document is None else document)
        return validate_runtime_ownership(**args)

    def validate(self, document=None):
        return self.module.validate_kube_proxy_parent_configuration(ownership=self.ownership(document))

    def test_parent_proof_retains_raw_status_and_owned_daemon_chain(self):
        _, document = fixture()
        row(document, 'DaemonSet')['status'].update(numberReady=0, unreviewed=['retained'])
        row(document, 'ServiceAccount')['status'] = {'arbitrary': False}
        ownership = self.ownership(document)
        proof = self.module.validate_kube_proxy_parent_configuration(ownership=ownership)
        self.assertIs(proof.ownership, ownership)
        self.assertEqual(proof.ownership.runtime_objects, encode(document))
        chain = next(b for b in ownership.node_ownership.daemon_pods if b.daemon_set_name == 'kube-proxy')
        self.assertEqual(proof.bindings[0].daemon_set_uid, chain.daemon_set_uid)
        self.assertEqual(proof.bindings[0].daemon_set_resource_version, chain.daemon_set_resource_version)
        self.assertEqual(proof.bindings[0].service_account_uid, 'kube-proxy-sa')
        self.assertEqual(proof.bindings[0].service_account_resource_version, '100')
        self.assertFalse(proof.runtime_contract_complete)
        self.assertFalse(proof.full_application_contract_complete)
        self.assertEqual(replace(proof), proof)

    def test_factory_fresh_nested_literals(self):
        first = self.module.kube_proxy_parent_objects()
        second = self.module.kube_proxy_parent_objects()
        self.assertEqual([r['kind'] for r in first], ['DaemonSet', 'ServiceAccount'])
        self.assertEqual(first, second)
        first[0]['spec']['template']['spec']['containers'][0]['command'].append('poison')
        first[0]['spec']['template']['spec']['volumes'][0]['configMap']['name'] = 'poison'
        first[1]['metadata']['name'] = 'poison'
        self.assertEqual(second, self.module.kube_proxy_parent_objects())
        self.validate()

    def test_independent_full_serialized_defaults(self):
        _, document = fixture()
        spec = row(document, 'DaemonSet')['spec']
        spec['revisionHistoryLimit'] = 10
        spec['template']['metadata']['creationTimestamp'] = None
        pod = spec['template']['spec']
        pod.update(serviceAccount='kube-proxy', dnsPolicy='ClusterFirst', restartPolicy='Always',
            securityContext={}, terminationGracePeriodSeconds=30, schedulerName='default-scheduler')
        pod['volumes'][0]['configMap']['defaultMode'] = 420
        pod['volumes'][2]['hostPath']['type'] = ''
        container = pod['containers'][0]
        container.update(resources={}, terminationMessagePath='/dev/termination-log', terminationMessagePolicy='File')
        container['env'][0]['valueFrom']['fieldRef']['apiVersion'] = 'v1'
        self.validate(document)
        # Existing reviewed scalar default may fill maxSurge, never the whole strategy.
        del spec['updateStrategy']['rollingUpdate']['maxSurge']
        self.validate(document)

    def test_drift_rejected_after_dependency_accepts(self):
        prefix = ('spec', 'template', 'spec')
        container = (*prefix, 'containers', 0)
        mutations = [
            (('spec', 'updateStrategy', 'rollingUpdate', 'maxUnavailable'), True),
            (('spec', 'updateStrategy', 'rollingUpdate', 'maxUnavailable'), '1'),
            (('spec', 'updateStrategy', 'rollingUpdate', 'maxSurge'), False),
            (('spec', 'updateStrategy', 'rollingUpdate', 'maxSurge'), '0'),
            (('spec', 'updateStrategy', 'type'), 'OnDelete'),
            (('spec', 'selector', 'matchLabels'), {'k8s-app': 'foreign'}),
            (('spec', 'template', 'metadata', 'labels'), {'k8s-app': 'foreign'}),
            ((*container, 'image'), 'registry.k8s.io/kube-proxy:v1.36.0'),
            ((*container, 'imagePullPolicy'), 'Always'),
            ((*container, 'name'), 'foreign'),
            ((*container, 'command', 0), '/bin/kube-proxy'),
            ((*container, 'command', 1), '--config=/foreign'),
            ((*container, 'command', 2), '--hostname-override=expanded'),
            ((*container, 'env', 0, 'valueFrom', 'fieldRef', 'fieldPath'), 'metadata.name'),
            ((*container, 'env', 0, 'name'), 'FOREIGN'),
            ((*container, 'securityContext', 'privileged'), 1),
            ((*container, 'volumeMounts', 1, 'readOnly'), True),
            ((*container, 'volumeMounts', 2, 'readOnly'), False),
            ((*prefix, 'volumes', 0, 'configMap', 'name'), 'foreign'),
            ((*prefix, 'volumes', 1, 'hostPath', 'type'), 'File'),
            ((*prefix, 'volumes', 1, 'hostPath', 'path'), '/foreign'),
            ((*prefix, 'volumes', 2, 'hostPath', 'path'), '/foreign'),
            ((*prefix, 'hostNetwork'), 1),
            ((*prefix, 'serviceAccountName'), 'foreign'),
            ((*prefix, 'priorityClassName'), 'system-cluster-critical'),
            ((*prefix, 'nodeSelector'), {}),
            ((*prefix, 'tolerations'), []),
            ((*prefix, 'terminationGracePeriodSeconds'), 31),
            (('foreign',), {}), (('spec', 'foreign'), {}),
            (('metadata', 'generation'), 2), (('metadata', 'generation'), True),
            (('metadata', 'creationTimestamp'), 'invalid'),
            (('metadata', 'finalizers'), []), (('metadata', 'ownerReferences'), []),
            (('metadata', 'labels'), {'k8s-app': 'foreign'}),
            (('metadata', 'deletionTimestamp'), None),
            (('metadata', 'annotations'), {'foreign': 'value'}),
        ]
        for path, value in mutations:
            _, document = fixture()
            target = row(document, 'DaemonSet')
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path, value=value):
                ownership = self.ownership(document)
                with self.assertRaises(self.module.KubeProxyParentConfigurationError):
                    self.module.validate_kube_proxy_parent_configuration(ownership=ownership)

    def test_unreviewed_template_and_container_fields(self):
        extras = [('pod', 'initContainers', []), ('pod', 'affinity', {}),
            ('pod', 'automountServiceAccountToken', True), ('pod', 'priority', 2000001000),
            ('pod', 'preemptionPolicy', 'PreemptLowerPriority'), ('pod', 'enableServiceLinks', True),
            ('container', 'ports', []), ('container', 'livenessProbe', {}),
            ('container', 'resources', {'requests': {'cpu': '100m'}}), ('container', 'args', [])]
        for where, key, value in extras:
            _, document = fixture()
            pod = row(document, 'DaemonSet')['spec']['template']['spec']
            target = pod if where == 'pod' else pod['containers'][0]
            target[key] = value
            with self.subTest(where=where, key=key), self.assertRaises(self.module.KubeProxyParentConfigurationError):
                self.validate(document)

    def test_order_and_inherited_proxy_environment_rejected(self):
        for field in ('command', 'volumeMounts', 'volumes', 'proxy', 'extra-container'):
            _, document = fixture()
            pod = row(document, 'DaemonSet')['spec']['template']['spec']
            container = pod['containers'][0]
            if field == 'volumes': pod['volumes'].reverse()
            elif field == 'proxy': container['env'].append({'name': 'HTTP_PROXY', 'value': 'http://proxy.invalid'})
            elif field == 'extra-container': pod['containers'].append(deepcopy(container))
            else: container[field].reverse()
            with self.subTest(field=field), self.assertRaises(self.module.KubeProxyParentConfigurationError): self.validate(document)

    def test_required_parent_fields_and_metadata(self):
        for path in [('metadata', 'generation'), ('metadata', 'creationTimestamp'), ('metadata', 'labels'),
                     ('spec',), ('spec', 'updateStrategy'), ('spec', 'updateStrategy', 'rollingUpdate'),
                     ('spec', 'updateStrategy', 'rollingUpdate', 'maxUnavailable')]:
            _, document = fixture()
            target = row(document, 'DaemonSet')
            for key in path[:-1]: target = target[key]
            del target[path[-1]]
            with self.subTest(path=path), self.assertRaises(self.module.KubeProxyParentConfigurationError): self.validate(document)

    def test_service_account_extras_missing_and_duplicate_objects(self):
        for key, value in [('automountServiceAccountToken', False), ('secrets', []), ('imagePullSecrets', []), ('spec', {})]:
            _, document = fixture()
            row(document, 'ServiceAccount')[key] = value
            with self.subTest(key=key), self.assertRaises(self.module.KubeProxyParentConfigurationError): self.validate(document)
        for key, value in [('labels', {}), ('ownerReferences', []), ('finalizers', []), ('creationTimestamp', 'invalid')]:
            _, document = fixture()
            row(document, 'ServiceAccount')['metadata'][key] = value
            with self.subTest(key=key), self.assertRaises(self.module.KubeProxyParentConfigurationError): self.validate(document)
        _, document = fixture()
        del row(document, 'ServiceAccount')['metadata']['creationTimestamp']
        with self.assertRaises(self.module.KubeProxyParentConfigurationError): self.validate(document)
        _, document = fixture()
        document['items'].remove(row(document, 'ServiceAccount'))
        with self.assertRaises(self.module.KubeProxyParentConfigurationError): self.validate(document)
        _, document = fixture()
        document['items'].remove(row(document, 'DaemonSet'))
        with self.assertRaises(RuntimeOwnershipError): self.ownership(document)
        _, document = fixture()
        document['items'].append(deepcopy(row(document, 'ServiceAccount')))
        with self.assertRaises(RuntimeOwnershipError): self.ownership(document)

    def test_reviewed_runtime_metadata_and_invalid_managed_fields(self):
        _, document = fixture()
        for kind in ('DaemonSet', 'ServiceAccount'):
            metadata = row(document, kind)['metadata']
            metadata['annotations'] = {'kubectl.kubernetes.io/last-applied-configuration': '{}'}
            metadata['managedFields'] = [{'manager': 'kubeadm', 'operation': 'Update', 'apiVersion': 'v1',
                'fieldsType': 'FieldsV1', 'fieldsV1': {'f:metadata': {}}, 'time': '2026-09-08T01:00:00Z'}]
        self.validate(document)
        for kind in ('DaemonSet', 'ServiceAccount'):
            _, document = fixture()
            row(document, kind)['metadata']['managedFields'] = [{}]
            with self.subTest(kind=kind), self.assertRaises(self.module.KubeProxyParentConfigurationError): self.validate(document)

    def test_unreviewed_owned_pod_config_does_not_become_runtime_proof(self):
        _, document = fixture()
        pod = next(r for r in document['items'] if r['kind'] == 'Pod'
            and r['metadata'].get('ownerReferences', [{}])[0].get('name') == 'kube-proxy')
        pod['spec']['unreviewed'] = 'Pod configuration remains outside proof'
        proof = self.validate(document)
        self.assertIn(b'Pod configuration remains outside proof', proof.ownership.runtime_objects)
        self.assertFalse(proof.runtime_contract_complete)
        with self.assertRaises(TypeError): self.module.validate_kube_proxy_parent_configuration(ownership=proof.ownership, expected=[])

    def test_constructor_reconstruction_exact_types_and_strict_flags(self):
        proof = self.validate()
        for value in (True, 0, None):
            for flag in ('runtime_contract_complete', 'full_application_contract_complete'):
                with self.assertRaises(self.module.KubeProxyParentConfigurationError): replace(proof, **{flag: value})
        for field in ('daemon_set_uid', 'daemon_set_resource_version', 'service_account_uid', 'service_account_resource_version'):
            binding = replace(proof.bindings[0], **{field: '999'})
            with self.subTest(field=field), self.assertRaises(self.module.KubeProxyParentConfigurationError): replace(proof, bindings=(binding,))
        for field, value in [('namespace', 'default'), ('daemon_set_name', 'foreign'),
                             ('daemon_set_uid', None), ('daemon_set_resource_version', True),
                             ('service_account_uid', proof.bindings[0].daemon_set_uid)]:
            with self.subTest(field=field), self.assertRaises(self.module.KubeProxyParentConfigurationError):
                replace(proof.bindings[0], **{field: value})
        forged = deepcopy(proof.ownership)
        object.__setattr__(forged, 'runtime_objects', b'{}')
        forged_chain = deepcopy(proof.ownership)
        object.__setattr__(forged_chain.node_ownership, 'node_uid', 'foreign')
        for owner in (None, forged, forged_chain):
            with self.assertRaises(self.module.KubeProxyParentConfigurationError): replace(proof, ownership=owner)
        class SubOwnership(type(proof.ownership)): pass
        owner = SubOwnership(**{f: getattr(proof.ownership, f) for f in proof.ownership.__dataclass_fields__})
        with self.assertRaises(self.module.KubeProxyParentConfigurationError): replace(proof, ownership=owner)
        class SubBinding(type(proof.bindings[0])): pass
        binding = SubBinding(**{f: getattr(proof.bindings[0], f) for f in proof.bindings[0].__dataclass_fields__})
        for bindings in ([proof.bindings[0]], (), (binding,), (proof.bindings[0], proof.bindings[0])):
            with self.assertRaises(self.module.KubeProxyParentConfigurationError): replace(proof, bindings=bindings)


if __name__ == '__main__': unittest.main()
