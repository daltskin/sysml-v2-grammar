#!/usr/bin/env python3
"""
SysML v2 and KerML ANTLR4 Grammar Generator

Downloads official .kebnf BNF files from the SysML-v2-Release repository
and converts them into ANTLR4 .g4 grammar files compatible with antlr4ts:
the SysML grammar from the KerML and SysML KEBNF, and the KerML grammar from
the KerML KEBNF alone.

The generic part (KEBNF parser, ANTLR4 transformer, patch mechanism) knows no
language. Each language is a GrammarLanguage, in its own section below: the
KerML section (expressions, rule transforms, the patches that fix KerML
productions) refers to nothing of SysML; the SysML section adds its own
patches and transforms, and applies the KerML ones, as the SysML grammar
contains the KerML productions.

Usage:
    python generate_grammar.py [--tag TAG] [--language sysml|kerml] [--output-dir DIR] [--cache]
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

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
    source: str = ""  # the label of the .kebnf file it comes from


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
                # Merge: a rule defined again in a later file extends the
                # earlier definition. Append alternatives.
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
# Languages
# ---------------------------------------------------------------------------


@dataclass
class GrammarLanguage:
    """What a language's grammar adds to the generation: names, rules, transforms and patches."""

    title: str
    lexer_name: str
    parser_name: str
    # The script that generates it, named in the patch documentation.
    generator: str
    # The precedence-climbing expression rules, and the rules they replace.
    expression_rules: Callable[["Antlr4Transformer"], List[str]]
    expression_rule_names: Callable[["Antlr4Transformer"], Set[str]]
    # Undefined rules that are empty in the KEBNF.
    epsilon_rules: Set[str]
    # The post-generation patches, patch-file entries in the order they are applied.
    patches: List[dict]
    # Rewrites of the parsed rules before they are generated.
    rule_transforms: List[Callable[["Antlr4Transformer"], None]] = field(
        default_factory=list
    )
    # The lexer rules of notes and comments, as lines of the lexer grammar.
    comment_rules: List[str] = field(default_factory=list)
    # Sections of the patch documentation, before the patches.
    patch_doc_sections: List[str] = field(default_factory=list)


def rule_bodies(grammar: str) -> Dict[str, str]:
    """The parser rules of `grammar`, by name in grammar order, each with its body text."""
    return {
        match.group(1): match.group(2)
        for match in re.finditer(
            r"^([a-z]\w*)\n    :(.*?)\n    ;$", grammar, flags=re.DOTALL | re.MULTILINE
        )
    }


def rule_references(body: str) -> Set[str]:
    """The rule names a rule body refers to, leaving out the words of its comments."""
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.DOTALL)
    body = re.sub(r"//[^\n]*", " ", body)
    body = re.sub(r"'(?:\\.|[^'\\])*'", " ", body)
    return set(re.findall(r"\b([a-z]\w*)\b", body))


def unreachable_rules(grammar: str) -> List[str]:
    """The parser rules of `grammar` not reachable from `rootNamespace`, in grammar order."""
    bodies = rule_bodies(grammar)
    reachable: Set[str] = set()
    queue = ["rootNamespace"]
    while queue:
        name = queue.pop()
        if name in reachable or name not in bodies:
            continue
        reachable.add(name)
        queue.extend(ref for ref in rule_references(bodies[name]) if ref in bodies)
    return [name for name in bodies if name not in reachable]


def changed_rules(before: str, after: str) -> List[str]:
    """The parser rules of `after` that a change from `before` added or rewrote, in grammar order."""
    old, new = rule_bodies(before), rule_bodies(after)
    return [name for name, body in new.items() if old.get(name) != body]


def select_patches(patch_file: Dict[str, dict], keys: List[str]) -> List[dict]:
    """The entries of a patch file for `keys`, in that order, each with its fix number."""
    unknown = [key for key in keys if key not in patch_file]
    if unknown:
        raise KeyError(f"patches not in the patch file: {', '.join(unknown)}")
    return [{"id": key, **patch_file[key]} for key in keys]


def language_patches(patch_file: Dict[str, dict], language: str) -> List[dict]:
    """The entries of a patch file whose `language` list names `language`, in file order.

    The file order is the order the patches are applied in. An entry without a
    `language` list is an error, so no patch is left out unnoticed.
    """
    missing = [key for key, fix in patch_file.items() if not fix.get("language")]
    if missing:
        raise KeyError(f"patches without a language list: {', '.join(missing)}")
    return select_patches(
        patch_file,
        [key for key, fix in patch_file.items() if language in fix["language"]],
    )


def apply_patch(grammar: str, fix: dict) -> Tuple[str, Dict[str, object]]:
    """Apply one patch-file entry: the patched grammar, and its record for the documentation.

    An entry replaces text (`replace`, optionally by regex), removes the rules
    unreachable from `rootNamespace` (`remove_unreachable_rules`) or only
    documents a change made elsewhere (`applied`). `{count}` in its texts is
    the number of rules removed.
    """
    prev = grammar
    for item in fix.get("replace", []):
        if item.get("regex"):
            matches = len(re.findall(item["old"], grammar))
        else:
            matches = grammar.count(item["old"])
        if "expect_once" in fix and matches != 1:
            raise ValueError(fix["expect_once"])
        if item.get("regex"):
            grammar = re.sub(item["old"], item["new"], grammar)
        else:
            grammar = grammar.replace(item["old"], item["new"])

    removed: List[str] = []
    if fix.get("remove_unreachable_rules"):
        removed = unreachable_rules(grammar)
        for rule_name in removed:
            grammar = re.sub(
                r"\n" + rule_name + r"\n    :.*?\n    ;\n",
                "\n",
                grammar,
                flags=re.DOTALL,
            )
        # Collapse runs of 3+ blank lines left by removals
        grammar = re.sub(r"\n{3,}", "\n\n", grammar)

    def text(key: str) -> str:
        return str(fix.get(key, "")).replace("{count}", str(len(removed)))

    if fix.get("replace"):
        # The rules of this grammar the replacements changed: none if skipped.
        changed = changed_rules(prev, grammar)
        rules = ", ".join(changed)
        applied = grammar != prev
    else:
        rules = text("rules")
        applied = fix.get("applied", grammar != prev)
    return grammar, {
        "id": fix["id"],
        "category": fix["category"],
        "summary": text("summary"),
        "description": text("description"),
        "rules": rules,
        "applied": applied,
    }


# ---------------------------------------------------------------------------
# ANTLR4 Transformer
# ---------------------------------------------------------------------------


# Primary expression postfix operators
POSTFIX_OPERATORS = [".", ".?", "->", "#", "["]


class Antlr4Transformer:
    """Transforms parsed .kebnf rules into ANTLR4 grammar strings."""

    def __init__(
        self,
        rules: Dict[str, GrammarRule],
        rule_order: List[str],
        language: GrammarLanguage,
    ):
        self.rules = rules
        self.rule_order = rule_order
        self.language = language
        self.title = language.title
        self.lexer_name = language.lexer_name
        self.parser_name = language.parser_name
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
        lines.append(f" * {self.title} ANTLR4 Grammar")
        lines.append(
            f" * Derived from the OMG {self.title} specification (KEBNF format)."
        )
        lines.append(" * Source: https://github.com/Systems-Modeling/SysML-v2-Release")
        lines.append(" * Generator: https://github.com/daltskin/sysml-v2-grammar")
        lines.append(" * License: MIT")
        lines.append(" */")
        lines.append("")
        lines.append(f"lexer grammar {self.lexer_name};")
        lines.append("")
        # antlr-format configuration (required by grammars-v4 CI)
        lines.append(
            "// $antlr-format alignTrailingComments true, columnLimit 150, useTab false"
        )
        lines.append(
            "// $antlr-format allowShortRulesOnASingleLine false, allowShortBlocksOnASingleLine true"
        )
        lines.append("// $antlr-format alignSemicolons hanging, alignColons hanging")
        lines.append(
            "// $antlr-format minEmptyLines 1, maxEmptyLinesToKeep 1, reflowComments false"
        )
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

        # Notes and comments, by the language
        lines.extend(self.language.comment_rules)
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
        lines.append(f" * {self.title} ANTLR4 Grammar")
        lines.append(
            f" * Derived from the OMG {self.title} specification (KEBNF format)."
        )
        lines.append(" * Source: https://github.com/Systems-Modeling/SysML-v2-Release")
        lines.append(" * Generator: https://github.com/daltskin/sysml-v2-grammar")
        lines.append(" * License: MIT")
        lines.append(" */")
        lines.append("")
        lines.append(f"parser grammar {self.parser_name};")
        lines.append("")
        lines.append("options {")
        lines.append(f"    tokenVocab = {self.lexer_name};")
        lines.append("}")
        lines.append("")
        # antlr-format configuration (required by grammars-v4 CI)
        lines.append(
            "// $antlr-format alignTrailingComments true, columnLimit 150, useTab false"
        )
        lines.append(
            "// $antlr-format allowShortRulesOnASingleLine false, allowShortBlocksOnASingleLine true"
        )
        lines.append("// $antlr-format alignSemicolons hanging, alignColons hanging")
        lines.append(
            "// $antlr-format minEmptyLines 1, maxEmptyLinesToKeep 1, reflowComments false"
        )
        lines.append("")

        # Generate expression rules with proper precedence
        lines.append("// ===== Expression rules (precedence-climbing) =====")
        lines.append("")
        lines.extend(self.language.expression_rules(self))
        lines.append("")

        # Name rule: names can be identifiers or unrestricted (quoted) names
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

        expression_rules = self.language.expression_rule_names(self)

        # Post-process: break mutual left-recursion cycles
        # FilterPackage → ImportDeclaration → NamespaceImport → FilterPackage
        # Fix by making FilterPackage reference non-filter alternatives directly
        for transform in self.language.rule_transforms:
            transform(self)

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
        expr_rules = self.language.expression_rule_names(self)

        # Rules defined by expression generator
        expr_defined = {
            "ownedExpression",
            "primaryExpression",
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
            # Rules that match nothing (empty alternative) in the official BNF
            epsilon_rules = self.language.epsilon_rules
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
        """Apply the language's post-generation patches in order, recording each one."""
        self.applied_patches: List[Dict[str, object]] = []
        for fix in self.language.patches:
            grammar, applied = apply_patch(grammar, fix)
            self.applied_patches.append(applied)
        # A stub header whose stubs a patch removed is left with no rules.
        grammar = re.sub(
            r"\n// ===== Stub rules for undefined references =====\n(?://[^\n]*\n)*\s*\Z",
            "\n",
            grammar,
        )
        # Name only the rules of the final grammar: a later patch may remove a rule.
        final = rule_bodies(grammar)
        for applied, fix in zip(self.applied_patches, self.language.patches):
            if fix.get("replace"):
                names = str(applied["rules"]).split(", ")
                kept = ", ".join(n for n in names if n in final)
                if applied["applied"] and not kept:
                    kept = "(only rules a later patch removes)"
                applied["rules"] = kept
        return grammar

    def generate_patches_md(self, release_tag: str, grammar_version: str) -> str:
        """Generate the patch documentation of the grammar."""
        patches = list(self.applied_patches)
        lines = [
            "# Grammar Patches",
            "",
            "Post-generation patches applied to the ANTLR4 grammar to fix known issues in the",
            f"OMG {self.title} KEBNF specification when translated to ANTLR4.",
            "",
            f"- **Grammar version**: `{grammar_version}`",
            f"- **OMG release**: `{release_tag}`",
            f"- **Total patches**: {len(patches)}",
            f"- **Applied**: {sum(1 for p in patches if p['applied'])}",
            f"- **Skipped**: {sum(1 for p in patches if not p['applied'])}",
            "",
        ]

        lines.extend(self.language.patch_doc_sections)

        # Group by category
        categories: Dict[str, List[Dict[str, str]]] = {}
        for p in patches:
            categories.setdefault(p["category"], []).append(p)

        for category, patches in categories.items():
            lines.append(f"## {category}")
            lines.append("")
            lines.append("| # | Summary | Rules | Applied |")
            lines.append("|---|---------|-------|---------|")
            for p in patches:
                status = "Yes" if p["applied"] else "No"
                rules = p.get("rules", "")
                # Escape pipe characters in summary/rules for table
                summary = p["summary"].replace("|", "\\|")
                rules_escaped = rules.replace("|", "\\|")
                lines.append(f"| {p['id']} | {summary} | {rules_escaped} | {status} |")
            lines.append("")
            for p in patches:
                lines.append(f"### Fix {p['id']}: {p['summary']}")
                lines.append("")
                lines.append(p["description"])
                if p.get("rules"):
                    lines.append("")
                    lines.append(f"**Affected rules**: {p['rules']}")
                lines.append("")

        lines.append("---")
        lines.append("")
        lines.append(f"*Auto-generated by `{self.language.generator}`.*")
        lines.append("")

        return "\n".join(lines)

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


def download_kebnf(
    repo: str, tag: str, key: str, path: str, cache_dir: Optional[str] = None
) -> str:
    """Download one .kebnf file of release `tag` from GitHub, from the cache if there."""
    import requests

    url = f"https://raw.githubusercontent.com/{repo}/{tag}/{path}"
    cache_path = Path(cache_dir) / f"{key}-{tag}.kebnf" if cache_dir else None
    if cache_path and cache_path.exists():
        print(f"  Using cached {key} from {cache_path}")
        return cache_path.read_text()

    print(f"  Downloading {key} from {url}...")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    content = resp.text

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(content)
    return content


# ---------------------------------------------------------------------------
# KerML expressions (KerML 8.2.5.8, operator precedence of Table 6)
# ---------------------------------------------------------------------------

# Operator precedence, lowest to highest (KerML Table 6)
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


def expression_rule_names(t: "Antlr4Transformer") -> Set[str]:
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


def expression_rules(t: "Antlr4Transformer") -> List[str]:
    """Generate ANTLR4 expression rules with proper precedence.

    The source KEBNF leaves precedence implicit. ANTLR direct-left-recursive
    alternatives must therefore be emitted from high to low precedence,
    with a right-recursive exponentiation tier and the conditional form
    last so its ``else`` operand owns trailing operators.
    """
    lines = []

    # ANTLR direct-left-recursive alternatives are emitted high-to-low.
    lines.append("ownedExpression")
    lines.append("    : ( ISTYPE | HASTYPE | AT_SIGN | AS ) typeReference")
    lines.append("    | ALL typeReference")
    lines.append("    | ( PLUS | MINUS | TILDE | NOT ) ownedExpression")
    lines.append(
        "    | <assoc=right> ownedExpression ( STAR_STAR | CARET ) ownedExpression"
    )
    lines.append("    | ownedExpression ( STAR | SLASH | PERCENT ) ownedExpression")
    lines.append("    | ownedExpression ( PLUS | MINUS ) ownedExpression")
    lines.append("    | ownedExpression DOT_DOT ownedExpression")
    lines.append("    | ownedExpression ( LT | GT | LE | GE ) ownedExpression")
    lines.append("    | ownedExpression ( ISTYPE | HASTYPE | AT_SIGN ) typeReference")
    lines.append("    | ownedExpression AS typeReference")
    lines.append(
        "    | ownedExpression ( EQ_EQ | BANG_EQ | EQ_EQ_EQ | BANG_EQ_EQ ) ownedExpression"
    )
    lines.append("    | ownedExpression ( AMP | AND ) ownedExpression")
    lines.append("    | ownedExpression XOR ownedExpression")
    lines.append("    | ownedExpression ( PIPE | OR ) ownedExpression")
    lines.append("    | ownedExpression IMPLIES ownedExpression")
    lines.append("    | ownedExpression QUESTION_QUESTION ownedExpression")
    lines.append("    | primaryExpression")
    lines.append(
        "    | IF ownedExpression QUESTION ownedExpression ELSE ownedExpression"
    )
    lines.append("    ;")
    lines.append("")

    lines.append("primaryExpression")
    lines.append("    : qualifiedName ( AT_AT | META ) typeReference")
    lines.append("    | baseExpression")
    lines.append("      ( DOT featureChainMember )?")
    lines.append("      (")
    lines.append("        ( LBRACK sequenceExpressionList RBRACK")
    lines.append("        | HASH LPAREN sequenceExpressionList RPAREN")
    lines.append(
        "        | ARROW featureChainMember ( bodyExpression | qualifiedName | argumentList )"
    )
    lines.append("        | DOT bodyExpression")
    lines.append("        | DOT_QUESTION bodyExpression")
    lines.append("        )")
    lines.append("        ( DOT featureChainMember )?")
    lines.append("      )*")
    lines.append("    ;")
    lines.append("")

    lines.append("typeReference")
    lines.append("    : qualifiedName")
    lines.append("    ;")
    lines.append("")

    lines.append("sequenceExpressionList")
    lines.append("    : ownedExpression ( COMMA ownedExpression )* COMMA?")
    lines.append("    ;")
    lines.append("")

    lines.append("baseExpression")
    lines.append("    : nullExpression")
    lines.append("    | literalExpression")
    lines.append(
        "    | qualifiedName DOT qualifiedName ( DOT qualifiedName )* argumentList"
    )
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
    lines.append("    : NEW featureChainMember argumentList")
    lines.append("    ;")
    lines.append("")

    # Body expression
    lines.append("bodyExpression")
    lines.append("    : LBRACE functionBodyPart RBRACE")
    lines.append("    ;")
    lines.append("")

    # Argument list
    lines.append("argumentList")
    lines.append("    : LPAREN ( positionalArgumentList | namedArgumentList )? RPAREN")
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


# The expression changes documented before the patches.
EXPRESSION_LEDGER = [
    "## Expression scope ledger",
    "",
    "The expression changes are limited to the generated `ownedExpression` precedence order and the directly required primary boundaries. Each row has a distinguishing regression; restoring the corresponding hunk reproduces the listed failure.",
    "Non-empty `functionBodyPart` ambiguity is inherited from the base grammar and remains a separate body follow-up; this patch covers only empty-body postfix boundaries and makes no claim about non-empty body acceptance.",
    "",
    "| Generated hunk | Official evidence | Distinguishing regression | Restore failure |",
    "|---|---|---|---|",
    "| `ownedExpression` tier order and final conditional alternative | [KEBNF operator productions](https://github.com/Systems-Modeling/SysML-v2-Release/blob/de1070ae8e79c21532b8004fc663d47b35d0e9fa/bnf/KerML-textual-bnf.kebnf#L932-L969); [OMG Table 6](https://www.omg.org/spec/KerML/1.0/PDF#page=124) | `a + b * c`; `a == b & c xor d | e implies f ?? g`; `if a ? b else c + d` | Base order groups lower-precedence operators inside higher-precedence operands and lets the trailing operator escape the `else` branch. |",
    "| Right-associative exponentiation tier | [KEBNF associativity note](https://github.com/Systems-Modeling/SysML-v2-Release/blob/de1070ae8e79c21532b8004fc663d47b35d0e9fa/bnf/KerML-textual-bnf.kebnf#L1061-L1064) | `a * b ** c`; `a ** b * c`; `a ** b ** c`; `a ^ b ^ c` | Base emission places exponentiation below multiplication in the ANTLR alternative order, so adjacent-tier grouping is wrong; the explicit right-associative marker alone does not repair that precedence. |",
    "| Classification/metaclassification and type-reference boundaries | [KEBNF classification productions](https://github.com/Systems-Modeling/SysML-v2-Release/blob/de1070ae8e79c21532b8004fc663d47b35d0e9fa/bnf/KerML-textual-bnf.kebnf#L979-L1037) | `a istype T + b`; `a istype T as U`; `a + b @@ T`; `a @@ T @@ U` | Restoring the boundary loses recursive raw-KEBNF forms or accepts the invalid chained metaclassification form. |",
    "| `primaryExpression` postfix boundary | [KEBNF primary-expression productions](https://github.com/Systems-Modeling/SysML-v2-Release/blob/de1070ae8e79c21532b8004fc663d47b35d0e9fa/bnf/KerML-textual-bnf.kebnf#L1068-L1178); [official Pilot primary rules](https://github.com/Systems-Modeling/SysML-v2-Pilot-Implementation/blob/fa709f28dfd49dfdb7ee83e4e19da2f57e0eb3aa/org.omg.kerml.expressions.xtext/src/org/omg/kerml/expressions/xtext/KerMLExpressions.xtext#L300-L324) | `-a.f`; `not a.f`; `~a[1]`; `-a->F()`; `all T.f`; `istype T.f` | Restoring direct-left-recursive postfix alternatives changes the official grouping `-(a.f)` to `(-a).f`, and permits postfix continuation after `all` or classification operands. |",
    "| Empty-parenthesized boundary | [KEBNF `NullExpression`](https://github.com/Systems-Modeling/SysML-v2-Release/blob/de1070ae8e79c21532b8004fc663d47b35d0e9fa/bnf/KerML-textual-bnf.kebnf#L1182-L1193) | `()` | The PR base reaches `()` through both `nullExpression` and optional `sequenceExpressionList`, producing one exact ambiguity; retaining one path preserves acceptance with zero ambiguity. |",
    "| Skipped Fix 53 metadata-cast base alternative | [KEBNF classification production](https://github.com/Systems-Modeling/SysML-v2-Release/blob/de1070ae8e79c21532b8004fc663d47b35d0e9fa/bnf/KerML-textual-bnf.kebnf#L979-L985) | `(as T).isMandatory` | Restoring Fix 53 creates an exact ambiguity; the direct `AS` classification alternative accepts this form without the duplicate base production. |",
    "| Sequence, invocation, and constructor primary boundaries | [KEBNF primary/base productions](https://github.com/Systems-Modeling/SysML-v2-Release/blob/de1070ae8e79c21532b8004fc663d47b35d0e9fa/bnf/KerML-textual-bnf.kebnf#L1068-L1233) | `a[1,]`; `a#(1,)`; `a.f.g()`; `new A.B()`; `a[]` | Base accepts empty sequence/index forms, does not preserve trailing commas, or rejects a qualified feature-chain invocation. |",
    "",
]


# ---------------------------------------------------------------------------
# KerML rule transforms
# ---------------------------------------------------------------------------


def kerml_break_filter_package_recursion(
    t: "Antlr4Transformer",
    recursive_import_refs: Set[str] = frozenset({"ImportDeclaration"}),
) -> None:
    """Break the mutual left-recursion cycle:
    FilterPackage → ImportDeclaration → NamespaceImport → FilterPackage.

    Solution: Replace FilterPackage's first alternative
    (ImportDeclaration (FilterPackageMember)+) with inlined non-recursive
    alternatives: (membershipImport | namespaceImportNonFilter) (filterPackageMember)+
    where namespaceImportNonFilter = qualifiedName '::' '*' ('::' '**')?
    """
    if "FilterPackage" not in t.rules:
        return

    rule = t.rules["FilterPackage"]
    # `recursive_import_refs`: the import references that lead back to
    # ImportDeclaration and must be replaced with the non-recursive
    # FilterPackageImportDeclaration.
    new_alts = []
    seen_alt_keys = set()
    for alt in rule.alternatives:
        # Check if this alt starts with ImportDeclaration or an import reference
        has_import_ref = any(
            isinstance(e, NonTerminal) and e.name in recursive_import_refs for e in alt
        )
        if has_import_ref:
            # Replace the import reference with non-recursive inline:
            # ( membershipImport | namespaceImportDirect ) instead
            new_elements = []
            for e in alt:
                if isinstance(e, NonTerminal) and e.name in recursive_import_refs:
                    # Inline: (MembershipImport | NamespaceImportDirect)
                    # where NamespaceImportDirect is the non-FilterPackage alt of NamespaceImport
                    new_elements.append(
                        NonTerminal(name="FilterPackageImportDeclaration")
                    )
                else:
                    new_elements.append(e)
        else:
            new_elements = list(alt)
        # De-duplicate: definitions of FilterPackage through different import
        # references collapse to the same non-recursive alternative once rewritten.
        alt_key = tuple(
            e.name if isinstance(e, NonTerminal) else repr(e) for e in new_elements
        )
        if alt_key in seen_alt_keys:
            continue
        seen_alt_keys.add(alt_key)
        new_alts.append(new_elements)
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
    t.rules["FilterPackageImportDeclaration"] = helper
    t.rule_order.append("FilterPackageImportDeclaration")

    # Create NamespaceImportDirect: the non-FilterPackage alternatives
    # from NamespaceImport
    if "NamespaceImport" in t.rules:
        ns_rule = t.rules["NamespaceImport"]
        direct_alts = []
        for alt in ns_rule.alternatives:
            # Skip alternatives that reference FilterPackage
            has_filter = any(
                isinstance(e, NonTerminal) and e.name == "FilterPackage" for e in alt
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
            t.rules["NamespaceImportDirect"] = direct_rule
            t.rule_order.append("NamespaceImportDirect")
        else:
            # Fallback: all NamespaceImport alts use FilterPackage,
            # just create MembershipImport as the only option
            pass


# Notes and comments: `//* ... */` is a regular comment, as OMG's examples use
# it to comment out model text (Fixes 42, 50). This departs from KerML 8.2.2.2,
# where it is a multi-line note, which is skipped.
KERML_COMMENT_RULES = [
    "// Comments",
    "// REGULAR_COMMENT also matches //* ... */ (OMG block-comment-out convention).",
    "REGULAR_COMMENT : '/*' .*? '*/' | '//*' .*? '*/' ;",
    "// SINGLE_LINE_NOTE: '//' followed by non-'*' content (to avoid consuming",
    "// //* ... */ block comments which are handled by REGULAR_COMMENT).",
    "// A bare '//' at end of line is handled by the second rule.",
    "SINGLE_LINE_NOTE : '//' ~[*\\r\\n] ~[\\r\\n]* -> skip ;",
    "BARE_LINE_COMMENT : '//' -> skip ;",
]

# Rules that match nothing in the KerML BNF.
KERML_EPSILON_RULES = {"emptyFeature"}


def kerml_language(
    lexer_name: str, parser_name: str, patches: List[dict]
) -> GrammarLanguage:
    """The KerML grammar's description for the generator."""
    return GrammarLanguage(
        title="KerML",
        lexer_name=lexer_name,
        parser_name=parser_name,
        generator="scripts/generate_grammar.py",
        expression_rules=expression_rules,
        expression_rule_names=expression_rule_names,
        epsilon_rules=KERML_EPSILON_RULES,
        patches=patches,
        rule_transforms=[kerml_break_filter_package_recursion],
        comment_rules=KERML_COMMENT_RULES,
        patch_doc_sections=EXPRESSION_LEDGER,
    )


# ---------------------------------------------------------------------------
# SysML rule transforms
# ---------------------------------------------------------------------------


def sysml_break_filter_package_recursion(t: Antlr4Transformer) -> None:
    """KerML's FilterPackage transform, for SysML's FilterPackage as well.

    As of the OMG 2026-05 release the SysML kebnf redefines FilterPackage via
    an intermediate `FilterPackageImport : Import = ImportDeclaration` rule, so
    both names have to be broken to avoid re-introducing the mutual
    left-recursion cycle. The now-orphaned FilterPackageImport rule is dropped:
    since it expands to ImportDeclaration, leaving it in place would keep the
    left-recursion cycle alive and emit a dead rule.
    """
    kerml_break_filter_package_recursion(
        t, {"ImportDeclaration", "FilterPackageImport"}
    )
    if "FilterPackageImport" in t.rules:
        del t.rules["FilterPackageImport"]
        if "FilterPackageImport" in t.rule_order:
            t.rule_order.remove("FilterPackageImport")


# Notes and comments of the SysML grammar: KerML's, since SysML's lexical
# structure is KerML's except for its reserved keywords and symbols (SysML
# 8.2.2.1.2).
SYSML_COMMENT_RULES = KERML_COMMENT_RULES

# Rules that match nothing in the SysML BNF, KerML's included.
SYSML_EPSILON_RULES = KERML_EPSILON_RULES | {
    "emptyActionUsage",
    "emptyUsage",
    "emptyMultiplicity",
    "emptyEndMember",
    "portConjugation",  # Conjugated port definition is derived, not user-written
    "emptyParameterMember",  # Empty parameter in transitions
}


def sysml_language(
    lexer_name: str, parser_name: str, patches: List[dict]
) -> GrammarLanguage:
    """The SysML grammar's description for the generator, built on KerML's."""
    return GrammarLanguage(
        title="SysML v2",
        lexer_name=lexer_name,
        parser_name=parser_name,
        generator="scripts/generate_grammar.py",
        expression_rules=expression_rules,
        expression_rule_names=expression_rule_names,
        epsilon_rules=SYSML_EPSILON_RULES,
        patches=patches,
        rule_transforms=[sysml_break_filter_package_recursion],
        comment_rules=SYSML_COMMENT_RULES,
        patch_doc_sections=EXPRESSION_LEDGER,
    )


def download_bnf(config: dict, cache_dir: Optional[str] = None) -> Tuple[str, str]:
    """Download the KerML and SysML .kebnf files of a config's release. Returns (kerml_content, sysml_content)."""
    files = config["bnf_files"]
    tag, repo = config["release_tag"], config["release_repo"]
    return (
        download_kebnf(repo, tag, "kerml", files["kerml"], cache_dir),
        download_kebnf(repo, tag, "sysml", files["sysml"], cache_dir),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_kebnf(contents: List[Tuple[str, str]]) -> KebnfParser:
    """Step 2: parse the .kebnf files, (content, source label) in order, and print the rule counts."""
    print("Step 2: Parsing .kebnf files...")
    kebnf_parser = KebnfParser()
    for content, source in contents:
        kebnf_parser.parse_file(content, source)
    print(f"  Total rules: {len(kebnf_parser.rules)}")
    print(
        f"  Lexical rules: {sum(1 for r in kebnf_parser.rules.values() if r.is_lexical)}"
    )
    print(
        f"  Parser rules: {sum(1 for r in kebnf_parser.rules.values() if not r.is_lexical)}"
    )
    print()
    return kebnf_parser


def transform(
    kebnf_parser: KebnfParser, language: GrammarLanguage
) -> Antlr4Transformer:
    """Step 3: transform the parsed rules for a language, and print the terminals found."""
    print("Step 3: Transforming to ANTLR4...")
    transformer = Antlr4Transformer(
        kebnf_parser.rules, kebnf_parser.rule_order, language
    )
    print(f"  Keywords found: {len(transformer.keywords)}")
    print(f"  Operators found: {len(transformer.operators)}")
    print()
    return transformer


def write_grammar(
    transformer: Antlr4Transformer,
    output: Dict[str, str],
    output_dir: Path,
    release_tag: str,
    grammar_version: str,
) -> None:
    """Step 4: write the lexer and parser grammars and the patch documentation."""
    print("Step 4: Generating .g4 files...")
    output_dir.mkdir(parents=True, exist_ok=True)

    lexer_grammar = transformer.generate_lexer()
    parser_grammar = transformer.generate_parser()

    lexer_path = output_dir / output["lexer_grammar"].split("/")[-1]
    parser_path = output_dir / output["parser_grammar"].split("/")[-1]

    lexer_path.write_text(lexer_grammar)
    parser_path.write_text(parser_grammar)

    print(f"  Lexer:  {lexer_path} ({len(lexer_grammar)} bytes)")
    print(f"  Parser: {parser_path} ({len(parser_grammar)} bytes)")

    # Step 5: Write patch documentation
    patches_md = transformer.generate_patches_md(release_tag, grammar_version)
    patches_path = output_dir / output["patches"].split("/")[-1]
    patches_path.write_text(patches_md)
    applied = sum(1 for p in transformer.applied_patches if p["applied"])
    total = len(transformer.applied_patches)
    print(f"  Patches: {patches_path} ({applied}/{total} applied)")
    print()


def generate_sysml(
    config: dict,
    patch_file: Dict[str, dict],
    cache_dir: Optional[Path],
    output_dir: Path,
) -> None:
    """Generate the SysML grammar from the KerML and SysML KEBNF."""
    # Step 1: Download
    print("Step 1: Downloading .kebnf files...")
    kerml_content, sysml_content = download_bnf(config, cache_dir)
    print(f"  KerML: {len(kerml_content)} bytes")
    print(f"  SysML: {len(sysml_content)} bytes")
    print()

    kebnf_parser = parse_kebnf([(kerml_content, "kerml"), (sysml_content, "sysml")])
    sysml = config["sysml"]
    options = sysml["options"]
    transformer = transform(
        kebnf_parser,
        sysml_language(
            options["lexer_name"],
            options["grammar_name"],
            language_patches(patch_file, "sysml"),
        ),
    )
    write_grammar(
        transformer,
        sysml["output"],
        output_dir,
        config["release_tag"],
        config["grammar_version"],
    )


def generate_kerml(
    config: dict,
    patch_file: Dict[str, dict],
    cache_dir: Optional[Path],
    output_dir: Path,
) -> None:
    """Generate the KerML grammar from the KerML KEBNF alone."""
    kerml = config["kerml"]
    tag = config["release_tag"]
    print(f"KerML grammar (release tag {tag})")
    print()

    # Step 1: Download
    print("Step 1: Downloading .kebnf file...")
    kerml_content = download_kebnf(
        config["release_repo"], tag, "kerml", config["bnf_files"]["kerml"], cache_dir
    )
    print(f"  KerML: {len(kerml_content)} bytes")
    print()

    kebnf_parser = parse_kebnf([(kerml_content, "kerml")])
    options = kerml["options"]
    transformer = transform(
        kebnf_parser,
        kerml_language(
            options["lexer_name"],
            options["grammar_name"],
            language_patches(patch_file, "kerml"),
        ),
    )
    write_grammar(
        transformer,
        kerml["output"],
        output_dir,
        tag,
        config["grammar_version"],
    )


def main():
    parser_arg = argparse.ArgumentParser(
        description="Generate the SysML and KerML ANTLR4 grammars from the OMG KEBNF"
    )
    parser_arg.add_argument("--tag", help="Release tag (e.g., 2025-12)")
    parser_arg.add_argument(
        "--language",
        choices=["sysml", "kerml"],
        help="Generate only this language's grammar (default: both)",
    )
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

    # Validate release tags to prevent path traversal and URL injection
    tag = config["release_tag"]
    if not re.match(r"^[a-zA-Z0-9._-]+$", tag):
        print(f"Error: invalid release tag: {tag!r}", file=sys.stderr)
        print(
            "Tags must contain only alphanumeric characters, dots, hyphens, and underscores.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Determine paths – config.json lives at scripts/config.json,
    # so project_root is one level up from scripts/.
    project_root = config_path.parent.parent
    output_dir = Path(args.output_dir) if args.output_dir else project_root / "grammar"
    cache_dir = project_root / ".grammar-cache" if args.cache else None
    # The post-generation patches; each language's section lists those it applies.
    patch_file = json.loads((project_root / config["patch_file"]).read_text())

    print("SysML v2 ANTLR4 Grammar Generator")
    print(f"  Release tag: {config['release_tag']}")
    print(f"  Output dir:  {output_dir}")
    print()

    if args.language in (None, "sysml"):
        generate_sysml(config, patch_file, cache_dir, output_dir)
    if args.language in (None, "kerml"):
        generate_kerml(config, patch_file, cache_dir, output_dir)

    print("Done! Grammar files written to the grammar/ directory.")


if __name__ == "__main__":
    main()
