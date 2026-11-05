# Pillowbox: retarget from Pi 40-pin header to CM4/CM5 carrier

Items marked **verify** are from general CM4/CM5 platform knowledge, not checked against
datasheets in this project. Confirm against the CM4 and CM5 datasheets and the official
CM4/CM5 IO-board reference designs.

## Decisions first

- [ ] **Power input**: USB-C PD sink (9–20 V → 5 V buck) vs. plain 5 V/5 A input. 5.1 kΩ Rd
      only (today's J5) caps the board at 3 A @ 5 V, and only with a 3 A source: too little
      for CM5 + USB devices. Raspberry Pi's CM5 IO board uses a 27 W PD supply (**verify**).
- [ ] **Role of J5**: power-only, power + STM32 USB, or power + CM USB2 (rpiboot/flashing).
- [ ] **Lite variants** (no eMMC): support them (microSD socket on the SD pins) or not.
- [ ] **Ethernet magnetics location**: far end of the FPC (recommended) or on this board.
- [ ] **Connector mated height** (DF40 1.5 mm vs 3.0 mm): sets what fits under the module.
- [ ] Keep or drop the ID EEPROM (U11): no longer a HAT; optional as carrier ID.

## Power

- [ ] 5 V rail for the CM: size for CM5 worst case (plan ≥ 5 A at 5 V incl. downstream USB).
      Check module input current and allowed ripple/transient specs (**verify** both modules).
- [ ] Input protection: reverse polarity, TVS, inrush limit / eFuse on the CM 5 V feed.
- [ ] Re-budget the board rails: U7 (TMI7003C) currently runs from +5 V; check total load with
      U2 (~0.3 A @ 3V3), STM32, FPGA, and confirm U7 input/current limits.
- [ ] Don't load the CM's own 3.3 V / 1.8 V outputs with board circuitry beyond their rating
      (**verify** limits). Keep the board's own rails.
- [ ] Power sequencing / control: GLOBAL_EN, RUN_PG (CM4), PWR_BUT (CM5): decide whether the
      STM32 can hold the CM off or reset it; add a power button if needed (**verify** pin names).
- [ ] Remove the J5 ↔ Pi back-feed concern (single supply now) and update J5's protection.

## CM connectors and GPIO interface

- [ ] Place 2× Hirose DF40C-100DS (100-pin, 0.4 mm). Use the official CM4 footprint/pinout
      and check the CM5 compatibility table (**verify**).
- [ ] **GPIO_VREF**: tie to the CM's 3.3 V output so GPIO bank 0 runs at 3.3 V (matches the
      STM32). On CM4 this pin selects 1.8 / 3.3 V (**verify** CM5 behaviour).
- [ ] Re-route all existing Pi nets by BCM GPIO number (same on CM4/CM5):
      - HOST_TX / HOST_RX → GPIO15 RXD / GPIO14 TXD
      - HOST_SCK / HOST_HIPO / HOST_HOPI / HOST_nCS → GPIO11 / GPIO9 / GPIO10 / GPIO8 (CE0)
      - HOST_ALM / HOST_ALMn → GPIO16 / GPIO17
      - ID_EEP_SDA / ID_EEP_SCL → ID_SD / ID_SC (GPIO0/1)
- [ ] Fix the open net-name mismatch first: `HOST_CS` (U15 PB12) vs `HOST_nCS` (J4 pin 24).
- [ ] Optional: NRST and BOOT0 of the STM32 to two spare CM GPIOs (flash STM32 via its ROM
      bootloader over USART1 or SPI2 from the CM).
- [ ] Optional: STM32 USB to a CM USB2 port instead of / in addition to UART + SPI.
- [ ] Leave unused high-speed interfaces (PCIe, HDMI, MIPI, USB3) unconnected per datasheet
      recommendations (**verify** any required terminations/straps).

## Boot / provisioning

- [ ] nRPIBOOT: jumper or button + test point (forces USB boot for eMMC flashing).
- [ ] Route the CM's USB2 port used for rpiboot (CM4: USB2 OTG; CM5: **verify** which port)
      to a connector or test pads. J5 is the obvious candidate if it's not used for the STM32.
- [ ] CM4 EEPROM_nWP: decide on bootloader-EEPROM write protect (**verify** CM5 equivalent).
- [ ] Console: the CM's primary UART (GPIO14/15) is now the STM32 link → disable the Linux
      serial console there, or move the console to another UART / test pads.

## Ethernet over FPC

- [ ] Use the CM's integrated GbE PHY. Route the 4 MDI pairs (TRD0–3) + 2 LED pins to the FPC.
- [ ] Recommended: **magnetics at the far end** (MagJack on the panel board); the FPC then
      carries PHY-side, ground-referenced pairs. Magnetics on this board would put the 1500 Vrms
      isolation boundary on the FPC, which conflicts with a ground-referenced flex stackup.
- [ ] Center-tap handling per the CM4/CM5 IO-board designs (CM4: center taps to caps only,
      not to a supply, **verify** for both modules), Bob Smith termination at the jack.
- [ ] FPC: 100 Ω ±10 % differential pairs over a solid ground layer, ground pins between pairs
      (G-S-S-G), length-matched within each pair, as short as practical. Pin count roughly:
      8 MDI + 2 LED + 3V3 + several GND (≥ 16–20 pins).
- [ ] Get the FPC stackup and impedance from the flex vendor; include connector transitions
      in the budget.
- [ ] RJ45 shield → chassis, not directly to logic ground (RC/cap). ESD handled on the line
      side by the magnetics; optional low-C TVS on the PHY side.
- [ ] Check total MDI routing length / loss from PHY to jack against the CM layout guidance.
- [ ] No PoE unless explicitly added (would need PoE magnetics + PD controller).

## Mechanical / thermal

- [ ] Board outline and keep-outs for the 55 × 40 mm module, 4× M2.5 mounting standoffs.
- [ ] CM5 runs much hotter than CM4: heatsink/fan clearance; CM5 fan pins (**verify**).
- [ ] Keep the TDR front end (bridges, clip lines, U2, muxes) away from the CM and its
      switching supply; re-check noise coupling into the hold nodes.
- [ ] Wireless variants: antenna keep-out / U.FL access and enclosure.

## Clean-up

- [ ] Remove J4 (40-pin header) and its HAT-specific parts (U11 if dropped, R86/R87 if
      the CM side provides pull-ups, HAT+ stacking address strap R90/R91).
- [ ] Re-run ERC/connectivity after re-routing; regenerate the MCU pin table.
- [ ] Software: device-tree overlays for UART/SPI0/GPIO on CM4 and CM5 (CM5 GPIOs come from
      RP1; same BCM numbering, different drivers).

## CM4 vs CM5 caveats

- Mechanically and largely electrically compatible on the two DF40 connectors, but some
  CM4 pins were repurposed on CM5 (MIPI lanes ↔ USB3, power button, RTC battery, fan).
  This board doesn't need those interfaces; keep them unconnected so both modules work
  (**verify** in the CM5 datasheet's compatibility table).
- CM5 power and thermal budgets are substantially higher: size the input for CM5.
- CM5 RTC: optional VBAT backup cell (**verify** pin).
- Bring-up: test with both a CM4 and a CM5 before the next revision.
