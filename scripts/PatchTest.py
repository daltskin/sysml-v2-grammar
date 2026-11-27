#!/usr/bin/env python3
"""Post-generation patches: selection by language, application, and their documentation."""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

from generate_grammar import (
    apply_patch,
    changed_rules,
    language_patches,
    unreachable_rules,
)

ROOT = Path(__file__).resolve().parent.parent
LANGUAGES = {"sysml", "kerml"}
CONFIG = json.loads((ROOT / "scripts" / "config.json").read_text())
PATCH_FILE = json.loads((ROOT / "scripts" / "patches.json").read_text())

# A small grammar in the generator's layout: a rule name, its body, `    ;`.
GRAMMAR = """
rootNamespace
    : a b
    ;

a
    : X  // b is mentioned here only in a comment: see rule c
    ;

b
    : Y
    ;

c
    : Z
    ;
"""


def fix(**entry: object) -> dict:
    """A patch-file entry with the fields every entry has."""
    return {"id": "1", "category": "Test", "summary": "s", "description": "d", **entry}


def patch_docs(language: str) -> str:
    """The generated patch documentation of a language's grammar."""
    return (ROOT / CONFIG[language]["output"]["patches"]).read_text()


def grammar_rules(language: str) -> set[str]:
    """The parser and lexer rule names of a language's generated grammar."""
    output = CONFIG[language]["output"]
    text = "".join(
        (ROOT / output[key]).read_text() for key in ("parser_grammar", "lexer_grammar")
    )
    return set(re.findall(r"^(?:fragment\s+)?([A-Za-z_]\w*)\s*\n?\s*:", text, re.M))


class PatchSelectionTest(unittest.TestCase):
    def test_selects_by_language_in_file_order(self) -> None:
        patch_file = {
            "2": {"language": ["sysml"]},
            "1": {"language": ["sysml", "kerml"]},
            "3": {"language": ["kerml"]},
        }
        self.assertEqual(
            [p["id"] for p in language_patches(patch_file, "sysml")], ["2", "1"]
        )
        self.assertEqual(
            [p["id"] for p in language_patches(patch_file, "kerml")], ["1", "3"]
        )

    def test_entry_without_a_language_is_an_error(self) -> None:
        for entry in ({}, {"language": []}):
            with self.subTest(entry=entry), self.assertRaises(KeyError):
                language_patches({"1": {"language": ["sysml"]}, "2": entry}, "sysml")

    def test_patch_file_languages_are_known(self) -> None:
        for key, entry in PATCH_FILE.items():
            with self.subTest(fix=key):
                self.assertTrue(entry.get("language"))
                self.assertLessEqual(set(entry["language"]), LANGUAGES)

    def test_unreachable_rule_removal_is_applied_last(self) -> None:
        # Fix 52 removes the rules no other patch has made reachable.
        for language in LANGUAGES:
            with self.subTest(language=language):
                self.assertEqual(language_patches(PATCH_FILE, language)[-1]["id"], "52")


class ApplyPatchTest(unittest.TestCase):
    def test_replacement_records_the_rules_it_changed(self) -> None:
        grammar, record = apply_patch(
            GRAMMAR,
            fix(replace=[{"old": "    : Y\n", "new": "    : Y?\n"}], rules="stale"),
        )
        self.assertIn("    : Y?\n", grammar)
        self.assertTrue(record["applied"])
        self.assertEqual(record["rules"], "b")

    def test_replacement_that_matches_nothing_is_skipped(self) -> None:
        grammar, record = apply_patch(
            GRAMMAR, fix(replace=[{"old": "no such text", "new": "x"}], rules="b")
        )
        self.assertEqual(grammar, GRAMMAR)
        self.assertFalse(record["applied"])
        self.assertEqual(record["rules"], "")

    def test_regex_replacement(self) -> None:
        grammar, record = apply_patch(
            GRAMMAR,
            fix(replace=[{"old": r"(?<=: )Z\b", "new": "Z+", "regex": True}]),
        )
        self.assertIn("    : Z+\n", grammar)
        self.assertEqual(record["rules"], "c")

    def test_expect_once_counts_regex_matches(self) -> None:
        once = {"expect_once": "must match once"}
        # One regex match of a pattern whose literal text occurs nowhere.
        apply_patch(
            GRAMMAR,
            fix(replace=[{"old": r"\bZ\b", "new": "Z", "regex": True}], **once),
        )
        for old, regex in ((r"\b[XY]\b", True), ("    ;\n", False), ("none", False)):
            with self.subTest(old=old), self.assertRaises(ValueError):
                apply_patch(
                    GRAMMAR,
                    fix(replace=[{"old": old, "new": "x", "regex": regex}], **once),
                )

    def test_renamed_rule_is_recorded_by_its_new_name(self) -> None:
        _, record = apply_patch(
            GRAMMAR,
            fix(replace=[{"old": "\nc\n", "new": "\nc_\n"}]),
        )
        self.assertEqual(record["rules"], "c_")

    def test_unreachable_rules_are_removed_and_counted(self) -> None:
        grammar, record = apply_patch(
            GRAMMAR,
            fix(
                remove_unreachable_rules=True,
                summary="Remove {count} rules",
                rules="({count} rules removed)",
            ),
        )
        self.assertNotIn("\nc\n", grammar)
        self.assertIn("\nb\n", grammar)
        self.assertEqual(record["summary"], "Remove 1 rules")
        self.assertEqual(record["rules"], "(1 rules removed)")

    def test_documentation_only_entry(self) -> None:
        grammar, record = apply_patch(
            GRAMMAR, fix(applied=True, rules="REGULAR_COMMENT (lexer rule)")
        )
        self.assertEqual(grammar, GRAMMAR)
        self.assertTrue(record["applied"])
        self.assertEqual(record["rules"], "REGULAR_COMMENT (lexer rule)")


class RuleAnalysisTest(unittest.TestCase):
    def test_a_rule_named_only_in_a_comment_is_unreachable(self) -> None:
        self.assertEqual(unreachable_rules(GRAMMAR), ["c"])

    def test_a_rule_reached_through_a_chain_is_reachable(self) -> None:
        grammar = GRAMMAR.replace("    : Y\n", "    : Y c\n")
        self.assertEqual(unreachable_rules(grammar), [])

    def test_changed_rules(self) -> None:
        after = GRAMMAR.replace("    : Y\n", "    : Y?\n").replace(
            "\nc\n    : Z\n    ;\n", "\nd\n    : Z\n    ;\n"
        )
        # b rewritten and d added; c removed, so not a rule of the result.
        self.assertEqual(changed_rules(GRAMMAR, after), ["b", "d"])
        self.assertEqual(changed_rules(GRAMMAR, GRAMMAR), [])


class PatchDocumentationTest(unittest.TestCase):
    def test_only_patches_declared_not_applied_are_skipped(self) -> None:
        # A patch tagged for a language applies there, unless it says it doesn't.
        for language in LANGUAGES:
            with self.subTest(language=language):
                skipped = set(
                    re.findall(r"^\| (\w+) \|.*\| No \|$", patch_docs(language), re.M)
                )
                declared = {
                    key
                    for key, entry in PATCH_FILE.items()
                    if language in entry["language"] and entry.get("applied") is False
                }
                self.assertEqual(skipped, declared)

    def test_affected_rules_of_replacements_are_rules_of_the_grammar(self) -> None:
        for language in LANGUAGES:
            rules = grammar_rules(language)
            docs = patch_docs(language)
            for key, entry in PATCH_FILE.items():
                if language not in entry["language"] or not entry.get("replace"):
                    continue
                with self.subTest(language=language, fix=key):
                    section = re.search(
                        rf"^### Fix {re.escape(key)}: .*?(?=^### |^---)",
                        docs,
                        re.M | re.S,
                    )
                    self.assertIsNotNone(section)
                    listed = re.search(
                        r"\*\*Affected rules\*\*: (.*)", section.group(0)
                    )
                    self.assertIsNotNone(listed)
                    names = listed.group(1).split(", ")
                    if names == ["(only rules a later patch removes)"]:
                        continue
                    self.assertLessEqual(set(names), rules)


if __name__ == "__main__":
    result = unittest.main(exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
