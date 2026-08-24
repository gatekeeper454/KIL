import importlib.util
import unittest


class PackageScaffoldTest(unittest.TestCase):
    def test_package_exposes_its_preimplementation_version(self):
        spec = importlib.util.find_spec("kil")
        self.assertIsNotNone(spec, "the kil package must be importable")
        self.assertIsNotNone(spec.loader, "the kil package must have an initializer")
        package = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(package)
        self.assertEqual(package.__version__, "0.0.0")


if __name__ == "__main__":
    unittest.main()
