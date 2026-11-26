#!/usr/bin/env python3
"""KerML grammar regressions.

The KerML grammar is generated from the KerML KEBNF alone. These tests check
it against the KerML specification:

  KerML 8.2.2.6 Reserved Words: the words KerML reserves are not names; a word
  only SysML reserves (SysML 8.2.2.1.2) is a name in KerML.
  KerML 7.4.8.5: an invariant may be declared without a feature declaration
  (`inv { ... }`, `inv false { ... }`).
  KerML 8.2.3.4.1 (Note 1): a text is parsed from `RootNamespace` as a whole,
  so input after the last top-level element it can match is an error.
  SysML-only syntax is not KerML.
  Notes and comments are as in the SysML grammar: `//* ... */` is a regular
  comment (Fixes 42, 50), departing from KerML 8.2.2.2's multi-line note.

The reserved keyword lists are read from the `RESERVED_KEYWORD` productions of
the configured KEBNF files, not written here.

Run (Python ANTLR target):
    PYTHONPATH=<build>/antlr-python-kerml/grammar python scripts/KerMLGrammarTest.py
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener

try:
    from grammar.KerMLLexer import KerMLLexer
    from grammar.KerMLParser import KerMLParser
except ModuleNotFoundError:
    # ANTLR writes flat modules when the grammar paths are absolute.
    from KerMLLexer import KerMLLexer
    from KerMLParser import KerMLParser

from generate_grammar import download_kebnf

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".grammar-cache"


def kebnf(bnf_key: str) -> str:
    """The text of a configured KEBNF file, of its language's release."""
    config = json.loads((ROOT / "scripts" / "config.json").read_text())
    tag = config.get(bnf_key, {}).get("release_tag", config["release_tag"])
    path = config["bnf_files"][bnf_key]
    return download_kebnf(config["release_repo"], tag, bnf_key, path, str(CACHE_DIR))


def reserved_keywords(text: str) -> set[str]:
    """The words of the `RESERVED_KEYWORD` production of a KEBNF text."""
    production = re.search(
        r"^RESERVED_KEYWORD\s*=(.*?)(?=^\S)", text, flags=re.M | re.S
    )
    if production is None:
        raise AssertionError("no RESERVED_KEYWORD production")
    return set(re.findall(r"'([a-z]+)'", production.group(1)))


def keywords_used(text: str) -> set[str]:
    """The words a KEBNF text's productions use as keywords (quoted terminals)."""
    return set(re.findall(r"'([a-z]+)'", text))


class Errors(ErrorListener):
    def __init__(self) -> None:
        self.messages: list[str] = []

    def syntaxError(self, recognizer, offending_symbol, line, column, message, e):
        self.messages.append(f"line {line}:{column} {message}")


def parse(text: str) -> list[str]:
    """The syntax errors of `text` parsed with the KerML grammar from rootNamespace."""
    errors = Errors()
    lexer = KerMLLexer(InputStream(text))
    lexer.removeErrorListeners()
    lexer.addErrorListener(errors)
    parser = KerMLParser(CommonTokenStream(lexer))
    parser.removeErrorListeners()
    parser.addErrorListener(errors)
    parser.rootNamespace()
    return errors.messages


class KerMLGrammarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        kerml = kebnf("kerml")
        sysml = kebnf("sysml")
        cls.kerml_keywords = reserved_keywords(kerml)
        cls.sysml_keywords = reserved_keywords(sysml)
        # A word KerML's productions use as a keyword is a token, though KerML
        # 8.2.2.6 may not list it: `new` (7.4.9.3 "the keyword new").
        cls.kerml_names = cls.sysml_keywords - cls.kerml_keywords - keywords_used(kerml)
        # The KEBNF lists must be found and differ, or the tests below test nothing.
        assert len(cls.kerml_keywords) > 50, cls.kerml_keywords
        assert cls.kerml_names, "no word only SysML reserves"

    def test_word_only_sysml_reserves_is_a_kerml_name(self) -> None:
        for word in sorted(self.kerml_names):
            for text in (
                f"package P {{ feature {word}; }}",  # declared name
                f"package P {{ feature <{word}> x; }}",  # short name
                f"package P {{ classifier C; feature x : P::{word}; }}",  # qualified name
                f"package P {{ feature a; feature y :> a.{word}; }}",  # feature chain
            ):
                with self.subTest(word=word, text=text):
                    self.assertEqual(parse(text), [])

    def test_word_kerml_reserves_is_not_a_name(self) -> None:
        for word in sorted(self.kerml_keywords):
            for text in (
                f"package P {{ classifier <{word}> C; }}",  # short name
                f"package P {{ feature x : P::{word}; }}",  # qualified name
            ):
                with self.subTest(word=word, text=text):
                    self.assertNotEqual(parse(text), [])

    def test_sysml_only_syntax_is_rejected(self) -> None:
        for text in (
            "package P { part def D; }",
            "package P { action a; }",
            "package P { attribute def A; }",
        ):
            with self.subTest(text=text):
                self.assertNotEqual(parse(text), [])

    def test_invariant_without_a_feature_declaration(self) -> None:
        # KerML 7.4.8.5's own examples, inside a class.
        for body in (
            "inv { fuelLevel >= 0 & fuelLevel <= maxFuelLevel }",
            "inv false { fuelLevel > maxFuelLevel }",
            "inv true { true }",
            "private inv { true }",
            "inv i1 { true }",
        ):
            text = f"package P {{ class FuelTank {{ feature fuelLevel; feature maxFuelLevel; {body} }} }}"
            with self.subTest(body=body):
                self.assertEqual(parse(text), [])

    def test_notes_and_comments(self) -> None:
        # A single-line note is skipped (KerML 8.2.2.2). `//* ... */` is a regular
        # comment, as in the SysML grammar (Fixes 42, 50), not KerML's skipped
        # multi-line note: a comment element, or a placeholder expression.
        for text in (
            "package P { classifier C; // a note\n}",
            "package P { comment c /* a comment body */ }",
            "package P { classifier C { doc /* documentation */ } }",
            "package P { //* a comment */ classifier C; }",
            "package P { //* a\nmulti-line comment */ }",
            "package P { comment c //* a comment body */ }",
            "package P { feature x = ( //* placeholder */ ); }",
            "package P { feature x = ( /* placeholder */ ); }",
        ):
            with self.subTest(text=text):
                self.assertEqual(parse(text), [])
        # A comment is a token, not skipped: not allowed where a name is.
        for text in (
            "package P { classifier /* not a note */ C; }",
            "package P { classifier //* not a note */ C; }",
        ):
            with self.subTest(text=text):
                self.assertNotEqual(parse(text), [])

    def test_root_namespace_is_the_whole_text(self) -> None:
        for text in (
            "",
            "// only a note",
            "classifier C;",
            "doc /* top level */ classifier A { feature c : C; } class C; datatype D; feature f : C; package P;",
        ):
            with self.subTest(text=text):
                self.assertEqual(parse(text), [])
        # Each stops a parse without EOF before the offending input, without an error.
        for text in (
            "classifier C; }",
            "classifier C; part def D;",
            "package P { } classifier",
            "classifier C; 1 + 2",
            "}",
        ):
            with self.subTest(text=text):
                self.assertNotEqual(parse(text), [])

    def test_kerml_declarations(self) -> None:
        for text in (
            "package K { classifier C; class Cl; struct S; behavior B; datatype D; assoc A; }",
            "package K { function f { in x; return r; } predicate p { in x; } }",
            "package K { feature g : K::C; end feature e; const end feature c; }",
        ):
            with self.subTest(text=text):
                self.assertEqual(parse(text), [])


if __name__ == "__main__":
    result = unittest.main(exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
