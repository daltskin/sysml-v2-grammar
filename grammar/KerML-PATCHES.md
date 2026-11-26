# Grammar Patches

Post-generation patches applied to the ANTLR4 grammar to fix known issues in the
OMG KerML KEBNF specification when translated to ANTLR4.

- **Grammar version**: `2026.09.1`
- **OMG release**: `2026-09.1`
- **Total patches**: 21
- **Applied**: 15
- **Skipped**: 6

## Expression scope ledger

The expression changes are limited to the generated `ownedExpression` precedence order and the directly required primary boundaries. Each row has a distinguishing regression; restoring the corresponding hunk reproduces the listed failure.
Non-empty `functionBodyPart` ambiguity is inherited from the base grammar and remains a separate body follow-up; this patch covers only empty-body postfix boundaries and makes no claim about non-empty body acceptance.

| Generated hunk | Official evidence | Distinguishing regression | Restore failure |
|---|---|---|---|
| `ownedExpression` tier order and final conditional alternative | [KEBNF operator productions](https://github.com/Systems-Modeling/SysML-v2-Release/blob/de1070ae8e79c21532b8004fc663d47b35d0e9fa/bnf/KerML-textual-bnf.kebnf#L932-L969); [OMG Table 6](https://www.omg.org/spec/KerML/1.0/PDF#page=124) | `a + b * c`; `a == b & c xor d | e implies f ?? g`; `if a ? b else c + d` | Base order groups lower-precedence operators inside higher-precedence operands and lets the trailing operator escape the `else` branch. |
| Right-associative exponentiation tier | [KEBNF associativity note](https://github.com/Systems-Modeling/SysML-v2-Release/blob/de1070ae8e79c21532b8004fc663d47b35d0e9fa/bnf/KerML-textual-bnf.kebnf#L1061-L1064) | `a * b ** c`; `a ** b * c`; `a ** b ** c`; `a ^ b ^ c` | Base emission places exponentiation below multiplication in the ANTLR alternative order, so adjacent-tier grouping is wrong; the explicit right-associative marker alone does not repair that precedence. |
| Classification/metaclassification and type-reference boundaries | [KEBNF classification productions](https://github.com/Systems-Modeling/SysML-v2-Release/blob/de1070ae8e79c21532b8004fc663d47b35d0e9fa/bnf/KerML-textual-bnf.kebnf#L979-L1037) | `a istype T + b`; `a istype T as U`; `a + b @@ T`; `a @@ T @@ U` | Restoring the boundary loses recursive raw-KEBNF forms or accepts the invalid chained metaclassification form. |
| `primaryExpression` postfix boundary | [KEBNF primary-expression productions](https://github.com/Systems-Modeling/SysML-v2-Release/blob/de1070ae8e79c21532b8004fc663d47b35d0e9fa/bnf/KerML-textual-bnf.kebnf#L1068-L1178); [official Pilot primary rules](https://github.com/Systems-Modeling/SysML-v2-Pilot-Implementation/blob/fa709f28dfd49dfdb7ee83e4e19da2f57e0eb3aa/org.omg.kerml.expressions.xtext/src/org/omg/kerml/expressions/xtext/KerMLExpressions.xtext#L300-L324) | `-a.f`; `not a.f`; `~a[1]`; `-a->F()`; `all T.f`; `istype T.f` | Restoring direct-left-recursive postfix alternatives changes the official grouping `-(a.f)` to `(-a).f`, and permits postfix continuation after `all` or classification operands. |
| Empty-parenthesized boundary | [KEBNF `NullExpression`](https://github.com/Systems-Modeling/SysML-v2-Release/blob/de1070ae8e79c21532b8004fc663d47b35d0e9fa/bnf/KerML-textual-bnf.kebnf#L1182-L1193) | `()` | The PR base reaches `()` through both `nullExpression` and optional `sequenceExpressionList`, producing one exact ambiguity; retaining one path preserves acceptance with zero ambiguity. |
| Skipped Fix 53 metadata-cast base alternative | [KEBNF classification production](https://github.com/Systems-Modeling/SysML-v2-Release/blob/de1070ae8e79c21532b8004fc663d47b35d0e9fa/bnf/KerML-textual-bnf.kebnf#L979-L985) | `(as T).isMandatory` | Restoring Fix 53 creates an exact ambiguity; the direct `AS` classification alternative accepts this form without the duplicate base production. |
| Sequence, invocation, and constructor primary boundaries | [KEBNF primary/base productions](https://github.com/Systems-Modeling/SysML-v2-Release/blob/de1070ae8e79c21532b8004fc663d47b35d0e9fa/bnf/KerML-textual-bnf.kebnf#L1068-L1233) | `a[1,]`; `a#(1,)`; `a.f.g()`; `new A.B()`; `a[]` | Base accepts empty sequence/index forms, does not preserve trailing commas, or rejects a qualified feature-chain invocation. |

## Spec BNF fix

| # | Summary | Rules | Applied |
|---|---------|-------|---------|
| 4 | Make `STANDARD` optional in `libraryPackage` | libraryPackage | Yes |
| 55 | Optional `featureDeclaration` in `invariant` | invariant | Yes |

### Fix 4: Make `STANDARD` optional in `libraryPackage`

Same `?=` boolean assignment issue as Fix 3.

**Affected rules**: libraryPackage

### Fix 55: Optional `featureDeclaration` in `invariant`

KerML 7.4.8.5 declares invariants without a feature declaration (`inv { fuelLevel >= 0 & fuelLevel <= maxFuelLevel }`, `inv false { fuelLevel > maxFuelLevel }`), as the Kernel Semantic Library does (`Occurrences.kerml`, `StatePerformances.kerml`, ...), but the KEBNF `Invariant` production requires `FeatureDeclaration`. Made it optional.

**Affected rules**: invariant

## SLL prediction fix

| # | Summary | Rules | Applied |
|---|---------|-------|---------|
| 11 | Merge `qualifiedName \| ownedFeatureChain` alternatives | generalType, specificType, unioning, intersecting, differencing, ownedFeatureInverting, ownedConjugation, ownedDisjoining, instantiatedTypeMember | Yes |
| 12 | Simplify `flowEnd` after feature chain merge | flowEnd | No |
| 22 | Merge expression alternatives in `baseExpression` | baseExpression | Yes |

### Fix 11: Merge `qualifiedName | ownedFeatureChain` alternatives

ANTLR4's SLL prediction mode can't distinguish `qualifiedName` from `ownedFeatureChain` because they share the same prefix. Merged ~15 rules with `qualifiedName | ownedFeatureChain` patterns into `qualifiedName ( DOT qualifiedName )*`. Patterns A–H cover named rules, inline alternatives, and `featureChain` variants.

**Affected rules**: generalType, specificType, unioning, intersecting, differencing, ownedFeatureInverting, ownedConjugation, ownedDisjoining, instantiatedTypeMember

### Fix 12: Simplify `flowEnd` after feature chain merge

`ownedReferenceSubsetting` now consumes dots greedily (Fix 11), so the explicit `DOT` in `flowEnd` is never reached. Simplified to `qualifiedName ( DOT qualifiedName )*`.

**Affected rules**: flowEnd

### Fix 22: Merge expression alternatives in `baseExpression`

Merged `featureReferenceExpression`, `metadataAccessExpression`, and `invocationExpression` into a single alternative that avoids SLL prediction ambiguity on `qualifiedName` lookahead.

**Affected rules**: baseExpression

## Extension compatibility

| # | Summary | Rules | Applied |
|---|---------|-------|---------|
| 13 | Rewrite `identification` to prevent empty match | identification | Yes |
| 14 | Optional `identification` in annotation rules | commentAnnotation, documentation, textualRepresentation | Yes |
| 16 | Optional `identification` in namespace/type/classifier declarations | namespaceDeclaration, typeDeclaration, classifierDeclaration | Yes |
| 17 | Optional `identification` in relationship declarations | subtypeDeclaration, conjugationDeclaration, disjoiningDeclaration, subclassificationDeclaration, featureTypingDeclaration, subsettingDeclaration, redefinitionDeclaration, featuringDeclaration | Yes |
| 18 | Optional `identification` in definitions, packages, and other declarations | definitionDeclaration, packageDeclaration, multiplicitySubset, multiplicityRange, dependencyDeclaration, metadataFeatureDeclaration, metadataUsageDeclaration | Yes |
| 24 | Optional `usageDeclaration` in `ownedCrossFeature` | ownedCrossFeature | No |
| 35 | Optional `usageDeclaration` in `flowDeclaration`; remove redundant alternative | flowDeclaration | No |

### Fix 13: Rewrite `identification` to prevent empty match

The generator produces `( LT name GT )? ( name )?` which can match the empty string. Rewritten to explicit alternatives that each require at least one component.

**Affected rules**: identification

### Fix 14: Optional `identification` in annotation rules

`Comment`, `Documentation` and `TextualRepresentation` have an `Identification` that may be empty (KerML 8.2.3.3.2, 8.2.3.1). With Fix 13 requiring a name or short name in `identification`, made it optional in comment, doc, and rep declarations.

**Affected rules**: commentAnnotation, documentation, textualRepresentation

### Fix 16: Optional `identification` in namespace/type/classifier declarations

A namespace, type or classifier may be anonymous: its `Identification` is empty (KerML 8.2.3.1). With Fix 13 requiring a name or short name in `identification`, made it optional in `namespaceDeclaration`, `typeDeclaration`, and `classifierDeclaration`.

**Affected rules**: namespaceDeclaration, typeDeclaration, classifierDeclaration

### Fix 17: Optional `identification` in relationship declarations

Made `identification` optional in specialization, conjugation, disjoining, subclassifier, typing, subset, redefinition, and featuring declarations.

**Affected rules**: subtypeDeclaration, conjugationDeclaration, disjoiningDeclaration, subclassificationDeclaration, featureTypingDeclaration, subsettingDeclaration, redefinitionDeclaration, featuringDeclaration

### Fix 18: Optional `identification` in definitions, packages, and other declarations

Made `identification` optional in `definitionDeclaration`, `packageDeclaration`, `multiplicitySubset`, `multiplicityRange`, `dependencyDeclaration`, `metadataFeatureDeclaration`, and `metadataUsageDeclaration`.

**Affected rules**: definitionDeclaration, packageDeclaration, multiplicitySubset, multiplicityRange, dependencyDeclaration, metadataFeatureDeclaration, metadataUsageDeclaration

### Fix 24: Optional `usageDeclaration` in `ownedCrossFeature`

Made `usageDeclaration` optional in the `basicUsagePrefix` alternative.

**Affected rules**: ownedCrossFeature

### Fix 35: Optional `usageDeclaration` in `flowDeclaration`; remove redundant alternative

Made `usageDeclaration` optional and removed the redundant `flowEndMember TO flowEndMember` alternative (already covered by the preceding alternative with optional parts).

**Affected rules**: flowDeclaration

## Structural optimization

| # | Summary | Rules | Applied |
|---|---------|-------|---------|
| 19 | Simplify `packageBody` alternatives | packageBody | No |
| 20 | Restructure `multiplicityPart` ordering keywords | multiplicityPart | Yes |
| 21 | Collapse redundant `resultExpressionMember` alternatives | resultExpressionMember | No |

### Fix 19: Simplify `packageBody` alternatives

Removed the `namespaceBodyElement | elementFilterMember` alternative. The extension uses only `packageBodyElement*` for package bodies.

**Affected rules**: packageBody

### Fix 20: Restructure `multiplicityPart` ordering keywords

Made the ordering keywords (`ORDERED`, `NONUNIQUE`) combinable with `ownedMultiplicity` in a single branch.

**Affected rules**: multiplicityPart

### Fix 21: Collapse redundant `resultExpressionMember` alternatives

The generator produces two alternatives where the second (`memberPrefix?`) subsumes the first (`memberPrefix`). Collapsed to a single alternative.

**Affected rules**: resultExpressionMember

## Target compatibility

| # | Summary | Rules | Applied |
|---|---------|-------|---------|
| 39 | Rename `empty*` rules for Go target compatibility | emptyFeature_, emptyMultiplicity_, emptyUsage_, emptyActionUsage_ | Yes |

### Fix 39: Rename `empty*` rules for Go target compatibility

The Go ANTLR runtime generates exported methods from rule names. Rules named `empty*` collide with Go identifiers. Appended `_` to: `emptyFeature` → `emptyFeature_`, `emptyMultiplicity` → `emptyMultiplicity_`, `emptyUsage` → `emptyUsage_`, `emptyActionUsage` → `emptyActionUsage_`.

**Affected rules**: emptyFeature_, emptyMultiplicity_, emptyUsage_, emptyActionUsage_

## Conformance fix

| # | Summary | Rules | Applied |
|---|---------|-------|---------|
| 42 | Handle `//*..*/` block comments in `REGULAR_COMMENT` lexer rule | REGULAR_COMMENT (lexer rule, updated) | Yes |
| 50 | Allow `REGULAR_COMMENT` as a no-op expression in `baseExpression` | baseExpression | Yes |
| 57 | `rootNamespace` is the whole text (`EOF`) | rootNamespace | Yes |

### Fix 42: Handle `//*..*/` block comments in `REGULAR_COMMENT` lexer rule

Official OMG SysML v2 training/validation files use `//* ... */` to comment out code blocks. Changed `REGULAR_COMMENT` to `'//'? '/*' .*? '*/'` so it also matches the `//` prefix form. ANTLR longest-match ensures `REGULAR_COMMENT` wins over `SINGLE_LINE_NOTE` for single-line `//* ... */`.

**Affected rules**: REGULAR_COMMENT (lexer rule, updated)

### Fix 50: Allow `REGULAR_COMMENT` as a no-op expression in `baseExpression`

Analysis Case Usage Example.sysml uses `= ( //* ... */ )` where the entire expression is a commented-out placeholder. After Fix 42 unified `//*` into `REGULAR_COMMENT`, the token appears inside parenthesized expressions. Added `REGULAR_COMMENT` as an alternative in `baseExpression`.

**Affected rules**: baseExpression

### Fix 57: `rootNamespace` is the whole text (`EOF`)

Every valid KerML text is parsed starting from the `RootNamespace` production (KerML 8.2.3.4.1, Note 1), whose body is the list of the text's top-level elements (KerML 7.2.5.3). The KEBNF production has no end-of-input marker, so the generated `rootNamespace` stops, without an error, before the first input it can't match, and the rest of the text is neither parsed nor reported. Added `EOF` after `namespaceBodyElement*`; what the production matches is unchanged.

**Affected rules**: rootNamespace

## Extension

| # | Summary | Rules | Applied |
|---|---------|-------|---------|
| 53 | Add metadata cast expression `(as Type)` to `baseExpression` | baseExpression | No |

### Fix 53: Add metadata cast expression `(as Type)` to `baseExpression`

Skipped because the direct ``AS`` classification alternative covers the same parenthesized form without a duplicate base production.

**Affected rules**: baseExpression

## Dead rule removal

| # | Summary | Rules | Applied |
|---|---------|-------|---------|
| 52 | Remove 34 unreachable parser rules | (34 rules removed) | Yes |

### Fix 52: Remove 34 unreachable parser rules

Removed 34 parser rules unreachable from `rootNamespace`: definitions that other fixes left behind, or that no production references.

**Affected rules**: (34 rules removed)

---

*Auto-generated by `scripts/generate_grammar.py`.*
