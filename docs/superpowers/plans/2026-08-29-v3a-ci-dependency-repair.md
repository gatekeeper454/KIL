# V3A CI Dependency Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make pull request 4 reproducibly install and declare the optional V3A laboratory cryptography dependency before running the complete test suite.

**Architecture:** Preserve the approved dependency boundary: the V1 deterministic kernel remains standard-library-only, while V3A exposes `cryptography==50.0.0` through a `lab` project extra and the existing exact requirements pin. GitHub Actions installs that pin before `make validate`; repository help and bootstrap documentation disclose the requirement.

**Tech Stack:** Python 3.11+, `tomllib`, `unittest`, GitHub Actions YAML, `cryptography==50.0.0`, setuptools project metadata.

---

### Task 1: Lock the dependency/bootstrap contract with regression tests

**Files:**

- Create: `tests/test_dependency_contract.py`

- [x] **Step 1: Write the failing contract tests**

Create tests that read the real repository artifacts and assert:

```python
def test_ci_installs_lab_requirements_before_validation(self):
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    install = "python -m pip install --disable-pip-version-check -r requirements-lab.txt"
    self.assertIn(install, workflow)
    self.assertLess(workflow.index(install), workflow.index("make validate"))

def test_lab_extra_matches_the_exact_requirements_pin(self):
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
    requirement = (ROOT / "requirements-lab.txt").read_text().strip()
    self.assertEqual(metadata["project"]["optional-dependencies"]["lab"], [requirement])

def test_test_help_discloses_the_lab_dependency(self):
    makefile = (ROOT / "Makefile").read_text()
    self.assertIn("requires lab dependencies", makefile)
    self.assertNotIn("dependency-free unit suite", makefile)

def test_bootstrap_documents_the_lab_extra(self):
    readme = (ROOT / "README.md").read_text()
    self.assertIn('python -m pip install -e ".[lab]"', readme)
```

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_dependency_contract -v
```

Expected: four failures because CI does not install the requirements, the `lab`
project extra is absent, the Makefile still claims the suite is dependency-free,
and the bootstrap instructions omit the lab-extra installation command.

### Task 2: Implement the minimal coherent dependency repair

**Files:**

- Modify: `.github/workflows/ci.yml`
- Modify: `pyproject.toml`
- Modify: `Makefile`
- Modify: `README.md`

- [x] **Step 1: Install the exact lab pin in CI**

Insert this step after `actions/setup-python` and before `make validate`:

```yaml
      - run: python -m pip install --disable-pip-version-check -r requirements-lab.txt
```

- [x] **Step 2: Publish the optional lab dependency contract**

Add to `pyproject.toml`:

```toml
[project.optional-dependencies]
lab = ["cryptography==50.0.0"]
```

- [x] **Step 3: Correct command help and bootstrap documentation**

Change the Makefile help line to:

```make
	@echo "test      Run the complete unit suite (requires lab dependencies)"
```

Document `python -m pip install -e ".[lab]"` before `make test` in the README
bootstrap section while preserving the statement that bootstrap does not
install or download cluster dependencies.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_dependency_contract -v
```

Expected: all three tests pass.

- [x] **Step 5: Run the complete local validation**

Run:

```bash
make validate
```

Expected: all tests pass, project metadata check passes, and `git diff --check`
reports no errors.

### Task 3: Record and publish the correction

**Files:**

- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Modify: this implementation plan to mark executed steps complete

- [x] **Step 1: Append the implementation result to the specialist lineage**

Record the confirmed repair, exact verification evidence, affected artifacts,
remaining GitHub check state, and the next gate without changing V3A's modeled
evidence classification.

- [x] **Step 2: Review the patch and commit it**

Run:

```bash
git diff --check
git diff --stat
git status --short
git add .github/workflows/ci.yml Makefile README.md pyproject.toml tests/test_dependency_contract.py docs/superpowers/plans/2026-08-29-v3a-ci-dependency-repair.md docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md
git commit -m "Fix V3A CI dependency bootstrap"
```

- [x] **Step 3: Push and inspect pull request 4 checks**

Run:

```bash
git push origin feature/v3a-signed-state-authz
```

Expected: pull request 4 starts fresh `push` and `pull_request` CI jobs for the
new head commit.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
