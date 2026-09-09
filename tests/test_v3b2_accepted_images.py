from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import json
from pathlib import Path
import unittest


class AcceptedImagesTest(unittest.TestCase):
    def test_pins_match_accepted_manifest_and_reviewed_config_chain(self):
        from kil.v3b2_accepted_images import ACCEPTED_IMAGES, ACCEPTED_MANIFEST_SHA256
        path = Path(__file__).resolve().parents[1] / 'artifacts/generated/v3b1-local-envoy/v3b1-625262118e034d9c9b1df9c6e23bb54a78f01fe245a1b953d521b94884846e94/manifest.json'
        raw = path.read_bytes()
        self.assertEqual(ACCEPTED_MANIFEST_SHA256, 'fa39212f1ffad95a1b5a674021ac5ce4ed9458025ce0dcc80077070355141cd0')
        self.assertEqual(sha256(raw).hexdigest(), ACCEPTED_MANIFEST_SHA256)
        images = json.loads(raw)['immutable_images']
        kil, envoy = ACCEPTED_IMAGES
        self.assertEqual((kil.role, envoy.role), ('kil', 'envoy'))
        self.assertEqual(kil.target_digest, images['kil_image_id'])
        self.assertEqual(envoy.requested_image, images['envoy_digest'])
        self.assertEqual(kil.target_digest, 'sha256:45a167d79b92f352af05a3e9cb8a9df8e972e38ab23d04ca692053e2eaf63649')
        self.assertEqual(envoy.target_digest, 'sha256:57e14a549d7bd43c8d3f6d03e8cfa653e037d4b38e133acd9b54f38c524401b4')
        self.assertEqual(kil.config_digest, 'sha256:f21285be21c8f691b9b60b7e38bb309564a5cc238512c7455eb7759f4d922ddb')
        self.assertEqual(envoy.config_digest, 'sha256:ef846ec85aabf01a2ff7176a185260e476ca43d20478f57281d88f7a66d5671f')
        for item in ACCEPTED_IMAGES:
            self.assertEqual(replace(item), item)
            with self.assertRaises(FrozenInstanceError):
                item.config_digest = 'sha256:' + 'f' * 64

    def test_exact_finite_membership(self):
        from kil.v3b2_accepted_images import ACCEPTED_IMAGES, validate_accepted_image
        kil, envoy = ACCEPTED_IMAGES
        self.assertEqual(kil.requested_image, 'kil.local/kil-v3b2:sha256-' + kil.target_digest[7:])
        self.assertEqual(kil.image_refs, (kil.config_digest, 'kil.local/kil-v3b2@' + kil.target_digest))
        self.assertEqual(envoy.image_refs, (envoy.requested_image,))
        for item in ACCEPTED_IMAGES:
            for ref in item.image_refs:
                self.assertIsNone(validate_accepted_image(item.role, item.requested_image, ref))

    def test_nonmembers_and_types_rejected_without_override(self):
        from kil.v3b2_accepted_images import ACCEPTED_IMAGES, validate_accepted_image
        kil, envoy = ACCEPTED_IMAGES
        cases = [('other', kil.requested_image, kil.config_digest),
                 ('kil', kil.target_digest, kil.config_digest),
                 ('kil', kil.requested_image, kil.target_digest),
                 ('kil', kil.requested_image, envoy.config_digest),
                 ('kil', kil.requested_image, 'foreign/repo@' + kil.target_digest),
                 ('kil', kil.requested_image, 'docker://' + kil.config_digest),
                 ('envoy', envoy.requested_image, envoy.config_digest),
                 ('envoy', envoy.requested_image, 'docker-pullable://' + envoy.requested_image),
                 ('envoy', envoy.requested_image, envoy.target_digest),
                 ('envoy', envoy.requested_image.replace('docker.io/', ''), envoy.requested_image),
                 ('envoy', envoy.requested_image, envoy.requested_image + ' ')]
        for item in ACCEPTED_IMAGES:
            cases.append((item.role, item.requested_image + ':latest', item.image_refs[0]))
            cases.append((item.role, item.requested_image, 'sha256:' + 'f' * 64))
        class Text(str):
            pass
        for index in range(3):
            for bad in (None, 1, True, [], {}, Text(('kil', kil.requested_image, kil.config_digest)[index])):
                row = ['kil', kil.requested_image, kil.config_digest]
                row[index] = bad
                cases.append(tuple(row))
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_accepted_image(*case)
        with self.assertRaises(TypeError):
            validate_accepted_image('kil', kil.requested_image, kil.config_digest, accepted=ACCEPTED_IMAGES)
        with self.assertRaises(ValueError):
            replace(kil, config_digest=envoy.config_digest)
        with self.assertRaises(ValueError):
            replace(kil, image_refs=kil.image_refs + ('sha256:' + 'f' * 64,))
