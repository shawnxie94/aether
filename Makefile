# Aether project tasks.
#
# Most of the targets mirror the shell snippets that AGENT.md documents, so
# "make doctor" is the same as
#   PYTHONPATH=src python -m aether_core.cli doctor
# without anyone having to remember the prefix every time.

PY ?= python3
NODE ?= node
SRC := plugins/aether/src
TESTS := plugins/aether/tests
SCHEMAS := plugins/aether/schemas
SCRIPTS := plugins/aether/scripts

.PHONY: help test doctor validate schemas pack install-local \
        install-global verify clean cache-sync

help:
	@printf "Aether project tasks\n\n"
	@printf "  make test          Run the unittest suite\n"
	@printf "  make doctor        Run the aether CLI doctor\n"
	@printf "  make schemas       Validate every JSON schema in schemas/\n"
	@printf "  make validate      Run the aether payload validator (smoke)\n"
	@printf "  make pack          npm pack --dry-run the marketplace package\n"
	@printf "  make install-local Install the plugin into the local Codex cache\n"
	@printf "  make install-global Reinstall the global Codex marketplace entry\n"
	@printf "  make verify        Run scripts/verify_aether_layout.sh\n"
	@printf "  make cache-sync    Sync source changes into the Codex plugin cache\n"
	@printf "  make clean         Remove __pycache__ and .pyc files\n"

test:
	PYTHONPATH=$(SRC) $(PY) -m unittest discover -s $(TESTS)

doctor:
	PYTHONPATH=$(SRC) $(PY) -m aether_core.cli doctor

validate:
	PYTHONPATH=$(SRC) $(PY) -m aether_core.cli validate visual-asset \
	    --json plugins/aether/examples/visual-asset.json

schemas:
	@for schema in $(SCHEMAS)/*.json; do \
	        $(PY) -m json.tool "$$schema" >/dev/null || exit 1; \
	    done
	@echo "schemas ok"

pack:
	$(NODE) scripts/aether-plugin.js doctor
	npm pack --dry-run

install-local:
	bash $(SCRIPTS)/install-local.sh

install-global:
	$(NODE) scripts/aether-plugin.js install

verify:
	bash scripts/verify_aether_layout.sh

# Sync source changes into the live Codex plugin cache. The cache lives at
# ~/.codex/plugins/cache/aether/aether/<version>/ and is not auto-updated by
# editing source files, per AGENT.md.
CACHE_DIR := $(HOME)/.codex/plugins/cache/aether/aether/$(shell $(PY) -c "import json; print(json.load(open('plugins/aether/.codex-plugin/plugin.json'))['version'])")

cache-sync:
	@test -d "$(CACHE_DIR)" || { \
	    echo "Cache dir not found: $(CACHE_DIR)" >&2; \
	    echo "Run 'make install-local' first." >&2; \
	    exit 1; \
	}
	cp plugins/aether/src/aether_core/__init__.py \
	   plugins/aether/src/aether_core/composer.py \
	   plugins/aether/src/aether_core/embeddings.py \
	   plugins/aether/src/aether_core/migrations.py \
	   plugins/aether/src/aether_core/panel_data.py \
	   plugins/aether/src/aether_core/panel_export.py \
	   plugins/aether/src/aether_core/panel_server.py \
	   plugins/aether/src/aether_core/panel_template.py \
	   plugins/aether/src/aether_core/storage.py \
	   $(CACHE_DIR)/src/aether_core/
	rm -rf $(CACHE_DIR)/src/aether_core/panel
	cp -R plugins/aether/src/aether_core/panel \
	    $(CACHE_DIR)/src/aether_core/panel
	rm -rf $(CACHE_DIR)/src/aether_core/__pycache__
	@echo "synced to $(CACHE_DIR)"

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
