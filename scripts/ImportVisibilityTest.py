#!/usr/bin/env python3
"""Import visibility conformance tests.

The OMG grammar requires an explicit visibility keyword on every import:

  KerML-textual-bnf.kebnf (SysML-v2-Release 2026-08), Clause 8.2.3.4.2:
      Import =
          visibility = VisibilityIndicator
          'import' ( isImportAll ?= 'all' )?
          ImportDeclaration RelationshipBody

  SysML-textual-bnf.kebnf, Clause 8.2.2.5 (Namespaces and Packages):
      Import =
          visibility = VisibilityIndicator
          'import' ( isImportAll ?= 'all' )?
          ImportDeclaration RelationshipBody

  Contrast MemberPrefix in the same files, which deliberately wraps the
  same property in an optional group:
      MemberPrefix : Membership =
          ( visibility = VisibilityIndicator )?

  KerML v1.1 spec 7.2.5.4 / SysML v2.1 spec 7.5.3, on import visibility:
      "The visibility of an import is always shown explicitly by placing
      the keyword private, protected, or public before the import
      declaration."

Run (Python ANTLR target):
    PYTHONPATH=<build>/antlr-python/grammar python scripts/ImportVisibilityTest.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener

try:
    from grammar.SysMLv2Lexer import SysMLv2Lexer
    from grammar.SysMLv2Parser import SysMLv2Parser
except ModuleNotFoundError:
    # ANTLR writes flat modules when the grammar paths are absolute.
    from SysMLv2Lexer import SysMLv2Lexer
    from SysMLv2Parser import SysMLv2Parser


class Errors(ErrorListener):
    def __init__(self) -> None:
        self.syntax_errors = 0
        self.messages: list[str] = []

    def syntaxError(self, recognizer, offending_symbol, line, column, message, e):
        self.syntax_errors += 1
        self.messages.append(f"line {line}:{column} {message}")


@dataclass
class Case:
    input: str
    expected: bool
    note: str


def parse(text: str) -> tuple[bool, list[str]]:
    errors = Errors()
    lexer = SysMLv2Lexer(InputStream(text))
    lexer.removeErrorListeners()
    lexer.addErrorListener(errors)
    parser = SysMLv2Parser(CommonTokenStream(lexer))
    parser.removeErrorListeners()
    parser.addErrorListener(errors)
    parser.rootNamespace()
    return errors.syntax_errors == 0, errors.messages


def wrap(import_stmt: str) -> str:
    return f"package P {{\n    {import_stmt}\n}}\n"


# import declarations resolve against P::P1, declared in the harness.
CASES = [
    # --- Positive: each explicit visibility keyword must parse.
    Case(
        wrap("private import P1::A;"),
        True,
        "private membership import",
    ),
    Case(
        wrap("public import P1::A;"),
        True,
        "public membership import",
    ),
    Case(
        wrap("protected import P1::A;"),
        True,
        "protected membership import",
    ),
    Case(
        wrap("private import all P1::A;"),
        True,
        "'import all' membership import",
    ),
    Case(
        wrap("private import P1::*;"),
        True,
        "namespace import",
    ),
    Case(
        wrap("private import P1::**;"),
        True,
        "recursive import",
    ),
    Case(
        wrap("private import P1::*::**;"),
        True,
        "recursive namespace import",
    ),
    # --- Negative: bare 'import' must be a syntax error.
    Case(
        wrap("import P1::A;"),
        False,
        "bare import rejected: visibility required",
    ),
    Case(
        wrap("import P1::*;"),
        False,
        "bare namespace import rejected",
    ),
    Case(
        wrap("import all P1::A;"),
        False,
        "bare 'import all' rejected",
    ),
]


def main() -> int:
    accepted = rejected = 0
    failures = 0
    for case in CASES:
        ok, msgs = parse(case.input)
        if ok != case.expected:
            failures += 1
            print(f"❌ {case.note}: expected {'accept' if case.expected else 'reject'}, "
                  f"got {'accept' if ok else 'reject'}")
            for m in msgs[:2]:
                print(f"     {m}")
        elif ok:
            accepted += 1
            print(f"✅ accepted: {case.note}")
        else:
            rejected += 1
            print(f"✅ rejected: {case.note}")
    print(
        f"\nImport visibility checks: {len(CASES) - failures}/{len(CASES)} passed "
        f"({accepted} accepted, {rejected} rejected)"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
