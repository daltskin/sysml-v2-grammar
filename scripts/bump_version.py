#!/usr/bin/env python3
"""Bump the grammar revision in config.json.

Version format: YYYY.MM.REV
  - YYYY.MM  tracks the OMG SysML v2 release tag (e.g. 2026-01 → 2026.01)
  - REV      increments for each grammar release from that spec

Usage:
    python scripts/bump_version.py          # 2026.01.0 → 2026.01.1
    python scripts/bump_version.py --dry    # show what would change
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parent / "config.json"


def main() -> None:
    dry_run = "--dry" in sys.argv

    with CONFIG.open() as f:
        config = json.load(f)

    old_version = config.get("grammar_version", "")
    parts = old_version.split(".")
    if len(parts) != 3:
        print(f"Error: invalid grammar_version '{old_version}' (expected YYYY.MM.REV)")
        sys.exit(1)

    year, month, rev = parts
    new_rev = int(rev) + 1
    new_version = f"{year}.{month}.{new_rev}"

    tag = config.get("release_tag", "?")
    print(f"OMG release:  {tag}")
    print(f"Old version:  {old_version}")
    print(f"New version:  {new_version}")

    if dry_run:
        print("(dry run — no changes written)")
        return

    config["grammar_version"] = new_version
    with CONFIG.open("w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    print(f"✅ Updated {CONFIG.name}")


if __name__ == "__main__":
    main()
