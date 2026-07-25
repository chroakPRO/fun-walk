#!/usr/bin/env bash

set -euo pipefail

repo="$(git rev-parse --show-toplevel)"
gitignore="$repo/.gitignore"
limit=$((500 * 1024 * 1024))

touch "$gitignore"

find "$repo" \
    \( -path "$repo/.git" -o -path "$repo/.venv" \) -prune -o \
    -type f -print0 |
while IFS= read -r -d '' file; do
    size="$(stat -f '%z' "$file")"

    printf '%10.2f MiB  %s\n' \
        "$(awk -v bytes="$size" 'BEGIN { printf "%.2f", bytes / 1048576 }')" \
        "${file#"$repo"/}"

    if (( size > limit )); then
        relative="${file#"$repo"/}"
        pattern="/$(printf '%s' "$relative" |
            sed 's/\\/\\\\/g; s/\[/\\[/g; s/\*/\\*/g; s/?/\\?/g; s/^[#!]/\\&/')"

        grep -Fqx -- "$pattern" "$gitignore" ||
            printf '%s\n' "$pattern" >> "$gitignore"
    fi
done
