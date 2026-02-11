#!/usr/bin/env python3
"""Find cycles in the ANTLR4 grammar that could cause compilation issues."""
import re
import sys

def analyze_grammar(path):
    with open(path) as f:
        content = f.read()

    # Build rule dependency graph
    rules = {}
    current = None
    for line in content.split('\n'):
        m = re.match(r'^([a-zA-Z]\w+)\s*$', line.strip())
        if m:
            current = m.group(1)
            rules[current] = set()
            continue
        if current and line.strip() not in (';', ''):
            for ref in re.finditer(r'\b([a-z][a-zA-Z]+)\b', line):
                r = ref.group(1)
                if r != current and r not in ('assoc', 'right', 'left', 'empty'):
                    rules[current].add(r)
        if line.strip() == ';':
            current = None

    print(f"Total rules: {len(rules)}")

    # Find short cycles using iterative DFS
    all_cycles = []
    for start in sorted(rules.keys()):
        # BFS to find cycles back to start
        stack = [(start, [start])]
        visited = set()
        while stack:
            node, path = stack.pop()
            if len(path) > 8:
                continue
            for neighbor in sorted(rules.get(node, [])):
                if neighbor == start and len(path) > 1:
                    cycle = path + [neighbor]
                    cycle_key = ' -> '.join(sorted(set(cycle[:-1])))
                    if cycle_key not in visited:
                        all_cycles.append(cycle)
                        visited.add(cycle_key)
                elif neighbor not in path and neighbor in rules and len(path) < 7:
                    stack.append((neighbor, path + [neighbor]))

    # Deduplicate cycles
    unique = {}
    for c in all_cycles:
        key = tuple(sorted(set(c[:-1])))
        if key not in unique or len(c) < len(unique[key]):
            unique[key] = c

    cycles = sorted(unique.values(), key=len)
    print(f"\nFound {len(cycles)} unique cycles (depth <= 7):")
    for c in cycles[:30]:
        print(f"  len={len(c)-1}: {' -> '.join(c)}")

    # Check for epsilon-like paths
    # Rules that have only optional content or are very short
    print("\n\nRules with very few dependencies (potential bottlenecks):")
    for name in sorted(rules):
        deps = rules[name]
        if len(deps) == 0:
            print(f"  {name}: leaf rule (no deps)")

if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else 'grammar/SysMLv2.g4'
    analyze_grammar(path)
