#!/usr/bin/env python3
"""Layout of the generated SDKs: each grammar in its own folder of each target's, `sysml/` and `kerml/`."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generate_sdks


class SdkLayoutTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name)
        self.files = generate_sdks.grammar_files(
            generate_sdks.load_config(), generate_sdks.GRAMMARS
        )

    def run_antlr(self, command, cwd, capture_output, text):
        """Stand in for ANTLR: write one file named after each grammar file into `-o`."""
        out = Path(command[command.index("-o") + 1])
        for grammar in command[command.index("-lib") + 2 :]:
            (out / Path(grammar).with_suffix(".gen").name).write_text("generated")
        return subprocess.CompletedProcess(command, 0, "", "")

    def generate(self, grammars: list[str]) -> Path:
        files = {grammar: self.files[grammar] for grammar in grammars}
        with patch.object(generate_sdks.subprocess, "run", side_effect=self.run_antlr):
            code, _, _, _ = generate_sdks.generate_language("Go", self.output, files)
        self.assertEqual(code, 0)
        return self.output / "Go"

    def test_each_grammar_in_its_own_folder(self) -> None:
        target = self.generate(["sysml", "kerml"])
        self.assertEqual(sorted(p.name for p in target.iterdir()), ["kerml", "sysml"])
        self.assertEqual(
            sorted(p.name for p in (target / "sysml").iterdir()),
            ["SysMLv2Lexer.gen", "SysMLv2Parser.gen"],
        )
        self.assertEqual(
            sorted(p.name for p in (target / "kerml").iterdir()),
            ["KerMLLexer.gen", "KerMLParser.gen"],
        )

    def test_one_grammar_alone(self) -> None:
        self.assertEqual(
            sorted(p.name for p in self.generate(["sysml"]).iterdir()), ["sysml"]
        )
        self.assertEqual(
            sorted(p.name for p in self.generate(["kerml"]).iterdir()), ["kerml"]
        )

    def test_relative_output_root_is_resolved(self) -> None:
        # ANTLR runs from grammar/, so its output and library paths must be absolute.
        commands: list[list[str]] = []

        def run(command, cwd, capture_output, text):
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        with (
            patch.object(generate_sdks.subprocess, "run", side_effect=run),
            patch.object(generate_sdks, "ensure_clean_dir"),
            patch.object(Path, "mkdir"),
        ):
            generate_sdks.generate_language("Go", Path(".build/sdks"), self.files)
        self.assertEqual(len(commands), 2)
        for command in commands:
            for flag in ("-o", "-lib"):
                self.assertTrue(Path(command[command.index(flag) + 1]).is_absolute())

    def test_manifest_keeps_earlier_keys_and_names_each_folder(self) -> None:
        generate_sdks.write_manifest(self.output, ["Go"], generate_sdks.GRAMMARS)
        manifest = json.loads((self.output / "manifest.json").read_text())
        config = generate_sdks.load_config()
        self.assertEqual(manifest["grammar_version"], config["grammar_version"])
        self.assertEqual(manifest["release_tag"], config["release_tag"])
        self.assertEqual(manifest["languages"], ["Go"])
        self.assertEqual(manifest["grammars"]["sysml"]["directory"], "sysml")
        self.assertEqual(manifest["grammars"]["kerml"]["directory"], "kerml")
        self.assertEqual(manifest["grammars"]["kerml"]["parser"], "KerMLParser")


if __name__ == "__main__":
    result = unittest.main(exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
