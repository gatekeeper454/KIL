.PHONY: help check-python test docs-html docs-html-check validate replay v3a-demo v3b-tools v3b-preflight v4-future-controller-test

PYTHON ?= python3

help:
	@echo "test      Run the complete unit suite (requires lab and docs dependencies)"
	@echo "v4-future-controller-test Run deferred V4 controller lifecycle tests"
	@echo "validate  Run all bootstrap checks"
	@echo "docs-html Generate self-contained HTML readers (requires docs dependencies)"
	@echo "docs-html-check Check generated HTML readers (requires docs dependencies)"
	@echo "replay    Emit a modeled historical bundle (requires OUTPUT and VERSION)"
	@echo "v3a-demo  Emit the modeled V3A process bundle (requires OUTPUT and VERSION)"
	@echo "v3b-tools Download and content-lock the isolated V3B toolchain"
	@echo "v3b-preflight Verify installed V3B tools against the local content lock"

check-python:
	$(PYTHON) -c "import sys; sys.version_info >= (3, 11) or sys.exit(f'KIL requires Python >= 3.11; found {sys.version.split()[0]}')"

test: check-python
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

v4-future-controller-test: check-python
	KIL_RUN_V4_FUTURE_TESTS=1 PYTHONPATH=src $(PYTHON) -m unittest tests.test_v3b2_controller.V3B2ControllerTest -v

docs-html: check-python
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src $(PYTHON) tools/render_markdown.py

docs-html-check: check-python
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src $(PYTHON) tools/render_markdown.py --check

validate: test docs-html-check
	$(PYTHON) -c "from pathlib import Path; assert '[project]' in Path('pyproject.toml').read_text()"
	git diff --check

replay: check-python
	@test -n "$(OUTPUT)" || (echo "OUTPUT is required" >&2; exit 2)
	@test -n "$(VERSION)" || (echo "VERSION is required" >&2; exit 2)
	PYTHONPATH=src $(PYTHON) tools/replay.py --output "$(OUTPUT)" --implementation-version "$(VERSION)"

v3a-demo: check-python
	@test -n "$(OUTPUT)" || (echo "OUTPUT is required" >&2; exit 2)
	@test -n "$(VERSION)" || (echo "VERSION is required" >&2; exit 2)
	PYTHONPATH=src $(PYTHON) tools/v3a_demo.py --output "$(OUTPUT)" --implementation-version "$(VERSION)"

v3b-tools: check-python
	PATH="$(CURDIR)/.tools/bin:$$PATH" PYTHONPATH=src $(PYTHON) tools/bootstrap_v3b_tools.py install

v3b-preflight: check-python
	PATH="$(CURDIR)/.tools/bin:$$PATH" PYTHONPATH=src $(PYTHON) tools/bootstrap_v3b_tools.py verify
