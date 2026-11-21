#!/bin/bash
# Run DRC on a KiCad 7 board with the KiCad nightly CLI, on a scratch COPY
# (the nightly rewrites files in its newer format; the sources stay KiCad 7).
#
# usage: tools/run_drc.sh [--rules asis|jlc4] [--no-refill] [--parity] <board.kicad_pcb> [out-prefix]
#   --rules asis   (default) use the board's own .kicad_pro / .kicad_dru if present,
#                  otherwise KiCad's built-in defaults
#   --rules jlc4   create/patch the COPIED .kicad_pro with JLCPCB 4-layer constraints
#                  (see kicad_inject_rules.py); also copies tools/jlc4.kicad_dru if the
#                  board has no .kicad_dru of its own
#   --no-refill    do not refill zones before DRC (default: refill, on the copy only;
#                  the generators write unfilled zones)
#   --parity       also check schematic parity (off by default: stand-alone blocks)
# writes <out-prefix>.drc.rpt and <out-prefix>.drc.json (default prefix: board path
# without .kicad_pcb, i.e. next to the board) and prints a summary by type/severity.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
RULES=asis; REFILL=--refill-zones; PARITY=
while [ $# -gt 0 ]; do
  case "$1" in
    --rules) RULES="$2"; shift 2;;
    --no-refill) REFILL=; shift;;
    --parity) PARITY=--schematic-parity; shift;;
    -h|--help) sed -n '2,16p' "$0"; exit 0;;
    *) break;;
  esac
done
[ $# -ge 1 ] || { sed -n '2,16p' "$0"; exit 2; }
BOARD="$(readlink -f "$1")"
[ -f "$BOARD" ] || { echo "no such board: $1" >&2; exit 2; }
PREFIX="${2:-${BOARD%.kicad_pcb}}"
mkdir -p "$(dirname "$PREFIX")"
PREFIX="$(cd "$(dirname "$PREFIX")" && pwd)/$(basename "$PREFIX")"
CLI="${KICAD_CLI_NIGHTLY:-kicad-cli-nightly}"
SCRATCH_BASE="${KICAD_SCRATCH:-${TMPDIR:-/tmp}}"
mkdir -p "$SCRATCH_BASE"
WORK="$(mktemp -d "$SCRATCH_BASE/kicad-drc.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

NAME="$(basename "${BOARD%.kicad_pcb}")"
SRC="$(dirname "$BOARD")"
cp "$BOARD" "$WORK/"
for ext in kicad_pro kicad_dru; do
  [ -f "$SRC/$NAME.$ext" ] && cp "$SRC/$NAME.$ext" "$WORK/"
done
# project-local libraries referenced by a .kicad_pro next to the board
[ -f "$SRC/fp-lib-table" ] && cp "$SRC/fp-lib-table" "$WORK/"
# schematic parity needs the schematic (same basename) next to the copied board: if the
# board directory has none, copy the project's schematic sheets + symbol libraries
if [ -n "$PARITY" ] && [ ! -f "$SRC/$NAME.kicad_sch" ]; then
  SCH="$(cd "$HERE/.." && pwd)/kicad"
  cp "$SCH"/*.kicad_sch "$WORK/"
  [ -f "$SCH/scope-fe.kicad_sch" ] && [ "$NAME" != scope-fe ] && mv "$WORK/scope-fe.kicad_sch" "$WORK/$NAME.kicad_sch"
  for f in sym-lib-table scope-fe.kicad_sym; do [ -f "$SCH/$f" ] && cp "$SCH/$f" "$WORK/"; done
  [ -f "$WORK/fp-lib-table" ] || { [ -f "$SCH/fp-lib-table" ] && cp "$SCH/fp-lib-table" "$WORK/"; }
  [ -d "$SCH/lib" ] && cp -r "$SCH/lib" "$WORK/"
fi
if [ "$RULES" = jlc4 ]; then
  python3 -I "$HERE/kicad_inject_rules.py" "$WORK/$NAME.kicad_pro" jlc4
  [ -f "$WORK/$NAME.kicad_dru" ] || cp "$HERE/jlc4.kicad_dru" "$WORK/$NAME.kicad_dru"
elif [ "$RULES" != asis ]; then
  echo "unknown --rules $RULES" >&2; exit 2
fi

cd "$WORK"
for fmt in report json; do
  ext=rpt; [ $fmt = json ] && ext=json
  "$CLI" pcb drc --severity-all --units mm $REFILL $PARITY --format $fmt \
      -o "$WORK/out.drc.$ext" "$NAME.kicad_pcb" >/dev/null
done
cp "$WORK/out.drc.rpt" "$PREFIX.drc.rpt"
cp "$WORK/out.drc.json" "$PREFIX.drc.json"
python3 -I "$HERE/kicad_report_summary.py" drc "$PREFIX.drc.json"
echo "  rule set: $RULES${REFILL:+, zones refilled (copy)}"
python3 -I "$HERE/kicad_inject_rules.py" "$WORK/$NAME.kicad_pro" show
echo "  -> $PREFIX.drc.rpt, $PREFIX.drc.json"
