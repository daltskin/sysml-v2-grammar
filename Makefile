.PHONY: help install install-dev generate lint lint-python lint-yaml lint-actions audit validate parse-examples clean download-antlr

PYTHON     ?= python3
PIP        ?= pip
ANTLR_VER  := 4.13.2
ANTLR_JAR  := /tmp/antlr4.jar
ANTLR_URL  := https://www.antlr.org/download/antlr-$(ANTLR_VER)-complete.jar
ANTLR_SHA  := eae2dfa119a64327444672aff63e9ec35a20180dc5b8090b7a6ab85125df4d76
TAG        ?=

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

install: ## Install runtime Python dependencies
	$(PIP) install -r scripts/requirements.txt

install-dev: install ## Install runtime + linting dependencies
	$(PIP) install ruff yamllint actionlint-py pip-audit

# ---------------------------------------------------------------------------
# Grammar generation
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
# Linting
# ---------------------------------------------------------------------------

lint: lint-python lint-yaml lint-actions ## Run all linters

lint-python: ## Lint Python scripts with ruff
	ruff check scripts/
	ruff format --check scripts/

lint-yaml: ## Lint YAML files with yamllint
	yamllint .github/workflows/*.yml

lint-actions: ## Lint GitHub Actions workflows with actionlint
	actionlint .github/workflows/*.yml

format: ## Auto-format Python scripts
	ruff format scripts/
	ruff check --fix scripts/

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

audit: ## Scan Python dependencies for known vulnerabilities
	pip-audit -r scripts/requirements.txt

# ---------------------------------------------------------------------------
# Validation (requires Java 17+)
# ---------------------------------------------------------------------------

$(ANTLR_JAR):
	curl -fsSL -o $(ANTLR_JAR) $(ANTLR_URL)
	echo "$(ANTLR_SHA)  $(ANTLR_JAR)" | sha256sum -c -

download-antlr: $(ANTLR_JAR) ## Download and verify the ANTLR4 JAR

validate: $(ANTLR_JAR) ## Compile grammar with ANTLR4 (Java target)
	@mkdir -p /tmp/antlr-out
	java -jar $(ANTLR_JAR) -Dlanguage=Java -o /tmp/antlr-out \
		grammar/SysMLv2Lexer.g4 grammar/SysMLv2.g4
	@echo "✅ Grammar compiles successfully"

validate-ts: $(ANTLR_JAR) ## Compile grammar with ANTLR4 (TypeScript target)
	@mkdir -p /tmp/antlr-out-ts
	java -jar $(ANTLR_JAR) -Dlanguage=TypeScript -visitor -no-listener \
		-o /tmp/antlr-out-ts grammar/SysMLv2Lexer.g4 grammar/SysMLv2.g4
	@echo "✅ TypeScript target compiles successfully"

parse-examples: $(ANTLR_JAR) ## Parse example .sysml files through the grammar
	@mkdir -p /tmp/antlr-test
	java -jar $(ANTLR_JAR) -Dlanguage=Java -o /tmp/antlr-test \
		grammar/SysMLv2Lexer.g4 grammar/SysMLv2.g4
	cd /tmp/antlr-test/grammar && javac -cp "$(ANTLR_JAR):." *.java
	@cd /tmp/antlr-test/grammar && PASS=0; FAIL=0; \
	for f in $(CURDIR)/examples/*.sysml; do \
		printf "Parsing $$(basename $$f)... "; \
		if java -cp "$(ANTLR_JAR):." org.antlr.v4.gui.TestRig SysMLv2 rootNamespace "$$f" 2>&1 | grep -qi "error"; then \
			echo "❌ FAIL"; FAIL=$$((FAIL + 1)); \
		else \
			echo "✅ PASS"; PASS=$$((PASS + 1)); \
		fi; \
	done; \
	echo ""; echo "Results: $$PASS passed, $$FAIL failed"; \
	[ $$FAIL -eq 0 ]

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

cycles: ## Detect left-recursion cycles in the grammar
	$(PYTHON) scripts/find_cycles.py grammar/SysMLv2.g4

clean: ## Remove generated/cached artifacts
	rm -rf /tmp/antlr-out /tmp/antlr-out-ts /tmp/antlr-test
	rm -rf .grammar-cache __pycache__ scripts/__pycache__

ci: lint audit drift-check validate parse-examples ## Run full CI pipeline locally
