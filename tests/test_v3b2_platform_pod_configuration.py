"""Static platform inventory acceptance; no runtime/readiness certification."""
import importlib.util
import unittest
from dataclasses import replace


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

        args, _, source = fixture()
        self.inputs = dependencies(args, source)
        self.proof = validate_platform_pod_configuration(**self.inputs)

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
