from dataclasses import asdict, replace
from hashlib import sha256
import importlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kil import v3b2_proofs as proofs
from kil.v3b2_application_policy_stage import application_policy_observation_specs
from kil.v3b2_manifests import render_kind_config
from kil.v3b2_policy_stage_checkpoint import encode_policy_stage_checkpoint
from tests.test_v3b2_pre_driver_runtime import fixture as runtime_fixture
from tests.test_v3b2_application_policy_stage import ROOT

MODULE = 'kil.v3b2_pre_driver_checkpoint'


def fixture():
    args, runtime = runtime_fixture()
    args['owned_identity'] = replace(args['owned_identity'], cluster_incarnation_uid='11111111-1111-4111-8111-111111111111')
    document = proofs.decode(args['runtime_objects'])
    next(r for r in document['items'] if r['kind'] == 'Namespace' and r['metadata']['name'] == 'kube-system')['metadata']['uid'] = args['owned_identity'].cluster_incarnation_uid
    args['runtime_objects'] = proofs.canonical(document)
    identity, workload, profile = (args[key] for key in ('owned_identity', 'workload', 'profile'))
    kind = render_kind_config(profile)
    objects = proofs.decode(args['rendered_objects'])['items']
    base = {'run_id': workload.run_id.removeprefix('v3b2-'),
            'profile': proofs.decode((ROOT / 'deploy/kind/v3b2-profile.json').read_bytes()),
            'workload': asdict(workload), 'owned_identity': asdict(identity),
            'application_objects': objects, 'applied_objects': objects,
            'kind_node_image': profile.kind_node_image,
            'kind_config_path': str(Path(identity.kubeconfig).parent / 'kind-config.yaml'),
            'kind_config_sha256': sha256(kind).hexdigest(), 'runtime_contract_complete': False,
            'node_image_source_version': 1,
            'images': [{'reference': image.query_reference, 'manifest_digest': image.target_digest,
                        'config_digest': image.config_digest, 'target_media_type': image.target_media_type,
                        'allowed_repo_tags': list(image.allowed_repo_tags),
                        'allowed_repo_digests': list(image.allowed_repo_digests)}
                       for image in runtime.node_images.expected_images]}
    node = proofs.canonical([{'Id': identity.node_container_id, 'Name': '/kil-v3-lab-control-plane',
        'Image': 'sha256:' + '6' * 64, 'Config': {'Image': profile.kind_node_image,
        'Labels': {'io.x-k8s.kind.cluster': 'kil-v3-lab', 'io.x-k8s.kind.role': 'control-plane'}}}])
    payloads = {'node_before': node, 'node': node, 'kind_configuration': kind,
        'cluster_namespace': proofs.canonical({'apiVersion': 'v1', 'kind': 'Namespace',
            'metadata': {'name': 'kube-system', 'uid': identity.cluster_incarnation_uid}})}
    intent = {'image': base['images'][0]['reference'], 'envoy_image': base['images'][1]['reference']}
    image_context = proofs.ExpectedContext(base['run_id'], 1, 'image_load', proofs.canonical(intent), proofs.canonical(base))
    payloads.update({row.label: row.stdout for row in (*runtime.node_images.inspections, runtime.node_images.node_images)})
    source_rows = tuple(proofs.RawObservation(request.label,
        () if request.command is None else request.command.argv,
        () if request.command is None else request.command.env, 0, payloads[request.label], b'')
        for request in proofs.OPERATIONS['image_load'].requests(image_context))
    decision = proofs.decide(image_context, source_rows)
    assert decision.outcome == 'complete', decision
    source = proofs.observation_bundle(image_context, source_rows, decision)
    inputs = {**base, 'prior_node_image_source': proofs.decode(source), 'history': [
        {'sequence': 1, 'event': 'image_load_intent', 'details': intent},
        proofs.terminal_event(image_context, decision, sha256(source).hexdigest())]}
    context = proofs.ExpectedContext(base['run_id'], 3, 'application_apply',
        proofs.canonical({'manifest_sha256': sha256(args['rendered_objects']).hexdigest()}), proofs.canonical(inputs))
    current = proofs.decode(args['runtime_objects'])['items']
    desired_keys = {(r['kind'], r['metadata'].get('namespace', ''), r['metadata']['name'])
                    for r in objects if r['kind'] in {'Namespace', 'NetworkPolicy'}}
    policies = [r for r in current if (r['kind'], r['metadata'].get('namespace', ''), r['metadata']['name']) in desired_keys]
    payloads['policy_objects'] = proofs.canonical({'apiVersion': 'v1', 'kind': 'List', 'items': policies})
    from kil.v3b2_contracts import TRACK_NAMESPACES
    for _, ns in TRACK_NAMESPACES:
        payloads[ns + ':workload_absence'] = proofs.canonical({'apiVersion': 'v1', 'kind': 'List', 'items': []})
    specs = application_policy_observation_specs(identity)
    policy_rows = tuple(proofs.RawObservation(label, argv, env, 0, payloads[label], b'') for label, argv, env in specs)
    policy = encode_policy_stage_checkpoint(context, policy_rows)
    runtime_row = proofs.RawObservation('runtime_inventory', ('kubectl', '--kubeconfig', identity.kubeconfig,
        'get', proofs.RUNTIME_RESOURCES, '--all-namespaces', '--output', 'json'), (), 0, args['runtime_objects'], b'')
    rows = (policy_rows[0], runtime_row, *policy_rows[-3:])
    return context, policy, rows


class PreDriverCheckpointTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'pre-driver checkpoint module missing')
        self.module = importlib.import_module(MODULE)
        self.context, self.policy, self.rows = fixture()

    def test_retains_nineteen_pods_nine_runtime_and_policy_source(self):
        proof = self.module.validate_pre_driver_checkpoint(context=self.context,
            policy_checkpoint_bytes=self.policy, observations=self.rows)
        self.assertEqual(len(proof.runtime.bindings), 9)
        self.assertEqual(len(proof.policy_continuity), 18)
        self.assertEqual(proof.policy_checkpoint_bytes, self.policy)
        self.assertEqual(sum(r['kind'] == 'Pod' for r in proofs.decode(proof.runtime.ownership.runtime_objects)['items']), 19)
        self.assertIs(proof.runtime_contract_complete, False)
        self.assertIs(proof.full_application_contract_complete, False)
        self.assertEqual(replace(proof), proof)
        payload = self.module.encode_pre_driver_checkpoint(self.context, self.policy, self.rows)
        self.assertEqual(self.module.decode_pre_driver_checkpoint(payload, self.context), proof)

    def test_rejects_constructor_registry_transport_and_raw_tampering(self):
        validate = lambda rows: self.module.validate_pre_driver_checkpoint(context=self.context,
            policy_checkpoint_bytes=self.policy, observations=rows)
        proof = validate(self.rows)
        for changes in ({'runtime': object()}, {'policy_continuity': ()}, {'runtime_contract_complete': 1},
                        {'full_application_contract_complete': True}, {'raw_observations': proof.raw_observations + b' '},
                        {'policy_checkpoint_bytes': self.policy + b' '}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): replace(proof, **changes)
        for rows in (self.rows[:-1], (*self.rows, self.rows[-1]), tuple(reversed(self.rows)),
                     (replace(self.rows[0], env=()), *self.rows[1:]),
                     (replace(self.rows[0], returncode=1), *self.rows[1:]),
                     (replace(self.rows[0], stderr=b'warning'), *self.rows[1:]),
                     (*self.rows[:1], replace(self.rows[1], argv=('kubectl',)), *self.rows[2:]),
                     (*self.rows[:-1], replace(self.rows[-1], stdout=b'bad'))):
            with self.subTest(), self.assertRaises(ValueError): validate(rows)

    def test_policy_uid_and_configuration_changes_fail_but_rv_can_change(self):
        for field, value, accepted in (('uid', 'changed', False), ('resourceVersion', '1', True),
                                       ('resourceVersion', '', False), ('labels', {'foreign': 'yes'}, False)):
            document = proofs.decode(self.rows[1].stdout)
            row = next(r for r in document['items'] if r['kind'] == 'NetworkPolicy')
            row['metadata'][field] = value
            rows = (self.rows[0], replace(self.rows[1], stdout=proofs.canonical(document)), *self.rows[2:])
            if accepted:
                self.module.encode_pre_driver_checkpoint(self.context, self.policy, rows)
            else:
                with self.subTest(field=field), self.assertRaises(ValueError):
                    self.module.encode_pre_driver_checkpoint(self.context, self.policy, rows)

    def test_envelope_context_duplicates_and_ready_inventory_reject(self):
        payload = self.module.encode_pre_driver_checkpoint(self.context, self.policy, self.rows)
        for field, value in (('context_commitment', 'f' * 64), ('run_id', 'f' * 64),
                             ('intent_sequence', True), ('observations', []), ('policy_checkpoint', {})):
            document = proofs.decode(payload); document[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.module.decode_pre_driver_checkpoint(proofs.canonical(document), self.context)
        with self.assertRaises(ValueError): self.module.decode_pre_driver_checkpoint(payload + b' ', self.context)
        with self.assertRaises(ValueError): self.module.decode_pre_driver_checkpoint(b'{"schema":0,' + payload[1:], self.context)
        _, ready = runtime_fixture()
        rows = (self.rows[0], replace(self.rows[1], stdout=ready.configuration.ownership.runtime_objects), *self.rows[2:])
        with self.assertRaises(ValueError): self.module.encode_pre_driver_checkpoint(self.context, self.policy, rows)

    def test_decoder_rejects_non_hex_types_as_invalid_evidence(self):
        payload = self.module.encode_pre_driver_checkpoint(self.context, self.policy, self.rows)
        for value in (None, [], 1):
            document = proofs.decode(payload); document['observations'][1]['stdout_hex'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.module.decode_pre_driver_checkpoint(proofs.canonical(document), self.context)

    def test_source_and_node_bracket_are_revalidated(self):
        for index, field, value in ((0, 'Id', 'f' * 64), (0, 'Image', 'sha256:' + 'f' * 64),
                                    (2, 'Name', '/foreign')):
            rows = list(self.rows); node = proofs.decode(rows[index].stdout); node[0][field] = value
            rows[index] = replace(rows[index], stdout=proofs.canonical(node))
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.module.encode_pre_driver_checkpoint(self.context, self.policy, tuple(rows))
        inputs = proofs.decode(self.context.inputs); inputs.pop('prior_node_image_source')
        context = replace(self.context, inputs=proofs.canonical(inputs))
        policy = proofs.decode(self.policy); policy['context_commitment'] = context.commitment
        with self.assertRaises(ValueError):
            self.module.encode_pre_driver_checkpoint(context, proofs.canonical(policy), self.rows)

    def durable_setup(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.private = Path(temporary.name).resolve(); self.private.chmod(0o700)
        self.path = self.private / 'journal.json'
        self.target = self.private / 'pre-driver-stage-3.json'
        policy = self.private / 'policy-stage-3.json'; policy.write_bytes(self.policy); policy.chmod(0o600)
        self.journal = {'run_id': self.context.run_id, 'teardown_from_sequence': None,
            'expected_inputs_sha256': 'a' * 64, 'events': [{'sequence': 3, 'event': 'application_apply_intent',
                                                         'details': proofs.decode(self.context.intent)}]}

    def publish(self):
        with patch(MODULE + '.load_journal', return_value=self.journal), patch(
                MODULE + '.load_expected_context', return_value=self.context):
            return self.module.publish_pre_driver_checkpoint(self.path, self.context, self.rows)

    def test_durable_write_once_reads_existing_policy_and_authenticates_pending_context(self):
        self.assertTrue(hasattr(self.module, 'publish_pre_driver_checkpoint'), 'durable publisher missing')
        self.durable_setup()
        proof = self.publish(); self.assertEqual(self.publish(), proof)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.module.read_pre_driver_checkpoint(self.path, self.context), proof)
        self.assertEqual(self.module.read_pre_driver_checkpoint_bytes(self.path, self.context), self.target.read_bytes())
        self.target.write_bytes(b'corrupt')
        with self.assertRaises(ValueError): self.publish()
        self.assertEqual(self.target.read_bytes(), b'corrupt')
        self.target.unlink()
        for field, value in (('teardown_from_sequence', 3), ('expected_inputs_sha256', None),
                             ('run_id', 'f' * 64), ('events', [])):
            original = self.journal[field]; self.journal[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.publish()
            self.journal[field] = original
        with patch(MODULE + '.load_journal', return_value=self.journal), patch(
                MODULE + '.load_expected_context', return_value=replace(self.context, intent_sequence=4)):
            with self.assertRaises(ValueError): self.module.publish_pre_driver_checkpoint(self.path, self.context, self.rows)
        (self.private / 'policy-stage-3.json').unlink()
        with self.assertRaises((ValueError, OSError)): self.publish()
        self.assertFalse(self.target.exists())

    def test_reader_permissions_links_fifo_and_oversize(self):
        self.assertTrue(hasattr(self.module, 'publish_pre_driver_checkpoint'), 'durable publisher missing')
        self.durable_setup(); self.publish()
        read = lambda: self.module.read_pre_driver_checkpoint(self.path, self.context)
        self.target.chmod(0o644)
        with self.assertRaises(ValueError): read()
        self.target.chmod(0o600)
        os.link(self.target, self.private / 'alias')
        with self.assertRaises(ValueError): read()
        (self.private / 'alias').unlink()
        saved = self.private / 'saved'; self.target.rename(saved); self.target.symlink_to(saved)
        with self.assertRaises((ValueError, OSError)): read()
        self.target.unlink(); os.mkfifo(self.target, 0o600)
        with self.assertRaises(ValueError): read()
        self.target.unlink()
        with self.target.open('wb') as stream: stream.truncate(self.module._MAX_BYTES + 1)
        self.target.chmod(0o600)
        with patch(MODULE + '.os.read', side_effect=AssertionError('oversize file was read')):
            with self.assertRaises(ValueError): read()

    def test_reader_detects_parent_and_file_changes_during_read(self):
        self.assertTrue(hasattr(self.module, 'publish_pre_driver_checkpoint'), 'durable publisher missing')
        self.durable_setup(); self.publish()
        real_read = os.read
        for mutation in ('parent_permissions', 'file_permissions', 'file_replacement', 'parent_replacement'):
            saved = self.private.parent / (self.private.name + '-saved')
            changed = False
            original = self.target.read_bytes()
            def changed_read(*args):
                nonlocal changed
                data = real_read(*args)
                if not changed:
                    changed = True
                    if mutation == 'parent_permissions': self.private.chmod(0o755)
                    elif mutation == 'file_permissions': self.target.chmod(0o644)
                    elif mutation == 'file_replacement':
                        self.target.unlink(); self.target.write_bytes(original); self.target.chmod(0o600)
                    else:
                        self.private.rename(saved); self.private.mkdir(mode=0o700)
                return data
            try:
                with self.subTest(mutation=mutation), patch(MODULE + '.os.read', side_effect=changed_read):
                    with self.assertRaises(ValueError): self.module.read_pre_driver_checkpoint(self.path, self.context)
            finally:
                if mutation == 'parent_replacement' and changed:
                    self.private.rmdir(); saved.rename(self.private)
                self.private.chmod(0o700); self.target.chmod(0o600)
