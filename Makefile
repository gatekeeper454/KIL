.PHONY: help test validate

help:
	@echo "test      Run the dependency-free unit suite"
	@echo "validate  Run all bootstrap checks"

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

validate: test
	python3 -c "from pathlib import Path; assert '[project]' in Path('pyproject.toml').read_text()"
	git diff --check
