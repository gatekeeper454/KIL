"""Independent observed parent fixture and literal typed-template serialization."""
from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import json
import unittest

from kil.v3b2_runtime_ownership import validate_runtime_ownership
from kil.v3b2_kube_proxy_parent_configuration import validate_kube_proxy_parent_configuration
from tests.test_v3b2_kube_proxy_parent_configuration import fixture as parent_fixture, row
from tests.test_v3b2_runtime_ownership import encode

MODULE = 'kil.v3b2_kube_proxy_revision'


def fixture():
    args, document = parent_fixture()
    daemon = row(document, 'DaemonSet')
    pod = next(r for r in document['items'] if r['kind'] == 'Pod'
        and r['metadata'].get('ownerReferences', [{}])[0].get('name') == 'kube-proxy')
    pod['metadata'].setdefault('labels', {})['controller-revision-hash'] = 'abc123'
    template = deepcopy(daemon['spec']['template'])
    template['$patch'] = 'replace'
    spec = template['spec']
    spec.update(serviceAccount='kube-proxy', dnsPolicy='ClusterFirst', restartPolicy='Always',
        securityContext={}, terminationGracePeriodSeconds=30, schedulerName='default-scheduler')
    spec['volumes'][0]['configMap']['defaultMode'] = 420
    spec['volumes'][2]['hostPath']['type'] = ''
    container = spec['containers'][0]
    container.update(resources={}, terminationMessagePath='/dev/termination-log', terminationMessagePolicy='File')
    container['env'][0]['valueFrom']['fieldRef']['apiVersion'] = 'v1'
    del container['volumeMounts'][1]['readOnly']
    document['items'].append({'apiVersion': 'apps/v1', 'kind': 'ControllerRevision',
        'metadata': {'name': 'kube-proxy-abc123', 'namespace': 'kube-system', 'uid': 'proxy-revision',
            'resourceVersion': '101', 'creationTimestamp': '2026-09-08T01:00:00Z',
            'labels': {'k8s-app': 'kube-proxy', 'controller-revision-hash': 'abc123'},
            'ownerReferences': [{'apiVersion': 'apps/v1', 'kind': 'DaemonSet', 'name': 'kube-proxy',
                'uid': daemon['metadata']['uid'], 'controller': True, 'blockOwnerDeletion': True}]},
        'revision': 1, 'data': {'spec': {'template': template}}})
    return args, document


def revision(document):
    return next(r for r in document['items'] if r['kind'] == 'ControllerRevision')


class KubeProxyRevisionTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'kube-proxy revision adapter is missing')
        self.module = importlib.import_module(MODULE)

    def parent(self, document=None):
        args, default = fixture()
        args['runtime_objects'] = encode(default if document is None else document)
        return validate_kube_proxy_parent_configuration(ownership=validate_runtime_ownership(**args))

    def validate(self, document=None):
        return self.module.validate_kube_proxy_revision(parent=self.parent(document))

    def test_exact_parent_identity_raw_retention_and_binding(self):
        parent = self.parent()
        proof = self.module.validate_kube_proxy_revision(parent=parent)
        self.assertIs(proof.parent, parent)
        self.assertEqual(proof.parent.ownership.runtime_objects, encode(fixture()[1]))
        chain = next(b for b in parent.ownership.node_ownership.daemon_pods if b.daemon_set_name == 'kube-proxy')
        binding = proof.bindings[0]
        for field in ('daemon_set_uid', 'daemon_set_resource_version', 'pod_name', 'pod_uid', 'pod_resource_version'):
            self.assertEqual(getattr(binding, field), getattr(chain, field))
        self.assertEqual(binding.revision_name, 'kube-proxy-abc123')
        self.assertEqual(binding.revision_uid, 'proxy-revision')
        self.assertFalse(proof.runtime_contract_complete)
        self.assertFalse(proof.full_application_contract_complete)
        self.assertEqual(replace(proof), proof)

    def test_consistent_opaque_rename(self):
        _, doc = fixture()
        rev = revision(doc)
        rev['metadata']['name'] = 'kube-proxy-z9'
        rev['metadata']['labels']['controller-revision-hash'] = 'z9'
        pod = next(r for r in doc['items'] if r['kind'] == 'Pod' and r['metadata'].get('labels', {}).get('controller-revision-hash') == 'abc123')
        pod['metadata']['labels']['controller-revision-hash'] = 'z9'
        self.assertEqual(self.validate(doc).bindings[0].revision_label, 'z9')

    def test_unrelated_revision_and_labeled_service_account_are_retained(self):
        _, doc = fixture()
        doc['items'].extend([
            {'apiVersion': 'apps/v1', 'kind': 'ControllerRevision', 'metadata': {
                'name': 'calico-node-abc', 'namespace': 'kube-system', 'uid': 'unrelated-cr', 'resourceVersion': '102'}, 'data': {'uncertified': True}},
            {'apiVersion': 'v1', 'kind': 'ServiceAccount', 'metadata': {
                'name': 'unrelated', 'namespace': 'kube-system', 'uid': 'unrelated-sa', 'resourceVersion': '103', 'labels': {'k8s-app': 'kube-proxy'}}}])
        self.assertEqual(self.validate(doc).parent.ownership.runtime_objects, encode(doc))

    def test_raw_patch_defaults_omissions_types_order_and_admission_fail_closed(self):
        paths = [(('metadata', 'creationTimestamp'), None), (('spec', 'priority'), 2000001000),
            (('spec', 'preemptionPolicy'), 'PreemptLowerPriority'), (('spec', 'enableServiceLinks'), True),
            (('spec', 'automountServiceAccountToken'), True), (('spec', 'affinity'), {}),
            (('spec', 'tolerations'), []), (('spec', 'terminationGracePeriodSeconds'), True),
            (('spec', 'containers', 0, 'resources'), None),
            (('spec', 'containers', 0, 'volumeMounts', 1, 'readOnly'), False),
            (('spec', 'containers', 0, 'securityContext', 'privileged'), 1),
            (('$patch',), 'merge'), (('foreign',), {})]
        for path, value in paths:
            _, doc = fixture()
            target = revision(doc)['data']['spec']['template']
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(self.module.KubeProxyRevisionError): self.validate(doc)
        for key in ('serviceAccount', 'dnsPolicy', 'restartPolicy', 'securityContext', 'terminationGracePeriodSeconds', 'schedulerName'):
            _, doc = fixture()
            del revision(doc)['data']['spec']['template']['spec'][key]
            with self.subTest(missing=key), self.assertRaises(self.module.KubeProxyRevisionError): self.validate(doc)
        _, doc = fixture()
        revision(doc)['data']['spec']['template']['spec']['containers'][0]['command'].reverse()
        with self.assertRaises(self.module.KubeProxyRevisionError): self.validate(doc)

    def test_revision_closed_root_metadata_and_owner(self):
        mutations = [(('revision',), True), (('revision',), 2), (('revision',), '1'),
            (('apiVersion',), 'apps/v2'), (('status',), {}), (('foreign',), {}),
            (('metadata', 'generation'), 1), (('metadata', 'finalizers'), []),
            (('metadata', 'deletionTimestamp'), None), (('metadata', 'foreign'), {}),
            (('metadata', 'creationTimestamp'), 'invalid'), (('metadata', 'managedFields'), [{}]),
            (('metadata', 'ownerReferences', 0, 'controller'), 1),
            (('metadata', 'ownerReferences', 0, 'blockOwnerDeletion'), False),
            (('metadata', 'ownerReferences', 0, 'kind'), 'Deployment'),
            (('metadata', 'ownerReferences', 0, 'uid'), 'foreign'),
            (('metadata', 'labels', 'foreign'), 'extra'),
            (('metadata', 'labels', 'controller-revision-hash'), 'different')]
        for path, value in mutations:
            _, doc = fixture()
            target = revision(doc)
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(self.module.KubeProxyRevisionError): self.validate(doc)
        for key in ('creationTimestamp', 'labels', 'ownerReferences'):
            _, doc = fixture()
            del revision(doc)['metadata'][key]
            with self.subTest(missing=key), self.assertRaises(self.module.KubeProxyRevisionError): self.validate(doc)

    def test_nested_patch_serialization_fields_are_required_and_exact(self):
        paths = [('spec', 'containers', 0, 'resources'),
            ('spec', 'containers', 0, 'terminationMessagePath'),
            ('spec', 'containers', 0, 'terminationMessagePolicy'),
            ('spec', 'containers', 0, 'env', 0, 'valueFrom', 'fieldRef', 'apiVersion'),
            ('spec', 'volumes', 0, 'configMap', 'defaultMode'),
            ('spec', 'volumes', 2, 'hostPath', 'type')]
        for path in paths:
            _, doc = fixture()
            target = revision(doc)['data']['spec']['template']
            for key in path[:-1]: target = target[key]
            del target[path[-1]]
            with self.subTest(missing=path), self.assertRaises(self.module.KubeProxyRevisionError): self.validate(doc)
        for path in [(), ('spec',)]:
            _, doc = fixture()
            target = revision(doc)['data']
            for key in path: target = target[key]
            target['foreign'] = {}
            with self.subTest(extra=path), self.assertRaises(self.module.KubeProxyRevisionError): self.validate(doc)

    def test_owned_pod_hash_must_match_but_pod_configuration_remains_uncertified(self):
        for value in (None, 'different', True):
            _, doc = fixture()
            pod = next(r for r in doc['items'] if r['kind'] == 'Pod'
                and r['metadata'].get('labels', {}).get('controller-revision-hash') == 'abc123')
            if value is None: del pod['metadata']['labels']['controller-revision-hash']
            else: pod['metadata']['labels']['controller-revision-hash'] = value
            parent = self.parent(doc)
            with self.subTest(value=value), self.assertRaises(self.module.KubeProxyRevisionError):
                self.module.validate_kube_proxy_revision(parent=parent)
        _, doc = fixture()
        pod = next(r for r in doc['items'] if r['kind'] == 'Pod'
            and r['metadata'].get('labels', {}).get('controller-revision-hash') == 'abc123')
        pod['spec']['uncertified'] = 'retained'
        self.assertIn(b'uncertified', self.validate(doc).parent.ownership.runtime_objects)

    def test_candidate_union_rejects_orphans_and_duplicates_after_parent_acceptance(self):
        for signal in ('prefix', 'label', 'owner_uid', 'owner_name'):
            for duplicate in (False, True):
                _, doc = fixture()
                orphan = deepcopy(revision(doc))
                meta = orphan['metadata']
                meta.update(name='foreign', uid='orphan-revision', labels={}, ownerReferences=[])
                if signal == 'prefix': meta['name'] = 'kube-proxy-orphan'
                elif signal == 'label': meta['labels'] = {'k8s-app': 'kube-proxy'}
                elif signal == 'owner_uid': meta['ownerReferences'] = [{'uid': row(doc, 'DaemonSet')['metadata']['uid']}]
                else: meta['ownerReferences'] = [{'name': 'kube-proxy'}]
                if not duplicate: doc['items'].remove(revision(doc))
                doc['items'].append(orphan)
                parent = self.parent(doc)
                with self.subTest(signal=signal, duplicate=duplicate), self.assertRaises(self.module.KubeProxyRevisionError):
                    self.module.validate_kube_proxy_revision(parent=parent)
        _, doc = fixture()
        doc['items'].remove(revision(doc))
        with self.assertRaises(self.module.KubeProxyRevisionError): self.validate(doc)

    def test_annotations_exact_copy_and_managed_fields(self):
        _, doc = fixture()
        annotation = {'kubectl.kubernetes.io/last-applied-configuration': '{}'}
        row(doc, 'DaemonSet')['metadata']['annotations'] = annotation
        revision(doc)['metadata']['annotations'] = deepcopy(annotation)
        revision(doc)['metadata']['managedFields'] = [{'manager': 'controller', 'operation': 'Update',
            'apiVersion': 'apps/v1', 'fieldsType': 'FieldsV1', 'fieldsV1': {'f:data': {}}}]
        self.validate(doc)
        revision(doc)['metadata']['annotations'][next(iter(annotation))] = 'different'
        parent = self.parent(doc)
        with self.assertRaises(self.module.KubeProxyRevisionError): self.module.validate_kube_proxy_revision(parent=parent)
        _, doc = fixture()
        revision(doc)['metadata']['annotations'] = {}
        self.validate(doc)
        revision(doc)['metadata']['annotations'] = {'foreign': 'value'}
        with self.assertRaises(self.module.KubeProxyRevisionError): self.validate(doc)

    def test_dependency_reconstruction_rejects_forged_source(self):
        proof = self.validate()
        for raw in (b'{}', None):
            parent = deepcopy(proof.parent)
            object.__setattr__(parent.ownership, 'runtime_objects', raw)
            with self.assertRaises(self.module.KubeProxyRevisionError): replace(proof, parent=parent)
        parent = deepcopy(proof.parent)
        doc = json.loads(parent.ownership.runtime_objects)
        row(doc, 'DaemonSet')['spec']['template']['spec']['containers'][0]['image'] = 'poison'
        object.__setattr__(parent.ownership, 'runtime_objects', encode(doc))
        with self.assertRaises(self.module.KubeProxyRevisionError): replace(proof, parent=parent)
        parent = deepcopy(proof.parent)
        object.__setattr__(parent.ownership.node_ownership, 'node_uid', 'foreign')
        with self.assertRaises(self.module.KubeProxyRevisionError): replace(proof, parent=parent)

    def test_exact_constructors_bindings_flags_and_subclasses(self):
        proof = self.validate()
        for flag in ('runtime_contract_complete', 'full_application_contract_complete'):
            for value in (True, 0, None):
                with self.assertRaises(self.module.KubeProxyRevisionError): replace(proof, **{flag: value})
        for field, value in [('namespace', 'default'), ('daemon_set_name', 'foreign'), ('pod_name', 'kube-proxy-too-long'),
                ('revision_label', ''), ('revision_label', 'abcdefghijk'), ('revision_label', 'UPPER'),
                ('revision_name', 'foreign'), ('revision_uid', proof.bindings[0].pod_uid),
                ('revision_resource_version', True), ('pod_uid', None)]:
            with self.subTest(field=field), self.assertRaises(self.module.KubeProxyRevisionError): replace(proof.bindings[0], **{field: value})
        for field in ('revision_uid', 'revision_resource_version', 'pod_uid', 'pod_resource_version', 'daemon_set_uid', 'daemon_set_resource_version'):
            binding = replace(proof.bindings[0], **{field: '999'})
            with self.assertRaises(self.module.KubeProxyRevisionError): replace(proof, bindings=(binding,))
        class SubParent(type(proof.parent)): pass
        parent = SubParent(**{f: getattr(proof.parent, f) for f in proof.parent.__dataclass_fields__})
        for parent in (None, parent):
            with self.assertRaises(self.module.KubeProxyRevisionError): replace(proof, parent=parent)
        class SubBinding(type(proof.bindings[0])): pass
        binding = SubBinding(**{f: getattr(proof.bindings[0], f) for f in proof.bindings[0].__dataclass_fields__})
        for bindings in ([proof.bindings[0]], (), (binding,), (proof.bindings[0], proof.bindings[0])):
            with self.assertRaises(self.module.KubeProxyRevisionError): replace(proof, bindings=bindings)


if __name__ == '__main__': unittest.main()
