from dataclasses import replace
from hashlib import sha256
import unittest
from unittest.mock import patch
from pathlib import Path

from kil import v3b2_proofs as p
from tests.test_v3b2_application_runtime_boundary import fixture


def raw_rows(rows):
    return tuple(p.RawObservation(r['label'], tuple(r['argv']), tuple(map(tuple, r['env'])),
        r['returncode'], bytes.fromhex(r['stdout_hex']), bytes.fromhex(r['stderr_hex'])) for r in rows)


def opted_fixture():
    context, checkpoint, args, _ = fixture()
    inputs = p.decode(context.inputs)
    source = inputs['prior_node_image_source']
    historical = p.ExpectedContext(source['run_id'], source['intent_sequence'], source['family'],
        p.canonical(source['intent']), p.canonical(dict(source['expected_inputs'], application_source_version=1)))
    source_rows = raw_rows(source['observations'])
    decision = p.decide(historical, source_rows)
    encoded = p.observation_bundle(historical, source_rows, decision)
    inputs.update(application_source_version=1, prior_node_image_source=p.decode(encoded))
    inputs['history'][1] = p.terminal_event(historical, decision, sha256(encoded).hexdigest())
    context = replace(context, inputs=p.canonical(inputs))
    document = p.decode(checkpoint)
    from kil.v3b2_policy_stage_checkpoint import encode_policy_stage_checkpoint
    from kil.v3b2_pre_driver_checkpoint import encode_pre_driver_checkpoint
    policy = encode_policy_stage_checkpoint(context, raw_rows(document['policy_checkpoint']['observations']))
    before = raw_rows(document['observations'])
    checkpoint = encode_pre_driver_checkpoint(context, policy, before)
    rows = (p.RawObservation('pre_driver_checkpoint', (), (), 0, checkpoint, b''),
            before[0], replace(before[1], stdout=args['runtime_objects']), *before[2:])
    return context, rows


class ApplicationTerminalTest(unittest.TestCase):
    def test_preflight_normalizes_historical_read_errors_without_dispatch(self):
        from kil import v3b2_controller as controller
        c = controller.V3B2Controller.__new__(controller.V3B2Controller)
        c.journal_path = Path('/unused/journal.json')
        for failed_loader in ('load_journal', 'load_expected_context'):
            with self.subTest(loader=failed_loader):
                failure = OSError('historical read failed')
                with patch.object(controller, 'load_journal', return_value={'events': []}) as journal, \
                        patch.object(controller, 'load_expected_context') as context, \
                        patch.object(controller, 'append_event') as append, patch.object(c, '_run') as run:
                    (journal if failed_loader == 'load_journal' else context).side_effect = failure
                    with self.assertRaisesRegex(controller.ControllerError, '^application_evidence_budget_failed$') as raised:
                        c._preflight_application_evidence({})
                    self.assertIs(raised.exception.__cause__, failure)
                    append.assert_not_called()
                    run.assert_not_called()

    def test_collector_reads_only_historical_checkpoint_with_application_cap(self):
        from kil import v3b2_controller as controller
        from kil import v3b2_pre_driver_checkpoint as checkpoint
        from kil.v3b2_application_evidence_budget import MAX_APPLICATION_CHECKPOINT_BYTES
        context, rows = opted_fixture()
        c = controller.V3B2Controller.__new__(controller.V3B2Controller)
        c.journal_path = Path('/unused/journal.json')
        request = p.OPERATIONS['application_apply'].requests(context)[0]
        with patch.object(checkpoint, 'read_pre_driver_checkpoint_bytes', return_value=rows[0].stdout) as reader:
            self.assertEqual(c._collect_observations(context, requests=(request,)), (rows[0],))
        reader.assert_called_once_with(c.journal_path, context, maximum=MAX_APPLICATION_CHECKPOINT_BYTES)
        with patch.object(checkpoint, 'read_pre_driver_checkpoint_bytes', side_effect=ValueError('missing')):
            failed = c._collect_observations(context, requests=(request,))
        self.assertNotEqual(failed[0].returncode, 0)
        with patch.object(checkpoint, '_private_location', return_value=(None, Path('/unused'))), \
                patch.object(checkpoint, '_read_checkpoint_bytes', side_effect=ValueError('oversize')) as reader, \
                patch.object(checkpoint, 'decode_pre_driver_checkpoint') as decoder:
            with self.assertRaisesRegex(ValueError, 'oversize'):
                checkpoint.read_pre_driver_checkpoint_bytes(c.journal_path, context, maximum=20)
            self.assertEqual(reader.call_args.args[2], 20)
            decoder.assert_not_called()

    def test_preflight_rejects_budget_without_appending_or_dispatch(self):
        from kil import v3b2_controller as controller
        from kil import v3b2_application_evidence_budget as budget
        context, _ = opted_fixture()
        c = controller.V3B2Controller.__new__(controller.V3B2Controller)
        c.journal_path = Path('/unused/journal.json')
        journal = {'events': [{'sequence': 1, 'event': 'calico_apply_complete', 'details': {}}]}
        with patch.object(controller, 'load_journal', return_value=journal), \
                patch.object(controller, 'load_expected_context', return_value=context) as loader, \
                patch.object(controller, 'append_event') as append, \
                patch.object(c, '_run') as run, \
                patch.object(budget, 'MAX_APPLICATION_INPUT_BYTES', 1):
            with self.assertRaisesRegex(controller.ControllerError, 'application_evidence_budget_failed'):
                c._preflight_application_evidence({'manifest_sha256': 'a' * 64})
        append.assert_not_called()
        run.assert_not_called()
        self.assertEqual(len(journal['events']), 1)
        self.assertEqual(loader.call_args.args[1]['events'][-1]['event'], 'application_apply_intent')

    def test_preflight_measures_actual_request_metadata(self):
        from kil import v3b2_controller as controller
        from kil import v3b2_application_evidence_budget as budget
        context, _ = opted_fixture()
        c = controller.V3B2Controller.__new__(controller.V3B2Controller)
        c.journal_path = Path('/unused/journal.json')
        maximum = len(budget._metadata(context, [], 'unknown', 'abandoned')) + 1
        with patch.object(controller, 'load_journal', return_value={'events': []}), \
                patch.object(controller, 'load_expected_context', return_value=context), \
                patch.object(budget, 'MAX_APPLICATION_METADATA_BYTES', maximum), \
                patch.object(controller, 'append_event') as append, patch.object(c, '_run') as run:
            with self.assertRaisesRegex(controller.ControllerError, 'application_evidence_budget_failed'):
                c._preflight_application_evidence({})
        append.assert_not_called()
        run.assert_not_called()

    def test_global_marker_and_base_checkpoint_claims_reject(self):
        for extra in ({'application_source_version': True}, {'application_source_version': 1.0},
                {'application_source_version': None}, {'application_source_version': 2},
                {'application_source_version': 1}, {'pre_driver_checkpoint': {}},
                {'pre_driver_checkpoint_bytes': '00'}, {'pre_driver_checkpoint_path': '/tmp/checkpoint'}):
            with self.subTest(extra=extra), self.assertRaises(p.ProofError):
                p._expected_for_intent(extra, {}, {'event': 'readiness_intent'}, [], {})

    def test_real_abandoned_application_bundle_replays(self):
        original, rows = opted_fixture()
        base = p.decode(original.inputs)
        for key in ('prior_node_image_source', 'history', 'prior_service_bindings',
                    'prior_node_image_references', 'applied_objects'):
            base.pop(key, None)
        payload = p.canonical(base)
        intent = {'sequence': 1, 'event': 'application_apply_intent', 'details': p.decode(original.intent)}
        journal = {'run_id': original.run_id, 'owned_identity': base['owned_identity'],
            'expected_inputs_sha256': sha256(payload).hexdigest(), 'events': [intent],
            'profile_start_refused_sequence': None, 'teardown_from_sequence': 1}
        context = p.expected_context(payload, journal, lambda *_: self.fail('unexpected proof read'))
        rows = (replace(rows[0], returncode=1, stdout=b'', stderr=b'missing checkpoint'), *rows[1:])
        decision = p.decide(context, rows)
        self.assertEqual(decision.outcome, 'teardown_only')
        encoded = p.observation_bundle(context, rows, decision)
        digest = sha256(encoded).hexdigest()
        terminal = p.terminal_event(context, decision, digest)
        self.assertEqual(terminal['event'], 'application_apply_abandoned_for_teardown')
        journal['events'] += [terminal, {'sequence': 3, 'event': 'cluster_delete_intent', 'details': {}}]
        replayed = p.expected_context(payload, journal, lambda sequence, proof_hash: encoded)
        self.assertEqual(replayed.family, 'cluster_delete')
        self.assertNotIn('pre_driver_checkpoint', p.decode(replayed.inputs))
        from kil import v3b2_application_evidence_budget as budget
        with patch.object(budget, 'validate_application_encoded_budget', side_effect=p.ProofError('encoded budget first')):
            malformed = p.decode(encoded)
            malformed['observations'][0]['stdout_hex'] = 'not hex'
            changed = p.canonical(malformed)
            journal['events'][1]['details']['observed_proof_sha256'] = sha256(changed).hexdigest()
            with self.assertRaisesRegex(p.ProofError, 'encoded budget first'):
                p.expected_context(payload, journal, lambda *_: changed)

    def test_direct_version_one_validator_rejects_legacy(self):
        from kil.v3b2_application_terminal import validate_application_terminal
        context, _, _, _ = fixture()
        with self.assertRaises(p.ProofError):
            validate_application_terminal(context, ())

    def test_writer_checks_budget_before_canonical_expansion(self):
        context, rows = opted_fixture()
        from kil import v3b2_application_evidence_budget as budget
        decision = p.ProofDecision('unknown', 'abandoned')
        limit = len(rows[0].stdout)
        with patch.object(budget, 'MAX_APPLICATION_CHECKPOINT_BYTES', limit):
            self.assertIsInstance(p.observation_bundle(context, rows, decision), bytes)
            with self.assertRaisesRegex(p.ProofError, 'aggregate byte bound'):
                p.observation_bundle(context, (replace(rows[0], stdout=rows[0].stdout + b' '), *rows[1:]), decision)

    def test_current_full_source_remains_pending_and_pure(self):
        context, rows = opted_fixture()
        with patch('pathlib.Path.open', side_effect=AssertionError('offline proof reads filesystem')):
            decision = p.decide(context, rows)
        self.assertEqual(decision.category, 'platform_admission_terminal_gate_pending')
        summary = p.decode(decision.bindings)
        self.assertEqual(len(summary['runtime_continuity']), 9)
        self.assertEqual(len(summary['policy_continuity']), 18)
        self.assertIs(summary['runtime_contract_complete'], False)
        self.assertIs(summary['full_application_contract_complete'], False)
        self.assertEqual(decision.outcome, 'unknown')

    def test_registry_and_checkpoint_drift_fail_closed(self):
        context, rows = opted_fixture()
        for changed in (rows[1:], (replace(rows[0], stdout=b'{}'), *rows[1:]),
                (rows[1], rows[0], *rows[2:]),
                (rows[0], replace(rows[1], env=()), *rows[2:])):
            with self.subTest(labels=[r.label for r in changed]):
                decision = p.decide(context, changed)
                self.assertEqual(decision.outcome, 'unknown')
                self.assertNotEqual(decision.category, 'platform_admission_terminal_gate_pending')

    def test_current_runtime_and_node_drift_fail_closed(self):
        context, rows = opted_fixture()
        for kind in ('Pod', 'ConfigMap', 'NetworkPolicy'):
            document = p.decode(rows[2].stdout)
            row = next(r for r in document['items'] if r['kind'] == kind and
                       r['metadata'].get('namespace', '').startswith('kil-'))
            if kind == 'ConfigMap':
                row['data'] = {'unexpected': 'changed'}
            else:
                row['metadata']['uid'] += '-changed'
            decision = p.decide(context, (*rows[:2], replace(rows[2], stdout=p.canonical(document)), *rows[3:]))
            self.assertEqual(decision.outcome, 'unknown')
            self.assertNotEqual(decision.category, 'platform_admission_terminal_gate_pending')
        node = p.decode(rows[1].stdout)
        node[0]['Image'] = 'sha256:' + 'f' * 64
        decision = p.decide(context, (rows[0], replace(rows[1], stdout=p.canonical(node)), *rows[2:]))
        self.assertEqual(decision.outcome, 'unknown')
        self.assertNotEqual(decision.category, 'platform_admission_terminal_gate_pending')

    def test_registry_opt_in_and_invalid_versions(self):
        context, _, _, _ = fixture()
        self.assertEqual(len(p.OPERATIONS['application_apply'].requests(context)), 5)
        inputs = p.decode(context.inputs)
        opted = replace(context, inputs=p.canonical(dict(inputs, application_source_version=1)))
        requests = p.OPERATIONS['application_apply'].requests(opted)
        self.assertEqual([r.label for r in requests], ['pre_driver_checkpoint', 'node_before',
            'runtime_inventory', 'node', 'cluster_namespace', 'kind_configuration'])
        self.assertEqual(requests[0].source, 'pre_driver_checkpoint')
        self.assertIsNone(requests[0].command)
        for version in (True, 1.0, None, 2):
            with self.subTest(version=version), self.assertRaises(p.ProofError):
                p.OPERATIONS['application_apply'].requests(replace(context,
                    inputs=p.canonical(dict(inputs, application_source_version=version))))
