from pathlib import Path
import tomllib
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DependencyContractTest(unittest.TestCase):
    def test_lab_extra_matches_the_exact_requirements_pin(self):
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
        requirement = (ROOT / "requirements-lab.txt").read_text().strip()
        optional_dependencies = metadata["project"].get("optional-dependencies", {})

        self.assertEqual(optional_dependencies.get("lab"), [requirement])

    def test_ci_installs_docs_requirements_before_validation(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        install = (
            "python -m pip install --disable-pip-version-check "
            "-r requirements-lab.txt -r requirements-docs.txt"
        )

        self.assertIn(install, workflow)
        self.assertLess(workflow.index(install), workflow.index("make validate"))

    def test_docs_extra_matches_the_exact_requirements_pins(self):
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
        requirements = (ROOT / "requirements-docs.txt").read_text().splitlines()
        optional = metadata["project"].get("optional-dependencies", {})

        self.assertEqual(requirements, ["markdown-it-py==4.2.0", "mdurl==0.1.2"])
        self.assertEqual(optional.get("docs"), requirements)

    def test_make_help_discloses_the_docs_dependency(self):
        result = subprocess.run(
            ["make", "help"], cwd=ROOT, check=True, text=True,
            stdout=subprocess.PIPE,
        )
        help_text = result.stdout.splitlines()

        self.assertNotIn("dependency-free unit suite", result.stdout)
        self.assertIn(
            "test      Run the complete unit suite (requires lab and docs dependencies)",
            help_text,
        )
        self.assertIn(
            "docs-html Generate self-contained HTML readers (requires docs dependencies)",
            help_text,
        )
        self.assertIn(
            "docs-html-check Check generated HTML readers (requires docs dependencies)",
            help_text,
        )

    def test_bootstrap_documents_both_extras(self):
        readme = (ROOT / "README.md").read_text()

        self.assertIn('python -m pip install -e ".[lab,docs]"', readme)


if __name__ == "__main__":
    unittest.main()
