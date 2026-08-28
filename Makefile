.PHONY: help install generate sdk sdk-archive test lint format clean ci update-conformance contrib version bump-revision

PYTHON     ?= python3
PIP        ?= pip
ANTLR_VER  := 4.13.2
BUILD_DIR  := .build
ANTLR_JAR  := $(BUILD_DIR)/antlr4.jar
ANTLR_URL  := https://www.antlr.org/download/antlr-$(ANTLR_VER)-complete.jar
ANTLR_SHA  := eae2dfa119a64327444672aff63e9ec35a20180dc5b8090b7a6ab85125df4d76
TAG        ?=
SDK_JOBS   ?= 0
export PATH := $(HOME)/.local/bin:$(PATH)

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

install: ## Install all dependencies (Python + linting tools)
	$(PIP) install -r scripts/requirements.txt
	$(PIP) install -r scripts/requirements-dev.txt || \
		(echo "Retrying dev dependencies..." && sleep 5 && $(PIP) install -r scripts/requirements-dev.txt)

$(ANTLR_JAR):
	@mkdir -p $(BUILD_DIR)
	curl -fsSL -o $(ANTLR_JAR) $(ANTLR_URL)
	echo "$(ANTLR_SHA)  $(ANTLR_JAR)" | sha256sum -c -

# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------

generate: ## Regenerate ANTLR4 grammar from OMG spec
	$(PYTHON) scripts/generate_grammar.py $(if $(TAG),--tag $(TAG)) --cache

sdk: $(ANTLR_JAR) ## Generate ANTLR4 SDKs (all targets, or set LANGUAGE=Cpp)
	$(PYTHON) scripts/generate_sdks.py --jobs $(SDK_JOBS) $(if $(LANGUAGE),--language $(LANGUAGE))

sdk-archive: $(ANTLR_JAR) ## Generate all ANTLR4 SDKs and package a release zip
	$(PYTHON) scripts/generate_sdks.py --archive --jobs $(SDK_JOBS)

# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

test: $(ANTLR_JAR) ## Validate grammar, parse examples, run conformance
	@echo "── Compiling grammar (Java target) ──"
	@mkdir -p $(BUILD_DIR)/antlr-out
	java -jar $(ANTLR_JAR) -Dlanguage=Java -o $(BUILD_DIR)/antlr-out \
		grammar/SysMLv2Lexer.g4 grammar/SysMLv2Parser.g4
	@echo "✅ Grammar compiles"
	@echo ""
	@echo "── Parsing example files ──"
	@mkdir -p $(BUILD_DIR)/antlr-test
	java -jar $(ANTLR_JAR) -Dlanguage=Java -o $(BUILD_DIR)/antlr-test \
		grammar/SysMLv2Lexer.g4 grammar/SysMLv2Parser.g4
	cd $(BUILD_DIR)/antlr-test/grammar && javac -cp "$(CURDIR)/$(ANTLR_JAR):." *.java
	@cd $(BUILD_DIR)/antlr-test/grammar && PASS=0; FAIL=0; \
	for f in $(CURDIR)/examples/*.sysml; do \
		printf "  Parsing $$(basename $$f)... "; \
		ERR=$$(java -cp "$(CURDIR)/$(ANTLR_JAR):." org.antlr.v4.gui.TestRig SysMLv2 rootNamespace "$$f" 2>&1 >/dev/null); \
		if [ -n "$$ERR" ]; then \
			echo "❌ FAIL"; echo "$$ERR" | head -1 | sed 's/^/	    /'; FAIL=$$((FAIL + 1)); \
		else \
			echo "✅ PASS"; PASS=$$((PASS + 1)); \
		fi; \
	done; \
	echo ""; echo "  Results: $$PASS passed, $$FAIL failed"; \
	[ $$FAIL -eq 0 ]
	@echo ""
	@if [ -d test/fixtures/conformance/training ]; then \
		echo "── Running conformance tests ──"; \
		$(PYTHON) scripts/conformance.py --verbose; \
	else \
		echo "── Conformance fixtures not found (run 'make update-conformance' to fetch) ──"; \
	fi

update-conformance: ## Fetch official OMG conformance fixtures + standard library
	$(PYTHON) scripts/conformance.py --fetch

# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------

lint: ## Lint, audit, and check grammar drift
	@echo "── Linting Python ──"
	ruff check scripts/
	ruff format --check scripts/
	@echo ""
	@echo "── Linting YAML ──"
	$(PYTHON) -m yamllint .github/workflows/*.yml
	@echo ""
	@echo "── Linting GitHub Actions ──"
	actionlint .github/workflows/*.yml
	@echo ""
	@echo "── Security audit ──"
	pip-audit -r scripts/requirements.txt
	@echo ""
	@echo "── Grammar drift check ──"
	@$(PYTHON) scripts/generate_grammar.py $(if $(TAG),--tag $(TAG)) --cache
	@if git diff --exit-code grammar/; then \
		echo "✅ Grammar files are up to date"; \
	else \
		echo "⚠️  Grammar files have drifted — run 'make generate' and commit"; \
		exit 1; \
	fi

format: ## Auto-format Python scripts
	ruff format scripts/
	ruff check --fix scripts/

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

clean: ## Remove generated/cached artifacts
	rm -rf $(BUILD_DIR)
	rm -rf .grammar-cache __pycache__ scripts/__pycache__
	rm -rf grammar/.antlr
	rm -rf contrib
	rm -rf test/fixtures sysml.library

contrib: ## Build and verify grammars-v4 contribution
	$(PYTHON) scripts/build_contrib.py --verify

version: ## Show current grammar version
	@jq -r '.grammar_version' scripts/config.json

bump-revision: ## Bump grammar revision (2026.01.0 → 2026.01.1)
	$(PYTHON) scripts/bump_version.py

# ---------------------------------------------------------------------------
# CI
# ---------------------------------------------------------------------------

ci: lint test contrib sdk-archive ## Full CI pipeline
