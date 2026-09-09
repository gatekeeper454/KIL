from copy import deepcopy
from dataclasses import replace
import json
import unittest

from kil.v3b2_pre_driver_ownership import validate_pre_driver_ownership
from tests.test_v3b2_runtime_image_inventory import fixture as ready_fixture


def fixture():
    args, ready = ready_fixture()
    doc = json.loads(args['runtime_objects'])
    doc['items'] = [row for row in doc['items'] if not (row['kind'] == 'Pod'
                    and row['metadata'].get('namespace', '').startswith('kil-')
                    and row['metadata']['name'] == 'driver')]
    args['runtime_objects'] = json.dumps(doc).encode()
    return args, ready


class PreDriverRuntimeTest(unittest.TestCase):
    def test_nine_generated_ready_pods_reconstruct_without_drivers(self):
        from kil.v3b2_pre_driver_runtime import validate_pre_driver_runtime
        args, ready = fixture()
        own = validate_pre_driver_ownership(**args)
        proof = validate_pre_driver_runtime(ownership=own, node_images=ready.node_images)
        self.assertIs(proof.ownership, own)
        self.assertEqual(len(proof.bindings), 9)
        self.assertEqual(len(proof.configuration_bindings), 9)
        self.assertEqual({row.role for row in proof.bindings}, {'authz', 'envoy', 'target'})
        self.assertIs(proof.runtime_contract_complete, False)
        self.assertIs(proof.full_application_contract_complete, False)
        self.assertEqual(replace(proof), proof)

    def test_runtime_and_configuration_drift_reject(self):
        from kil.v3b2_pre_driver_runtime import validate_pre_driver_runtime
        args, ready = fixture()
        changes = [
            lambda p: p['spec']['containers'][0].update(command=['bad']),
            lambda p: p['status']['conditions'][0].update(status='False'),
            lambda p: p['status']['containerStatuses'][0].update(ready=False),
            lambda p: p['status']['containerStatuses'][0].update(restartCount=1),
            lambda p: p['status']['containerStatuses'][0].update(imageID='sha256:'+'f'*64),
            lambda p: p['metadata']['annotations'].update({'cni.projectcalico.org/podIP':'10.244.0.240/32'}),
        ]
        for change in changes:
            with self.subTest(change=change):
                doc = json.loads(args['runtime_objects'])
                pod = next(r for r in doc['items'] if r['kind']=='Pod' and r['metadata'].get('namespace','').startswith('kil-'))
                change(pod)
                with self.assertRaises(ValueError):
                    own = validate_pre_driver_ownership(**dict(args, runtime_objects=json.dumps(doc).encode()))
                    validate_pre_driver_runtime(ownership=own, node_images=ready.node_images)

    def test_forged_fields_flags_and_wrong_dependencies_reject(self):
        from kil.v3b2_pre_driver_runtime import validate_pre_driver_runtime
        args, ready = fixture()
        own = validate_pre_driver_ownership(**args)
        proof = validate_pre_driver_runtime(ownership=own, node_images=ready.node_images)
        for changes in ({'bindings':proof.bindings[:-1]}, {'configuration_bindings':()},
                        {'runtime_contract_complete':True}, {'full_application_contract_complete':1},
                        {'ownership':ready.configuration.ownership}, {'node_images':object()}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): replace(proof, **changes)
        forged = deepcopy(proof.bindings)
        object.__setattr__(forged[0], 'image_ref', 'forged')
        with self.assertRaises(ValueError): replace(proof, bindings=forged)
        images = deepcopy(ready.node_images)
        object.__setattr__(images.identity, 'node_container_id', 'f'*64)
        with self.assertRaises(ValueError): validate_pre_driver_runtime(ownership=own, node_images=images)

    def test_ready_wrappers_reject_pre_driver_dependencies(self):
        from kil.v3b2_generated_kil_pod_configuration import validate_generated_kil_pod_configuration
        from kil.v3b2_runtime_endpoints import validate_runtime_endpoints
        from kil.v3b2_kil_pod_runtime import validate_kil_pod_runtime
        from kil.v3b2_pre_driver_runtime import validate_pre_driver_runtime
        args, ready = fixture()
        own = validate_pre_driver_ownership(**args)
        proof = validate_pre_driver_runtime(ownership=own, node_images=ready.node_images)
        for validator in (validate_generated_kil_pod_configuration, validate_runtime_endpoints):
            with self.assertRaises(ValueError): validator(ownership=own)
        with self.assertRaises(ValueError):
            validate_kil_pod_runtime(configuration=proof, endpoints=proof, node_images=ready.node_images)

    def test_early_driver_extra_and_missing_pods_reject(self):
        from kil.v3b2_pre_driver_runtime import validate_pre_driver_runtime
        args, ready = fixture()
        doc = json.loads(args['runtime_objects'])
        driver = next(r for r in json.loads(ready.configuration.ownership.runtime_objects)['items']
                      if r['kind']=='Pod' and r['metadata']['name']=='driver')
        pod = next(r for r in doc['items'] if r['kind']=='Pod' and r['metadata'].get('namespace','').startswith('kil-'))
        extra = deepcopy(pod)
        extra['metadata']['name'] += '-extra'
        for items in (doc['items']+[driver], doc['items']+[extra], [r for r in doc['items'] if r is not pod]):
            with self.subTest(count=len(items)), self.assertRaises(ValueError):
                own = validate_pre_driver_ownership(**dict(args, runtime_objects=json.dumps({'apiVersion':'v1','kind':'List','items':items}).encode()))
                validate_pre_driver_runtime(ownership=own, node_images=ready.node_images)

    def test_endpoint_target_drift_and_runtime_collisions_reject(self):
        from kil.v3b2_pre_driver_runtime import validate_pre_driver_runtime
        args, ready = fixture()
        for change in ('endpoint', 'container', 'sandbox', 'ip'):
            doc = json.loads(args['runtime_objects'])
            pods = [r for r in doc['items'] if r['kind']=='Pod' and r['metadata'].get('namespace','').startswith('kil-')]
            first, second = pods[:2]
            if change == 'endpoint':
                row = next(r for r in doc['items'] if r['kind']=='EndpointSlice' and r['metadata']['namespace'].startswith('kil-'))
                row['endpoints'][0]['targetRef']['uid'] = second['metadata']['uid']
            elif change == 'container':
                second['status']['containerStatuses'][0]['containerID'] = first['status']['containerStatuses'][0]['containerID']
            elif change == 'sandbox':
                second['metadata']['annotations']['cni.projectcalico.org/containerID'] = first['metadata']['annotations']['cni.projectcalico.org/containerID']
            else:
                second['status']['podIP'] = first['status']['podIP']
            with self.subTest(change=change), self.assertRaises(ValueError):
                own = validate_pre_driver_ownership(**dict(args, runtime_objects=json.dumps(doc).encode()))
                validate_pre_driver_runtime(ownership=own, node_images=ready.node_images)

    def test_reconstruction_rejects_forged_retained_endpoint_proofs(self):
        from kil.v3b2_pre_driver_runtime import validate_pre_driver_runtime
        args, ready = fixture()
        own = validate_pre_driver_ownership(**args)
        proof = validate_pre_driver_runtime(ownership=own, node_images=ready.node_images)
        for field in ('service_allocation', 'platform_endpoints', 'kil_endpoints'):
            with self.subTest(field=field), self.assertRaises(ValueError): replace(proof, **{field:object()})
        forged = deepcopy(proof.service_allocation)
        object.__setattr__(forged, 'bindings', b'[]')
        with self.assertRaises(ValueError): replace(proof, service_allocation=forged)
