# SysML v2 ANTLR4 Grammar

ANTLR4 grammar for the SysML v2 textual notation, automatically generated from
the OMG [Systems-Modeling/SysML-v2-Release](https://github.com/Systems-Modeling/SysML-v2-Release)
specification grammar (KEBNF format).

## Quick Start

### Devcontainer (recommended)

Open in GitHub Codespaces or VS Code Dev Containers — everything is pre-installed
and ready via the `postCreateCommand`.

### Manual Setup

```bash
# Install runtime + dev dependencies (ruff, yamllint, actionlint, pip-audit)
make install-dev

# Download and SHA256-verify the ANTLR4 JAR
make download-antlr
```

### Common Commands

```bash
make generate          # Regenerate grammar from the OMG spec
make validate          # Compile grammar with ANTLR4 (Java target)
make validate-ts       # Compile grammar with ANTLR4 (TypeScript target)
make parse-examples    # Parse example .sysml files through the grammar
make lint              # Run all linters (ruff, yamllint, actionlint)
make audit             # Scan Python dependencies for known CVEs
make format            # Auto-format Python scripts
make ci                # Run full CI pipeline locally
make help              # Show all available targets
```

### Generating for a Specific Release

```bash
make generate TAG=2025-12
```

The generated `.g4` files are written to `grammar/`.

## Repository Structure

```
├── grammar/
│   ├── SysMLv2.g4          # Parser grammar (generated)
│   ├── SysMLv2Lexer.g4     # Lexer grammar (generated)
│   └── SysMLv2Lexer.tokens # Token vocabulary
├── scripts/
│   ├── generate_grammar.py  # KEBNF → ANTLR4 converter
│   ├── config.json          # Generator configuration
│   ├── requirements.txt     # Python dependencies
│   ├── kebnf_grammar.lark   # Lark grammar for KEBNF parsing
│   └── postprocess-antlr.js # Post-processor for TypeScript output
├── examples/
│   ├── vehicle-model.sysml
│   ├── toaster-system.sysml
│   └── camera.sysml
└── .github/workflows/
    ├── generate.yml          # CI: regenerate, validate, release
    └── watch-upstream.yml    # Cron: detect new OMG releases
```

## Grammar Generation Pipeline

1. **Download**: Fetches `.kebnf` BNF files from the OMG SysML v2 Release repository
2. **Parse**: Regex-based KEBNF parser extracts rules, terminals, and properties
3. **Transform**: Converts to ANTLR4 format with precedence-climbing for expressions,
   keyword extraction, and 12 spec-ambiguity patches
4. **Generate**: Writes split lexer/parser `.g4` grammars

## Configuration

[scripts/config.json](scripts/config.json) controls the generator:

| Key | Description |
|-----|-------------|
| `release_tag` | OMG release tag (e.g., `2025-12`) |
| `release_repo` | GitHub repo for the OMG spec |
| `bnf_files` | Paths to KerML and SysML KEBNF files within the release |
| `output` | Output file names for parser and lexer grammars |
| `options` | Grammar name, lexer name, root rule |

## Using with ANTLR4

### Java

```bash
make download-antlr
make validate
```

Or directly:

```bash
java -jar .build/antlr4.jar -Dlanguage=Java \
  grammar/SysMLv2Lexer.g4 grammar/SysMLv2.g4
```

### TypeScript

```bash
make validate-ts
```

Or with post-processing for CommonJS compatibility:

```bash
java -jar .build/antlr4.jar -Dlanguage=TypeScript -visitor -no-listener \
  grammar/SysMLv2Lexer.g4 grammar/SysMLv2.g4
node scripts/postprocess-antlr.js
```

### Python

```bash
java -jar .build/antlr4.jar -Dlanguage=Python3 \
  grammar/SysMLv2Lexer.g4 grammar/SysMLv2.g4
```

## CI / CD

The `generate.yml` workflow runs on every push and PR to `main`:

1. **Regenerate** — checks grammar hasn't drifted from the generator output
2. **Validate** — compiles with ANTLR4 (Java + TypeScript targets)
3. **Parse examples** — runs all `.sysml` files through the grammar
4. **Release** — publishes a GitHub Release with versioned grammar artifacts
   (main branch only)

## Upstream Tracking

The `watch-upstream.yml` workflow runs weekly to check for new releases of the
OMG SysML v2 specification. When a new tag is detected, it automatically opens
a pull request with regenerated grammar files.

## Current Spec Version

- **Release**: `2025-12`
- **Source**: [Systems-Modeling/SysML-v2-Release](https://github.com/Systems-Modeling/SysML-v2-Release/tree/2025-12)

## Contributing to grammars-v4

This repo automates the creation of a ready-to-submit contribution for
[antlr/grammars-v4](https://github.com/antlr/grammars-v4).

```bash
make contrib           # Build contribution directory → contrib/sysml/sysmlv2/
make contrib-verify    # Build + verify all grammars-v4 requirements
```

The `contrib` target generates:

| File | Purpose |
|------|---------|
| `SysMLv2.g4` | Parser grammar — EOF-patched, antlr-formatted |
| `SysMLv2Lexer.g4` | Lexer grammar — antlr-formatted |
| `pom.xml` | Maven test configuration |
| `desc.xml` | trgen test descriptor |
| `README.md` | Documentation with source references |
| `examples/*.sysml` | Test input files |

The CI pipeline builds and verifies the contribution on every push, and attaches
a `grammars-v4-sysmlv2-<tag>` artifact to each GitHub Release.

To submit a PR:

1. Fork [antlr/grammars-v4](https://github.com/antlr/grammars-v4)
2. Copy `contrib/sysml/sysmlv2/` into your fork
3. Add `<module>sysml/sysmlv2</module>` to the root `pom.xml`
4. Run `cd sysml/sysmlv2 && mvn clean test`
5. Open a PR against `antlr/grammars-v4:master`

## Related Projects

- [daltskin/VSCode_SysML_Extension](https://github.com/daltskin/VSCode_SysML_Extension) — VS Code extension using this grammar
- [antlr/grammars-v4](https://github.com/antlr/grammars-v4) — Community grammar repository (future contribution target)

## License

[MIT](LICENSE) — Copyright (c) 2025 J Dalton

The SysML v2 specification grammar is owned by the Object Management Group (OMG).
This project provides a derived ANTLR4 translation of the official KEBNF grammar.
