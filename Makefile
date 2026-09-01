.PHONY: help check-python test validate replay v3a-demo v3b-tools v3b-preflight kil-showcase

PYTHON ?= python3
SHOWCASE_PORT ?= 8767

help:
	@echo "test      Run the complete unit suite (requires lab dependencies)"
	@echo "validate  Run all bootstrap checks"
	@echo "replay    Emit a modeled historical bundle (requires OUTPUT and VERSION)"
	@echo "v3a-demo  Emit the modeled V3A process bundle (requires OUTPUT and VERSION)"
	@echo "v3b-tools Download and content-lock the isolated V3B toolchain"
	@echo "v3b-preflight Verify installed V3B tools against the local content lock"
	@echo "kil-showcase Serve the synchronized Presenter/Audience showcase locally"

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

v3b-tools: check-python
	PATH="$(CURDIR)/.tools/bin:$$PATH" PYTHONPATH=src $(PYTHON) tools/bootstrap_v3b_tools.py install

v3b-preflight: check-python
	PATH="$(CURDIR)/.tools/bin:$$PATH" PYTHONPATH=src $(PYTHON) tools/bootstrap_v3b_tools.py verify

kil-showcase:
	@echo "Presenter: http://127.0.0.1:$(SHOWCASE_PORT)/kil-presenter-audience-demo.html?mode=presenter&session=showcase"
	@echo "Use Open audience view in the presenter, or open the same URL with mode=audience."
	$(PYTHON) -m http.server $(SHOWCASE_PORT) --bind 127.0.0.1 --directory docs/demo
