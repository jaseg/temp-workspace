#!/bin/bash
# (Re)install the KiCad nightly CLI from the official AppImage builds, headless, without FUSE.
# Leaves the system KiCad 7 (/usr/bin/kicad-cli, python3 pcbnew) untouched.
#
# usage: sudo tools/install_kicad_nightly.sh [AppImage-tar-URL]
#   default: newest x86_64 full build listed on
#   https://downloads.kicad.org/kicad/linux/explore/nightlies
# env: KN_PREFIX (default /opt/kicad-nightly), KN_KEEP_3D=0 to drop the 2 GB 3D models
set -euo pipefail
PREFIX="${KN_PREFIX:-/opt/kicad-nightly}"
INDEX=https://downloads.kicad.org/kicad/linux/explore/nightlies
URL="${1:-}"
if [ -z "$URL" ]; then
  URL="$(curl -fsSL "$INDEX" | grep -oE 'https://downloads\.kicad\.org/kicad/linux/explore/nightlies/download/kicad-nightly-[^"]*-x86_64\.AppImage\.tar' | head -1)"
fi
[ -n "$URL" ] || { echo "could not find a nightly AppImage on $INDEX" >&2; exit 1; }
echo "downloading $URL"
df -h "$(dirname "$PREFIX")" | tail -1
DL="$(mktemp -d)"; trap 'rm -rf "$DL"' EXIT
curl -fSL -o "$DL/kicad.tar" "$URL"
mkdir -p "$DL/x"; tar -C "$DL/x" -xf "$DL/kicad.tar"; rm "$DL/kicad.tar"
IMG="$(ls "$DL"/x/*.AppImage)"; chmod +x "$IMG"
sha256sum "$IMG"

# extract (no FUSE): the AppImage runtime's --appimage-extract; fall back to unsquashfs
rm -rf "$PREFIX.new"; mkdir -p "$PREFIX.new"
if ! (cd "$PREFIX.new" && "$IMG" --appimage-extract >/dev/null); then
  off="$("$IMG" --appimage-offset)"; unsquashfs -q -o "$off" -d "$PREFIX.new/AppDir" "$IMG"
fi
[ -d "$PREFIX.new/AppDir" ] || mv "$PREFIX.new/squashfs-root" "$PREFIX.new/AppDir"
rm -f "$IMG"
rm -rf "$PREFIX.new/AppDir/share/kicad/demos"
[ "${KN_KEEP_3D:-1}" = 1 ] || rm -rf "$PREFIX.new/AppDir/share/kicad/3dmodels"

# swap in, keep the private config dir
mkdir -p "$PREFIX"
rm -rf "$PREFIX/AppDir.old"; [ -d "$PREFIX/AppDir" ] && mv "$PREFIX/AppDir" "$PREFIX/AppDir.old"
mv "$PREFIX.new/AppDir" "$PREFIX/AppDir"; rm -rf "$PREFIX.new" "$PREFIX/AppDir.old" "$PREFIX/squashfs-root"

# wrapper
cat > /usr/local/bin/kicad-cli-nightly <<EOF
#!/bin/bash
# Headless wrapper for the KiCad nightly AppImage (extracted, no FUSE needed).
# Installed by design/lowcost/tools/install_kicad_nightly.sh. Does not touch the system KiCad 7.
KN_ROOT="\${KICAD_NIGHTLY_ROOT:-$PREFIX/AppDir}"
[ -x "\$KN_ROOT/AppRun" ] || { echo "kicad-cli-nightly: \$KN_ROOT/AppRun missing (run install_kicad_nightly.sh)" >&2; exit 127; }
# Keep the nightly's settings away from ~/.config/kicad (KiCad 7 lives there)
export KICAD_CONFIG_HOME="\${KICAD_CONFIG_HOME:-$PREFIX/config}"
mkdir -p "\$KICAD_CONFIG_HOME" 2>/dev/null
# Bundled stock libraries (AppRun/.env sets KICAD_STOCK_DATA_HOME; made explicit here)
S="\$KN_ROOT/share/kicad"
export KICAD_STOCK_DATA_HOME="\$S"
for v in 10 11; do
  export KICAD\${v}_SYMBOL_DIR="\${S}/symbols" KICAD\${v}_FOOTPRINT_DIR="\${S}/footprints" \\
         KICAD\${v}_3DMODEL_DIR="\${S}/3dmodels" KICAD\${v}_TEMPLATE_DIR="\${S}/template"
done
# Don't let the host's KiCad 7 Python or display leak in; the CLI is headless.
unset PYTHONPATH PYTHONHOME DISPLAY WAYLAND_DISPLAY
export LANG="\${LANG:-C.UTF-8}" LC_ALL="\${LC_ALL:-C.UTF-8}"
# AppRun -> sharun sets LD_LIBRARY_PATH/APPDIR etc. from AppDir/.env
exec "\$KN_ROOT/AppRun" kicad-cli "\$@"
EOF
chmod +x /usr/local/bin/kicad-cli-nightly

# global symbol / footprint tables pointing at the bundled stock libraries
VER="$(cd /tmp && kicad-cli-nightly version | tail -1)"; MAJ="$(echo "$VER" | cut -d. -f1,2)"
mkdir -p "$PREFIX/config/$MAJ"
cp "$PREFIX/AppDir/share/kicad/template/sym-lib-table" "$PREFIX/AppDir/share/kicad/template/fp-lib-table" "$PREFIX/config/$MAJ/"
(cd /tmp && kicad-cli-nightly version --format about | sed -n 3p)
cat "$PREFIX/AppDir/share/kicad/appimage.json" 2>/dev/null | grep -E '"(version|build_timestamp)"' || true
python3 -c "import pcbnew; print('system pcbnew', pcbnew.Version())"
