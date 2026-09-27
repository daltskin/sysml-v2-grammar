"""Exercise the Makefile example runner with controlled Java process results."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


class ExampleRunnerTest(unittest.TestCase):
    def test_process_results(self):
        cases = (
            (0, "", True),
            (7, "", False),
            (0, "line 1:0 mismatched input", False),
            (7, "ClassCastException", False),
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / ".build/antlr-test/grammar").mkdir(parents=True)
            (workspace / "examples").mkdir()
            (workspace / "examples/control.sysml").write_text("package Control;\n")
            executable_directory = workspace / "bin"
            executable_directory.mkdir()
            java = executable_directory / "java"
            java.write_text(
                '#!/bin/sh\nprintf "%s" "$TEST_JAVA_STDERR" >&2\n'
                'exit "$TEST_JAVA_EXIT_CODE"\n'
            )
            java.chmod(0o755)

            for exit_code, stderr, should_pass in cases:
                with self.subTest(exit_code=exit_code, stderr=stderr):
                    environment = os.environ.copy()
                    environment.update(
                        TEST_JAVA_EXIT_CODE=str(exit_code),
                        TEST_JAVA_STDERR=stderr,
                        MAKEFLAGS="",
                        MFLAGS="",
                        MAKEOVERRIDES="",
                    )
                    result = subprocess.run(
                        [
                            "make",
                            "--no-print-directory",
                            "-f",
                            str(ROOT / "Makefile"),
                            f"PATH={executable_directory}:{os.defpath}",
                            "test-examples",
                        ],
                        cwd=workspace,
                        env=environment,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    output = result.stdout + result.stderr
                    self.assertEqual(result.returncode == 0, should_pass, output)
                    expected = (
                        "1 passed, 0 failed" if should_pass else "0 passed, 1 failed"
                    )
                    self.assertIn(expected, result.stdout)


if __name__ == "__main__":
    unittest.main()
