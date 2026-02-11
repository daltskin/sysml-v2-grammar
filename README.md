# SysML v2 ANTLR4 Grammar

ANTLR4 grammar for the SysML v2 textual notation, automatically generated from
the OMG [Systems-Modeling/SysML-v2-Release](https://github.com/Systems-Modeling/SysML-v2-Release)
specification grammar (KEBNF format).

## Quick Start

```bash
# Install Python dependencies
pip install -r scripts/requirements.txt

# Generate grammar from the OMG spec (downloads KEBNF automatically)
python scripts/generate_grammar.py

# Or specify a different release tag
python scripts/generate_grammar.py --tag 2025-12
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
│   └── Camera.sysml
└── .github/workflows/
    ├── generate.yml          # CI: regenerate + validate grammar
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
java -jar antlr-4.13.2-complete.jar -Dlanguage=Java grammar/SysMLv2Lexer.g4 grammar/SysMLv2.g4
```

### TypeScript
```bash
java -jar antlr-4.13.2-complete.jar -Dlanguage=TypeScript -visitor -no-listener \
  grammar/SysMLv2Lexer.g4 grammar/SysMLv2.g4
node scripts/postprocess-antlr.js  # Fix CommonJS compatibility
```

### Python
```bash
java -jar antlr-4.13.2-complete.jar -Dlanguage=Python3 grammar/SysMLv2Lexer.g4 grammar/SysMLv2.g4
```

## Upstream Tracking

The `watch-upstream.yml` workflow runs weekly to check for new releases of the
OMG SysML v2 specification. When a new tag is detected, it automatically opens
a pull request with regenerated grammar files.

## Current Spec Version

- **Release**: `2025-12`
- **Source**: [Systems-Modeling/SysML-v2-Release](https://github.com/Systems-Modeling/SysML-v2-Release/tree/2025-12)

## Related Projects

- [daltskin/VSCode_SysML_Extension](https://github.com/daltskin/VSCode_SysML_Extension) — VS Code extension using this grammar
- [antlr/grammars-v4](https://github.com/antlr/grammars-v4) — Community grammar repository (future contribution target)

## License

[MIT](LICENSE) — Copyright (c) 2025 J Dalton

The SysML v2 specification grammar is owned by the Object Management Group (OMG).
This project provides a derived ANTLR4 translation of the official KEBNF grammar.
