"""Normal-dispatch pre-driver barrier; no live runtime commands."""
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from kil import v3b2_controller as controller
from kil import v3b2_pre_driver_checkpoint as checkpoint
from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_journal import OwnedIdentity
from kil.v3b2_manifests import WorkloadIdentity
from kil.v3b2_proofs import canonical, decode
from tests.test_v3b2_pre_driver_checkpoint import fixture


class PreDriverControllerTest(unittest.TestCase):
    def setUp(self):
        self.context, self.policy, self.rows = fixture()
        inputs = decode(self.context.inputs)
        self.c = controller.V3B2Controller.__new__(controller.V3B2Controller)
        self.c.profile = V3B2Profile.from_mapping(inputs['profile'])
        self.c._identity = OwnedIdentity(**inputs['owned_identity'])
        self.c._workload = WorkloadIdentity(**inputs['workload'])
        self.c.kind_config = Path(inputs['kind_config_path'])
        self.c.journal_path = Path('/unused/journal.json')
        self.c._collect_observations = Mock(return_value=self.rows)

    def test_collects_exact_five_fresh_requests_before_publication(self):
        with patch.object(controller, 'load_expected_context', return_value=self.context), \
                patch.object(checkpoint, 'publish_pre_driver_checkpoint') as publish:
            self.c._checkpoint_pre_driver_runtime()
        args, kwargs = self.c._collect_observations.call_args
        self.assertEqual(args, (self.context,))
        requests = kwargs['requests']
        self.assertEqual([r.label for r in requests],
                         ['node_before', 'runtime_inventory', 'node', 'cluster_namespace', 'kind_configuration'])
        for request, (label, argv, env) in zip(requests, checkpoint.pre_driver_observation_specs(self.c._identity)):
            self.assertEqual(request.label, label)
            if label == 'kind_configuration':
                self.assertIsNone(request.command)
                self.assertEqual(request.source, 'file')
                self.assertEqual(request.paths, (str(self.c.kind_config),))
            else:
                self.assertEqual(request.command.argv, argv)
                self.assertEqual(request.command.env, env)
                self.assertIsNone(request.command.stdin)
                self.assertFalse(request.command.mutating)
                self.assertEqual(request.command.timeout_s, 300 if label == 'runtime_inventory' else 60)
        publish.assert_called_once_with(self.c.journal_path, self.context, self.rows)

    def test_mismatched_context_rejects_before_collection_or_publication(self):
        variants = [replace(self.context, family='image_load')]
        for key in ('profile', 'workload', 'owned_identity', 'kind_config_path'):
            inputs = decode(self.context.inputs)
            inputs[key] = '/foreign/config' if key == 'kind_config_path' else {}
            variants.append(replace(self.context, inputs=canonical(inputs)))
        for key, field, value in (('workload', 'run_id', 'v3b2-' + 'f' * 64),
                                  ('owned_identity', 'node_container_id', 'f' * 64)):
            inputs = decode(self.context.inputs)
            inputs[key][field] = value
            variants.append(replace(self.context, inputs=canonical(inputs)))
        for index, context in enumerate(variants):
            with self.subTest(index=index), \
                    patch.object(controller, 'load_expected_context', return_value=context), \
                    patch.object(checkpoint, 'publish_pre_driver_checkpoint') as publish:
                with self.assertRaisesRegex(controller.ControllerError, '^pre_driver_checkpoint_failed$'):
                    self.c._checkpoint_pre_driver_runtime()
                self.c._collect_observations.assert_not_called()
                publish.assert_not_called()

    def lifecycle(self, failure=None, polling_failure=False, policy_state='valid'):
        """Exercise actual application dispatch; earlier independent stages are inert."""
        c = self.c
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        private = Path(temporary.name).resolve()
        private.chmod(0o700)
        c.journal_path = private / 'journal.json'
        if policy_state != 'missing':
            policy_path = private / 'policy-stage-3.json'
            policy_path.write_bytes(self.policy if policy_state == 'valid' else b'corrupt')
            policy_path.chmod(0o600)
        journal = {'run_id': self.context.run_id, 'teardown_from_sequence': None,
                   'expected_inputs_sha256': 'a' * 64,
                   'events': [{'sequence': 3, 'event': 'application_apply_intent',
                               'details': decode(self.context.intent)}]}
        c._prepared, c._up, c._events = True, False, []
        c.kubeconfig = Path(c._identity.kubeconfig)
        c.paths = SimpleNamespace(repository=Path('/unused'), private=Path('/unused'))
        c._journal_pair = Mock()  # Pre-application operation families are outside this test.
        c._preflight_application_evidence = Mock()  # Independently covered by terminal integration tests.
        c._pending_runtime_image_authority = Mock(return_value=object())
        c._checkpoint_application_policy = Mock()
        c._abandon_for_teardown = Mock()
        c._require_observed_terminal = Mock(side_effect=controller.ControllerError('terminal_boundary'))
        events = []
        result = controller.CommandResult(0, '{}', '')
        c._observe = Mock(return_value=controller.CommandResult(1 if polling_failure else 0, '{}', ''))
        def run(command, category):
            if command.stdin:
                kinds = {r['kind'] for r in decode(command.stdin)['items']}
                if kinds == {'Pod'}:
                    checkpoint.read_pre_driver_checkpoint(c.journal_path, self.context)
                    events.append('drivers')
                else:
                    events.append('apply')
            return result
        c._run = run
        real_publish = checkpoint.publish_pre_driver_checkpoint
        def publish(path, context, observations):
            if failure:
                raise failure
            real_publish(path, context, observations)
            events.append('persisted')
        with ExitStack() as stack:
            for name, value in (('_write_exclusive', None), ('_read_regular', b'calico'),
                                ('append_event', None), ('parse_calico_runtime_workload', None),
                                ('parse_ready_endpoint_slice', ('endpoint', 'uid'))):
                stack.enter_context(patch.object(controller, name, return_value=value))
            stack.enter_context(patch.object(controller, 'load_expected_context', return_value=self.context))
            stack.enter_context(patch.object(checkpoint, 'load_expected_context', return_value=self.context))
            stack.enter_context(patch.object(checkpoint, 'load_journal', return_value=journal))
            publisher = stack.enter_context(patch.object(checkpoint, 'publish_pre_driver_checkpoint', side_effect=publish))
            with self.assertRaises(controller.ControllerError) as raised:
                c._up_lifecycle()
        return str(raised.exception), events, publisher

    def test_successful_checkpoint_precedes_first_driver_apply(self):
        error, events, publisher = self.lifecycle()
        self.assertEqual(error, 'terminal_boundary')
        self.assertEqual(events, ['apply', 'apply', 'apply', 'persisted', 'drivers'])
        self.assertEqual(publisher.call_count, 1)
        self.c._abandon_for_teardown.assert_not_called()

    def test_failed_checkpoint_abandons_application_without_driver_dispatch(self):
        for failure, policy_state in ((OSError('fsync failed'), 'valid'), (None, 'missing'), (None, 'corrupt')):
            with self.subTest(failure=failure, policy_state=policy_state):
                error, events, publisher = self.lifecycle(failure, policy_state=policy_state)
                self.assertEqual(error, 'pre_driver_checkpoint_failed')
                self.assertNotIn('drivers', events)
                self.c._abandon_for_teardown.assert_called_once_with('application_apply', decode(self.context.intent))
                self.c._require_observed_terminal.assert_not_called()
                self.assertEqual(publisher.call_count, 1)

    def test_bad_transport_prevents_driver_dispatch(self):
        self.c._collect_observations.return_value = (replace(self.rows[0], returncode=1), *self.rows[1:])
        error, events, _ = self.lifecycle()
        self.assertEqual(error, 'pre_driver_checkpoint_failed')
        self.assertNotIn('drivers', events)
        self.c._abandon_for_teardown.assert_called_once()

    def test_failed_polling_never_collects_or_publishes(self):
        error, events, publisher = self.lifecycle(polling_failure=True)
        self.assertEqual(error, 'application_readiness_failed')
        self.assertNotIn('drivers', events)
        self.c._collect_observations.assert_not_called()
        publisher.assert_not_called()

    def test_recovery_does_not_produce_pre_driver_checkpoint(self):
        journal = {'events': [{'event': 'application_apply_intent', 'details': decode(self.context.intent)}]}
        self.c._restore_foreign_comparison = Mock()
        decision = SimpleNamespace(outcome='unknown', category='invalid_or_missing_observation')
        with patch.object(controller, 'load_journal', return_value=journal), \
                patch.object(controller, 'load_expected_context', return_value=self.context), \
                patch.object(controller, 'append_observed_terminal', return_value=decision), \
                patch('kil.v3b2_proofs.cleanup_commands', return_value=()), \
                patch.object(checkpoint, 'publish_pre_driver_checkpoint') as publish, \
                patch.object(self.c, '_checkpoint_pre_driver_runtime') as producer:
            result = self.c.recover()
        self.assertEqual(result['proof_outcome'], 'unknown')
        self.c._collect_observations.assert_called_once_with(self.context)
        producer.assert_not_called()
        publish.assert_not_called()


if __name__ == '__main__':
    unittest.main()
