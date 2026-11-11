import json

import pytest
from factorio_poles import config
from factorio_poles.config import Settings
from factorio_poles.network import Pole
from factorio_poles.plan import IU_NM, CircleSpec, ImageSpec, PolylineSpec, make_plan
from factorio_poles.prototypes import BIG, SMALL
from factorio_poles.textures import BUNDLED, TexturePack


def poles():
    return [
        Pole("a", "VCC", SMALL, (10.0, 10.0)),
        Pole("b", "VCC", SMALL, (16.0, 10.0)),
        Pole("c", "VCC", BIG, (16.0, 40.0)),  # out of reach: stranded
        Pole("d", "GND", SMALL, (10.0, 12.0)),
    ]


def test_plan_items():
    plan = make_plan(poles(), Settings(), TexturePack([BUNDLED]))
    kinds = {}
    for item in plan.items:
        kinds.setdefault(type(item), []).append(item.key)
    assert sorted(kinds[ImageSpec]) == ["pole:a", "pole:b", "pole:c", "pole:d"]
    assert sorted(kinds[PolylineSpec]) == ["wire-shadow:a:b", "wire:a:b"]
    assert kinds[CircleSpec] == ["reach:c"]
    assert any("split into 2" in w for w in plan.warnings)


def test_plan_coordinates_are_on_kicad_grid():
    plan = make_plan(poles(), Settings(tile_mm=1.0), TexturePack([BUNDLED]))
    for item in plan.items:
        pts = [item.position] if isinstance(item, ImageSpec) else getattr(item, "points", None) or [item.center]
        for x, y in pts:
            assert x % IU_NM == 0 and y % IU_NM == 0


def test_plan_without_shadows_or_textures():
    plan = make_plan(poles(), Settings(shadows=False, mark_islands=False), None)
    assert [i.key for i in plan.items] == ["wire:a:b"]


def test_signatures_are_stable_and_position_independent_for_images():
    pack = TexturePack([BUNDLED])
    p1 = make_plan(poles(), Settings(), pack)
    p2 = make_plan(poles(), Settings(), pack)
    assert [i.sig for i in p1.items] == [i.sig for i in p2.items]

    moved = poles()
    moved[3] = Pole("d", "GND", SMALL, (11.0, 12.0))
    p3 = make_plan(moved, Settings(), pack)
    img = {i.key: i for i in p3.items if isinstance(i, ImageSpec)}
    ref = {i.key: i for i in p1.items if isinstance(i, ImageSpec)}
    assert img["pole:d"].sig == ref["pole:d"].sig
    assert img["pole:d"].position != ref["pole:d"].position


def test_wire_starts_at_copper_point():
    s = Settings()
    plan = make_plan(poles()[:2], s, None)
    wire = next(i for i in plan.items if i.key == "wire:a:b")
    frame = plan.frames["a"]
    cu = SMALL.connection_points[frame].wire.copper
    assert wire.points[0] == pytest.approx(((10 + cu[0]) * s.tile_nm, (10 + cu[1]) * s.tile_nm), abs=IU_NM)


def test_settings_file(tmp_path):
    (tmp_path / config.SETTINGS_FILE).write_text(
        json.dumps({"tile_mm": 1.27, "textures": ["art"], "connection_mode": "mesh"})
    )
    s = config.load(tmp_path)
    assert s.tile_mm == 1.27
    assert s.connection_mode == "mesh"
    assert s.textures == (str((tmp_path / "art").resolve()),)
    assert config.load(tmp_path / "nowhere") == Settings()


def test_settings_file_rejects_typos(tmp_path):
    (tmp_path / config.SETTINGS_FILE).write_text(json.dumps({"tile_size": 1}))
    with pytest.raises(ValueError, match="unknown setting"):
        config.load(tmp_path)


def test_wire_shadow_starts_where_the_pole_shadow_ends():
    from factorio_poles import geometry

    s = Settings()
    plan = make_plan(poles()[:2], s, None)
    shadow = next(i for i in plan.items if i.key == "wire-shadow:a:b")
    cp = SMALL.connection_points[plan.frames["a"]]
    end = geometry.apply(geometry.shadow_matrix(cp.wire.copper, cp.shadow.copper, s.shadow_angle), cp.shadow.copper)
    assert shadow.points[0] == pytest.approx(((10 + end[0]) * s.tile_nm, (10 + end[1]) * s.tile_nm), abs=IU_NM)
    assert shadow.color[3] == s.shadow_opacity
    # By default shadows fall away from the viewer: up and to the right on the sheet.
    assert end[0] > 0 and end[1] < 0 and end[0] == pytest.approx(-end[1], rel=1e-6)
