#!/usr/bin/env python3
"""SysML v2 Grammar Conformance Test Runner.

Parses official OMG SysML v2 Release files (training, validation, examples,
standard library) through the ANTLR4 Java grammar and reports failures.

Usage:
    python scripts/conformance.py                    # Run all suites
    python scripts/conformance.py --suite validation  # Run one suite
    python scripts/conformance.py --fetch             # Fetch fixtures first

Requires:
    - Java 17+ on PATH
    - ANTLR4 JAR at .build/antlr4.jar (run `make download-antlr`)
    - Compiled grammar at .build/antlr-test/ (built automatically)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / ".build"
ANTLR_JAR = BUILD_DIR / "antlr4.jar"
GRAMMAR_CLASS_DIR = BUILD_DIR / "antlr-test" / "grammar"
FIXTURES_DIR = ROOT / "test" / "fixtures" / "conformance"
CONFIG_PATH = ROOT / "scripts" / "config.json"

# Standard library is fetched alongside the conformance fixtures (not committed).
LIBRARY_DIR = ROOT / "sysml.library"

SUITES: dict[str, dict] = {
    "library": {
        "label": "Standard Library",
        "dir": LIBRARY_DIR,
        "extensions": [".sysml"],
    },
    "training": {
        "label": "Official Training Examples",
        "dir": FIXTURES_DIR / "training",
        "extensions": [".sysml"],
    },
    "validation": {
        "label": "Official Validation Models",
        "dir": FIXTURES_DIR / "validation",
        "extensions": [".sysml"],
    },
    "examples": {
        "label": "Official SysML Examples",
        "dir": FIXTURES_DIR / "examples",
        "extensions": [".sysml"],
    },
}


@dataclass
class ParseFailure:
    file: str
    stderr: str


@dataclass
class SuiteResult:
    name: str
    label: str
    total: int
    failures: list[ParseFailure] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


def find_files(directory: Path, extensions: list[str]) -> list[Path]:
    """Recursively find files matching given extensions."""
    if not directory.exists():
        return []
    results = []
    for ext in extensions:
        results.extend(directory.rglob(f"*{ext}"))
    return sorted(results)


def ensure_grammar_compiled() -> None:
    """Compile the grammar with ANTLR4 Java target if not already done."""
    if not ANTLR_JAR.exists():
        print(
            "❌ ANTLR4 JAR not found. Run 'make download-antlr' first.", file=sys.stderr
        )
        sys.exit(1)

    # Check if already compiled
    if (GRAMMAR_CLASS_DIR / "SysMLv2Parser.class").exists():
        return

    print("  Compiling grammar (Java target)...")
    compile_dir = BUILD_DIR / "antlr-test"
    compile_dir.mkdir(parents=True, exist_ok=True)

    # NOTE: ANTLR must be given *relative* grammar paths (with cwd=ROOT),
    # otherwise it writes the generated sources directly into compile_dir
    # instead of compile_dir/grammar/, and the javac step below fails
    # because its cwd (GRAMMAR_CLASS_DIR) does not exist.
    subprocess.run(
        [
            "java",
            "-jar",
            ".build/antlr4.jar",
            "-Dlanguage=Java",
            "-o",
            str(compile_dir),
            "grammar/SysMLv2Lexer.g4",
            "grammar/SysMLv2Parser.g4",
        ],
        cwd=str(ROOT),
        check=True,
        capture_output=True,
    )

    # NOTE: subprocess.run with a list does not perform shell glob
    # expansion, so "*.java" must be expanded in Python. Passing the
    # literal string makes javac fail with "invalid flag" / exit 2.
    java_sources = sorted(p.name for p in GRAMMAR_CLASS_DIR.glob("*.java"))
    if not java_sources:
        print(
            f"❌ ANTLR did not generate any Java sources in {GRAMMAR_CLASS_DIR}.",
            file=sys.stderr,
        )
        sys.exit(1)

    subprocess.run(
        ["javac", "-cp", f"{ANTLR_JAR}:.", *java_sources],
        cwd=str(GRAMMAR_CLASS_DIR),
        check=True,
        capture_output=True,
    )


def parse_file(filepath: Path) -> ParseFailure | None:
    """Parse a single file through ANTLR4 TestRig. Returns failure or None.

    Fails on ANY signal of trouble, not just recognized message patterns:
      - nonzero process exit (TestRig usually exits 0 even on syntax errors,
        but infrastructure failures such as missing classes exit nonzero)
      - subprocess timeout
      - ANY non-empty stderr (ANTLR reports syntax errors on stderr with
        "line N:M ..." messages that need not contain the word "error")

    The previous substring check ("error" or "line ") silently swallowed
    infrastructure failures such as the ClassCastException from invoking
    TestRig with the parser's class name instead of the grammar base name,
    reporting every file as PASS without parsing it at all.
    """
    try:
        result = subprocess.run(
            [
                "java",
                "-cp",
                f"{ANTLR_JAR}:.",
                "org.antlr.v4.gui.TestRig",
                # TestRig derives "<grammarName>Lexer" and "<grammarName>Parser"
                # from the first argument, so it must be the grammar base name
                # "SysMLv2" -- passing "SysMLv2Parser" loads the parser class as
                # the lexer and throws ClassCastException on every invocation,
                # which the old failure detection silently ignored.
                "SysMLv2",
                "rootNamespace",
                str(filepath),
            ],
            cwd=str(GRAMMAR_CLASS_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return ParseFailure(file=_display_path(filepath), stderr="timed out after 120s")

    if result.returncode != 0:
        detail = (
            result.stderr.strip().split("\n")[0][:120] or f"exit {result.returncode}"
        )
        return ParseFailure(
            file=_display_path(filepath), stderr=f"exit {result.returncode}: {detail}"
        )

    stderr = result.stderr.strip()
    if stderr:
        first_line = stderr.split("\n")[0][:120]
        return ParseFailure(file=_display_path(filepath), stderr=first_line)
    return None


def run_suite(name: str, suite: dict) -> SuiteResult:
    """Run conformance tests for a single suite."""
    label = suite["label"]
    directory = Path(suite["dir"])
    extensions = suite["extensions"]

    files = find_files(directory, extensions)

    if not files:
        print(f"  ⚠  {label}: no files found (run --fetch to download)")
        return SuiteResult(name=name, label=label, total=0)

    failures: list[ParseFailure] = []
    for f in files:
        failure = parse_file(f)
        if failure:
            failures.append(failure)

    return SuiteResult(name=name, label=label, total=len(files), failures=failures)


def fetch_fixtures() -> None:
    """Download fixtures and the standard library from the configured release."""
    with open(CONFIG_PATH) as config_file:
        config = json.load(config_file)
    repo = config["release_repo"]
    tag = config["release_tag"]
    if not isinstance(repo, str) or not re.fullmatch(
        r"[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+", repo
    ):
        print(f"❌ Invalid release repository: {repo!r}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(tag, str) or not re.fullmatch(r"[a-zA-Z0-9._-]+", tag):
        print(f"❌ Invalid release tag: {tag!r}", file=sys.stderr)
        sys.exit(1)
    archive_url = f"https://github.com/{repo}/archive/refs/tags/{tag}.tar.gz"
    print(f"📥 Fetching conformance fixtures and standard library from {repo}@{tag}...")

    with tempfile.TemporaryDirectory() as tmpdir:
        archive_path = Path(tmpdir) / "release.tar.gz"
        urllib.request.urlretrieve(archive_url, str(archive_path))

        extract_dir = Path(tmpdir) / "extracted"
        extract_dir.mkdir()

        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=str(extract_dir), filter="data")

        roots = list(extract_dir.iterdir())
        if len(roots) != 1 or not roots[0].is_dir():
            print(f"❌ Unexpected archive structure: {roots}", file=sys.stderr)
            sys.exit(1)
        src_root = roots[0]

        mapping = {
            "sysml/src/training": "training",
            "sysml/src/validation": "validation",
            "sysml/src/examples": "examples",
        }
        library_subdirs = ("Domain Libraries", "Kernel Libraries", "Systems Library")
        src_lib = src_root / "sysml.library"

        # Validate every source before replacing the existing fixtures or library.
        for src_rel in mapping:
            if not find_files(src_root / src_rel, [".sysml"]):
                print(f"❌ Missing or empty fixture suite: {src_rel}", file=sys.stderr)
                sys.exit(1)
        for sub in library_subdirs:
            if not find_files(src_lib / sub, [".sysml", ".kerml"]):
                print(
                    f"❌ Missing or empty standard library directory: {sub}",
                    file=sys.stderr,
                )
                sys.exit(1)

        if FIXTURES_DIR.exists():
            shutil.rmtree(FIXTURES_DIR)
        FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
        for src_rel, dst_name in mapping.items():
            dst = FIXTURES_DIR / dst_name
            shutil.copytree(src_root / src_rel, dst)
            count = len(list(dst.rglob("*.sysml")))
            print(f"  {dst_name}: {count} .sysml files")

        for sub in library_subdirs:
            target = LIBRARY_DIR / sub
            if target.exists():
                shutil.rmtree(target)
        for item in src_lib.iterdir():
            if item.is_dir():
                dst = LIBRARY_DIR / item.name
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(item, dst)
        sysml_count = len(list(LIBRARY_DIR.rglob("*.sysml")))
        kerml_count = len(list(LIBRARY_DIR.rglob("*.kerml")))
        print(f"  Library: {sysml_count} .sysml, {kerml_count} .kerml files")

    print("\n✅ Conformance fixtures updated")


def _display_path(filepath: Path) -> str:
    """Relative path when under ROOT, absolute path otherwise."""
    try:
        return str(filepath.relative_to(ROOT))
    except ValueError:
        return str(filepath)


# A file that MUST parse: exercises package/definition/usage and an expression.
VALID_CONTROL = """package Control {
    part def P {
        attribute x : Integer = 1 + 2 * 3;
    }
    part p : P;
}
"""

# A file that MUST be rejected: unbalanced brace and a stray operator.
INVALID_CONTROL = """package Control {
    part def P {
        attribute x = 1 + ;
}
"""


def run_self_check() -> None:
    """Verify the harness itself can distinguish valid from invalid input.

    Runs the TestRig pipeline on one known-good and one known-bad file before
    touching the real suites. If either control behaves unexpectedly, abort:
    a runner that cannot fail is worse than no runner at all (see the vacuous
    PASS history of this script).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        valid = Path(tmpdir) / "valid.sysml"
        valid.write_text(VALID_CONTROL)
        failure = parse_file(valid)
        if failure is not None:
            print(
                "❌ Self-check failed: known-VALID control was rejected:",
                file=sys.stderr,
            )
            print(f"   {failure.stderr}", file=sys.stderr)
            sys.exit(2)

        invalid = Path(tmpdir) / "invalid.sysml"
        invalid.write_text(INVALID_CONTROL)
        failure = parse_file(invalid)
        if failure is None:
            print(
                "❌ Self-check failed: known-INVALID control was accepted. "
                "The harness cannot detect syntax errors; refusing to run.",
                file=sys.stderr,
            )
            sys.exit(2)

    print("  ✅ Self-check: valid control accepted, invalid control rejected")


def main() -> None:
    parser = argparse.ArgumentParser(description="SysML v2 Grammar Conformance Tests")
    parser.add_argument(
        "--fetch", action="store_true", help="Fetch/update fixtures from OMG repo"
    )
    parser.add_argument(
        "--suite", choices=list(SUITES.keys()), help="Run only this suite"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show individual file failures"
    )
    args = parser.parse_args()

    if args.fetch:
        fetch_fixtures()
        return

    print("SysML v2 Grammar Conformance Tests")
    print("=" * 50)

    ensure_grammar_compiled()

    run_self_check()

    suites_to_run = {args.suite: SUITES[args.suite]} if args.suite else SUITES
    results: list[SuiteResult] = []
    any_failure = False

    for name, suite in suites_to_run.items():
        result = run_suite(name, suite)
        results.append(result)

        if result.total == 0:
            continue

        if result.passed:
            print(f"  ✅ {result.label}: {result.total}/{result.total} passed")
        else:
            any_failure = True
            failed = len(result.failures)
            passed = result.total - failed
            print(
                f"  ❌ {result.label}: {passed}/{result.total} passed ({failed} failures)"
            )
            if args.verbose:
                for f in result.failures:
                    print(f"       ✗ {f.file} — {f.stderr}")

    # Summary
    print()
    total_files = sum(r.total for r in results)
    total_failures = sum(len(r.failures) for r in results)
    print(
        f"📊 Total: {total_files - total_failures}/{total_files} files passed across {len(results)} suites"
    )

    if any_failure:
        print()
        print("Failing files:")
        for r in results:
            for f in r.failures:
                print(f"  ✗ {f.file}")
                print(f"    {f.stderr}")
        sys.exit(1)
    else:
        print("\n✅ All conformance tests passed")


if __name__ == "__main__":
    main()
