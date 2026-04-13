#!/usr/bin/env python3
"""Find parser rules unreachable from rootNamespace."""

import re
import sys


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "grammar/SysMLv2Parser.g4"
    with open(path) as f:
        text = f.read()

    lines = text.split("\n")

    # Find all rule definitions with line numbers
    defs = {}
    for i, line in enumerate(lines, 1):
        m = re.match(r"^(\w+)\s*$", line.rstrip())
        if m and i + 1 <= len(lines) and lines[i].strip().startswith(":"):
            defs[m.group(1)] = i
        else:
            m = re.match(r"^(\w+)\s*:", line.rstrip())
            if m:
                defs[m.group(1)] = i

    # Build adjacency: rule -> rules it references
    # Split the grammar into rule blocks using the definition line numbers
    sorted_defs = sorted(defs.items(), key=lambda x: x[1])
    adj = {}
    for idx, (name, start_line) in enumerate(sorted_defs):
        # Rule body extends from the definition line to the next rule's definition
        if idx + 1 < len(sorted_defs):
            end_line = sorted_defs[idx + 1][1] - 1
        else:
            end_line = len(lines)
        body = "\n".join(lines[start_line:end_line])  # skip the rule name line itself
        adj[name] = set()
        for token in re.findall(r"\b([a-z]\w+)\b", body):
            if token in defs and token != name:
                adj[name].add(token)

    # BFS from rootNamespace
    reachable = set()
    queue = ["rootNamespace"]
    while queue:
        current = queue.pop(0)
        if current in reachable:
            continue
        reachable.add(current)
        for dep in adj.get(current, []):
            if dep not in reachable:
                queue.append(dep)

    unreachable = set(defs.keys()) - reachable
    print(f"Total rules: {len(defs)}")
    print(f"Reachable from rootNamespace: {len(reachable)}")
    print(f"Unreachable: {len(unreachable)}")
    print()
    for name in sorted(unreachable):
        print(f"  Line {defs[name]:4d}: {name}")


if __name__ == "__main__":
    main()
