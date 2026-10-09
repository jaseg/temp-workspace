"""Payload presets: approximate outer sizes of common development boards (UI convenience).

Each preset sets the payload's width (across the box: the board's short side), depth (along
the box: its long side) and height (the full stack, from the solder joints underneath to the
tallest connector or add-on board on top). Heights are rounded up and partly estimated from
typical connector and header heights, so they are a starting point: measure your own board
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
    # Arduino UNO Q: Uno footprint, 68.58 x 53.34 mm; female headers on top, a shield stacks on
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
