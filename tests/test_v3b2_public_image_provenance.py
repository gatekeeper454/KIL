"""Pure guard fixtures supply trusted contexts; they do not replay a lifecycle."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import importlib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from kil import v3b2_proofs as proofs
from kil.v3b2_evidence import build_public_bundle
from tests.test_v3b2_evidence import private_evidence, KIL_IMAGE_ID
from tests import test_v3b2_node_image_source as source_tests


class PublicImageProvenanceTest(unittest.TestCase):
    def setUp(self):
        try:
            module = importlib.import_module('kil.v3b2_public_image_provenance')
        except ModuleNotFoundError:
            self.fail('publication provenance guard is missing')
        self.guard = module.validate_public_image_provenance
        fixture = source_tests.NodeImageSourceTest(); fixture.setUp()
        prior = proofs.expected_context(fixture.payload, fixture.journal, lambda *_: fixture.bundle)
        self.inputs = proofs.decode(prior.inputs)
        self.inputs['history'].append({'sequence': 4, 'event': 'readiness_complete',
                                      'details': {'observed_proof_sha256': 'a' * 64}})
        self.manifest = build_public_bundle(private_evidence())
        self.manifest['run_id'] = 'v3b2-' + prior.run_id
        topology = self.manifest['topology_attestation']
        for key in ('node_container_id', 'cluster_incarnation_uid'):
            topology[key] = self.inputs['owned_identity'][key]
        self.inputs['source_images'] = deepcopy(topology['pod_images'])
        self.context = replace(prior, family='publication', intent_sequence=10,
                               inputs=proofs.canonical(self.inputs))

    def test_exact_seventeen_rows_pass(self):
        self.assertEqual(len(self.inputs['source_images']), 17)
        self.guard(self.context, proofs.canonical(self.manifest))

    def test_manifest_substitutions_reject(self):
        for field, value in [('image_id', 'kil.local/kil-v3b2@' + KIL_IMAGE_ID),
                             ('uid', '99999999-9999-4999-8999-999999999999'),
                             ('resource_version', '9999'), ('container', 'different'),
                             ('container_id', 'containerd://' + 'f' * 64)]:
            changed = deepcopy(self.manifest)
            row = next(r for r in changed['topology_attestation']['pod_images'] if r['container'] == 'authz')
            row[field] = value
            with self.subTest(field=field), self.assertRaises(proofs.ProofError):
                self.guard(self.context, proofs.canonical(changed))
        for field in ('node_container_id', 'cluster_incarnation_uid', 'run_id'):
            changed = deepcopy(self.manifest)
            target = changed if field == 'run_id' else changed['topology_attestation']
            target[field] = 'different'
            with self.subTest(field=field), self.assertRaises(proofs.ProofError):
                self.guard(self.context, proofs.canonical(changed))

    def test_invalid_authority_rejects(self):
        variants = []
        for marker in (True, 1.0, None, 2):
            changed = deepcopy(self.inputs); changed['node_image_source_version'] = marker; variants.append(changed)
        for sequence in (True, 4.0, 2, 10):
            changed = deepcopy(self.inputs); changed['history'][-1]['sequence'] = sequence; variants.append(changed)
        changed = deepcopy(self.inputs); changed['history'].pop(); variants.append(changed)
        changed = deepcopy(self.inputs); changed['history'].append(deepcopy(changed['history'][-1])); variants.append(changed)
        changed = deepcopy(self.inputs); changed['history'][-1]['details']['observed_proof_sha256'] = 'bad'; variants.append(changed)
        changed = deepcopy(self.inputs); changed['source_images'].pop(); variants.append(changed)
        changed = deepcopy(self.inputs); changed.pop('source_images'); variants.append(changed)
        changed = deepcopy(self.inputs); changed['prior_node_image_source'] = {'bindings': {}}; variants.append(changed)
        for changed in variants:
            with self.subTest(changed=changed.keys()), self.assertRaises(proofs.ProofError):
                self.guard(replace(self.context, inputs=proofs.canonical(changed)), proofs.canonical(self.manifest))

    def test_context_type_family_and_bounded_strict_json(self):
        for context in (True, {}, replace(self.context, family='readiness')):
            with self.assertRaises(proofs.ProofError): self.guard(context, proofs.canonical(self.manifest))
        for raw in (b'{"x":1,"x":2}', b'x' * (proofs.MAX_OBSERVATION_BYTES + 1)):
            with self.assertRaises(proofs.ProofError): self.guard(self.context, raw)

    def test_marker_absent_skips_new_checks_only(self):
        inputs = deepcopy(self.inputs); inputs.pop('node_image_source_version')
        self.guard(replace(self.context, inputs=proofs.canonical(inputs)), b'legacy')

    def test_repaired_accepted_alias_passes_public_semantics_but_not_private_selection(self):
        from kil import v3b2_evidence as evidence
        candidate = build_public_bundle(private_evidence())
        row = next(r for r in candidate['topology_attestation']['pod_images'] if r['container'] == 'authz')
        row['image_id'] = 'kil.local/kil-v3b2@' + KIL_IMAGE_ID
        artifacts = evidence._artifacts(candidate)
        candidate['public_commitment_sha256'] = evidence._public_commitment(candidate, artifacts)
        payloads = {'manifest.json': proofs.canonical(candidate), **artifacts}
        payloads['SHA256SUMS'] = ''.join(f'{sha256(raw).hexdigest()}  {name}\n'
            for name, raw in sorted(payloads.items())).encode()
        evidence._verify_sums(payloads, set(evidence.PUBLIC_FILES))
        evidence._verify_v3b2(payloads)
        with self.assertRaisesRegex(proofs.ProofError, 'replayed readiness selection'):
            self.guard(self.context, payloads['manifest.json'])

    def test_immutable_source_rows_are_overwritten_from_established_snapshot(self):
        fixture = source_tests.NodeImageSourceTest(); fixture.setUp()
        base = deepcopy(fixture.base); base['source_images'] = [{'injected': True}]
        intent = {'sequence': 10, 'event': 'publication_intent', 'details': {}}
        for established, expected in (({}, []),
                ({'runtime_snapshot': {'pod_images': self.inputs['source_images']}}, self.inputs['source_images'])):
            context = proofs._expected_for_intent(base, fixture.journal, intent, [], established)
            self.assertEqual(proofs.decode(context.inputs)['source_images'], expected)

    def test_terminal_publication_calls_same_guard_after_semantic_verification(self):
        from kil.v3b2_evidence import prepare_publication
        prepared = prepare_publication(private_evidence(request_free=True), Path('/tmp/public'))
        inputs = {'public_parent': '/tmp/public', 'teardown_only': False, 'history': [
            {'event': family + '_complete', 'details': {'observed_proof_sha256': 'a' * 64}}
            for family in ('cluster_absence_proof', 'profile_absence_proof', 'foreign_snapshot_comparison')]}
        intent = {'destination': str(prepared.destination), 'tree_commitment_sha256': prepared.tree_commitment,
                  'public_commitment_sha256': prepared.public_commitment}
        context = proofs.ExpectedContext(prepared.run_id[5:], 10, 'publication', proofs.canonical(intent), proofs.canonical(inputs))
        observation = proofs.RawObservation('publication_tree', (), (), 0,
            proofs.canonical({name: payload.hex() for name, payload in prepared.payloads}), b'')
        with patch('kil.v3b2_public_image_provenance.validate_public_image_provenance',
                   side_effect=proofs.ProofError('guard sentinel')) as guard:
            with self.assertRaisesRegex(proofs.ProofError, 'guard sentinel'):
                proofs._publication(context, (observation,))
            guard.assert_called_once_with(context, dict(prepared.payloads)['manifest.json'])

    def test_controller_mismatch_does_not_publish_prepared(self):
        from kil.v3b2_controller import V3B2Controller, ControllerError
        from tests.test_v3b2_evidence import PROFILE, RUN_ID, ENVOY_DIGEST
        from kil.v3b2_manifests import WorkloadIdentity
        topology = deepcopy(self.manifest['topology_attestation'])
        candidate = deepcopy(self.manifest); candidate['topology_attestation']['pod_images'][0]['uid'] = 'different'
        prepared = SimpleNamespace(destination=Path('/tmp/public/run'), public_commitment='a'*64,
                                   tree_commitment='b'*64, payloads=(('manifest.json', proofs.canonical(candidate)),))
        controller = SimpleNamespace(owned_absence_proven=True,
            _runtime_projection={'topology_attestation':topology,'policy_attestation':{}},
            _workload=WorkloadIdentity(RUN_ID, KIL_IMAGE_ID, ENVOY_DIGEST), profile=PROFILE,
            _identity=SimpleNamespace(**self.inputs['owned_identity']), _foreign_records_before=[],
            _foreign_records_after=[], _foreign_before=[], run_id=RUN_ID, _profile_sha256='a'*64,
            journal_path=Path('/tmp/journal.json'), _source_commit='a'*40, execution_nonce='x',
            _tool_identities={}, _request_cases=[], _context_after='', _context_before='',
            _source_attestations=[], paths=SimpleNamespace(public=Path('/tmp/public')), _events=[],
            _require_observed_terminal=Mock())
        with patch('kil.v3b2_controller.load_journal', return_value={}), patch(
                'kil.v3b2_controller.prepare_publication', return_value=prepared), patch(
                'kil.v3b2_controller.append_event') as append, patch(
                'kil.v3b2_controller.load_expected_context', return_value=self.context) as loader, patch(
                'kil.v3b2_controller.publish_prepared') as publish:
            with self.assertRaisesRegex(ControllerError, 'publication_failed'):
                V3B2Controller._publish(controller)
            publish.assert_not_called()
            loader.assert_called_once_with(controller.journal_path)
            append.assert_called_once()
