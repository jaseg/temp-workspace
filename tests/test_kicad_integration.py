"""End-to-end tests against a real headless KiCad nightly (``kicad-cli api-server``).

Skipped unless the nightly has been fetched (``tools/kicad-nightly.sh fetch``) and
kicad-python with schematic support is importable (``tools/dev-setup.sh``).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NIGHTLY = ROOT / "tools" / "kicad-nightly.sh"
NIGHTLY_DIR = Path(os.environ.get("KICAD_NIGHTLY_DIR", ROOT / ".cache" / "kicad-nightly"))

kipy = pytest.importorskip("kipy")
pytest.importorskip("kipy.schematic")
if not (NIGHTLY_DIR / "squashfs-root" / "AppRun").exists():
    pytest.skip("KiCad nightly not fetched (tools/kicad-nightly.sh fetch)", allow_module_level=True)

from factorio_poles import kicad_io
from factorio_poles.config import Settings
from factorio_poles.textures import BUNDLED, TexturePack
from kipy import KiCad
from kipy.geometry import Vector2
from kipy.proto.common.types import DocumentType


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    d = tmp_path_factory.mktemp("demo")
    for name in ("demo.kicad_pro", "demo.kicad_sch"):
        shutil.copy(ROOT / "demo" / name, d / name)
    lib = ROOT / "symbols" / "factorio_poles.kicad_sym"
    (d / "sym-lib-table").write_text(
        (ROOT / "demo" / "sym-lib-table")
        .read_text()
        .replace("${KIPRJMOD}/../symbols/factorio_poles.kicad_sym", str(lib))
    )
    return d


@pytest.fixture(scope="module")
def sch(project, tmp_path_factory):
    sock = tmp_path_factory.mktemp("sock") / "api.sock"
    env = dict(os.environ, KICAD_NIGHTLY_DIR=str(NIGHTLY_DIR), KICAD_CONFIG_HOME=str(project / ".config"))
    proc = subprocess.Popen(
        [str(NIGHTLY), "kicad-cli", "api-server", "--socket", str(sock), str(project / "demo.kicad_pro")],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(300):
            if sock.exists():
                break
            if proc.poll() is not None:
                pytest.fail(f"api-server exited: {proc.stdout.read().decode(errors='replace')}")
            time.sleep(0.1)
        # A fresh config directory makes the server's first requests slow; wait until it answers.
        kicad = KiCad(socket_path=f"ipc://{sock}", timeout_ms=60000)
        for _ in range(30):
            try:
                kicad.ping()
                break
            except Exception:  # noqa: BLE001
                time.sleep(1)
        kicad.open_document(str(project / "demo.kicad_sch"), DocumentType.DOCTYPE_SCHEMATIC)
        yield kicad.get_schematic()
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


SETTINGS = Settings(use_factorio_install=False)
PACK = TexturePack([BUNDLED])


def generated(s):
    return {k: v for k, v in kicad_io.generated_items(s).items()}


def test_reads_all_demo_poles(sch):
    poles = kicad_io.read_poles(sch, SETTINGS)
    assert len(poles) == 18
    assert {p.net for p in poles} == {"+5V", "VBUS", "GND"}
    assert {p.type.name for p in poles} == {"small-electric-pole", "medium-electric-pole", "big-electric-pole"}


def test_clear_then_update_then_idempotent(sch):
    kicad_io.sync(sch, SETTINGS, None, clear=True)
    assert generated(sch) == {}

    (res,) = kicad_io.sync(sch, SETTINGS, PACK)
    items = generated(sch)
    assert res.created == len(res.plan.items) == len(items)
    assert all(len(v) == 1 for v in items.values())
    assert sum(k.startswith("pole:") for k in items) == 18
    assert sum(k.startswith("wire:") for k in items) == len(res.plan.wires) == 14
    assert [k for k in items if k.startswith("reach:")] == [f"reach:{p.id}" for p in res.plan.stranded()]

    (again,) = kicad_io.sync(sch, SETTINGS, PACK)
    assert not again.changed


def test_generated_items_are_locked_and_visible(sch):
    kicad_io.sync(sch, SETTINGS, PACK)
    for entries in generated(sch).values():
        for item, _ in entries:
            assert item.locked
            if hasattr(item, "shape") and item.shape is not None and hasattr(item.shape, "polygons"):
                assert not item.shape.polygons[0].outline.closed  # wires are open polylines
            if hasattr(item, "image_data"):
                assert item.proto.opacity == 1.0
                assert item.image_data[:8] == b"\x89PNG\r\n\x1a\n"


def test_moving_a_pole_only_touches_its_items(sch):
    kicad_io.sync(sch, SETTINGS, PACK)
    syms = [s for s in sch.get_symbols() if kicad_io.pole_type_of(s) and s.value == "GND"]
    sym = max(syms, key=lambda s: s.position.x)  # the small pole at the end of the GND line
    before = generated(sch)
    sym.position = Vector2.from_xy(sym.position.x, sym.position.y + int(2.54e6))
    commit = sch.begin_commit()
    kicad_io.update_items(sch, [sym])
    sch.push_commit(commit, "move")

    (res,) = kicad_io.sync(sch, SETTINGS, PACK)
    after = generated(sch)
    assert res.updated >= 1  # its sprite moved
    changed = {k for k in after if k not in before or before[k][0][1] != after[k][0][1]}
    assert changed and all(sym.id.value in k for k in changed)


def test_changing_the_net_rewires(sch):
    kicad_io.sync(sch, SETTINGS, PACK)
    syms = [s for s in sch.get_symbols() if kicad_io.pole_type_of(s) and s.value == "+5V"]
    sym = min(syms, key=lambda s: s.position.x)
    sym.value = "+3V3"
    commit = sch.begin_commit()
    kicad_io.update_items(sch, [sym])
    sch.push_commit(commit, "net")
    (res,) = kicad_io.sync(sch, SETTINGS, PACK)
    assert not any(sym.id.value in w.key for w in res.plan.wires)


def test_save_round_trip(sch, project):
    kicad_io.sync(sch, SETTINGS, PACK)
    sch.save()
    text = (project / "demo.kicad_sch").read_text()
    assert text.count('(custom_property "factorio_poles"') == sum(len(v) for v in generated(sch).values())
