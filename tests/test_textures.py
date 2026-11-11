import io

import pytest
from factorio_poles import textures
from factorio_poles.prototypes import BIG, POLE_TYPES, SMALL
from factorio_poles.textures import BUNDLED, TextureError, TexturePack, check_sheet, kicad_image_scale
from PIL import Image


@pytest.mark.parametrize("pole", POLE_TYPES, ids=lambda p: p.name)
def test_bundled_textures_match_factorio_layout(pole):
    for sheet in (pole.picture, pole.shadow):
        assert check_sheet(BUNDLED / sheet.filename, sheet) is None


def test_sprite_is_trimmed_and_positioned():
    pack = TexturePack([BUNDLED])
    s = pack.sprite(SMALL, 0, shadow=False)
    img = Image.open(io.BytesIO(s.png))
    assert img.size == s.size_px
    assert img.info["dpi"][0] == pytest.approx(textures.PNG_PPI, abs=0.01)
    assert s.size_px[0] <= SMALL.picture.width and s.size_px[1] <= SMALL.picture.height
    # The pole stands on its position: the image's bottom edge is just below it, the top
    # reaches the wire connection point.
    top = s.center[1] - s.size_px[1] * s.tiles_per_pixel / 2
    bottom = s.center[1] + s.size_px[1] * s.tiles_per_pixel / 2
    assert top <= SMALL.connection_points[0].wire.copper[1]
    assert 0 < bottom < 0.5


def test_shadow_extends_sprite_towards_the_sun_direction():
    pack = TexturePack([BUNDLED])
    plain = pack.sprite(BIG, 2, shadow=False)
    shaded = pack.sprite(BIG, 2, shadow=True)
    right = lambda s: s.center[0] + s.size_px[0] * s.tiles_per_pixel / 2
    assert right(shaded) > right(plain) + 1
    assert right(shaded) >= BIG.connection_points[2].shadow.copper[0]


def test_sprites_are_cached():
    pack = TexturePack([BUNDLED])
    assert pack.sprite(SMALL, 1) is pack.sprite(SMALL, 1)


def test_wrong_sized_sheet_falls_back(tmp_path):
    bad = tmp_path / SMALL.picture.filename
    bad.parent.mkdir(parents=True)
    Image.new("RGBA", (10, 10)).save(bad)
    pack = TexturePack([tmp_path, BUNDLED])
    assert pack.resolve(SMALL.picture) == BUNDLED / SMALL.picture.filename
    assert any("expected 288x220" in w for w in pack.warnings)


def test_missing_everywhere(tmp_path):
    with pytest.raises(TextureError):
        TexturePack([tmp_path]).resolve(SMALL.picture)


def test_search_path_order(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORIO_POLES_TEXTURES", str(tmp_path / "env"))
    roots = textures.search_path([tmp_path / "cfg"], use_factorio=False)
    assert roots == [tmp_path / "cfg", tmp_path / "env", BUNDLED]


def test_image_scale():
    # 64 sprite pixels per tile at 2.54 mm per tile: 0.039688 mm per pixel; native is 25.4/300.
    assert kicad_image_scale(0.5 / 32, 2.54) == pytest.approx((2.54 / 64) / (25.4 / 300))


def test_shadow_recast_at_45_degrees():
    pack = TexturePack([BUNDLED])
    game = pack.sprite(BIG, 0, shadow=True)
    diag = pack.sprite(BIG, 0, shadow=True, shadow_angle=45)
    bottom = lambda s: s.center[1] + s.size_px[1] * s.tiles_per_pixel / 2
    right = lambda s: s.center[0] + s.size_px[0] * s.tiles_per_pixel / 2
    # The game's shadow runs right along the ground; at 45 degrees it reaches as far down as right.
    assert bottom(diag) > bottom(game) + 2
    assert right(diag) < right(game)


def test_shadow_opacity():
    pack = TexturePack([BUNDLED])

    def shadow_alpha(opacity):
        # Total alpha with the shadow minus without it: the shadow's own contribution.
        with_shadow = Image.open(io.BytesIO(pack.sprite(SMALL, 0, True, 45, opacity).png))
        without = Image.open(io.BytesIO(pack.sprite(SMALL, 0, False).png))
        total = lambda im: sum(im.getchannel("A").histogram()[v] * v for v in range(256))
        return total(with_shadow) - total(without)

    light, dark = shadow_alpha(0.2), shadow_alpha(0.5)
    assert 0 < light < dark
    assert light / dark == pytest.approx(0.4, rel=0.1)
