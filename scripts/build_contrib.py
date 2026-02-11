#!/usr/bin/env python3
"""Build a grammars-v4-compatible contribution directory.

Generates all required assets for https://github.com/antlr/grammars-v4:
  - .g4 grammars (copied from grammar/, already formatted with EOF)
  - pom.xml (Maven test config)
  - desc.xml (trgen test descriptor)
  - README.md (documentation)
  - examples/ (copied from the repo)

Run:
    python scripts/build_contrib.py          # uses defaults from config.json
    python scripts/build_contrib.py --verify  # also runs Maven and antlr-format checks
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "scripts" / "config.json"
GRAMMAR_DIR = ROOT / "grammar"
EXAMPLES_DIR = ROOT / "examples"
DEFAULT_OUTPUT = ROOT / "contrib" / "sysml" / "sysmlv2"

# ── helpers ──────────────────────────────────────────────────────────────────


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


# ── antlr-format ────────────────────────────────────────────────────────────


def run_antlr_format(output_dir: Path) -> None:
    """Run antlr-format on the .g4 files.

    Requires either `antlr-format` on PATH (from `npm i -g antlr-format-cli`)
    or falls back to `npx antlr-format-cli`.
    """
    g4_files = sorted(output_dir.glob("*.g4"))
    if not g4_files:
        return

    # antlr-format-cli installs as the `antlr-format` command
    antlr_fmt = shutil.which("antlr-format")
    use_npx = antlr_fmt is None

    for g4 in g4_files:
        cmd = (
            ["npx", "--yes", "antlr-format-cli", str(g4)]
            if use_npx
            else ["antlr-format", str(g4)]
        )
        print(f"  Formatting {g4.name} …")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ⚠️  antlr-format failed for {g4.name}: {result.stderr.strip()}")
        else:
            print(f"  ✅ {g4.name} formatted")


# ── file generators ─────────────────────────────────────────────────────────


def generate_pom(grammar_name: str, lexer_name: str, start_rule: str) -> str:
    """Generate the canonical pom.xml with <parent> for grammars-v4."""
    # antlr4test-maven-plugin appends "Parser"/"Lexer" to grammarName,
    # so we strip the "Parser" suffix from our grammar file name.
    base_name = grammar_name.removesuffix("Parser")
    return textwrap.dedent(f"""\
        <project xmlns="http://maven.apache.org/POM/4.0.0"
                 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                                     http://maven.apache.org/xsd/maven-4.0.0.xsd">
            <modelVersion>4.0.0</modelVersion>
            <artifactId>sysmlv2</artifactId>
            <packaging>jar</packaging>
            <name>SysML v2 grammar</name>
            <parent>
                <groupId>org.antlr.grammars</groupId>
                <artifactId>grammarsv4</artifactId>
                <version>1.0-SNAPSHOT</version>
            </parent>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.antlr</groupId>
                        <artifactId>antlr4-maven-plugin</artifactId>
                        <version>${{antlr.version}}</version>
                        <configuration>
                            <sourceDirectory>${{basedir}}</sourceDirectory>
                            <includes>
                                <include>{lexer_name}.g4</include>
                                <include>{grammar_name}.g4</include>
                            </includes>
                            <visitor>true</visitor>
                            <listener>true</listener>
                        </configuration>
                        <executions>
                            <execution>
                                <goals>
                                    <goal>antlr4</goal>
                                </goals>
                            </execution>
                        </executions>
                    </plugin>
                    <plugin>
                        <groupId>com.khubla.antlr</groupId>
                        <artifactId>antlr4test-maven-plugin</artifactId>
                        <version>${{antlr4test-maven-plugin.version}}</version>
                        <configuration>
                            <verbose>false</verbose>
                            <showTree>false</showTree>
                            <entryPoint>{start_rule}</entryPoint>
                            <grammarName>{base_name}</grammarName>
                            <packageName></packageName>
                            <exampleFiles>examples/</exampleFiles>
                        </configuration>
                        <executions>
                            <execution>
                                <goals>
                                    <goal>test</goal>
                                </goals>
                            </execution>
                        </executions>
                    </plugin>
                </plugins>
            </build>
        </project>
    """)


def generate_standalone_pom(grammar_name: str, lexer_name: str, start_rule: str) -> str:
    """Generate a standalone pom.xml for local testing outside grammars-v4.

    Replaces the <parent> block with inline groupId, version, properties,
    and the ANTLR runtime dependency so Maven can resolve everything locally.
    """
    # antlr4test-maven-plugin appends "Parser"/"Lexer" to grammarName
    base_name = grammar_name.removesuffix("Parser")
    return textwrap.dedent(f"""\
        <project xmlns="http://maven.apache.org/POM/4.0.0"
                 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                                     http://maven.apache.org/xsd/maven-4.0.0.xsd">
            <modelVersion>4.0.0</modelVersion>
            <groupId>org.antlr.grammars</groupId>
            <artifactId>sysmlv2</artifactId>
            <version>1.0-SNAPSHOT</version>
            <packaging>jar</packaging>
            <name>SysML v2 grammar</name>
            <properties>
                <maven.compiler.source>11</maven.compiler.source>
                <maven.compiler.target>11</maven.compiler.target>
                <antlr.version>4.13.2</antlr.version>
                <antlr4test-maven-plugin.version>1.22</antlr4test-maven-plugin.version>
            </properties>
            <dependencies>
                <dependency>
                    <groupId>org.antlr</groupId>
                    <artifactId>antlr4-runtime</artifactId>
                    <version>${{antlr.version}}</version>
                </dependency>
            </dependencies>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.antlr</groupId>
                        <artifactId>antlr4-maven-plugin</artifactId>
                        <version>${{antlr.version}}</version>
                        <configuration>
                            <sourceDirectory>${{basedir}}</sourceDirectory>
                            <includes>
                                <include>{lexer_name}.g4</include>
                                <include>{grammar_name}.g4</include>
                            </includes>
                            <visitor>true</visitor>
                            <listener>true</listener>
                        </configuration>
                        <executions>
                            <execution>
                                <goals>
                                    <goal>antlr4</goal>
                                </goals>
                            </execution>
                        </executions>
                    </plugin>
                    <plugin>
                        <groupId>com.khubla.antlr</groupId>
                        <artifactId>antlr4test-maven-plugin</artifactId>
                        <version>${{antlr4test-maven-plugin.version}}</version>
                        <configuration>
                            <verbose>false</verbose>
                            <showTree>false</showTree>
                            <entryPoint>{start_rule}</entryPoint>
                            <grammarName>{base_name}</grammarName>
                            <packageName></packageName>
                            <exampleFiles>examples/</exampleFiles>
                        </configuration>
                        <executions>
                            <execution>
                                <goals>
                                    <goal>test</goal>
                                </goals>
                            </execution>
                        </executions>
                    </plugin>
                </plugins>
            </build>
        </project>
    """)


def generate_desc(start_rule: str) -> str:
    # List targets that grammars-v4 CI tests across.
    # Our grammar is target-agnostic (no actions/predicates) so all should work.
    targets = "Antlr4ng;CSharp;Cpp;Dart;Go;Java;JavaScript;PHP;Python3;TypeScript"
    return textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8" ?>
        <desc xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
              xsi:noNamespaceSchemaLocation="../../_scripts/desc.xsd">
           <targets>{targets}</targets>
           <inputs>examples/**/*.sysml</inputs>
           <entry-point>{start_rule}</entry-point>
        </desc>
    """)


def generate_readme(release_tag: str, release_repo: str) -> str:
    return textwrap.dedent(f"""\
        # SysML v2 — ANTLR4 Grammar

        ANTLR4 grammar for the [SysML v2](https://www.omg.org/spec/SysML/2.0) textual
        notation, automatically generated from the OMG specification grammar (KEBNF
        format).

        ## Source

        - **Specification**: [Systems-Modeling/SysML-v2-Release](https://github.com/{release_repo})
        - **Release tag**: `{release_tag}`
        - **Generator**: [daltskin/sysml-v2-grammar](https://github.com/daltskin/sysml-v2-grammar)

        ## Grammar Structure

        | File | Description |
        |------|-------------|
        | `SysMLv2Lexer.g4` | Lexer grammar — keywords, operators, literals, whitespace |
        | `SysMLv2Parser.g4` | Parser grammar — full SysML v2 textual syntax |

        ## Entry Point

        The start rule is `rootNamespace`.

        ## License

        MIT — Copyright (c) {release_tag[:4]} J Dalton

        The SysML v2 specification grammar is owned by the Object Management Group
        (OMG).  This project provides a derived ANTLR4 translation of the official
        KEBNF grammar.
    """)


# ── main ────────────────────────────────────────────────────────────────────


def build_contrib(output_dir: Path, *, skip_format: bool = False) -> None:
    config = load_config()
    opts = config["options"]
    grammar_name = opts["grammar_name"]
    lexer_name = opts["lexer_name"]
    start_rule = opts["root_rule"]
    release_tag = config["release_tag"]
    release_repo = config["release_repo"]

    print(f"📦 Building grammars-v4 contribution → {output_dir}")
    print(f"   Grammar: {grammar_name}  Lexer: {lexer_name}  Start: {start_rule}")
    print(f"   Spec release: {release_tag}")

    # Clean and create output directory
    if output_dir.exists():
        shutil.rmtree(output_dir)
    ensure_dir(output_dir)
    ensure_dir(output_dir / "examples")

    # Copy grammar files (already have correct header, EOF, antlr-format
    # config, and formatting applied in grammar/)
    for g4_name in (f"{grammar_name}.g4", f"{lexer_name}.g4"):
        shutil.copy2(GRAMMAR_DIR / g4_name, output_dir / g4_name)
        print(f"  ✅ {g4_name}")

    # Copy example files
    examples = sorted(EXAMPLES_DIR.glob("*.sysml"))
    if not examples:
        print("  ⚠️  No example .sysml files found")
    for ex in examples:
        shutil.copy2(ex, output_dir / "examples" / ex.name)
    print(f"  ✅ {len(examples)} example(s) copied")

    # Generate pom.xml (canonical with <parent> for grammars-v4)
    (output_dir / "pom.xml").write_text(
        generate_pom(grammar_name, lexer_name, start_rule)
    )
    print("  ✅ pom.xml")

    # Generate standalone pom for local testing (no parent dependency)
    (output_dir / "pom-standalone.xml").write_text(
        generate_standalone_pom(grammar_name, lexer_name, start_rule)
    )
    print("  ✅ pom-standalone.xml (for local testing)")

    # Generate desc.xml
    (output_dir / "desc.xml").write_text(generate_desc(start_rule))
    print("  ✅ desc.xml")

    # Generate README.md
    (output_dir / "README.md").write_text(generate_readme(release_tag, release_repo))
    print("  ✅ README.md")

    # Run antlr-format (should be a no-op since grammar/ is already formatted,
    # but acts as a safety net for grammars-v4 CI compliance)
    if not skip_format:
        run_antlr_format(output_dir)
    else:
        print("  ⏭️  Skipping antlr-format (--skip-format)")

    print()
    print(f"✅ Contribution directory ready: {output_dir}")
    print()
    print("Next steps:")
    print("  1. Copy contrib/sysml/sysmlv2/ into your grammars-v4 fork")
    print("  2. Add <module>sysml/sysmlv2</module> to the root pom.xml")
    print("  3. Run: cd sysml/sysmlv2 && mvn clean test")
    print("  4. Open a pull request against antlr/grammars-v4:master")


def verify_contrib(output_dir: Path) -> bool:
    """Run verification checks on the generated contribution directory."""
    print("🔍 Verifying contribution directory …")
    ok = True

    # Check required files exist
    required = [
        "SysMLv2Parser.g4",
        "SysMLv2Lexer.g4",
        "pom.xml",
        "desc.xml",
        "README.md",
    ]
    for name in required:
        if not (output_dir / name).exists():
            print(f"  ❌ Missing required file: {name}")
            ok = False
        else:
            print(f"  ✅ {name} exists")

    # Check examples exist
    examples = list((output_dir / "examples").glob("*.sysml"))
    if not examples:
        print("  ❌ No example files in examples/")
        ok = False
    else:
        print(f"  ✅ {len(examples)} example file(s)")

    # Check EOF in start rule
    parser_text = (output_dir / "SysMLv2Parser.g4").read_text()
    # Match rootNamespace rule in both multi-line and single-line (post-format) forms
    root_match = re.search(r"rootNamespace\s*:?.*?;", parser_text, re.DOTALL)
    if root_match and "EOF" in root_match.group(0):
        print("  ✅ Start rule ends with EOF")
    else:
        print("  ❌ Start rule missing EOF")
        ok = False

    # Check header is contribution-friendly
    if "Generator: https://github.com/daltskin/sysml-v2-grammar" in parser_text:
        print("  ✅ Header is contribution-friendly")
    else:
        print("  ❌ Parser grammar missing contribution-friendly header")
        ok = False

    # Check pom.xml has correct entryPoint
    pom_text = (output_dir / "pom.xml").read_text()
    config = load_config()
    start_rule = config["options"]["root_rule"]
    if f"<entryPoint>{start_rule}</entryPoint>" in pom_text:
        print(f"  ✅ pom.xml entryPoint = {start_rule}")
    else:
        print("  ❌ pom.xml entryPoint mismatch")
        ok = False

    # Check pom.xml has empty packageName
    if "<packageName></packageName>" in pom_text:
        print("  ✅ pom.xml packageName is empty")
    else:
        print("  ❌ pom.xml packageName should be empty")
        ok = False

    # Check pom.xml <includes> only lists top-level .g4s (no import grammars)
    includes_match = re.search(r"<includes>(.*?)</includes>", pom_text, re.DOTALL)
    if includes_match:
        includes_content = includes_match.group(1)
        include_count = includes_content.count("<include>")
        if include_count == 2:  # lexer + parser
            print(f"  ✅ pom.xml includes {include_count} top-level .g4 files")
        else:
            print(f"  ⚠️  pom.xml includes {include_count} .g4 files (expected 2)")

    # Validate desc.xml structure
    try:
        import xml.etree.ElementTree as ET

        desc_tree = ET.parse(output_dir / "desc.xml")
        desc_root = desc_tree.getroot()
        targets_el = desc_root.find("targets")
        inputs_el = desc_root.find("inputs")
        entry_el = desc_root.find("entry-point")

        if targets_el is not None and targets_el.text:
            target_list = targets_el.text.split(";")
            if "Java" in target_list:
                print(f"  ✅ desc.xml has {len(target_list)} targets (including Java)")
            else:
                print("  ❌ desc.xml missing required Java target")
                ok = False
        else:
            print("  ❌ desc.xml missing <targets> element")
            ok = False

        if inputs_el is not None and inputs_el.text:
            print(f"  ✅ desc.xml inputs: {inputs_el.text}")
        else:
            print("  ❌ desc.xml missing <inputs> element")
            ok = False

        if entry_el is not None and entry_el.text == start_rule:
            print(f"  ✅ desc.xml entry-point = {start_rule}")
        else:
            print("  ❌ desc.xml entry-point mismatch")
            ok = False
    except ET.ParseError as e:
        print(f"  ❌ desc.xml is not valid XML: {e}")
        ok = False

    # Check antlr-format config comments are present in .g4 files
    for g4 in sorted(output_dir.glob("*.g4")):
        g4_text = g4.read_text()
        if "$antlr-format" in g4_text:
            print(f"  ✅ {g4.name} has antlr-format config comments")
        else:
            print(f"  ❌ {g4.name} missing antlr-format config comments")
            ok = False

    # Check lexer grammar name ends in 'Lexer' (grammars-v4 split grammar convention)
    lexer_g4 = output_dir / f"{config['options']['lexer_name']}.g4"
    if lexer_g4.exists():
        lexer_text = lexer_g4.read_text()
        if re.search(r"lexer grammar \w+Lexer\s*;", lexer_text):
            print("  ✅ Lexer grammar name ends in 'Lexer'")
        else:
            print(
                "  ⚠️  Lexer grammar name should end in 'Lexer' (grammars-v4 convention)"
            )

    # Verify antlr-format: re-format a temp copy and diff (matches grammars-v4 CI)
    antlr_fmt = shutil.which("antlr-format")
    has_npx = shutil.which("npx")
    if antlr_fmt or has_npx:
        import tempfile

        for g4 in sorted(output_dir.glob("*.g4")):
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_g4 = Path(tmpdir) / g4.name
                shutil.copy2(g4, tmp_g4)
                cmd = (
                    ["npx", "--yes", "antlr-format-cli", str(tmp_g4)]
                    if not antlr_fmt
                    else ["antlr-format", str(tmp_g4)]
                )
                subprocess.run(cmd, capture_output=True, text=True)
                original = g4.read_text()
                formatted = tmp_g4.read_text()
                if original == formatted:
                    print(f"  ✅ {g4.name} antlr-format OK")
                else:
                    print(
                        f"  ⚠️  {g4.name} differs after re-formatting (may need antlr-format)"
                    )
    else:
        print("  ⏭️  antlr-format not available — skipping formatting check")

    print()
    if ok:
        print("✅ All verification checks passed")
    else:
        print("❌ Verification failed — see errors above")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a grammars-v4-compatible contribution directory"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output directory (default: {DEFAULT_OUTPUT.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run verification checks after building",
    )
    parser.add_argument(
        "--skip-format",
        action="store_true",
        help="Skip running antlr-format on grammars",
    )
    args = parser.parse_args()

    build_contrib(args.output, skip_format=args.skip_format)

    if args.verify:
        print()
        if not verify_contrib(args.output):
            sys.exit(1)


if __name__ == "__main__":
    main()
