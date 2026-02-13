# Release Checklist

Steps for publishing a new grammar release. Releases are tagged
`vYYYY.MM.REV` (see [Versioning](#versioning) below).

---

## 1. Pre-release

- [ ] All CI checks pass on `main` (`make ci`)
- [ ] Grammar compiles with zero ANTLR warnings (`make validate`)
- [ ] All example files parse successfully (`make test`)
- [ ] grammars-v4 contribution builds and verifies (`make contrib`)
- [ ] No grammar drift from generator output (`make drift-check`)

## 2. Bump version

```bash
make bump-revision          # e.g. 2026.01.0 → 2026.01.1
# or for a new OMG release, watch-upstream resets to YYYY.MM.0

make version                # confirm the new version
```

- [ ] Version bumped in `scripts/config.json`
- [ ] Commit: `git add scripts/config.json && git commit -m "chore: bump grammar version to $(jq -r .grammar_version scripts/config.json)"`

## 3. Merge to main

- [ ] Open a PR (or push directly if appropriate)
- [ ] CI passes on the PR
- [ ] Merge to `main`

## 4. Automated release

The `generate.yml` workflow handles the rest automatically on merge to `main`:

- [ ] GitHub Release created with tag `vYYYY.MM.REV`
- [ ] Grammar artifacts attached (`SysMLv2Parser.g4`, `SysMLv2Lexer.g4`, `SysMLv2Lexer.tokens`)
- [ ] Contribution artifact uploaded (`grammars-v4-sysmlv2-YYYY.MM.REV`)

## 5. Post-release (if updating grammars-v4)

- [ ] Copy `contrib/sysml/sysmlv2/` into your [antlr/grammars-v4](https://github.com/antlr/grammars-v4) fork
- [ ] Add `<module>sysml/sysmlv2</module>` to the root `pom.xml` (first submission only)
- [ ] Run `cd sysml/sysmlv2 && mvn clean test`
- [ ] Open/update PR against `antlr/grammars-v4:master`

---

## Versioning

Format: **`YYYY.MM.REV`**

| Segment   | Meaning                                                      |
|-----------|--------------------------------------------------------------|
| `YYYY.MM` | Derived from the OMG release tag (e.g. `2026-01` → `2026.01`) |
| `REV`     | Revision counter — starts at `0`, incremented per release    |

- `REV` resets to `0` when the OMG release tag changes (handled by `watch-upstream.yml`)
- Use `make bump-revision` (or `python scripts/bump_version.py`) to increment `REV`
- Use `make bump-revision` with `--dry` flag to preview without writing changes

## When to release

| Scenario                          | Action                                  |
|-----------------------------------|-----------------------------------------|
| New OMG spec release detected     | `watch-upstream` opens PR → merge → auto-release `YYYY.MM.0` |
| Grammar bug fix or improvement    | `make bump-revision` → merge → auto-release |
| Generator patch (no grammar change) | No release needed (grammar unchanged)  |
| CI/tooling-only change            | No release needed                       |
