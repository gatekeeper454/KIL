.PHONY: help test validate

PYTHON ?= python3

help:
	@echo "test      Run the dependency-free unit suite"
	@echo "validate  Run all bootstrap checks"

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

validate: test
	$(PYTHON) -c "from pathlib import Path; assert '[project]' in Path('pyproject.toml').read_text()"
	git diff --check
