# SysML v2 ANTLR4 Grammar

ANTLR4 grammars for the SysML v2 and the KerML textual notations, automatically generated from the OMG [Systems-Modeling/SysML-v2-Release](https://github.com/Systems-Modeling/SysML-v2-Release) specification grammars (KEBNF format).

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
| `make generate` | Regenerate the SysML and KerML `.g4` grammars from the OMG spec |
| `make generate-sysml` | Regenerate the SysML grammar only |
| `make generate-kerml` | Regenerate the KerML grammar only |
| `make sdk` | Generate ANTLR4 source SDKs for all targets, or one via `LANGUAGE=...` |
| `make sdk-archive` | Generate all SDKs and package `.build/releases/sysml-v2-sdks-<version>.zip` |
| `make test` | Compile grammar, parse examples, run conformance tests |
| `make lint` | Lint Python, YAML, Actions, security audit, drift check |
| `make format` | Auto-format Python scripts |
| `make clean` | Remove all generated/cached artifacts |
| `make ci` | Full CI pipeline (`lint` + `test` + `contrib` + `sdk-archive`) |
| `make update-conformance` | Fetch official OMG conformance fixtures, SysML and KerML |
| `make help` | Show all targets |

## Generate Target-Language SDKs

ANTLR4 can emit parser source trees for every code generator bundled in the
pinned toolchain. This repo exposes that directly, for the SysML and the KerML
grammar alike: each target's folder holds one folder per grammar, `sysml/`
(`SysMLv2Lexer`/`SysMLv2Parser`) and `kerml/` (`KerMLLexer`/`KerMLParser`), and
`manifest.json` names each grammar's folder and files. The grammars share rule
names, so they are kept apart: in one Go package or PHP namespace their context
classes would clash. Earlier releases had the SysML files directly in each
target's folder; they are now in its `sysml/` folder.

```bash
make sdk                 # Generate every ANTLR4 target under .build/sdks/
make sdk LANGUAGE=Cpp    # Generate only the C++ SDK
make sdk LANGUAGE=Go     # Generate only the Go SDK
make sdk GRAMMAR=kerml   # Generate only the KerML grammar's SDKs
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

The generated output lives under `.build/sdks/<Language>/<grammar>/`, next to a
`.build/sdks/manifest.json` file describing the grammar version, upstream release tag, and
generated targets. These SDKs are raw ANTLR output, so language-specific
runtimes and packaging remain the responsibility of downstream consumers.

## Updating to a New Upstream Release

When the OMG publishes a new SysML v2 Release (detected by the `watch-upstream.yml` cron workflow):

```bash
# 1. Update config to point at the new release tag
#    Edit scripts/config.json: set release_tag and grammar_version

# 2. Regenerate the grammar (fetches new KEBNF, applies patches)
make generate TAG=2026-02

# 3. Fetch conformance fixtures + standard library for the configured release, then test
make update-conformance
make test

# 4. If tests fail, add new patches to scripts/patches.json
#    (see grammar/SysML-PATCHES.md and grammar/KerML-PATCHES.md for existing ones),
#    then repeat from step 2.

# 5. Once green, run the full CI pipeline to verify everything
make ci

# 6. Commit and push
git add -A
git commit -m "chore: update grammar to OMG release 2026-03"
git push
```

`make update-conformance` downloads both the official fixtures and standard
library from `release_repo` and `release_tag` in `scripts/config.json`, not from
upstream `master`, and the KerML fixtures (the KerML examples and the Kernel
Libraries) from the same release. Update the config before fetching; `make generate TAG=...`
does not change it. Both downloads are ignored local caches, refreshed by CI
before conformance testing; they are not committed to this repository.

The CI workflow will automatically create a GitHub Release with the versioned
grammar artifacts, contribution zip, and all generated language SDKs.

### Patch Workflow

The OMG KEBNF spec has known ambiguities and omissions that require post-generation patches. These are applied automatically by `generate_grammar.py` and documented in [grammar/SysML-PATCHES.md](grammar/SysML-PATCHES.md) and [grammar/KerML-PATCHES.md](grammar/KerML-PATCHES.md). When a new upstream release introduces new constructs that fail conformance:

1. Identify failing files: `make test` or `python scripts/conformance.py --verbose` (`--language sysml|kerml` for one language)
2. Add the fix to `scripts/patches.json`, keyed by its fix number (`replace` lists its `old`/`new` texts), with the grammars it applies to in its `language` list: `["sysml"]`, `["kerml"]`, or `["sysml", "kerml"]`. A fix of a KerML production is `["sysml", "kerml"]` when both grammars need it, as the SysML grammar contains the KerML productions; it is `["kerml"]` when the SysML grammar doesn't need it, because SysML has its own production or fix for the construct, so the SysML grammar stays unchanged. A fix whose `old` text only occurs in the SysML grammar (e.g. a rule merged from both KEBNF files) is `["sysml"]`. The patches are applied in the file's order, so a new fix goes before Fix 52, which removes the rules left unreachable and comes last
3. Re-generate: `make generate`
4. Re-test: `make test`

## Repository Structure

```
├── grammar/
│   ├── SysMLv2Parser.g4     # Parser grammar (generated)
│   ├── SysMLv2Lexer.g4      # Lexer grammar (generated)
│   ├── SysMLv2Lexer.tokens  # Token vocabulary
│   ├── SysML-PATCHES.md     # Documented post-generation patches of the SysML grammar
│   ├── KerMLParser.g4       # KerML parser grammar (generated)
│   ├── KerMLLexer.g4        # KerML lexer grammar (generated)
│   └── KerML-PATCHES.md     # Documented post-generation patches of the KerML grammar
├── scripts/
│   ├── generate_grammar.py  # KEBNF → ANTLR4 converter, SysML and KerML
│   ├── generate_sdks.py     # ANTLR4 target SDK generator + release archive packer
│   ├── conformance.py       # Conformance test runner, SysML and KerML
│   ├── build_contrib.py     # grammars-v4 contribution builder
│   ├── config.json          # Generator configuration
│   ├── patches.json         # Post-generation patches, by fix number
│   └── requirements.txt     # Python dependencies
├── examples/                # Hand-written .sysml test files
├── CHANGELOG.md             # Changes, and deviations from the standard
├── test/fixtures/           # OMG conformance fixtures (fetched, not committed)
└── .github/workflows/
    ├── generate.yml         # CI: lint → test → release
    └── watch-upstream.yml   # Cron: detect new OMG releases
```

## Grammar Generation Pipeline

1. **Download** — Fetches `.kebnf` BNF files from the OMG SysML v2 Release repo
2. **Parse** — Extracts rules, terminals, and properties from KEBNF format
3. **Transform** — Converts to ANTLR4 with precedence-climbing expressions, keyword extraction, and spec-ambiguity patches ([SysML](grammar/SysML-PATCHES.md), [KerML](grammar/KerML-PATCHES.md))
4. **Generate** — Writes split lexer/parser `.g4` grammars

The same generator writes the KerML grammar, from the KerML KEBNF alone, rooted at KerML's `rootNamespace` (`--language kerml` generates only it, `--language sysml` only the SysML grammar). In `generate_grammar.py`, the generic part (KEBNF parser, ANTLR4 transformer, patch mechanism) knows no language; the KerML section (expressions, rule transforms, notes and comments) refers to nothing of SysML; the SysML section adds its own transforms. The patches are data, in `scripts/patches.json`, applied in the file's order; each one's `language` list names the grammars it applies to (see the Patch Workflow above).

## KerML Grammar

The KerML grammar (`grammar/KerMLLexer.g4`, `grammar/KerMLParser.g4`) is
generated from the KerML KEBNF alone and rooted at KerML's `rootNamespace`, so
it parses KerML text, such as the Kernel Libraries (`.kerml`), without SysML's
productions:

- Its lexer reserves KerML's keywords (KerML 8.2.2.6), so a word only SysML
  reserves, such as `part` or `action`, is a name.
- It reads strings, names, white space, notes and comments exactly as the SysML
  grammar does, as SysML's lexical structure is KerML's apart from the reserved
  words (SysML 8.2.2.1.2).
- Its patches are documented in [grammar/KerML-PATCHES.md](grammar/KerML-PATCHES.md);
  its deviations from the standard, and those of the SysML grammar, are listed
  in [CHANGELOG.md](CHANGELOG.md).

## Configuration

[scripts/config.json](scripts/config.json) controls the generator:

| Key | Description |
|-----|-------------|
| `release_tag` | OMG release tag (e.g., `2026-02`) |
| `grammar_version` | Grammar version (e.g., `2026.02.0`) |
| `release_repo` | GitHub repo for the OMG spec |
| `bnf_files` | Paths to KerML and SysML KEBNF files |
| `patch_file` | The post-generation patches, by fix number (`scripts/patches.json`) |
| `sysml` | The SysML grammar: `output` (parser and lexer grammars, patch documentation) and `options` (grammar and lexer names, root rule). Its patches are those of `patch_file` whose `language` list names `sysml` |
| `kerml` | The KerML grammar: `output` and `options` as for `sysml`, from the same `release_tag`. Its patches are those whose `language` list names `kerml` |

## CI / CD

The `generate.yml` workflow runs on every push and PR to `main`:

1. **Lint** — Python, YAML, Actions linting + security audit + grammar drift check
2. **Test** — Compile grammar, parse examples, run conformance, build contribution, and generate the all-language SDK archive
3. **Release** — Publishes a GitHub Release with the contribution zip and the all-language SDK zip (main branch only)

The ANTLR4 JAR is downloaded and SHA256-verified automatically on first use.

## Upstream Tracking

The `watch-upstream.yml` workflow runs weekly to check for new releases of the
OMG SysML v2 specification. When a new tag is detected, it automatically opens
a pull request with the regenerated SysML and KerML grammar files. It checks all tag pages and
recognizes both monthly tags (`2026-09`) and dotted updates (`2026-09.1`),
selecting the newest by version order. Missing valid release tags fail the run
rather than reporting that the grammar is up to date.

## Current Spec Version

- **Grammar version**: `2026.09.1`
- **OMG release**: `2026-09.1`
- **Source**: [Systems-Modeling/SysML-v2-Release](https://github.com/Systems-Modeling/SysML-v2-Release/tree/2026-09.1)

### 2026.09.0 compatibility notes

- Typed ends in action bodies now parse, including the September library's
  `Flows::messages` source and target ends. The same support applies to shared
  non-behavior body items in states, calculations and cases.
- This is an explicit departure from the published SysML 2.0 BNF
  (8.2.2.9.2 and 8.2.2.17), consistent with the OMG library and the Pilot's
  `OccurrenceUsagePrefix`. It extends the existing end-occurrence support,
  rather than changing the downloaded library or excluding it from conformance.
  [PR #18](https://github.com/daltskin/sysml-v2-grammar/pull/18) tracks the
  discrepancy. Remove the compatibility alternative when the upstream BNF
  provides the equivalent route; generation fails if the expected body rule
  changes. See generated [Fix 54](grammar/SysML-PATCHES.md#fix-54-allow-typed-ends-in-shared-non-behavior-body-items)
  for the evidence and regression tests.

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
resets the version to `YYYY.MM.0` if the release month changes. For an upstream
update within the same month (e.g., `2026-09` → `2026-09.1`), it increments the
current grammar revision instead, avoiding reuse of an existing release version.
The upstream suffix is not the grammar revision counter.

## Contributing to grammars-v4

This repo automates the creation of a ready-to-submit contribution of the SysML grammar for [antlr/grammars-v4](https://github.com/antlr/grammars-v4); the KerML grammar isn't part of it.

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
