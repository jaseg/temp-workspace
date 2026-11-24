# Strobe arms STRB_A / STRB_K: result (simulation only; validation RF-1, RF-2, RF-3/R204)

Scripts: `wave_gen.py` (strobe source: 2xTRF chain from `sim/strobe/chain.py`, 152 ps, scaled to the 4.30 V
AC-coupled step), `arms.py` (deck, cases, `results.json`), `plots.py` (`arms.png`), `amp.py` (copy of sim/sampler).
Deck = `sim/sampler/bridge.py` final circuit (24.9 R rails, 47 pF C0G, 1 k bias feeds, 10 R input leg, 2.2 pF
hold + TPH2501 Cin) plus: tap 1.37 mm from the driver, TL401 80 + 5 ps (RF-2), D401 clamp, CLIP 1.6 mm, balun as in
`sim/scope_sampler.py`, two 50 R arms at 5.925 ps/mm (16.747 mm = 99 ps), R204 as built (inline on A at 1.45 mm;
0.765 mm stub + 30 fF off K at 3.8 mm), rail tracks 2.565 mm, 0.15 pF per rail node, hold copper +268 fF (THEORY-6).
Aperture = 10-90 % of the held step response with a clean 35 ps input (1.2 R, no lead L); "system" = BUF802
model behind a 2 GHz first-order edge. Kick-out always with the BUF802 model. Eff > 100 % = held value
overshoots (memory coefficient 1 - eff < 0); the deconvolution handles either sign.
Not comparable 1:1 with sim/sampler (3 V ideal pulse there, 4.3 V chain pulse here).

## What the arms do
The bridge end is open while the diodes are off, the tap end is 25 R and then a short. The incident pulse
doubles at the open end, so the bridge is driven harder than in the lumped deck (peak 0.96 vs 0.82 V above the
-2 V bias): wider conduction, wider aperture, more efficiency and more amplitude margin. The residue returns
inverted after ~200 ps: a reverse swing to -3.6 V across the bridge (-2.5 V lumped), ~1.8 V per diode (BV 4 V).
The same-polarity return at ~+400 ps stays below conduction: **no second sampling instant** (step response flat
to within 0.3 % from -900 to -150 ps, `arms.png` left). The sampling instant moves +110 ps (trigger-delay offset).

## Numbers (bias +/-1 V unless stated; clean input)
| Case | aperture | eff | gain | ped | kick in / BUF / trig (mVpp) | rev. peak |
|---|---|---|---|---|---|---|
| lumped (old deck: no arms) | 100 ps | 90 % | 0.72 | +48 mV | 194 / 110 / 23 | -2.5 V |
| **as built** (99 ps arms, 85 ps stub, R204 as built) | **129 ps** | 124 % | 0.60 | +31 | 209 / 115 / 25 | -3.6 V |
| as built, stub 80 ps (RF-2 fixed) | 123 ps | 121 % | 0.60 | +31 | 208 / 111 / 25 | -3.7 V |
| R204 symmetric at the balun (RF-3) | 131 ps | 125 % | 0.61 | +32 | **180 / 100 / 22** | -3.7 V |
| R204 1 k at the bridge end | 127 ps | 122 % | 0.60 | +33 | 180 / 98 / 22 | -3.4 V |
| coupled pair (Zodd 50 R, Zeven 56 R) | 130 ps | 124 % | 0.61 | +33 | 183 / 101 / 22 | -3.7 V |
| + 200 R across the bridge end | 101 ps | 100 % | 0.54 | +39 | 186 / 96 / 22 | -2.6 V |
| + 100 R + 10 pF across the bridge end | 75 ps | 65 % | 0.44 | +55 | 164 / 84 / 20 | -2.2 V |
| 12 R / 25 R series per arm at the balun | 109 / 85 ps | 109 / 87 % | 0.56 / 0.50 | +38 / +47 | 200 / 185 in | -3.0 / -2.6 V |
| 4 mm arms, T401 moved, tap + stub stay (CLIP 14.35 mm) | 125 ps | 109 % | 0.70 | +45 | 207 / 116 / 25 | -3.4 V |
| 4 / 8 / 12 mm arms, T401 + tap + stub moved along | 108 / 107 / 116 ps | 105 / 114 / 120 % | 0.59 / 0.56 / 0.57 | +46 / +39 / +34 | ~195-216 in | -2.7 / -3.1 / -3.3 V |
| as built, bias +/-1.3 / +/-1.5 V | 105 / 88 ps | 109 / 95 % | 0.56 / 0.52 | +38 / +44 | 214 / 212 in | -4.5 / -5.0 V |
| as built, strobe -25 % / +10 % | 96 / 138 ps | 98 / 129 % | 0.53 / 0.62 | +33 | 175 / 214 in | -3.4 / -3.7 V |
| lumped, strobe -25 % | 53 ps | 50 % | 0.35 | +62 | 194 in | -2.4 V |
| **recommended**: as built + R204 sym + 80 ps stub + bias +/-1.3 V | **100 ps** | 105 % | 0.55 | +36 | **186 / 102 / 22** | -4.6 V |
| recommended, strobe -25 % / +10 % / bias +/-1.46 V | 56 / 112 / 85 ps | 60 / 115 / 93 % | 0.38 / 0.57 / 0.51 | +43 / +37 / +40 | 174 / 199 / 188 in | -4.3 / -4.6 / -5.0 V |
| 4 mm arms + T401/tap/stub at the bridge, 80 ps, +/-1.15 V | 79 ps | 90 % | 0.48 | +48 | 207 / 125 / 24 | -3.1 V |

System (BUF802 2 GHz): lumped 138 ps (eff 84 %); as built 198 ps (eff 120 %); as built +/-1.3 V 160 ps;
recommended 149 ps (eff 100 %, gain 0.50, ~2.3 GHz); 4 mm + tap at the bridge 135 ps (+/-1 V, eff 97 %) / 119 ps
(+/-1.15 V, eff 87 %).

## Findings
1. The 99 ps arms widen the aperture by 29 % at the nominal +/-1 V bias (system 138 -> 198 ps) because they
   over-drive the bridge, not because of re-strobing. The bias DAC is the knob: +/-1.3 V gives 100 ps clean /
   149 ps system at eff ~100 %. At equal efficiency the as-built arms cost ~7 % aperture (85 vs 79 ps) and
   ~10 % system rise time against a 4 mm layout.
2. Moving only T401 / R204 to C201 / C202 does nothing (125 ps): the resonator runs from the stub tap to the
   bridge, so the CLIP line takes over the length. A real fix moves T401 + tap + TL401 (13.5 mm) + D401 + C410.
3. A coupled 100 R pair behaves like the two 50 R lines (on 0.0994 mm prepreg the pair is only loosely coupled).
   Damping costs strobe energy: 200 R at the bridge end or 12-25 R at the balun only trades efficiency for
   aperture, the same trade the bias DAC makes for free.
4. R204 asymmetry (RF-3) adds 16 % to the kick-out (209 vs 180 mV at the bridge input, 25 vs 22 mV at the
   trigger end); pedestal unchanged within 1 mV. RF-2 (stub +5 ps) costs 6 ps of aperture.
5. Higher bias reduces amplitude margin: recommended setting at strobe -25 % drops to eff 60 % (as built at
   +/-1 V keeps 98 %). Bias must be set per board in calibration (target eff ~100 %), not fixed.

## Recommendation (geometry to build)
- **Keep T401 and the 16.75 mm uncoupled 50 R arms** (layout as built). The hold cluster (U201, C205, R207,
  R208, C208: 2.5-9.3 mm right of the bridge centre, U201.3 <= 2 mm from D202.3) sits between the bridge and
  T401, and the rails are 8.1 mm apart; the useful re-layout (T401 + tap + 13.5 mm stub + clamp within 4 mm)
  has no room in the block and buys ~10 % system rise time. Replace the schematic note "within 5 mm, coupled
  100 R pair" by "16.75 mm 50 R arms, equal +/-0.1 mm, sim/strobe_arms".
- **Rotate R204 so both pads sit inline in the arms at equal distance from T401** (or move it to C201 / C202).
- **Fix RF-2** (GND via at NT401 pad 1 end or stub -0.85 mm).
- **Nominal bias +/-1.3 V** (VBIAS_A -1.3 V, inside -0.50..-1.46 V; VBIAS_K +1.3 V), trimmed per board for eff
  ~100 %. Update gain / efficiency in theory and sampler notes: gain ~0.55 (system 0.50), eff ~100-105 %,
  pedestal ~+36 mV, reverse peak 4.6 V across the bridge (2.3 V per diode, BV 4 V min).

## Open
Balun as a lumped CM choke (DLW21SN real CM L ~0.15 uH, line length of the windings not modelled); chain pulse
amplitude unmeasured (aperture vs bias calibration covers it); falling-edge reverse pulse (+160 ns) not re-run.
