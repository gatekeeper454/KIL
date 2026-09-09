from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import unittest
from unittest.mock import patch

from kil.v3b2_proofs import canonical, decode
from kil.v3b2_pre_driver_checkpoint import encode_pre_driver_checkpoint, decode_pre_driver_checkpoint
from kil.v3b2_runtime_ownership import validate_runtime_ownership
from kil.v3b2_generated_kil_pod_configuration import validate_generated_kil_pod_configuration
from kil.v3b2_runtime_endpoints import validate_runtime_endpoints
from kil.v3b2_kil_pod_runtime import validate_kil_pod_runtime
from kil.v3b2_node_image_references import validate_node_image_references
from tests.test_v3b2_pre_driver_checkpoint import fixture as checkpoint_fixture
from tests.test_v3b2_runtime_image_inventory import fixture as ready_fixture

MODULE = 'kil.v3b2_application_runtime_boundary'


def fixture():
    context, policy, observations = checkpoint_fixture()
    checkpoint = encode_pre_driver_checkpoint(context, policy, observations)
    pre = decode_pre_driver_checkpoint(checkpoint, context)
    args, _ = ready_fixture()
    document = decode(args['runtime_objects'])
    desired = {(r['kind'], r['metadata'].get('namespace', ''), r['metadata']['name']): r
               for r in decode(args['rendered_objects'])['items']}
    # The ownership fixture intentionally omits Deployment application metadata.
    # Add the literal requested labels/annotation to this broader admission fixture.
    for row in document['items']:
        key = row['kind'], row['metadata'].get('namespace', ''), row['metadata']['name']
        if row['kind'] == 'Deployment' and key in desired:
            row['metadata']['labels'] = deepcopy(desired[key]['metadata']['labels'])
            row['metadata']['annotations'].update(desired[key]['metadata']['annotations'])
    next(r for r in document['items'] if r['kind'] == 'Namespace' and
         r['metadata']['name'] == 'kube-system')['metadata']['uid'] = pre.runtime.ownership.owned_identity.cluster_incarnation_uid
    args.update(owned_identity=pre.runtime.ownership.owned_identity, runtime_objects=canonical(document))
    return context, checkpoint, args, pre.runtime.node_images


def runtime(args, images):
    ownership = validate_runtime_ownership(**args)
    return validate_kil_pod_runtime(configuration=validate_generated_kil_pod_configuration(ownership=ownership),
        endpoints=validate_runtime_endpoints(ownership=ownership), node_images=images)


class ApplicationRuntimeBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'application runtime boundary is missing')
        self.module = importlib.import_module(MODULE)
        self.context, self.checkpoint, self.args, self.images = fixture()

    def validate(self, proof=None):
        return self.module.validate_application_runtime_boundary(context=self.context,
            pre_driver_checkpoint_bytes=self.checkpoint, runtime=proof or runtime(self.args, self.images))

    def test_same_source_retained_and_incomplete(self):
        current = runtime(self.args, self.images)
        with patch('pathlib.Path.open', side_effect=AssertionError('filesystem access')):
            proof = self.validate(current)
        self.assertIs(proof.context, self.context)
        self.assertIs(proof.runtime, current)
        self.assertIs(proof.pre_driver_checkpoint_bytes, self.checkpoint)
        self.assertEqual(len(proof.runtime_continuity), 9)
        self.assertEqual(len(proof.application_boundary.policy_continuity), 18)
        applied = decode(proof.application_boundary.configuration.applied_objects)['items']
        self.assertEqual(len(applied), 60)
        source = decode(current.configuration.ownership.runtime_objects)['items']
        self.assertTrue(all(row in source for row in applied))
        self.assertIs(proof.runtime_contract_complete, False)
        self.assertIs(proof.full_application_contract_complete, False)
        self.assertEqual(replace(proof), proof)
        self.assertEqual(len(decode(proof.summary())['runtime_continuity']), 9)

    def changed_runtime(self, field, value, rv=None):
        document = decode(self.args['runtime_objects'])
        pod = next(r for r in document['items'] if r['kind'] == 'Pod' and
                   r['metadata'].get('namespace', '').startswith('kil-') and r['metadata']['name'] != 'driver')
        metadata = pod['metadata']; old_uid = metadata['uid']
        status = pod['status']
        if field == 'uid': metadata['uid'] = value
        elif field == 'pod_ip':
            status.update(podIP=value, podIPs=[{'ip': value}])
            metadata['annotations'].update({'cni.projectcalico.org/podIP': value + '/32',
                                            'cni.projectcalico.org/podIPs': value + '/32'})
        elif field == 'cni_sandbox_id': metadata['annotations']['cni.projectcalico.org/containerID'] = value
        elif field == 'started_at': status['containerStatuses'][0]['state']['running']['startedAt'] = value
        elif field == 'app_container_id': status['containerStatuses'][0]['containerID'] = value
        if rv is not None: metadata['resourceVersion'] = rv
        for row in document['items']:
            if row['kind'] == 'EndpointSlice':
                for endpoint in row['endpoints']:
                    ref = endpoint.get('targetRef', {})
                    if ref.get('uid') == old_uid:
                        ref['uid'] = metadata['uid']
                        endpoint['addresses'] = [status['podIP']]
        return runtime(dict(self.args, runtime_objects=canonical(document)), self.images)

    def test_independently_valid_incarnation_changes_reject_even_without_rv_change(self):
        for field, value in (('uid', 'replacement-pod'), ('pod_ip', '10.244.0.240'),
                ('cni_sandbox_id', 'e' * 64), ('app_container_id', 'containerd://' + 'e' * 64),
                ('started_at', '2026-09-08T04:05:06Z')):
            for rv in (None, '9999'):
                with self.subTest(field=field, rv=rv):
                    current = self.changed_runtime(field, value, rv)
                    with self.assertRaisesRegex(ValueError, 'incarnation changed'):
                        self.validate(current)

    def test_resource_versions_are_validated_but_not_ordered(self):
        for rv in ('1', '9999'):
            with self.subTest(rv=rv):
                proof = self.validate(self.changed_runtime(None, None, rv))
                self.assertIn(rv, {r.final_resource_version for r in proof.runtime_continuity})

    def test_constructor_and_nested_proof_tampering_reject(self):
        proof = self.validate()
        for changes in ({'runtime': object()}, {'application_boundary': object()},
                {'runtime_continuity': ()}, {'runtime_contract_complete': 1},
                {'full_application_contract_complete': True},
                {'pre_driver_checkpoint_bytes': self.checkpoint + b' '},
                {'context': replace(self.context, intent_sequence=5)}):
            with self.subTest(fields=list(changes)), self.assertRaises(ValueError): replace(proof, **changes)
        bindings = deepcopy(proof.runtime_continuity)
        object.__setattr__(bindings[0], 'final_resource_version', '99999')
        with self.assertRaises(ValueError): replace(proof, runtime_continuity=bindings)
        current = deepcopy(proof.runtime)
        object.__setattr__(current.configuration.ownership, 'runtime_objects', b'{}')
        with self.assertRaises(ValueError): self.validate(current)
        pre = decode_pre_driver_checkpoint(self.checkpoint, self.context)
        with self.assertRaises(ValueError): self.validate(pre.runtime)

    def test_policy_uid_and_static_configuration_are_derived_from_current_raw(self):
        document = decode(self.args['runtime_objects'])
        policy = next(r for r in document['items'] if r['kind'] == 'NetworkPolicy')
        policy['metadata']['uid'] = 'replacement-policy'
        current = runtime(dict(self.args, runtime_objects=canonical(document)), self.images)
        with self.assertRaisesRegex(ValueError, 'invalid application runtime boundary'):
            self.validate(current)
        document = decode(self.args['runtime_objects'])
        deployment = next(r for r in document['items'] if r['kind'] == 'Deployment' and
                          r['metadata'].get('namespace', '').startswith('kil-'))
        deployment['metadata']['annotations']['kil.dev/run-id'] = 'foreign'
        current = runtime(dict(self.args, runtime_objects=canonical(document)), self.images)
        with self.assertRaises(ValueError): self.validate(current)

    def test_malformed_checkpoint_and_wrong_types_reject(self):
        current = runtime(self.args, self.images)
        for checkpoint in (b'bad', self.checkpoint + b' ', bytearray(self.checkpoint), None):
            with self.subTest(), self.assertRaises(ValueError):
                self.module.validate_application_runtime_boundary(context=self.context,
                    pre_driver_checkpoint_bytes=checkpoint, runtime=current)
        for field in ('runtime_image', 'image_ref'):
            forged = deepcopy(current)
            object.__setattr__(forged.bindings[0], field, 'changed')
            with self.subTest(field=field), self.assertRaises(ValueError): self.validate(forged)

    def test_independently_valid_different_node_source_rejects(self):
        images = validate_node_image_references(identity=self.images.identity,
            docker_config=self.images.docker_config, expected_images=self.images.expected_images,
            node_images=self.images.node_images, inspections=(replace(self.images.inspections[0],
                stdout=self.images.inspections[0].stdout + b' '), *self.images.inspections[1:]))
        current = runtime(self.args, images)
        with self.assertRaisesRegex(ValueError, 'node image authority changed'):
            self.validate(current)
