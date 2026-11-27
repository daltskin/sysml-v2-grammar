"""Verify the conformance runner: each grammar compiled anew when it changes, and suite selection."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import conformance

ROOT = Path(__file__).resolve().parent.parent


class ConformanceCompileTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "grammar").mkdir()
        for name in (
            "SysMLv2Lexer.g4",
            "SysMLv2Parser.g4",
            "KerMLLexer.g4",
            "KerMLParser.g4",
        ):
            (self.root / "grammar" / name).write_text(f"grammar {name};\n")
        build = self.root / ".build"
        build.mkdir()
        self.jar = build / "antlr4.jar"
        self.jar.write_text("jar")
        self.sysml_dir = build / "conformance" / "sysml"
        self.kerml_dir = build / "conformance" / "kerml"
        self.calls: list[str] = []
        self.failing_tool = ""

        contexts = ExitStack()
        self.addCleanup(contexts.close)
        contexts.enter_context(redirect_stdout(io.StringIO()))
        self.stderr = contexts.enter_context(redirect_stderr(io.StringIO()))
        for name, value in (
            ("ROOT", self.root),
            ("BUILD_DIR", build),
            ("ANTLR_JAR", self.jar),
            ("SYSML_COMPILE_DIR", self.sysml_dir),
            ("SYSML_GRAMMAR_CLASS_DIR", self.sysml_dir / "grammar"),
            ("KERML_COMPILE_DIR", self.kerml_dir),
            ("KERML_GRAMMAR_CLASS_DIR", self.kerml_dir / "grammar"),
        ):
            contexts.enter_context(patch.object(conformance, name, value))
        contexts.enter_context(
            patch.object(conformance.subprocess, "run", side_effect=self.run_tool)
        )

    def run_tool(self, command, cwd, capture_output, text):
        """Stand in for ANTLR (writes a Java source) and javac (writes a class)."""
        tool = "antlr" if command[0] == "java" else "javac"
        self.calls.append(tool)
        if tool == self.failing_tool:
            return subprocess.CompletedProcess(
                command, 1, "", f"{tool}: rule x undefined"
            )
        if tool == "antlr":
            parser = Path(command[-1]).stem
            out = Path(command[command.index("-o") + 1]) / "grammar"
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{parser}.java").write_text("source")
        else:
            for source in Path(cwd).glob("*.java"):
                source.with_suffix(".class").write_text("class")
        return subprocess.CompletedProcess(command, 0, "", "")

    def compile_kerml(self) -> list[str]:
        """The tool calls of one KerML compilation request."""
        self.calls = []
        conformance.ensure_kerml_grammar_compiled()
        return self.calls

    def test_stale_parser_without_stamp_is_compiled(self):
        # A parser compiled before the stamp existed, older than its grammar.
        class_dir = self.kerml_dir / "grammar"
        class_dir.mkdir(parents=True)
        (class_dir / "KerMLParser.class").write_text("old class")
        (class_dir / "KerMLParser$GoneContext.class").write_text("old class")

        self.assertEqual(self.compile_kerml(), ["antlr", "javac"])
        self.assertEqual((class_dir / "KerMLParser.class").read_text(), "class")
        self.assertFalse((class_dir / "KerMLParser$GoneContext.class").exists())

    def test_unchanged_grammar_is_not_compiled_again(self):
        self.assertEqual(self.compile_kerml(), ["antlr", "javac"])
        self.assertEqual(self.compile_kerml(), [])

    def test_changed_grammar_file_is_compiled_again(self):
        for name in ("KerMLParser.g4", "KerMLLexer.g4"):
            with self.subTest(changed=name):
                self.compile_kerml()
                grammar = self.root / "grammar" / name
                grammar.write_text(grammar.read_text() + "// changed\n")
                self.assertEqual(self.compile_kerml(), ["antlr", "javac"])
                self.assertEqual(self.compile_kerml(), [])

    def test_failed_compilation_reports_the_tool_output_and_is_retried(self):
        for tool, calls in (("antlr", ["antlr"]), ("javac", ["antlr", "javac"])):
            with self.subTest(tool=tool):
                grammar = self.root / "grammar" / "KerMLParser.g4"
                grammar.write_text(grammar.read_text() + f"// {tool}\n")
                self.failing_tool = tool
                with self.assertRaises(SystemExit) as error:
                    self.compile_kerml()
                self.assertEqual(error.exception.code, 1)
                self.assertEqual(self.calls, calls)
                self.assertIn(f"{tool}: rule x undefined", self.stderr.getvalue())
                self.failing_tool = ""
                self.assertEqual(self.compile_kerml(), ["antlr", "javac"])

    def test_each_language_compiles_its_own_grammar(self):
        conformance.ensure_sysml_grammar_compiled()
        conformance.ensure_kerml_grammar_compiled()
        self.assertTrue((self.sysml_dir / "grammar" / "SysMLv2Parser.class").exists())
        self.assertTrue((self.kerml_dir / "grammar" / "KerMLParser.class").exists())

        # A KerML grammar change leaves the compiled SysML grammar current, and back.
        kerml = self.root / "grammar" / "KerMLParser.g4"
        kerml.write_text(kerml.read_text() + "// changed\n")
        self.calls = []
        conformance.ensure_sysml_grammar_compiled()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.compile_kerml(), ["antlr", "javac"])

        sysml = self.root / "grammar" / "SysMLv2Lexer.g4"
        sysml.write_text(sysml.read_text() + "// changed\n")
        self.calls = []
        conformance.ensure_sysml_grammar_compiled()
        self.assertEqual(self.calls, ["antlr", "javac"])
        self.assertEqual(self.compile_kerml(), [])


class ConformanceBuildDirectoryTest(unittest.TestCase):
    def test_no_other_build_step_writes_to_the_runner_directories(self):
        # A grammar stamp describes the classes in its directory only if nothing
        # else compiles into it: no Makefile step may write there.
        makefile = (ROOT / "Makefile").read_text()
        written = set(re.findall(r"\$\(BUILD_DIR\)/([\w.-]+)", makefile))
        runner = {
            conformance.SYSML_COMPILE_DIR.relative_to(conformance.BUILD_DIR).parts[0],
            conformance.KERML_COMPILE_DIR.relative_to(conformance.BUILD_DIR).parts[0],
        }
        self.assertTrue(written, "no build directories found in the Makefile")
        self.assertEqual(written & runner, set())
        self.assertNotEqual(
            conformance.SYSML_COMPILE_DIR, conformance.KERML_COMPILE_DIR
        )


class ConformanceSuiteSelectionTest(unittest.TestCase):
    def run_main(self, *args: str) -> tuple[int, list[str]]:
        """The exit code of the runner with `args`, and the languages it ran."""
        ran: list[str] = []

        def run_language(language, suites, verbose):
            ran.append(language)
            return []

        stderr = io.StringIO()
        with (
            patch.object(sys, "argv", ["conformance.py", *args]),
            patch.object(conformance, "run_language", side_effect=run_language),
            redirect_stdout(io.StringIO()),
            redirect_stderr(stderr),
        ):
            try:
                conformance.main()
            except SystemExit as exit_:
                return int(exit_.code or 0), ran
        return 0, ran

    def test_suite_of_no_selected_language_is_an_error(self):
        for args in (
            ("--language", "kerml", "--suite", "training"),
            ("--language", "kerml", "--suite", "validation"),
            ("--language", "sysml", "--suite", "library-kerml-only"),
        ):
            with self.subTest(args=args):
                code, ran = self.run_main(*args)
                self.assertEqual(code, 2)
                self.assertEqual(ran, [])

    def test_suite_runs_in_each_selected_language_that_has_it(self):
        shared = set(conformance.SUITES["sysml"]) & set(conformance.SUITES["kerml"])
        only_sysml = set(conformance.SUITES["sysml"]) - set(conformance.SUITES["kerml"])
        self.assertTrue(shared and only_sysml)
        self.assertEqual(
            self.run_main("--suite", sorted(shared)[0]), (0, ["sysml", "kerml"])
        )
        self.assertEqual(
            self.run_main("--suite", sorted(only_sysml)[0]), (0, ["sysml"])
        )
        self.assertEqual(self.run_main(), (0, ["sysml", "kerml"]))


if __name__ == "__main__":
    unittest.main()
