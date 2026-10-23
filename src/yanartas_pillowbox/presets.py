"""Presets: approximate outer sizes of common development boards for the payload (UI
convenience), and FPC connector series for the cable's plug (a setting: ``fpc_connector``).

Each preset sets the payload's width (across the box: the board's short side), depth (along
the box: its long side) and height (the full stack, from the solder joints underneath to the
tallest connector or add-on board on top). Heights are rounded up and partly estimated from
typical connector heights, so they are a starting point: measure your own board
(with cables) before cutting.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PayloadPreset:
    id: str
    label: str
    group: str
    width: float
    depth: float
    height: float


PAYLOAD_PRESETS: tuple[PayloadPreset, ...] = (
    # Raspberry Pi: Model A (3A+) 65 x 56 mm, Model B (4/5) 85 x 56 mm (Pi 5: 85 x 56 x 20 mm
    # overall). A HAT sits on 11 mm standoffs above the board and adds about 2 mm over the
    # Model B's USB/Ethernet stacks (or 9 mm on a Model A).
    PayloadPreset("rpi-a", "Raspberry Pi Model A (3A+)", "Raspberry Pi", 56, 65, 12),
    PayloadPreset("rpi-a-hat", "Raspberry Pi Model A + HAT", "Raspberry Pi", 56, 65, 21),
    PayloadPreset("rpi-b", "Raspberry Pi Model B (4 / 5)", "Raspberry Pi", 56, 85, 20),
    PayloadPreset("rpi-b-hat", "Raspberry Pi Model B + HAT", "Raspberry Pi", 56, 85, 22),
    PayloadPreset("rpi-zero", "Raspberry Pi Zero / Zero 2 W", "Raspberry Pi", 30, 65, 6),
    PayloadPreset("rpi-zero-phat", "Raspberry Pi Zero + pHAT", "Raspberry Pi", 30, 65, 16),
    # Arduino UNO Q: Uno outline, 68.58 x 53.34 mm; female headers on top, a shield stacks on
    # them.
    PayloadPreset("uno-q", "Arduino UNO Q", "Arduino", 53.5, 69, 14),
    PayloadPreset("uno-q-shield", "Arduino UNO Q + shield", "Arduino", 53.5, 69, 24),
    PayloadPreset("stm32-nucleo-64", "STM32 Nucleo-64", "Microcontroller boards", 70, 82.5, 22),
    # Linux SBCs. Odroid N2+: 100 x 91 x 18.75 mm including its heatsink.
    PayloadPreset("beaglebone-black", "BeagleBone Black", "Linux SBCs", 54.5, 86.5, 17),
    PayloadPreset("odroid-c4", "Odroid C4", "Linux SBCs", 56, 85, 20),
    PayloadPreset("odroid-n2plus", "Odroid N2+ (with heatsink)", "Linux SBCs", 91, 100, 20),
    # NVIDIA: the Orin Nano (Super) developer kit is 103 x 90.5 x 34.77 mm; the Orin Nano 2
    # keeps the same form factor.
    PayloadPreset(
        "jetson-orin-nano", "Jetson Orin Nano / Super dev kit", "NVIDIA Jetson", 90.5, 103, 35
    ),
    PayloadPreset("jetson-orin-nano-2", "Jetson Orin Nano 2", "NVIDIA Jetson", 90.5, 103, 35),
)


def presets_json() -> list[dict[str, Any]]:
    return [asdict(p) for p in PAYLOAD_PRESETS]


# ----------------------------------------------------------------------------- connectors
CUSTOM = "custom"


@dataclass(frozen=True)
class ConnectorSeries:
    """An FPC connector series: what its makers recommend for the FPC's end (the cable's
    plug), and the contact counts stocked at Mouser, Digi-Key or LCSC. The plug's width is
    ``(pins - 1) * pitch + 2 * edge_margin``; ``plug_length`` is how far back from its end
    the FPC is stiffened (and its contacts exposed: less)."""

    id: str
    label: str  # (with the pitch: the dropdown's group)
    pitch: float
    edge_margin: float
    plug_length: float
    pins: tuple[int, ...]


# From the makers' recommended FPC dimensions (every one of these: the FPC (pins + 1) x pitch
# wide, so the edge margin is one pitch; the plug's length the stiffened end), and the
# contact counts in stock at LCSC (checked 2026-10-23; Mouser's and Digi-Key's stock not).
# Left out: Hirose FH35C (0.3 mm: its contacts staggered in two rows, which the plug's
# footprint does not draw) and Molex 52745 (no drawing to be had).
CONNECTOR_SERIES: tuple[ConnectorSeries, ...] = (
    # Hirose FH12, flip lock, bottom contact: stiffener 4.5 min, contacts exposed 3.5 min.
    ConnectorSeries(
        "hirose-fh12", "Hirose FH12 (0.5 mm)", 0.5, 0.5, 4.5,
        (6, 8, 10, 11, 12, 15, 16, 18, 20, 22, 24, 26, 28, 30, 32, 33, 34, 36, 40, 45, 50, 53),
    ),
    # Hirose FH34SRJ, back flip, 1 mm high: stiffening film 2.5 ± 0.3 (contacts exposed 1.5).
    ConnectorSeries(
        "hirose-fh34srj", "Hirose FH34SRJ (0.5 mm)", 0.5, 0.5, 2.5,
        (4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 18, 20, 22, 24, 26, 30, 34, 40, 45, 50),
    ),
    # Molex Easy-On 503480, back flip: stiffener 3 min, contacts exposed 2 min.
    ConnectorSeries(
        "molex-503480", "Molex 503480 (0.5 mm)", 0.5, 0.5, 3.0,
        (6, 8, 10, 12, 14, 16, 20, 22, 26, 32),
    ),
    # Omron XF2M, rotary back lock: stiffener 4.5, contacts exposed 2.5 min.
    ConnectorSeries(
        "omron-xf2m", "Omron XF2M (0.5 mm)", 0.5, 0.5, 4.5,
        (6, 8, 10, 12, 14, 18, 20, 22, 26, 30, 32, 33, 34, 38, 40, 45, 50, 54, 60),
    ),
    # TE Connectivity 1734839, top contact: stiffener 4.5 min, contacts exposed 3.5 min.
    ConnectorSeries("te-1734839", "TE 1734839 (0.5 mm)", 0.5, 0.5, 4.5, (16, 18, 20, 31)),
    # XUNPU FPC-05F (a generic LCSC part), flip, bottom contact: stiffener 6.
    ConnectorSeries(
        "xunpu-fpc-05f", "XUNPU FPC-05F (0.5 mm)", 0.5, 0.5, 6.0,
        (6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 36, 40, 50),
    ),
    # TE Connectivity 84953, 1 mm, top contact: backing 3.8 min, contacts exposed 2.7 min.
    ConnectorSeries(
        "te-84953", "TE 84953 (1.0 mm)", 1.0, 1.0, 3.8, (4, 5, 6, 9, 10, 14, 15, 18, 20)
    ),
)  # fmt: skip


def connector_choices() -> list[tuple[str, str, str, dict[str, float]]]:
    """Each preset (series and pin count): (value, label, group, the settings it fixes)."""
    out = []
    for s in CONNECTOR_SERIES:
        for n in s.pins:
            values = {
                "fpc_pins": float(n),
                "fpc_pitch": s.pitch,
                "fpc_edge_margin": s.edge_margin,
                "fpc_plug_length": s.plug_length,
            }
            out.append((f"{s.id}-{n}", f"{s.label.split(' (')[0]}, {n} pins", s.label, values))
    return out


def connector_values(value: str) -> dict[str, float] | None:
    """The settings the preset ``value`` fixes; none for ``custom``."""
    for v, _, _, values in connector_choices():
        if v == value:
            return values
    return None
