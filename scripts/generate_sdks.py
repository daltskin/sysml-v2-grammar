#!/usr/bin/env python3
"""Generate language-specific ANTLR4 SDK source trees.

By default this script emits source SDKs for every target language bundled with
the pinned ANTLR4 JAR.  A specific target can be generated with `--language`.

Examples:
    python scripts/generate_sdks.py
    python scripts/generate_sdks.py --language Cpp
    python scripts/generate_sdks.py --archive
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / ".build"
RELEASE_DIR = BUILD_DIR / "releases"
OUTPUT_ROOT = BUILD_DIR / "sdks"
ANTLR_JAR = BUILD_DIR / "antlr4.jar"
CONFIG_PATH = ROOT / "scripts" / "config.json"
GRAMMAR_DIR = ROOT / "grammar"
GRAMMAR_FILES = ["SysMLv2Lexer.g4", "SysMLv2Parser.g4"]

TARGET_PREFIX = "org/antlr/v4/codegen/target/"
TARGET_SUFFIX = "Target.class"


def load_config() -> dict:
    """Read repository configuration once so release metadata stays in sync."""
    with open(CONFIG_PATH) as f:
        return json.load(f)


def discover_languages() -> list[str]:
    """Discover official ANTLR4 code generation targets from the pinned JAR."""
    if not ANTLR_JAR.exists():
        print(f"❌ ANTLR4 JAR not found: {ANTLR_JAR}", file=sys.stderr)
        print("   Run `make sdk` or `make test` to download it first.", file=sys.stderr)
        sys.exit(1)

    languages: set[str] = set()
    with zipfile.ZipFile(ANTLR_JAR) as jar:
        for member in jar.namelist():
            if not member.startswith(TARGET_PREFIX) or not member.endswith(
                TARGET_SUFFIX
            ):
                continue

            language = member.removeprefix(TARGET_PREFIX).removesuffix(TARGET_SUFFIX)
            if not language or "/" in language:
                continue

            # Ignore the abstract base target and keep only concrete generators.
            if language == "Target":
                continue

            languages.add(language)

    return sorted(languages)


def resolve_languages(requested: list[str], supported: list[str]) -> list[str]:
    """Validate user-selected targets while preserving the requested order."""
    if not requested:
        return supported

    missing = [language for language in requested if language not in supported]
    if missing:
        supported_text = ", ".join(supported)
        missing_text = ", ".join(missing)
        print(f"❌ Unsupported ANTLR4 target(s): {missing_text}", file=sys.stderr)
        print(f"   Supported targets: {supported_text}", file=sys.stderr)
        sys.exit(2)

    # Deduplicate without scrambling the user's preferred order.
    return list(dict.fromkeys(requested))


def ensure_clean_dir(path: Path) -> None:
    """Remove stale generated files before writing a fresh target tree."""
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def count_generated_files(path: Path) -> int:
    """Count generated files for a compact success summary."""
    return sum(1 for item in path.rglob("*") if item.is_file())


def generate_language(language: str, output_root: Path) -> None:
    """Generate one target-language SDK with ANTLR4."""
    output_dir = output_root / language
    ensure_clean_dir(output_dir)

    # Run from grammar/ so ANTLR writes files directly into the target directory
    # instead of nesting another `grammar/` level in the output tree.
    cmd = [
        "java",
        "-jar",
        str(ANTLR_JAR),
        f"-Dlanguage={language}",
        "-listener",
        "-visitor",
        "-o",
        str(output_dir),
        *GRAMMAR_FILES,
    ]

    result = subprocess.run(
        cmd,
        cwd=GRAMMAR_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"❌ Failed to generate {language} SDK", file=sys.stderr)
        if result.stdout.strip():
            print(result.stdout.strip(), file=sys.stderr)
        if result.stderr.strip():
            print(result.stderr.strip(), file=sys.stderr)
        sys.exit(result.returncode)

    print(f"  ✅ {language:<10} {count_generated_files(output_dir)} file(s)")


def write_manifest(output_root: Path, languages: list[str]) -> None:
    """Keep the generated output self-describing for release consumers."""
    config = load_config()
    manifest = {
        "grammar_version": config["grammar_version"],
        "release_tag": config["release_tag"],
        "languages": languages,
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def archive_sdks(output_root: Path) -> Path:
    """Package the generated SDK trees into the release archive."""
    config = load_config()
    version = config["grammar_version"]
    archive_name = f"sysml-v2-sdks-{version}.zip"
    archive_path = RELEASE_DIR / archive_name
    archive_root = Path(archive_name.removesuffix(".zip"))

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        archive_path.unlink()

    with zipfile.ZipFile(
        archive_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for path in sorted(output_root.rglob("*")):
            if path.is_dir():
                continue
            archive.write(path, archive_root / path.relative_to(output_root))

    print()
    print(f"📦 SDK archive: {archive_path}")
    return archive_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate language-specific ANTLR4 SDK source trees"
    )
    parser.add_argument(
        "--language",
        action="append",
        default=[],
        help="Generate only the named ANTLR4 target (repeatable)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=OUTPUT_ROOT,
        help=f"Directory for generated SDKs (default: {OUTPUT_ROOT.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Zip the generated SDKs into .build/releases/",
    )
    args = parser.parse_args()

    supported = discover_languages()
    languages = resolve_languages(args.language, supported)

    # Start from a clean root so the manifest and archive never mix targets from
    # different runs.
    ensure_clean_dir(args.output_root)

    print("🛠️  Generating ANTLR4 SDKs")
    print(f"   Targets: {', '.join(languages)}")
    print(f"   Output:  {args.output_root}")

    for language in languages:
        generate_language(language, args.output_root)

    write_manifest(args.output_root, languages)

    if args.archive:
        archive_sdks(args.output_root)

    print()
    print("✅ SDK generation complete")


if __name__ == "__main__":
    main()
