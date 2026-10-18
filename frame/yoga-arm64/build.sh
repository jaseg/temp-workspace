#!/bin/sh
# Builds yoga.dll for Windows ARM64 (the native ARM64 Beat Saber from bs-arm64), as a drop-in for the x64-only
# Libs/Native/yoga.dll that BeatLeader's UI library ships.
# Usage: build.sh <llvm-mingw dir> <yoga source checkout> <output dir>
# Yoga v3.2.1 has every export of the DLL in BeatLeader 0.10.0 (bs1.42+) except the two in bindings.cpp.
set -eu
TOOLCHAIN=$1
YOGA=$2
OUT=$3
HERE=$(cd "$(dirname "$0")" && pwd)
[ "$(git -C "$YOGA" describe --tags)" = v3.2.1 ] || { echo "expected yoga v3.2.1 in $YOGA" >&2; exit 1; }
mkdir -p "$OUT"
# No exceptions: Wine's ARM64 C++ unwinding needs a patched runtime, and Yoga only throws on fatal asserts.
# Everything is linked statically (libc++, libunwind), and every symbol exported, like the upstream MinGW build.
"$TOOLCHAIN/bin/aarch64-w64-mingw32-clang++" -std=c++20 -O2 -fno-exceptions -DNDEBUG -I"$YOGA" \
	"$HERE/bindings.cpp" $(find "$YOGA/yoga" -name '*.cpp' | sort) \
	-shared -static -Wl,--export-all-symbols -o "$OUT/yoga.dll"
echo "built $OUT/yoga.dll"
