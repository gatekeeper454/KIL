.PHONY: help check-python test validate replay v3a-demo

PYTHON ?= python3

help:
	@echo "test      Run the complete unit suite (requires lab dependencies)"
	@echo "validate  Run all bootstrap checks"
	@echo "replay    Emit a modeled historical bundle (requires OUTPUT and VERSION)"
	@echo "v3a-demo  Emit the modeled V3A process bundle (requires OUTPUT and VERSION)"

check-python:
	$(PYTHON) -c "import sys; sys.version_info >= (3, 11) or sys.exit(f'KIL requires Python >= 3.11; found {sys.version.split()[0]}')"

test: check-python
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

validate: test
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
