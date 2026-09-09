from dataclasses import replace
import unittest

from kil.v3b2_proofs import reconstruct_node_image_references
from tests import test_v3b2_node_image_integration as integration


class String(str): pass


class NodeImageReconstructionTest(unittest.TestCase):
    def setUp(self):
        fixture=integration.NodeImageIntegrationTest(); fixture.setUp()
        self.context=fixture.context; self.observations=fixture.observations()

    def test_retains_full_raw_observations_and_independent_expectations(self):
        proof=reconstruct_node_image_references(self.context,self.observations)
        self.assertEqual(proof.inspections,self.observations[1:3])
        self.assertEqual(proof.node_images,self.observations[3])
        self.assertEqual(tuple(row.query_reference for row in proof.expected_images),
                         tuple(row.expected.query_reference for row in proof.bindings))
        self.assertFalse(proof.runtime_contract_complete)

    def test_wrong_family_typed_command_transport_and_bracket_reject(self):
        class StringSubclass(str): pass
        variants=[(replace(self.context,family="readiness"),self.observations),
                  (replace(self.context,family=StringSubclass("image_load")),self.observations),
          (self.context,(replace(self.observations[0],argv=(String(self.observations[0].argv[0]),*self.observations[0].argv[1:])),*self.observations[1:])),
          (self.context,(replace(self.observations[0],env=((String("DOCKER_CONFIG"),self.observations[0].env[0][1]),self.observations[0].env[1])),*self.observations[1:]))]
        changed=list(self.observations); changed[1]=replace(changed[1],returncode=1); variants.append((self.context,tuple(changed)))
        changed=list(self.observations); changed[-3]=replace(changed[-3],stdout=b"[]\n"); variants.append((self.context,tuple(changed)))
        for context,observations in variants:
            with self.subTest(family=context.family),self.assertRaises(ValueError): reconstruct_node_image_references(context,observations)

    def test_wrong_intent_and_configuration_are_rejected(self):
        from kil.v3b2_proofs import canonical,decode
        intent=decode(self.context.intent); intent["image"]="kil.local/kil-v3b2:sha256-"+"9"*64
        with self.assertRaises(ValueError): reconstruct_node_image_references(replace(self.context,intent=canonical(intent)),self.observations)
        changed=list(self.observations); changed[-1]=replace(changed[-1],stdout=b"foreign\n")
        with self.assertRaises(ValueError): reconstruct_node_image_references(self.context,tuple(changed))


if __name__=="__main__": unittest.main()
