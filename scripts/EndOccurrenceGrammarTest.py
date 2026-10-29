#!/usr/bin/env python3
"""Regressions for typed ends in definition, interface and behavior bodies.

SysML 2.0 8.2.2.17 omits an end-occurrence route in NonBehaviorBodyItem.
The 2026-09 Systems Library uses it in Flows::messages, and the Pilot
OccurrenceUsagePrefix accepts EndUsagePrefix. Fix 54 bridges this BNF gap.
"""

from __future__ import annotations

import unittest

from antlr4 import CommonTokenStream, InputStream, Token
from antlr4.error.ErrorListener import ErrorListener
from antlr4.tree.Tree import TerminalNode

from grammar.SysMLv2Lexer import SysMLv2Lexer
from grammar.SysMLv2Parser import SysMLv2Parser

from generate_grammar import Antlr4Transformer


class Errors(ErrorListener):
    def __init__(self) -> None:
        self.messages: list[str] = []

    def syntaxError(self, recognizer, offending_symbol, line, column, message, e):
        self.messages.append(f"line {line}:{column} {message}")


class EndOccurrenceTests(unittest.TestCase):
    def parse(self, text: str):
        errors = Errors()
        lexer = SysMLv2Lexer(InputStream(text))
        lexer.removeErrorListeners()
        lexer.addErrorListener(errors)
        tokens = CommonTokenStream(lexer)
        parser = SysMLv2Parser(tokens)
        parser.removeErrorListeners()
        parser.addErrorListener(errors)
        tree = parser.rootNamespace()
        self.assertEqual(tokens.LA(1), Token.EOF)
        return tree, errors.messages

    def assert_end_count(self, text: str, expected: int) -> None:
        tree, errors = self.parse(text)
        self.assertEqual(errors, [])
        pending = [tree]
        count = 0
        while pending:
            node = pending.pop()
            if isinstance(node, TerminalNode):
                continue
            if node.getRuleIndex() == SysMLv2Parser.RULE_endOccurrenceUsageElement:
                count += 1
            pending.extend(node.getChildren())
        self.assertEqual(count, expected)

    def test_september_messages(self) -> None:
        self.assert_end_count(
            """package Flows {
                abstract action messages: Message[0..*] nonunique :> transfers, actions {
                    end occurrence source: Occurrence :>> Message::source, transfers::source;
                    end occurrence target: Occurrence :>> Message::target, transfers::target;
                }
            }""",
            2,
        )

    def test_shared_nonbehavior_bodies(self) -> None:
        for owner in [
            "action def A",
            "action a",
            "state def S",
            "state s",
            "calc def C",
            "calc c",
            "analysis def A",
            "analysis a",
            "use case def U",
            "verification def V",
        ]:
            with self.subTest(owner=owner):
                self.assert_end_count(
                    f"package P {{ {owner} {{ "
                    "private end occurrence source : Occurrence :>> Base::source;"
                    " } }",
                    1,
                )

    def test_existing_definition_and_interface_ends(self) -> None:
        for owner in ["connection def C", "interface def I", "flow def F"]:
            with self.subTest(owner=owner):
                self.assert_end_count(
                    f"package P {{ {owner} {{ end [1] port p : Port; }} }}", 1
                )

    def test_end_prefix_forms_in_action_body(self) -> None:
        for declaration in [
            "end item payload : Item;",
            "end part participant : Part;",
            "end [0..1] port endpoint : Port;",
            "end source [1] occurrence observed : Occurrence;",
            "end [0..*] nonunique item payload : Item;",
        ]:
            with self.subTest(declaration=declaration):
                self.assert_end_count(
                    f"package P {{ action a {{ {declaration} }} }}", 1
                )

    def test_malformed_ends_are_rejected(self) -> None:
        for declaration in [
            "end occurrence source : ;",
            "end occurrence source : Occurrence :>> ;",
            "end [0..] occurrence source : Occurrence;",
            "end end occurrence source : Occurrence;",
            "end occurrence source : Occurrence",
        ]:
            with self.subTest(declaration=declaration):
                _, errors = self.parse(f"package P {{ action a {{ {declaration} }} }}")
                self.assertTrue(errors)

    def test_upstream_body_drift_fails_visibly(self) -> None:
        transformer = Antlr4Transformer({}, [])
        with self.assertRaisesRegex(
            ValueError, "Fix 54: NonBehaviorBodyItem has changed"
        ):
            transformer._apply_grammar_patches(
                "nonBehaviorBodyItem\n    : importRule\n    ;"
            )


if __name__ == "__main__":
    unittest.main()
