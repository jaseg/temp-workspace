#!/bin/bash
# Run ERC on design/lowcost/kicad/scope-fe.kicad_sch with the KiCad nightly CLI.
# The nightly rewrites files in its own (newer) format, so it only ever runs on a
# scratch COPY of the project; the KiCad 7 sources are never touched.
#
# usage: tools/run_erc.sh [out-dir]      (default out-dir: design/lowcost/kicad/export)
# writes <out-dir>/erc.rpt and <out-dir>/erc.json, prints a summary by type.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJ="$(cd "$HERE/.." && pwd)/kicad"
OUT="$(mkdir -p "${1:-$PROJ/export}" && cd "${1:-$PROJ/export}" && pwd)"
CLI="${KICAD_CLI_NIGHTLY:-kicad-cli-nightly}"
SCRATCH_BASE="${KICAD_SCRATCH:-${TMPDIR:-/tmp}}"
mkdir -p "$SCRATCH_BASE"
WORK="$(mktemp -d "$SCRATCH_BASE/kicad-erc.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

# copy the schematic project (sheets, .kicad_pro, sym/fp-lib-table, scope-fe.kicad_sym, lib/)
mkdir -p "$WORK/kicad"
tar -C "$PROJ" --exclude ./export --exclude ./gen --exclude '*.kicad_prl' --exclude '*-backups' -cf - . | tar -C "$WORK/kicad" -xf -
cd "$WORK/kicad"
"$CLI" sch erc --severity-all --units mm --format report -o "$WORK/erc.rpt" scope-fe.kicad_sch >/dev/null
"$CLI" sch erc --severity-all --units mm --format json   -o "$WORK/erc.json" scope-fe.kicad_sch >/dev/null
cp "$WORK/erc.rpt" "$WORK/erc.json" "$OUT/"
python3 -I "$HERE/kicad_report_summary.py" erc "$OUT/erc.json"
echo "  -> $OUT/erc.rpt, $OUT/erc.json"
