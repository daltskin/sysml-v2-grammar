# Grammar Patches

Post-generation patches applied to the ANTLR4 grammar to fix known issues in the
OMG SysML v2 KEBNF specification when translated to ANTLR4.

- **Grammar version**: `2026.03.0`
- **OMG release**: `2026-03`
- **Total patches**: 56
- **Applied**: 55
- **Skipped**: 1

## Spec BNF fix

| # | Summary | Rules | Applied |
|---|---------|-------|---------|
| 1 | Double-THEN in `entryTransitionMember` | entryTransitionMember | Yes |
| 2 | Double-THEN in `defaultTargetSuccession` (reserved) | defaultTargetSuccession | No |
| 3 | Make `NOT` optional in `satisfyRequirementUsage` | satisfyRequirementUsage | Yes |
| 4 | Make `STANDARD` optional in `libraryPackage` | libraryPackage | Yes |
| 5 | Make `visibilityIndicator` optional in `importRule` | importRule | Yes |
| 6 | Add `allocationDefinition` to `definitionElement` | definitionElement | Yes |
| 7 | Make `ASSERT` optional before `SATISFY` | satisfyRequirementUsage | Yes |
| 8 | Add `ACTION` keyword support to `sendNode` | sendNode | Yes |
| 9 | Add `returnParameterMember` to `caseBodyItem` | caseBodyItem | Yes |
| 10 | Define missing `calculationUsageDeclaration` | calculationUsageDeclaration | Yes |

### Fix 1: Double-THEN in `entryTransitionMember`

`targetSuccession` expands to `sourceEndMember THEN connectorEndMember` where `sourceEndMember` is empty, producing a double `THEN` keyword. Replaced with `transitionSuccessionMember` which skips the empty source end.

**Affected rules**: entryTransitionMember

### Fix 2: Double-THEN in `defaultTargetSuccession` (reserved)

`defaultTargetSuccession` = `sourceEndMember THEN connectorEndMember`. When used as `THEN defaultTargetSuccession`, it creates a double `THEN`. No-op for now — only applied if tests expose the issue.

**Affected rules**: defaultTargetSuccession

### Fix 3: Make `NOT` optional in `satisfyRequirementUsage`

The KEBNF uses `isNegated ?= 'not'` without explicit `?`, but the `?=` boolean assignment semantically implies optionality.

**Affected rules**: satisfyRequirementUsage

### Fix 4: Make `STANDARD` optional in `libraryPackage`

Same `?=` boolean assignment issue as Fix 3.

**Affected rules**: libraryPackage

### Fix 5: Make `visibilityIndicator` optional in `importRule`

The KEBNF uses `visibility = VisibilityIndicator` without an explicit `( )?` wrapper, unlike `memberPrefix` which uses `( visibility = VisibilityIndicator )?`. In practice, `import Foo::*;` is valid without a visibility prefix.

**Affected rules**: importRule

### Fix 6: Add `allocationDefinition` to `definitionElement`

An omission in the official SysML v2 BNF spec. `AllocationUsage` IS in `StructureUsageElement`, but `AllocationDefinition` was not added to `DefinitionElement`.

**Affected rules**: definitionElement

### Fix 7: Make `ASSERT` optional before `SATISFY`

The OMG reference model (2025-10 release) uses `satisfy` without `assert`. Made optional for backward compatibility with canonical examples.

**Affected rules**: satisfyRequirementUsage

### Fix 8: Add `ACTION` keyword support to `sendNode`

`AcceptNode` uses `ActionNodeUsageDeclaration?` (with `action` keyword) via `AcceptNodeDeclaration`. Apply same pattern to `sendNode`.

**Affected rules**: sendNode

### Fix 9: Add `returnParameterMember` to `caseBodyItem`

The canonical OMG reference model uses `return` inside analysis blocks. Since analysis extends calculation in the SysML metamodel, `returnParameterMember` should be valid in case bodies.

**Affected rules**: caseBodyItem

### Fix 10: Define missing `calculationUsageDeclaration`

Referenced but never defined in the KEBNF spec. Semantically identical to `constraintUsageDeclaration` (`usageDeclaration valuePart?`).

**Affected rules**: calculationUsageDeclaration

## SLL prediction fix

| # | Summary | Rules | Applied |
|---|---------|-------|---------|
| 11 | Merge `qualifiedName \| ownedFeatureChain` alternatives | ownedSubsetting, ownedReferenceSubsetting, ownedCrossSubsetting, ownedRedefinition, ownedFeatureTyping, generalType, specificType, unioning, intersecting, differencing, ownedFeatureInverting, ownedConjugation, ownedDisjoining, featureChainMember, instantiatedTypeMember | Yes |
| 12 | Simplify `flowEnd` after feature chain merge | flowEnd | Yes |
| 22 | Merge expression alternatives in `baseExpression` | baseExpression | Yes |
| 25 | Factor `definitionBodyItem` for SLL prediction | definitionBodyItem, definitionBodyItemContent | Yes |

### Fix 11: Merge `qualifiedName | ownedFeatureChain` alternatives

ANTLR4's SLL prediction mode can't distinguish `qualifiedName` from `ownedFeatureChain` because they share the same prefix. Merged ~15 rules with `qualifiedName | ownedFeatureChain` patterns into `qualifiedName ( DOT qualifiedName )*`. Patterns A–H cover named rules, inline alternatives, and `featureChain` variants.

**Affected rules**: ownedSubsetting, ownedReferenceSubsetting, ownedCrossSubsetting, ownedRedefinition, ownedFeatureTyping, generalType, specificType, unioning, intersecting, differencing, ownedFeatureInverting, ownedConjugation, ownedDisjoining, featureChainMember, instantiatedTypeMember

### Fix 12: Simplify `flowEnd` after feature chain merge

`ownedReferenceSubsetting` now consumes dots greedily (Fix 11), so the explicit `DOT` in `flowEnd` is never reached. Simplified to `qualifiedName ( DOT qualifiedName )*`.

**Affected rules**: flowEnd

### Fix 22: Merge expression alternatives in `baseExpression`

Merged `featureReferenceExpression`, `metadataAccessExpression`, and `invocationExpression` into a single alternative that avoids SLL prediction ambiguity on `qualifiedName` lookahead.

**Affected rules**: baseExpression

### Fix 25: Factor `definitionBodyItem` for SLL prediction

Replaced the 6-alternative `definitionBodyItem` with a factored version. After `memberPrefix` is consumed, the next token (`ALIAS`, `VARIANT`, keyword, or identifier) unambiguously selects the branch, reducing the SLL prediction DFA.

**Affected rules**: definitionBodyItem, definitionBodyItemContent

## Extension compatibility

| # | Summary | Rules | Applied |
|---|---------|-------|---------|
| 13 | Rewrite `identification` to prevent empty match | identification | Yes |
| 14 | Optional `identification` in annotation rules | commentAnnotation, documentation, textualRepresentation | Yes |
| 16 | Optional `identification` in namespace/type/classifier declarations | namespaceDeclaration, typeDeclaration, classifierDeclaration | Yes |
| 17 | Optional `identification` in relationship declarations | subtypeDeclaration, conjugationDeclaration, disjoiningDeclaration, subclassificationDeclaration, featureTypingDeclaration, subsettingDeclaration, redefinitionDeclaration, featuringDeclaration | Yes |
| 18 | Optional `identification` in definitions, packages, and other declarations | definitionDeclaration, packageDeclaration, multiplicitySubset, multiplicityRange, dependencyDeclaration, metadataFeatureDeclaration, metadataUsageDeclaration | Yes |
| 23 | Optional `usageDeclaration` and anonymous usages | usage, usageDeclaration | Yes |
| 24 | Optional `usageDeclaration` in `ownedCrossFeature` | ownedCrossFeature | Yes |
| 26 | Add `endFeatureUsage` rule; reorder `nonOccurrenceUsageElement` | endFeatureUsage (new), nonOccurrenceUsageElement | Yes |
| 27 | Optional `usageDeclaration` in connection/binding/succession | connectionUsage, bindingConnectorAsUsage, successionAsUsage | Yes |
| 28 | Optional `usageDeclaration` in interface/allocation/message | interfaceUsageDeclaration, allocationUsage, messageDeclaration | Yes |
| 29 | Optional `usageDeclaration` in action rules | actionUsageDeclaration, performActionUsageDeclaration | Yes |
| 30 | Optional `usageDeclaration` in control nodes | mergeNode, joinNode, forkNode, decisionNode | Yes |
| 31 | Optional `identification` in payload parameter trigger | triggerUsageDeclaration | Yes |
| 32 | Optional `usageDeclaration` in for-loop variables | forVariableDeclarationMember, forVariableDeclaration | Yes |
| 33 | Optional `usageDeclaration` in state/transition rules | successionDeclaration, exhibitStateUsage, transitionDeclaration | Yes |
| 34 | Optional `usageDeclaration` in constraint/requirement/use case | constraintUsageDeclaration, requirementUsage, useCaseUsage | Yes |
| 35 | Optional `usageDeclaration` in `flowDeclaration`; remove redundant alternative | flowDeclaration | Yes |
| 36 | Simplify `payloadFeature` alternatives | payloadFeature | Yes |
| 37 | Remove redundant `payloadFeatureSpecializationPart` alternative | payloadFeatureSpecializationPart | Yes |

### Fix 13: Rewrite `identification` to prevent empty match

The generator produces `( LT name GT )? ( name )?` which can match the empty string. Rewritten to explicit alternatives that each require at least one component.

**Affected rules**: identification

### Fix 14: Optional `identification` in annotation rules

SysML allows anonymous comments, documentation, and representations. Made `identification` optional in comment, doc, and rep declarations.

**Affected rules**: commentAnnotation, documentation, textualRepresentation

### Fix 16: Optional `identification` in namespace/type/classifier declarations

SysML allows anonymous definitions. Made `identification` optional in `namespaceDeclaration`, `typeDeclaration`, and `classifierDeclaration`.

**Affected rules**: namespaceDeclaration, typeDeclaration, classifierDeclaration

### Fix 17: Optional `identification` in relationship declarations

Made `identification` optional in specialization, conjugation, disjoining, subclassifier, typing, subset, redefinition, and featuring declarations.

**Affected rules**: subtypeDeclaration, conjugationDeclaration, disjoiningDeclaration, subclassificationDeclaration, featureTypingDeclaration, subsettingDeclaration, redefinitionDeclaration, featuringDeclaration

### Fix 18: Optional `identification` in definitions, packages, and other declarations

Made `identification` optional in `definitionDeclaration`, `packageDeclaration`, `multiplicitySubset`, `multiplicityRange`, `dependencyDeclaration`, `metadataFeatureDeclaration`, and `metadataUsageDeclaration`.

**Affected rules**: definitionDeclaration, packageDeclaration, multiplicitySubset, multiplicityRange, dependencyDeclaration, metadataFeatureDeclaration, metadataUsageDeclaration

### Fix 23: Optional `usageDeclaration` and anonymous usages

Anonymous usages are common in SysML (e.g., `part :> Vehicle;`). Made `usageDeclaration` optional in `usage` and added `featureSpecializationPart` as a standalone alternative in `usageDeclaration`.

**Affected rules**: usage, usageDeclaration

### Fix 24: Optional `usageDeclaration` in `ownedCrossFeature`

Made `usageDeclaration` optional in the `basicUsagePrefix` alternative.

**Affected rules**: ownedCrossFeature

### Fix 26: Add `endFeatureUsage` rule; reorder `nonOccurrenceUsageElement`

Handles unnamed end features with specialization in connection/flow/interface definition bodies (e.g., `end :>> QualifiedName;`). Also repositions `defaultReferenceUsage` to end of `nonOccurrenceUsageElement`.

**Affected rules**: endFeatureUsage (new), nonOccurrenceUsageElement

### Fix 27: Optional `usageDeclaration` in connection/binding/succession

Made `usageDeclaration` optional in connection usage, binding connector, and succession as usage declarations.

**Affected rules**: connectionUsage, bindingConnectorAsUsage, successionAsUsage

### Fix 28: Optional `usageDeclaration` in interface/allocation/message

Made `usageDeclaration` optional in `interfaceUsageDeclaration`, allocation declaration, and `messageDeclaration`.

**Affected rules**: interfaceUsageDeclaration, allocationUsage, messageDeclaration

### Fix 29: Optional `usageDeclaration` in action rules

Made `usageDeclaration` optional in `actionUsageDeclaration` and `performActionUsageDeclaration`.

**Affected rules**: actionUsageDeclaration, performActionUsageDeclaration

### Fix 30: Optional `usageDeclaration` in control nodes

Made `usageDeclaration` optional in `mergeNode`, `joinNode`, `forkNode`, and `decisionNode`.

**Affected rules**: mergeNode, joinNode, forkNode, decisionNode

### Fix 31: Optional `identification` in payload parameter trigger

Made `identification` optional for trigger payload parameters.

**Affected rules**: triggerUsageDeclaration

### Fix 32: Optional `usageDeclaration` in for-loop variables

Made `usageDeclaration` optional in `forVariableDeclarationMember` and `forVariableDeclaration`.

**Affected rules**: forVariableDeclarationMember, forVariableDeclaration

### Fix 33: Optional `usageDeclaration` in state/transition rules

Made `usageDeclaration` optional in succession, exhibit state, and transition declarations.

**Affected rules**: successionDeclaration, exhibitStateUsage, transitionDeclaration

### Fix 34: Optional `usageDeclaration` in constraint/requirement/use case

Made `usageDeclaration` optional in `constraintUsageDeclaration`, requirement usage, and use case usage declarations.

**Affected rules**: constraintUsageDeclaration, requirementUsage, useCaseUsage

### Fix 35: Optional `usageDeclaration` in `flowDeclaration`; remove redundant alternative

Made `usageDeclaration` optional and removed the redundant `flowEndMember TO flowEndMember` alternative (already covered by the preceding alternative with optional parts).

**Affected rules**: flowDeclaration

### Fix 36: Simplify `payloadFeature` alternatives

Uses `identification?` consistently and removes redundant alternatives that are subsumed by optional identification.

**Affected rules**: payloadFeature

### Fix 37: Remove redundant `payloadFeatureSpecializationPart` alternative

The third alternative `( featureSpecialization )+` is identical to the first `featureSpecialization+`. Removed the duplicate.

**Affected rules**: payloadFeatureSpecializationPart

## Structural optimization

| # | Summary | Rules | Applied |
|---|---------|-------|---------|
| 15 | Simplify `rootNamespace` to `packageBodyElement* EOF` | rootNamespace | Yes |
| 19 | Simplify `packageBody` alternatives | packageBody | Yes |
| 20 | Restructure `multiplicityPart` ordering keywords | multiplicityPart | Yes |
| 21 | Collapse redundant `resultExpressionMember` alternatives | resultExpressionMember | Yes |

### Fix 15: Simplify `rootNamespace` to `packageBodyElement* EOF`

The `namespaceBodyElement*` alternative is redundant since `packageBodyElement` encompasses all valid top-level elements. `EOF` ensures the parser consumes the entire input.

**Affected rules**: rootNamespace

### Fix 19: Simplify `packageBody` alternatives

Removed the `namespaceBodyElement | elementFilterMember` alternative. The extension uses only `packageBodyElement*` for package bodies.

**Affected rules**: packageBody

### Fix 20: Restructure `multiplicityPart` ordering keywords

Made the ordering keywords (`ORDERED`, `NONUNIQUE`) combinable with `ownedMultiplicity` in a single branch.

**Affected rules**: multiplicityPart

### Fix 21: Collapse redundant `resultExpressionMember` alternatives

The generator produces two alternatives where the second (`memberPrefix?`) subsumes the first (`memberPrefix`). Collapsed to a single alternative.

**Affected rules**: resultExpressionMember

## KerML/SysML merge fix

| # | Summary | Rules | Applied |
|---|---------|-------|---------|
| 18b | Remove bare-bracket alternative from `multiplicityRange` | multiplicityRange | Yes |
| 18c | Remove `multiplicityRange` from `ownedMultiplicity` | ownedMultiplicity | Yes |
| 18d | Merge `typedBy` alternatives | typedBy | Yes |
| 18e | Merge `typings` alternatives | typings | Yes |

### Fix 18b: Remove bare-bracket alternative from `multiplicityRange`

The KerML and SysML specs each define `MultiplicityRange`. The generator merges both into alternatives, but the bare-bracket form duplicates `ownedMultiplicityRange`, creating an ambiguity in `ownedMultiplicity`.

**Affected rules**: multiplicityRange

### Fix 18c: Remove `multiplicityRange` from `ownedMultiplicity`

`multiplicityRange` is a declaration-level rule (starts with `MULTIPLICITY` keyword), not an inline modifier like `ownedMultiplicityRange` (bare `[bounds]`).

**Affected rules**: ownedMultiplicity

### Fix 18d: Merge `typedBy` alternatives

KerML defines `TypedBy` with `(COLON | TYPED BY) ownedFeatureTyping`. SysML overrides with `(COLON | DEFINED BY) featureTyping`. Since `featureTyping` includes `ownedFeatureTyping`, the `COLON` prefix is ambiguous. Merged into one alternative.

**Affected rules**: typedBy

### Fix 18e: Merge `typings` alternatives

Same issue as 18d: `ownedFeatureTyping` vs `featureTyping` in comma-separated list. `featureTyping` is the superset, so use it for both.

**Affected rules**: typings

## ANTLR warning suppression

| # | Summary | Rules | Applied |
|---|---------|-------|---------|
| 38 | Remove redundant `?`/`*` on epsilon-capable sub-rules (warning 154) | featurePrefix, resultExpressionMember, endUsagePrefix, sendNode, returnParameterMember, requirementConstraintMember, framedConcernMember | Yes |

### Fix 38: Remove redundant `?`/`*` on epsilon-capable sub-rules (warning 154)

ANTLR warning(154) fires when an optional block `(…)?` or `(…)*` contains an alternative that can already match the empty string. Removed redundant markers in `featurePrefix`, `resultExpressionMember`, `endUsagePrefix`, `sendNode`, `returnParameterMember`, `requirementConstraintMember`, and `framedConcernMember`.

**Affected rules**: featurePrefix, resultExpressionMember, endUsagePrefix, sendNode, returnParameterMember, requirementConstraintMember, framedConcernMember

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
| 40 | Add `endOccurrenceUsageElement` for `end [mult] port/item/part` | endOccurrenceUsageElement (new), definitionBodyItem, interfaceOccurrenceUsageElement | Yes |
| 41 | Allow bare `NOT SATISFY` without `ASSERT` prefix | satisfyRequirementUsage | Yes |
| 42 | Handle `//*..*/` block comments in `REGULAR_COMMENT` lexer rule | REGULAR_COMMENT (lexer rule, updated) | Yes |
| 43 | Allow optional name and `nonunique` in `endOccurrenceUsageElement` | endOccurrenceUsageElement | Yes |
| 44 | Allow keywords as names in name positions | name, unreservedKeyword (new) | Yes |
| 45 | Reorder `actionNodeMember` before `behaviorUsageMember` in `actionBehaviorMember` | actionBehaviorMember | Yes |
| 46 | Track cascading parse errors in `SysML.sysml` metadata defs | (cascading — no rule change needed) | Yes |
| 47 | Allow `send` without inline payload/receiver in `sendNode` | sendNode | Yes |
| 48 | Allow prefix metadata annotations on enumeration value members | enumerationUsageMember | Yes |
| 49 | Allow `REF` in body parameter declarations for `{in ref ...}` blocks | feature | Yes |
| 50 | Allow `REGULAR_COMMENT` as a no-op expression in `baseExpression` | baseExpression | Yes |
| 51 | Allow `definitionBodyItem` in `functionBodyPart` for body expressions | functionBodyPart | Yes |

### Fix 40: Add `endOccurrenceUsageElement` for `end [mult] port/item/part`

Official SysML v2 training and validation models use `end [1] port p : P`, `end [0..1] item c : C`, and `end port sp : OutPort` inside connection, interface, and flow definition bodies. Added `endOccurrenceUsageElement : END (ownedCrossMultiplicityMember)? occurrenceUsageElement` and referenced it from `definitionBodyItem` and `interfaceOccurrenceUsageElement`.

**Affected rules**: endOccurrenceUsageElement (new), definitionBodyItem, interfaceOccurrenceUsageElement

### Fix 41: Allow bare `NOT SATISFY` without `ASSERT` prefix

The official OMG example `RequirementTest.sysml` uses `not satisfy r1 by p;` without an `assert` prefix. Fix 3 made `NOT` optional inside `ASSERT (NOT)?`, and Fix 7 made `ASSERT` optional, but `( ASSERT ( NOT )? )?` does not allow bare `NOT SATISFY`. Changed to `( ASSERT ( NOT )? | NOT )?`.

**Affected rules**: satisfyRequirementUsage

### Fix 42: Handle `//*..*/` block comments in `REGULAR_COMMENT` lexer rule

Official OMG SysML v2 training/validation files use `//* ... */` to comment out code blocks. Changed `REGULAR_COMMENT` to `'//'? '/*' .*? '*/'` so it also matches the `//` prefix form. ANTLR longest-match ensures `REGULAR_COMMENT` wins over `SINGLE_LINE_NOTE` for single-line `//* ... */`.

**Affected rules**: REGULAR_COMMENT (lexer rule, updated)

### Fix 43: Allow optional name and `nonunique` in `endOccurrenceUsageElement`

Official OMG standard library and examples use `end theCauses [*] occurrence theCause :> causes`, `end inCart[0..1] item cart : ShoppingCart`, and `end [0..*] nonunique item selectedProduct`. Added optional `name` after END and optional `NONUNIQUE` before the occurrence keyword.

**Affected rules**: endOccurrenceUsageElement

### Fix 44: Allow keywords as names in name positions

The OMG standard library uses keywords as identifiers: `attribute type : String` (ImageMetadata), `alias multiplicity for degeneracy` (ISQChemistryMolecular), `attribute <var> ...` (SI), and `subsets step`, `redefines behavior`, `subsets feature`, `redefines function`, `subsets member`, `redefines predicate` (SysML.sysml). Added `unreservedKeyword` alternative to the `name` rule.

**Affected rules**: name, unreservedKeyword (new)

### Fix 45: Reorder `actionNodeMember` before `behaviorUsageMember` in `actionBehaviorMember`

The official ActionTest.sysml uses `action snd send { ... }`. Previously `behaviorUsageMember` (via `actionUsage`) matched `action snd` first and then failed on `send`. Moving `actionNodeMember` before `behaviorUsageMember` in `actionBehaviorMember` lets the parser try the send-node interpretation first.

**Affected rules**: actionBehaviorMember

### Fix 46: Track cascading parse errors in `SysML.sysml` metadata defs

SysML.sysml contains chained `subsets` and `redefines` patterns inside sequential `metadata def` blocks (e.g. `subsets step, usage subsets Metadata::metadataItems`). These fail due to ANTLR error recovery from earlier constructs, not a missing grammar rule. Individual patterns parse correctly. Resolves when all other conformance fixes are applied.

**Affected rules**: (cascading — no rule change needed)

### Fix 47: Allow `send` without inline payload/receiver in `sendNode`

ActionTest.sysml uses `action snd send { in :>> payload = s; }` where the payload is specified inside the body. The `sendNode` rule required either `nodeParameterMember` or `emptyParameterMember senderReceiverPart` after SEND, but the second branch mandated `senderReceiverPart` (VIA/TO). Made it optional.

**Affected rules**: sendNode

### Fix 48: Allow prefix metadata annotations on enumeration value members

MetadataTest.sysml uses `#Security enum secret : ClassificationLevel = 2;` inside an enum def body. The `enumerationUsageMember` rule only allowed `memberPrefix enumeratedValue`, without prefix metadata support. Added `( prefixMetadataMember )*` to allow metadata annotations like `#Security`.

**Affected rules**: enumerationUsageMember

### Fix 49: Allow `REF` in body parameter declarations for `{in ref ...}` blocks

TradeStudies, 7b-Variant Configurations, and 15_05-Unification use `->forAll {in ref w; ...}` and `->selectOne {in ref a { ... } ...}`. The `feature` rule uses `basicFeaturePrefix featureDeclaration` but `basicFeaturePrefix` has no `REF` keyword. Added optional `( REF )?` between `basicFeaturePrefix` and `featureDeclaration`.

**Affected rules**: feature

### Fix 50: Allow `REGULAR_COMMENT` as a no-op expression in `baseExpression`

Analysis Case Usage Example.sysml uses `= ( //* ... */ )` where the entire expression is a commented-out placeholder. After Fix 42 unified `//*` into `REGULAR_COMMENT`, the token appears inside parenthesized expressions. Added `REGULAR_COMMENT` as an alternative in `baseExpression`.

**Affected rules**: baseExpression

### Fix 51: Allow `definitionBodyItem` in `functionBodyPart` for body expressions

VehicleGeometryAndCoordinateFrames.sysml uses `private attribute` inside a `->forAll { ... }` body expression. The `functionBodyPart` rule only allowed `typeBodyElement` which routes through `featureMember` — too limited for usage elements like `attributeUsage` with visibility modifiers. Added `definitionBodyItem` as an alternative.

**Affected rules**: functionBodyPart

## Dead rule removal

| # | Summary | Rules | Applied |
|---|---------|-------|---------|
| 52 | Remove 45 unreachable parser rules | (45 rules removed — see commit for full list) | Yes |

### Fix 52: Remove 45 unreachable parser rules

Removed 45 parser rules unreachable from `rootNamespace`. These include merged rules (Fixes 11/22 left definitions behind), feature chain rules (merged into `qualifiedName ( DOT qualifiedName )*` patterns), and metamodel wrapper passthroughs (e.g., `bodyArgumentMember : bodyArgument`) that exist in the KEBNF for type annotations with no ANTLR4 equivalent. Reduces the grammar by ~9%, resulting in smaller ATN serialization, fewer DFA decisions, shallower parse trees, and fewer generated Context classes.

**Affected rules**: (45 rules removed — see commit for full list)

---

*Auto-generated by `scripts/generate_grammar.py`.*
