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
from yanartas_pillowbox.crosssection import CrossSection, max_sagitta

MAX_SAG_55 = max_sagitta(55.0)  # the default box is 55 mm wide


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
        ({"height": 2 * MAX_SAG_55 + 0.01}, "height"),  # too steep for a 55 mm wide box
        ({"glue_tab_width": 60.2}, "glue_tab_width"),  # wider than one panel (60.11 mm)
        ({"thickness": -0.1}, "thickness"),
        ({"thickness": 6}, "thickness"),
        ({"height": 2, "thickness": 1.8}, "thickness"),  # cut sagitta would vanish
        ({"glue_tab_width": 1}, "glue_tab_width"),
        ({"glue_tab_taper": -1}, "glue_tab_taper"),
        ({"glue_tab_taper": 70}, "glue_tab_taper"),  # > edge/2 - 1 = (120 + 20)/2 - 1
    ],
)
def test_validation_errors(changes, field):
    errs = errors_for(**changes)
    assert field in errs, errs


def test_boundary_values_accepted():
    assert Config.from_dict({"height": 2 * MAX_SAG_55}).height == 2 * MAX_SAG_55
    assert Config.from_dict({"glue_tab_width": 60}).glue_tab_width == 60
    assert Config.from_dict({"glue_tab_taper": 69}).glue_tab_taper == 69
    assert Config.from_dict({"glue_tab_taper": 0, "thickness": 0}).thickness == 0
    assert (
        Config.from_dict(
            {"width": 10, "length": 10, "height": 4, "glue_tab_taper": 4, "glue_tab_width": 5}
        ).width
        == 10
    )


def test_length_is_measured_on_the_midline():
    """``length`` runs between the curved folds' apexes; the straight edges are longer by
    the fold sagitta at each end, i.e. by the height."""
    cfg = Config.from_dict({"length": 100, "height": 24})
    assert cfg.edge_length == pytest.approx(124)


def test_removed_options_are_ignored():
    old = {"stroke_width": 0.5, "thumb_notch": True, "label": True, "arc_mode": "sagitta"}
    assert Config.from_dict(old) == Config.defaults()


def test_multiple_errors_reported_together():
    errs = errors_for(width="x", length="nope", thickness=10)
    assert set(errs) >= {"width", "length", "thickness"}


def test_old_color_settings_are_ignored():
    assert Config.from_dict({"color_cut": "#00FF00"}) == Config.defaults()


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
        (55, {"height": 2 * MAX_SAG_55}),
    ],
)
def test_width_drives_the_cross_section(width, arc):
    """``width`` is the closed cross-section width; the flat panel width (half the
    circumference) is derived so that the folded panel spans exactly that width."""
    cfg = Config.from_dict({"width": width, "length": 400, "glue_tab_width": 5, **arc})
    section = CrossSection(cfg.panel_width, cfg.fold_sagitta)
    assert section.closed_width == pytest.approx(width, rel=1e-12)
    assert cfg.circumference == pytest.approx(2 * cfg.panel_width)
    assert cfg.panel_width > width  # the bulge needs more material than the chord


def test_circumference_is_computed_not_stored():
    cfg = Config.defaults()
    assert "circumference" not in cfg.to_dict() and "panel_width" not in cfg.to_dict()
    assert Config.from_dict({"circumference": 999}) == cfg  # unknown keys are ignored


def test_v1_documents_are_migrated():
    """Schema 1 stored the flat panel width as ``width``; loading converts it to the closed
    width so the box (and its pattern) stays the same."""
    v1 = {"version": 1, "width": 60.0, "depth": 20.0, "length": 100.0}
    cfg = Config.from_dict(v1, require_version=True)
    assert cfg.panel_width == pytest.approx(60.0, abs=1e-4)
    assert cfg.width == pytest.approx(CrossSection(60.0, 10.0).closed_width, abs=1e-4)
    assert cfg.edge_length == 100.0 and cfg.to_dict()["version"] == SCHEMA_VERSION
    # Missing fields use the version-1 defaults (60 mm panel, depth 20).
    assert Config.from_dict({"version": 1}).panel_width == pytest.approx(60.0, abs=1e-4)
    sag = Config.from_dict({"version": 1, "width": 80, "arc_mode": "sagitta", "sagitta": 5})
    assert sag.panel_width == pytest.approx(80.0, abs=1e-4) and sag.height == 10
    with pytest.raises(ConfigError) as info:
        Config.from_dict({"version": 1, "width": -3})
    assert "width" in info.value.errors


def test_v2_documents_are_migrated():
    """Schema 2 called the height ``depth``, could set the sagitta directly, and measured
    ``length`` corner to corner. Loading keeps the same box."""
    v2 = {"version": 2, "width": 50.0, "depth": 16.0, "length": 116.0, "stroke_width": 0.2}
    cfg = Config.from_dict(v2, require_version=True)
    assert (cfg.width, cfg.height, cfg.length, cfg.edge_length) == (50, 16, 100, 116)
    sag = Config.from_dict({"version": 2, "arc_mode": "sagitta", "sagitta": 7, "length": 120})
    assert (sag.height, sag.edge_length) == (14, 120)
    assert Config.from_dict({"version": 2}).edge_length == 120  # v2 defaults: 120, depth 20
