"""Test-wide setup. The tests use 0.4 mm material (most expected values assume it), while
the UI default is thinner: ``Config.defaults()``, and so every config built from it, gets
0.4 mm here."""

from dataclasses import replace

from yanartas_pillowbox.config import Config

_ui_defaults = Config.defaults.__func__  # type: ignore[attr-defined]


def _test_defaults(cls: type[Config]) -> Config:
    return replace(_ui_defaults(cls), thickness=0.4)


Config.defaults = classmethod(_test_defaults)  # type: ignore[method-assign]
