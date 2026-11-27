#!/usr/bin/env python3
"""SysML v2 and KerML Grammar Conformance Test Runner.

Parses official OMG SysML v2 Release files through the ANTLR4 Java grammars
and reports failures: the SysML files (training, validation, examples,
standard library) with the SysML grammar, and the KerML files (KerML
examples, Kernel Libraries) with the KerML grammar.

Usage:
    python scripts/conformance.py                     # Run all suites
    python scripts/conformance.py --language kerml    # Run one language's suites
    python scripts/conformance.py --suite validation  # Run one suite (of each language)
    python scripts/conformance.py --fetch             # Fetch fixtures first

Requires:
    - Java 17+ on PATH
    - ANTLR4 JAR at .build/antlr4.jar (run `make download-antlr`)
    - Compiled grammars at .build/antlr-test/ and .build/antlr-test-kerml/ (built automatically,
      and rebuilt when a grammar file changes)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / ".build"
ANTLR_JAR = BUILD_DIR / "antlr4.jar"
CONFIG_PATH = ROOT / "scripts" / "config.json"

# The runner's own compile directories: nothing else writes to them, so a
# directory's grammar stamp always describes the classes in it.
CONFORMANCE_BUILD_DIR = BUILD_DIR / "conformance"

# SysML: the compiled grammar and the fixtures fetched from the configured release.
SYSML_COMPILE_DIR = CONFORMANCE_BUILD_DIR / "sysml"
SYSML_GRAMMAR_CLASS_DIR = SYSML_COMPILE_DIR / "grammar"
SYSML_FIXTURES_DIR = ROOT / "test" / "fixtures" / "conformance"
# Standard library is fetched alongside the SysML conformance fixtures (not committed).
SYSML_LIBRARY_DIR = ROOT / "sysml.library"

# KerML: the compiled grammar and the fixtures fetched from KerML's configured release.
KERML_COMPILE_DIR = CONFORMANCE_BUILD_DIR / "kerml"
KERML_GRAMMAR_CLASS_DIR = KERML_COMPILE_DIR / "grammar"
KERML_FIXTURES_DIR = ROOT / "test" / "fixtures" / "kerml-conformance"
# Release directory -> fixture directory, all of them KerML.
KERML_FETCHED = {
    "kerml/src/examples": "examples",
    "sysml.library/Kernel Libraries": "library",
}

# The suites of each language, by language and suite name.
SUITES: dict[str, dict[str, dict]] = {
    "sysml": {
        "library": {
            "label": "Standard Library",
            "dir": SYSML_LIBRARY_DIR,
            "extensions": [".sysml"],
        },
        "training": {
            "label": "Official Training Examples",
            "dir": SYSML_FIXTURES_DIR / "training",
            "extensions": [".sysml"],
        },
        "validation": {
            "label": "Official Validation Models",
            "dir": SYSML_FIXTURES_DIR / "validation",
            "extensions": [".sysml"],
        },
        "examples": {
            "label": "Official SysML Examples",
            "dir": SYSML_FIXTURES_DIR / "examples",
            "extensions": [".sysml"],
        },
    },
    "kerml": {
        "examples": {
            "label": "Official KerML Examples",
            "dir": KERML_FIXTURES_DIR / "examples",
            "extensions": [".kerml"],
        },
        "library": {
            "label": "Kernel Libraries",
            "dir": KERML_FIXTURES_DIR / "library",
            "extensions": [".kerml"],
        },
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


# Written next to a compiled grammar: the digest of the grammar files it was compiled from.
GRAMMAR_STAMP = "grammar.sha256"


def grammar_digest(grammars: list[Path]) -> str:
    """The SHA-256 of the contents of `grammars`, in order, to tell a current compiled grammar from a stale one."""
    digest = hashlib.sha256()
    for grammar in grammars:
        digest.update(grammar.name.encode() + b"\0" + grammar.read_bytes() + b"\0")
    return digest.hexdigest()


def run_compiler(tool: str, command: list[str], cwd: Path) -> None:
    """Run one compilation step; on failure, print the tool's own messages and exit."""
    result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ {tool} failed (exit {result.returncode}):", file=sys.stderr)
        for output in (result.stdout, result.stderr):
            if output.strip():
                print(output.strip(), file=sys.stderr)
        sys.exit(1)


def ensure_grammar_compiled(compile_dir: Path, lexer: str, parser: str) -> None:
    """Compile a grammar with the ANTLR4 Java target into `compile_dir`/grammar, unless already compiled from the same grammar files.

    The lexer and parser paths are relative to ROOT. A changed grammar file, or a
    compiled grammar without the stamp of its grammar files, is compiled anew.
    """
    if not ANTLR_JAR.exists():
        print(
            "❌ ANTLR4 JAR not found. Run 'make download-antlr' first.", file=sys.stderr
        )
        sys.exit(1)

    class_dir = compile_dir / "grammar"
    stamp = class_dir / GRAMMAR_STAMP
    digest = grammar_digest([ROOT / lexer, ROOT / parser])
    if stamp.exists() and stamp.read_text() == digest:
        return

    print(f"  Compiling {Path(parser).stem} (Java target)...")
    # Start clean, so no class of a rule the grammar no longer has is left.
    shutil.rmtree(class_dir, ignore_errors=True)
    class_dir.mkdir(parents=True)

    # NOTE: ANTLR must be given *relative* grammar paths (with cwd=ROOT),
    # otherwise it writes the generated sources directly into compile_dir
    # instead of compile_dir/grammar/. The lexer's tokens file is written to
    # class_dir and read from there (-lib).
    run_compiler(
        "ANTLR",
        [
            "java",
            "-jar",
            str(ANTLR_JAR),
            "-Dlanguage=Java",
            "-o",
            str(compile_dir),
            "-lib",
            str(class_dir),
            lexer,
            parser,
        ],
        ROOT,
    )

    # NOTE: subprocess.run with a list does not perform shell glob
    # expansion, so "*.java" must be expanded in Python. Passing the
    # literal string makes javac fail with "invalid flag" / exit 2.
    java_sources = sorted(p.name for p in class_dir.glob("*.java"))
    if not java_sources:
        print(
            f"❌ ANTLR did not generate any Java sources in {class_dir}.",
            file=sys.stderr,
        )
        sys.exit(1)

    run_compiler("javac", ["javac", "-cp", f"{ANTLR_JAR}:.", *java_sources], class_dir)
    # Only a completed compilation is stamped, so a failed one is retried.
    stamp.write_text(digest)


def ensure_sysml_grammar_compiled() -> None:
    """SysML-specific: compile the SysML grammar, unless compiled from the current grammar files."""
    ensure_grammar_compiled(
        SYSML_COMPILE_DIR, "grammar/SysMLv2Lexer.g4", "grammar/SysMLv2Parser.g4"
    )


def ensure_kerml_grammar_compiled() -> None:
    """KerML-specific: compile the KerML grammar, unless compiled from the current grammar files."""
    ensure_grammar_compiled(
        KERML_COMPILE_DIR, "grammar/KerMLLexer.g4", "grammar/KerMLParser.g4"
    )


def parse_file(filepath: Path, grammar: str, class_dir: Path) -> ParseFailure | None:
    """Parse a single file through ANTLR4 TestRig with grammar `grammar` compiled in `class_dir`. Returns failure or None.

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
                grammar,
                "rootNamespace",
                str(filepath),
            ],
            cwd=str(class_dir),
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


def run_suite(name: str, suite: dict, grammar: str, class_dir: Path) -> SuiteResult:
    """Run conformance tests for a single suite, with the grammar `grammar` compiled in `class_dir`."""
    label = suite["label"]
    directory = Path(suite["dir"])
    extensions = suite["extensions"]

    files = find_files(directory, extensions)

    if not files:
        print(f"  ⚠  {label}: no files found (run --fetch to download)")
        return SuiteResult(name=name, label=label, total=0)

    failures: list[ParseFailure] = []
    for f in files:
        failure = parse_file(f, grammar, class_dir)
        if failure:
            failures.append(failure)

    return SuiteResult(name=name, label=label, total=len(files), failures=failures)


@contextmanager
def release_source() -> Iterator[Path]:
    """The source root of the configured release's archive, downloaded once and extracted into a temporary directory."""
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
    print(f"📥 Fetching the release archive of {repo}@{tag}...")

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
        yield roots[0]


def fetch_sysml_fixtures(src_root: Path | None = None) -> None:
    """SysML-specific: copy the SysML fixtures and the standard library from the release source (downloaded if not given)."""
    if src_root is None:
        with release_source() as root:
            fetch_sysml_fixtures(root)
        return

    print("  SysML conformance fixtures and standard library:")
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

    if SYSML_FIXTURES_DIR.exists():
        shutil.rmtree(SYSML_FIXTURES_DIR)
    SYSML_FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    for src_rel, dst_name in mapping.items():
        dst = SYSML_FIXTURES_DIR / dst_name
        shutil.copytree(src_root / src_rel, dst)
        count = len(list(dst.rglob("*.sysml")))
        print(f"  {dst_name}: {count} .sysml files")

    for sub in library_subdirs:
        target = SYSML_LIBRARY_DIR / sub
        if target.exists():
            shutil.rmtree(target)
    for item in src_lib.iterdir():
        if item.is_dir():
            dst = SYSML_LIBRARY_DIR / item.name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(item, dst)
    sysml_count = len(list(SYSML_LIBRARY_DIR.rglob("*.sysml")))
    kerml_count = len(list(SYSML_LIBRARY_DIR.rglob("*.kerml")))
    print(f"  Library: {sysml_count} .sysml, {kerml_count} .kerml files")

    print("\n✅ Conformance fixtures updated")


def fetch_kerml_fixtures(src_root: Path | None = None) -> None:
    """KerML-specific: copy the KerML examples and Kernel Libraries from the release source (downloaded if not given)."""
    if src_root is None:
        with release_source() as root:
            fetch_kerml_fixtures(root)
        return

    print("  KerML conformance fixtures:")
    # Validate every source before replacing the existing fixtures.
    for src_rel in KERML_FETCHED:
        if not find_files(src_root / src_rel, [".kerml"]):
            print(
                f"❌ Missing or empty KerML fixture directory: {src_rel}",
                file=sys.stderr,
            )
            sys.exit(1)
    if KERML_FIXTURES_DIR.exists():
        shutil.rmtree(KERML_FIXTURES_DIR)
    KERML_FIXTURES_DIR.mkdir(parents=True)
    for src_rel, dst_name in KERML_FETCHED.items():
        dst = KERML_FIXTURES_DIR / dst_name
        shutil.copytree(src_root / src_rel, dst)
        print(f"  {dst_name}: {len(find_files(dst, ['.kerml']))} .kerml files")


def fetch_fixtures(languages: list[str]) -> None:
    """Fetch the fixtures of `languages`, all from one download of the release archive."""
    with release_source() as src_root:
        for language in languages:
            LANGUAGES[language]["fetch"](src_root)


def _display_path(filepath: Path) -> str:
    """Relative path when under ROOT, absolute path otherwise."""
    try:
        return str(filepath.relative_to(ROOT))
    except ValueError:
        return str(filepath)


# A SysML file that MUST parse: exercises package/definition/usage and an expression.
SYSML_VALID_CONTROL = """package Control {
    part def P {
        attribute x : Integer = 1 + 2 * 3;
    }
    part p : P;
}
"""

# A SysML file that MUST be rejected: unbalanced brace and a stray operator.
SYSML_INVALID_CONTROL = """package Control {
    part def P {
        attribute x = 1 + ;
}
"""


# A KerML file that MUST parse: KerML declarations, a feature chain and an invariant.
KERML_VALID_CONTROL = """package Control {
    classifier C;
    class K :> C {
        feature x : C;
        feature y :> x.x;
        inv i { true }
    }
}
"""

# A KerML file that MUST be rejected: SysML syntax, an unbalanced brace and a stray operator.
KERML_INVALID_CONTROL = """package Control {
    part def P {
        feature x = 1 + ;
}
"""


def run_self_check(
    grammar: str,
    class_dir: Path,
    valid_control: str,
    invalid_control: str,
    suffix: str,
) -> None:
    """Verify the harness itself can distinguish valid from invalid input.

    Runs the TestRig pipeline on one known-good and one known-bad file before
    touching the real suites. If either control behaves unexpectedly, abort:
    a runner that cannot fail is worse than no runner at all (see the vacuous
    PASS history of this script).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        valid = Path(tmpdir) / f"valid{suffix}"
        valid.write_text(valid_control)
        failure = parse_file(valid, grammar, class_dir)
        if failure is not None:
            print(
                "❌ Self-check failed: known-VALID control was rejected:",
                file=sys.stderr,
            )
            print(f"   {failure.stderr}", file=sys.stderr)
            sys.exit(2)

        invalid = Path(tmpdir) / f"invalid{suffix}"
        invalid.write_text(invalid_control)
        failure = parse_file(invalid, grammar, class_dir)
        if failure is None:
            print(
                "❌ Self-check failed: known-INVALID control was accepted. "
                "The harness cannot detect syntax errors; refusing to run.",
                file=sys.stderr,
            )
            sys.exit(2)

    print("  ✅ Self-check: valid control accepted, invalid control rejected")


# What each language's suites run with: the grammar, how to compile and fetch,
# and the self-check controls.
LANGUAGES: dict[str, dict] = {
    "sysml": {
        "title": "SysML v2 Grammar Conformance Tests",
        "grammar": "SysMLv2",
        "class_dir": SYSML_GRAMMAR_CLASS_DIR,
        "compile": ensure_sysml_grammar_compiled,
        "fetch": fetch_sysml_fixtures,
        "controls": (SYSML_VALID_CONTROL, SYSML_INVALID_CONTROL, ".sysml"),
    },
    "kerml": {
        "title": "KerML Grammar Conformance Tests",
        "grammar": "KerML",
        "class_dir": KERML_GRAMMAR_CLASS_DIR,
        "compile": ensure_kerml_grammar_compiled,
        "fetch": fetch_kerml_fixtures,
        "controls": (KERML_VALID_CONTROL, KERML_INVALID_CONTROL, ".kerml"),
    },
}


def run_language(
    language: str, suites: dict[str, dict], verbose: bool
) -> list[SuiteResult]:
    """Run one language's suites, after its self-check, and print each result."""
    spec = LANGUAGES[language]
    print(spec["title"])
    print("=" * 50)
    spec["compile"]()
    run_self_check(spec["grammar"], spec["class_dir"], *spec["controls"])
    results: list[SuiteResult] = []
    for name, suite in suites.items():
        result = run_suite(name, suite, spec["grammar"], spec["class_dir"])
        results.append(result)
        if result.total == 0:
            continue
        if result.passed:
            print(f"  ✅ {result.label}: {result.total}/{result.total} passed")
        else:
            failed = len(result.failures)
            passed = result.total - failed
            print(
                f"  ❌ {result.label}: {passed}/{result.total} passed ({failed} failures)"
            )
            if verbose:
                for f in result.failures:
                    print(f"       ✗ {f.file} — {f.stderr}")
    print()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SysML v2 and KerML Grammar Conformance Tests"
    )
    parser.add_argument(
        "--fetch", action="store_true", help="Fetch/update fixtures from OMG repo"
    )
    parser.add_argument(
        "--language",
        choices=list(SUITES.keys()),
        help="Only this language's suites (default: all)",
    )
    parser.add_argument(
        "--suite",
        choices=sorted({name for suites in SUITES.values() for name in suites}),
        help="Run only this suite, of each language that has it",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show individual file failures"
    )
    args = parser.parse_args()

    languages = [args.language] if args.language else list(SUITES.keys())

    if args.fetch:
        fetch_fixtures(languages)
        return

    # A suite that none of the selected languages has would run nothing and pass.
    if args.suite and not any(args.suite in SUITES[lang] for lang in languages):
        parser.error(
            f"suite {args.suite!r} does not exist for {' or '.join(languages)}; "
            f"its suites are: {', '.join(sorted(n for lang in languages for n in SUITES[lang]))}"
        )

    results: list[SuiteResult] = []
    for language in languages:
        suites = SUITES[language]
        if args.suite:
            if args.suite not in suites:
                continue
            suites = {args.suite: suites[args.suite]}
        results += run_language(language, suites, args.verbose)

    # Summary
    total_files = sum(r.total for r in results)
    total_failures = sum(len(r.failures) for r in results)
    print(
        f"📊 Total: {total_files - total_failures}/{total_files} files passed across {len(results)} suites"
    )

    if total_failures:
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
