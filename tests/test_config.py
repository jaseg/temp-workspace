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

D = Config.defaults()
MAX_H = max_height(D.width, D.thickness)  # the steepest box of the default width
NARROW = {"width": 55, "height": 20, "fpc_cable": "none"}  # a front panel under the tab limit
WF = Config.from_dict(NARROW).shell.front.width


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
    assert Config.from_dict({"width": D.width + 10}).width == D.width + 10
    assert Config.from_dict({}) == Config.defaults()


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
        ({"height": MAX_H + 0.01}, "height"),  # too steep for the default box
        ({**NARROW, "glue_tab_width": WF + 0.01}, "glue_tab_width"),  # wider than the panel
        ({"thickness": -0.1}, "thickness"),
        ({"thickness": 6}, "thickness"),
        ({"height": 2, "thickness": 1.6}, "thickness"),  # inner flaps would vanish
        ({"glue_tab_width": 1}, "glue_tab_width"),
        ({"end_wall_gap": -1}, "end_wall_gap"),
        ({"end_wall_gap": 501}, "end_wall_gap"),
        ({"lid_overlap": -1}, "lid_overlap"),
        ({"mesh_partitions": 0}, "mesh_partitions"),
        ({"mesh_partitions": 2.5}, "mesh_partitions"),
        ({"mesh_partitions": 17}, "mesh_partitions"),
        ({"fpc_cable": "back"}, "fpc_cable"),  # (schema 8's ends: now up or down)
    ],
)
def test_validation_errors(changes, field):
    errs = errors_for(**changes)
    assert field in errs, errs


def test_boundary_values_accepted():
    # (the steepest box is too steep at the sides for lids: no end wall gap)
    assert (
        Config.from_dict({"height": MAX_H, "end_wall_gap": 0, "fpc_cable": "none"}).height == MAX_H
    )
    assert Config.from_dict({**NARROW, "glue_tab_width": WF - 0.01}).glue_tab_width == WF - 0.01
    assert Config.from_dict({"thickness": 0}).thickness == 0
    assert (
        Config.from_dict(
            {
                "width": 10,
                "length": 10,
                "height": 4,
                "glue_tab_width": 5,
                "end_wall_gap": 0,
                "fpc_cable": "none",
            }
        ).width
        == 10
    )


def test_length_is_measured_on_the_midline():
    """``length`` runs between the inner end walls on the centreline; the straight edges are
    longer by the height and three thicknesses (inner wall at height/2 + t from the corner
    line, plus half its thickness, at both ends)."""
    cfg = Config.from_dict(
        {"length": 100, "height": 24, "thickness": 0.5, "lid_offset": 0, "fpc_cable": "none"}
    )
    assert cfg.edge_length == pytest.approx(125.5)
    assert (
        Config.from_dict(
            {"length": 100, "height": 24, "thickness": 0, "fpc_cable": "none"}
        ).edge_length
        == 124
    )


def test_end_wall_gap_lengthens_the_front_panel():
    """The front panel runs on by the end wall gap at each end; the back panel (and the
    interior) keep their length."""
    cfg = Config.from_dict(
        {
            "length": 100,
            "height": 24,
            "thickness": 0.5,
            "end_wall_gap": 7,
            "lid_offset": 0,
            "fpc_cable": "none",
        }
    )
    assert cfg.edge_length == pytest.approx(125.5)
    assert cfg.front_length == pytest.approx(139.5)
    assert cfg.with_values(end_wall_gap=0).front_length == pytest.approx(125.5)


def test_lid_offset_is_limited_by_the_45_degree_turn():
    """The lid offset widens the end sections along the front panel's continued fold arc,
    which has to stay under 45 degrees: the limit is stated, and a box too steep for even a
    resting lid asks for no gap."""
    from yanartas_pillowbox.geometry import max_lid_offset

    cfg = Config.defaults()
    limit = max_lid_offset(cfg.shell)
    assert cfg.with_values(lid_offset=math.floor(limit * 100) / 100)
    errs = errors_for(lid_offset=limit + 0.1)
    assert "lid_offset" in errs and "45 degrees" in errs["lid_offset"]
    steep = {
        "width": 55,
        "height": max_height(55.0, 0.4),
        "thickness": 0.4,
        "lid_offset": 0,
        "fpc_cable": "none",
    }
    assert "end_wall_gap" in errors_for(**steep)  # steepest box: no room for lids
    assert Config.from_dict({**steep, "end_wall_gap": 0})


def test_multiple_errors_reported_together():
    errs = errors_for(width="x", length="nope", thickness=10)
    assert set(errs) >= {"width", "length", "thickness"}


def test_print_side_validated():
    assert Config.from_dict({"print_side": "inside"}).print_side == "inside"
    assert "print_side" in errors_for(print_side="top")


def test_version_check():
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
    assert parse_cli_value("payload_clearance", "2.5") == 2.5
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
        (55, {"height": MAX_H}),
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
            "end_wall_gap": 0,  # (lids need a flat enough box)
            "fpc_cable": "none",
            **arc,
        }
    )
    shell = cfg.shell
    assert shell.inner_fold[0] - shell.inner_glue[0] == pytest.approx(width, rel=1e-10)
    assert shell.inner_fold[0] == pytest.approx(width / 2, rel=1e-10)  # centred
    if t == 0:  # zero thickness: both panels are the plain cross-section of that width
        for sec in (shell.front, shell.back):
            assert sec.width == pytest.approx(panel_width(width, arc["height"] / 2), rel=1e-12)
            assert CrossSection(sec.width, sec.sagitta).closed_width == pytest.approx(width)
    else:  # the material sits outside the interior
        assert shell.front.closed_width > width and shell.back.closed_width > width


def test_interior_height_and_flap_offsets():
    """The panels' inner surfaces are height/2 above and below the centre; the outer (front)
    flaps' wall stands t outside the inner (back) flaps' wall."""
    cfg = Config.from_dict({"height": 18, "thickness": 0.8, "fpc_cable": "none"})
    shell = cfg.shell
    front_inner = shell.front_point(shell.front.width / 2)[1] - 0.4
    back_inner = shell.back_point(shell.back.width / 2)[1] + 0.4
    assert (front_inner, back_inner) == pytest.approx((9, -9))
    assert shell.back.sagitta - shell.front.sagitta == pytest.approx(0.8)
    # Outer flaps reach the back panel's outer surface, inner flaps the front's inner surface.
    # (exactly at the panels' apexes, which are a fraction of t apart across the box)
    assert shell.front.sagitta + shell.front_cut_sagitta == pytest.approx(18 + 1.2, abs=0.01)
    back_cut = shell.back_cuts[len(shell.back_cuts) // 2][1]
    assert shell.back.sagitta + back_cut == pytest.approx(18 + 0.4, abs=0.01)


def test_mesh_nets_per_side():
    """The space-filling curve's partitions each carry the set traces; KiMesh has no
    partitions."""
    d = Config.defaults()
    assert (d.mesh_partitions, d.mesh_traces, d.mesh_algorithm) == (3, 4, "kimesh")
    assert d.mesh_nets == 4
    assert d.with_values(mesh_algorithm="sfc").mesh_nets == 12
    assert d.with_values(mesh_algorithm="sfc", mesh_partitions=1, mesh_traces=5).mesh_nets == 5


def test_mesh_seed_is_any_text():
    """The mesh seed takes any text, the layout's seed its SHA-256 hash: the same every
    time, another for other text."""
    cfg = Config.defaults()
    a = cfg.with_values(mesh_seed="hello, box")
    assert a.seed == cfg.with_values(mesh_seed="hello, box").seed
    assert a.seed != cfg.with_values(mesh_seed="hello, box!").seed != cfg.seed
    assert 0 <= a.seed < 2**63 and cfg.with_values(mesh_seed="").seed >= 0
    assert parse_cli_value("mesh_seed", "my box") == "my box"
    assert errors_for(mesh_seed=1) == {"mesh_seed": "must be text"}
