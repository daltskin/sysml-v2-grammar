#!/usr/bin/env python3
"""Emit one auditable parser result row for each expression input."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from antlr4.tree.Tree import ParseTree, TerminalNode

from ExpressionGrammarTest import ParseResult, children, parse


OPERATORS = {
    "if",
    "+",
    "-",
    "~",
    "not",
    "**",
    "^",
    "*",
    "/",
    "%",
    "..",
    "<",
    ">",
    "<=",
    ">=",
    "==",
    "!=",
    "===",
    "!==",
    "&",
    "and",
    "xor",
    "|",
    "or",
    "implies",
    "??",
    "istype",
    "hastype",
    "as",
    "@",
    "@@",
    "meta",
    "all",
}
POSTFIX_TERMINALS = {".", ".?", "[", "]", "#", "->", "(", ")"}


def source_span(node: ParseTree, text: str) -> str:
    """Return the source slice covered by one parser context."""
    start = getattr(getattr(node, "start", None), "start", None)
    stop = getattr(getattr(node, "stop", None), "stop", None)
    if start is None or stop is None:
        return text.strip()
    return text[start : stop + 1].strip()


def nested_contexts(node: ParseTree) -> list[ParseTree]:
    return [child for child in children(node) if not isinstance(child, TerminalNode)]


def direct_terminals(node: ParseTree) -> list[str]:
    return [
        child.getText() for child in children(node) if isinstance(child, TerminalNode)
    ]


def semantic_group(node: ParseTree, text: str) -> str:
    """Render the parser's operator tree as a compact parenthesized grouping."""
    operators = direct_terminals(node)
    operator = next((value for value in operators if value in OPERATORS), None)
    nested = nested_contexts(node)
    if operator is None:
        if any(value in POSTFIX_TERMINALS for value in operators):
            return source_span(node, text)
        if len(nested) == 1:
            return semantic_group(nested[0], text)
        return source_span(node, text)

    if operator == "if" and len(nested) >= 3:
        condition = semantic_group(nested[0], text)
        then_branch = semantic_group(nested[1], text)
        else_branch = semantic_group(nested[2], text)
        return (
            f"if {condition if not condition.startswith('if ') else '(' + condition + ')'} ? "
            f"{then_branch if not then_branch.startswith('if ') else '(' + then_branch + ')'} else "
            f"{else_branch if not else_branch.startswith('if ') else '(' + else_branch + ')'}"
        )

    if operator == "all" and len(nested) == 1:
        return f"(all {semantic_group(nested[0], text)})"

    if operator in {"+", "-", "~", "not"} and len(nested) == 1:
        return f"({operator} {semantic_group(nested[0], text)})"

    if len(nested) >= 2:
        left = semantic_group(nested[0], text)
        right = semantic_group(nested[-1], text)
        if left.startswith("if "):
            left = f"({left})"
        if right.startswith("if "):
            right = f"({right})"
        return f"({left} {operator} {right})"

    return source_span(node, text)


def grouping(result: ParseResult, text: str) -> str:
    rendered = semantic_group(result.tree, text)
    if (
        rendered != "()"
        and rendered.startswith("(")
        and rendered.endswith(")")
        and "," not in rendered[1:-1]
    ):
        return rendered[1:-1]
    return rendered


def row(index: int, text: str, result: ParseResult, include_tree: bool) -> str:
    accepted = result.accepted()
    if accepted:
        behavior = f"accept(group={grouping(result, text)})"
    else:
        behavior = (
            "reject("
            f"lex={result.lexer_errors.syntax_errors},"
            f"parse={result.parser_errors.syntax_errors},"
            f"amb={result.parser_errors.exact_ambiguities},"
            f"eof={str(result.eof).lower()})"
        )
    fields = [
        str(index),
        behavior,
    ]
    if include_tree:
        fields.append(f"tree={' '.join(result.tree.toStringTree().split())}")
    return "\t".join(fields)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path, help="One expression per line")
    parser.add_argument(
        "--trees", action="store_true", help="Include compact parse trees in output"
    )
    args = parser.parse_args()

    accepted = 0
    rejected = 0
    for index, line in enumerate(args.corpus.read_text(encoding="utf-8").splitlines()):
        result = parse(line)
        print(row(index, line, result, args.trees))
        if result.accepted():
            accepted += 1
        else:
            rejected += 1
    print(
        f"# total={accepted + rejected} accepted={accepted} rejected={rejected}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
