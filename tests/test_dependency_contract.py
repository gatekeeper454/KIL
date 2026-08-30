from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DependencyContractTest(unittest.TestCase):
    def test_ci_installs_lab_requirements_before_validation(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        install = (
            "python -m pip install --disable-pip-version-check "
            "-r requirements-lab.txt"
        )

        self.assertIn(install, workflow)
        self.assertLess(workflow.index(install), workflow.index("make validate"))

    def test_lab_extra_matches_the_exact_requirements_pin(self):
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
        requirement = (ROOT / "requirements-lab.txt").read_text().strip()

        optional_dependencies = metadata["project"].get("optional-dependencies", {})

        self.assertEqual(optional_dependencies.get("lab"), [requirement])

    def test_test_help_discloses_the_lab_dependency(self):
        makefile = (ROOT / "Makefile").read_text()

        self.assertIn("requires lab dependencies", makefile)
        self.assertNotIn("dependency-free unit suite", makefile)

    def test_bootstrap_documents_the_lab_extra(self):
        readme = (ROOT / "README.md").read_text()

        self.assertIn('python -m pip install -e ".[lab]"', readme)


if __name__ == "__main__":
    unittest.main()
