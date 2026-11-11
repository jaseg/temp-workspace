#!/usr/bin/env bash
# Install this checkout into a KiCad nightly as a development plugin (Linux).
#
#   1. links plugin/ into KiCad's user plugin directory, so edits take effect immediately
#   2. if KiCad has already created the plugin's Python environment (it does so the first
#      time it loads the plugin), puts the kicad-python built by tools/dev-setup.sh in
#      front of the PyPI release there - released kicad-python has no schematic API yet
#
# Run it, start KiCad once (Preferences > Plugins: enable the API server), then run it
# again for step 2.  Environment: KICAD_VERSION (default 10.99), XDG_DATA_HOME,
# XDG_CACHE_HOME, KICAD_DOCUMENTS_HOME, KICAD_CACHE_HOME - as KiCad uses them.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VER="${KICAD_VERSION:-10.99}"
ID="org.jaseg.factorio-poles"

docs="${KICAD_DOCUMENTS_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}}"
cache="${KICAD_CACHE_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}}"
plugins="$docs/kicad/$VER/plugins"
venv="$cache/kicad/$VER/python-environments/$ID"

mkdir -p "$plugins"
ln -sfn "$ROOT/plugin" "$plugins/factorio-poles"
echo "linked $plugins/factorio-poles -> $ROOT/plugin"

kipy="$ROOT/.cache/kicad-python"
if [ ! -d "$kipy/kipy/proto/schematic" ]; then
    echo "note: run tools/dev-setup.sh to build kicad-python with the schematic API" >&2
elif [ -d "$venv" ]; then
    site="$(echo "$venv"/lib/python3*/site-packages)"
    # A .pth line starting with "import" is executed; this puts our kipy ahead of PyPI's.
    echo "import sys; sys.path.insert(0, '$kipy')" > "$site/00-kicad-python-dev.pth"
    # kicad-python from source needs a few things the PyPI release does not pull in.
    "$venv/bin/python" -m pip install --quiet --only-binary :all: \
        'protobuf>=5.29.6,<6' 'pynng>=0.9,<0.10' 'jsonschema>=4.23,<5' 'zstandard>=0.25,<0.26' typing_extensions
    echo "kicad-python from $kipy is now used by $venv"
else
    echo "start KiCad once so it creates $venv, then run this again" >&2
fi

cat <<EOF

To place poles, add the symbol library to your project (or global) symbol library table:
    $ROOT/symbols/factorio_poles.kicad_sym
EOF
