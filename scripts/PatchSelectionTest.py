#!/usr/bin/env python3
"""Selection of a grammar's patches by the `language` list of each patch-file entry."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from generate_grammar import language_patches

ROOT = Path(__file__).resolve().parent.parent
LANGUAGES = {"sysml", "kerml"}


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
        patch_file = json.loads((ROOT / "scripts" / "patches.json").read_text())
        for key, fix in patch_file.items():
            with self.subTest(fix=key):
                self.assertTrue(fix.get("language"))
                self.assertLessEqual(set(fix["language"]), LANGUAGES)

    def test_unreachable_rule_removal_is_applied_last(self) -> None:
        # Fix 52 removes the rules no other patch has made reachable.
        patch_file = json.loads((ROOT / "scripts" / "patches.json").read_text())
        for language in LANGUAGES:
            with self.subTest(language=language):
                self.assertEqual(language_patches(patch_file, language)[-1]["id"], "52")


if __name__ == "__main__":
    result = unittest.main(exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
