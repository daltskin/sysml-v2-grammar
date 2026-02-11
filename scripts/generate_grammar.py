#!/usr/bin/env python3
"""
SysML v2 ANTLR4 Grammar Generator

Downloads official .kebnf BNF files from the SysML-v2-Release repository
and converts them into ANTLR4 .g4 grammar files compatible with antlr4ts.

Usage:
    python generate_grammar.py [--tag TAG] [--output-dir DIR] [--cache]
"""

import json
import os
import sys
import re
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Data structures for the intermediate representation
# ---------------------------------------------------------------------------


@dataclass
class RuleElement:
    """Base class for elements within a grammar rule."""

    pass


@dataclass
class Terminal(RuleElement):
    """A quoted terminal string like 'package'."""

    value: str  # The string without quotes


@dataclass
class NonTerminal(RuleElement):
    """A reference to another rule."""

    name: str


@dataclass
class QualifiedNameRef(RuleElement):
    """A [QualifiedName] cross-reference — becomes a rule ref in ANTLR4."""

    conjugated: bool = False  # True if preceded by ~


@dataclass
class Repetition(RuleElement):
    """A repetition modifier (?, +, *)."""

    child: RuleElement
    modifier: str  # '?', '+', or '*'


@dataclass
class Group(RuleElement):
    """A parenthesized alternation group."""

    alternatives: list  # List of sequences (each sequence is a list of RuleElement)


@dataclass
class Sequence(RuleElement):
    """A sequence of elements."""

    elements: list  # List of RuleElement


@dataclass
class Alternative(RuleElement):
    """An alternation of sequences."""

    sequences: list  # List of Sequence


@dataclass
class GrammarRule:
    """A parsed grammar rule from the .kebnf file."""

    name: str
    parent_type: Optional[str]  # The type after ':', or None
    alternatives: list  # List of lists of RuleElement (each alt is a sequence)
    is_lexical: bool = False  # True for UPPER_CASE rules
    source: str = ""  # 'kerml' or 'sysml'


# ---------------------------------------------------------------------------
# .kebnf Parser (regex-based, not using Lark — more robust for this format)
# ---------------------------------------------------------------------------


class KebnfParser:
    """Parses .kebnf files into GrammarRule objects."""

    def __init__(self):
        self.rules: Dict[str, GrammarRule] = {}
        self.rule_order: List[str] = []

    def parse_file(self, content: str, source: str) -> Dict[str, GrammarRule]:
        """Parse a .kebnf file content into rules."""
        # Normalize line endings
        content = content.replace("\r\n", "\n").replace("\r", "\n")

        # Join continuation lines (lines starting with whitespace)
        lines = content.split("\n")
        joined_lines = []
        for line in lines:
            if line and (line[0] == " " or line[0] == "\t"):
                if joined_lines:
                    joined_lines[-1] += " " + line.strip()
                else:
                    joined_lines.append(line.strip())
            else:
                joined_lines.append(line)

        # Rejoin and split by rule boundaries
        full_text = "\n".join(joined_lines)

        # Extract rules using regex
        # Rules look like: RuleName : Type = body  OR  RuleName = body  OR  LEXICAL_NAME = body
        rule_pattern = re.compile(
            r"^([A-Z][A-Za-z_]+)\s*(?::\s*([A-Z][A-Za-z]+)\s*)?=\s*(.*?)(?=\n[A-Z]|\n//|\Z)",
            re.MULTILINE | re.DOTALL,
        )

        for match in rule_pattern.finditer(full_text):
            name = match.group(1)
            parent_type = match.group(2)
            body = match.group(3).strip()

            is_lexical = bool(re.match(r"^[A-Z][A-Z_]+$", name))

            # Skip rules with empty body or body that is only non-parsing blocks {}.
            # These are semantic-only constructs (e.g., EmptyFeature, EmptyUsage)
            # that would create epsilon alternatives causing ANTLR4 stack overflow.
            stripped_body = re.sub(r"\s+", "", body)
            if not body or stripped_body == "{}":
                continue

            # Parse the body into alternatives
            alternatives = self._parse_alternatives(body)

            if name in self.rules:
                # Merge: some rules are defined in both kerml and sysml,
                # sysml extends kerml rules. Append alternatives.
                existing = self.rules[name]
                existing.alternatives.extend(alternatives)
            else:
                rule = GrammarRule(
                    name=name,
                    parent_type=parent_type,
                    alternatives=alternatives,
                    is_lexical=is_lexical,
                    source=source,
                )
                self.rules[name] = rule
                self.rule_order.append(name)

        return self.rules

    def _parse_alternatives(self, body: str) -> list:
        """Parse a rule body into a list of alternatives (each a list of elements)."""
        # Split by top-level | (not inside parens or quotes)
        alts = self._split_alternatives(body)
        result = []
        for alt in alts:
            elements = self._parse_sequence(alt.strip())
            if elements:
                result.append(elements)
        return result

    def _split_alternatives(self, text: str) -> List[str]:
        """Split text by top-level | characters."""
        parts = []
        current = []
        depth = 0
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == "'":
                # Skip quoted strings
                current.append(ch)
                i += 1
                while i < len(text) and text[i] != "'":
                    if text[i] == "\\":
                        current.append(text[i])
                        i += 1
                    current.append(text[i])
                    i += 1
                if i < len(text):
                    current.append(text[i])
                    i += 1
                continue
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "|" and depth == 0:
                parts.append("".join(current))
                current = []
                i += 1
                continue
            current.append(ch)
            i += 1
        if current:
            parts.append("".join(current))
        return parts

    def _parse_sequence(self, text: str) -> list:
        """Parse a sequence of elements from text."""
        elements = []
        tokens = self._tokenize(text)
        i = 0
        while i < len(tokens):
            tok = tokens[i]

            # Skip property assignments (semantic actions)
            # Pattern: lowercaseProp (=|+=|?=) value
            if (
                i + 2 < len(tokens)
                and tokens[i + 1] in ("=", "+=", "?=")
                and tok[0].islower()
            ):
                # prop = value or prop += value or prop ?= value
                # The value is the next token — keep it if it's a grammar element
                value_tok = tokens[i + 2]
                i += 3  # skip prop, operator, value

                # If value starts a group '(', parse it as a grouped alternation
                # e.g. kind = ( 'at' | 'after' ) → ( AT | AFTER )
                if value_tok == "(":
                    group_tokens, end_i = self._extract_group(tokens, i - 1)
                    group_text = " ".join(group_tokens)
                    group_alts = self._split_alternatives(group_text)
                    group_seqs = []
                    for alt in group_alts:
                        seq = self._parse_sequence(alt.strip())
                        if seq:
                            group_seqs.append(seq)
                    if group_seqs:
                        elem = Group(alternatives=group_seqs)
                        # Check for repetition after group
                        if end_i < len(tokens) and tokens[end_i] in ("?", "+", "*"):
                            elem = Repetition(child=elem, modifier=tokens[end_i])
                            end_i += 1
                        elements.append(elem)
                    i = end_i
                elif value_tok:
                    elem = self._make_element(value_tok)
                    if elem is not None:
                        elements.append(elem)
                continue

            # Skip nonparsing blocks { ... }
            if tok == "{":
                depth = 1
                i += 1
                while i < len(tokens) and depth > 0:
                    if tokens[i] == "{":
                        depth += 1
                    elif tokens[i] == "}":
                        depth -= 1
                    i += 1
                continue

            # Handle parenthesized groups
            if tok == "(":
                group_tokens, end_i = self._extract_group(tokens, i)
                group_text = " ".join(group_tokens)
                group_alts = self._split_alternatives(group_text)
                group_seqs = []
                for alt in group_alts:
                    seq = self._parse_sequence(alt.strip())
                    if seq:
                        group_seqs.append(seq)

                elem = Group(alternatives=group_seqs)

                # Check for repetition after group
                i = end_i
                if i < len(tokens) and tokens[i] in ("?", "+", "*"):
                    elem = Repetition(child=elem, modifier=tokens[i])
                    i += 1
                elements.append(elem)
                continue

            # Make element from token
            elem = self._make_element(tok)
            if elem is not None:
                i += 1
                # Check for repetition
                if i < len(tokens) and tokens[i] in ("?", "+", "*"):
                    elem = Repetition(child=elem, modifier=tokens[i])
                    i += 1
                elements.append(elem)
            else:
                i += 1

        return elements

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize a sequence into meaningful tokens."""
        tokens = []
        i = 0
        text = text.strip()
        while i < len(text):
            # Skip whitespace
            if text[i] in (" ", "\t", "\n"):
                i += 1
                continue

            # Quoted strings
            if text[i] == "'":
                j = i + 1
                while j < len(text):
                    if text[j] == "\\":
                        j += 2
                        continue
                    if text[j] == "'":
                        j += 1
                        break
                    j += 1
                tokens.append(text[i:j])
                i = j
                continue

            # [QualifiedName] cross-references
            if text[i] == "[":
                j = text.index("]", i) + 1
                tokens.append(text[i:j])
                i = j
                continue

            # ~[QualifiedName]
            if text[i] == "~" and i + 1 < len(text) and text[i + 1] == "[":
                j = text.index("]", i) + 1
                tokens.append(text[i:j])
                i = j
                continue

            # Single-char tokens
            if text[i] in ("(", ")", "{", "}", "?", "+", "*", "|"):
                tokens.append(text[i])
                i += 1
                continue

            # Multi-char operators
            if text[i : i + 2] in ("+=", "?="):
                tokens.append(text[i : i + 2])
                i += 2
                continue
            if text[i] == "=":
                tokens.append("=")
                i += 1
                continue

            # Identifiers (rule names, property names)
            if text[i].isalpha() or text[i] == "_":
                j = i
                while j < len(text) and (text[j].isalnum() or text[j] in ("_", ".")):
                    j += 1
                tokens.append(text[i:j])
                i = j
                continue

            # Skip other characters
            i += 1

        return tokens

    def _extract_group(self, tokens: List[str], start: int) -> Tuple[List[str], int]:
        """Extract tokens inside parentheses, return (inner_tokens, next_index)."""
        depth = 1
        i = start + 1  # skip opening (
        inner = []
        while i < len(tokens) and depth > 0:
            if tokens[i] == "(":
                depth += 1
            elif tokens[i] == ")":
                depth -= 1
                if depth == 0:
                    i += 1
                    return (inner, i)
            inner.append(tokens[i])
            i += 1
        return (inner, i)

    def _is_rule_ref(self, tok: str) -> bool:
        """Check if a token is a rule name reference."""
        return bool(re.match(r"^[A-Z]", tok)) and tok not in ("true", "false")

    def _is_terminal(self, tok: str) -> bool:
        """Check if a token is a terminal (quoted string)."""
        return tok.startswith("'") and tok.endswith("'")

    def _make_element(self, tok: str) -> Optional[RuleElement]:
        """Create a RuleElement from a token."""
        if tok.startswith("'") and tok.endswith("'"):
            value = tok[1:-1].replace("\\'", "'")
            return Terminal(value=value)
        elif tok == "[QualifiedName]":
            return QualifiedNameRef(conjugated=False)
        elif tok.startswith("~["):
            return QualifiedNameRef(conjugated=True)
        elif re.match(r"^[A-Z]", tok):
            return NonTerminal(name=tok)
        elif tok in ("true", "false"):
            return Terminal(value=tok)
        return None


# ---------------------------------------------------------------------------
# ANTLR4 Transformer
# ---------------------------------------------------------------------------

# Operator precedence from SysML v2 spec Table 6 (lowest to highest)
OPERATOR_PRECEDENCE = [
    # (operators, name, associativity)
    (["if"], "conditional", "none"),  # Ternary if ? : else
    (["??"], "nullCoalescing", "left"),
    (["implies"], "implies", "left"),
    (["or"], "logicalOr", "left"),
    (["and"], "logicalAnd", "left"),
    (["xor"], "xor", "left"),
    (["|"], "bitwiseOr", "left"),
    (["&"], "bitwiseAnd", "left"),
    (["==", "!=", "===", "!=="], "equality", "left"),
    (["<", ">", "<=", ">="], "relational", "left"),
    ([".."], "range", "left"),
    (["+", "-"], "additive", "left"),
    (["*", "/", "%"], "multiplicative", "left"),
    (["**", "^"], "exponentiation", "right"),
]

UNARY_OPERATORS = ["+", "-", "~", "not"]

CLASSIFICATION_OPERATORS = ["istype", "hastype", "@"]
CAST_OPERATOR = "as"
META_CLASSIFICATION_OPERATORS = ["@@"]
META_CAST_OPERATOR = "meta"

# Primary expression postfix operators
POSTFIX_OPERATORS = [".", ".?", "->", "#", "["]


class Antlr4Transformer:
    """Transforms parsed .kebnf rules into ANTLR4 grammar strings."""

    def __init__(self, rules: Dict[str, GrammarRule], rule_order: List[str]):
        self.rules = rules
        self.rule_order = rule_order
        self.keywords: Set[str] = set()
        self.operators: Set[str] = set()
        self._collect_terminals()

        # Rules to skip (semantic-only, no syntactic content after stripping)
        self.skip_rules: Set[str] = set()

        # Rules that are purely wrappers (single alternative, single ref)
        self.inline_rules: Dict[str, str] = {}

    def _collect_terminals(self):
        """Collect all terminal strings (keywords and operators) from PARSER rules only.

        Lexer rules contain character enumerations (A-Z, 0-9) and descriptive
        text that should NOT be treated as keywords or operators.
        """
        # Collect from parser rules only
        for rule in self.rules.values():
            if rule.is_lexical:
                continue  # Skip lexer rules entirely
            for alt in rule.alternatives:
                self._collect_from_elements(alt)

        # Filter out things that aren't real keywords/operators
        # Remove single characters (from character class refs), descriptive text
        filtered_kw = set()
        for kw in self.keywords:
            # Skip single characters
            if len(kw) <= 1:
                continue
            # Skip descriptive text (contains spaces, too long)
            if " " in kw or len(kw) > 30:
                continue
            # Must be a valid identifier-like keyword
            if re.match(r"^[a-z][a-zA-Z]*$", kw):
                filtered_kw.add(kw)
        self.keywords = filtered_kw

        # Also add keywords from RESERVED_KEYWORD rule if present
        if "RESERVED_KEYWORD" in self.rules:
            for alt in self.rules["RESERVED_KEYWORD"].alternatives:
                for elem in alt:
                    if isinstance(elem, Terminal) and re.match(r"^[a-z]", elem.value):
                        self.keywords.add(elem.value)

        # Extract operators from RESERVED_SYMBOL rule if present
        if "RESERVED_SYMBOL" in self.rules:
            for alt in self.rules["RESERVED_SYMBOL"].alternatives:
                for elem in alt:
                    if isinstance(elem, Terminal) and not re.match(
                        r"^[a-zA-Z]", elem.value
                    ):
                        self.operators.add(elem.value)

    def _collect_from_elements(self, elements: list):
        """Recursively collect terminals from a list of elements."""
        for elem in elements:
            if isinstance(elem, Terminal):
                if re.match(r"^[a-zA-Z]", elem.value):
                    self.keywords.add(elem.value)
                else:
                    self.operators.add(elem.value)
            elif isinstance(elem, Repetition):
                self._collect_from_elements([elem.child])
            elif isinstance(elem, Group):
                for alt in elem.alternatives:
                    self._collect_from_elements(alt)

    def generate_lexer(self) -> str:
        """Generate the ANTLR4 lexer grammar."""
        lines = []
        lines.append("/*")
        lines.append(" * SysML v2.0 ANTLR4 Lexer Grammar")
        lines.append(" * AUTO-GENERATED from official SysML v2 specification BNF")
        lines.append(
            " * Do not edit manually — run: python scripts/grammar/generate_grammar.py"
        )
        lines.append(" */")
        lines.append("")
        lines.append("lexer grammar SysMLv2Lexer;")
        lines.append("")

        # Keywords (sorted alphabetically)
        lines.append("// Keywords")
        sorted_keywords = sorted(self.keywords)
        for kw in sorted_keywords:
            token_name = self._keyword_to_token(kw)
            lines.append(f"{token_name} : '{kw}' ;")
        lines.append("")

        # Multi-character operators (sorted by length desc, then alphabetically)
        lines.append("// Operators and punctuation")
        op_tokens = self._generate_operator_tokens()
        for token_name, pattern in op_tokens:
            escaped = self._escape_antlr(pattern)
            lines.append(f"{token_name} : '{escaped}' ;")
        lines.append("")

        # Identifier
        lines.append("// Identifiers")
        lines.append("IDENTIFIER : [a-zA-Z_] [a-zA-Z0-9_]* ;")
        lines.append("")

        # String literal
        lines.append("// String literals")
        lines.append("STRING : '\\'' ( '\\\\' . | ~['\\\\] )* '\\'' ;")
        lines.append("DOUBLE_STRING : '\"' ( '\\\\' . | ~[\"\\\\] )* '\"' ;")
        lines.append("")

        # Numeric literals
        lines.append("// Numeric literals")
        lines.append("INTEGER : [0-9]+ ;")
        lines.append(
            "REAL : [0-9]* '.' [0-9]+ ( [eE] [+-]? [0-9]+ )? | [0-9]+ [eE] [+-]? [0-9]+ ;"
        )
        lines.append("")

        # Comments and whitespace
        lines.append("// Comments")
        lines.append("REGULAR_COMMENT : '/*' .*? '*/' ;")
        lines.append("SINGLE_LINE_NOTE : '//' ~[\\r\\n]* -> skip ;")
        lines.append("")

        lines.append("// Whitespace")
        lines.append("WS : [ \\t\\r\\n]+ -> skip ;")

        return "\n".join(lines)

    def generate_parser(self) -> str:
        """Generate the ANTLR4 parser grammar."""
        # Identify rules that resolve to empty (body is just {})
        # These are kept as rules but generate /* empty */ alternatives
        self._empty_rules = set()  # Disabled: empty rule removal causes stack overflow
        self._inline_map = {}  # Disabled: inlining causes stack overflow

        lines = []
        lines.append("/*")
        lines.append(" * SysML v2.0 ANTLR4 Parser Grammar")
        lines.append(" * AUTO-GENERATED from official SysML v2 specification BNF")
        lines.append(
            " * Do not edit manually — run: python scripts/grammar/generate_grammar.py"
        )
        lines.append(" */")
        lines.append("")
        lines.append("parser grammar SysMLv2;")
        lines.append("")
        lines.append("options {")
        lines.append("    tokenVocab = SysMLv2Lexer;")
        lines.append("}")
        lines.append("")

        # Generate expression rules with proper precedence
        lines.append("// ===== Expression rules (precedence-climbing) =====")
        lines.append("")
        lines.extend(self._generate_expression_rules())
        lines.append("")

        # Name rule: SysML v2 names can be identifiers or unrestricted (quoted) names
        lines.append("// ===== Name rule (Identifier or UnrestrictedName) =====")
        lines.append("")
        lines.append("name")
        lines.append("    : IDENTIFIER")
        lines.append("    | STRING")
        lines.append("    ;")
        lines.append("")

        # Generate all other parser rules
        lines.append("// ===== Parser rules =====")
        lines.append("")

        expression_rules = self._get_expression_rule_names()

        # Post-process: break mutual left-recursion cycles
        # FilterPackage → ImportDeclaration → NamespaceImport → FilterPackage
        # Fix by making FilterPackage reference non-filter alternatives directly
        self._break_filter_package_recursion()

        # Post-process: inline pass-through rules to reduce grammar depth.
        # Pass-throughs are rules with exactly 1 alternative containing
        # exactly 1 NonTerminal element. They add depth without syntax value
        # and cause ANTLR4's LL1Analyzer to stack-overflow on deep chains.
        inline_map = {}  # self._find_inline_candidates(expression_rules)
        self._inline_map = inline_map  # Store for use in _format_element

        for name in self.rule_order:
            rule = self.rules[name]
            if rule.is_lexical:
                continue  # Lexer rules handled separately
            if name in expression_rules:
                continue  # Expression rules handled above
            if name in self.skip_rules:
                continue
            if name in self._empty_rules:
                continue  # Skip semantically empty rules (body is {})
            # Inlining disabled to avoid stack overflow
            # if name in inline_map:
            #     continue  # Skip pass-through rules (inlined at call sites)

            antlr_name = self._to_parser_rule_name(name)
            rule_text = self._format_rule(rule)
            if rule_text:
                lines.append(f"{antlr_name}")
                lines.append(f"    : {rule_text}")
                lines.append("    ;")
                lines.append("")

        # Collect all referenced rule names and add stubs for undefined ones
        defined_rules = set()
        referenced_rules = set()
        expr_rules = self._get_expression_rule_names()

        # Rules defined by expression generator
        expr_defined = {
            "ownedExpression",
            "typeReference",
            "sequenceExpressionList",
            "baseExpression",
            "nullExpression",
            "featureReferenceExpression",
            "metadataAccessExpression",
            "invocationExpression",
            "constructorExpression",
            "bodyExpression",
            "argumentList",
            "positionalArgumentList",
            "namedArgumentList",
            "namedArgument",
            "literalExpression",
            "literalBoolean",
            "literalString",
            "literalInteger",
            "literalReal",
            "literalInfinity",
            "argumentMember",
            "argumentExpressionMember",
            "name",  # Defined above as IDENTIFIER | STRING
        }
        defined_rules.update(expr_defined)

        for name in self.rule_order:
            rule = self.rules[name]
            if rule.is_lexical:
                continue
            if name in expr_rules or name in self.skip_rules:
                continue
            antlr_name = self._to_parser_rule_name(name)
            rule_text = self._format_rule(rule)
            if rule_text:
                defined_rules.add(antlr_name)
                # Scan for references
                for ref_match in re.finditer(r"\b([a-z][a-zA-Z]+)\b", rule_text):
                    ref = ref_match.group(1)
                    # Skip ANTLR4 keywords and token names
                    if ref not in ("assoc", "right", "left"):
                        referenced_rules.add(ref)

        undefined = referenced_rules - defined_rules
        # Filter out lexer tokens (all caps) and known expression-only rules
        undefined = {
            r
            for r in undefined
            if not r.isupper() and r not in self.keywords and r not in {"empty"}
        }

        if undefined:
            lines.append("")
            lines.append("// ===== Stub rules for undefined references =====")
            lines.append(
                "// These rules are referenced in the spec but not fully defined."
            )
            lines.append("// They need manual review and completion.")
            lines.append("")
            # Known epsilon (empty) rules from the SysML v2 spec
            # These rules match nothing (empty alternative) in the official BNF
            epsilon_rules = {
                "emptyActionUsage",
                "emptyUsage",
                "emptyFeature",
                "emptyMultiplicity",
                "emptyEndMember",
                "portConjugation",  # Conjugated port definition is derived, not user-written
                "emptyParameterMember",  # Empty parameter in transitions
            }
            for rule_name in sorted(undefined):
                lines.append(f"{rule_name}")
                if rule_name in epsilon_rules:
                    lines.append("    : /* epsilon */")
                else:
                    lines.append(f"    : IDENTIFIER  /* TODO: stub for {rule_name} */")
                lines.append("    ;")
                lines.append("")

        result = "\n".join(lines)

        # Apply grammar patches for known BNF issues
        result = self._apply_grammar_patches(result)

        return result

    def _apply_grammar_patches(self, grammar: str) -> str:
        """Apply post-generation patches to fix known BNF spec issues.

        The SysML v2 BNF spec has some patterns that produce redundant keywords
        when flattened into an ANTLR4 grammar. These patches fix them.
        """

        # Fix 1: entryTransitionMember has 'THEN targetSuccession' but
        # targetSuccession = sourceEndMember THEN connectorEndMember, where
        # sourceEndMember is empty. This creates a double-THEN.
        # Fix: Replace 'THEN targetSuccession' with 'THEN transitionSuccessionMember'
        # (transitionSuccessionMember = emptyEndMember connectorEndMember, where
        # emptyEndMember is empty, so it just matches connectorEndMember)
        grammar = grammar.replace(
            "entryTransitionMember\n"
            "    : memberPrefix ( guardedTargetSuccession | THEN targetSuccession ) SEMI",
            "entryTransitionMember\n"
            "    : memberPrefix ( guardedTargetSuccession | THEN transitionSuccessionMember ) SEMI",
        )

        # Fix 2: defaultTargetSuccession has similar double-THEN issue.
        # defaultTargetSuccession = sourceEndMember THEN connectorEndMember
        # When used as 'THEN defaultTargetSuccession' in other rules, it creates
        # double-THEN. Fix: use emptyEndMember before THEN in the rule itself.
        # (No-op for now - only fix if tests expose this)

        # Fix 3: satisfyRequirementUsage has ( NOT ) but NOT should be optional.
        # The KEBNF spec uses ( isNegated ?= 'not' ) without explicit ?, but the
        # ?= boolean assignment semantically implies optionality.
        grammar = grammar.replace("ASSERT ( NOT ) SATISFY", "ASSERT ( NOT )? SATISFY")

        # Fix 4: libraryPackage has ( STANDARD ) but STANDARD should be optional.
        # Same ?= boolean assignment issue.
        grammar = grammar.replace(": ( STANDARD ) LIBRARY", ": ( STANDARD )? LIBRARY")

        # Fix 5: importRule has visibilityIndicator as required, but it should
        # be optional. The KEBNF uses 'visibility = VisibilityIndicator' without
        # explicit ( )? wrapper, unlike memberPrefix which uses
        # '( visibility = VisibilityIndicator )?'. The generator strips the
        # property assignment but doesn't infer optionality from the = operator.
        # In practice, 'import Foo::*;' is valid without a visibility prefix.
        grammar = grammar.replace(
            "importRule\n    : visibilityIndicator IMPORT",
            "importRule\n    : ( visibilityIndicator )? IMPORT",
        )

        # Fix 6: allocationDefinition is defined as a rule but not included in
        # definitionElement. This is an omission in the official SysML v2 BNF
        # spec (2025-12). AllocationUsage IS in StructureUsageElement, but
        # AllocationDefinition was not added to DefinitionElement.
        grammar = grammar.replace(
            "    | metadataDefinition\n    | extendedDefinition",
            "    | metadataDefinition\n"
            "    | allocationDefinition\n"
            "    | extendedDefinition",
        )

        # Fix 7: satisfyRequirementUsage requires 'assert' before 'satisfy' in
        # the 2025-12 BNF, but the official OMG reference model (2025-10 release)
        # uses 'satisfy' without 'assert'. Make 'assert' optional for
        # backward compatibility with canonical examples.
        grammar = grammar.replace(
            "ASSERT ( NOT )? SATISFY", "( ASSERT ( NOT )? )? SATISFY"
        )

        # Fix 8: sendNode uses ActionUsageDeclaration? (no keyword) but the
        # official OMG reference model uses 'action <name> send ...' pattern.
        # AcceptNode uses ActionNodeUsageDeclaration? (with 'action' keyword)
        # via AcceptNodeDeclaration. Apply same pattern to sendNode.
        grammar = grammar.replace(
            "sendNode\n    : occurrenceUsagePrefix actionUsageDeclaration? SEND",
            "sendNode\n"
            "    : occurrenceUsagePrefix ( actionNodeUsageDeclaration | actionUsageDeclaration )? SEND",
        )

        # Fix 9: CaseBody (used by analysis, use case, etc.) does not include
        # ReturnParameterMember in CaseBodyItem, but CalculationBody does.
        # The canonical OMG reference model uses 'return' inside analysis blocks.
        # Since analysis extends calculation in the SysML metamodel, add
        # returnParameterMember to caseBodyItem.
        grammar = grammar.replace(
            "caseBodyItem\n    : actionBodyItem\n    | subjectMember",
            "caseBodyItem\n"
            "    : actionBodyItem\n"
            "    | returnParameterMember\n"
            "    | subjectMember",
        )

        # Fix 10: calculationUsageDeclaration is referenced but never defined in
        # the KEBNF spec. It's semantically identical to constraintUsageDeclaration
        # (= usageDeclaration valuePart?). Replace the stub.
        grammar = grammar.replace(
            "calculationUsageDeclaration\n"
            "    : IDENTIFIER  /* TODO: stub for calculationUsageDeclaration */",
            "calculationUsageDeclaration\n    : usageDeclaration valuePart?",
        )

        # Fix 11: SLL mode ambiguity with qualifiedName | ownedFeatureChain.
        # The SysML KEBNF redefines rules like OwnedSubsetting with
        # [QualifiedName] | OwnedFeatureChain. When merged with KerML's
        # GeneralType, this creates 3-way alternatives:
        #   generalType | qualifiedName | ownedFeatureChain
        # In SLL prediction mode, ANTLR can't distinguish between qualifiedName
        # (matches just 'name') and ownedFeatureChain (starts with qualifiedName
        # then DOT) because they share the same prefix. SLL resolves to the
        # first alternative, consuming just the name and leaving DOT unexpected.
        # Fix: merge these into a single unambiguous production:
        #   qualifiedName ( DOT qualifiedName )*
        # This handles both simple names and dot-separated feature chains.

        # Pattern A: Rules with 'generalType | qualifiedName | ownedFeatureChain'
        for rule_name in [
            "ownedSubsetting",
            "ownedReferenceSubsetting",
            "ownedCrossSubsetting",
            "ownedRedefinition",
            "ownedFeatureTyping",
        ]:
            grammar = grammar.replace(
                f"{rule_name}\n"
                f"    : generalType\n"
                f"    | qualifiedName\n"
                f"    | ownedFeatureChain\n"
                f"    ;",
                f"{rule_name}\n    : qualifiedName ( DOT qualifiedName )*\n    ;",
            )

        # Pattern B: Rules with 'qualifiedName | ownedFeatureChain'
        for rule_name in [
            "generalType",
            "specificType",
            "unioning",
            "intersecting",
            "differencing",
            "ownedFeatureInverting",
        ]:
            grammar = grammar.replace(
                f"{rule_name}\n    : qualifiedName\n    | ownedFeatureChain\n    ;",
                f"{rule_name}\n    : qualifiedName ( DOT qualifiedName )*\n    ;",
            )

        # Pattern C: Rules with 'qualifiedName | featureChain'
        for rule_name in ["ownedConjugation", "ownedDisjoining"]:
            grammar = grammar.replace(
                f"{rule_name}\n    : qualifiedName\n    | featureChain\n    ;",
                f"{rule_name}\n    : qualifiedName ( DOT qualifiedName )*\n    ;",
            )

        # Pattern D: featureChainMember has 3 alternatives that overlap
        grammar = grammar.replace(
            "featureChainMember\n"
            "    : featureReferenceMember\n"
            "    | ownedFeatureChainMember\n"
            "    | qualifiedName\n"
            "    ;",
            "featureChainMember\n    : qualifiedName ( DOT qualifiedName )*\n    ;",
        )

        # Pattern E: instantiatedTypeMember overlaps
        grammar = grammar.replace(
            "instantiatedTypeMember\n"
            "    : instantiatedTypeReference\n"
            "    | ownedFeatureChainMember\n"
            "    ;",
            "instantiatedTypeMember\n    : qualifiedName ( DOT qualifiedName )*\n    ;",
        )

        # Pattern F: Inline ( qualifiedName | featureChain ) in rules
        grammar = grammar.replace(
            "( qualifiedName | featureChain )", "qualifiedName ( DOT qualifiedName )*"
        )

        # Pattern G: Inline ( qualifiedName | ownedFeatureChain ) in rules
        grammar = grammar.replace(
            "( qualifiedName | ownedFeatureChain )",
            "qualifiedName ( DOT qualifiedName )*",
        )

        # Pattern H: chainingDeclaration's ( ownedFeatureChaining | featureChain )
        grammar = grammar.replace(
            "( ownedFeatureChaining | featureChain )",
            "qualifiedName ( DOT qualifiedName )*",
        )

        # Fix 12: flowEnd rule has ( ownedReferenceSubsetting DOT )? which
        # conflicts with Fix 11. ownedReferenceSubsetting now consumes dots
        # greedily, so the explicit DOT is never reached. flowEnd is
        # semantically a feature chain (prefix.flowFeature), so simplify it.
        grammar = grammar.replace(
            "flowEnd\n"
            "    : ( ownedReferenceSubsetting DOT )? flowFeatureMember\n"
            "    | ( flowEndSubsetting )? flowFeatureMember\n"
            "    ;",
            "flowEnd\n    : qualifiedName ( DOT qualifiedName )*\n    ;",
        )

        return grammar

    def _get_expression_rule_names(self) -> Set[str]:
        """Rules handled by the expression precedence generator.

        These are either rewritten into the precedence-climbing ownedExpression
        rule, or emitted as dedicated helper rules in _generate_expression_rules().
        They must be excluded from the main rule generation loop.
        """
        return {
            # Core expression chain (rewritten into ownedExpression)
            "OwnedExpression",
            "ConditionalExpression",
            "ConditionalBinaryOperatorExpression",
            "BinaryOperatorExpression",
            "UnaryOperatorExpression",
            "ClassificationExpression",
            "MetaclassificationExpression",
            "ExtentExpression",
            "ConditionalBinaryOperator",
            "BinaryOperator",
            "UnaryOperator",
            "ClassificationTestOperator",
            "CastOperator",
            "MetaclassificationTestOperator",
            "MetaCastOperator",
            "PrimaryExpression",
            "NonFeatureChainPrimaryExpression",
            "BracketExpression",
            "IndexExpression",
            "SequenceExpression",
            "SelectExpression",
            "CollectExpression",
            "FunctionOperationExpression",
            "FeatureChainExpression",
            # Argument wrapper rules (inlined into expression helpers)
            "ArgumentMember",
            "Argument",
            "ArgumentValue",
            "ArgumentExpressionMember",
            "ArgumentExpression",
            "ArgumentExpressionValue",
            "PrimaryArgumentMember",
            "PrimaryArgument",
            "PrimaryArgumentValue",
            "NonFeatureChainPrimaryArgumentMember",
            "NonFeatureChainPrimaryArgument",
            "NonFeatureChainPrimaryArgumentValue",
            "MetadataArgumentMember",
            "MetadataArgument",
            "MetadataValue",
            "OwnedExpressionReferenceMember",
            "OwnedExpressionReference",
            # Expression helper rules emitted by _generate_expression_rules()
            "TypeReference",
            "SequenceExpressionList",
            "BaseExpression",
            "NullExpression",
            "FeatureReferenceExpression",
            "MetadataAccessExpression",
            "InvocationExpression",
            "ConstructorExpression",
            "BodyExpression",
            "ArgumentList",
            "PositionalArgumentList",
            "NamedArgumentList",
            "NamedArgument",
            "LiteralExpression",
            "LiteralBoolean",
            "LiteralString",
            "LiteralInteger",
            "LiteralReal",
            "LiteralInfinity",
        }

    def _generate_expression_rules(self) -> List[str]:
        """Generate ANTLR4 expression rules with proper precedence.

        This converts the flat .kebnf expression grammar (which uses implicit
        precedence from spec Table 6) into ANTLR4's native left-recursive
        precedence-climbing format.
        """
        lines = []

        # Main expression rule with precedence alternatives
        lines.append("ownedExpression")
        lines.append(
            "    : IF ownedExpression QUESTION ownedExpression ELSE ownedExpression"
        )
        lines.append("    | ownedExpression QUESTION_QUESTION ownedExpression")
        lines.append("    | ownedExpression IMPLIES ownedExpression")
        lines.append("    | ownedExpression OR ownedExpression")
        lines.append("    | ownedExpression AND ownedExpression")
        lines.append("    | ownedExpression XOR ownedExpression")
        lines.append("    | ownedExpression PIPE ownedExpression")
        lines.append("    | ownedExpression AMP ownedExpression")
        lines.append(
            "    | ownedExpression ( EQ_EQ | BANG_EQ | EQ_EQ_EQ | BANG_EQ_EQ ) ownedExpression"
        )
        lines.append("    | ownedExpression ( LT | GT | LE | GE ) ownedExpression")
        lines.append("    | ownedExpression DOT_DOT ownedExpression")
        lines.append("    | ownedExpression ( PLUS | MINUS ) ownedExpression")
        lines.append("    | ownedExpression ( STAR | SLASH | PERCENT ) ownedExpression")
        lines.append(
            "    | <assoc=right> ownedExpression ( STAR_STAR | CARET ) ownedExpression"
        )
        lines.append("    | ( PLUS | MINUS | TILDE | NOT ) ownedExpression")
        lines.append("    | ( AT_SIGN | AT_AT ) typeReference")
        lines.append(
            "    | ownedExpression ( ISTYPE | HASTYPE | AT_SIGN ) typeReference"
        )
        lines.append("    | ownedExpression AS typeReference")
        lines.append("    | ownedExpression AT_AT typeReference")
        lines.append("    | ownedExpression META typeReference")
        lines.append("    | ownedExpression LBRACK sequenceExpressionList? RBRACK")
        lines.append("    | ownedExpression HASH LPAREN sequenceExpressionList? RPAREN")
        lines.append("    | ownedExpression argumentList")
        lines.append("    | ownedExpression DOT qualifiedName")
        lines.append("    | ownedExpression DOT_QUESTION bodyExpression")
        lines.append(
            "    | ownedExpression ARROW qualifiedName ( bodyExpression | argumentList )"
        )
        lines.append("    | ALL typeReference")
        lines.append("    | baseExpression")
        lines.append("    ;")
        lines.append("")

        # Type reference for classification/cast
        lines.append("typeReference")
        lines.append("    : qualifiedName")
        lines.append("    ;")
        lines.append("")

        # Sequence expression (no empty alt — use sequenceExpressionList? at call sites)
        lines.append("sequenceExpressionList")
        lines.append("    : ownedExpression ( COMMA ownedExpression )*")
        lines.append("    ;")
        lines.append("")

        # Base expressions (non-recursive)
        lines.append("baseExpression")
        lines.append("    : nullExpression")
        lines.append("    | literalExpression")
        lines.append("    | featureReferenceExpression")
        lines.append("    | metadataAccessExpression")
        lines.append("    | invocationExpression")
        lines.append("    | constructorExpression")
        lines.append("    | bodyExpression")
        lines.append("    | LPAREN sequenceExpressionList? RPAREN")
        lines.append("    ;")
        lines.append("")

        # Null expression
        lines.append("nullExpression")
        lines.append("    : NULL")
        lines.append("    | LPAREN RPAREN")
        lines.append("    ;")
        lines.append("")

        # Feature reference
        lines.append("featureReferenceExpression")
        lines.append("    : qualifiedName")
        lines.append("    ;")
        lines.append("")

        # Metadata access
        lines.append("metadataAccessExpression")
        lines.append("    : qualifiedName DOT METADATA")
        lines.append("    ;")
        lines.append("")

        # Invocation
        lines.append("invocationExpression")
        lines.append("    : qualifiedName argumentList")
        lines.append("    ;")
        lines.append("")

        # Constructor
        lines.append("constructorExpression")
        lines.append("    : NEW qualifiedName argumentList")
        lines.append("    ;")
        lines.append("")

        # Body expression
        lines.append("bodyExpression")
        lines.append("    : LBRACE functionBodyPart RBRACE")
        lines.append("    ;")
        lines.append("")

        # Argument list
        lines.append("argumentList")
        lines.append(
            "    : LPAREN ( positionalArgumentList | namedArgumentList )? RPAREN"
        )
        lines.append("    ;")
        lines.append("")

        lines.append("positionalArgumentList")
        lines.append("    : ownedExpression ( COMMA ownedExpression )*")
        lines.append("    ;")
        lines.append("")

        lines.append("namedArgumentList")
        lines.append("    : namedArgument ( COMMA namedArgument )*")
        lines.append("    ;")
        lines.append("")

        lines.append("namedArgument")
        lines.append("    : qualifiedName EQ ownedExpression")
        lines.append("    ;")
        lines.append("")

        # Literal expressions
        lines.append("literalExpression")
        lines.append("    : literalBoolean")
        lines.append("    | literalString")
        lines.append("    | literalInteger")
        lines.append("    | literalReal")
        lines.append("    | literalInfinity")
        lines.append("    ;")
        lines.append("")

        lines.append("literalBoolean : TRUE | FALSE ;")
        lines.append("literalString : DOUBLE_STRING ;")
        lines.append("literalInteger : INTEGER ;")
        lines.append("literalReal : REAL ;")
        lines.append("literalInfinity : STAR ;")
        lines.append("")

        # Argument wrapper rules — these are semantic wrapper chains in the
        # KEBNF that all ultimately resolve to an OwnedExpression:
        #   ArgumentMember → Argument → ArgumentValue → OwnedExpression
        #   ArgumentExpressionMember → ArgumentExpression → ArgumentExpressionValue
        #     → OwnedExpressionReference → OwnedExpressionMember → OwnedExpression
        lines.append("argumentMember")
        lines.append("    : ownedExpression")
        lines.append("    ;")
        lines.append("")
        lines.append("argumentExpressionMember")
        lines.append("    : ownedExpression")
        lines.append("    ;")
        lines.append("")

        return lines

    def _break_filter_package_recursion(self):
        """Break the mutual left-recursion cycle:
        FilterPackage → ImportDeclaration → NamespaceImport → FilterPackage.

        Solution: Replace FilterPackage's first alternative
        (ImportDeclaration (FilterPackageMember)+) with inlined non-recursive
        alternatives: (membershipImport | namespaceImportNonFilter) (filterPackageMember)+
        where namespaceImportNonFilter = qualifiedName '::' '*' ('::' '**')?
        """
        if "FilterPackage" not in self.rules:
            return

        rule = self.rules["FilterPackage"]
        new_alts = []
        for alt in rule.alternatives:
            # Check if this alt starts with ImportDeclaration or an import reference
            has_import_ref = any(
                isinstance(e, NonTerminal) and e.name == "ImportDeclaration"
                for e in alt
            )
            if has_import_ref:
                # Replace ImportDeclaration with non-recursive inline:
                # ( membershipImport | namespaceImportDirect ) instead
                new_elements = []
                for e in alt:
                    if isinstance(e, NonTerminal) and e.name == "ImportDeclaration":
                        # Inline: (MembershipImport | NamespaceImportDirect)
                        # where NamespaceImportDirect is the non-FilterPackage alt of NamespaceImport
                        new_elements.append(
                            NonTerminal(name="FilterPackageImportDeclaration")
                        )
                    else:
                        new_elements.append(e)
                new_alts.append(new_elements)
            else:
                new_alts.append(alt)
        rule.alternatives = new_alts

        # Create the helper rule FilterPackageImportDeclaration
        # which is ImportDeclaration minus the FilterPackage path
        helper = GrammarRule(
            name="FilterPackageImportDeclaration",
            parent_type=None,
            alternatives=[
                [NonTerminal(name="MembershipImport")],
                [NonTerminal(name="NamespaceImportDirect")],
            ],
            is_lexical=False,
            source="generated",
        )
        self.rules["FilterPackageImportDeclaration"] = helper
        self.rule_order.append("FilterPackageImportDeclaration")

        # Create NamespaceImportDirect: the non-FilterPackage alternatives
        # from NamespaceImport
        if "NamespaceImport" in self.rules:
            ns_rule = self.rules["NamespaceImport"]
            direct_alts = []
            for alt in ns_rule.alternatives:
                # Skip alternatives that reference FilterPackage
                has_filter = any(
                    isinstance(e, NonTerminal) and e.name == "FilterPackage"
                    for e in alt
                )
                if not has_filter:
                    direct_alts.append(alt)

            if direct_alts:
                direct_rule = GrammarRule(
                    name="NamespaceImportDirect",
                    parent_type=None,
                    alternatives=direct_alts,
                    is_lexical=False,
                    source="generated",
                )
                self.rules["NamespaceImportDirect"] = direct_rule
                self.rule_order.append("NamespaceImportDirect")
            else:
                # Fallback: all NamespaceImport alts use FilterPackage,
                # just create MembershipImport as the only option
                pass

    def _find_inline_candidates(self, expression_rules: Set[str]) -> Dict[str, str]:
        """Find pass-through rules that can be inlined to reduce grammar depth.

        A pass-through rule is one with exactly 1 alternative containing
        exactly 1 NonTerminal element. For example:
            usageBody = DefinitionBody  ->  replace usageBody refs with definitionBody

        Returns a dict mapping PascalCase source rule name to PascalCase target rule name.
        Resolves transitive chains: A → B → C becomes A → C.
        """
        inline_map: Dict[str, str] = {}

        for name, rule in self.rules.items():
            if rule.is_lexical:
                continue
            if name in expression_rules:
                continue
            if name in self._empty_rules:
                continue
            if name in self.skip_rules:
                continue

            # Check if this is a pass-through: 1 alternative, 1 element
            if len(rule.alternatives) == 1:
                alt = rule.alternatives[0]
                if len(alt) == 1:
                    elem = alt[0]
                    if isinstance(elem, NonTerminal):
                        inline_map[name] = elem.name
                    elif isinstance(elem, QualifiedNameRef):
                        inline_map[name] = "QualifiedName"

        # Resolve transitive chains
        changed = True
        max_iter = 20
        while changed and max_iter > 0:
            changed = False
            max_iter -= 1
            for src, target in list(inline_map.items()):
                if target in inline_map:
                    inline_map[src] = inline_map[target]
                    changed = True

        # Don't inline rules that would create a self-reference
        for src, target in list(inline_map.items()):
            if src == target:
                del inline_map[src]

        return inline_map

    def _find_empty_rules(self) -> Set[str]:
        """Find rules that resolve to empty (body is just {} in the spec).

        These are semantic-only constructs (EmptyFeature, EmptyUsage, etc.)
        that create AST nodes but consume no input tokens. In ANTLR4, epsilon
        alternatives cause expensive lookahead and potential stack overflows.

        Returns set of PascalCase rule names that should be treated as empty.
        """
        empty = set()
        for name, rule in self.rules.items():
            if rule.is_lexical:
                continue
            # A rule is "empty" if all its alternatives are empty sequences
            if all(len(alt) == 0 for alt in rule.alternatives):
                empty.add(name)

        # Transitively: a rule that only references empty rules is also empty
        changed = True
        while changed:
            changed = False
            for name, rule in self.rules.items():
                if name in empty or rule.is_lexical:
                    continue
                is_empty = True
                for alt in rule.alternatives:
                    if len(alt) == 0:
                        continue  # Empty alt
                    # Check if all elements in this alt resolve to empty rules
                    for elem in alt:
                        if isinstance(elem, NonTerminal) and elem.name in empty:
                            continue  # References an empty rule
                        is_empty = False
                        break
                    if not is_empty:
                        break
                if is_empty and rule.alternatives:
                    empty.add(name)
                    changed = True

        return empty

    def _format_rule(self, rule: GrammarRule) -> str:
        """Format a rule's alternatives as ANTLR4 text."""
        alt_texts = []
        seen = set()
        for alt in rule.alternatives:
            text = self._format_sequence(alt)
            if text and text not in seen:
                alt_texts.append(text)
                seen.add(text)
            elif not text and not alt:  # Intentionally empty alternative
                if "/* empty */" not in seen:
                    alt_texts.append("/* empty */")
                    seen.add("/* empty */")

        if not alt_texts:
            return ""

        return "\n    | ".join(alt_texts)

    def _format_sequence(self, elements: list) -> str:
        """Format a sequence of elements as ANTLR4 text."""
        parts = []
        for elem in elements:
            text = self._format_element(elem)
            if text:
                parts.append(text)
        return " ".join(parts)

    def _format_element(self, elem: RuleElement) -> str:
        """Format a single element as ANTLR4 text."""
        if isinstance(elem, Terminal):
            return self._terminal_to_token(elem.value)
        elif isinstance(elem, NonTerminal):
            # Check if this is a lexer rule reference (ALL_CAPS or MIXED_CAPS)
            if self._is_lexer_rule_name(elem.name):
                return self._lexer_rule_to_token(elem.name)
            # Check if this references a semantically empty rule
            if hasattr(self, "_empty_rules") and elem.name in self._empty_rules:
                return ""  # Drop reference to empty rule
            # Apply pass-through inlining
            name = elem.name
            if hasattr(self, "_inline_map") and name in self._inline_map:
                name = self._inline_map[name]
            return self._to_parser_rule_name(name)
        elif isinstance(elem, QualifiedNameRef):
            return "qualifiedName"
        elif isinstance(elem, Repetition):
            inner = self._format_element(elem.child)
            if not inner:
                return ""
            if isinstance(elem.child, Group):
                return f"{inner}{elem.modifier}"
            return f"{inner}{elem.modifier}"
        elif isinstance(elem, Group):
            alt_texts = []
            for alt in elem.alternatives:
                text = self._format_sequence(alt)
                if text:
                    alt_texts.append(text)
            if len(alt_texts) == 1:
                return f"( {alt_texts[0]} )"
            return "( " + " | ".join(alt_texts) + " )"
        return ""

    def _is_lexer_rule_name(self, name: str) -> bool:
        """Check if a name is a lexer rule (ALL_CAPS or MIXED_CAPS pattern).

        Examples: NAME, STRING_VALUE, TYPED_BY, SPECIALIZES, DECIMAL_VALUE
        """
        # If it's in the rules dict and marked as lexical
        if name in self.rules and self.rules[name].is_lexical:
            return True
        # If the name matches ALL_CAPS pattern (with underscores allowed)
        if re.match(r"^[A-Z][A-Z_0-9]+$", name):
            return True
        return False

    def _lexer_rule_to_token(self, name: str) -> str:
        """Map a .kebnf lexer rule name to its ANTLR4 token equivalent.

        Some lexer rules like NAME, STRING_VALUE, DECIMAL_VALUE map to
        our lexer tokens IDENTIFIER, DOUBLE_STRING, INTEGER, etc.
        """
        # Map compound/alias lexer rules to actual tokens
        lexer_token_map = {
            "NAME": "name",
            "STRING_VALUE": "DOUBLE_STRING",
            "DECIMAL_VALUE": "INTEGER",
            "EXPONENTIAL_VALUE": "REAL",
            "REGULAR_COMMENT": "REGULAR_COMMENT",
            # Compound tokens: symbol OR keyword alternatives
            "TYPED_BY": "( COLON | TYPED BY )",
            "DEFINED_BY": "( COLON | DEFINED BY )",
            "SPECIALIZES": "( COLON_GT | SPECIALIZES )",
            "SUBSETS": "( COLON_GT | SUBSETS )",
            "REFERENCES": "( COLON_COLON_GT | REFERENCES )",
            "CROSSES": "( FAT_ARROW | CROSSES )",
            "REDEFINES": "( COLON_GT_GT | REDEFINES )",
            "CONJUGATES": "( TILDE | CONJUGATES )",
        }
        if name in lexer_token_map:
            return lexer_token_map[name]
        # Default: use as-is (might be a fragment or other token)
        return name

    def _to_parser_rule_name(self, name: str) -> str:
        """Convert PascalCase .kebnf rule name to camelCase ANTLR4 parser rule name."""
        if not name:
            return name
        # Special cases
        if name == "QualifiedName":
            return "qualifiedName"
        result = name[0].lower() + name[1:]
        # ANTLR4 reserved words that can't be used as rule names
        antlr_reserved = {
            "import",
            "fragment",
            "lexer",
            "parser",
            "grammar",
            "returns",
            "locals",
            "throws",
            "catch",
            "finally",
            "mode",
            "options",
            "tokens",
            "channels",
        }
        if result in antlr_reserved:
            result = result + "Rule"
        return result

    def _keyword_to_token(self, keyword: str) -> str:
        """Convert a keyword string to its ANTLR4 token name."""
        return keyword.upper().replace(" ", "_")

    def _terminal_to_token(self, value: str) -> str:
        """Convert a terminal value to its ANTLR4 token reference."""
        if re.match(r"^[a-zA-Z]", value):
            return value.upper().replace(" ", "_")
        # Operator tokens — names must not collide with keyword tokens
        token_map = {
            ":": "COLON",
            "::": "COLON_COLON",
            ":>": "COLON_GT",
            ":>>": "COLON_GT_GT",
            "::>": "COLON_COLON_GT",
            ":=": "COLON_EQ",
            ";": "SEMI",
            ",": "COMMA",
            ".": "DOT",
            "..": "DOT_DOT",
            ".?": "DOT_QUESTION",
            "(": "LPAREN",
            ")": "RPAREN",
            "{": "LBRACE",
            "}": "RBRACE",
            "[": "LBRACK",
            "]": "RBRACK",
            "<": "LT",
            ">": "GT",
            "<=": "LE",
            ">=": "GE",
            "=": "EQ",
            "==": "EQ_EQ",
            "!=": "BANG_EQ",
            "===": "EQ_EQ_EQ",
            "!==": "BANG_EQ_EQ",
            "+": "PLUS",
            "-": "MINUS",
            "*": "STAR",
            "/": "SLASH",
            "%": "PERCENT",
            "^": "CARET",
            "**": "STAR_STAR",
            "~": "TILDE",
            "#": "HASH",
            "$": "DOLLAR",
            "|": "PIPE",
            "&": "AMP",
            "->": "ARROW",
            "=>": "FAT_ARROW",
            "?": "QUESTION",
            "??": "QUESTION_QUESTION",
            "@": "AT_SIGN",
            "@@": "AT_AT",
        }
        return token_map.get(value, f"'{self._escape_antlr(value)}'")

    def _generate_operator_tokens(self) -> List[Tuple[str, str]]:
        """Generate token definitions for operators, sorted longest first."""
        token_map = {
            ":>>": "COLON_GT_GT",
            "::>": "COLON_COLON_GT",
            "===": "EQ_EQ_EQ",
            "!==": "BANG_EQ_EQ",
            "**": "STAR_STAR",
            "??": "QUESTION_QUESTION",
            "::": "COLON_COLON",
            ":>": "COLON_GT",
            ":=": "COLON_EQ",
            "..": "DOT_DOT",
            ".?": "DOT_QUESTION",
            "->": "ARROW",
            "=>": "FAT_ARROW",
            "==": "EQ_EQ",
            "!=": "BANG_EQ",
            "<=": "LE",
            ">=": "GE",
            "@@": "AT_AT",
            ":": "COLON",
            ";": "SEMI",
            ",": "COMMA",
            ".": "DOT",
            "(": "LPAREN",
            ")": "RPAREN",
            "{": "LBRACE",
            "}": "RBRACE",
            "[": "LBRACK",
            "]": "RBRACK",
            "<": "LT",
            ">": "GT",
            "=": "EQ",
            "+": "PLUS",
            "-": "MINUS",
            "*": "STAR",
            "/": "SLASH",
            "%": "PERCENT",
            "^": "CARET",
            "~": "TILDE",
            "#": "HASH",
            "$": "DOLLAR",
            "|": "PIPE",
            "&": "AMP",
            "?": "QUESTION",
            "@": "AT_SIGN",
        }
        # Sort by length descending (ANTLR4 needs longest match first)
        items = sorted(token_map.items(), key=lambda x: (-len(x[0]), x[0]))
        return [(v, k) for k, v in items]

    def _escape_antlr(self, s: str) -> str:
        """Escape a string for ANTLR4."""
        return s.replace("\\", "\\\\").replace("'", "\\'")


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def download_bnf(config: dict, cache_dir: Optional[str] = None) -> Tuple[str, str]:
    """Download .kebnf files from GitHub. Returns (kerml_content, sysml_content)."""
    import requests

    tag = config["release_tag"]
    repo = config["release_repo"]

    results = {}
    for key, path in config["bnf_files"].items():
        url = f"https://raw.githubusercontent.com/{repo}/{tag}/{path}"

        # Check cache first
        if cache_dir:
            cache_path = Path(cache_dir) / f"{key}-{tag}.kebnf"
            if cache_path.exists():
                print(f"  Using cached {key} from {cache_path}")
                results[key] = cache_path.read_text()
                continue

        print(f"  Downloading {key} from {url}...")
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        content = resp.text

        if cache_dir:
            cache_path = Path(cache_dir) / f"{key}-{tag}.kebnf"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(content)

        results[key] = content

    return results["kerml"], results["sysml"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser_arg = argparse.ArgumentParser(
        description="Generate ANTLR4 grammar from SysML v2 BNF"
    )
    parser_arg.add_argument("--tag", help="Release tag (e.g., 2025-12)")
    parser_arg.add_argument(
        "--output-dir", help="Output directory for .g4 files", default=None
    )
    parser_arg.add_argument(
        "--cache", action="store_true", help="Cache downloaded files"
    )
    parser_arg.add_argument(
        "--config",
        help="Path to config.json",
        default=os.path.join(os.path.dirname(__file__), "config.json"),
    )
    args = parser_arg.parse_args()

    # Load config
    config_path = Path(args.config)
    with open(config_path) as f:
        config = json.load(f)

    if args.tag:
        config["release_tag"] = args.tag

    # Validate release tag to prevent path traversal and URL injection
    tag = config["release_tag"]
    if not re.match(r"^[a-zA-Z0-9._-]+$", tag):
        print(f"Error: invalid release tag: {tag!r}", file=sys.stderr)
        print(
            "Tags must contain only alphanumeric characters, dots, hyphens, and underscores.",
            file=sys.stderr,
        )
        sys.exit(1)
    config["release_tag"] = tag

    # Determine paths – config.json lives at scripts/config.json,
    # so project_root is one level up from scripts/.
    project_root = config_path.parent.parent
    output_dir = Path(args.output_dir) if args.output_dir else project_root / "grammar"
    cache_dir = project_root / ".grammar-cache" if args.cache else None

    print("SysML v2 ANTLR4 Grammar Generator")
    print(f"  Release tag: {config['release_tag']}")
    print(f"  Output dir:  {output_dir}")
    print()

    # Step 1: Download
    print("Step 1: Downloading .kebnf files...")
    kerml_content, sysml_content = download_bnf(config, cache_dir)
    print(f"  KerML: {len(kerml_content)} bytes")
    print(f"  SysML: {len(sysml_content)} bytes")
    print()

    # Step 2: Parse
    print("Step 2: Parsing .kebnf files...")
    kebnf_parser = KebnfParser()
    kebnf_parser.parse_file(kerml_content, "kerml")
    kebnf_parser.parse_file(sysml_content, "sysml")
    print(f"  Total rules: {len(kebnf_parser.rules)}")
    print(
        f"  Lexical rules: {sum(1 for r in kebnf_parser.rules.values() if r.is_lexical)}"
    )
    print(
        f"  Parser rules: {sum(1 for r in kebnf_parser.rules.values() if not r.is_lexical)}"
    )
    print()

    # Step 3: Transform
    print("Step 3: Transforming to ANTLR4...")
    transformer = Antlr4Transformer(kebnf_parser.rules, kebnf_parser.rule_order)
    print(f"  Keywords found: {len(transformer.keywords)}")
    print(f"  Operators found: {len(transformer.operators)}")
    print()

    # Step 4: Generate
    print("Step 4: Generating .g4 files...")
    output_dir.mkdir(parents=True, exist_ok=True)

    lexer_grammar = transformer.generate_lexer()
    parser_grammar = transformer.generate_parser()

    lexer_path = output_dir / config["output"]["lexer_grammar"].split("/")[-1]
    parser_path = output_dir / config["output"]["parser_grammar"].split("/")[-1]

    lexer_path.write_text(lexer_grammar)
    parser_path.write_text(parser_grammar)

    print(f"  Lexer:  {lexer_path} ({len(lexer_grammar)} bytes)")
    print(f"  Parser: {parser_path} ({len(parser_grammar)} bytes)")
    print()
    print("Done! Grammar files written to the grammar/ directory.")


if __name__ == "__main__":
    main()
