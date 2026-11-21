# Input buffer: alternatives to the BUF802

Question: is there a cheaper or better 1 MΩ (switchable 50 Ω) input buffer for 2 GHz
than the BUF802, and is a fully differential input stage worth it? Budget for the whole
front end is 80 USD. Research done 2026-11-21, about 25 minutes, no simulation.

## Result

**Keep the BUF802** as the 1 MΩ buffer. No other integrated part reaches 2 GHz with
pA bias current, and it is now among the cheaper fast parts (4.83 at LCSC, 6.77 at
DigiKey). A fully differential amplifier cannot replace it: every FDA found has a
resistive input (tens to hundreds of ohms), so a differential stage only makes sense
*behind* the BUF802, in the trigger path. That option costs about 13–15 (LMH5401) and
is not recommended for the base build; leave it as a footprint option (see below).

## Requirements used for screening

- -3 dB bandwidth ≥ 2.5 GHz at the gain used (the buffer must not be the only limit; the
  divider and the sampler also roll off), i.e. rise time ≤ 140 ps.
- Input: 1 MΩ ∥ ~10 pF after the 5:1 divider → buffer bias current ≤ ~100 pA (1 nA
  through the 1.6 MΩ/422 kΩ divider is already 0.3 mV offset; µA is out of the question
  without a servo that fights it), input capacitance ≤ ~2 pF.
- Gain about 1 (the divider sets the scale); output into 10 Ω + the bridge, or 50 Ω.
- Noise not critical: sampler and ADC dominate (tens of µV rms).
- Price: a few dollars, stocked at LCSC/DigiKey/Mouser.

## Candidates

Prices: single unit, USD. "LCSC" and "DK" are from search snapshots of the
distributor pages (LCSC product pages load prices with JavaScript and could not be read
directly, and the LCSC search API was blocked by the CDN). Treat every price as
±20 % and check before ordering.

| Part | Type | BW at needed gain | Bias / Zin | Supply | Price | Verdict |
|---|---|---|---|---|---|---|
| **BUF802** (TI) | JFET buffer, G=1 | 3.1 GHz at 1 Vpp, 1.6 GHz at 2 Vpp | 25 pA max | ±4.5–±6.5 V, 34 mA | 4.83 LCSC C4370628 (180 in stock, snapshot); 6.77 DK | **Keep** |
| BUF602 (TI) | bipolar buffer | 1 GHz | 7 µA max | ±1.4–±6.3 V | ~2–3 (unverified) | Too slow, bias too high |
| OPA818 (TI) | JFET op amp, decompensated G≥7 | 765 MHz at G=7 (GBW 2.7 GHz) | 4 pA, 1.9 pF | 6–13 V | 12.21 LCSC (no stock), ~12 EUR DK | Too slow; gain 7 wrong for this point |
| OPA859 (TI) | FET op amp | ~0.9 GHz G=1 class (from memory) | pA | 3.3–5 V | ~3–4 (unverified) | Too slow |
| ADA4817-1 (ADI) | FET op amp | 1.05 GHz G=1 (from memory) | pA | 5–10 V | ~5–7 (unverified) | Too slow |
| LTC6268-10 (ADI) | CMOS op amp, G≥10 | 4 GHz GBW → ~350 MHz at G=10 | fA | 3–5 V | ~6–8 (unverified) | Too slow |
| LMH6559 (TI) | bipolar buffer | 1.75 GHz small signal | µA (bipolar) | 3–10 V | 2.73–4.45 LCSC | Bias too high; DK lists it as no longer manufactured |
| TPH2861 (3PEAK) | bipolar op amp, G≥7 | GBW 8 GHz → ~1 GHz at G=7 | bipolar (µA class, number not found) | 5 V, 19 mA | not found on LCSC | Not a 1 MΩ buffer; possible trigger gain stage |
| Chinese buffers on LCSC | – | none found above ~1 GHz with FET input | – | – | – | Nothing usable found |
| Discrete JFET/pHEMT follower + BJT follower | e.g. BF862 or LSBF862 + BFR92/BFR380 | > 2 GHz is possible (old Tek FET probes), not proven here | pA–nA (JFET); gate leak (pHEMT) | ±5 V | ~1–2 | Cheaper by ~3, but needs its own DC servo, protection, careful matching; BF862 obsolete (LSBF862 replaces it); Ciss ~10 pF loads the divider. Not worth the risk for 3 USD |

### Fully differential amplifiers (for a differential stage behind the buffer)

| Part | BW | Gain / input | Supply, current | Price | Notes |
|---|---|---|---|---|---|
| LMH5401 (TI) | GBW 8 GHz, usable DC–2 GHz at 12 dB | resistive input, SE→diff capable; 1.25 nV/√Hz | 3.3–5 V, 55 mA (275 mW) | 13.0 Arrow / 13.1 Octopart; ~14.60 LCSC C2057542 (10 in stock, snapshot) | Best fit if a differential stage is wanted |
| LMH3401 (TI) | 7 GHz | fixed 16 dB, 50 Ω SE input → diff | 3.3–5 V, 55 mA | ~13–15 DK (250-pc reel price 15.11), Octopart 14.49 | 16 dB fixed; 50 Ω input loads the BUF802 |
| LMH6554 (TI) | 2.8 GHz at G=1 | resistive | 5 V class | 8.89–10.33 LCSC C701927 | Cheapest FDA ≥ 2 GHz found |
| LMH6552 (TI) | 1.5 GHz at G=1 | resistive | 5–12 V | not checked | Too slow for 2 GHz |
| THS4541 (TI) | 620 MHz G=1, 500 MHz G=2 | resistive | 2.7–5.4 V, 10 mA | not checked (~3–4) | Too slow; ADC-driver class |
| ADA4927, ADA4960, LTC6409 (ADI) | ~2.3 GHz, ~5 GHz, ~10 GHz GBW (from memory) | resistive | 5 V | ~8–20 (unverified) | Same role as LMH5401, no price advantage found |
| Chinese FDAs (3PEAK, SGMICRO, Runic) | none found ≥ 1 GHz | – | – | – | 3PEAK TPH25xx is 250 MHz single-ended |

Key point: all FDAs present a resistive input set by their gain network. None can be
the 1 MΩ input. A "fully differential input stage" would therefore be either
(a) BUF802 → FDA, or (b) a discrete differential FET pair at the input, which is the
discrete-follower risk doubled and gains nothing for a single-ended probe.

## What a differential stage would buy

Where it would sit: BUF802 output → resistive pick-off (the trigger branch already has
one) → LMH5401 SE→diff at 12 dB → TLV3801 differential inputs (via the TMUX136).

- **Trigger sensitivity.** The TLV3801 already has differential inputs; today one side
  gets the signal and the other a DAC threshold. A DC-coupled 4× (12 dB) gain stage in
  front would lower the data-trigger minimum from about 200 mV to about 50–70 mV at the
  probe point (estimate, not simulated; limited by noise and threshold-DAC resolution
  then). The TRF37D73 cannot do this because it is AC coupled; the FDA is DC coupled, so
  trigger level still works.
- **Edge recovery.** Larger, symmetric drive at the comparator cuts overdrive
  dispersion (TLV3801: about 5 ps at ±19 mV). The delay-line taps still see the
  comparator output, so the tap snapshots do not improve directly.
- **Main signal path.** No gain: the bridge is driven single-ended from the BUF802 and
  a differential sampler would need two bridges, two hold amplifiers and a second ADC
  channel; diff→SE conversion afterwards (balun or op amp) would add loss or bandwidth
  limit. Not worth it.

Cost of the option: about 13–15 for the LMH5401 plus ~0.5 passives, plus a 5 V rail
at 55 mA (0.3 W, on top of the BUF802's 0.35 W). That is ~18 % of the 80 USD budget for
a 3–4× trigger-sensitivity gain that the external clock input already covers for small
signals. LMH6554 (~9–10) is the cheaper fallback with less gain-bandwidth.

Recommendation: do not fit in the base build. If board space allows, place an
LMH5401 footprint in the trigger branch with 0 Ω bypass links, so it can be populated
if 200 mV proves too high in practice.

## 50 Ω mode

None of the buffers above provides 50 Ω. Switchable 50 Ω remains a termination
switched at the connector (RF relay or a 50 Ω resistor through a low-capacitance
switch), with the 5:1 divider bypassed or left in. Not researched further here.

## Unverified points

- LCSC prices are search-engine snapshots (BUF802IRGTR 4.83, LMH5401 ~14.60,
  LMH6554 8.89–10.33); live pages not readable (JavaScript; LCSC API blocked).
- Mouser not checked for any part.
- OPA859, ADA4817, LTC6268-10, ADA4927, ADA4960, LTC6409 bandwidths and all their
  prices are from memory.
- TPH2861 input bias current and LCSC availability not found.
- No Chinese FET-input buffer ≥ 1 GHz or FDA ≥ 1 GHz found; LCSC parametric search was
  not reachable, so this is "not found", not "does not exist".
- Trigger sensitivity gain with the LMH5401 (200 → 50–70 mV) is an estimate, not simulated.

## Sources

- TI product pages: ti.com/product/BUF802, LMH5401, LMH3401, OPA818, THS4541, BUF602
  (fetched 2026-11-21).
- LCSC: C4370628 (BUF802IRGTR), C2057542 (LMH5401IRMST), C701927 (LMH6554LEE),
  C2057373/C2877649 (LMH6559), OPA818IDRGT datasheet listing C2859543.
- DigiKey BUF802IRGTR 15857423 (6.77, 1907 in stock per snapshot); DigiKey LMH3401IRMST
  4988167; Octopart/Arrow for LMH5401.
- 3PEAK TPH2861 datasheet Rev. A.4 (orwintech.com mirror).
