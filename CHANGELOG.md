# Changelog

## [Unreleased]

### Fixed

- The conformance runner always tests the current grammar of each language.

### Changed

- **Breaking:** the SDKs have one folder per grammar, `<Language>/sysml/` and `<Language>/kerml/`.
- **Breaking:** `grammar/PATCHES.md` is renamed `grammar/SysML-PATCHES.md`.
- The patches are in `scripts/patches.json`, each with the languages it applies to; `scripts/config.json` has a `sysml` and a `kerml` section.

### Added

- A KerML grammar (`KerMLLexer.g4`, `KerMLParser.g4`), generated from the KerML KEBNF, with its SDKs and conformance tests. It reads strings, names, white space, notes and comments exactly as the SysML grammar does.
