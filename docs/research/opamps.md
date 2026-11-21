# Auxiliary op amps: research notes

November 2026. Single-unit prices (USD) from LCSC product pages (lcsc.com/product-image/Cxxxx.html,
which render prices server-side) and DigiKey product/search pages. Mouser was not checked.
LCSC search and API endpoints render client-side and could not be used; the C-numbers were
found through web search. Datasheet numbers were read from the PDFs (pdftotext) unless
marked "unverified".

## Roles

1. **DC servo / low-frequency path of the BUF802 composite buffer.** At least +/-5 V supply,
   pA bias (1 MOhm+ networks), low offset and drift, unity-gain stable, roughly 10 MHz GBW so
   that the crossover flatness matches the OPA197/OPA140 design (summary: OPA197 10 MHz,
   OPA140 11 MHz).
2. **Hold amplifier after the BAT15-04W bridge.** Reads a 2.2 pF hold cap: pA bias, Cin below
   about 3 pF, gain 2-5, settles to 10 bits in 100-300 ns, +/-2.5 V supply is enough.
3. **General: bias, DAC buffer, ADC driver** (STM32G474 12-bit ADC at up to 4 Msps).

## Reference parts (western)

| Part | Price, lowest source | Key specs (datasheet / distributor) |
|---|---|---|
| OPA197IDBVR | **0.75 LCSC C221351** (71k stock); DigiKey 2.38 | 36 V, 10 MHz, CMOS RRIO, Ib 5 pA typ / 20 pA max, drift 2.5 uV/C max, Vos 100 uV max (TI page) |
| OPA140AIDBVR | DigiKey 4.42 (0 stock, restock May 2027); LCSC 7.53 (0 stock) | 36 V JFET, 11 MHz, Ib 0.5 pA typ. Supply problem right now |
| OPA810IDBVR | LCSC 3.07 C2833513 (3.3k stock) | 27 V, 70 MHz-class JFET-ish CMOS; Ib ~2 pA (unverified here) |
| OPA356AIDBVR | LCSC 1.44 C183100 (2.9k stock) | 5.5 V, 200 MHz GBW, 450 MHz UGB, Ib 3 pA typ / 50 pA max (TI page) |

## Role 1 candidates: DC servo

**TPA1881-TR (3PEAK), LCSC C2930535, 2.62 LCSC / 2.11 DigiKey (2.6k stock both).**
Datasheet (3PEAK "36V, 12MHz, Zero Drift Op Amps"): 4.5-36 V, Vos +/-15 uV max,
drift 0.05 typ / 0.15 uV/C max, Ib 10 pA typ, Cin 5 pF diff, GBW 12 MHz, SR 12 V/us,
PM 60 deg, en 6 nV/rtHz flat to 10 kHz, in 200 fA/rtHz at 10 kHz. Rail-to-rail.
Concern: chopper. The chopping frequency and ripple/glitch spectrum are not in the extracted
text; in a composite loop the residual chopper ripple sits right in the band where the
servo and BUF802 paths cross over. 200 fA/rtHz into 1 MOhm is 0.2 uV/rtHz, much larger than
the 6 nV voltage noise; a CMOS non-chopper part is much quieter here. Also 3x the OPA197 price.

**TP2271-TR (3PEAK, SOT-23-5) / TP2272-SO1R (dual, SOP-8, LCSC C39487549, 0.50 at 5+, 4k
stock).** Datasheet Rev D.1 (chipdip copy): 2.7-36 V, GBW 7 MHz, SR 20 V/us, Vos 1.0 mV max,
drift 2 uV/C typ, Ib 3 pA typ (250 pA at 85 C), en 19 nV/rtHz at 1 kHz, unity-gain stable,
EMI hardened, RRO, input to -0.3 V below V-. TP2271 single: DigiKey lists it non-stock
(0.285 at 3000-reel, 9-week lead); no LCSC listing found. TP2272-SR (C95871) is out of stock
at LCSC. So the in-stock form is the dual TP2272-SO1R; the second half can serve as a bias
buffer (role 3). Slower than OPA197 (7 vs 10 MHz): the crossover must be re-trimmed anyway.
Offset (1 mV) is calibrated out by the offset DAC; drift (2 uV/C typ) is fine for a scope.

**SGM8291 (SGMICRO).** Datasheet: 4.5-36 V, Vos 1.5 mV max, drift 3 uV/C, Ib 20 pA typ,
but GBW only 1.4 MHz and SR 7 V/us. Too slow for the composite loop crossover. Rejected.

Not found: Gainsil, RunIC, COSINE, Linearin, Corebai or HGSEMI 36 V CMOS parts with pA bias
and ~10 MHz GBW (searches returned nothing usable in the time available; their catalogs are
mostly 5.5 V CMOS or bipolar 36 V clones). SGM8261 is bipolar (nA bias). 3PEAK TP6001
(LCSC C248581) appeared in results but was not checked.

**Role 1 verdict: keep the OPA197 (0.75 at LCSC, in stock).** It is now cheaper at LCSC
than any Chinese alternative with comparable bandwidth. Second source: TP2272-SO1R
(0.50, dual) if the 7 MHz GBW is acceptable after re-trimming. TPA1881 only if offset drift
ever matters more than noise (chopper ripple unknown).

## Role 2 candidates: hold amplifier

Settling estimate for a non-inverting gain G with GBW f_GBW: closed-loop pole at
f_GBW/G, tau = G/(2 pi f_GBW). 10 bits needs ln(2^10) = 6.9 tau plus any slew time.

**TPH2501-TR (3PEAK, SOT-23-5), LCSC C126713, 0.43 at 5+ (6.9k stock); DigiKey 0.91
(2.0k stock).** Datasheet (3PEAK, chipdip copy, pdftotext): 2.5-5.5 V (+/-1.25 to
+/-2.75 V), UGB 250 MHz, GBW 120 MHz (G=+10), SR 180 V/us, settling 25 ns to 0.1 % and
40 ns to 0.01 % (G=+1, 2 V step), Vos +/-500 uV max, drift 1 typ / 2 uV/C max,
**Ib 0.3 pA typ / 3 pA max at 27 C**, 150 pA at 85 C, 300 pA at 125 C,
**Cin 2.7 pF differential, 1 pF common mode**, en 6.5 nV/rtHz at 1 MHz,
in 50 fA/rtHz, RRIO, unity-gain stable, > 100 mA output. CMRR 65 dB min / 85 typ.
At G = 2.2: pole about 55 MHz, tau 2.9 ns, 10-bit settling about 20 ns plus about 10 ns slew
for a 2 V step. Far inside the 100-300 ns window (the OPA810 needed most of a 100 ns
strobe period). Droop: 3 pA / 2.2 pF = 1.4 uV/us at 27 C; 150 pA at 85 C gives 68 uV/us,
still below 1 LSB of 1 V/1024 over 10 us. The 1 pF CM input capacitance adds to the 2.2 pF
hold cap (in the non-inverting configuration the differential Cin is bootstrapped);
include about 1 pF plus pad in the sampler gain calculation.
Dual TPH2502-SR (C118223, 0.58) and quad TPH2504-TR (C126708, 1.00) exist.

**SGM8051XN5/TR (SGMICRO, SOT-23-5).** Datasheet (sg-micro.com, June 2017 rev): 2.5-5.5 V,
-3 dB BW 250 MHz feature / 180 MHz table (G=+1, 150 Ohm load), GBW 90 MHz (G=+10),
SR 93/-118 V/us, settling 58 ns to 0.1 % (G=+2, 2 V step), Vos 2 typ / 8 mV max,
drift 4.4 uV/C, Ib 6 pA typ (no max), RRO only. Cin not given in the extracted text.
Price: sg-micro.com resale 1.14 (1-24); no LCSC listing found (unverified). Slower to
settle and worse offset than the TPH2501; second source only.

**OPA356 (TI), LCSC C183100, 1.44.** 200 MHz GBW, Ib 3 pA typ / 50 pA max, 5.5 V. The
western reference; 3.3x the TPH2501 price.

**Role 2 verdict: TPH2501-TR.** Faster, lower bias, specified Cin, 0.43 at LCSC. Fall back to
OPA356 or SGM8051.

## Role 3 candidates: general bias / DAC buffer / ADC driver

STM32G474 ADC: 12-bit, up to 4 Msps; the sample-and-hold capacitor (about 5 pF, from ST's
datasheet, unverified here) must be recharged within a few ADC clocks, so the driver needs
tens of MHz and a small RC (e.g. 33-50 Ohm + 100-470 pF) at the pin.

| Use | Part | Price | Notes |
|---|---|---|---|
| ADC driver (2 ch) | TPH2502-SR, LCSC C118223 | 0.58 (10k stock) | Same die as the hold amp; 120 MHz GBW; one part can do hold amp + ADC driver if the hold amp output already drives the ADC directly |
| DAC / bias buffers, 5 V rail | TP1541A-TR, LCSC C99007 | 0.38 at 5+ (1.6k stock) | 1.3 MHz class, Ib 1 pA typ, Vos 400 uV max (from search, datasheet not re-read); dual TP1542A-SR (C99005) is out of stock at LCSC |
| Bias buffers on +/-5 V or wider | TP2272-SO1R, LCSC C39487549 | 0.50 at 5+ (4k stock) | 36 V, 7 MHz, 3 pA; second half of the servo dual |
| Cheap fallback | OPA197 | 0.75 | Covers anything up to 36 V |

## Suggested allocation

- Servo: OPA197 (0.75), or TP2272-SO1R (0.50) with its second channel as a +/-5 V bias buffer.
- Hold amp: TPH2501-TR (0.43). If the hold amp output can drive the STM32G474 ADC pin through
  an RC, no separate driver is needed.
- Bias/DAC buffers: TP2272-SO1R second channel, TP1541A, or a TPH2504 quad if several fast
  buffers are needed (bridge bias, comparator thresholds).
- Total for this group: roughly 1.5-2.5 USD.

## Unverified points

- TPH2501 settling at G = 2-5 with a 2.2 pF source impedance: estimate only, not simulated;
  no SPICE model checked (3PEAK publishes some models; availability not checked).
- TPA1881 chopping frequency and ripple: not found in the extracted text.
- SGM8051 LCSC availability and price; Cin.
- OPA810 Ib figure (not re-read in this pass).
- TP1541A Vos/Ib numbers from search snippets, not from the PDF.
- STM32G474 ADC sampling capacitance (about 5 pF) not re-read.
- Mouser prices not checked; DigiKey checked only for OPA197, OPA140, TPH2501, TPA1881, TP2271.
- Chinese vendors other than 3PEAK and SGMICRO: nothing suitable found, but the search was
  brief and their own selection tables were not browsed.

## Sources

- LCSC: C221351 (OPA197), C126713 (TPH2501), C118223 (TPH2502), C126708 (TPH2504),
  C2930535 (TPA1881), C39487549 (TP2272-SO1R), C95871 (TP2272-SR), C99007 (TP1541A),
  C99005 (TP1542A), C183100 (OPA356), C2833513 (OPA810), C444867 (OPA140):
  https://www.lcsc.com/product-image/Cxxxx.html
- DigiKey: TPH2501-TR 22228511, TPA1881-TR 22228749, keyword searches OPA197IDBVR,
  OPA140AIDBVR, TP2271-TR.
- Datasheets: TPH2501 (static.chipdip.ru/lib/986/DOC012986131.pdf), TP2271 Rev D.1
  (static.chipdip.ru/lib/178/DOC014178500.pdf), TPA1881 (atta.szlcsc.com ...F44ECE59...pdf),
  SGM8051 and SGM8291 (sg-micro.com assets PDFs).
