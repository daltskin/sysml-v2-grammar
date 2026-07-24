# SysML v2 ANTLR4 Grammar

ANTLR4 grammar for the SysML v2 textual notation, automatically generated from the OMG [Systems-Modeling/SysML-v2-Release](https://github.com/Systems-Modeling/SysML-v2-Release) specification grammar (KEBNF format).

## Quick Start

```bash
make install           # Install all dependencies
make generate          # Regenerate grammar from the OMG spec
make sdk               # Generate SDKs for every ANTLR4 target
make test              # Validate grammar + parse examples + conformance
```

### Commands

| Command | Description |
|---------|-------------|
| `make install` | Install Python dependencies + linting tools |
| `make generate` | Regenerate `.g4` grammar from OMG spec |
| `make sdk` | Generate ANTLR4 source SDKs for all targets, or one via `LANGUAGE=...` |
| `make sdk-archive` | Generate all SDKs and package `.build/releases/sysml-v2-sdks-<version>.zip` |
| `make test` | Compile grammar, parse examples, run conformance tests |
| `make lint` | Lint Python, YAML, Actions, security audit, drift check |
| `make format` | Auto-format Python scripts |
| `make clean` | Remove all generated/cached artifacts |
| `make ci` | Full CI pipeline (`lint` + `test` + `contrib` + `sdk-archive`) |
| `make update-conformance` | Fetch official OMG conformance fixtures |
| `make help` | Show all targets |

## Generate Target-Language SDKs

ANTLR4 can emit parser source trees for every code generator bundled in the
pinned toolchain. This repo exposes that directly:

```bash
make sdk                 # Generate every ANTLR4 target under .build/sdks/
make sdk LANGUAGE=Cpp    # Generate only the C++ SDK
make sdk LANGUAGE=Go     # Generate only the Go SDK
make sdk SDK_JOBS=0      # Auto-parallelize by CPU count (fastest)
make sdk-archive         # Generate all SDKs + zip them for release use
```

Set `SDK_JOBS=<n>` to control parallel workers (`0` means auto-detect, `1`
forces serial generation).

By default, SDK output is restricted to paths under `.build/` to avoid
accidental directory cleanup. To intentionally write outside `.build`, pass:

```bash
python3 scripts/generate_sdks.py --output-root /tmp/sysml-sdks --allow-outside-build
```

For the current ANTLR `4.13.2` toolchain, `make sdk` generates source SDKs for:

- `CSharp`
- `Cpp`
- `Dart`
- `Go`
- `Java`
- `JavaScript`
- `PHP`
- `Python3`
- `Swift`
- `TypeScript`

The generated output lives under `.build/sdks/<Language>/` and includes a
`manifest.json` file describing the grammar version, upstream release tag, and
generated targets. These SDKs are raw ANTLR output, so language-specific
runtimes and packaging remain the responsibility of downstream consumers.

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

The CI workflow will automatically create a GitHub Release with the versioned
grammar artifacts, contribution zip, and all generated language SDKs.

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
│   ├── generate_sdks.py     # ANTLR4 target SDK generator + release archive packer
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
2. **Test** — Compile grammar, parse examples, run conformance, build contribution, and generate the all-language SDK archive
3. **Release** — Publishes a GitHub Release with the contribution zip and the all-language SDK zip (main branch only)

The ANTLR4 JAR is downloaded and SHA256-verified automatically on first use.

## Upstream Tracking

The `watch-upstream.yml` workflow runs weekly to check for new releases of the
OMG SysML v2 specification. When a new tag is detected, it automatically opens
a pull request with regenerated grammar files.

## Current Spec Version

- **Grammar version**: `2026.05.0`
- **OMG release**: `2026-05`
- **Source**: [Systems-Modeling/SysML-v2-Release](https://github.com/Systems-Modeling/SysML-v2-Release/tree/2026-05)

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
