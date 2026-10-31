#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/upstream-release.sh"

assert_equal() {
  if [ "$1" != "$2" ]; then
    printf 'FAIL: expected %s, got %s\n' "$1" "$2" >&2
    exit 1
  fi
}

assert_failure() {
  local expected="$1" output status
  shift
  # Capture expected errors so GitHub Actions does not create failure annotations.
  if output=$("$@" 2>&1); then
    printf 'FAIL: expected command to fail: %s\n' "$*" >&2
    exit 1
  else
    status=$?
  fi
  assert_equal 1 "$status"
  assert_equal "$expected" "$output"
}

for tag in 2026-09 2026-09.1 2026-09.10 2025-09.1; do
  release_tag_is_valid "$tag"
done
for tag in '' 2026-00 2026-13 2026-09. 2026-09.1.2 2026-09-rc1 '2026-09;echo bad'; do
  if release_tag_is_valid "$tag"; then
    printf 'FAIL: accepted invalid tag %s\n' "$tag" >&2
    exit 1
  fi
done

assert_equal 2026-09.1 "$(printf '%s\n' 2026-09.1 2026-09 2026-08 | latest_release_tag)"
assert_equal 2026-09.10 "$(printf '%s\n' 2026-09.2 2026-09.10 2026-09 | latest_release_tag)"
assert_equal 2026-10 "$(printf '%s\n' 2026-09.10 2026-10 2026-10-rc1 | latest_release_tag)"
assert_equal 2026-09 "$(printf '%s\n' invalid 2026-09 | latest_release_tag)"
# A valid release must not be missed after the first page of unrelated tags.
assert_equal 2026-09.1 "$(
  { for i in {1..40}; do echo "unrelated-$i"; done; echo 2026-09.1; } | latest_release_tag
)"
printf '%s\n' invalid 2026-09-rc1 |
  assert_failure '::error::No valid upstream release tags found' latest_release_tag
assert_failure '::error::No valid upstream release tags found' latest_release_tag < /dev/null

assert_equal 2026.09.1 "$(next_grammar_version 2026-09.1 2026.09.0)"
assert_equal 2026.09.8 "$(next_grammar_version 2026-09.2 2026.09.7)"
assert_equal 2026.09.10 "$(next_grammar_version 2026-09.10 2026.09.9)"
assert_equal 2026.10.0 "$(next_grammar_version 2026-10 2026.09.7)"
assert_equal 2027.01.0 "$(next_grammar_version 2027-01.1 2026.12.3)"
assert_failure '::error::Invalid upstream tag format: 2026-09-rc1' \
  next_grammar_version 2026-09-rc1 2026.09.0
assert_failure '::error::Invalid grammar version: invalid' \
  next_grammar_version 2026-09.1 invalid

echo 'Upstream release regressions passed'
