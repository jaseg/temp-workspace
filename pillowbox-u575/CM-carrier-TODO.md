# Pillowbox: retarget from Pi 40-pin header to CM4/CM5 carrier

Items marked **verify** are from general CM4/CM5 platform knowledge, not checked against
datasheets in this project. Confirm against the CM4 and CM5 datasheets and the official
CM4/CM5 IO-board reference designs.

## Decisions (settled)

- Power: 12–24 V / 2 A arrives over the FPC; on-board 5 V / 5 A buck feeds the CM and U7.
- FPC carries **only** input power + the CM's Ethernet (4 MDI pairs, LEDs).
- Ethernet magnetics / RJ45 at the **far end** of the FPC.
- CM USB2 comes out on a **second on-board USB-C**; J5 stays for the STM32.
- microSD socket fitted (only used by CM4/CM5 Lite variants).
- DF40 mated height **3.0 mm** (components allowed under the module).
- No carrier ID EEPROM (CM carriers don't normally have one) → drop U11 and its parts.

## 5 V / 5 A buck (input 12–24 V, from the FPC)

LCSC stock/prices checked 2026-11-05 (USD, 100-pc price).

| Part | LCSC | Vin max | Type | LCSC stock | ~100 pc | Notes |
|---|---|---|---|---|---|---|
| **TPS54560BDDAR** (TI) | C1850354 | 60 V | async, 92 mΩ HS | 26 539 | $0.57 | Recommended: 60 V absorbs hot-plug ringing; needs a 5 A/60 V Schottky; WEBENCH/EVM available |
| RT6365GSP (Richtek) | C3024482 | 60 V | async, 70 mΩ HS | 8 234 | $0.76 | Same class as TPS54560B, 2nd-source candidate (pinout not checked) |
| **AP64500SP-13** (Diodes) | C2070920 | 40 V | **sync**, 45/20 mΩ, 6.8 A min peak limit | 1 972 | $1.13 | Best efficiency/least heat; 40 V needs a damped input (see below) |
| SCT2450STER (SCT) | C509400 | 36 V | sync, 45/20 mΩ | 1 620 | $1.98 | Sync alternative, less margin at 24 V |
| SCT2650STER (SCT) | C2840771 | 60 V | async, 80 mΩ HS | 10 830 | $1.97 | Works, but pricier than TPS54560B |
| LM76005RNPR (TI) | C2866241 | 60 V | sync | 5 474 | $3.74 | Only cheap-ish 60 V sync option; WQFN-30, not "inexpensive" |
| SY8205FCC | C111875 | 30 V | sync | 7 801 | $0.25 | **Rejected**: 30 V too close to 24 V + transients |
| XL4005E1 | C73332 | 32 V | async, 300 kHz | 33 526 | $0.59 | **Rejected**: 32 V, low frequency, big inductor |

- [ ] Pick TPS54560B (robust, cheapest) or AP64500 (cooler, needs input damping).
- [ ] Hot-plug of 24 V through cable + FPC can ring to ~2× Vin. A 40 V part cannot be protected
      by a TVS at 24 V nominal (a 24–26 V standoff TVS clamps above 40 V); add a damping bulk
      cap with real ESR (aluminium electrolytic / polymer, 50 V) at the input regardless.
- [ ] Input protection: reverse polarity (P-FET), TVS (SMBJ-class, standoff ≥ 26 V; fine for a
      60 V buck), fuse/PTC, π-filter so buck noise doesn't couple onto the FPC next to the MDI pairs.
- [ ] Rough parts for 400 kHz: L ≈ 6.8 µH, Isat ≥ 8 A; Schottky 5 A / 60 V (SS56/B560C class)
      for the async options; 50 V input MLCCs; ≥ 2×22 µF output + bulk.
- [ ] **Power budget**: 12 V × 2 A = 24 W in → ≈ 21 W at 5 V ≈ 4.2 A total, minus the board
      (~0.5 A) ≈ 3.6 A for the CM at 12 V input. The full 5 A is only available above ~15 V input.
      Tell CM5 firmware the supply limit (`usb_max_current_enable` etc., **verify**) and/or cap
      the downstream USB current.
- [ ] +5V net today = J5 VBUS + J4 5V + J3 pin 1 + U7 inputs. New: buck output → U7 + CM;
      **disconnect J5 VBUS from +5V** (VBUS sense only, or keep as standalone input via an
      ideal-diode OR — decide), remove J4, decide whether J3 pin 1 still exports +5V.
- [ ] Don't load the CM's own 3.3 V / 1.8 V outputs beyond their rating (**verify** limits).
- [ ] Power/reset control: GLOBAL_EN, RUN_PG (CM4), PWR_BUT (CM5) — STM32 control optional
      (**verify** pin names).

## FPC (power + Ethernet only)

- [ ] Pin plan: 12–24 V ×N, GND ×N (≥ 4+4 pins at ~0.5 A/pin for 0.5 mm FFC; fewer at 1.0 mm
      pitch — check connector/FFC current rating and drop), 4 MDI pairs G-S-S-G, 2 LED lines,
      3.3 V for LEDs. Power pins at one edge, MDI at the other, ground pins in between.
- [ ] 100 Ω ±10 % differential pairs over solid ground, length-matched within each pair;
      stackup/impedance from the flex vendor; keep the FPC short.
- [ ] Far-end board: MagJack/magnetics, center taps per CM4/CM5 IO-board design (CM4: caps
      only, not to a supply, **verify**), Bob Smith termination, shield → chassis via RC.
- [ ] Optional low-C TVS on the PHY side at the carrier end.
- [ ] No PoE.

## CM connectors and GPIO interface

- [ ] 2× Hirose DF40C-100DS (100-pin, 0.4 mm), 3.0 mm mated height. Official CM4 footprint
      and the CM5 compatibility table (**verify**).
- [ ] GPIO_VREF to the CM's 3.3 V output (3.3 V GPIO bank, matches the STM32) (**verify** CM5).
- [ ] Re-route the existing Pi nets by BCM GPIO number:
      - HOST_TX / HOST_RX → GPIO15 RXD / GPIO14 TXD
      - HOST_SCK / HOST_HIPO / HOST_HOPI / HOST_nCS → GPIO11 / GPIO9 / GPIO10 / GPIO8 (CE0)
      - HOST_ALM / HOST_ALMn → GPIO16 / GPIO17
- [ ] Fix the open name mismatch: `HOST_CS` (U15 PB12) vs `HOST_nCS` (J4 pin 24).
- [ ] Leave GPIO0/GPIO1 (ID_SD/ID_SC) free — firmware reserves them for HAT ID.
- [ ] Optional: STM32 NRST/BOOT0 to two spare CM GPIOs (flash the STM32 from the CM).
- [ ] Leave PCIe, HDMI, MIPI, USB3 unconnected (**verify** required straps/terminations).

## CM USB-C (second connector)

- [ ] Use the USB2 port common to CM4 (OTG) and CM5 (**verify** which CM5 port does rpiboot).
- [ ] Decide role: device-only (Rd 5.1 kΩ, rpiboot/gadget; VBUS only sensed, never fed into
      +5V) vs dual-role (CC controller, VBUS from +5V through a current-limited switch).
- [ ] ESD on D+/D− (another USBLC6), shield/CC per Type-C spec.
- [ ] nRPIBOOT jumper/button + test point; CM4 EEPROM_nWP decision (**verify** CM5).

## microSD

- [ ] Wire to the CM's SD pins (used only by Lite variants; eMMC variants leave them unused,
      **verify** for CM5).
- [ ] Card power switch driven by the CM's SD_PWR_ON (**verify**), 3.3 V card supply with
      decoupling, card-detect if supported, ESD on the lines.
- [ ] Short, matched SDIO routing.

## Clean-up of the current design

- [ ] Remove J4 (40-pin header).
- [ ] Remove the ID EEPROM: U11, R86/R87 (ID bus pull-ups), R90/R91 (E0 strap), R108 (WC
      pull-up); delete nets ID_EEP_SCL/SDA/~{WC}. Frees STM32 PB6, PB7, PC14.
- [ ] Console: GPIO14/15 are the STM32 link → disable the Linux serial console there or move it.
- [ ] Re-run ERC/connectivity; regenerate the MCU pin table.
- [ ] Software: device-tree overlays for UART/SPI0/GPIO on CM4 and CM5 (CM5 GPIOs via RP1).

## Mechanical / thermal

- [ ] 55 × 40 mm module outline, 4× M2.5 standoffs at 3 mm stack height.
- [ ] CM5 heat: heatsink/fan clearance; CM5 fan pins (**verify**).
- [ ] Keep the buck and its switching node away from the TDR front end and the hold nodes.
- [ ] Wireless variants: antenna keep-out / U.FL access.

## CM4 vs CM5 caveats

- Some CM4 pins were repurposed on CM5 (MIPI lanes ↔ USB3, power button, RTC battery, fan).
  None are used here; keep them unconnected so both modules work (**verify**).
- Size power and thermal for CM5. Bring up with both a CM4 and a CM5.
