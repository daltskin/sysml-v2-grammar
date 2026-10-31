#!/usr/bin/env bash

release_tag_is_valid() {
  [[ "$1" =~ ^[0-9]{4}-(0[1-9]|1[0-2])(\.[0-9]+)?$ ]]
}

latest_release_tag() {
  local tag latest
  latest=$(
    while IFS= read -r tag; do
      if release_tag_is_valid "$tag"; then
        printf '%s\n' "$tag"
      fi
    done | sort -rV | sed -n '1p'
  )
  if [ -z "$latest" ]; then
    echo "::error::No valid upstream release tags found" >&2
    return 1
  fi
  printf '%s\n' "$latest"
}

next_grammar_version() {
  local tag="$1" current="$2" prefix revision
  if ! release_tag_is_valid "$tag"; then
    echo "::error::Invalid upstream tag format: $tag" >&2
    return 1
  fi
  if ! [[ "$current" =~ ^[0-9]{4}\.(0[1-9]|1[0-2])\.[0-9]+$ ]]; then
    echo "::error::Invalid grammar version: $current" >&2
    return 1
  fi

  prefix="${tag%%.*}"
  prefix="${prefix/-/.}"
  revision=0
  if [ "${current%.*}" = "$prefix" ]; then
    revision="${current##*.}"
    revision=$((10#$revision + 1))
  fi
  printf '%s.%s\n' "$prefix" "$revision"
}
