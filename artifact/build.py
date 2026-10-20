"""Build the in-browser (Pyodide) version of the web UI as a static site.

Usage: python artifact/build.py [--out DIR] [--pyodide-tgz FILE]

Writes DIR (default artifact/dist/): the package's geometry modules and pb_api.py, run by
Pyodide in a web worker (pyworker.js); pyshim.js, which answers the frontend's /api/*
requests from that worker; and the frontend, unchanged except for the patches below.
DIR/index.html is the page body for a claude.ai Artifact (the viewer adds the document
skeleton); DIR/local-test.html is the same page as a full document for local testing
(python -m http.server -d DIR).

The Pyodide runtime comes from the npm tarball (downloaded to artifact/.cache/ unless
--pyodide-tgz is given) and is checked against the registry's integrity hash. The PCB
layout's packages come from Pyodide's CDN (shapely, with numpy and GEOS: checked against the
tarball's pyodide-lock.json) and from PyPI (gerbonara: checked against a pinned hash); they
are cached in artifact/.cache/ too.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent / "src/yanartas_pillowbox"
STATIC = PKG / "static"

PYODIDE_VERSION = "0.26.4"
PYODIDE_URL = f"https://registry.npmjs.org/pyodide/-/pyodide-{PYODIDE_VERSION}.tgz"
PYODIDE_SHA512 = (
    "z2CHsjVlhhJi5tYBF0AYAfNEPo3zq/z+xOpFtk1tweJkRaTqU4UK/7pLvo8DBU2VDPH31vB3pSI+8fnoqrVrFg=="
)
PYODIDE_FILES = ("pyodide.mjs", "pyodide.asm.js", "pyodide.asm.wasm", "pyodide-lock.json")

# The package modules the API needs (no Flask, no file persistence).
PY_MODULES = (
    "__init__", "api", "config", "crosssection", "dimensions", "fpc", "geometry", "kimesh",
    "mesh", "payload", "pcb", "presets", "progress", "scad", "sfc", "svg",
)  # fmt: skip

# The PCB layout's dependencies, loaded by the worker on the first PCB request. Pyodide's own
# packages (with their dependencies, as its lock file lists them):
PYODIDE_CDN = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"
PYODIDE_PACKAGES = ("shapely",)
# Pure-Python wheels, installed without their dependencies: gerbonara needs click (a Pyodide
# package), quart (only for its own server, unused) and rtree (stubs/rtree stands in).
WHEELS = {
    "gerbonara-1.6.3-py3-none-any.whl": (
        "https://files.pythonhosted.org/packages/91/25/df1ba4ab100da4fecc4c843946b72f98909885"
        "810d5eb6c4c6cfedbdea31/gerbonara-1.6.3-py3-none-any.whl",
        "fccf782acdc98e80e3a418b7ed57d35c4f6ac7a8bc5e5d3ddc48bdd870919be2",
    ),
}
PYODIDE_EXTRA = ("click",)  # (gerbonara's, imported by modules the layout does not use)


def patch(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, f"patch target found {text.count(old)}x: {old[:60]!r}"
    return text.replace(old, new)


def pyodide_tarball(path: Path | None) -> bytes:
    if path is None:
        path = HERE / ".cache" / f"pyodide-{PYODIDE_VERSION}.tgz"
        if not path.exists():
            path.parent.mkdir(exist_ok=True)
            print("downloading", PYODIDE_URL)
            with urllib.request.urlopen(PYODIDE_URL) as res:
                path.write_bytes(res.read())
    data = path.read_bytes()
    digest = base64.b64encode(hashlib.sha512(data).digest()).decode()
    if digest != PYODIDE_SHA512:
        raise SystemExit(f"{path}: sha512 mismatch, not the pyodide {PYODIDE_VERSION} tarball")
    return data


def fetch_checked(url: str, sha256: str) -> bytes:
    """``url``'s content, cached in artifact/.cache/, checked against its sha256."""
    path = HERE / ".cache" / url.rsplit("/", 1)[1]
    if not path.exists():
        path.parent.mkdir(exist_ok=True)
        print("downloading", url)
        with urllib.request.urlopen(url) as res:
            path.write_bytes(res.read())
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise SystemExit(f"{path}: sha256 mismatch")
    return data


PART = 4_000_000  # characters per part of an encoded package (artifact files: 16 MB at most)


def write_parts(path: Path, data: bytes) -> int:
    """``data`` base64-encoded into ``<path>.<i>.b64.txt`` parts; returns their count."""
    text = base64.b64encode(data).decode()
    parts = [text[i : i + PART] for i in range(0, len(text), PART)]
    for i, part in enumerate(parts):
        path.with_name(f"{path.name}.{i}.b64.txt").write_text(part)
    return len(parts)


def pyodide_packages(lock: dict, names: tuple[str, ...]) -> list[dict]:
    """The lock's entries of ``names`` and everything they depend on, dependencies first."""
    out: list[dict] = []

    def add(name: str) -> None:
        entry = lock["packages"][name]
        if entry in out:
            return
        for dep in entry.get("depends", []):
            add(dep)
        out.append(entry)

    for name in names:
        add(name)
    return out


def build_mesh(out: Path) -> None:
    """The mesh settling's WebAssembly build (rust/wasm) and its glue, in DIR/mesh/: needs
    cargo with the wasm32-unknown-unknown target and wasm-bindgen (the crate's version)."""
    rust = HERE.parent / "rust"
    for tool in ("cargo", "wasm-bindgen"):
        if shutil.which(tool) is None:
            raise SystemExit(
                f"{tool} not found: install Rust (rustup target add wasm32-unknown-unknown; "
                "cargo install wasm-bindgen-cli at the version in rust/Cargo.lock), "
                "or pass --no-wasm (the browser then settles in numpy: far slower)"
            )
    subprocess.run(
        ["cargo", "build", "--release", "-p", "pillowbox-mesh-wasm",
         "--target", "wasm32-unknown-unknown"],
        cwd=rust, check=True,
    )  # fmt: skip
    wasm = rust / "target/wasm32-unknown-unknown/release/pillowbox_mesh_wasm.wasm"
    subprocess.run(
        ["wasm-bindgen", "--target", "web", "--no-typescript", "--out-dir", str(out / "mesh"),
         str(wasm)],
        check=True,
    )  # fmt: skip


def build(out: Path, tgz: Path | None, mesh: bool = True) -> None:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # Python: the package modules verbatim, plus the API module; pyworker.js loads the files
    # listed in py/files.json.
    (out / "py/yanartas_pillowbox").mkdir(parents=True)
    files = ["pb_api.py", *(f"yanartas_pillowbox/{name}.py" for name in PY_MODULES)]
    for name in PY_MODULES:
        shutil.copy(PKG / f"{name}.py", out / f"py/yanartas_pillowbox/{name}.py")
    shutil.copy(HERE / "pb_api.py", out / "py/pb_api.py")
    (out / "py/files.json").write_text(json.dumps(files, indent=1) + "\n")

    # Pyodide runtime. Artifacts do not serve .zip files: the standard library ships
    # base64-encoded as text and pyworker.js hands it to Pyodide as a blob URL.
    (out / "pyodide").mkdir()
    with tarfile.open(fileobj=io.BytesIO(pyodide_tarball(tgz)), mode="r:gz") as tar:
        for name in PYODIDE_FILES:
            (out / "pyodide" / name).write_bytes(tar.extractfile(f"package/{name}").read())
        stdlib = tar.extractfile("package/python_stdlib.zip").read()
    (out / "pyodide/python_stdlib.zip.b64.txt").write_text(base64.b64encode(stdlib).decode())

    # The PCB layout's packages, base64-encoded like the standard library: the worker loads
    # them on the first PCB request (py/pcb.json lists them).
    lock = json.loads((out / "pyodide/pyodide-lock.json").read_text())
    packages = pyodide_packages(lock, (*PYODIDE_PACKAGES, *PYODIDE_EXTRA))
    parts = {}
    for entry in packages:
        data = fetch_checked(PYODIDE_CDN + entry["file_name"], entry["sha256"])
        parts[entry["file_name"]] = write_parts(out / "pyodide" / entry["file_name"], data)
    (out / "py/wheels").mkdir()
    for name, (url, sha256) in WHEELS.items():
        parts[name] = write_parts(out / "py/wheels" / name, fetch_checked(url, sha256))
    stubs = sorted(p.relative_to(HERE / "stubs").as_posix() for p in (HERE / "stubs").rglob("*.py"))
    for name in stubs:
        (out / "py/stubs" / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(HERE / "stubs" / name, out / "py/stubs" / name)
    (out / "py/pcb.json").write_text(
        json.dumps(
            {
                "packages": [*PYODIDE_PACKAGES, *PYODIDE_EXTRA],
                "files": [e["file_name"] for e in packages],
                "parts": parts,
                "wheels": list(WHEELS),
                "stubs": stubs,
            },
            indent=1,
        )
        + "\n"
    )

    for name in ("pyshim.js", "pyworker.js"):
        shutil.copy(HERE / name, out / name)
    if mesh:
        build_mesh(out)

    # Frontend: verbatim except for the patches below.
    (out / "static/js/components").mkdir(parents=True)
    (out / "static/css").mkdir()
    for src in (STATIC / "js").rglob("*.js"):
        if src.name != "app.js":
            shutil.copy(src, out / "static" / src.relative_to(STATIC))

    app = (STATIC / "js/app.js").read_text()
    app, n = re.subn(
        r"function saveBlob\(blob, name\) \{\n.*?\n\}\n",
        "function saveBlob(blob, name) {\n"
        "  // Artifact build: saved through the viewer's downloads capability (pyshim.js).\n"
        "  window.pbSave(blob, name);\n}\n",
        app,
        count=1,
        flags=re.S,
    )
    assert n == 1, "saveBlob not found in app.js"
    # The downloads capability only accepts known extensions; OpenSCAD source goes out as text.
    app = patch(app, 'fileName("-interior.scad")', 'fileName("-interior.scad.txt")')
    (out / "static/js/app.js").write_text(app)

    # three.js ships as the page's own files: the viewer's CSP allows 'self' scripts but no
    # CDN, and ignores import maps, so pb-preview3d.js must import it by relative path.
    (out / "static/vendor/three").mkdir(parents=True)
    for name in ("three.module.min.js", "OrbitControls.js", "LICENSE"):
        shutil.copy(STATIC / "vendor/three" / name, out / "static/vendor/three" / name)

    # CSS: follow the viewer's explicit light/dark choice too, not only the OS setting.
    css = (STATIC / "css/app.css").read_text()
    m = re.search(
        r"@media \(prefers-color-scheme: dark\) \{\n  :root \{\n(.*?)\n  \}\n\}\n", css, re.S
    )
    assert m, "dark block not found in app.css"
    dark = m.group(1)
    css = css.replace(
        m.group(0),
        '@media (prefers-color-scheme: dark) {\n  :root:not([data-theme="light"]) {\n'
        f"{dark}\n    color-scheme: dark;\n  }}\n}}\n"
        f':root[data-theme="dark"] {{\n{dark}\n  color-scheme: dark;\n}}\n'
        ':root[data-theme="light"] { color-scheme: light; }\n',
    )
    css += (
        "\n/* Artifact build: keep a 16px side gutter at every width. */\n"
        ".layout { padding-inline: 16px; }\n"
    )
    (out / "static/css/app.css").write_text(css)

    # The page: the repo's index.html body, with the shim loaded before the app. No inline
    # scripts (the viewer's CSP refuses them).
    html = (STATIC / "index.html").read_text()
    body = html[html.index("<body>") + len("<body>") : html.index("</body>")].strip("\n")
    page = (
        "<title>Pillow Box Designer</title>\n"
        '<link rel="stylesheet" href="static/css/app.css">\n'
        '<script type="module" src="pyshim.js"></script>\n'
        '<script type="module" src="static/js/app.js"></script>\n'
        f"{body}\n"
    )
    (out / "index.html").write_text(page)

    # Local test page: the same content in a document. A module script runs first, as in
    # the viewer, so that an import map would be ignored here too.
    (out / "local-test.html").write_text(
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        "<style>:root{color-scheme:light}body{margin:0}[hidden]{display:none!important}</style>"
        '<script type="module">/* stands in for the viewer shell */</script>'
        "</head><body>" + page + "</body></html>"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=HERE / "dist", help="output directory")
    ap.add_argument("--pyodide-tgz", type=Path, help=f"local pyodide-{PYODIDE_VERSION}.tgz")
    ap.add_argument(
        "--no-wasm", action="store_true", help="leave out the mesh settling's WebAssembly build"
    )
    args = ap.parse_args()
    build(args.out, args.pyodide_tgz, mesh=not args.no_wasm)
    print("built", args.out)


if __name__ == "__main__":
    main()
