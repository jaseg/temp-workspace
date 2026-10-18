# yoga.dll for ARM64 Beat Saber

BeatLeader's UI library (Reactive) lays out its menus with [Yoga](https://github.com/facebook/yoga) and ships it as
`Libs/Native/yoga.dll`, x64 only. The native ARM64 game from bs-arm64 can't load x64 DLLs, so BeatLeader's UI
breaks there. This builds a Windows ARM64 `yoga.dll` to put in its place.

- **Source:** Yoga v3.2.1 (MIT). It has every export of the DLL in BeatLeader 0.10.0 (`bs1.42+` zip), plus the
  two functions Reactive adds on top, in `bindings.cpp`: `YGBindingsConfigSetLogger` and `YGLoggerWrapper`. Their
  signatures were recovered from Reactive.dll's metadata; no source for them is published.
- **Build:** `./build.sh <llvm-mingw> <yoga checkout at v3.2.1> <out dir>` with
  [llvm-mingw](https://github.com/mstorsjo/llvm-mingw) (built here with 20261006). Statically linked, no C++
  exceptions (Wine's ARM64 C++ unwinding needs bs-arm64's patched runtime; Yoga only throws on fatal asserts).
- **Install:** with BeatLeader 0.10.0 from `BeatLeader-0.10.0-bs1.42+.zip` (all its files), replace
  `Libs/Native/yoga.dll` in the instance with the built one.

On the Frame the 1.40.2 build was installed before; it's backed up in the instance under
`.liveviewer-backup/beatleader-0.10.0-bs1.40.2/`.
