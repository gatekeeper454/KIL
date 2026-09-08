"""Closed Colima inventory and directory-only completeness, using temporary homes."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch


def profile(name='foreign', **extra):
    return dict(name=name, status='Running', arch='aarch64', cpus=2,
                memory=4 * 1024**3, disk=20 * 1024**3, runtime='docker') | extra


def roster(names):
    """Pure retained roster fixture; controller tests collect actual directories."""
    entries = sorted(names)
    return {'directory': {'device': 1, 'inode': 2, 'mode': stat.S_IFDIR | 0o700, 'entries': entries},
            'children': [{'name': name, 'device': 1, 'inode': index + 3, 'mode': stat.S_IFDIR | 0o700}
                         for index, name in enumerate(entries)]}


def inventory_observations(rows, authority, snapshot):
    from kil import v3b2_proofs as proofs
    private = Path(authority['private'])
    env = (('DOCKER_CONFIG', str(private / 'docker-config')), ('TMPDIR', str(private / 'runtime-tmp')))
    return (proofs.RawObservation('profile_roster_before', (), (), 0, proofs.canonical(snapshot), b''),
            proofs.RawObservation('profile_inventory', proofs.PROFILE_INVENTORY_ARGV, env, 0, proofs.canonical(rows), b''),
            proofs.RawObservation('profile_roster_after', (), (), 0, proofs.canonical(snapshot), b''))


class ColimaInventoryTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('kil.v3b2_colima_inventory'),
                             'shared closed Colima inventory boundary is missing')
        from kil import v3b2_colima_inventory
        self.inventory = v3b2_colima_inventory

    def test_jsonl_array_single_object_and_successful_empty(self):
        rows = [profile('a'), profile('b')]
        for payload in (json.dumps(rows).encode(), b'\n'.join(json.dumps(r).encode() for r in rows)):
            self.assertEqual(self.inventory.decode_inventory(payload), rows)
        self.assertEqual(self.inventory.decode_inventory(json.dumps(rows[0]).encode()), rows[:1])
        for payload in (b'', b' \n\t', b'[]\n'):
            self.assertEqual(self.inventory.decode_inventory(payload), [])
        with self.assertRaises(ValueError):
            self.inventory.decode_inventory(b'', returncode=1)
        with self.assertRaises(ValueError):
            self.inventory.decode_inventory(b'', stderr=b'partial')

    def test_runtime_address_and_alias_normalization(self):
        for runtime in ('docker', 'containerd', 'incus', 'docker+k3s', 'containerd+k3s', 'incus+k3s', 'none'):
            for address in (None, '192.0.2.15', '2001:db8::1'):
                row = profile(runtime=runtime, status='running', arch='arm64')
                if address is not None:
                    row['address'] = address
                expected = row | {'status': 'Running', 'arch': 'aarch64'}
                self.assertEqual(self.inventory.validate_records([row]), [expected])
        self.assertEqual(self.inventory.validate_records([profile(arch='amd64', status='stopped')])[0]['arch'], 'x86_64')

    def test_invalid_closed_records_and_bounds(self):
        bad = []
        for field in profile():
            row = profile(); del row[field]; bad.append([row])
        bad += [[profile(extra=1)], [profile(runtime='none+k3s')], [profile(runtime='unknown')],
                [profile(), profile()], [profile(name='')], [profile(name='../foreign')],
                [profile(name='x' * 4097)], [profile(name='bad\ud800')]]
        for field in ('cpus', 'memory', 'disk'):
            bad += [[profile(**{field: value})] for value in (True, 0, -1, 1.0, '2', 2**64)]
        for address in ('', 'http://192.0.2.1', '192.0.2.1/24', 'fe80::1%en0', '[::1]:22', 'localhost', 123, None):
            bad.append([profile(address=address)])
        bad.append([profile(str(i)) for i in range(self.inventory.MAX_RECORDS + 1)])
        for rows in bad:
            with self.subTest(rows=str(rows)[:100]), self.assertRaises(ValueError):
                self.inventory.validate_records(rows)
        duplicate = json.dumps(profile()).replace('"runtime": "docker"', '"runtime": "none", "runtime": "docker"').encode()
        for payload in (duplicate, b'{"name":"a","name":"b"}', b'{}\n{}', b'null', b'[NaN]', b'\xff',
                        b' ' * (self.inventory.MAX_PAYLOAD_BYTES + 1)):
            with self.subTest(payload=payload[:50]), self.assertRaises(ValueError):
                self.inventory.decode_inventory(payload)

    def test_complete_roster_and_default_mapping(self):
        for rows, names in (([], []), ([profile('default')], ['colima']),
                            ([profile()], ['_config', '_networks', '_disks', '_templates', '_cache', 'colima-foreign'])):
            snapshot = roster(names)
            self.assertEqual(self.inventory.require_complete(rows, snapshot, deepcopy(snapshot)), rows)
        self.assertEqual(self.inventory.require_complete([], None, None), [])

    def test_truncated_partial_ambiguous_missing_and_changed_rosters_fail(self):
        cases = [([], roster(['colima-foreign'])), ([profile()], None),
                 ([profile()], roster(['colima-foreign', 'colima-other'])),
                 ([], roster(['other-vm'])), ([], roster(['colimafoo'])),
                 ([], roster(['colima-default'])), ([], roster(['colima-colima-foo'])),
                 ([], roster(['_unknown'])), ([], {'directory': None, 'children': []})]
        for rows, observed in cases:
            with self.subTest(observed=observed), self.assertRaises(ValueError):
                self.inventory.require_complete(rows, observed, observed)
        before = roster(['colima-foreign']); after = deepcopy(before)
        after['children'][0]['inode'] += 1
        with self.assertRaises(ValueError):
            self.inventory.require_complete([profile()], before, after)
        unsafe = deepcopy(before); unsafe['children'][0]['mode'] = stat.S_IFLNK | 0o777
        with self.assertRaises(ValueError):
            self.inventory.require_complete([profile()], unsafe, unsafe)

    def test_roster_reads_only_directory_metadata_and_rejects_symlinks(self):
        from kil.v3b2_profile_state import ProfilePaths
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); paths = ProfilePaths(root / 'home', root / 'private')
            foreign = paths.lima / 'colima-foreign'; foreign.mkdir(parents=True)
            (foreign / 'secret').write_text('guest data is out of scope')
            with patch('kil.v3b2_profile_state.os.read', side_effect=AssertionError('guest content read')):
                observed = self.inventory.capture_roster(paths)
            self.assertEqual(self.inventory.require_complete([profile()], observed, observed), [profile()])
            foreign.rename(paths.lima / 'other')
            foreign.symlink_to(paths.lima / 'other', target_is_directory=True)
            with self.assertRaises(ValueError):
                self.inventory.capture_roster(paths)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); (root / 'target').mkdir(); (root / 'home').symlink_to(root / 'target')
            with self.assertRaises(ValueError):
                self.inventory.capture_roster(ProfilePaths(root / 'home', root / 'private'))

    def test_non_directory_roster_is_rejected_without_reading_its_bytes(self):
        from kil.v3b2_profile_state import ProfilePaths
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); paths = ProfilePaths(root / 'home', root / 'private')
            paths.colima.mkdir(parents=True); paths.lima.write_bytes(b'not a directory')
            with patch('kil.v3b2_profile_state.os.read', side_effect=AssertionError('roster file read')):
                with self.assertRaises(ValueError):
                    self.inventory.capture_roster(paths)

    def test_adapters_share_closed_full_normalization(self):
        from kil.v3b2_controller import V3B2Controller
        from kil.v3b2_evidence import _foreign_records
        row = profile(runtime='incus+k3s', address='2001:db8::2', arch='arm64', status='running')
        expected = self.inventory.validate_records([row])
        self.assertEqual(V3B2Controller._foreign_records(json.dumps(row)), expected)
        self.assertEqual(_foreign_records([row]), expected)

    def test_private_address_state_is_keyed_and_publicly_closed(self):
        from kil.v3b2_evidence import project_foreign_profiles, _verify_foreign_projection
        key = b'private projection secret'
        before = profile(address='192.0.2.15')
        for after in (profile(address='2001:db8::2'), profile(), before | {'runtime': 'incus+k3s'}):
            public = project_foreign_profiles([before], [after], key)
            self.assertFalse(public['unchanged'])
            self.assertNotEqual(public['before'][0]['state_hmac_sha256'], public['after'][0]['state_hmac_sha256'])
            text = json.dumps(public)
            for secret in ('foreign', '192.0.2.15', '2001:db8::2', key.decode(), 'address'):
                self.assertNotIn(secret, text)
            _verify_foreign_projection(public)
            forged = deepcopy(public); forged['unchanged'] = True
            with self.assertRaises(ValueError):
                _verify_foreign_projection(forged)
            malformed = deepcopy(public); malformed['after'][0]['state_hmac_sha256'] = 'invalid'
            with self.assertRaises(ValueError):
                _verify_foreign_projection(malformed)
        other = project_foreign_profiles([before], [before], b'another private key')
        public = project_foreign_profiles([before], [before], key)
        self.assertNotEqual(public['before'][0]['state_hmac_sha256'], other['before'][0]['state_hmac_sha256'])

    def test_pure_proof_requires_complete_stable_bracket_and_exact_environment(self):
        from kil import v3b2_proofs as proofs
        authority = {'home': '/tmp/isolated-home', 'private': '/tmp/isolated-private'}
        before = profile(address='192.0.2.15')
        expected = {'foreign_before': [before], 'global_context_before': 'global', 'profile_paths': authority}
        context = proofs.ExpectedContext('a' * 64, 1, 'foreign_snapshot_comparison', b'{}\n', proofs.canonical(expected))
        env = (('DOCKER_CONFIG', '/tmp/isolated-private/docker-config'), ('TMPDIR', '/tmp/isolated-private/runtime-tmp'))
        def observations(rows, snapshot):
            return (proofs.RawObservation('profile_roster_before', (), (), 0, proofs.canonical(snapshot), b''),
                    proofs.RawObservation('profile_inventory', proofs.PROFILE_INVENTORY_ARGV, env, 0, proofs.canonical(rows), b''),
                    proofs.RawObservation('profile_roster_after', (), (), 0, proofs.canonical(snapshot), b''),
                    proofs.RawObservation('global_context', ('docker', 'context', 'show'), (), 0, b'global\n', b''))
        good = observations([before], roster(['colima-foreign']))
        self.assertEqual(proofs.decide(context, good).outcome, 'complete')
        self.assertTrue(proofs.decode(proofs.decide(context, good).bindings)['unchanged'])
        changed = observations([before | {'address': '2001:db8::1'}], roster(['colima-foreign']))
        self.assertFalse(proofs.decode(proofs.decide(context, changed).bindings)['unchanged'])
        missing = good[1:]
        truncated = observations([], roster(['colima-foreign']))
        partial = observations([before], roster(['colima-foreign', 'colima-second']))
        wrong_env = (good[0], proofs.RawObservation('profile_inventory', proofs.PROFILE_INVENTORY_ARGV, (), 0, proofs.canonical([before]), b''), *good[2:])
        moved = (good[2], good[1], good[0], good[3])
        changed_roster = (*good[:2], proofs.RawObservation('profile_roster_after', (), (), 0, proofs.canonical(roster([])), b''), good[3])
        for bad in (missing, truncated, partial, wrong_env, moved, changed_roster):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                proofs._profile_rows(bad, authority)
            self.assertEqual(proofs.decide(context, bad).outcome, 'unknown')
        retained = proofs.observation_bundle(context, good, proofs.decide(context, good))
        self.assertIn(b'profile_roster_before', retained)

    def test_all_profile_registry_requests_bracket_inventory(self):
        from kil import v3b2_proofs as proofs
        for family in ('profile_start', 'profile_stop', 'profile_delete', 'profile_absence_proof', 'foreign_snapshot_comparison'):
            context = proofs.ExpectedContext('a' * 64, 1, family, b'{}\n', proofs.canonical({
                'profile_paths': {'home': '/tmp/home', 'private': '/tmp/private'}, 'active_paths': []}))
            requests = proofs.OPERATIONS[family].requests(context)
            self.assertEqual([row.label for row in requests[:3]],
                             ['profile_roster_before', 'profile_inventory', 'profile_roster_after'])


class ColimaInventoryControllerTest(unittest.TestCase):
    from tests import test_v3b2_controller as fixtures
    setUp = fixtures.V3B2ControllerTest.setUp
    tearDown = fixtures.V3B2ControllerTest.tearDown

    def test_preflight_rejects_successful_truncated_empty_or_partial_inventory(self):
        from kil.v3b2_controller import ControllerError
        for name in ('foreign', 'second'):
            (self.controller.profile_paths.lima / ('colima-' + name)).mkdir(parents=True)
        for rows in ([], [profile()]):
            self.runner.profiles = rows
            with self.subTest(rows=rows), self.assertRaisesRegex(ControllerError, 'incomplete_profile_inventory'):
                self.controller.preflight()
            self.assertFalse(self.controller.journal_path.exists())
            self.assertFalse(any(command.mutating for command in self.runner.commands))

    def test_preflight_accepts_complete_jsonl_and_preserves_private_fields(self):
        from kil.v3b2_controller import CommandResult, V3B2Controller
        rows = [profile('default', runtime='none'), profile(address='2001:db8::5', runtime='incus+k3s')]
        for name in ('colima', 'colima-foreign'):
            (self.controller.profile_paths.lima / name).mkdir(parents=True)
        original = self.runner.run
        def run(command):
            if command.argv == ('colima', 'list', '--json'):
                self.runner.commands.append(command)
                return CommandResult(0, '\n'.join(json.dumps(row) for row in rows) + '\n', '')
            return original(command)
        with patch.object(self.runner, 'run', side_effect=run):
            self.controller.preflight()
        expected = json.loads(self.controller.expected_inputs_path.read_bytes())
        self.assertEqual(expected['foreign_before'], rows)
        self.assertFalse(expected['runtime_contract_complete'])
        self.assertEqual(V3B2Controller(self.paths, self.runner)._foreign_records_before, rows)
        observations = self.controller._collect_profile_inventory()
        inventory = next(row for row in observations if row.label == 'profile_inventory')
        self.assertEqual(dict(inventory.env), {'DOCKER_CONFIG': str(self.controller.docker_config),
                                            'TMPDIR': str(self.controller.profile_paths.tmp)})
        self.assertFalse(any(command.mutating for command in self.runner.commands))

    def test_preflight_changed_bracket_and_symlinked_roster_fail_before_authority(self):
        from kil.v3b2_controller import ControllerError
        (self.controller.profile_paths.lima / 'colima-foreign').mkdir(parents=True)
        self.runner.profiles = [profile()]
        original = self.runner.run
        def changed(command):
            result = original(command)
            if command.argv == ('colima', 'list', '--json'):
                (self.controller.profile_paths.lima / 'colima-second').mkdir()
            return result
        with patch.object(self.runner, 'run', side_effect=changed):
            with self.assertRaisesRegex(ControllerError, 'incomplete_profile_inventory'):
                self.controller.preflight()
        self.assertFalse(self.controller.journal_path.exists())
        foreign = self.controller.profile_paths.lima / 'colima-foreign'
        foreign.rmdir(); foreign.symlink_to(self.isolated_home)
        with self.assertRaises(ControllerError):
            self.controller.preflight()
        self.assertFalse(self.controller.journal_path.exists())
        self.assertFalse(any(command.mutating for command in self.runner.commands))

    def test_owned_foreign_runtime_or_address_never_proves_owned_configuration(self):
        from kil.v3b2_journal import append_event, load_expected_context
        from kil import v3b2_proofs as proofs
        from tests.test_v3b2_profile_state import create_profile
        self.controller.preflight()
        create_profile(self.controller.profile_paths)
        append_event(self.controller.journal_path, 'profile_start_intent', {'colima_profile': 'kil-v3-lab'})
        context = load_expected_context(self.controller.journal_path)
        owned = profile('kil-v3-lab', cpus=4, memory=8 * 1024**3, disk=60 * 1024**3)
        for changed in (owned | {'runtime': 'incus'}, owned | {'address': '192.0.2.10'}):
            self.runner.profiles = [changed]
            observations = self.controller._collect_observations(context)
            self.assertEqual(proofs.decide(context, observations).outcome, 'unknown')
            self.assertEqual(proofs.cleanup_commands(context, observations), ())
        self.runner.profiles = [owned]
        self.assertEqual(proofs.decide(context, self.controller._collect_observations(context)).outcome, 'complete')

    def test_incomplete_inventory_retains_private_active_paths(self):
        self.controller.preflight()
        (self.controller.profile_paths.lima / 'colima-foreign').mkdir(parents=True)
        self.controller.kubeconfig.write_bytes(b'private recovery material')
        self.assertFalse(self.controller._clear_active_paths_if_profile_absent())
        self.assertTrue(self.controller.kubeconfig.exists())
        self.assertFalse(any(command.mutating for command in self.runner.commands))

    def test_offline_replay_rejects_missing_roster_even_with_repaired_proof_digest(self):
        from hashlib import sha256
        from kil.v3b2_controller import ControllerError, V3B2Controller
        from kil.v3b2_journal import load_journal
        from kil.v3b2_proofs import canonical
        self.controller.preflight()
        self.controller._journal_pair('profile_start', {'colima_profile': 'kil-v3-lab'}, self.controller._start_profile)
        with patch.object(self.runner, 'run', side_effect=AssertionError('offline replay ran a command')):
            V3B2Controller(self.paths, self.runner)
            journal = load_journal(self.controller.journal_path)
            terminal = journal['events'][-1]
            digest = terminal['details']['observed_proof_sha256']
            document = json.loads((self.paths.private / ('proof-1-' + digest + '.json')).read_bytes())
            document['observations'] = [row for row in document['observations'] if row['label'] != 'profile_roster_before']
            payload = canonical(document); replacement = sha256(payload).hexdigest()
            repaired_path = self.paths.private / ('proof-1-' + replacement + '.json')
            repaired_path.write_bytes(payload)
            repaired_path.chmod(0o600)
            terminal['details']['observed_proof_sha256'] = replacement
            self.controller.journal_path.write_bytes(canonical(journal))
            with self.assertRaisesRegex(ControllerError, 'prior_proof_invalid'):
                V3B2Controller(self.paths, self.runner)

    def _ready_for_foreign_comparison(self):
        from kil.v3b2_controller import CommandResult, ControllerError
        row = profile(address='192.0.2.15')
        self.runner.profiles = [row]
        (self.controller.profile_paths.lima / 'colima-foreign').mkdir(parents=True)
        self.controller.preflight()
        with self.assertRaises(ControllerError):
            self.controller._journal_pair('profile_start', {'colima_profile': 'kil-v3-lab'}, lambda: CommandResult(0, '', ''))
        self.controller._clear_active_paths_if_profile_absent()
        self.controller._journal_pair('profile_absence_proof', {'colima_profile': 'kil-v3-lab'}, lambda: CommandResult(0, '', ''))
        return row

    def _assert_retained_foreign_state(self, controller):
        from hashlib import sha256
        from kil.v3b2_journal import load_journal
        from kil.v3b2_proofs import canonical
        from kil.v3b2_colima_inventory import decode_inventory
        journal = load_journal(controller.journal_path)
        terminal = journal['events'][-1]
        digest = terminal['details']['observed_proof_sha256']
        path = self.paths.private / ('proof-' + str(terminal['sequence'] - 1) + '-' + digest + '.json')
        document = json.loads(path.read_bytes())
        rows = {row['label']: row for row in document['observations']}
        after = decode_inventory(bytes.fromhex(rows['profile_inventory']['stdout_hex']))
        context_after = bytes.fromhex(rows['global_context']['stdout_hex']).decode().strip()
        commitment = sha256(canonical({'profiles': after, 'global_context': context_after})).hexdigest()
        self.assertEqual(terminal['details']['attestation_sha256'], commitment)
        self.assertEqual(controller._foreign_records_after, after)
        self.assertEqual(controller._context_after, context_after)
        self.assertEqual(document['bindings'], {'foreign_after': after, 'global_context_after': context_after,
                                              'attestation_sha256': commitment,
                                              'unchanged': after == controller._foreign_records_before and context_after == controller._context_before})
        self.assertEqual(terminal['details']['unchanged'], document['bindings']['unchanged'])
        return journal, path, document

    def _sequential_foreign_samples(self, *, changed_first):
        from kil.v3b2_controller import CommandResult, ControllerError, V3B2Controller
        before = self._ready_for_foreign_comparison()
        changed = before | {'address': '2001:db8::15'}
        samples = [changed, before] if changed_first else [before, changed]
        original = self.runner.run; count = 0
        def sequential(command):
            nonlocal count
            if command.argv == ('colima', 'list', '--json'):
                row = samples[min(count, 1)]; count += 1
                return CommandResult(0, json.dumps([row]), '')
            return original(command)
        with patch.object(self.runner, 'run', side_effect=sequential):
            try:
                self.controller._compare_foreign()
            except ControllerError as error:
                self.assertEqual(str(error), 'foreign_state_changed')
        self._assert_retained_foreign_state(self.controller)
        self.assertEqual(count, 1, 'normal comparison took a second independent sample')
        with patch.object(self.runner, 'run', side_effect=AssertionError('hydration sampled live state')):
            resumed = V3B2Controller(self.paths, self.runner)
            self._assert_retained_foreign_state(resumed)

    def test_address_changes_between_samples_cannot_split_terminal_and_private_state(self):
        self._sequential_foreign_samples(changed_first=False)

    def test_address_reverts_between_samples_cannot_split_terminal_and_private_state(self):
        self._sequential_foreign_samples(changed_first=True)

    def test_pending_foreign_recovery_rederives_changed_sample_and_hydrates_after_terminal(self):
        from kil.v3b2_controller import V3B2Controller
        from kil.v3b2_journal import append_event
        before = self._ready_for_foreign_comparison()
        self.runner.profiles = [before | {'address': '2001:db8::15'}]
        append_event(self.controller.journal_path, 'foreign_snapshot_comparison_intent',
                     {'unchanged': True, 'attestation_sha256': 'f' * 64})
        self.assertEqual(self.controller.recover()['proof_outcome'], 'complete')
        journal, _path, _document = self._assert_retained_foreign_state(self.controller)
        self.assertFalse(journal['events'][-1]['details']['unchanged'])
        with patch.object(self.runner, 'run', side_effect=AssertionError('hydration sampled live state')):
            self._assert_retained_foreign_state(V3B2Controller(self.paths, self.runner))

    def test_repaired_foreign_proof_digest_cannot_relabel_attestation_or_after_state(self):
        from hashlib import sha256
        from kil.v3b2_controller import ControllerError, V3B2Controller
        from kil.v3b2_proofs import canonical, ProofError
        from kil.v3b2_journal import load_expected_context
        self._ready_for_foreign_comparison()
        self.controller._compare_foreign()
        journal, path, document = self._assert_retained_foreign_state(self.controller)
        for field, value in (('attestation_sha256', 'f' * 64), ('foreign_after', [profile(address='2001:db8::19')])):
            forged = deepcopy(document); forged['bindings'][field] = value
            payload = canonical(forged); digest = sha256(payload).hexdigest()
            replacement = path.with_name('proof-' + str(journal['events'][-1]['sequence'] - 1) + '-' + digest + '.json')
            replacement.write_bytes(payload)
            replacement.chmod(0o600)
            changed_journal = deepcopy(journal)
            changed_journal['events'][-1]['details']['observed_proof_sha256'] = digest
            if field == 'attestation_sha256':
                changed_journal['events'][-1]['details']['attestation_sha256'] = value
            self.controller.journal_path.write_bytes(canonical(changed_journal))
            with self.subTest(field=field), self.assertRaisesRegex(ProofError, 'runtime proof does not revalidate'):
                load_expected_context(self.controller.journal_path, state_only=True)
            with self.subTest(field=field), self.assertRaisesRegex(ControllerError, 'prior_proof_invalid'):
                V3B2Controller(self.paths, self.runner)

    def test_maximum_private_before_snapshot_survives_hydration_reader_bound(self):
        from kil.v3b2_colima_inventory import MAX_RECORDS, MAX_NAME_BYTES, RESOURCE_LIMITS
        from kil.v3b2_controller import V3B2Controller
        self.runner.profiles = [profile(str(index).zfill(4) + 'x' * (MAX_NAME_BYTES - 4),
            cpus=RESOURCE_LIMITS['cpus'], memory=RESOURCE_LIMITS['memory'], disk=RESOURCE_LIMITS['disk'],
            arch='x86_64', runtime='containerd+k3s', address='ffff:ffff:ffff:ffff:ffff:ffff:255.255.255.255')
            for index in range(MAX_RECORDS)]
        for row in self.runner.profiles:
            (self.controller.profile_paths.lima / ('colima-' + row['name'])).mkdir(parents=True)
        self.controller.preflight()
        self.assertLess(self.controller.foreign_snapshot_path.stat().st_size, 1024 * 1024)
        with patch.object(self.runner, 'run', side_effect=AssertionError('hydration sampled live state')):
            self.assertEqual(V3B2Controller(self.paths, self.runner)._foreign_records_before, self.runner.profiles)


if __name__ == '__main__':
    unittest.main()
