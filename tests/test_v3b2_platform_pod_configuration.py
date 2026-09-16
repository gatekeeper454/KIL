"""Static platform inventory acceptance; no runtime/readiness certification."""
import importlib.util
import json
import unittest
from copy import deepcopy
from dataclasses import fields, replace
from types import SimpleNamespace

from kil.v3b2_platform_pod_configuration import (
    PlatformPodConfigurationError, validate_platform_pod_configuration,
)
from kil.v3b2_runtime_ownership import validate_runtime_ownership
from tests.v3b2_platform_configuration_fixture import (
    NAMES, dependencies, encode, rebase_args, source_for,
)


def retained_ownership(name, component):
    """Explicit heterogeneous component paths; no inferred candidate authority."""
    if name == 'calico_node':
        return component.revision.ownership
    if name in ('coredns', 'local_path'):
        return component.parent.ownership
    if name == 'kube_proxy':
        return component.revision.parent.ownership
    return component.ownership


def derived_record(original):
    derived = type('Derived' + type(original).__name__, (type(original),), {})
    return derived(**{field.name: getattr(original, field.name)
                      for field in fields(original)})


class PlatformFixtureTest(unittest.TestCase):
    def test_all_components_accept_one_inventory_without_readiness(self):
        self.assertIsNotNone(
            importlib.util.find_spec('tests.v3b2_platform_configuration_fixture'),
            'shared independent platform fixture is missing',
        )
        from tests.v3b2_platform_configuration_fixture import fixture, dependencies, NAMES

        args, _, source = fixture()
        values = dependencies(args, source)
        self.assertEqual(sum(len(values[name].bindings) for name in NAMES), 10)
        self.assertEqual(len(values['coredns'].bindings), 2)
        for name in NAMES:
            with self.subTest(component=name):
                values[name].__post_init__()
                self.assertIs(values[name].runtime_contract_complete, False)


class PlatformCompositionTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            importlib.util.find_spec('kil.v3b2_platform_pod_configuration'),
            'typed platform configuration aggregate is missing',
        )
        from kil.v3b2_platform_pod_configuration import validate_platform_pod_configuration
        from tests.v3b2_platform_configuration_fixture import fixture, dependencies

        self.args, self.document, self.source = fixture()
        self.inputs = dependencies(self.args, self.source)
        self.proof = validate_platform_pod_configuration(**self.inputs)

    def assert_rejected_input(self, name, value):
        inputs = dict(self.inputs, **{name: value})
        with self.assertRaises(PlatformPodConfigurationError):
            validate_platform_pod_configuration(**inputs)
        with self.assertRaises(PlatformPodConfigurationError):
            replace(self.proof, **{name: value})

    def assert_valid_alternate_then_reject_mixes(self, args, source):
        alternate = dependencies(args, source)
        complete = validate_platform_pod_configuration(**alternate)
        self.assertEqual(len(complete.bindings), 10)
        self.assertEqual(replace(complete), complete)
        self.assertIs(complete.runtime_contract_complete, False)
        self.assertIs(complete.full_application_contract_complete, False)
        for name in self.inputs:
            with self.subTest(input=name):
                self.assert_rejected_input(name, alternate[name])

    def test_exact_public_export_surface(self):
        from kil import v3b2_platform_pod_configuration as module

        self.assertEqual(getattr(module, '__all__', None), (
            'PlatformPodConfigurationError',
            'PlatformPodConfigurationBinding',
            'PlatformPodConfigurationProof',
            'validate_platform_pod_configuration',
        ))

    def test_exact_ten_platform_incarnations_and_deterministic_order(self):
        bindings = self.proof.bindings
        self.assertIs(type(bindings), tuple)
        self.assertEqual(len(bindings), 10)
        self.assertEqual(bindings, tuple(sorted(bindings)))
        self.assertEqual(sum(b.component == 'coredns' for b in bindings), 2)
        self.assertEqual(len({(b.namespace, b.pod_name) for b in bindings}), 10)
        self.assertEqual(len({b.pod_uid for b in bindings}), 10)

    def test_retained_inputs_and_constructor_replay(self):
        for name, value in self.inputs.items():
            with self.subTest(input=name):
                self.assertIs(getattr(self.proof, name), value)
        self.assertEqual(replace(self.proof), self.proof)

    def test_completion_flags_are_singleton_false(self):
        self.assertIs(self.proof.runtime_contract_complete, False)
        self.assertIs(self.proof.full_application_contract_complete, False)

    def test_all_dependencies_reject_none_objects_lookalikes_and_subclasses(self):
        for name, original in self.inputs.items():
            lookalike = SimpleNamespace(**{field.name: getattr(original, field.name)
                                          for field in fields(original)})
            for value in (None, object(), lookalike, derived_record(original)):
                with self.subTest(input=name, candidate_type=type(value).__name__):
                    self.assert_rejected_input(name, value)

    def test_missing_keyword_is_python_type_error_not_explicit_none(self):
        for name in self.inputs:
            with self.subTest(input=name):
                missing = dict(self.inputs)
                del missing[name]
                with self.assertRaises(TypeError):
                    validate_platform_pod_configuration(**missing)
                self.assert_rejected_input(name, None)

    def test_constructor_rejects_binding_container_count_order_and_duplicates(self):
        bindings = self.proof.bindings
        for candidate in ((), list(bindings), bindings[:-1], bindings + bindings[:1],
                          tuple(reversed(bindings)), bindings[:-1] + bindings[:1]):
            with self.subTest(candidate=candidate):
                with self.assertRaises(PlatformPodConfigurationError):
                    replace(self.proof, bindings=candidate)

    def test_constructor_rejects_wrong_binding_types_and_subclasses(self):
        binding = self.proof.bindings[0]
        for candidate in (None, object(), derived_record(binding)):
            with self.subTest(candidate_type=type(candidate).__name__):
                with self.assertRaises(PlatformPodConfigurationError):
                    replace(self.proof, bindings=(candidate,) + self.proof.bindings[1:])

    def test_constructor_rejects_projected_identity_drift(self):
        binding = self.proof.bindings[0]
        for field, value in (('pod_name', 'alternate-platform-pod'),
                             ('pod_uid', 'forged-platform-uid'),
                             ('pod_resource_version', '99999')):
            with self.subTest(field=field):
                changed = replace(binding, **{field: value})
                with self.assertRaises(PlatformPodConfigurationError):
                    replace(self.proof, bindings=(changed,) + self.proof.bindings[1:])

    def test_binding_rejects_invalid_components_and_namespace_pairs(self):
        binding = self.proof.bindings[0]
        for component in ('application', '', None, 0):
            with self.subTest(component=component):
                with self.assertRaises(PlatformPodConfigurationError):
                    replace(binding, component=component)
        for original in self.proof.bindings:
            for namespace in ('default', '', None, 0,
                              'kube-system' if original.namespace != 'kube-system'
                              else 'local-path-storage'):
                with self.subTest(component=original.component, namespace=namespace):
                    with self.assertRaises(PlatformPodConfigurationError):
                        replace(original, namespace=namespace)

    def test_constructor_rejects_non_singleton_false_completion_flags(self):
        for flag in ('runtime_contract_complete', 'full_application_contract_complete'):
            for value in (True, 0, None, 'false'):
                with self.subTest(flag=flag, value=value):
                    with self.assertRaises(PlatformPodConfigurationError):
                        replace(self.proof, **{flag: value})

    def test_constructor_replays_forged_binding_component_and_namespace_validation(self):
        for field, value in (('component', 'application'), ('namespace', 'default')):
            with self.subTest(field=field):
                bindings = deepcopy(self.proof.bindings)
                object.__setattr__(bindings[0], field, value)
                with self.assertRaises(PlatformPodConfigurationError):
                    replace(self.proof, bindings=bindings)

    def test_all_components_reject_forged_nested_binding_uids(self):
        for name in NAMES:
            with self.subTest(component=name):
                component = deepcopy(self.inputs[name])
                binding = component.bindings[0]
                field = 'pod_uid' if name in ('calico_node', 'kube_proxy', 'scheduler',
                    'etcd', 'apiserver', 'controller_manager') else 'uid'
                object.__setattr__(binding, field, 'forged-platform-uid')
                self.assert_rejected_input(name, component)

    def test_all_components_reject_malformed_binding_containers_before_replay(self):
        for name in NAMES:
            original = self.inputs[name]
            for candidate in ((), list(original.bindings), original.bindings + original.bindings):
                with self.subTest(component=name, candidate_type=type(candidate).__name__):
                    component = deepcopy(original)
                    object.__setattr__(component, 'bindings', candidate)
                    self.assert_rejected_input(name, component)

    def test_independently_valid_whitespace_inventory_cannot_be_mixed(self):
        args = dict(self.args, runtime_objects=self.args['runtime_objects'] + b'\n')
        self.assert_valid_alternate_then_reject_mixes(args, self.source)

    def test_arbitrary_pod_status_is_uninterpreted_but_inventory_cannot_be_mixed(self):
        document = deepcopy(self.document)
        for row in document['items']:
            if row['kind'] == 'Pod':
                row['status'] = {'arbitrary': ['not-ready', False]}
        args = dict(self.args, runtime_objects=encode(document))
        self.assert_valid_alternate_then_reject_mixes(args, self.source)

    def test_independently_valid_complete_manifest_sources_cannot_be_mixed(self):
        alternate_source = source_for(self.args, sequence=6)
        self.assertNotEqual(alternate_source, self.source)
        alternate = dependencies(self.args, alternate_source)
        complete = validate_platform_pod_configuration(**alternate)
        self.assertEqual(replace(complete), complete)
        for name in ('apiserver', 'controller_manager'):
            with self.subTest(component=name):
                self.assert_rejected_input(name, alternate[name])

    def test_independently_valid_full_owned_identity_changes_cannot_be_mixed(self):
        owned = self.args['owned_identity']
        for field, value in (('docker_host', 'unix:///tmp/alternate/kil-v3-lab/docker.sock'),
                             ('kubeconfig', '/tmp/alternate/kubeconfig')):
            with self.subTest(field=field):
                args = rebase_args(self.args, self.document,
                                   owned_identity=replace(owned, **{field: value}))
                self.assert_valid_alternate_then_reject_mixes(args, source_for(args))

    def test_docker_endpoint_without_lab_suffix_rejects_at_earlier_identity_boundary(self):
        from kil.v3b2_journal import JournalError

        with self.assertRaises(JournalError):
            replace(self.args['owned_identity'], docker_host='unix:///tmp/alternate/docker.sock')

    def test_independently_valid_workload_run_change_cannot_be_mixed(self):
        args = rebase_args(self.args, self.document,
                          workload=replace(self.args['workload'], run_id='v3b2-' + 'd' * 64))
        self.assert_valid_alternate_then_reject_mixes(args, source_for(args))

    def test_profile_image_drift_rejects_at_earlier_schema_and_replay_boundaries(self):
        from kil.v3b2_contracts import SchemaError

        image = 'kindest/node:v1.36.1@sha256:' + 'e' * 64
        with self.assertRaises(SchemaError):
            replace(self.args['profile'], kind_node_image=image)
        component = deepcopy(self.inputs['calico_node'])
        object.__setattr__(component.revision.ownership.profile, 'kind_node_image', image)
        self.assert_rejected_input('calico_node', component)

    def test_calico_byte_variants_reject_at_earlier_content_lock_boundary(self):
        revision = self.inputs['calico_node'].revision
        for changes in ({'calico_source': revision.calico_source + b'\n# alternate\n'},
                        {'calico_projection': revision.calico_projection + b'\n'}):
            with self.subTest(changed=next(iter(changes))):
                with self.assertRaises(ValueError):
                    dependencies(self.args, self.source, **changes)

    def test_nested_calico_source_forgery_cannot_bypass_reconstruction(self):
        component = deepcopy(self.inputs['calico_node'])
        object.__setattr__(component.revision, 'calico_source', b'not Calico')
        self.assert_rejected_input('calico_node', component)

    def test_each_configuration_drift_is_owned_but_rejected_on_component_replay(self):
        for name in NAMES:
            with self.subTest(component=name):
                component = deepcopy(self.inputs[name])
                owned = retained_ownership(name, component)
                binding = component.bindings[0]
                pod_name = (binding.pod_name if name in ('calico_node', 'kube_proxy',
                    'scheduler', 'etcd', 'apiserver', 'controller_manager') else binding.name)
                document = json.loads(owned.runtime_objects)
                rows = [row for row in document['items'] if row['kind'] == 'Pod'
                        and row['metadata'].get('namespace') == binding.namespace
                        and row['metadata']['name'] == pod_name]
                self.assertEqual(len(rows), 1)
                rows[0]['spec']['containers'][0]['image'] = 'invalid.example/config-drift:v1'
                changed = encode(document)
                ownership = validate_runtime_ownership(**dict(self.args, runtime_objects=changed))
                self.assertEqual(ownership.deployment_ownership,
                                 self.inputs['ownership'].deployment_ownership)
                self.assertEqual(ownership.node_ownership,
                                 self.inputs['ownership'].node_ownership)
                object.__setattr__(owned, 'runtime_objects', changed)
                self.assert_rejected_input(name, component)

    def test_malformed_retained_inventory_is_local_error_with_cause(self):
        ownership = deepcopy(self.inputs['ownership'])
        object.__setattr__(ownership, 'runtime_objects', b'not JSON')
        with self.assertRaises(PlatformPodConfigurationError) as validator_error:
            validate_platform_pod_configuration(**dict(self.inputs, ownership=ownership))
        self.assertIsInstance(validator_error.exception.__cause__, ValueError)
        with self.assertRaises(PlatformPodConfigurationError) as constructor_error:
            replace(self.proof, ownership=ownership)
        self.assertIsInstance(constructor_error.exception.__cause__, ValueError)
