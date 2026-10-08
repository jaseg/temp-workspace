"""Laser-ready SVG folding patterns for pillow boxes."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("yanartas-pillowbox")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0"
