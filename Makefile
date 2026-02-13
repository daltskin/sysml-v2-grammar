.PHONY: help install generate drift-check lint format validate test clean contrib version bump-revision ci

PYTHON     ?= python3
PIP        ?= pip
ANTLR_VER  := 4.13.2
BUILD_DIR  := .build
ANTLR_JAR  := $(BUILD_DIR)/antlr4.jar
ANTLR_URL  := https://www.antlr.org/download/antlr-$(ANTLR_VER)-complete.jar
ANTLR_SHA  := eae2dfa119a64327444672aff63e9ec35a20180dc5b8090b7a6ab85125df4d76
TAG        ?=

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

install: ## Install Python dependencies and dev tools
	$(PIP) install -r scripts/requirements.txt
	$(PIP) install ruff yamllint actionlint-py pip-audit

# ---------------------------------------------------------------------------
# Grammar
# ---------------------------------------------------------------------------

generate: ## Regenerate ANTLR4 grammar from OMG spec
	$(PYTHON) scripts/generate_grammar.py $(if $(TAG),--tag $(TAG)) --cache

drift-check: generate ## Check that committed grammar matches generator output
	@if git diff --exit-code grammar/; then \
		echo "✅ Grammar files are up to date"; \
	else \
		echo "⚠️  Grammar files have drifted — run 'make generate' and commit"; \
		exit 1; \
	fi

# ---------------------------------------------------------------------------
# Lint & format
# ---------------------------------------------------------------------------

lint: ## Run all linters
	ruff check scripts/
	ruff format --check scripts/
	yamllint .github/workflows/*.yml
	actionlint .github/workflows/*.yml

format: ## Auto-format Python scripts
	ruff format scripts/
	ruff check --fix scripts/

# ---------------------------------------------------------------------------
# Validate & test (requires Java 17+)
# ---------------------------------------------------------------------------

$(ANTLR_JAR):
	@mkdir -p $(BUILD_DIR)
	curl -fsSL -o $(ANTLR_JAR) $(ANTLR_URL)
	echo "$(ANTLR_SHA)  $(ANTLR_JAR)" | sha256sum -c -

validate: $(ANTLR_JAR) ## Compile grammar with ANTLR4 (Java + TypeScript)
	@mkdir -p $(BUILD_DIR)/antlr-out $(BUILD_DIR)/antlr-out-ts
	java -jar $(ANTLR_JAR) -Dlanguage=Java -o $(BUILD_DIR)/antlr-out \
		grammar/SysMLv2Lexer.g4 grammar/SysMLv2Parser.g4
	java -jar $(ANTLR_JAR) -Dlanguage=TypeScript -visitor -no-listener \
		-o $(BUILD_DIR)/antlr-out-ts grammar/SysMLv2Lexer.g4 grammar/SysMLv2Parser.g4
	@echo "✅ Grammar compiles successfully (Java + TypeScript)"

test: $(ANTLR_JAR) ## Parse example .sysml files through the grammar
	@mkdir -p $(BUILD_DIR)/antlr-test
	java -jar $(ANTLR_JAR) -Dlanguage=Java -o $(BUILD_DIR)/antlr-test \
		grammar/SysMLv2Lexer.g4 grammar/SysMLv2Parser.g4
	cd $(BUILD_DIR)/antlr-test/grammar && javac -cp "$(CURDIR)/$(ANTLR_JAR):." *.java
	@cd $(BUILD_DIR)/antlr-test/grammar && PASS=0; FAIL=0; \
	for f in $(CURDIR)/examples/*.sysml; do \
		printf "Parsing $$(basename $$f)... "; \
		if java -cp "$(CURDIR)/$(ANTLR_JAR):." org.antlr.v4.gui.TestRig SysMLv2Parser rootNamespace "$$f" 2>&1 | grep -qi "error"; then \
			echo "❌ FAIL"; FAIL=$$((FAIL + 1)); \
		else \
			echo "✅ PASS"; PASS=$$((PASS + 1)); \
		fi; \
	done; \
	echo ""; echo "Results: $$PASS passed, $$FAIL failed"; \
	[ $$FAIL -eq 0 ]

# ---------------------------------------------------------------------------
# Contribution (grammars-v4)
# ---------------------------------------------------------------------------

contrib: ## Build and verify grammars-v4 contribution
	$(PYTHON) scripts/build_contrib.py --verify

# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

version: ## Show current grammar version and OMG release tag
	@VERSION=$$(jq -r '.grammar_version' scripts/config.json); \
	TAG=$$(jq -r '.release_tag' scripts/config.json); \
	echo "Grammar version: $$VERSION (OMG release: $$TAG)"

bump-revision: ## Bump the grammar revision (e.g. 2026.01.0 → 2026.01.1)
	@$(PYTHON) scripts/bump_version.py

# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------

clean: ## Remove generated/cached artifacts
	rm -rf $(BUILD_DIR) .grammar-cache __pycache__ scripts/__pycache__ grammar/.antlr contrib

ci: lint drift-check validate test contrib ## Run full CI pipeline locally
