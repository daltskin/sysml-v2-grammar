#!/usr/bin/env python3
"""Run focused expression precedence and boundary regressions."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Iterable, List, Optional

from antlr4 import CommonTokenStream, InputStream, Token
from antlr4.atn.PredictionMode import PredictionMode
from antlr4.error.ErrorListener import ErrorListener
from antlr4.tree.Tree import ParseTree, TerminalNode

try:
    from grammar.SysMLv2Lexer import SysMLv2Lexer
    from grammar.SysMLv2Parser import SysMLv2Parser
except ModuleNotFoundError:
    # ANTLR writes flat modules when the grammar paths are absolute.
    from SysMLv2Lexer import SysMLv2Lexer
    from SysMLv2Parser import SysMLv2Parser


class Errors(ErrorListener):
    """Collect syntax diagnostics and exact ambiguities for one parse."""

    def __init__(self) -> None:
        self.syntax_errors = 0
        self.exact_ambiguities = 0

    def syntaxError(
        self, recognizer, offending_symbol, line, column, message, exception
    ):
        self.syntax_errors += 1

    def reportAmbiguity(
        self, recognizer, dfa, start_index, stop_index, exact, ambig_alts, configs
    ):
        if exact:
            self.exact_ambiguities += 1

    def reportAttemptingFullContext(self, *args):
        pass

    def reportContextSensitivity(self, *args):
        pass


@dataclass
class Case:
    """Describe one expected expression parse and optional tree shape checks."""

    input: str
    expected: bool
    root_operator: Optional[str] = None
    associative_operator: Optional[str] = None
    left_associative: bool = True
    condition_operator: Optional[str] = None
    then_operator: Optional[str] = None
    else_operator: Optional[str] = None
    check_conditional: bool = False

    def root(self, operator: str) -> "Case":
        self.root_operator = operator
        return self

    def left(self, operator: str) -> "Case":
        self.associative_operator = operator
        self.left_associative = True
        return self

    def right(self, operator: str) -> "Case":
        self.associative_operator = operator
        self.left_associative = False
        return self

    def branches(
        self,
        condition: Optional[str],
        then_branch: Optional[str],
        else_branch: Optional[str],
    ) -> "Case":
        self.check_conditional = True
        self.condition_operator = condition
        self.then_operator = then_branch
        self.else_operator = else_branch
        return self


def valid(text: str) -> Case:
    return Case(text, True)


def invalid(text: str) -> Case:
    return Case(text, False)


def expression_cases() -> List[Case]:
    cases: List[Case] = []

    precedence = [
        ("a + b * c", "+"),
        ("a * b + c", "+"),
        ("a .. b + c", ".."),
        ("a + b .. c", ".."),
        ("a < b .. c", "<"),
        ("a .. b < c", "<"),
        ("a < b == c", "=="),
        ("a == b < c", "=="),
        ("a and b == c", "and"),
        ("a == b and c", "and"),
        ("a xor b and c", "xor"),
        ("a and b xor c", "xor"),
        ("a or b xor c", "or"),
        ("a xor b or c", "or"),
        ("a implies b or c", "implies"),
        ("a or b implies c", "implies"),
        ("a ?? b implies c", "??"),
        ("a implies b ?? c", "??"),
        ("a == b & c xor d | e implies f ?? g", "??"),
    ]
    cases.extend(valid(text).root(operator) for text, operator in precedence)

    for operator in [
        "+",
        "-",
        "*",
        "/",
        "%",
        "..",
        "<",
        "==",
        "&",
        "and",
        "xor",
        "|",
        "or",
        "implies",
        "??",
    ]:
        cases.append(valid(f"a {operator} b {operator} c").left(operator))
    cases.extend(
        [
            valid("a & b and c").root("and"),
            valid("a | b or c").root("or"),
            valid("a == b === c").root("==="),
            valid("a < b <= c").root("<="),
            valid("a * b ** c").root("*"),
            valid("a ** b * c").root("*"),
            valid("a ** b ** c").right("**"),
            valid("a ^ b ^ c").right("^"),
            valid("a ** b ^ c").root("**"),
            valid("a ^ b ** c").root("^"),
            valid("-a.f").root("-"),
            valid("not a.f").root("not"),
        ]
    )

    cases.extend(
        [
            valid("if a ? b else c").root("if").branches(None, None, None),
            valid("if a + b ? c * d else e ** f").root("if").branches("+", "*", "**"),
            valid("if a ? b else c + d").root("if").branches(None, None, "+"),
            valid("if a ? b else c ?? d").root("if").branches(None, None, "??"),
            valid("if if a ? b else c ? d else e")
            .root("if")
            .branches("if", None, None),
            valid("if a ? if b ? c else d else e")
            .root("if")
            .branches(None, "if", None),
            valid("if a ? b else if c ? d else e")
            .root("if")
            .branches(None, None, "if"),
            valid("a + if b ? c else d").root("+").branches(None, None, None),
            valid("a + if b ? c else d + e").root("+").branches(None, None, "+"),
            valid("a + if b ? c else d ?? e").root("+").branches(None, None, "??"),
            valid("a ** if b ? c else d").root("**").branches(None, None, None),
            valid("-if b ? c else d").root("-"),
            valid("not if b ? c else d").root("not"),
        ]
    )

    cases.extend(
        [
            valid("istype T"),
            valid("hastype T"),
            valid("@ T"),
            valid("as T"),
            valid("a istype T"),
            valid("a @@ T"),
            valid("a meta T"),
            valid("a istype T + b").root("+"),
            valid("a + b istype T").root("istype"),
            valid("a as T + b").root("+"),
            valid("a + b as T").root("as"),
            valid("a == b istype T").root("=="),
            valid("a + b @@ T").root("+"),
            valid("a @@ T + b").root("+"),
            valid("a meta T < b").root("<"),
            valid("a @@ T as U").root("as"),
            valid("a @@ T == b").root("=="),
            valid("a meta T == b").root("=="),
            valid("a istype T as U"),
            valid("(as T).isMandatory"),
        ]
    )
    cases.extend(
        invalid(text)
        for text in [
            "@@ T",
            "meta T",
            "a.metadata @@ T",
            "a.metadata meta T",
            "a istype",
            "a @@",
            "a @@ T @@ U",
            "a meta T meta U",
            "all T.f",
            "istype T.f",
            "a @@ T.f",
        ]
    )

    # Non-empty body ambiguity is inherited from functionBodyPart and remains
    # intentionally outside this expression-only patch.
    cases.extend(
        valid(text)
        for text in [
            "a.b",
            "a.b.c",
            "a()",
            "a.f()",
            "a().b",
            "a.f().g",
            "a.f.g()",
            "a + b.f",
            "a + b[1]",
            "a[1].b",
            "a[1,]",
            "a#(1).b",
            "a.f()[1]",
            "a.b[1,].d",
            "(a,)",
            "()",
            "a(x = b)",
            "new T()",
            "new A.B()",
            "a->F()",
            "a->F g",
            "a->F.g()",
            "a->F {}",
            "a.{}",
            "a.?{}",
            "~a[1]",
            "-a->F()",
            "a#(1,)",
        ]
    )
    cases.extend(
        invalid(text)
        for text in [
            "a ? b else c",
            "if a ? b",
            "if a ? b else",
            "if a b ? c else d",
            "a +",
            "a **",
            "-",
            "not",
            "a[]",
            "a#()",
            "a(b)(c)",
            "a()()",
            "a.f()()",
            "a.f().g()",
            "a.f(x).g(y)",
            "a->F().g()",
            "a[1].f()",
            "a#(1).f()",
            "a.{}.f()",
            "(a + b).f()",
            "a->F",
            "a->F.g",
            "a + b c",
            "a + ?",
            "a + b trailing",
        ]
    )

    # Conditional expressions recursively occupy every OwnedExpression slot.
    conditional = "if b ? c else d"
    conditional_operators = [
        "??",
        "implies",
        "|",
        "or",
        "xor",
        "&",
        "and",
        "==",
        "!=",
        "===",
        "!==",
        "<",
        ">",
        "<=",
        ">=",
        "..",
        "+",
        "-",
        "*",
        "/",
        "%",
        "**",
        "^",
    ]
    cases.extend(
        valid(text)
        for text in [
            "if b ? c else d",
            "if if a ? b else c ? d else e",
            "if a ? if b ? c else d else e",
            "if a ? b else if c ? d else e",
        ]
    )
    for operator in conditional_operators:
        cases.extend(
            [
                valid(f"a {operator} {conditional}"),
                valid(f"{conditional} {operator} a"),
                valid(f"if a ? b else c {operator} if d ? e else f"),
            ]
        )
    for operator in ["+", "-", "~", "not"]:
        prefix = "not " if operator == "not" else operator
        cases.extend(
            [
                valid(f"{prefix}{conditional}"),
                valid(f"{prefix}if a ? if b ? c else d else e"),
            ]
        )
    for operator in ["+", "-", "~", "not"]:
        prefix = "not " if operator == "not" else operator
        cases.append(valid(f"{prefix}({conditional})"))
    for operator in conditional_operators:
        cases.extend(
            [
                valid(f"a {operator} ({conditional})"),
                valid(f"({conditional}) {operator} a"),
            ]
        )
    cases.extend(
        valid(text)
        for text in [
            "a + if b ? c else d + e",
            "a + if b ? c else d * e",
            "a + b * if c ? d else e",
            "a ?? if b ? c else d",
            "a ** if b ? c else d",
        ]
    )
    return cases


def children(tree: ParseTree) -> Iterable[ParseTree]:
    for index in range(tree.getChildCount()):
        yield tree.getChild(index)


def terminals(tree: ParseTree, text: str) -> List[TerminalNode]:
    if isinstance(tree, TerminalNode):
        return [tree] if tree.getText() == text else []
    result: List[TerminalNode] = []
    for child in children(tree):
        result.extend(terminals(child, text))
    return result


def has_direct_terminal(tree: ParseTree, text: str) -> bool:
    return any(
        isinstance(child, TerminalNode) and child.getText() == text
        for child in children(tree)
    )


def find_conditional(tree: ParseTree) -> Optional[ParseTree]:
    if has_direct_terminal(tree, "if"):
        return tree
    for child in children(tree):
        found = find_conditional(child)
        if found is not None:
            return found
    return None


def conditional_branches(tree: ParseTree) -> List[ParseTree]:
    return [child for child in children(tree) if not isinstance(child, TerminalNode)]


def check_branch(branch: ParseTree, expected: Optional[str], text: str) -> None:
    if expected is not None and not has_direct_terminal(branch, expected):
        raise AssertionError(
            f"Unexpected conditional branch for `{text}`: expected `{expected}`\n"
            f"{branch.toStringTree(recog=branch.parser if hasattr(branch, 'parser') else None)}"
        )


def check_shape(case: Case, tree: ParseTree) -> None:
    if case.root_operator is not None:
        roots = terminals(tree, case.root_operator)
        if not any(terminal.getParent() is tree for terminal in roots):
            raise AssertionError(
                f"Unexpected root for `{case.input}`: {tree.toStringTree()}"
            )

    if case.associative_operator is not None:
        operators = terminals(tree, case.associative_operator)
        if len(operators) != 2:
            raise AssertionError(f"Expected two operators in `{case.input}`")
        first_is_root = operators[0].getParent() is tree
        if first_is_root == case.left_associative:
            raise AssertionError(
                f"Unexpected associativity for `{case.input}`: {tree.toStringTree()}"
            )

    if case.check_conditional:
        conditional = find_conditional(tree)
        if conditional is None:
            raise AssertionError(f"Expected conditional expression for `{case.input}`")
        branches = conditional_branches(conditional)
        if len(branches) != 3:
            raise AssertionError(
                f"Conditional does not have three branches for `{case.input}`"
            )
        check_branch(branches[0], case.condition_operator, case.input)
        check_branch(branches[1], case.then_operator, case.input)
        check_branch(branches[2], case.else_operator, case.input)


@dataclass
class ParseResult:
    tree: ParseTree
    lexer_errors: Errors
    parser_errors: Errors
    eof: bool

    def accepted(self) -> bool:
        return (
            self.lexer_errors.syntax_errors == 0
            and self.parser_errors.syntax_errors == 0
            and self.parser_errors.exact_ambiguities == 0
            and self.eof
        )

    def diagnostics(self) -> str:
        return (
            f"lexerErrors={self.lexer_errors.syntax_errors}, "
            f"parserErrors={self.parser_errors.syntax_errors}, "
            f"exactAmbiguities={self.parser_errors.exact_ambiguities}, "
            f"eof={str(self.eof).lower()}"
        )


def parse(text: str, root: bool = False) -> ParseResult:
    lexer_errors = Errors()
    lexer = SysMLv2Lexer(InputStream(text))
    lexer.removeErrorListeners()
    lexer.addErrorListener(lexer_errors)
    tokens = CommonTokenStream(lexer)
    tokens.fill()

    parser_errors = Errors()
    parser = SysMLv2Parser(tokens)
    parser.removeErrorListeners()
    parser.addErrorListener(parser_errors)
    parser._interp.predictionMode = PredictionMode.LL_EXACT_AMBIG_DETECTION
    tree = parser.rootNamespace() if root else parser.ownedExpression()
    eof = parser.getCurrentToken().type == Token.EOF
    return ParseResult(tree, lexer_errors, parser_errors, eof)


def main() -> int:
    cases = expression_cases()
    accepted = 0
    rejected = 0
    for index, case in enumerate(cases, start=1):
        result = parse(case.input)
        actual = result.accepted()
        if actual != case.expected:
            raise AssertionError(
                f"Case {index} expected {case.expected} for `{case.input}`: "
                f"{result.diagnostics()}\n{result.tree.toStringTree()}"
            )
        if actual:
            check_shape(case, result.tree)
            accepted += 1
        else:
            rejected += 1

    valid_roots = [
        "package P { attribute x = a + b; }",
        "package P { attribute x = if a ? b else c + d; }",
    ]
    for text in valid_roots:
        result = parse(text, root=True)
        if not result.accepted():
            raise AssertionError(
                f"Root expression should be accepted: {text}: {result.diagnostics()}"
            )

    invalid_root = "package P { attribute x = a + ; }"
    if parse(invalid_root, root=True).accepted():
        raise AssertionError(f"Root expression should be rejected: {invalid_root}")

    print(
        f"Expression grammar checks passed: {len(cases)} cases "
        f"({accepted} accepted, {rejected} rejected); root entrypoint passed"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
