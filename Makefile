.PHONY: help install generate generate-sysml generate-kerml sdk sdk-archive test test-examples lint format clean ci update-conformance contrib version bump-revision

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

generate: generate-sysml generate-kerml ## Regenerate the SysML and KerML grammars from the OMG spec

generate-sysml: ## Regenerate the SysML ANTLR4 grammar
	$(PYTHON) scripts/generate_grammar.py --language sysml $(if $(TAG),--tag $(TAG)) --cache

generate-kerml: ## Regenerate the KerML ANTLR4 grammar
	$(PYTHON) scripts/generate_grammar.py --language kerml $(if $(TAG),--tag $(TAG)) --cache

sdk: $(ANTLR_JAR) ## Generate ANTLR4 SDKs (all targets, or set LANGUAGE=Cpp; both grammars, or GRAMMAR=kerml)
	$(PYTHON) scripts/generate_sdks.py --jobs $(SDK_JOBS) $(if $(LANGUAGE),--language $(LANGUAGE)) $(if $(GRAMMAR),--grammar $(GRAMMAR))

sdk-archive: $(ANTLR_JAR) ## Generate all ANTLR4 SDKs and package a release zip
	$(PYTHON) scripts/generate_sdks.py --archive --jobs $(SDK_JOBS)

# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

test: $(ANTLR_JAR) ## Validate grammar, parse examples, run conformance
	bash scripts/UpstreamReleaseTest.sh
	$(PYTHON) scripts/ConformanceFetchTest.py
	$(PYTHON) scripts/ConformanceRunnerTest.py
	$(PYTHON) scripts/ExampleRunnerTest.py
	$(PYTHON) scripts/PatchTest.py
	$(PYTHON) scripts/SdkGenerationTest.py
	@echo "── Compiling grammar (Java target) ──"
	@mkdir -p $(BUILD_DIR)/antlr-out
	java -jar $(ANTLR_JAR) -Dlanguage=Java -o $(BUILD_DIR)/antlr-out \
		grammar/SysMLv2Lexer.g4 grammar/SysMLv2Parser.g4
	@echo "✅ Grammar compiles"
	@echo ""
	@echo "── Running focused expression regressions (Python target) ──"
	@mkdir -p $(BUILD_DIR)/antlr-python
	java -jar $(ANTLR_JAR) -Dlanguage=Python3 -o $(BUILD_DIR)/antlr-python \
		grammar/SysMLv2Lexer.g4 grammar/SysMLv2Parser.g4
	PYTHONPATH="$(CURDIR)/$(BUILD_DIR)/antlr-python" $(PYTHON) scripts/ExpressionGrammarTest.py
	@echo ""
	@echo "── Running import visibility regressions (Python target) ──"
	PYTHONPATH="$(CURDIR)/$(BUILD_DIR)/antlr-python" $(PYTHON) scripts/ImportVisibilityTest.py
	@echo ""
	@echo "── Running end-occurrence regressions (Python target) ──"
	PYTHONPATH="$(CURDIR)/$(BUILD_DIR)/antlr-python" $(PYTHON) scripts/EndOccurrenceGrammarTest.py
	@echo ""
	@echo "── Compiling KerML grammar (Java target) ──"
	@mkdir -p $(BUILD_DIR)/antlr-out-kerml/grammar
	java -jar $(ANTLR_JAR) -Dlanguage=Java -o $(BUILD_DIR)/antlr-out-kerml \
		-lib $(BUILD_DIR)/antlr-out-kerml/grammar grammar/KerMLLexer.g4 grammar/KerMLParser.g4
	@echo "✅ KerML grammar compiles"
	@echo ""
	@echo "── Running KerML grammar regressions (Python target) ──"
	@mkdir -p $(BUILD_DIR)/antlr-python-kerml/grammar
	java -jar $(ANTLR_JAR) -Dlanguage=Python3 -o $(BUILD_DIR)/antlr-python-kerml \
		-lib $(BUILD_DIR)/antlr-python-kerml/grammar grammar/KerMLLexer.g4 grammar/KerMLParser.g4
	PYTHONPATH="$(CURDIR)/$(BUILD_DIR)/antlr-python-kerml" $(PYTHON) scripts/KerMLGrammarTest.py
	@echo ""
	@echo "── Running lexical structure regressions, both grammars (Python target) ──"
	SYSML_PYTHON_DIR="$(CURDIR)/$(BUILD_DIR)/antlr-python/grammar" \
		KERML_PYTHON_DIR="$(CURDIR)/$(BUILD_DIR)/antlr-python-kerml/grammar" \
		$(PYTHON) scripts/LexicalStructureTest.py
	@echo ""
	@echo "── Parsing example files (Java target) ──"
	@mkdir -p $(BUILD_DIR)/antlr-test
	java -jar $(ANTLR_JAR) -Dlanguage=Java -o $(BUILD_DIR)/antlr-test \
		grammar/SysMLv2Lexer.g4 grammar/SysMLv2Parser.g4
	cd $(BUILD_DIR)/antlr-test/grammar && javac -cp "$(CURDIR)/$(ANTLR_JAR):." *.java
	$(MAKE) test-examples
	@echo ""
	@if [ -d test/fixtures/conformance/training ] && [ -d test/fixtures/kerml-conformance/examples ]; then \
		echo "── Running conformance tests ──"; \
		$(PYTHON) scripts/conformance.py --verbose; \
	elif [ -d test/fixtures/conformance/training ] || [ -d test/fixtures/kerml-conformance/examples ]; then \
		echo "❌ Only one language's conformance fixtures found (run 'make update-conformance' to fetch both)"; \
		exit 1; \
	else \
		echo "── Conformance fixtures not found (run 'make update-conformance' to fetch) ──"; \
	fi

test-examples:
	@cd $(BUILD_DIR)/antlr-test/grammar && PASS=0; FAIL=0; \
	for f in $(CURDIR)/examples/*.sysml; do \
		printf "  Parsing $$(basename $$f)... "; \
		ERR=$$(java -cp "$(CURDIR)/$(ANTLR_JAR):." org.antlr.v4.gui.TestRig SysMLv2 rootNamespace "$$f" 2>&1 >/dev/null); \
		EXIT_CODE=$$?; \
		if [ $$EXIT_CODE -ne 0 ] || [ -n "$$ERR" ]; then \
			echo "❌ FAIL"; echo "$$ERR" | head -1 | sed 's/^/	    /'; FAIL=$$((FAIL + 1)); \
		else \
			echo "✅ PASS"; PASS=$$((PASS + 1)); \
		fi; \
	done; \
	echo ""; echo "  Results: $$PASS passed, $$FAIL failed"; \
	[ $$FAIL -eq 0 ]

update-conformance: ## Fetch the SysML and KerML fixtures + standard library from the configured OMG releases
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
