"""Independent literal producer expectations for the pinned Calico controller."""
from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import json
from pathlib import Path
import unittest

from kil.v3b2_runtime_ownership import validate_runtime_ownership
from tests.test_v3b2_runtime_ownership import fixture as owner_fixture, encode

ROOT = Path(__file__).resolve().parents[1]
NAME = 'calico-kube-controllers'
MODULE = 'kil.v3b2_calico_controller_configuration'


def template():
    return {'metadata': {'name': NAME, 'namespace': 'kube-system', 'labels': {'k8s-app': NAME}},
        'spec': {'nodeSelector': {'kubernetes.io/os': 'linux'}, 'tolerations': [
            {'key': 'CriticalAddonsOnly', 'operator': 'Exists'},
            {'key': 'node-role.kubernetes.io/master', 'effect': 'NoSchedule'},
            {'key': 'node-role.kubernetes.io/control-plane', 'effect': 'NoSchedule'}],
            'serviceAccountName': NAME, 'securityContext': {'seccompProfile': {'type': 'RuntimeDefault'}},
            'priorityClassName': 'system-cluster-critical', 'containers': [{'name': NAME,
                'image': 'quay.io/calico/kube-controllers@sha256:adf0ac895796d21bca5383bc81c4cd2614be3a4308085b47857d7999f4cc2b1f',
                'imagePullPolicy': 'IfNotPresent', 'env': [{'name': 'ENABLED_CONTROLLERS', 'value': 'node,loadbalancer'},
                    {'name': 'DATASTORE_TYPE', 'value': 'kubernetes'}],
                'livenessProbe': {'exec': {'command': ['/usr/bin/check-status', '-l']}, 'periodSeconds': 10,
                    'initialDelaySeconds': 10, 'failureThreshold': 6, 'timeoutSeconds': 10},
                'readinessProbe': {'exec': {'command': ['/usr/bin/check-status', '-r']}, 'periodSeconds': 10},
                'securityContext': {'runAsNonRoot': True}}]}}


def fixture():
    args = owner_fixture()
    doc = json.loads(args['runtime_objects'])
    dep = next(r for r in doc['items'] if r['kind'] == 'Deployment' and r['metadata']['name'] == NAME)
    dep['metadata']['labels'] = {'k8s-app': NAME}
    dep['spec'] = {'replicas': 1, 'selector': {'matchLabels': {'k8s-app': NAME}},
                   'strategy': {'type': 'Recreate'}, 'template': template()}
    pod = next(r for r in doc['items'] if r['kind'] == 'Pod' and r['metadata']['name'].startswith(NAME))
    pod['metadata'].update(generateName=pod['metadata']['ownerReferences'][0]['name'] + '-',
                          generation=1, creationTimestamp='2026-09-08T01:02:03Z')
    pod['metadata']['labels']['k8s-app'] = NAME
    pod['spec'] = template()['spec']
    pod['spec'].update(priority=2000000000, preemptionPolicy='PreemptLowerPriority')
    pod['spec']['tolerations'] += [{'key': 'node.kubernetes.io/not-ready', 'operator': 'Exists',
        'effect': 'NoExecute', 'tolerationSeconds': 300}, {'key': 'node.kubernetes.io/unreachable',
        'operator': 'Exists', 'effect': 'NoExecute', 'tolerationSeconds': 300}]
    pod['spec']['volumes'] = [{'name': 'kube-api-access-bcdf2', 'projected': {'defaultMode': 420, 'sources': [
        {'serviceAccountToken': {'path': 'token', 'expirationSeconds': 3607}},
        {'configMap': {'name': 'kube-root-ca.crt', 'items': [{'key': 'ca.crt', 'path': 'ca.crt'}]}},
        {'downwardAPI': {'items': [{'path': 'namespace', 'fieldRef': {'apiVersion': 'v1', 'fieldPath': 'metadata.namespace'}}]}}]}}]
    pod['spec']['containers'][0]['volumeMounts'] = [{'name': 'kube-api-access-bcdf2', 'readOnly': True,
        'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount'}]
    sa = {'apiVersion': 'v1', 'kind': 'ServiceAccount', 'metadata': {'name': NAME, 'namespace': 'kube-system',
        'uid': 'calico-service-account', 'resourceVersion': '1000'}}
    doc['items'].append(sa)
    return args, doc, dep, pod, sa


class CalicoConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'Calico configuration adapter is missing')
        self.m = importlib.import_module(MODULE)

    def validate(self, data=None, **changes):
        args, doc, *_ = data or fixture()
        args['runtime_objects'] = encode(doc)
        values = dict(ownership=validate_runtime_ownership(**args),
            calico_source=(ROOT / 'deploy/kind/calico-v3.32.0.yaml').read_bytes(),
            calico_projection=(ROOT / 'deploy/kind/calico-v3.32.0.objects.json').read_bytes())
        values.update(changes)
        return self.m.validate_calico_controller_configuration(**values)

    def test_unscheduled_scheduled_and_serialized_defaults(self):
        for scheduled in (False, True):
            data = fixture(); pod = data[3]
            if scheduled: pod['spec']['nodeName'] = 'kil-v3-lab-control-plane'
            pod['spec'].update(serviceAccount=NAME, enableServiceLinks=True, restartPolicy='Always', dnsPolicy='ClusterFirst')
            pod['spec']['containers'][0].update(resources={}, terminationMessagePath='/dev/termination-log', terminationMessagePolicy='File')
            proof = self.validate(data)
            self.assertEqual(len(proof.bindings), 1)
            self.assertFalse(proof.runtime_contract_complete)
            self.assertFalse(proof.full_application_contract_complete)
            self.assertEqual(replace(proof), proof)

    def test_full_raw_retention_status_uninterpreted(self):
        data = fixture()
        for row in data[2:]: row['status'] = {'uninterpreted': ['not-certified', False]}
        proof = self.validate(data)
        self.assertEqual(proof.ownership.runtime_objects, encode(data[1]))
        self.assertEqual(proof.calico_source, (ROOT / 'deploy/kind/calico-v3.32.0.yaml').read_bytes())

    def test_pod_configuration_mutations_preserve_valid_ownership(self):
        def assign(path, value):
            def change(p):
                for key in path[:-1]: p = p[key]
                p[path[-1]] = value
            return change
        cases = [(['spec', 'priority'], True), (['spec', 'priority'], 0),
            (['spec', 'preemptionPolicy'], 'Never'), (['spec', 'automountServiceAccountToken'], True),
            (['spec', 'imagePullSecrets'], []), (['spec', 'serviceAccount'], 'default'),
            (['spec', 'nodeName'], 'foreign'), (['spec', 'initContainers'], []),
            (['spec', 'containers', 0, 'image'], 'foreign'), (['foreign'], {}),
            (['metadata', 'generateName'], 'foreign-'), (['metadata', 'finalizers'], []),
            (['metadata', 'generation'], True), (['metadata', 'annotations'], {'foreign': 'x'}),
            (['spec', 'tolerations', 1, 'operator'], 'Equal'),
            (['spec', 'volumes', 0, 'name'], 'kube-api-access-abcde'),
            (['spec', 'volumes', 0, 'projected', 'sources', 0, 'serviceAccountToken', 'expirationSeconds'], 3600),
            (['spec', 'volumes', 0, 'projected', 'sources', 0, 'serviceAccountToken', 'audience'], 'foreign'),
            (['spec', 'containers', 0, 'volumeMounts', 0, 'readOnly'], False)]
        for path, value in cases:
            data = fixture(); assign(path, value)(data[3])
            with self.subTest(path=path), self.assertRaises(self.m.CalicoControllerConfigurationError): self.validate(data)
        for key in ('sources',):
            data = fixture(); data[3]['spec']['volumes'][0]['projected'][key].reverse()
            with self.assertRaises(self.m.CalicoControllerConfigurationError): self.validate(data)

    def test_independent_deployment_and_service_account(self):
        for target, field, value in ((4, 'automountServiceAccountToken', False), (4, 'imagePullSecrets', [])):
            data = fixture(); data[target][field] = value
            with self.assertRaises(self.m.CalicoControllerConfigurationError): self.validate(data)
        data = fixture()
        data[2]['spec']['template']['spec']['containers'][0]['image'] = 'foreign'
        data[3]['spec']['containers'][0]['image'] = 'foreign'
        with self.assertRaises(self.m.CalicoControllerConfigurationError): self.validate(data)

    def test_source_dependency_and_reconstruction_poison(self):
        proof = self.validate()
        for changes in ({'calico_source': b'bad'}, {'calico_projection': b'bad'}, {'ownership': None},
            {'calico_source': b'x' * (2 * 1024 * 1024 + 1)}):
            with self.assertRaises(self.m.CalicoControllerConfigurationError): self.validate(**changes)
        for changes in ({'bindings': ()}, {'runtime_contract_complete': True}, {'full_application_contract_complete': True},
            {'calico_source': proof.calico_source + b'\n'}, {'calico_projection': proof.calico_projection + b'\n'}):
            with self.assertRaises(self.m.CalicoControllerConfigurationError): replace(proof, **changes)

    def test_cni_and_managed_metadata(self):
        data = fixture(); pod = data[3]
        pod['spec']['nodeName'] = 'kil-v3-lab-control-plane'
        pod['metadata']['annotations'] = {'cni.projectcalico.org/podIP': '10.244.0.50/32',
            'cni.projectcalico.org/podIPs': '10.244.0.50/32', 'cni.projectcalico.org/containerID': '1' * 64}
        pod['metadata']['managedFields'] = [{'manager': 'kube-controller-manager', 'operation': 'Update',
            'apiVersion': 'v1', 'fieldsType': 'FieldsV1', 'fieldsV1': {'f:spec': {}}}]
        self.validate(data)
        for change in ('partial', 'foreign-ip', 'unscheduled', 'sandbox', 'managed', 'time'):
            bad = deepcopy(data)
            if change == 'partial': del bad[3]['metadata']['annotations']['cni.projectcalico.org/podIPs']
            if change == 'foreign-ip': bad[3]['metadata']['annotations']['cni.projectcalico.org/podIP'] = '192.168.0.1/32'
            if change == 'unscheduled': del bad[3]['spec']['nodeName']
            if change == 'sandbox': bad[3]['metadata']['annotations']['cni.projectcalico.org/containerID'] = bad[0]['owned_identity'].node_container_id
            if change == 'managed': bad[3]['metadata']['managedFields'] = [{'manager': 'x'}]
            if change == 'time': bad[3]['metadata']['creationTimestamp'] = 'invalid'
            with self.subTest(change=change), self.assertRaises(self.m.CalicoControllerConfigurationError): self.validate(bad)

    def test_token_closed_shape_and_exact_correlation(self):
        for change in ('mismatch', 'extra-volume', 'extra-mount', 'extra-container', 'optional', 'mode', 'mount-extra', 'extra-source'):
            data = fixture(); spec = data[3]['spec']
            volume = spec['volumes'][0]; mount = spec['containers'][0]['volumeMounts'][0]
            if change == 'mismatch': mount['name'] = 'kube-api-access-bcdf3'
            if change == 'extra-volume': spec['volumes'].append(deepcopy(volume))
            if change == 'extra-mount': spec['containers'][0]['volumeMounts'].append(deepcopy(mount))
            if change == 'extra-container': spec['containers'].append(deepcopy(spec['containers'][0]))
            if change == 'optional': volume['projected']['sources'][1]['configMap']['optional'] = False
            if change == 'mode': volume['projected']['sources'][1]['configMap']['items'][0]['mode'] = 420
            if change == 'mount-extra': mount['subPath'] = ''
            if change == 'extra-source': volume['projected']['sources'].append({})
            with self.subTest(change=change), self.assertRaises(self.m.CalicoControllerConfigurationError): self.validate(data)

    def test_binding_and_dependency_forgery(self):
        proof = self.validate()
        wrong = replace(proof.bindings[0], uid='foreign')
        with self.assertRaises(self.m.CalicoControllerConfigurationError): replace(proof, bindings=(wrong,))
        forged = deepcopy(proof.ownership)
        object.__setattr__(forged, 'runtime_contract_complete', True)
        with self.assertRaises(self.m.CalicoControllerConfigurationError): replace(proof, ownership=forged)
        for field, value in (('namespace', 'foreign'), ('deployment_name', 'foreign')):
            with self.assertRaises(self.m.CalicoControllerConfigurationError): replace(proof.bindings[0], **{field: value})

    def test_binding_identity_errors_are_adapter_errors(self):
        proof = self.validate()
        for field, value in (('uid', ''), ('resource_version', '0')):
            with self.assertRaises(self.m.CalicoControllerConfigurationError): replace(proof.bindings[0], **{field: value})


if __name__ == '__main__': unittest.main()
