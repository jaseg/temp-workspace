#!/usr/bin/env bash
# Fetch the tools the benchmark runs: FreeCAD 1.1.3 (OCCT 7.9.3) from conda-forge, and SolidCraft
# (with its vendored SolidCore kernel) at the commit benchmarked. Everything lands in tools/ and src/.
set -euo pipefail
cd "$(dirname "$0")"
SOLIDCRAFT_REV=b5716d0fb8052b25a9ce512485a8fc38cb8a2000   # main, 2026-11-09

mkdir -p tools src
if [ ! -x tools/bin/micromamba ]; then
  curl -sSL https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C tools bin/micromamba
fi
if [ ! -x tools/fc/bin/python ]; then
  MAMBA_ROOT_PREFIX="$PWD/tools/mamba" tools/bin/micromamba create -y -q -p "$PWD/tools/fc" -c conda-forge "freecad=1.1.3"
fi
if [ ! -d src/solidcraft ]; then
  git clone https://github.com/tangency-labs/solidcraft.git src/solidcraft
fi
git -C src/solidcraft fetch -q origin "$SOLIDCRAFT_REV" || true
git -C src/solidcraft checkout -q "$SOLIDCRAFT_REV"
(cd src/solidcraft && cargo build --release -p solidcraft-cli)
