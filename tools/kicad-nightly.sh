#!/usr/bin/env bash
# Fetch and run the official KiCad nightly AppImage (x86_64 Linux).
#
#   tools/kicad-nightly.sh fetch                 download the latest nightly (once)
#   tools/kicad-nightly.sh version               print the cached nightly's version
#   tools/kicad-nightly.sh <program> [args...]   run kicad, eeschema, kicad-cli, ...
#
# e.g. a headless API server for the demo project:
#   tools/kicad-nightly.sh kicad-cli api-server --socket /tmp/fp.sock demo/demo.kicad_pro
#
# Environment:
#   KICAD_NIGHTLY_DIR      cache directory (default: .cache/kicad-nightly)
#   KICAD_NIGHTLY_VERSION  pin a build, e.g. 10.99.0.6401.gf25b8c5aa4 (default: newest)
#   KICAD_CONFIG_HOME      KiCad settings dir (default: an isolated one in the cache)
set -euo pipefail

BUCKET="https://kicad-downloads.s3.cern.ch"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="${KICAD_NIGHTLY_DIR:-$ROOT/.cache/kicad-nightly}"

latest_key() {
    # List appimage/nightly/ (paginated) and pick the newest full (non-lite) AppImage.
    local marker="" page keys=""
    while :; do
        page="$(curl -fsS "$BUCKET/?prefix=appimage/nightly/&marker=$marker")"
        keys+="$(printf '%s' "$page" | grep -o '<Key>[^<]*</Key>' | sed 's/<[^>]*>//g')"$'\n'
        printf '%s' "$page" | grep -q '<IsTruncated>true' || break
        marker="$(printf '%s' "$keys" | grep . | tail -1)"
    done
    printf '%s' "$keys" | grep -E 'kicad-nightly-.*-x86_64\.AppImage\.tar$' |
        if [ -n "${KICAD_NIGHTLY_VERSION:-}" ]; then grep -F -- "-$KICAD_NIGHTLY_VERSION-"; else cat; fi |
        sort -V | tail -1
}

fetch() {
    local key name
    key="$(latest_key)"
    [ -n "$key" ] || { echo "no nightly AppImage found" >&2; exit 1; }
    name="$(basename "$key" .tar)"
    if [ -f "$DIR/VERSION" ] && [ "$(cat "$DIR/VERSION")" = "$name" ] && [ -x "$DIR/squashfs-root/AppRun" ]; then
        echo "up to date: $name" >&2
        return
    fi
    echo "downloading $name" >&2
    rm -rf "$DIR"
    mkdir -p "$DIR"
    curl -fL --progress-bar "$BUCKET/$key" | tar -x -C "$DIR"
    chmod +x "$DIR/$name"
    # Extract instead of mounting: works without FUSE (containers, CI).
    (cd "$DIR" && "./$name" --appimage-extract >/dev/null)
    rm -f "$DIR/$name"
    echo "$name" > "$DIR/VERSION"
    echo "installed to $DIR" >&2
}

case "${1:-}" in
fetch) fetch ;;
version) cat "$DIR/VERSION" ;;
"")
    sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
*)
    [ -x "$DIR/squashfs-root/AppRun" ] || fetch
    export KICAD_CONFIG_HOME="${KICAD_CONFIG_HOME:-$DIR/config}"
    mkdir -p "$KICAD_CONFIG_HOME"
    exec "$DIR/squashfs-root/AppRun" "$@"
    ;;
esac
