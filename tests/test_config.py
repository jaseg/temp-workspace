import math

import pytest

from yanartas_pillowbox.config import (
    FIELD_SPECS,
    SCHEMA_VERSION,
    Config,
    ConfigError,
    SchemaVersionError,
    parse_cli_value,
)
from yanartas_pillowbox.crosssection import CrossSection, max_height, panel_width

MAX_H_55 = max_height(55.0, 0.4)  # the default box is 55 mm wide, 0.4 mm material


def errors_for(**changes):
    with pytest.raises(ConfigError) as info:
        Config.from_dict({**Config.defaults().to_dict(), **changes})
    return info.value.errors


def test_defaults_are_valid():
    cfg = Config.defaults()
    assert Config.from_dict(cfg.to_dict()) == cfg
    assert cfg.to_dict()["version"] == SCHEMA_VERSION


def test_every_field_has_a_spec():
    names = {s.name for s in FIELD_SPECS}
    assert names == set(Config.defaults().to_dict()) - {"version"}


def test_missing_fields_use_defaults():
    assert Config.from_dict({"width": 80}).width == 80
    assert Config.from_dict({}) == Config.defaults()


def test_ints_coerced_to_float():
    cfg = Config.from_dict({"width": 80})
    assert isinstance(cfg.width, float)


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"width": "wide"}, "width"),
        ({"width": True}, "width"),
        ({"width": math.nan}, "width"),
        ({"width": math.inf}, "width"),
        ({"width": 5}, "width"),
        ({"length": 0}, "length"),
        ({"length": -1}, "length"),
        ({"height": 0}, "height"),
        ({"height": MAX_H_55 + 0.01}, "height"),  # too steep for a 55 mm wide box
        ({"glue_tab_width": 60.4}, "glue_tab_width"),  # wider than the front panel (60.33)
        ({"thickness": -0.1}, "thickness"),
        ({"thickness": 6}, "thickness"),
        ({"height": 2, "thickness": 1.6}, "thickness"),  # inner flaps would vanish
        ({"glue_tab_width": 1}, "glue_tab_width"),
        ({"glue_tab_taper": -1}, "glue_tab_taper"),
        ({"glue_tab_taper": 70}, "glue_tab_taper"),  # > edge/2 - 1 = (120 + 20 + 1.2)/2 - 1
    ],
)
def test_validation_errors(changes, field):
    errs = errors_for(**changes)
    assert field in errs, errs


def test_boundary_values_accepted():
    assert Config.from_dict({"height": MAX_H_55}).height == MAX_H_55
    assert Config.from_dict({"glue_tab_width": 60.3}).glue_tab_width == 60.3
    assert Config.from_dict({"glue_tab_taper": 69.6}).glue_tab_taper == 69.6
    assert Config.from_dict({"glue_tab_taper": 0, "thickness": 0}).thickness == 0
    assert (
        Config.from_dict(
            {
                "width": 10,
                "length": 10,
                "height": 4,
                "glue_tab_taper": 4,
                "glue_tab_width": 5,
                "interior_walls": False,
            }
        ).width
        == 10
    )


def test_length_is_measured_on_the_midline():
    """``length`` runs between the inner end walls on the centreline; the straight edges are
    longer by the height and three thicknesses (inner wall at height/2 + t from the corner
    line, plus half its thickness, at both ends)."""
    cfg = Config.from_dict({"length": 100, "height": 24, "thickness": 0.5})
    assert cfg.edge_length == pytest.approx(125.5)
    assert Config.from_dict({"length": 100, "height": 24, "thickness": 0}).edge_length == 124


def test_multiple_errors_reported_together():
    errs = errors_for(width="x", length="nope", thickness=10)
    assert set(errs) >= {"width", "length", "thickness"}


def test_print_side_validated():
    assert Config.from_dict({"print_side": "inside"}).print_side == "inside"
    assert "print_side" in errors_for(print_side="top")


def test_version_handling():
    with pytest.raises(SchemaVersionError):
        Config.from_dict({"version": 0})
    with pytest.raises(SchemaVersionError):
        Config.from_dict({"version": "1"})
    with pytest.raises(SchemaVersionError):
        Config.from_dict({}, require_version=True)
    assert Config.from_dict({"version": SCHEMA_VERSION}) == Config.defaults()


def test_not_a_dict():
    with pytest.raises(ConfigError):
        Config.from_dict([1, 2])


def test_unknown_keys_ignored():
    assert Config.from_dict({"bogus": 1}) == Config.defaults()


def test_cli_value_parsing():
    assert parse_cli_value("width", "80") == 80.0
    assert parse_cli_value("payload_margin", "2.5") == 2.5
    with pytest.raises(ConfigError):
        parse_cli_value("nope", "1")
    with pytest.raises(ConfigError):
        parse_cli_value("width", "abc")


# ------------------------------------------------------------------ width / circumference
@pytest.mark.parametrize(
    ("width", "arc"),
    [
        (55, {"height": 20}),
        (10, {"height": 3}),
        (300, {"height": 110}),
        (80, {"height": 1}),
        (55, {"height": MAX_H_55}),
    ],
)
@pytest.mark.parametrize("t", [0.0, 0.4, 1.5])
def test_width_drives_the_cross_section(width, arc, t):
    """``width`` is the interior cross-section width, between the material's inner corners at
    the two side folds; the flat panel widths are derived from it."""
    if arc["height"] - t < 0.5 or arc["height"] > max_height(width, t):
        pytest.skip("not a valid box")
    cfg = Config.from_dict(
        {
            "width": width,
            "length": 400,
            "glue_tab_width": 5,
            "thickness": t,
            "interior_walls": False,
            **arc,
        }
    )
    body = cfg.body
    assert body.inner_fold[0] - body.inner_glue[0] == pytest.approx(width, rel=1e-10)
    assert body.inner_fold[0] == pytest.approx(width / 2, rel=1e-10)  # centred
    assert cfg.circumference == pytest.approx(body.front.width + body.back.width)
    if t == 0:  # zero thickness: both panels are the plain cross-section of that width
        for sec in (body.front, body.back):
            assert sec.width == pytest.approx(panel_width(width, arc["height"] / 2), rel=1e-12)
            assert CrossSection(sec.width, sec.sagitta).closed_width == pytest.approx(width)
    else:  # the material sits outside the interior
        assert body.front.closed_width > width and body.back.closed_width > width


def test_interior_height_and_flap_offsets():
    """The panels' inner surfaces are height/2 above and below the centre; the outer (front)
    flaps' wall stands t outside the inner (back) flaps' wall."""
    cfg = Config.from_dict({"height": 18, "thickness": 0.8})
    body = cfg.body
    front_inner = body.front_point(body.front.width / 2)[1] - 0.4
    back_inner = body.back_point(body.back.width / 2)[1] + 0.4
    assert (front_inner, back_inner) == pytest.approx((9, -9))
    assert body.back.sagitta - body.front.sagitta == pytest.approx(0.8)
    # Outer flaps reach the back panel's outer surface, inner flaps the front's inner surface.
    # (exactly at the panels' apexes, which are a fraction of t apart across the box)
    assert body.front.sagitta + body.front_cut_sagitta == pytest.approx(18 + 1.2, abs=0.01)
    assert body.back.sagitta + body.back_cut_sagitta == pytest.approx(18 + 0.4)


def test_circumference_is_computed_not_stored():
    cfg = Config.defaults()
    assert "circumference" not in cfg.to_dict() and "panel_width" not in cfg.to_dict()
    assert Config.from_dict({"circumference": 999}) == cfg  # unknown keys are ignored


def test_interior_wall_validation():
    errs = errors_for(interior_wall_offset=60)  # no room left in a 120 mm box
    assert "interior_wall_offset" in errs
    errs = errors_for(height=1, thickness=0.4, payload_height=0.5)  # too low for the walls
    assert "interior_walls" in errs
    errs = errors_for(fpc_cutout="both", fpc_cutout_width=59)  # wider than the walls
    assert "fpc_cutout_width" in errs
