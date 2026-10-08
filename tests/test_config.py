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
        ({"arc_mode": "banana"}, "arc_mode"),
        ({"depth": 0}, "depth"),
        ({"depth": 24.01}, "depth"),  # > 0.4 W for W=60
        ({"arc_mode": "sagitta", "sagitta": 12.01}, "sagitta"),  # > 0.2 W
        ({"length": 20}, "length"),  # curved folds of both ends would cross (depth 20)
        ({"glue_tab_width": 60}, "glue_tab_width"),  # must be narrower than the box
        ({"thickness": -0.1}, "thickness"),
        ({"thickness": 6}, "thickness"),
        ({"depth": 2, "thickness": 1.8}, "thickness"),  # cut sagitta would vanish
        ({"glue_tab_width": 1}, "glue_tab_width"),
        ({"glue_tab_taper": -1}, "glue_tab_taper"),
        ({"glue_tab_taper": 60}, "glue_tab_taper"),  # > L/2 - 1
        ({"stroke_width": 0}, "stroke_width"),
        ({"color_cut": "red"}, "color_cut"),
        ({"color_cut": "#12345"}, "color_cut"),
        ({"color_fold_curved": 0xFF0000}, "color_fold_curved"),
        ({"thumb_notch": "yes"}, "thumb_notch"),
        ({"thumb_notch": True, "thumb_notch_radius": 29.9}, "thumb_notch_radius"),
        ({"thumb_notch": True, "thumb_notch_radius": 0.5}, "thumb_notch_radius"),
        ({"label": True, "label_text": "   "}, "label_text"),
        ({"label_text": "x" * 65}, "label_text"),
        ({"label_text": 5}, "label_text"),
        ({"label_size": 0}, "label_size"),
    ],
)
def test_validation_errors(changes, field):
    errs = errors_for(**changes)
    assert field in errs, errs


def test_boundary_values_accepted():
    w = 60
    assert Config.from_dict({"depth": 0.4 * w}).depth == 24
    assert Config.from_dict({"length": 21}).length == 21
    assert Config.from_dict({"glue_tab_taper": 59}).glue_tab_taper == 59
    assert Config.from_dict({"glue_tab_taper": 0, "thickness": 0}).thickness == 0
    assert (
        Config.from_dict(
            {"width": 10, "length": 10, "depth": 4, "glue_tab_taper": 4, "glue_tab_width": 5}
        ).width
        == 10
    )


def test_notch_radius_ignored_when_disabled():
    assert Config.from_dict({"thumb_notch": False, "thumb_notch_radius": 100})


def test_multiple_errors_reported_together():
    errs = errors_for(width="x", color_cut="nope", stroke_width=10)
    assert set(errs) >= {"width", "color_cut", "stroke_width"}


def test_colors_normalised():
    assert Config.from_dict({"color_cut": " #abcdef"}).color_cut == "#ABCDEF"


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
    assert parse_cli_value("thumb_notch", "yes") is True
    assert parse_cli_value("thumb_notch", "0") is False
    assert parse_cli_value("label_text", "a=b") == "a=b"
    with pytest.raises(ConfigError):
        parse_cli_value("nope", "1")
    with pytest.raises(ConfigError):
        parse_cli_value("width", "abc")
