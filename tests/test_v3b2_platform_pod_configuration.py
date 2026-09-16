"""Static platform inventory acceptance; no runtime/readiness certification."""
import importlib.util
import unittest


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
