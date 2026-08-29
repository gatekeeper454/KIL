.PHONY: help check-python test validate

PYTHON ?= python3

help:
	@echo "test      Run the dependency-free unit suite"
	@echo "validate  Run all bootstrap checks"

check-python:
	$(PYTHON) -c "import sys; sys.version_info >= (3, 11) or sys.exit(f'KIL requires Python >= 3.11; found {sys.version.split()[0]}')"

test: check-python
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

validate: test
	$(PYTHON) -c "from pathlib import Path; assert '[project]' in Path('pyproject.toml').read_text()"
	git diff --check
