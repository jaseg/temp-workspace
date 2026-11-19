#!/bin/sh
# Copy the kicad-diff viewer into web_src/js/vendor/kicad-diff (downstream addition).
# Usage: build/sync-kicad-diff.sh <path to a kicad-diff checkout>
set -eu
src=${1:?usage: build/sync-kicad-diff.sh <path to a kicad-diff checkout>}
dst=web_src/js/vendor/kicad-diff
rm -rf "$dst"
mkdir -p "$dst"
cp -R "$src/src" "$src/vendor" "$src/LICENSE" "$src/README.md" "$dst/"
git -C "$src" log -1 --format='%H %cd' --date=short > "$dst/VERSION"
echo "Synced kicad-diff $(cat "$dst/VERSION")"
