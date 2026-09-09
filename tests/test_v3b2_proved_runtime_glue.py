from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kil import v3b2_inventory as inventory, v3b2_proofs as proofs
from tests.test_v3b2_runtime_image_inventory import fixture


class ProvedRuntimeGlueTest(unittest.TestCase):
    def test_common_helper_derives_entire_chain_from_same_source(self):
        args, runtime = fixture()
        snapshot = inventory.parse_proved_runtime_inventory(args['runtime_objects'],profile=args['profile'],
            workload=args['workload'],owned_identity=args['owned_identity'],node_images=runtime.node_images)
        self.assertEqual((len(snapshot.objects),len(snapshot.pod_images)),(67,17))

    def test_common_helper_rejects_missing_wrong_and_drifting_sources(self):
        args, runtime = fixture()
        forged = deepcopy(runtime.node_images)
        object.__setattr__(forged.bindings[0], 'image_ref', 'sha256:'+'f'*64)
        changed = json.loads(args['runtime_objects'])
        pod = next(row for row in changed['items'] if row['kind']=='Pod' and row['metadata'].get('namespace','').startswith('kil-'))
        pod['status']['containerStatuses'][0]['imageID']='sha256:'+'f'*64
        for raw, images in ((args['runtime_objects'],None),(args['runtime_objects'],object()),
                            (args['runtime_objects'],forged),(json.dumps(changed).encode(),runtime.node_images)):
            with self.subTest(images=type(images)),self.assertRaises(inventory.InventoryError):
                inventory.parse_proved_runtime_inventory(raw,profile=args['profile'],workload=args['workload'],
                    owned_identity=args['owned_identity'],node_images=images)

    def context(self, args, family='readiness', complete=True):
        profile=json.loads((Path(__file__).resolve().parents[1]/'deploy/kind/v3b2-profile.json').read_bytes())
        return proofs.ExpectedContext('1'*64,8,family,b'{}\n',proofs.canonical({'profile':profile,
            'workload':asdict(args['workload']),'owned_identity':asdict(args['owned_identity']),
            'runtime_contract_complete':complete,'prior_service_bindings':[]}))

    def test_readiness_missing_prior_source_rejects_before_common_parser(self):
        args,_=fixture(); context=self.context(args)
        argv=('kubectl','--kubeconfig',args['owned_identity'].kubeconfig,'get',proofs.RUNTIME_RESOURCES,
              '--all-namespaces','--output','json')
        observation=proofs.RawObservation('runtime_inventory',argv,(),0,args['runtime_objects'],b'')
        with patch('kil.v3b2_inventory.parse_proved_runtime_inventory') as parser:
            self.assertEqual(proofs.decide(context,(observation,)).outcome,'unknown')
            parser.assert_not_called()
        pending=self.context(args,complete=False)
        with patch('kil.v3b2_proofs.reconstruct_prior_node_image_references') as source:
            self.assertEqual(proofs.decide(pending,()).category,'platform_inventory_contract_pending')
            source.assert_not_called()

    def test_controller_loads_pending_context_and_matches_independent_identity(self):
        from kil.v3b2_controller import V3B2Controller, ControllerError
        args,runtime=fixture(); context=self.context(args,family='application_apply')
        controller=SimpleNamespace(profile=args['profile'],_identity=args['owned_identity'],journal_path=Path('/tmp/owned/journal.json'))
        with patch('kil.v3b2_controller.load_expected_context',return_value=context) as loader, patch(
                'kil.v3b2_proofs.reconstruct_prior_node_image_references',return_value=runtime.node_images) as source:
            result=V3B2Controller._pending_runtime_image_authority(controller,args['workload'])
            self.assertEqual(result,runtime.node_images)
            loader.assert_called_once_with(controller.journal_path)
            source.assert_called_once_with(context)
        with patch('kil.v3b2_controller.load_expected_context',return_value=context), patch(
                'kil.v3b2_proofs.reconstruct_prior_node_image_references',side_effect=proofs.ProofError('invalid source')):
            with self.assertRaisesRegex(ControllerError,'runtime_image_authority_invalid'):
                V3B2Controller._pending_runtime_image_authority(controller,args['workload'])
        bad=proofs.decode(context.inputs); bad['workload']['kil_image_id']='sha256:'+'f'*64
        changed=proofs.ExpectedContext(context.run_id,context.intent_sequence,context.family,context.intent,proofs.canonical(bad))
        with patch('kil.v3b2_controller.load_expected_context',return_value=changed), patch(
                'kil.v3b2_proofs.reconstruct_prior_node_image_references') as source:
            with self.assertRaises(ControllerError):
                V3B2Controller._pending_runtime_image_authority(controller,args['workload'])
            source.assert_not_called()

    def test_readiness_passes_reconstructed_authority_and_identical_raw_to_common_helper(self):
        args,runtime=fixture(); context=self.context(args)
        argv=('kubectl','--kubeconfig',args['owned_identity'].kubeconfig,'get',proofs.RUNTIME_RESOURCES,
              '--all-namespaces','--output','json')
        observation=proofs.RawObservation('runtime_inventory',argv,(),0,args['runtime_objects'],b'')
        with patch('kil.v3b2_proofs.reconstruct_prior_node_image_references',return_value=runtime.node_images), patch(
                'kil.v3b2_inventory.parse_proved_runtime_inventory',wraps=inventory.parse_proved_runtime_inventory) as parser:
            # This isolates glue; the source helper has its own replay tests.
            # Remaining full application validation is deliberately not satisfied.
            self.assertEqual(proofs.decide(context,(observation,)).outcome,'unknown')
            self.assertEqual(parser.call_args.args[0],args['runtime_objects'])
            self.assertEqual(parser.call_args.kwargs['node_images'],runtime.node_images)
            self.assertEqual(parser.call_args.kwargs['owned_identity'],args['owned_identity'])
