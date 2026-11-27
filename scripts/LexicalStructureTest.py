#!/usr/bin/env python3
"""Lexical structure: the KerML and SysML grammars read it alike (SysML 8.2.2.1.2).

SysML's lexical structure is identical to KerML's, apart from the reserved
words (SysML 8.2.2.1.2). So for every text below, of strings, unrestricted
names, white space, notes and comments (KerML 8.2.2), the two grammars must
both accept it or both reject it; and the texts KerML 8.2.2 makes valid must be
accepted by both.

Run (Python ANTLR target), after generating both grammars' Python parsers:
    python scripts/LexicalStructureTest.py
with <build>/antlr-python/grammar and <build>/antlr-python-kerml/grammar, or
the directories in SYSML_PYTHON_DIR and KERML_PYTHON_DIR.
"""

from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / ".build"
for variable, default in (
    ("SYSML_PYTHON_DIR", BUILD / "antlr-python" / "grammar"),
    ("KERML_PYTHON_DIR", BUILD / "antlr-python-kerml" / "grammar"),
):
    sys.path.insert(0, os.environ.get(variable, str(default)))

# Each grammar's lexer and parser module, and a feature keyword it has.
GRAMMARS = {
    "sysml": ("SysMLv2Lexer", "SysMLv2Parser", "attribute"),
    "kerml": ("KerMLLexer", "KerMLParser", "feature"),
}

# The escape sequences of Table 4 (KerML 8.2.2.3) and of the KEBNF ESCAPE_SEQUENCE.
ESCAPES = ("\\'", '\\"', "\\\\", "\\b", "\\f", "\\t", "\\n", "\\r", "\\v")


class Errors(ErrorListener):
    def __init__(self) -> None:
        self.messages: list[str] = []

    def syntaxError(self, recognizer, offending_symbol, line, column, message, e):
        self.messages.append(f"line {line}:{column} {message}")


def parse(language: str, text: str) -> list[str]:
    """The lexer and parser errors of `text`, parsed from rootNamespace with `language`'s grammar."""
    lexer_name, parser_name, _ = GRAMMARS[language]
    lexer_class = getattr(importlib.import_module(lexer_name), lexer_name)
    parser_class = getattr(importlib.import_module(parser_name), parser_name)
    errors = Errors()
    lexer = lexer_class(InputStream(text))
    lexer.removeErrorListeners()
    lexer.addErrorListener(errors)
    parser = parser_class(CommonTokenStream(lexer))
    parser.removeErrorListeners()
    parser.addErrorListener(errors)
    parser.rootNamespace()
    return errors.messages


def in_grammar(language: str, template: str) -> str:
    """`template` with `{feature}` replaced by `language`'s feature keyword."""
    return template.replace("{feature}", GRAMMARS[language][2])


def quoted(content: str) -> tuple[str, str]:
    """`content` as an unrestricted name and as a string value."""
    return (
        f"package '{content}';",
        f'package P {{ {{feature}} x = "{content}"; }}',
    )


# Texts KerML 8.2.2 makes valid, which both grammars must accept.
VALID_TEXTS = (
    "package P;",
    "package\tP;",
    "\r\n package P { }\r\n",
    *(t for escape in ESCAPES for t in quoted(f"a{escape}b")),
    *quoted("a\tb"),
    *quoted(""),
    *quoted("\\\\"),
    "// a note\npackage P;",
    "//\npackage P;",
    "// a */ in a note\npackage P;",
    "package P; // a note at the end",
    "package P { // a note\n}",
    "package P { /* a comment */ }",
    "package P { //* a comment */ }",
    "package P { //* a\nmulti-line comment */ }",
    "package P { //** a comment **/ }",
)

# Texts both grammars must reject.
INVALID_TEXTS = (
    "package P { /* not closed }",
    "package P { //* a comment */ */ }",
    "package /* not a note */ P;",
    "package //* not a note */ P;",
)

# Texts whose reading both grammars must share, whatever it is: also the
# lexical departures both have (see the Known problems of the KerML grammar).
SHARED_TEXTS = (
    *VALID_TEXTS,
    *INVALID_TEXTS,
    "package\fP;",
    "package\vP;",
    "package\x00P;",
    *(t for escape in ("\\q", "\\0", "\\u", "\\ ") for t in quoted(f"a{escape}b")),
    *quoted("a\nb"),
    *quoted("a\r\nb"),
    "package 'a\\';",
    'package P { {feature} x = "a\\"; }',
    "//*** a header\npackage P;",
    "//*\npackage P;",
    "//* a note\npackage P; /* c */",
)


class LexicalStructureTest(unittest.TestCase):
    def test_both_grammars_read_lexical_structure_alike(self) -> None:
        for template in SHARED_TEXTS:
            with self.subTest(text=template):
                self.assertEqual(
                    parse("sysml", in_grammar("sysml", template)) == [],
                    parse("kerml", in_grammar("kerml", template)) == [],
                )

    def test_valid_lexical_structure_is_accepted(self) -> None:
        for language in GRAMMARS:
            for template in VALID_TEXTS:
                text = in_grammar(language, template)
                with self.subTest(language=language, text=text):
                    self.assertEqual(parse(language, text), [])

    def test_unterminated_and_misplaced_comments_are_rejected(self) -> None:
        for language in GRAMMARS:
            for text in INVALID_TEXTS:
                with self.subTest(language=language, text=text):
                    self.assertNotEqual(parse(language, text), [])


if __name__ == "__main__":
    result = unittest.main(exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
