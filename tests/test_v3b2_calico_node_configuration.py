"""Independent literal producer/admission additions to checksummed source fixtures."""
from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import unittest

from kil.v3b2_runtime_ownership import validate_runtime_ownership
from kil.v3b2_calico_node_revision import validate_calico_node_revision
from tests.test_v3b2_calico_node_revision import fixture as revision_fixture, ROOT
from tests.test_v3b2_runtime_ownership import encode

MODULE = 'kil.v3b2_calico_node_configuration'


def fixture():
    args, doc, ds, pod, revision = revision_fixture()
    node = pod['spec']['nodeName']
    pod['spec'] = deepcopy(revision['data']['spec']['template']['spec'])
    pod['metadata'].update(generation=1, generateName='calico-node-',
        creationTimestamp='2026-09-08T00:00:00Z', labels=deepcopy(revision['metadata']['labels']))
    spec = pod['spec']
    spec.update(nodeName=node, priority=2000001000, preemptionPolicy='PreemptLowerPriority',
        enableServiceLinks=True, affinity={'nodeAffinity': {'requiredDuringSchedulingIgnoredDuringExecution': {
            'nodeSelectorTerms': [{'matchFields': [{'key': 'metadata.name', 'operator': 'In', 'values': [node]}]}]}}})
    for suffix, effect in [('not-ready', 'NoExecute'), ('unreachable', 'NoExecute'),
            ('disk-pressure', 'NoSchedule'), ('memory-pressure', 'NoSchedule'), ('pid-pressure', 'NoSchedule'),
            ('unschedulable', 'NoSchedule'), ('network-unavailable', 'NoSchedule')]:
        spec['tolerations'].append({'key': 'node.kubernetes.io/' + suffix, 'operator': 'Exists', 'effect': effect})
    token = 'kube-api-access-bc245'
    spec['volumes'].append({'name': token, 'projected': {'defaultMode': 420, 'sources': [
        {'serviceAccountToken': {'path': 'token', 'expirationSeconds': 3607}},
        {'configMap': {'name': 'kube-root-ca.crt', 'items': [{'key': 'ca.crt', 'path': 'ca.crt'}]}},
        {'downwardAPI': {'items': [{'path': 'namespace', 'fieldRef': {'apiVersion': 'v1', 'fieldPath': 'metadata.namespace'}}]}}]}})
    for container in spec['initContainers'] + spec['containers']:
        container['volumeMounts'].append({'name': token, 'readOnly': True,
            'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount'})
    account = {'apiVersion': 'v1', 'kind': 'ServiceAccount', 'metadata': {
        'name': 'calico-node', 'namespace': 'kube-system', 'uid': 'calico-account',
        'resourceVersion': '802', 'creationTimestamp': '2026-09-08T00:00:00Z'}}
    doc['items'].append(account)
    return args, doc, ds, pod, revision, account


def dependency(data):
    args, doc, *_ = data
    args['runtime_objects'] = encode(doc)
    return validate_calico_node_revision(ownership=validate_runtime_ownership(**args),
        calico_source=(ROOT / 'deploy/kind/calico-v3.32.0.yaml').read_bytes(),
        calico_projection=(ROOT / 'deploy/kind/calico-v3.32.0.objects.json').read_bytes())


class CalicoNodeConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'Calico admitted configuration adapter is missing')
        self.m = importlib.import_module(MODULE)

    def validate(self, data=None):
        return self.m.validate_calico_node_configuration(revision=dependency(data or fixture()))

    def test_full_configuration_retained_dependency_identity_and_false_flags(self):
        data = fixture(); data[3]['status'] = {'uninterpreted': ['not-ready', False]}
        revision = dependency(data)
        proof = self.m.validate_calico_node_configuration(revision=revision)
        self.assertIs(proof.revision, revision)
        self.assertEqual(proof.revision.ownership.runtime_objects, encode(data[1]))
        self.assertFalse(proof.runtime_contract_complete)
        self.assertFalse(proof.full_application_contract_complete)
        self.assertEqual(replace(proof), proof)
        self.assertEqual(proof.bindings[0].pod_uid, data[3]['metadata']['uid'])
        self.assertEqual([len(c['volumeMounts']) for c in data[3]['spec']['initContainers'] + data[3]['spec']['containers']], [3, 3, 4, 9])

    def test_reviewed_api_defaults_and_false_mount_omission(self):
        data = fixture(); spec = data[3]['spec']
        for key in ('enableServiceLinks', 'dnsPolicy', 'restartPolicy', 'schedulerName', 'serviceAccount'):
            del spec[key]
        for c in spec['initContainers'] + spec['containers']:
            del c['terminationMessagePath']; del c['terminationMessagePolicy']
            c['volumeMounts'][0]['readOnly'] = False
        self.validate(data)

    def test_all_source_configuration_and_admission_mutations(self):
        mutations = [
            lambda s: s.update(hostNetwork=False), lambda s: s.update(terminationGracePeriodSeconds=30),
            lambda s: s.update(terminationGracePeriodSeconds=False), lambda s: s.update(securityContext={}),
            lambda s: s.update(priority=True), lambda s: s.update(priority=0),
            lambda s: s.update(preemptionPolicy='Never'), lambda s: s.update(priorityClassName='foreign'),
            lambda s: s.update(automountServiceAccountToken=True), lambda s: s.update(imagePullSecrets=[]),
            lambda s: s.update(serviceAccount='foreign'), lambda s: s.update(affinity={}),
            lambda s: s['affinity']['nodeAffinity']['requiredDuringSchedulingIgnoredDuringExecution']['nodeSelectorTerms'][0]['matchFields'][0].update(values=['foreign']),
            lambda s: s['tolerations'].reverse(), lambda s: s['tolerations'].pop(),
            lambda s: s['tolerations'][3].update(tolerationSeconds=300),
            lambda s: s['initContainers'].reverse(), lambda s: s['containers'].append(deepcopy(s['containers'][0])),
            lambda s: s['containers'][0]['env'].reverse(), lambda s: s['containers'][0].update(image='foreign'),
            lambda s: s['containers'][0].update(resources={'requests': {'cpu': '251m'}}),
            lambda s: s['containers'][0]['securityContext'].update(privileged=False),
            lambda s: s['initContainers'][0]['securityContext'].update(allowPrivilegeEscalation=False),
            lambda s: s['volumes'][0]['hostPath'].update(path='/foreign'),
            lambda s: s['initContainers'][2]['volumeMounts'][0].update(mountPropagation='None'),
            lambda s: s['volumes'].reverse(), lambda s: s['volumes'].pop(),
            lambda s: s['volumes'].append({'name': 'extra', 'emptyDir': {}}),
            lambda s: s['volumes'][-1].update(name='kube-api-access-abcde'),
            lambda s: s['volumes'][-1]['projected']['sources'].reverse(),
            lambda s: s['volumes'][-1]['projected']['sources'][0]['serviceAccountToken'].update(expirationSeconds=3600),
            lambda s: s['volumes'][-1]['projected'].update(extra=True),
            lambda s: s['volumes'][-1]['projected'].update(defaultMode=True),
        ]
        for index, mutate in enumerate(mutations):
            data = fixture(); mutate(data[3]['spec'])
            revision = dependency(data)  # Earlier proof must accept these mutations.
            with self.subTest(index=index), self.assertRaises(self.m.CalicoNodeConfigurationError):
                self.m.validate_calico_node_configuration(revision=revision)

    def test_token_mounts_correlate_all_four_containers(self):
        for index in range(4):
            for mutation in ('missing', 'name', 'order', 'writable', 'extra'):
                data = fixture(); s = data[3]['spec']; c = (s['initContainers'] + s['containers'])[index]
                if mutation == 'missing': c['volumeMounts'].pop()
                if mutation == 'name': c['volumeMounts'][-1]['name'] = 'kube-api-access-bc246'
                if mutation == 'order': c['volumeMounts'].reverse()
                if mutation == 'writable': c['volumeMounts'][-1]['readOnly'] = False
                if mutation == 'extra': c['volumeMounts'].append(deepcopy(c['volumeMounts'][-1]))
                with self.subTest(index=index, mutation=mutation), self.assertRaises(self.m.CalicoNodeConfigurationError): self.validate(data)

    def test_closed_metadata_and_root(self):
        for key, value in [('generation', True), ('generation', 2), ('creationTimestamp', 'bad'),
                ('generateName', 'foreign-'), ('annotations', {}),
                ('annotations', {'kubectl.kubernetes.io/last-applied-configuration': 'opaque'}),
                ('annotations', {'cni.projectcalico.org/podIP': '192.0.2.1/32'}),
                ('finalizers', []), ('deletionTimestamp', '2026-09-08T00:00:00Z'), ('extra', {}),
                ('managedFields', [{}])]:
            data = fixture(); data[3]['metadata'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(self.m.CalicoNodeConfigurationError): self.validate(data)
        for key in ('generation', 'creationTimestamp', 'generateName'):
            data = fixture(); del data[3]['metadata'][key]
            with self.assertRaises(self.m.CalicoNodeConfigurationError): self.validate(data)
        for where, key, value in [('metadata', 'labels', {'controller-revision-hash': 'abc123'}),
                ('metadata', 'labels', {'k8s-app': 'calico-node', 'controller-revision-hash': 'abc123', 'pod-template-generation': '1'}),
                ('root', 'extra', {})]:
            data = fixture(); (data[3] if where == 'root' else data[3]['metadata'])[key] = value
            with self.assertRaises(self.m.CalicoNodeConfigurationError): self.validate(data)

    def test_service_account_same_source_full_configuration(self):
        for key, value in [('automountServiceAccountToken', True), ('imagePullSecrets', []), ('secrets', []), ('extra', {})]:
            data = fixture(); data[5][key] = value
            with self.subTest(key=key), self.assertRaises(self.m.CalicoNodeConfigurationError): self.validate(data)
        data = fixture(); data[1]['items'].remove(data[5])
        with self.assertRaises(self.m.CalicoNodeConfigurationError): self.validate(data)

    def test_inherited_node_owner_hash_and_identity_gates(self):
        # These cannot form the prerequisite proof at all; preserve that gate.
        for mutation in ('node', 'unscheduled', 'owner', 'hash', 'uid', 'rv', 'apiVersion'):
            data = fixture(); pod = data[3]
            if mutation == 'node': pod['spec']['nodeName'] = 'foreign'
            if mutation == 'unscheduled': del pod['spec']['nodeName']
            if mutation == 'owner': pod['metadata']['ownerReferences'].append(deepcopy(pod['metadata']['ownerReferences'][0]))
            if mutation == 'hash': pod['metadata']['labels']['controller-revision-hash'] = 'foreign'
            if mutation == 'uid': pod['metadata']['uid'] = True
            if mutation == 'rv': pod['metadata']['resourceVersion'] = 1
            if mutation == 'apiVersion': pod['apiVersion'] = 'v2'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): dependency(data)

    def test_token_details_and_source_containers_remain_closed(self):
        mutations = [
            lambda s: s['volumes'][-1]['projected']['sources'][0]['serviceAccountToken'].update(audience='foreign'),
            lambda s: s['volumes'][-1]['projected']['sources'][1]['configMap'].update(name='foreign'),
            lambda s: s['volumes'][-1]['projected']['sources'][1]['configMap']['items'][0].update(key='foreign'),
            lambda s: s['volumes'][-1]['projected']['sources'][2]['downwardAPI']['items'][0]['fieldRef'].update(fieldPath='metadata.name'),
            lambda s: s['tolerations'].append(deepcopy(s['tolerations'][-1])),
            lambda s: s['tolerations'][4].update(tolerationSeconds=0),
            lambda s: s['containers'][0]['livenessProbe'].update(timeoutSeconds=99),
            lambda s: s['containers'][0]['readinessProbe'].update(failureThreshold=True),
            lambda s: s['containers'][0]['envFrom'].append({'configMapRef': {'name': 'foreign'}}),
            lambda s: s['containers'][0]['lifecycle'].update(postStart={'exec': {'command': ['foreign']}}),
            lambda s: s['initContainers'][1].update(image='foreign'),
            lambda s: s['initContainers'][2]['securityContext'].update(privileged=1),
        ]
        for index, mutate in enumerate(mutations):
            data = fixture(); mutate(data[3]['spec'])
            with self.subTest(index=index), self.assertRaises(self.m.CalicoNodeConfigurationError): self.validate(data)

    def test_different_valid_token_name_and_managed_fields(self):
        data = fixture(); s = data[3]['spec']; token = 'kube-api-access-zz999'
        s['volumes'][-1]['name'] = token
        for c in s['initContainers'] + s['containers']: c['volumeMounts'][-1]['name'] = token
        data[3]['metadata']['managedFields'] = [{'manager': 'kubelet', 'operation': 'Update',
            'apiVersion': 'v1', 'fieldsType': 'FieldsV1', 'fieldsV1': {'f:status': {}}, 'subresource': 'status'}]
        self.assertEqual(self.validate(data).bindings[0].token_volume_name, token)

    def test_constructor_forgery_and_raw_drift(self):
        proof = self.validate()
        for changes in ({'revision': None}, {'bindings': ()}, {'bindings': list(proof.bindings)},
                {'runtime_contract_complete': 0}, {'runtime_contract_complete': True},
                {'full_application_contract_complete': 0}, {'full_application_contract_complete': True}):
            with self.assertRaises(self.m.CalicoNodeConfigurationError): replace(proof, **changes)
        wrong = replace(proof.bindings[0], pod_uid='foreign')
        with self.assertRaises(self.m.CalicoNodeConfigurationError): replace(proof, bindings=(wrong,))
        for key, value in [('pod_uid', False), ('pod_resource_version', 1), ('token_volume_name', 'kube-api-access-abcde')]:
            with self.assertRaises(self.m.CalicoNodeConfigurationError): replace(proof.bindings[0], **{key: value})
        forged = deepcopy(proof.revision)
        object.__setattr__(forged, 'runtime_contract_complete', True)
        with self.assertRaises(self.m.CalicoNodeConfigurationError): replace(proof, revision=forged)
        class RevisionSubclass(type(proof.revision)): pass
        subclass = RevisionSubclass(proof.revision.ownership, proof.revision.calico_source,
            proof.revision.calico_projection, proof.revision.bindings)
        with self.assertRaises(self.m.CalicoNodeConfigurationError): replace(proof, revision=subclass)
        forged = deepcopy(proof.revision)
        object.__setattr__(forged.ownership, 'runtime_objects', forged.ownership.runtime_objects.replace(b'"hostNetwork":true', b'"hostNetwork":false'))
        with self.assertRaises(self.m.CalicoNodeConfigurationError): replace(proof, revision=forged)


if __name__ == '__main__': unittest.main()
