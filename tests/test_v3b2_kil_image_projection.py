from copy import deepcopy
from dataclasses import asdict, replace
import json
import unittest

from kil.v3b2_kil_pod_runtime import validate_kil_pod_runtime
from kil.v3b2_inventory import PodImageIdentity, InventoryError
from tests.test_v3b2_kil_pod_runtime import fixture


def runtime():
    configuration, endpoints, images, _ = fixture()
    return validate_kil_pod_runtime(configuration=configuration, endpoints=endpoints, node_images=images)


class KilImageProjectionTest(unittest.TestCase):
    def projection(self, source=None):
        from kil.v3b2_kil_image_projection import validate_kil_image_projection
        return validate_kil_image_projection(runtime=runtime() if source is None else source)

    def test_exact_wire_fields_requested_images_and_actual_refs(self):
        source = runtime()
        proof = self.projection(source)
        self.assertIs(proof.runtime, source)
        self.assertEqual(len(proof.rows), 12)
        self.assertEqual(proof.rows, tuple(sorted(proof.rows)))
        fields = {'image_role', 'container_type', 'namespace', 'pod', 'container', 'uid',
                  'resource_version', 'image', 'image_id', 'ready', 'container_id'}
        for row in proof.rows:
            self.assertEqual(set(asdict(row)), fields)
            self.assertIsNot(type(row), PodImageIdentity)
            binding = next(b for b in source.bindings if (b.namespace, b.name) == (row.namespace, row.pod))
            expected = source.node_images.bindings[1 if row.container == 'envoy' else 0].expected
            self.assertEqual(row.image, expected.query_reference)
            self.assertEqual(row.image_id, binding.image_ref)
            self.assertEqual((row.uid, row.resource_version, row.container_id),
                             (binding.uid, binding.resource_version, binding.app_container_id))
            self.assertIs(row.ready, True)
            if row.container == 'envoy':
                self.assertEqual(binding.runtime_image, expected.config_digest)
                self.assertNotEqual(row.image, binding.runtime_image)
            else:
                self.assertEqual(row.image_id, expected.config_digest)
                self.assertNotEqual(expected.config_digest, expected.target_digest)
            with self.assertRaises(InventoryError):
                PodImageIdentity(**asdict(row))
        self.assertEqual(replace(proof), proof)
        self.assertIs(proof.runtime_contract_complete, False)
        self.assertIs(proof.full_application_contract_complete, False)

    def test_constructor_rejects_forged_swapped_missing_and_extra_rows(self):
        proof = self.projection()
        for rows in (proof.rows[:-1], proof.rows + proof.rows[:1], tuple(reversed(proof.rows)),
                     list(proof.rows), (object(),) * 12):
            with self.subTest(rows=type(rows)), self.assertRaises(ValueError):
                replace(proof, rows=rows)
        for field, value in (('image', next(row.image for row in proof.rows if row.container == 'envoy')), ('uid', proof.rows[-1].uid),
                             ('image_id', 'sha256:' + 'f' * 64), ('ready', 1)):
            changed = deepcopy(proof.rows[0])
            object.__setattr__(changed, field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(proof, rows=(changed, *proof.rows[1:]))
        for field in ('runtime_contract_complete', 'full_application_contract_complete'):
            with self.assertRaises(ValueError):
                replace(proof, **{field: True})

    def test_raw_and_dependency_tampering_recomputed(self):
        source = runtime()
        for mode in ('raw', 'image', 'binding', 'rendered', 'type'):
            changed = deepcopy(source)
            if mode == 'raw':
                own = changed.configuration.ownership
                doc = json.loads(own.runtime_objects)
                pod = next(r for r in doc['items'] if r['kind'] == 'Pod' and r['metadata'].get('namespace', '').startswith('kil-'))
                pod['status']['containerStatuses'][0]['imageID'] = 'sha256:' + 'f' * 64
                object.__setattr__(own, 'runtime_objects', json.dumps(doc).encode())
            elif mode == 'image':
                object.__setattr__(changed.node_images.bindings[0], 'image_ref', 'sha256:' + 'f' * 64)
            elif mode == 'binding':
                object.__setattr__(changed.bindings[0], 'image_ref', 'sha256:' + 'f' * 64)
            elif mode == 'rendered':
                own = changed.configuration.ownership
                doc = json.loads(own.rendered_objects)
                pod = next(row for row in doc['items'] if row['kind'] == 'Pod')
                pod['spec']['containers'][0]['image'] = changed.node_images.bindings[1].expected.query_reference
                object.__setattr__(own, 'rendered_objects', json.dumps(doc).encode())
            else:
                changed = object()
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.projection(changed)

    def test_optional_kil_digest_alias_remains_actual_ref(self):
        from kil.v3b2_node_image_references import validate_node_image_references
        from kil.v3b2_runtime_ownership import validate_runtime_ownership
        from kil.v3b2_runtime_endpoints import validate_runtime_endpoints
        from kil.v3b2_generated_kil_pod_configuration import validate_generated_kil_pod_configuration
        config, _, images, args = fixture()
        expected = list(images.expected_images)
        alias = 'kil.local/kil-v3b2@' + expected[0].target_digest
        expected[0] = replace(expected[0], allowed_repo_digests=(alias,))
        inspections = list(images.inspections)
        payload = json.loads(inspections[0].stdout)
        payload['status']['repoDigests'] = [alias]
        inspections[0] = replace(inspections[0], stdout=json.dumps(payload).encode())
        node = replace(images.node_images, stdout=images.node_images.stdout +
                       f'{alias} {expected[0].target_media_type} {expected[0].target_digest} complete (1/1) 1 B true\n'.encode())
        images = validate_node_image_references(identity=images.identity, docker_config=images.docker_config,
                    expected_images=tuple(expected), inspections=tuple(inspections), node_images=node)
        doc = json.loads(config.ownership.runtime_objects)
        for row in doc['items']:
            if row['kind'] == 'Pod' and row['metadata'].get('namespace', '').startswith('kil-'):
                cs = row['status']['containerStatuses'][0]
                if cs['name'] != 'envoy':
                    cs['imageID'] = alias
        args['runtime_objects'] = json.dumps(doc).encode()
        own = validate_runtime_ownership(**args)
        source = validate_kil_pod_runtime(configuration=validate_generated_kil_pod_configuration(ownership=own),
                    endpoints=validate_runtime_endpoints(ownership=own), node_images=images)
        proof = self.projection(source)
        self.assertTrue(all(row.image_id == alias for row in proof.rows if row.container != 'envoy'))
        self.assertTrue(all(row.image == expected[0].query_reference for row in proof.rows if row.container != 'envoy'))
        with self.assertRaises(ValueError):
            replace(self.projection(), runtime=source)

    def test_forged_projection_revalidates_rows_and_source(self):
        proof = self.projection()
        for field, value in (('rows', proof.rows[:-1]), ('runtime', object()),
                             ('runtime_contract_complete', 0), ('full_application_contract_complete', 0)):
            forged = deepcopy(proof)
            object.__setattr__(forged, field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                forged.__post_init__()
        for field, value in (('image', 'x' * 1025), ('ready', 1), ('uid', None),
                             ('container_id', 'docker://' + 'a' * 64)):
            forged = deepcopy(proof.rows[0])
            object.__setattr__(forged, field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(proof, rows=(forged, *proof.rows[1:]))
