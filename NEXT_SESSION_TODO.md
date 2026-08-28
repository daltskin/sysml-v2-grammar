# sysml-v2-grammar upstream PR — next-session TODO

## Repo
- `~/sysml-v2-grammar` (user's fork `mycr0ft/sysml-v2-grammar`)
- branch: `fix/expression-precedence` (4 commits, pushed to origin)
- target upstream: `daltskin/sysml-v2-grammar`

## State of the branch (4 commits)

```
4757c4a fix: correct xor/and precedence order per the OMG XText grammar
ec63897 fix: restore postfix meta/@@/@ operators and 'all' extent expression
3d568dd fix: conformance runner and example check actually parse files
e55ed77 fix: per-precedence expression rules + ConnectorEnd/identification conformance fixes
```

All pushed to `origin/fix/expression-precedence`. None merged upstream yet.

Verified: **310/310 official OMG conformance files parse for real** (was vacuously
passing before the runner fixes). Plus three minimal repros from the session
(`connect X[0..1] to Y.Z[1];` fails on upstream — Fix 50a; `subject NS::Name;`
fails on upstream — Fix 50b; `a + b * c` parses as `(a+b)*c` on upstream —
precedence fix).

## What still needs doing

1. **Re-run conformance from the final branch tip** — `rm -rf .build/antlr-test`
   in `~/sysml-v2-grammar`, then
   `export PATH=/tmp/jdk-21.0.2/bin:$PATH && python3 scripts/conformance.py`.
   Expect 310/310. Cheap (~5 min).

2. **Re-verify the 3 minimal repros** against the final grammar (after the
   xor/and fix the grammar changed):
   - `connect lugBoltJoints[0..1] to wheel.w.mountingHoles[1];` → expect PASS
   - `subject SystemGateway::System_Driver;` → expect PASS
   - upstream parse of `a + b * c` → should still produce wrong tree (we can't
     assert this via the fixed runner — it's structural, not an error)

3. **Draft the PR description** (the big remaining piece). Structure:

   - Title: `fix: implement per-precedence expression rules + restore conformance`
   - Lead with the precedence bug (most important — it's a correctness issue,
     not just conformance)
   - One-paragraph summary of the per-cascade rewrite
   - Section: conformance runner fixes (the 3 bugs that made the suite vacuous)
   - Section: 5 conformance fix-patches (50a, 50b, 50c, 50d, xor/and) — each
     with a minimal repro before/after
   - Section: test infrastructure: 310/310 official fixture files now actually
     parse (compared to upstream's vacuous 310/310)
   - Reference the KEBNF/XText: cite the file from the
     `Systems-Modeling/SysML-v2-Pilot-Implementation` repo
     (KerMLExpressions.xtext on master)

4. **Consider a 6th fix patch**: the subject-qualified-name case may also want
   the two-alternative `subjectUsage : SUBJECT featureReferenceUsage` form from
   the OMG grammar (we only added `qualifiedIdentification` to `identification`).
   Worth a quick KEBNF grep to confirm whether upstream is missing this
   alternative.

5. **Open the PR** via `gh`:
   `gh pr create --repo daltskin/sysml-v2-grammar --base main --head mycr0ft:fix/expression-precedence --title "..." --body-file PR.md`

## Useful commands (path is `~/sysml-v2-grammar`)

```bash
export PATH=/tmp/jdk-21.0.2/bin:$PATH

# Run conformance from a clean state
rm -rf .build/antlr-test
python3 scripts/conformance.py          # expect 310/310

# Minimal repro for connectorEnd after-name multiplicity
printf 'part def Wheel {\n    port mountingHoles[4];\n}\n\npart def V {\n    part wheel : Wheel;\n    part lugBoltJoints[0..4];\n    connect lugBoltJoints[0..1] to wheel.w.mountingHoles[1];\n}\n' > /tmp/r1.sysml
# compile then test:
rm -rf .build/antlr-test && mkdir -p .build/antlr-test
java -jar .build/antlr4.jar -Dlanguage=Java -o .build/antlr-test grammar/SysMLv2Lexer.g4 grammar/SysMLv2Parser.g4
(cd .build/antlr-test/grammar && javac -cp "$HOME/sysml-v2-grammar/.build/antlr4.jar:." *.java)
java -cp "$HOME/sysml-v2-grammar/.build/antlr4.jar:." org.antlr.v4.gui.TestRig SysMLv2 rootNamespace /tmp/r1.sysml

# Inspect the generator patches
less scripts/generate_grammar.py    # _generate_expression_rules, Fix 50a/b/c/d, OPERATOR_PRECEDENCE

# Inspect PATCHES.md (auto-generated, lists all deviances from the KEBNF)
less grammar/PATCHES.md
```

## What is NOT in scope (deliberately deferred)

- `render state X { shape box; color ...; annotation "..."; }` is non-standard
  syntax (inherited from sysmlpy's old hand-patched grammar). Fixed on the
  sysmlpy side by rewriting 6 tests to OMG-standard forms. No daltskin change
  needed.
- The 7 phase1 sysmlpy grammar tests (`test_expression_capture_*_v046_phase1`)
  — purely visitor/classes work in `sysmlpy/src/sysmlpy/antlr_visitor.py`,
  unrelated to upstream grammar.

## Reminder: companion sysmlpy changes (already done this session)

- Commit `fb69678` on `main`: visitor rewrite + class fixes + 6 test rewrites
- Commit `5bbd7ac`: grammar + Python parser sync
- Commit `be05663`: v0.53.0 release notes, version bump, tag pushed
- GitHub release: https://github.com/mycr0ft/sysmlpy/releases/tag/v0.53.0
- Upstream PR for sysmlpy: not yet opened (would go to `Westfall-io/sysml2py`)