# ERC / DRC with the KiCad nightly CLI

The system KiCad (7.0.11, `/usr/bin/kicad-cli`, python `pcbnew`) has no `sch erc` / `pcb drc`.
The project's generators keep using KiCad 7; checks run with a separately installed
KiCad nightly CLI.

## Installed build

* KiCad **10.99.0-6860-gbdd2930d2b** (nightly, release build, built 2026-11-21 03:11 UTC,
  wxWidgets 3.3.2, Ubuntu 24.04 base), full x86_64 AppImage from the official KiCad server:
  `https://downloads.kicad.org/kicad/linux/explore/nightlies/download/kicad-nightly-10.99.0.6860.gbdd2930d2b-x86_64.AppImage.tar`
  (index: https://downloads.kicad.org/kicad/linux/explore/nightlies).
  AppImage sha256 `006939a00f1069b076831113d199eb0cddc1c7fcabe05c54683125b62fc0756f`.
* Extracted with `--appimage-extract` (no FUSE) to `/opt/kicad-nightly/AppDir` (~3.5 GB,
  includes the stock symbol / footprint / 3D libraries; `demos/` removed). The image was deleted.
* Private settings: `/opt/kicad-nightly/config/10.99/` (global `sym-lib-table` / `fp-lib-table`
  copied from the bundled template, pointing at `${KICAD10_SYMBOL_DIR}` etc.). `~/.config/kicad/7.0`
  is not touched.
* Wrapper: `/usr/local/bin/kicad-cli-nightly` runs `AppDir/AppRun kicad-cli` (sharun sets the
  library path / `APPDIR` / `KICAD_STOCK_DATA_HOME` from `AppDir/.env`), sets `KICAD_CONFIG_HOME`
  and `KICAD10_*_DIR` to the bundled libraries, unsets `DISPLAY`/`PYTHONPATH`. The CLI runs
  headless; no X server / xvfb is needed.

Re-install / update to the newest nightly: `tools/install_kicad_nightly.sh [tar-URL]`
(scrapes the index for the newest full x86_64 build, downloads, extracts, rewrites the wrapper
and the global library tables, prints the version and checks that system `pcbnew` is still 7.0.11).

## Always run on copies

KiCad 10.x silently upgrades files it saves (and writes `.kicad_prl` / project files). The
project must stay KiCad 7 format, so **never point the nightly at the files in the tree**.
`run_erc.sh` / `run_drc.sh` copy into a `mktemp -d` scratch dir (under `$KICAD_SCRATCH` or
`$TMPDIR`/`/tmp`) and delete it afterwards; only the reports are copied back.

## Scripts

    tools/run_erc.sh [out-dir]
        ERC of kicad/scope-fe.kicad_sch (all severities) -> kicad/export/erc.rpt + erc.json,
        summary by type.

    tools/run_drc.sh [--rules asis|jlc4] [--no-refill] [--parity] <board.kicad_pcb> [out-prefix]
        DRC (all severities) of a copy of the board (+ its .kicad_pro / .kicad_dru),
        zones refilled on the copy, schematic parity off unless --parity.
        Writes <out-prefix>.drc.rpt / .drc.json (default: next to the board), prints a
        summary by type/severity and the board-setup constraints that were used.

`kicad_report_summary.py` summarises any kicad-cli ERC/DRC JSON report.

### Design-rule sets

Most layout fragments / block boards have no `.kicad_pro`, so `--rules asis` uses KiCad's
built-in defaults (Default netclass clearance 0.2 mm, track 0.2 mm, via 0.5/0.3 mm; board
minimum hole 0.3 mm, via diameter 0.5 mm, edge clearance 0.5 mm, ...). That produces hundreds
of `clearance` / `track_width` / `via_diameter` / `drill_out_of_range` errors that are only
missing settings.

`--rules jlc4` creates/patches the **copied** `.kicad_pro` (`kicad_inject_rules.py`) and adds
`jlc4.kicad_dru` unless the board has its own:

| constraint | jlc4 value | note |
|---|---|---|
| min clearance / min track | 0.09 mm | JLCPCB 4-layer limit |
| Default netclass clearance / track | 0.10 / 0.15 mm | project target |
| Default via | 0.45 / 0.20 mm | project target |
| min via diameter | 0.35 mm | project uses 0.40 and 0.45 |
| min through-hole drill | 0.15 mm | JLC multilayer min (project uses 0.2) |
| min annular ring | 0.075 mm | project 0.1 .. 0.125 |
| hole to copper / hole to hole | 0.20 / 0.25 mm | |
| copper to board edge | 0.20 mm | edge-launch SMA pads and fragment `IF_PAD`s exempted in the .kicad_dru |
| silk text height / thickness | 0.8 / 0.08 mm | KiCad default; JLC legibility |

To make this permanent, the generators could write the same values into each board's
`.kicad_pro` (KiCad 7 reads the same keys) instead of injecting them at check time.
