from dataclasses import replace
import importlib
import importlib.util
import unittest
from unittest.mock import patch

from kil import v3b2_proofs as proofs

MODULE = 'kil.v3b2_application_evidence_budget'
MIB = 1024 * 1024


def context(**changes):
    return replace(proofs.ExpectedContext('a' * 64, 10000, 'application_apply',
        b'{}\n', proofs.canonical({'application_source_version': 1})), **changes)


def sized_object(size, **fields):
    base = proofs.canonical({**fields, 'padding': ''})
    return proofs.canonical({**fields, 'padding': 'x' * (size - len(base))})


def row(label='runtime_inventory', stdout=b'', stderr=b'', **changes):
    return replace(proofs.RawObservation(label, (), (), 0, stdout, stderr), **changes)


class ApplicationEvidenceBudgetTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'application evidence budget module missing')
        self.budget = importlib.import_module(MODULE)
        self.decision = proofs.ProofDecision('unknown', 'abandoned')

    def test_marker_is_exact_and_absence_is_legacy(self):
        self.assertFalse(self.budget.application_source_enabled({}))
        self.assertTrue(self.budget.application_source_enabled({'application_source_version': 1}))
        for value in (True, False, 1.0, None, 0, 2, '1', {}, []):
            with self.subTest(value=value), self.assertRaises(proofs.ProofError):
                self.budget.application_source_enabled({'application_source_version': value})
        with self.assertRaises(proofs.ProofError):
            self.budget.application_source_enabled([])

    def test_legacy_dispatch_skips_operation_budget(self):
        legacy = context(inputs=sized_object(5 * MIB + 1))
        with patch.object(self.budget, 'validate_application_context_budget', side_effect=AssertionError):
            self.assertFalse(self.budget.validate_application_dispatch_budget(legacy))
        self.assertFalse(self.budget.validate_application_dispatch_budget(context(family='readiness')))
        with self.assertRaises(proofs.ProofError):
            self.budget.validate_application_context_budget(legacy)

    def test_context_exact_input_limit_and_predecode_rejection(self):
        self.budget.validate_application_context_budget(context(inputs=sized_object(5 * MIB, application_source_version=1)))
        oversized = context(inputs=sized_object(5 * MIB + 1, application_source_version=1))
        with patch.object(proofs, 'decode', side_effect=AssertionError('decoded before bound')):
            with self.assertRaises(proofs.ProofError):
                self.budget.validate_application_context_budget(oversized)

    def test_context_intent_limit_precedes_decode(self):
        self.budget.validate_application_context_budget(context(intent=sized_object(MIB)))
        oversized = context(intent=sized_object(MIB + 1))
        with patch.object(proofs, 'decode', side_effect=AssertionError):
            with self.assertRaises(proofs.ProofError):
                self.budget.validate_application_context_budget(oversized)

    def test_each_raw_aggregate_includes_stderr_and_duplicate_checkpoint_labels(self):
        for label, maximum in (('pre_driver_checkpoint', 20 * MIB), ('node', 8 * MIB)):
            rows = (row(label, b'x' * (maximum - 1)), row(label, stderr=b'x'))
            self.budget.validate_application_bundle_budget(context(), rows, self.decision)
            with self.assertRaises(proofs.ProofError):
                self.budget.validate_application_bundle_budget(context(), (*rows, row(label, stderr=b'x')), self.decision)
        with self.assertRaises(proofs.ProofError):
            self.budget.validate_application_bundle_budget(context(), (row('node', b'x' * (8 * MIB)), row('node_before', stderr=b'x')), self.decision)

    def test_bindings_exact_limit_and_predecode_rejection(self):
        self.budget.validate_application_bundle_budget(context(), (), replace(self.decision, bindings=sized_object(MIB)))
        oversized = replace(self.decision, bindings=sized_object(MIB + 1))
        ctx = context()
        with patch.object(proofs, 'decode', side_effect=AssertionError):
            with self.assertRaises(proofs.ProofError):
                self.budget.validate_application_bundle_budget(ctx, (), oversized)

    def test_metadata_matches_outer_shape_without_hex_or_commitment(self):
        ctx, rows = context(), (row(stdout=b'x' * MIB, stderr=b'z'),)
        payload = proofs.decode(proofs.observation_bundle(ctx, rows, self.decision))
        payload['expected_inputs'] = {}; payload['bindings'] = {}
        for observed in payload['observations']:
            observed['stdout_hex'] = ''; observed['stderr_hex'] = ''
        exact = len(proofs.canonical(payload))
        with patch.object(proofs.ExpectedContext, 'commitment', property(lambda _: (_ for _ in ()).throw(AssertionError('commitment expanded')))):
            with patch.object(self.budget, 'MAX_APPLICATION_METADATA_BYTES', exact):
                self.budget.validate_application_bundle_budget(ctx, rows, self.decision)
            with patch.object(self.budget, 'MAX_APPLICATION_METADATA_BYTES', exact - 1):
                with self.assertRaises(proofs.ProofError):
                    self.budget.validate_application_bundle_budget(ctx, rows, self.decision)

    def test_real_metadata_cap_and_large_sequence(self):
        payload = proofs.decode(proofs.observation_bundle(context(), (), self.decision))
        payload['expected_inputs'] = {}; payload['bindings'] = {}
        size = len(proofs.canonical(payload))
        category = 'abandoned' + 'x' * (MIB - size)
        self.budget.validate_application_bundle_budget(context(), (), replace(self.decision, category=category))
        with self.assertRaises(proofs.ProofError):
            self.budget.validate_application_bundle_budget(context(), (), replace(self.decision, category=category + 'x'))
        with patch.object(self.budget, 'MAX_APPLICATION_METADATA_BYTES', size):
            with self.assertRaises(proofs.ProofError):
                self.budget.validate_application_bundle_budget(context(intent_sequence=10 ** 1000), (), self.decision)
        with self.assertRaises(proofs.ProofError):
            self.budget.validate_application_bundle_budget(context(intent_sequence=10 ** 10000), (), self.decision)

    def test_empty_failed_and_corrupt_sources_are_budget_valid(self):
        self.budget.validate_application_bundle_budget(context(), (), self.decision)
        self.budget.validate_application_bundle_budget(context(), (row('pre_driver_checkpoint', b'corrupt', b'failure', returncode=1),), self.decision)
        self.assertTrue(self.budget.validate_application_dispatch_budget(context(), (row(),)))

    def test_exact_observation_types_and_metadata_primitives(self):
        for rows in ([row()], (object(),), (row(argv=(True,)),), (row(env=(('x', 1),)),)):
            with self.subTest(rows=rows), self.assertRaises(proofs.ProofError):
                self.budget.validate_application_bundle_budget(context(), rows, self.decision)

    def test_real_application_fixture_is_accepted(self):
        from tests.test_v3b2_pre_driver_checkpoint import fixture
        ctx, _, rows = fixture()
        ctx = replace(ctx, inputs=proofs.canonical({**proofs.decode(ctx.inputs), 'application_source_version': 1}))
        self.budget.validate_application_bundle_budget(ctx, rows, self.decision)

    def test_encoded_raw_limits_match_without_decoding_hex(self):
        self.assertTrue(hasattr(self.budget, 'validate_application_encoded_budget'))
        ctx = context()
        document = proofs.decode(proofs.observation_bundle(ctx, (row(),), self.decision))
        for label, maximum in (('pre_driver_checkpoint', 20 * MIB), ('node', 8 * MIB)):
            # Nonhex characters are deliberately retained: semantic decoding is
            # subsequent; this helper must only count their encoded width.
            document['observations'][0].update(label=label, stdout_hex='z' * (2 * maximum - 2), stderr_hex='zz')
            self.budget.validate_application_encoded_budget(ctx, document)
            document['observations'][0]['stderr_hex'] += 'zz'
            with self.assertRaises(proofs.ProofError):
                self.budget.validate_application_encoded_budget(ctx, document)

    def test_encoded_metadata_bindings_and_types(self):
        self.assertTrue(hasattr(self.budget, 'validate_application_encoded_budget'))
        ctx = context()
        document = proofs.decode(proofs.observation_bundle(ctx, (row(),), self.decision))
        document['bindings'] = proofs.decode(sized_object(MIB))
        self.budget.validate_application_encoded_budget(ctx, document)
        document['bindings']['padding'] += 'x'
        with self.assertRaises(proofs.ProofError):
            self.budget.validate_application_encoded_budget(ctx, document)
        document['bindings'] = {}
        for value in ('a', 1, b'aa'):
            document['observations'][0]['stdout_hex'] = value
            with self.assertRaises(proofs.ProofError):
                self.budget.validate_application_encoded_budget(ctx, document)
        document['observations'][0]['stdout_hex'] = ''
        skeleton = {**document, 'expected_inputs': {}, 'bindings': {}}
        exact = len(proofs.canonical(skeleton))
        with patch.object(self.budget, 'MAX_APPLICATION_METADATA_BYTES', exact):
            self.budget.validate_application_encoded_budget(ctx, document)
        with patch.object(self.budget, 'MAX_APPLICATION_METADATA_BYTES', exact - 1):
            with self.assertRaises(proofs.ProofError):
                self.budget.validate_application_encoded_budget(ctx, document)
