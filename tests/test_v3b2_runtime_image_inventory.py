from copy import deepcopy
from dataclasses import asdict, replace
import json
import unittest
from unittest.mock import patch

from kil.v3b2_accepted_images import ACCEPTED_IMAGES
from kil.v3b2_inventory import InventoryError, parse_runtime_inventory
from kil.v3b2_kil_pod_runtime import validate_kil_pod_runtime
from kil.v3b2_runtime_ownership import validate_runtime_ownership
from kil.v3b2_runtime_endpoints import validate_runtime_endpoints
from kil.v3b2_generated_kil_pod_configuration import validate_generated_kil_pod_configuration
from kil.v3b2_node_image_references import ExpectedNodeImage, validate_node_image_references, node_image_inspect_argv
from tests.test_v3b2_kil_pod_runtime import fixture as runtime_fixture
from tests.test_v3b2_runtime_inventory_ownership import fixture as inventory_fixture


def fixture():
    args = inventory_fixture()
    args['owned_identity'] = replace(args['owned_identity'], docker_host='unix:///Users/test/.colima/kil-v3-lab/docker.sock')
    config, _, generic_images, _ = runtime_fixture()
    document = json.loads(args['runtime_objects'])
    good = {(row['metadata']['namespace'], row['metadata']['name']): row
            for row in json.loads(config.ownership.runtime_objects)['items']
            if row['kind'] == 'Pod' and row['metadata'].get('namespace', '').startswith('kil-')}
    for row in document['items']:
        if row['kind'] == 'Pod' and row['metadata'].get('namespace', '').startswith('kil-'):
            metadata = row['metadata']
            source = deepcopy(good[(metadata['namespace'], metadata['name'])])
            source['metadata'].update(uid=metadata['uid'], resourceVersion=metadata['resourceVersion'])
            role = source['spec']['containers'][0]['name']
            accepted = ACCEPTED_IMAGES[1 if role == 'envoy' else 0]
            source['spec']['containers'][0]['image'] = accepted.requested_image
            source['status']['containerStatuses'][0].update(
                image=accepted.config_digest if role == 'envoy' else accepted.requested_image,
                imageID=accepted.image_refs[0])
            row.clear(); row.update(source)
    expected = tuple(ExpectedNodeImage(item.role, item.requested_image, item.config_digest,
        item.target_digest, generic_images.expected_images[index].target_media_type,
        (item.requested_image,) if item.role == 'kil' else (),
        () if item.role == 'kil' else (item.requested_image,), item.config_digest)
        for index, item in enumerate(ACCEPTED_IMAGES))
    inspections = []
    env = (('DOCKER_CONFIG', generic_images.docker_config), ('DOCKER_HOST', args['owned_identity'].docker_host))
    table = ['REF TYPE DIGEST STATUS SIZE UNPACKED']
    for index, item in enumerate(expected):
        status = {'id':item.config_digest, 'repoTags':list(item.allowed_repo_tags),
                  'repoDigests':list(item.allowed_repo_digests), 'size':'1', 'username':'', 'pinned':False}
        inspections.append(replace(generic_images.inspections[index],
            env=env,
            argv=node_image_inspect_argv(args['owned_identity'].node_container_id, item.query_reference),
            stdout=json.dumps({'status':status}).encode()))
        for alias in (*item.allowed_repo_tags, *item.allowed_repo_digests):
            table.append(f'{alias} {item.target_media_type} {item.target_digest} complete (1/1) 1 B true')
    images = validate_node_image_references(identity=args['owned_identity'],
        docker_config=generic_images.docker_config, expected_images=expected, inspections=tuple(inspections),
        node_images=replace(generic_images.node_images, env=env, stdout=('\n'.join(table)+'\n').encode()))
    args['runtime_objects'] = json.dumps(document).encode()
    ownership = validate_runtime_ownership(**args)
    runtime = validate_kil_pod_runtime(configuration=validate_generated_kil_pod_configuration(ownership=ownership),
        endpoints=validate_runtime_endpoints(ownership=ownership), node_images=images)
    return args, runtime


def parse(args, proof):
    return parse_runtime_inventory(args['runtime_objects'], profile=args['profile'], workload=args['workload'],
        node_container_id=args['owned_identity'].node_container_id, docker_host=args['owned_identity'].docker_host,
        owned_identity=args['owned_identity'], kil_runtime_proof=proof)


class RuntimeImageInventoryTest(unittest.TestCase):
    def test_proof_backed_source_preserves_public_snapshot_schema(self):
        args, proof = fixture()
        result = parse(args, proof)
        self.assertEqual((len(result.objects),len(result.pod_images),len(result.endpoints)), (67,17,9))
        for row in result.pod_images:
            if row.image_role == 'workload':
                item = ACCEPTED_IMAGES[1 if row.container == 'envoy' else 0]
                self.assertEqual((row.image,row.image_id), (item.requested_image,item.image_refs[0]))
        self.assertNotIn('proof', json.dumps(asdict(result)))
        self.assertEqual(set(asdict(result)), {'cluster_incarnation_uid','node_container_id','docker_host',
            'namespaces','objects','pod_images','endpoints','policy_graph','calico_node_desired','calico_node_ready',
            'calico_controller_desired','calico_controller_ready'})

    def test_missing_forged_and_context_mismatched_authority_reject(self):
        args, proof = fixture()
        for candidate in (None, object()):
            with self.assertRaises(InventoryError): parse(args,candidate)
        forged = deepcopy(proof)
        object.__setattr__(forged.bindings[0], 'image_ref', ACCEPTED_IMAGES[1].image_refs[0])
        with self.assertRaises(InventoryError): parse(args,forged)
        changed = dict(args, runtime_objects=args['runtime_objects'] + b'\n')
        with self.assertRaises(InventoryError): parse(changed,proof)
        changed = dict(args, owned_identity=replace(args['owned_identity'],
            docker_host='unix:///Users/other/.colima/kil-v3-lab/docker.sock'))
        with self.assertRaises(InventoryError): parse(changed,proof)
        with self.assertRaises(InventoryError):
            parse_runtime_inventory(args['runtime_objects'],profile=args['profile'],workload=args['workload'],
                node_container_id=args['owned_identity'].node_container_id,docker_host=args['owned_identity'].docker_host,
                kil_runtime_proof=proof)

    def test_production_missing_proof_rejects_before_any_image_dto(self):
        args, _ = fixture()
        with patch('kil.v3b2_inventory.PodImageIdentity', side_effect=AssertionError('DTO created before proof')):
            with self.assertRaisesRegex(InventoryError, 'KIL image proof is invalid or missing'):
                parse(args,None)

    def test_changed_raw_container_identity_cannot_reuse_proof(self):
        args, proof = fixture()
        doc=json.loads(args['runtime_objects'])
        pod=next(row for row in doc['items'] if row['kind']=='Pod' and row['metadata'].get('namespace','').startswith('kil-'))
        pod['status']['containerStatuses'][0]['containerID']='containerd://'+'f'*64
        args['runtime_objects']=json.dumps(doc).encode()
        with self.assertRaisesRegex(InventoryError, 'KIL image proof is invalid or missing'):
            parse(args,proof)

    def test_calico_legacy_validation_is_not_bypassed_by_kil_authority(self):
        args, _ = fixture()
        doc=json.loads(args['runtime_objects'])
        pod=next(row for row in doc['items'] if row['kind']=='Pod' and row['metadata']['name'].startswith('calico-node-'))
        pod['status']['containerStatuses'][0]['imageID']='sha256:'+'f'*64
        args['runtime_objects']=json.dumps(doc).encode()
        own=validate_runtime_ownership(**args)
        _, original=fixture()
        proof=validate_kil_pod_runtime(configuration=validate_generated_kil_pod_configuration(ownership=own),
            endpoints=validate_runtime_endpoints(ownership=own),node_images=original.node_images)
        with self.assertRaisesRegex(InventoryError,'imageID must be an immutable realized digest identity'):
            parse(args,proof)
