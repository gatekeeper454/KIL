"""Independent serialized-template fixtures; no production default helper."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import importlib
import importlib.util
import json
from pathlib import Path
import unittest

from kil.v3b2_runtime_ownership import validate_runtime_ownership
from tests.test_v3b2_runtime_ownership import fixture as owner_fixture, encode

ROOT = Path(__file__).resolve().parents[1]
MODULE = 'kil.v3b2_calico_node_revision'
NAME = 'calico-node'


def fixture():
    args = owner_fixture()
    doc = json.loads(args['runtime_objects'])
    raw = (ROOT / 'deploy/kind/calico-v3.32.0.objects.json').read_bytes()
    assert sha256(raw).hexdigest() == 'de76213b8097d55a674cbe88ef9ac349317b067fb3c6fc326d4280d17c7104a8'
    pinned = next(r for r in json.loads(raw)['items'] if r['kind'] == 'DaemonSet')
    ds = next(r for r in doc['items'] if r['kind'] == 'DaemonSet' and r['metadata']['name'] == NAME)
    ds['spec'] = deepcopy(pinned['spec'])
    ds['metadata'].update(labels={'k8s-app': NAME}, generation=1, creationTimestamp='2026-09-08T00:00:00Z')
    pod = next(r for r in doc['items'] if r['kind'] == 'Pod' and r['metadata']['name'].startswith(NAME + '-'))
    pod['metadata']['labels'] = {'controller-revision-hash': 'abc123'}
    # Explicit reviewed API serialization, separate from production normalization.
    template = deepcopy(pinned['spec']['template'])
    spec = template['spec']
    spec.update(serviceAccount=NAME, dnsPolicy='ClusterFirst', restartPolicy='Always', schedulerName='default-scheduler')
    for container in spec['initContainers'] + spec['containers']:
        container.update(terminationMessagePath='/dev/termination-log', terminationMessagePolicy='File')
        if container['name'] != NAME: container['resources'] = {}
        for env in container.get('env', []):
            if 'fieldRef' in env.get('valueFrom', {}): env['valueFrom']['fieldRef']['apiVersion'] = 'v1'
        for mount in container['volumeMounts']:
            if mount.get('readOnly') is False: del mount['readOnly']
    spec['containers'][0]['livenessProbe']['successThreshold'] = 1
    spec['containers'][0]['readinessProbe'].update(successThreshold=1, failureThreshold=3)
    for volume in spec['volumes']:
        if volume['name'] in {'lib-modules', 'nodeproc', 'cni-net-dir', 'cni-log-dir', 'host-local-net-dir'}:
            volume['hostPath']['type'] = ''
    template['$patch'] = 'replace'
    revision = {'apiVersion': 'apps/v1', 'kind': 'ControllerRevision', 'revision': 1,
        'metadata': {'name': NAME + '-abc123', 'namespace': 'kube-system', 'uid': 'revision-uid',
            'resourceVersion': '701', 'creationTimestamp': '2026-09-08T00:00:00Z',
            'labels': {'k8s-app': NAME, 'controller-revision-hash': 'abc123'},
            'ownerReferences': [{'apiVersion': 'apps/v1', 'kind': 'DaemonSet', 'name': NAME,
                'uid': ds['metadata']['uid'], 'controller': True, 'blockOwnerDeletion': True}]},
        'data': {'spec': {'template': template}}}
    doc['items'].append(revision)
    return args, doc, ds, pod, revision


class CalicoNodeRevisionTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'Calico node revision adapter is missing')
        self.m = importlib.import_module(MODULE)

    def validate(self, data=None, **changes):
        args, doc, *_ = data or fixture()
        args['runtime_objects'] = encode(doc)
        # All mutation cases must still satisfy the earlier ownership layer.
        ownership = validate_runtime_ownership(**args)
        values = dict(ownership=ownership,
            calico_source=(ROOT / 'deploy/kind/calico-v3.32.0.yaml').read_bytes(),
            calico_projection=(ROOT / 'deploy/kind/calico-v3.32.0.objects.json').read_bytes())
        values.update(changes)
        return self.m.validate_calico_node_revision(**values)

    def test_exact_relation_raw_retention_and_noncompletion(self):
        data = fixture()
        data[2]['status']['uninterpreted'] = [False, 'not readiness']
        data[3]['status'] = {'uninterpreted': True}
        proof = self.validate(data)
        self.assertEqual(proof.ownership.runtime_objects, encode(data[1]))
        self.assertFalse(proof.runtime_contract_complete)
        self.assertFalse(proof.full_application_contract_complete)
        self.assertEqual(replace(proof), proof)
        binding = proof.bindings[0]
        self.assertEqual(binding.daemon_set_uid, data[2]['metadata']['uid'])
        self.assertEqual(binding.revision_uid, 'revision-uid')
        self.assertEqual(binding.pod_uid, data[3]['metadata']['uid'])
        self.assertEqual(binding.revision_label, 'abc123')

    def test_opaque_consistent_label_rename_is_not_compute_hash_certification(self):
        data = fixture()
        data[4]['metadata']['name'] = NAME + '-z9'
        data[4]['metadata']['labels']['controller-revision-hash'] = 'z9'
        data[3]['metadata']['labels']['controller-revision-hash'] = 'z9'
        self.assertEqual(self.validate(data).bindings[0].revision_label, 'z9')

    def test_pod_configuration_remains_outside_this_relation(self):
        data = fixture()
        data[3]['spec']['unreviewedConfiguration'] = {'kept': True}
        proof = self.validate(data)
        self.assertIn(b'unreviewedConfiguration', proof.ownership.runtime_objects)
        self.assertFalse(proof.full_application_contract_complete)

    def test_unrelated_kube_proxy_revision_retained_uncertified(self):
        data = fixture()
        data[1]['items'].append({'apiVersion': 'apps/v1', 'kind': 'ControllerRevision',
            'metadata': {'name': 'kube-proxy-abc', 'namespace': 'kube-system', 'uid': 'proxy-revision', 'resourceVersion': '800'},
            'data': {'uninterpreted': True}})
        self.assertEqual(len(self.validate(data).bindings), 1)

    def test_other_calico_labeled_resource_families_are_not_revisions(self):
        data = fixture()
        data[1]['items'].append({'apiVersion': 'v1', 'kind': 'ServiceAccount',
            'metadata': {'name': NAME, 'namespace': 'kube-system', 'uid': 'calico-account',
                'resourceVersion': '802', 'labels': {'k8s-app': NAME}}})
        self.validate(data)

    def test_raw_patch_strict_structure_defaults_order_and_types(self):
        for mutation in ('missing-default', 'null-time', 'priority', 'token', 'affinity', 'service-links',
                         'added-toleration', 'hash-label', 'reorder', 'extra', 'bool', 'patch', 'init-resource', 'false-mount'):
            data = fixture(); template = data[4]['data']['spec']['template']; spec = template['spec']
            if mutation == 'missing-default': del spec['dnsPolicy']
            if mutation == 'null-time': template['metadata']['creationTimestamp'] = None
            if mutation == 'priority': spec['priority'] = 2000001000
            if mutation == 'token': spec['volumes'].append({'name': 'kube-api-access-abcde'})
            if mutation == 'affinity': spec['affinity'] = {}
            if mutation == 'service-links': spec['enableServiceLinks'] = True
            if mutation == 'added-toleration': spec['tolerations'].append({'operator': 'Exists'})
            if mutation == 'hash-label': template['metadata']['labels']['controller-revision-hash'] = 'abc123'
            if mutation == 'reorder': spec['initContainers'].reverse()
            if mutation == 'extra': data[4]['data']['extra'] = {}
            if mutation == 'bool': spec['terminationGracePeriodSeconds'] = False
            if mutation == 'patch': template['$patch'] = 'merge'
            if mutation == 'init-resource': del spec['initContainers'][0]['resources']
            if mutation == 'false-mount': spec['containers'][0]['volumeMounts'][0]['readOnly'] = False
            with self.subTest(mutation=mutation), self.assertRaises(self.m.CalicoNodeRevisionError): self.validate(data)

    def test_revision_metadata_root_owner_label_mutations(self):
        changes = [('revision', True), ('revision', 2), ('apiVersion', 'apps/v2'), ('kind', 'Foreign'),
            ('status', {}), ('extra', {})]
        for key, value in changes:
            data = fixture(); data[4][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(self.m.CalicoNodeRevisionError): self.validate(data)
        changes = [('namespace', 'foreign'), ('generation', 1), ('generateName', NAME + '-'),
            ('creationTimestamp', 'bad'), ('managedFields', [{}]), ('finalizers', []), ('annotations', {'foreign': 'x'}),
            ('labels', {'k8s-app': NAME, 'controller-revision-hash': True}), ('ownerReferences', []),
            ('ownerReferences', [None]), ('ownerReferences', {}), ('name', NAME + '-wrong')]
        for key, value in changes:
            data = fixture(); data[4]['metadata'][key] = value
            with self.subTest(key=key), self.assertRaises(self.m.CalicoNodeRevisionError): self.validate(data)
        for key, value in [('controller', 1), ('blockOwnerDeletion', 1), ('uid', 'foreign'), ('kind', 'Deployment'),
                           ('name', 'foreign'), ('apiVersion', 'apps/v2'), ('extra', True)]:
            data = fixture(); data[4]['metadata']['ownerReferences'][0][key] = value
            with self.subTest(owner=key), self.assertRaises(self.m.CalicoNodeRevisionError): self.validate(data)
        for key in ('creationTimestamp', 'labels', 'ownerReferences'):
            data = fixture(); del data[4]['metadata'][key]
            with self.assertRaises(self.m.CalicoNodeRevisionError): self.validate(data)

    def test_candidates_union_missing_extra_and_orphans(self):
        data = fixture(); data[1]['items'].remove(data[4])
        with self.assertRaises(self.m.CalicoNodeRevisionError): self.validate(data)
        for reason in ('uid', 'owner-name', 'label', 'prefix'):
            data = fixture()
            extra = {'apiVersion': 'apps/v1', 'kind': 'ControllerRevision', 'metadata': {
                'name': 'orphan', 'namespace': 'elsewhere', 'uid': 'orphan-uid', 'resourceVersion': '900'}}
            if reason == 'uid': extra['metadata']['ownerReferences'] = [{'uid': data[2]['metadata']['uid']}]
            if reason == 'owner-name': extra['metadata']['ownerReferences'] = [{'name': NAME}]
            if reason == 'label': extra['metadata']['labels'] = {'k8s-app': NAME}
            if reason == 'prefix': extra['metadata']['name'] = NAME + '-orphan'
            data[1]['items'].append(extra)
            with self.subTest(reason=reason), self.assertRaises(self.m.CalicoNodeRevisionError): self.validate(data)

    def test_daemon_configuration_and_pod_label(self):
        for mutation in ('image', 'generation-bool', 'generation-two', 'extra-meta', 'labels', 'pod-hash'):
            data = fixture()
            if mutation == 'image': data[2]['spec']['template']['spec']['containers'][0]['image'] = 'foreign'
            if mutation == 'generation-bool': data[2]['metadata']['generation'] = True
            if mutation == 'generation-two': data[2]['metadata']['generation'] = 2
            if mutation == 'extra-meta': data[2]['metadata']['extra'] = {}
            if mutation == 'labels': data[2]['metadata']['labels']['extra'] = 'x'
            if mutation == 'pod-hash': data[3]['metadata']['labels']['controller-revision-hash'] = 'wrong'
            with self.subTest(mutation=mutation), self.assertRaises(self.m.CalicoNodeRevisionError): self.validate(data)

    def test_annotation_exact_copy_and_bounded_managed_fields(self):
        data = fixture()
        annotation = {'kubectl.kubernetes.io/last-applied-configuration': 'retained exact bytes'}
        data[2]['metadata']['annotations'] = deepcopy(annotation)
        data[4]['metadata']['annotations'] = deepcopy(annotation)
        data[4]['metadata']['managedFields'] = [{'manager': 'kube-controller-manager', 'operation': 'Update',
            'apiVersion': 'apps/v1', 'fieldsType': 'FieldsV1', 'fieldsV1': {'f:data': {}}}]
        self.validate(data)
        data[4]['metadata']['annotations']['kubectl.kubernetes.io/last-applied-configuration'] = 'different'
        with self.assertRaises(self.m.CalicoNodeRevisionError): self.validate(data)
        data = fixture(); data[4]['metadata']['annotations'] = {}; self.validate(data)

    def test_constructor_and_source_poison(self):
        proof = self.validate()
        for changes in ({'ownership': None}, {'calico_source': b'bad'}, {'calico_projection': b'bad'},
                        {'calico_source': b'x' * (2 * 1024 * 1024 + 1)}, {'calico_source': bytearray(b'a')},
                        {'calico_projection': b'x' * (2 * 1024 * 1024 + 1)}, {'calico_projection': bytearray(b'a')}):
            with self.assertRaises(self.m.CalicoNodeRevisionError): self.validate(**changes)
        for changes in ({'bindings': ()}, {'bindings': list(proof.bindings)}, {'runtime_contract_complete': 0},
                        {'runtime_contract_complete': True}, {'full_application_contract_complete': True},
                        {'calico_source': proof.calico_source + b'\n'}, {'calico_projection': proof.calico_projection + b'\n'}):
            with self.assertRaises(self.m.CalicoNodeRevisionError): replace(proof, **changes)
        forged = deepcopy(proof.ownership); object.__setattr__(forged, 'runtime_contract_complete', True)
        with self.assertRaises(self.m.CalicoNodeRevisionError): replace(proof, ownership=forged)
        wrong = replace(proof.bindings[0], revision_uid='foreign')
        with self.assertRaises(self.m.CalicoNodeRevisionError): replace(proof, bindings=(wrong,))
        for key, value in [('namespace', 'foreign'), ('daemon_set_name', 'foreign'), ('revision_label', True),
                           ('revision_uid', ''), ('revision_resource_version', 1), ('pod_uid', False)]:
            with self.subTest(key=key), self.assertRaises(self.m.CalicoNodeRevisionError): replace(proof.bindings[0], **{key: value})


if __name__ == '__main__': unittest.main()
