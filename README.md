# SysML v2 ANTLR4 Grammar

ANTLR4 grammar for the SysML v2 textual notation, automatically generated from the OMG [Systems-Modeling/SysML-v2-Release](https://github.com/Systems-Modeling/SysML-v2-Release) specification grammar (KEBNF format).

## Quick Start

```bash
make install           # Install all dependencies
make generate          # Regenerate grammar from the OMG spec
make test              # Validate grammar + parse examples + conformance
```

### Commands

| Command | Description |
|---------|-------------|
| `make install` | Install Python dependencies + linting tools |
| `make generate` | Regenerate `.g4` grammar from OMG spec |
| `make test` | Compile grammar, parse examples, run conformance tests |
| `make lint` | Lint Python, YAML, Actions, security audit, drift check |
| `make format` | Auto-format Python scripts |
| `make clean` | Remove all generated/cached artifacts |
| `make ci` | Full CI pipeline (`lint` + `test` + `contrib`) |
| `make update-conformance` | Fetch official OMG conformance fixtures |
| `make help` | Show all targets |

## Updating to a New Upstream Release

When the OMG publishes a new SysML v2 Release (detected by the `watch-upstream.yml` cron workflow):

```bash
# 1. Update config to point at the new release tag
#    Edit scripts/config.json: set release_tag and grammar_version

# 2. Regenerate the grammar (fetches new KEBNF, applies patches)
make generate TAG=2026-02

# 3. Fetch the latest conformance fixtures + standard library, then test
make update-conformance
make test

# 4. If tests fail, add new patches to
#    scripts/generate_grammar.py (see grammar/PATCHES.md for existing ones),
#    then repeat from step 2.

# 5. Once green, run the full CI pipeline to verify everything
make ci

# 6. Commit and push
git add -A
git commit -m "chore: update grammar to OMG release 2026-03"
git push
```

The CI workflow will automatically create a GitHub Release with the versioned grammar artifacts.

### Patch Workflow

The OMG KEBNF spec has known ambiguities and omissions that require post-generation patches. These are applied automatically by `generate_grammar.py` and documented in [grammar/PATCHES.md](grammar/PATCHES.md). When a new upstream release introduces new constructs that fail conformance:

1. Identify failing files: `make test` or `python scripts/conformance.py --verbose`
2. Add a fix in the `apply_patches()` method of `scripts/generate_grammar.py`
3. Re-generate: `make generate`
4. Re-test: `make test`

## Repository Structure

```
├── grammar/
│   ├── SysMLv2Parser.g4     # Parser grammar (generated)
│   ├── SysMLv2Lexer.g4      # Lexer grammar (generated)
│   ├── SysMLv2Lexer.tokens  # Token vocabulary
│   └── PATCHES.md           # Documented post-generation patches
├── scripts/
│   ├── generate_grammar.py  # KEBNF → ANTLR4 converter + patches
│   ├── conformance.py       # Conformance test runner
│   ├── build_contrib.py     # grammars-v4 contribution builder
│   ├── config.json          # Generator configuration
│   └── requirements.txt     # Python dependencies
├── examples/                # Hand-written .sysml test files
├── test/fixtures/           # OMG conformance fixtures (fetched, not committed)
└── .github/workflows/
    ├── generate.yml         # CI: lint → test → release
    └── watch-upstream.yml   # Cron: detect new OMG releases
```

## Grammar Generation Pipeline

1. **Download** — Fetches `.kebnf` BNF files from the OMG SysML v2 Release repo
2. **Parse** — Extracts rules, terminals, and properties from KEBNF format
3. **Transform** — Converts to ANTLR4 with precedence-climbing expressions, keyword extraction, and [spec-ambiguity patches](grammar/PATCHES.md)
4. **Generate** — Writes split lexer/parser `.g4` grammars

## Configuration

[scripts/config.json](scripts/config.json) controls the generator:

| Key | Description |
|-----|-------------|
| `release_tag` | OMG release tag (e.g., `2026-02`) |
| `grammar_version` | Grammar version (e.g., `2026.02.0`) |
| `release_repo` | GitHub repo for the OMG spec |
| `bnf_files` | Paths to KerML and SysML KEBNF files |
| `output` | Output file names for parser and lexer grammars |

## CI / CD

The `generate.yml` workflow runs on every push and PR to `main`:

1. **Lint** — Python, YAML, Actions linting + security audit + grammar drift check
2. **Test** — Compile grammar, parse examples, run conformance, build contribution
3. **Release** — Publishes a GitHub Release with versioned grammar artifacts (main branch only)

The ANTLR4 JAR is downloaded and SHA256-verified automatically on first use.
   (main branch only)

## Upstream Tracking

The `watch-upstream.yml` workflow runs weekly to check for new releases of the
OMG SysML v2 specification. When a new tag is detected, it automatically opens
a pull request with regenerated grammar files.

## Current Spec Version

- **Grammar version**: `2026.03.0`
- **OMG release**: `2026-03`
- **Source**: [Systems-Modeling/SysML-v2-Release](https://github.com/Systems-Modeling/SysML-v2-Release/tree/2026-03)

## Versioning

Grammar versions follow **`YYYY.MM.REV`** format:

| Segment | Meaning |
|---------|---------|
| `YYYY.MM` | Derived from the OMG release tag (e.g., `2026-01` → `2026.01`) |
| `REV` | Revision counter, starting at `0`, incremented for each grammar release |

Examples:

| Version | Scenario |
|---------|----------|
| `2026.01.0` | First grammar release from OMG `2026-01` |
| `2026.01.1` | Bug fix or improvement (same OMG spec) |
| `2026.03.0` | First release from new OMG `2026-03` (REV resets) |

To bump the revision before a new release:

```bash
make bump-revision     # 2026.01.0 → 2026.01.1
git add scripts/config.json
git commit -m "chore: bump grammar version to $(jq -r .grammar_version scripts/config.json)"
```

When the `watch-upstream` workflow detects a new OMG release, it automatically
resets the version to `YYYY.MM.0`.

## Contributing to grammars-v4

This repo automates the creation of a ready-to-submit contribution for [antlr/grammars-v4](https://github.com/antlr/grammars-v4).

```bash
make contrib           # Build and verify contribution → contrib/sysml/sysmlv2/
```

The `contrib` target generates:

| File | Purpose |
|------|---------|
| `SysMLv2Parser.g4` | Parser grammar (identical to `grammar/`) |
| `SysMLv2Lexer.g4` | Lexer grammar (identical to `grammar/`) |
| `pom.xml` | Maven test configuration |
| `desc.xml` | trgen test descriptor |
| `README.md` | Documentation with source references |
| `examples/*.sysml` | Test input files |

The CI pipeline builds and verifies the contribution on every push, and attaches
a `grammars-v4-sysmlv2-<version>.zip` asset to each GitHub Release.

## Related Projects

- [daltskin/VSCode_SysML_Extension](https://github.com/daltskin/VSCode_SysML_Extension) — VS Code extension using this grammar
- [antlr/grammars-v4](https://github.com/antlr/grammars-v4) — Community grammar repository (future contribution target)

## License

[MIT](LICENSE) — Copyright (c) 2025 J Dalton

The SysML v2 specification grammar is owned by the Object Management Group (OMG).
This project provides a derived ANTLR4 translation of the official KEBNF grammar.
