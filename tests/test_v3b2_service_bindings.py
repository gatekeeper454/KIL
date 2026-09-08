"""Independent API fixtures for the nine allocated KIL Services."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest

from kil import v3b2_proofs as proofs
from kil.v3b2_api_defaults import matches_configuration
from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_manifests import WorkloadIdentity, render_objects
from kil.v3b2_service_bindings import validate_service_allocations


ROOT = Path(__file__).resolve().parents[1]


def fixture():
    profile = V3B2Profile.load(ROOT / 'deploy/kind/v3b2-profile.json')
    workload = WorkloadIdentity('v3b2-' + '1' * 64, 'sha256:' + '2' * 64,
                                'docker.io/envoyproxy/envoy@sha256:' + '3' * 64)
    desired = [row for row in json.loads(render_objects(profile, workload))['items'] if row['kind'] == 'Service']
    observed = deepcopy(desired)
    # Literal API additions are independent of the validator's normalization.
    addresses = ['10.96.0.11', '10.96.0.12', '10.96.0.13', '10.96.1.1', '10.96.1.2',
                 '10.96.1.3', '10.96.255.252', '10.96.255.253', '10.96.255.254']
    for index, (row, address) in enumerate(zip(observed, addresses)):
        row['metadata'].update(uid=f'service-uid-{index}', resourceVersion=str(index + 1),
                               creationTimestamp='2026-09-07T00:00:00Z')
        row['spec'].update(clusterIP=address, clusterIPs=[address], ipFamilyPolicy='SingleStack',
                           ipFamilies=['IPv4'], sessionAffinity='None', internalTrafficPolicy='Cluster')
    return profile, workload, desired, observed


class ServiceBindingsTest(unittest.TestCase):
    def setUp(self):
        self.profile, self.workload, self.desired, self.observed = fixture()

    def validate(self, observed=None, **kwargs):
        return validate_service_allocations(self.observed if observed is None else observed,
                                            profile=self.profile, workload=self.workload, **kwargs)

    def test_accepts_nine_distinct_allocations_with_canonical_immutable_output(self):
        before = deepcopy(self.observed)
        result = self.validate(list(reversed(self.observed)))
        bindings = json.loads(result.bindings)
        self.assertEqual(len(bindings), 9)
        self.assertEqual(bindings, sorted(bindings, key=lambda row: (row['namespace'], row['name'])))
        expected = sorted([{'namespace': row['metadata']['namespace'], 'name': row['metadata']['name'],
                            'uid': row['metadata']['uid'], 'cluster_ip': row['spec']['clusterIP']}
                           for row in before], key=lambda row: (row['namespace'], row['name']))
        self.assertEqual(bindings, expected)
        self.assertEqual(result.bindings, proofs.canonical(expected))
        sanitized = json.loads(result.configurations)
        expected_configurations = deepcopy(before)
        for row in expected_configurations:
            for field in ('clusterIP', 'clusterIPs', 'ipFamilies', 'ipFamilyPolicy'):
                del row['spec'][field]
            self.assertEqual(row['spec']['sessionAffinity'], 'None')
            self.assertEqual(row['spec']['internalTrafficPolicy'], 'Cluster')
        expected_configurations.sort(key=lambda row: (row['apiVersion'], row['kind'],
                                                       row['metadata']['namespace'], row['metadata']['name']))
        self.assertEqual(sanitized, expected_configurations)
        self.assertEqual(self.observed, before)
        self.assertIs(type(result.configurations), bytes)
        with self.assertRaises(FrozenInstanceError):
            result.bindings = b'[]\n'

    def test_rejects_missing_allocation_fields(self):
        for field in ('clusterIP', 'clusterIPs', 'ipFamilyPolicy', 'ipFamilies'):
            with self.subTest(field=field):
                changed = deepcopy(self.observed)
                del changed[0]['spec'][field]
                with self.assertRaises(ValueError):
                    self.validate(changed)

    def test_rejects_invalid_address_forms_and_reserved_addresses(self):
        for address in (None, True, 1, '', 'None', '10.096.0.11', '10.96.0.11 ', '::1',
                        '10.95.0.11', '10.97.0.1', '10.96.0.0', '10.96.255.255', '10.96.0.1', '10.96.0.10'):
            with self.subTest(address=address):
                changed = deepcopy(self.observed)
                changed[0]['spec'].update(clusterIP=address, clusterIPs=[address])
                with self.assertRaises(ValueError):
                    self.validate(changed)

    def test_rejects_nonexact_family_and_allocation_types(self):
        for field, values in {
            'clusterIPs': (None, True, '10.96.0.11', [], ['10.96.0.12'], ['10.96.0.11', '10.96.0.12'], [True]),
            'ipFamilies': (None, True, 'IPv4', [], ['IPv6'], ['IPv4', 'IPv6'], [True]),
            'ipFamilyPolicy': (None, True, ['SingleStack'], 'PreferDualStack', 'RequireDualStack'),
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    changed = deepcopy(self.observed)
                    changed[0]['spec'][field] = value
                    with self.assertRaises(ValueError):
                        self.validate(changed)

    def test_rejects_configuration_owner_and_deletion_drift(self):
        changes = [
            ('spec', 'externalName', 'foreign.example'), ('spec', 'externalIPs', []),
            ('spec', 'type', 'NodePort'), ('spec', 'type', 'LoadBalancer'),
            ('spec', 'sessionAffinity', 'ClientIP'), ('spec', 'internalTrafficPolicy', 'Local'),
            ('spec', 'allocateLoadBalancerNodePorts', False), ('spec', 'unknown', {}),
            ('spec', 'selector', {}), ('metadata', 'labels', {}),
            ('metadata', 'ownerReferences', []), ('metadata', 'deletionTimestamp', None),
            ('metadata', 'deletionGracePeriodSeconds', 0),
        ]
        for parent, key, value in changes:
            with self.subTest(parent=parent, key=key, value=value):
                changed = deepcopy(self.observed)
                changed[0][parent][key] = value
                with self.assertRaises(ValueError):
                    self.validate(changed)
        for field, value in (('port', 9999), ('port', True), ('targetPort', '8080'), ('protocol', 'UDP'), ('nodePort', 30000)):
            with self.subTest(port_field=field):
                changed = deepcopy(self.observed)
                changed[0]['spec']['ports'][0][field] = value
                with self.assertRaises(ValueError):
                    self.validate(changed)
        changed = deepcopy(self.observed)
        changed[0]['spec']['ports'].append(deepcopy(changed[0]['spec']['ports'][0]))
        with self.assertRaises(ValueError):
            self.validate(changed)

    def test_rejects_invalid_or_missing_incarnation_metadata(self):
        for field, values in {'uid': (None, True, 1, '', ' uid', 'a' * 129),
                              'resourceVersion': (None, True, 1, '', '0', '01', '-1', str(2**64))}.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    changed = deepcopy(self.observed)
                    changed[0]['metadata'][field] = value
                    with self.assertRaises(ValueError):
                        self.validate(changed)
            changed = deepcopy(self.observed)
            del changed[0]['metadata'][field]
            with self.assertRaises(ValueError):
                self.validate(changed)

    def test_rejects_missing_extra_duplicate_and_wrong_service_identities(self):
        for changed in (self.observed[:-1], self.observed + [deepcopy(self.observed[0])], []):
            with self.assertRaises(ValueError):
                self.validate(changed)
        for parent, field, value in ((None, 'apiVersion', 'v2'), (None, 'kind', 'ConfigMap'),
                                      ('metadata', 'name', 'foreign'), ('metadata', 'namespace', 'default')):
            changed = deepcopy(self.observed)
            (changed[0] if parent is None else changed[0][parent])[field] = value
            with self.assertRaises(ValueError):
                self.validate(changed)

    def test_rejects_shared_addresses_or_uids(self):
        for duplicate in ('address', 'uid'):
            changed = deepcopy(self.observed)
            if duplicate == 'address':
                address = changed[1]['spec']['clusterIP']
                changed[0]['spec'].update(clusterIP=address, clusterIPs=[address])
            else:
                changed[0]['metadata']['uid'] = changed[1]['metadata']['uid']
            with self.assertRaises(ValueError):
                self.validate(changed)

    def test_rejects_malformed_identity_values_with_validation_errors(self):
        for field in ('name', 'namespace'):
            for value in ([], {}, None, True, 1):
                with self.subTest(field=field, value=value):
                    changed = deepcopy(self.observed)
                    changed[0]['metadata'][field] = value
                    with self.assertRaises((ValueError, TypeError)) as rejection:
                        self.validate(changed)
                    self.assertIsInstance(rejection.exception, ValueError)
        for value in (None, {}, True, tuple(self.observed)):
            with self.subTest(observed=value), self.assertRaises(ValueError):
                validate_service_allocations(value, profile=self.profile, workload=self.workload)

    def test_prior_bindings_preserve_uid_and_address_but_allow_resource_version_progress(self):
        prior = json.loads(self.validate().bindings)
        changed = deepcopy(self.observed)
        for row in changed:
            row['metadata']['resourceVersion'] = '1000'
        self.assertEqual(json.loads(self.validate(changed, prior_bindings=prior).bindings), prior)
        for field in ('uid', 'address'):
            replaced = deepcopy(changed)
            if field == 'uid':
                replaced[0]['metadata']['uid'] = 'replacement-uid'
            else:
                replaced[0]['spec'].update(clusterIP='10.96.2.1', clusterIPs=['10.96.2.1'])
            with self.assertRaises(ValueError):
                self.validate(replaced, prior_bindings=prior)

    def test_prior_bindings_are_closed_canonical_full_and_validated(self):
        prior = json.loads(self.validate().bindings)
        bad = [{}, True, [], prior[:-1], prior + [prior[0]], list(reversed(prior))]
        for field, value in (('uid', True), ('uid', ''), ('cluster_ip', True), ('cluster_ip', '10.96.0.10'),
                             ('cluster_ip', prior[1]['cluster_ip']), ('uid', prior[1]['uid']),
                             ('namespace', 'default'), ('name', 'foreign'), ('extra', 'value')):
            changed = deepcopy(prior)
            changed[0][field] = value
            bad.append(changed)
        changed = deepcopy(prior)
        del changed[0]['uid']
        bad.append(changed)
        for value in bad:
            with self.subTest(prior=value):
                with self.assertRaises(ValueError):
                    self.validate(prior_bindings=value)

    def test_requires_independently_validated_fixed_profile_and_workload(self):
        valid_profile, valid_workload = self.profile, self.workload
        for field, value in (('profile', {}), ('workload', {})):
            setattr(self, field, value)
            with self.assertRaises(ValueError):
                self.validate()
            self.profile, self.workload = valid_profile, valid_workload
        object.__setattr__(self.profile, 'service_subnet', '10.97.0.0/16')
        with self.assertRaises(ValueError):
            self.validate()

    def test_static_comparator_still_rejects_allocations_without_context(self):
        self.assertFalse(matches_configuration(self.desired[0], self.observed[0]))
        with self.assertRaises(proofs.ProofError):
            proofs.validate_applied_objects(self.desired, proofs.canonical({'kind': 'List', 'items': self.observed}))


if __name__ == '__main__':
    unittest.main()
