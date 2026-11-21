# Switchable 50 Ω termination at VIN: parts and methods

Question: how can a 50 Ω shunt termination at VIN be switched in (50 Ω mode) and out
(1 MΩ mode)? The input is DC-coupled and bipolar, up to ±2.5 V in 1 MΩ mode. The
requirements are a match from DC to 2 GHz, a DC-accurate resistance, under about 1 pF
added in 1 MΩ mode, and a cost under about 4–5 USD.

Research was done on 2026-11-21: about 40 minutes of web and datasheet lookups and small
lumped-model calculations in Python. No circuit simulation was run.

**Status:** the design will **not** include a switchable termination. The user has
chosen an external feed-through terminator instead. These notes are kept for reference
only and do not propose changes to the design.

## Result in brief

- **The match is limited by the input capacitance, not by the switch.** The re-run
  input simulation gives a return loss of 9.8 dB at 1 GHz and 3.4 dB at 2 GHz, even
  with an ideal terminator at the connector. The cause is the roughly 2 pF at VIN.
  - **What a switch cannot do:** no termination switch can bring the return loss up to
    15 dB at 2 GHz.
  - **What it can do:** stay close to the ideal-terminator result without adding
    capacitance in 1 MΩ mode.
  - **Inductance is not the problem.** With 2 pF at VIN, 1–3 nH of contact inductance
    in series with the 50 Ω partly cancels the capacitance. In the lumped model, about
    2 nH is the flattest case.
  - **Capacitance is the problem.** Every 0.5 pF the switch adds at VIN costs about
    0.6 dB at 1 GHz and 1.3 dB at 2 GHz in 1 MΩ mode, with a 50 Ω source.
- **Ranking for this instrument:**
  1. **External feed-through terminator.** This is the user's choice: no BOM cost, the
     best DC accuracy, and nothing added in 1 MΩ mode.
  2. **Best on-board switch if one is ever wanted: TE/Axicom IM03 signal relay.** It
     costs 2.0–3.5 USD at LCSC (stock checked live) and has published RF data
     (900 MHz) and published capacitance limits. Use both poles, on the ground side of
     2 × 100 Ω.
  3. **Omron G6K-2F-RF-S or Hongfa HFD48 RF relay.** These have the best datasheet RF
     data, but cost 13–14 USD (G6K, LCSC), which is about 3× the budget. No HFD48 price
     was found anywhere.
  - Semiconductor options either fail the 1 MΩ-mode capacitance limit (analog switches
    and MOSFETs at the ground side: 36–68 pF) or cost 22–100 USD (the PE42020 true-DC
    SOI switch, ADGM100x/ADGM13xx/ADGM1121 MEMS).
- **Legend for every number below:**
  - **[DS]** quoted from a datasheet read in this session.
  - **[LCSC]** read live from `lcsc.com/product-detail/<C#>.html` on 2026-11-21.
  - **[prices.md]** taken from `docs/research/prices.md` (Octopart, 2026-11-20).
  - **[snip]** taken from a web-search snippet of a distributor or aggregator page. It
    is undated and second-hand: **unverified**.
  - **[est]** my own estimate or model: **unverified**.

## Method and access notes

- **LCSC.** Product pages were fetched with curl, and `productPriceList` / `stockNumber`
  were parsed from the HTML. The `wmsc` search API could not be used (the call was
  refused in this environment). C numbers came from web search and the LCSC RF-relay
  category page (`lcsc.com/category/532.html`, 352 items, read through WebFetch).
- **DigiKey, Mouser.** Direct access returned 403 or "access denied". Octopart now
  answers with a captcha (PX block) and findchips returns an empty page, so neither
  could be scraped this time.
  - DigiKey and Mouser numbers are therefore either from `prices.md` (Octopart, the day
    before) or from search snippets. **Snippet prices are unverified.**
- **Datasheets.** Downloaded and read with pdftotext or as page images, stored under
  `scratchpad/term/ds` and not executed. The datasheets read this way were:
  - Hongfa HFD48 (2022 Rev 3.00)
  - Omron G6K(U)-2F-RF(-S) (with the engineering-data curves)
  - TE/Axicom IM series 108-98001 Rev K
  - pSemi PE42020 DOC-23814-4
  - Fujitsu FTR-B3 (LCSC copy)
- **analog.com was unreachable** (503 / connection failure). ADI numbers are from
  snippets.

## Part A: RF and high-frequency signal relays

### A.1 Datasheet RF data

All values are in a 50 Ω system and are the vendor's through-path (series) numbers.

**Hongfa HFD48** [DS, HFD48 datasheet, p. 114 "High-frequency characteristics"]
- **RF performance:** 3 GHz rating. Insertion loss ≤ 0.6 dB, VSWR ≤ 1.4, isolation
  ≥ 18 dB between open contacts and ≥ 25 dB between contact sets.
- **Contacts:** 2 Form C, contact resistance ≤ 100 mΩ, Au-plated silver alloy, SMT
  only, MSL3.
- **Coil, single-side stable:** 200 mW for every coil voltage. Coil codes:
  - HFD48/3 (45 Ω)
  - HFD48/4.5 (101 Ω)
  - HFD48/5 (125 Ω)
- **Coil, latching (1 coil):** 140 mW, e.g. HFD48/3-L at 64.3 Ω.
- **Ordering code:** for example HFD48/5-SR.
- **Price:** none found. There is no LCSC, JLCPCB, DigiKey or Mouser listing, and two
  web searches returned no price. The datasheet figures (0.6 dB / 1.4 / 18 dB at 3 GHz)
  match Omron's G6K-2F-RF-T class exactly, so expect a price class near the G6K's
  [est].

**Omron G6K(U)-2F-RF and G6K(U)-2F-RF-S** [DS, Omron datasheet; RS copy 0900766b80b76be8]
- **Ratings ("1-GHz band"):** at 1 GHz, isolation ≥ 20 dB (same pole) and ≥ 30 dB
  (different poles), insertion loss ≤ 0.2 dB, VSWR ≤ 1.2.
- **Coil:** about 100 mW. Single-side stable G6K, latching G6KU, coils from 3 to 24 V.
- **Engineering-data curves** (page 3, average of 5–10 units, read from the graph,
  ±2 dB). For the plain G6K-2F-RF:

  | Frequency | Isolation | Insertion loss | Return loss | VSWR |
  |---|---|---|---|---|
  | 1 GHz | about 27 dB | about 0.1 dB | about 30 dB | — |
  | 2 GHz | about 23 dB | about 0.27 dB | about 24 dB | about 1.12 |

  For the -S: return loss about 34 dB at 1 GHz and about 30 dB at 2 GHz.
- **Note 3 of the datasheet:** "The high-frequency characteristics depend on the
  mounting board."

**Omron G6K(U)-2F-RF-T** ("3-GHz band") [snip of the Omron datasheet]
- At 3 GHz: isolation 18 / 25 dB, insertion loss ≤ 0.6 dB, VSWR ≤ 1.4.

**Omron G6K-2F-RF-V** [snip]
- 8 GHz part, priced at 68–75 USD (LCSC). Out of scope.

**TE/Axicom IM series** [DS, 108-98001 Rev K, p. 22 "High Frequency Data"]
- **Capacitance** (all IM types):
  - coil to contacts: max 2 pF
  - adjacent contact sets: max 2 pF
  - open contacts: max 1 pF
- **RF characteristics at 100 MHz / 900 MHz:**

  | Type | Isolation (dB) | Insertion loss (dB) | VSWR |
  |---|---|---|---|
  | IM / IM-D / IM-E | −37 / −18.8 | −0.03 / −0.33 | 1.06 / 1.49 |
  | IM-A / IM-B | −33 / −13.5 | −0.06 / −1.00 | 1.10 / 2.00 |
  | IMC | −35 / −13.3 | −0.04 / −0.40 | 1.04 / 1.33 |

- **There are no data above 900 MHz.** The brief's assumption of "RF data to 3 GHz"
  for the IM is **not** borne out by Rev K.
- **Coil:** IM03 is the 5 V version (140 mW, 178 Ω). Variants: IM03GR (SMD gull-wing),
  IM03JR (SMD J-leg), IM03TS (THT).

**TE/Axicom HF3** [snip of the TE datasheet]
- 50 Ω version at 100 MHz / 900 MHz / 3 GHz:

  | Parameter | 100 MHz | 900 MHz | 3 GHz |
  |---|---|---|---|
  | Isolation | about −80 dB | about −72 dB | about −45 dB |
  | Insertion loss | −0.03 dB | −0.12 dB | −0.35 dB |
  | VSWR | 1.05 | 1.15 | 1.20 |

- HF3 S version: −55 dB isolation at 3 GHz.
- 1 Form C only, 15 × 7.6 × 10.6 mm.
- **HF6:** 6 GHz (from the catalogue summary in the IM datasheet). Not priced.

**Panasonic RS (ARS)** [snip]
- 3 GHz, 1 Form C, 10 W carrying power.

**Panasonic RE (ARE)** [snip]
- 2.6 GHz, 1 Form C. Some types are marked discontinued on the Panasonic site.

**Panasonic RA (ARA)** [snip]
- 1 GHz, 2 Form C, VSWR ≤ 1.2, insertion loss ≤ 0.3 dB.

**Panasonic RJ (ARJ)** [snip]
- 5–8 GHz. Priced at about 116–149 per unit (Mouser catalogue, currency unclear).
  Out of scope.

**Panasonic GQ/AGQ, TQ, TX-S**
- No RF table was found. Panasonic's own comparison page uses a GQ as its example of a
  "regular relay" and shows the data only as images up to 1 GHz, in a 75 Ω system.
  Treat these relays as having no RF data.

**Fujitsu FTR-B3 / FTR-B4**
- **RF variant:** an "-RF" variant of the FTR-B3 exists, 1 GHz, isolation ≥ 30 dB,
  insertion loss ≤ 0.2 dB [snip]. No distributor listing was found.
- **Standard types:** curves to 1 GHz only [snip]. The current LCSC datasheet copy of
  the FTR-B3 has no HF section [DS].

**KEMET (NEC/Tokin) EA2/EB2/EC2/EE2/UB2/UC2/UD2**
- The datasheets have "Performance data" pages, but no RF table could be read.
- **No published RF data was verified.**

**Hongfa HFD4 / HFD3 / HFD31**
- No RF data was found. The HFD4 is a 10 × 6.5 mm telecom relay like the IM.

**RF reed relays**
- Coto 9800/9900 [snip]
  - The 9800 series is "up to 6 GHz".
  - The 9802 is discontinued; the 9814 is the suggested replacement.
  - The bandwidth figure is defined at −3 dB.
- Standex-Meder CRF05 [snip]
  - "7 GHz" rating. Curves go to 7 GHz, but no numbers could be read.
- Pickering 111RF [snip]
  - Rated to 2.5 GHz on Pickering's page and to 1.5 GHz in Farnell's listing.
- Pickering 113RF [snip]
  - Rated to 3 GHz, coaxial.

**Cheap SIP reed relays on LCSC**
- Example: Pan Chang SIP-1A05.
- No RF data. With 20 mm long reeds the loop is long: 5–10 nH and 1–2 pF to the coil
  [est].

**Teledyne (J412 and similar), TE MW coaxial**
- 89–215 USD at LCSC. Out of scope.

### A.2 Prices and stock (qty 1, USD)

| Part | LCSC [LCSC] (C#, stock) | DigiKey | Mouser | Notes |
|---|---|---|---|---|
| Omron G6K-2F-RF-S DC5 | 14.14 (C2750987, 433) | 14.14 [prices.md] | 13.72 (-S DC4.5) [prices.md] | Best-documented RF relay |
| Omron G6K-2F-RF DC5 | 14.33 (C19166144, 33) | n/f | n/f | |
| Omron G6K-2F-RF-T DC5 | 13.37 (C2750990, 1) | n/f | n/f | 3 GHz type |
| Omron G6K-2F-RF-T-TR03-DC5 | 14.25 (C5644852, 49) | n/f | n/f | |
| Omron G6KU-2F-RF-S DC5 (latching) | n/f | n/f | 21.97 [snip] | |
| Hongfa HFD48/x | no listing | no listing | no listing | No price found |
| TE IM03GR (SMD) | 3.52 (C2153100, 760) | about 4.77 (PB1061CT-ND) [snip] | 1.88–2.33, 655-IM03GR [snip] | RF data to 900 MHz |
| TE IM03JR (SMD J-leg) | 3.02 (C5163704, 253) | n/f | n/f | |
| TE IM03TS (THT) | 2.53 (C1560489, 419) | n/f | n/f | |
| TE 1-1462037-8 (IM, THT) | 2.04 (C5366572, 762) | n/f | n/f | |
| TE IM03CGR (IMC, SMD) | 7.16 (C5439567, 0) | n/f | n/f | IMC: VSWR 1.33 at 900 MHz |
| TE HF3 1-1462051-6 | 10.80 (C6063455, 4) | n/f | n/f | |
| TE HF3 1462051-2 (HF3 53, 5 V) | 24.21 (C5163980, 4) | n/f | n/f | HF3 53S 15.75 at Octopart [snip] |
| TE HF3 1462051-1 | 20.66 (C5163922, 0) | n/f | n/f | |
| Panasonic ARS14Y4H | 14.84 (C4402945, 3) | n/f | ARS14Y24 39.06 (AUD?) [snip] | |
| Panasonic ARA200A05 | 27.09 (C719202, 0) | n/f | n/f | ARA200A4HZ 13.85 (C6125040, 0) |
| Standex CRF05-1A / -1AS | CRF03-1A 23.90 (C19468844, 0) | 15.72 / 12.92 [snip] | n/f | |
| Pickering 111RF / 113RF | n/f | n/f | n/f | 15.40 / 14.90 at the Pickering web shop [snip] |
| pSemi PE42020A | 26.03 (C726157, 1) | -X, 1,484 in stock (CA) [snip] | n/f | Octopart 22.20 [snip] |
| Fujitsu FTR-B3GA003Z-B10 | 1.42 (C2961043, 3,560) | n/f | n/f | No RF data |
| Hongfa HFD4/3 THT, HFD4/3-SR | 1.85 (C119084, 9,551); 2.02 (C90259, 2,981) | n/f | n/f | No RF data |
| Hongfa HFD3/3 (current K1) | 1.55 (C340658, 0) | n/f | n/f | No RF data, out of stock |
| Pan Chang SIP-1A05 reed | 0.96 (C10496, 0) | n/f | n/f | No RF data |

"n/f" means not found with the access available here. It does not mean the part is not
stocked.

**Finding.** No relay with RF data above 1 GHz is on offer for less than about
10.8 USD (HF3 at LCSC, only 4 in stock). The cheapest relays with **any** published RF
data and capacitance limits are the IM (to 900 MHz), at 2.0–3.5 USD at LCSC and about
2.3 at Mouser [snip].

### A.3 Shunt-termination estimates for the best candidates [est]

**Model**
- Lumped: source 50 Ω, then VIN with Cin = 2 pF, then the termination branch
  (49.9 Ω + L, plus any off-state C). The scripts are in `scratchpad/tools/`.
- My lumped values with an ideal 50 Ω at VIN are 10.5 dB at 1 GHz and 5.5 dB at
  2 GHz. The project simulation, which includes the 6 mm line and the connector, gives
  9.8 / 3.4 dB. Use the differences between cases, not the absolute values.

**Return loss in 50 Ω mode against series inductance**

| L in the 50 Ω branch | 0.5 GHz | 1 GHz | 2 GHz | VIN gain vs ideal 50 Ω without Cin, at 1 / 2 GHz |
|---|---|---|---|---|
| 0 (ideal R) | 16.2 dB | 10.5 dB | 5.5 dB | −0.41 / −1.45 dB |
| 1 nH | 18.1 | 12.2 | 6.6 | −0.20 / −0.80 |
| 2 nH | 20.4 | 14.0 | 7.1 | +0.09 / +0.04 |
| 3 nH | 23.2 | 15.4 | 6.5 | +0.45 / +0.86 |
| 4 nH | 26.0 | 15.5 | 5.3 | +0.85 / +1.53 |
| Ideal R plus 1 pF more at VIN | 12.8 | 7.4 | 3.3 | — |

The same L without the 2 pF gives 24.1 / 18.1 / 12.3 dB (2 nH) and 18.1 / 12.3 / 7.0 dB
(4 nH).

**Estimated parasitics per candidate**

- **IM, one pole.** The through-path VSWR is 1.49 at 900 MHz [DS]. Treated as a series
  L between two 50 Ω ports, that gives |Γ| = 0.197, so ωL ≈ 20 Ω and L ≈ 3.5 nH. This
  includes the pins and the test fixture [est].
  - Both poles in parallel: about 2–2.3 nH (mutual coupling assumed k ≈ 0.2) [est].
  - This is the "4 nH per pole, 2 nH paralleled" value the input simulation already
    assumed. From the table, about 14 dB at 1 GHz and about 7 dB at 2 GHz in the
    lumped model, about 0.1 dB flat.
  - **Off-state capacitance** is the open question. The datasheet maxima are 2 pF coil
    to contacts and 1 pF across the open contacts, per relay.
    - From the 900 MHz isolation (−18.8 dB) the open-contact capacitance is about
      0.2 pF [est].
    - The contact-to-coil part (coil at AC ground) is not separated out in the data.
      With both poles floating behind 2 × 100 Ω it could be 0.5–2 pF [est].
- **G6K-2F-RF(-S), hot side** (VIN → COM → NO → 49.9 Ω → GND). The relay path is a
  near-50 Ω line, so the termination looks like the through measurement: about 24 dB
  return loss at 2 GHz without Cin [DS curve].
  - In the off state, VIN carries the COM stub. Its electrical length is about
    20–30 ps, which gives about 0.4–0.6 pF, plus less than 0.1 pF across the open
    contact (from 27 dB isolation at 1 GHz) [est].
  - **Ground side** (49.9 Ω → COM → NO → GND): the relay's 50 Ω line ends in a short,
    so it behaves like an inductance of about Z0·τ ≈ 1–1.5 nH [est]. That gives the
    same result as the IM with both poles.
  - The RF relay buys little here, because Cin dominates.
- **HFD48.** Same datasheet class as the G6K-RF-T; the same estimate applies [est].

**Conclusion for Part A.** Because the 2 pF dominates, an expensive RF relay gains only
about 1–2 dB of return loss over a well-laid-out IM with both poles. The deciding
parameter is the relay's off-state capacitance, which neither class specifies
usefully. It must be measured.

## Part B: other ways to switch a 50 Ω termination

### B.0 How much capacitance the 1 MΩ mode can tolerate [est]

**Analog switch on the ground side: 50 Ω + Coff across VIN**

Source 50 Ω, Cin 2 pF, Rin 1 MΩ. The table gives the change in VIN against no switch.

| Coff | 100 MHz | 500 MHz | 1 GHz | 2 GHz | \|Zin\| at 100 MHz |
|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 796 Ω |
| 0.3 pF | −0.01 | −0.14 | −0.43 | −0.85 | 692 Ω |
| 1 pF | −0.03 | −0.62 | −1.62 | −2.48 | 531 Ω |
| 5 pF | −0.38 | −3.65 | −4.68 | −3.69 | 230 Ω |
| 20 pF | −2.79 | −5.62 | −5.10 | −3.49 | 85 Ω |
| 50 pF | −5.03 | −5.75 | −5.05 | −3.41 | 57 Ω |

- **Large Coff behaves like a termination.** For Coff 5 / 20 / 50 pF the branch is
  plain 50 Ω above 640 / 160 / 64 MHz. With a 50 Ω source this is a shelf down to
  −6 dB, with its pole at 318 / 80 / 32 MHz.
- **The effect on probes is worse.** With a passive 10:1 probe the input becomes
  50 Ω-loaded at high frequency, and the probe's compensation no longer matches the
  input at high frequency.
- **So a ground-side switch needs Coff of about 0.3 pF or less.** That rules out every
  CMOS analog switch and power MOSFET.

**Placing the contact on the ground side versus the hot side**

| Added C | At VIN directly (1 / 2 GHz) | Behind 50 Ω (1 / 2 GHz) | −3 dB bandwidth (direct / behind; none: 1.59 GHz) |
|---|---|---|---|
| 0.5 pF | −0.64 / −1.29 dB | −0.76 / −1.41 dB | 1.28 / 1.24 GHz |
| 1 pF | −1.32 / −2.47 dB | −1.62 / −2.48 dB | 1.06 / 0.99 GHz |
| 2 pF | −2.67 / −4.53 dB | −3.04 / −3.40 dB | 0.80 / 0.70 GHz |

- With a 50 Ω source, putting the 50 Ω in front of a small capacitance does **not**
  help. It only helps above about 1/(2π·50·C), which for C under 1 pF is above 3 GHz.
- The real benefits of the ground side are different:
  - There is no stub from VIN to the contact in 50 Ω mode, because R sits at VIN.
  - Coil-to-contact coupling and noise couple through 50 Ω instead of directly into VIN.
- **The brief's hope for "capacitance hidden behind 50 Ω" is not met** for the
  sub-pF values that matter.

### B.1 Integrated RF switch ICs

**pSemi PE42020** (SOI CMOS, "True DC", SPDT) [DS, DOC-23814-4]
- **Range and signal:** 0 Hz to 8 GHz. ±10 V DC or AC peak on the RF ports at ±15 V
  supplies; ±7 V at ±11 V.
- **Supplies:** VDD +11 to +15 V and VSS −11 to −15 V are required, with a strict
  power-up sequence.
- **Losses and match:**
  - Insertion loss 0.60 dB at 0 Hz, which is a series resistance of about 7 Ω [est,
    computed]. 0.85 dB from 0 to 3 GHz.
  - Return loss 20 dB (active port), and **23 dB at the terminated port** from 0 to
    3 GHz.
  - THD −84 dBc.
- **Termination mode:** the LZ pin selects absorptive mode, in which the unselected
  port is terminated with an internal 50 Ω. A switchable 50 Ω termination with
  datasheet RF data is therefore built in: VIN goes to RF1, and selecting RF2 makes RF1
  a 50 Ω load.
- **Not specified:**
  - The accuracy and tempco of the internal 50 Ω.
  - The off-state capacitance at the port. Expect a few tenths of a pF to about 1 pF
    of pad and transistor capacitance [est].
- **Price:** 26.03 at LCSC (1 in stock), 22.20 at Octopart [snip].
- **Verdict:** this is the only IC found that really works at DC with ±2.5 V, but it is
  over budget by 5× and needs ±11 V rails.

**Other pSemi parts (PE4259, PE42520 and similar), Skyworks, Qorvo, MACOM, Mini-Circuits
GaAs/SOI parts, and cheap LCSC switch ICs** (generic Wi-Fi SOI clones)
- These are specified from 9 kHz–10 MHz upward and need DC-blocking capacitors when DC
  is on the RF ports [est; not checked part by part]. They cannot pass a bipolar DC
  signal.

**ADI ADG901/902/918/919** (CMOS, absorptive)
- Single 1.65–2.75 V supply. The ADI page says they pass "dc signals up to 0.5 V
  without dc blocking capacitor" [snip].
- The shunt legs are internally terminated with 50 Ω.
- **Rejected:** they cannot handle ±2.5 V.

**ADI ADGM1004** (MEMS SP4T)
- 0 Hz to 13 GHz; Ron 1.8 Ω typical, 2.9 Ω max [snip]; insertion loss 0.45 dB at
  2.5 GHz [snip].
- DC range −6 to +6 V on the switch [snip of the JP datasheet], so ±2.5 V is fine.
- The DigiKey note says Ron varies with part, cycling, settling, bias and temperature
  [snip], so expect about ±1 Ω of DC error [est].
- The open capacitance was not found. Off-state isolation at GHz suggests tens of fF
  [est].
- **Price:** 46.30 at 1k (ADI) [snip].

**ADI ADGM1304, ADGM1121** (MEMS)
- ADGM1304: 0 Hz to 14 GHz, Ron 1.6 Ω [snip], 93.04 at Farnell [snip].
- ADGM1121: DC to 18 GHz, 102.39 at DigiKey [snip].
- Both, like the ADGM1004: no hot switching, need a DC path on the RF pins, and are
  ESD-sensitive [est from the family notes].

**Menlo Micro MM5130 / MM5120 / MM5600** (MEMS)
- DC to 18 or 26 GHz, Ron 1.2 Ω typical, 3 Ω max (MM5130) [snip].
- Needs a DC path to ground on the RF pins; not for hot switching [snip].
- No price was found; it is certainly far above 5 USD [est].

### B.2 Analog switches and discrete transistors

**Low-Ron CMOS switches**
- ADG1401 [snip of DS]:
  - 1 Ω, ±5 to ±15 V.
  - CS(off) 36 pF and CD(off) 41 pF typical at VS = 0 V; 61 and 68 pF at 6 V.
  - −3 dB bandwidth 82–120 MHz.
- ADG1611 [snip]: 1 Ω, 42 MHz bandwidth.
- Rule of thumb: for 1 Ω parts, Ron·Coff ≈ 40–60 Ω·pF.
- **Ground side:** Coff of 36–68 pF means a 50 Ω input above about 60–100 MHz in
  1 MΩ mode (table B.0). **Rejected.**
- **Hot side:** 40 pF directly at VIN. **Rejected.**

**Low-capacitance precision switches** (TMUX6111 class, ADG1219/ADG1201)
- TMUX6111: Coff 2.2–2.8 pF [snip].
- Their Ron is high (tens to hundreds of Ω [est; TMUX6111 Ron was not verified]).
- That ruins the DC accuracy and adds series resistance. Coff of 2–3 pF also still
  fails B.0. **Rejected.**

**TS5A / TS3A / NX3L / FSA / MAX4644 and similar**
- 5 V single-supply parts with tens of pF Coff and 100–300 MHz bandwidth [est].
- Signals below ground need the switch's GND pin taken to −2.5 V, with level-shifted
  logic.
- **Rejected** for the same capacitance reason.

**Discrete low-Rds(on) MOSFET or back-to-back pair on the ground side**
- Coss and Crss run to tens or hundreds of pF [est]. Same failure as above.
- A back-to-back pair halves the capacitance, but a body diode still conducts when the
  drain swings ±2.5 V with the gate held at a fixed voltage. **Rejected.**

**Discrete pHEMT or RF JFET on the ground side** (not researched down to a part number)
- **Technology figure of merit:** Ron·Coff ≈ 0.25–0.4 Ω·pF for GaAs pHEMT and
  0.1–0.2 Ω·pF for RF-SOI [est, typical literature values]. A 3 Ω device would then
  show about 0.1 pF off.
- **Off state:** the gate needs about −(2.5 V + |Vp|), i.e. −4 to −5 V, which the
  −5 V rail can supply. The gate-drain voltage then reaches about 7 V at +2.5 V on the
  drain, which is close to breakdown for many low-noise pHEMTs [est].
- **On state:** the device carries only about 3/53 of the signal, so it stays linear.
- **DC accuracy:** a 3 Ω Ron with about 0.3 %/K drift [est] adds less than 0.1 Ω over
  30 K. The part-to-part spread would be calibrated out, or absorbed by using 47 Ω.
- **Verdict:** physically the most promising semiconductor route, but it is
  unvalidated and needs a part search plus a gate-leakage check (leakage at 1 MΩ
  matters).

**PhotoMOS** (AQY221N2S, G3VM-21UR10)
- Last resort, as stated in the brief; not repeated here.

### B.3 Mechanical and relay-free options

**0 Ω link or solder jumper at the termination resistor**
- About 0.5 nH, zero cost, ideal at DC.
- Not user-switchable; a factory or service option only.

**SMA feed-through terminator** (the user's choice)
- Termination at the connector, accurate to the terminator's tolerance. Nothing is
  added to the PCB.
- Return loss is set by Cin: 9.8 / 3.4 dB at 1 / 2 GHz (project simulation).
- The terminator's own return loss is far better than that and plays no part [est].
- The terminator needs to be rated for the input power.

**Slide or DIP switch**
- No RF data was found (not searched in depth).
- On a 2.54 mm pitch the loop is about 5–10 nH and the contact capacitance about
  0.5–1 pF [est]. Worse than the IM.

**Coaxial SMA SPDT switch**
- Excellent RF, but well above budget (tens of USD and up) [est].

### B.4 Architectural alternatives

**Always-terminated 50 Ω input plus a separate 1 MΩ input** (second connector)
- Best 50 Ω quality, and no switch at all in the 1 MΩ path.
- Needs a second connector and either its own buffer or a path selection behind the
  buffer, which is a relay in the HF path. Costs more than 5 USD (a second BUF802 is
  5.89) [LCSC, prices.md].

**Active termination** (the buffer or an op amp synthesises 50 Ω)
- Needs loop gain at 2 GHz, which no part in the BOM has.
- Not DC-accurate at high frequency. **Rejected.**

**Digital step attenuator as a termination**
- DSAs are 50 Ω absorptive, but are specified from about 9 kHz and need DC blocks
  [est; not verified per part]. **Rejected** for DC coupling.

**Bias-tee tricks**
- Nothing found that keeps DC accuracy with a bipolar DC-coupled signal.

**Both poles in parallel, or two relays**
- Halves the inductance (about −40 % with mutual coupling [est]).
- Doubles the off capacitance of the floating node.
- With Cin of about 2 pF, 2 nH is close to the flattest case (table A.3), so paralleling
  helps flatness, not return loss.

**Ground side versus hot side**
- See B.0. No capacitance benefit for sub-pF values; the benefits are no stub in 50 Ω
  mode and coil coupling through 50 Ω.

**Split resistor (2 × 100 Ω, one per pole) and compensation**
- The split resistor is the current scheme; it keeps each pole's current path short.
- **Compensation result** [est]: in the lumped model, the best worst-case return loss
  from DC to 2 GHz is **13.0 dB**. It needs L1 = 3.25 nH in series from the connector
  to VIN plus L2 = 3.25 nH in the termination branch, which forms a T-like section
  around the 2 pF.
  - Results at 0.5 / 1 / 2 GHz: 27.8 / 27.6 / 13.0 dB.
  - For comparison, a 2 nH branch alone gives 20.4 / 14.0 / 7.1 dB.
- **This is the only route to about 15 dB at 2 GHz.** It is not a switch property, and
  L1 also changes the 1 MΩ-mode response (LC peaking with a 50 Ω source). It is listed
  for reference only.

## Part C: ranking and recommendation (for reference)

**What any termination switch can and cannot do, given the roughly 2 pF**
- **Cannot:** no switch placed at VIN can bring the 50 Ω-mode return loss above the
  Cin limit, which is about 10 dB at 1 GHz and 3–6 dB at 2 GHz in the project
  simulation and the lumped model.
- **Can:**
  - Contact inductance of 1–3 nH can recover about 2–4 dB at 1 GHz and flatten the VIN
    response to about 0.1 dB at 2 GHz (with 2 nH).
  - The switch must not add capacitance: every 0.5 pF costs about 0.6 dB at 1 GHz and
    1.3 dB at 2 GHz in 1 MΩ mode, and about 1–2 dB of return loss in 50 Ω mode.
- **For 15 dB at 2 GHz:** the 2 pF must be compensated (B.4) or reduced.

**Ranking for this instrument**

1. **External SMA feed-through terminator** (chosen).
   - Cost: 0 on the BOM.
   - RF: 9.8 / 3.4 dB at 1 / 2 GHz (simulation).
   - DC accuracy: set by the terminator's tolerance.
   - 1 MΩ mode: no added capacitance.
   - Sourcing and risk: none on the board. The risk is the user forgetting it, and
     power handling.
2. **TE/Axicom IM03GR**, both poles, on the ground side of 2 × 100 Ω 0.1 % 0603.
   - Cost: 3.52 at LCSC (760 in stock), about 2.3 at Mouser [snip], about 4.8 at
     DigiKey [snip]. 2.04–2.53 for the THT IM03TS at LCSC.
   - RF: about 14 / 7 dB at 1 / 2 GHz in the lumped model [est]. The only data is to
     900 MHz [DS].
   - DC accuracy: under 0.2 Ω. Contacts are about 50–100 mΩ [est]; the resistors are
     0.1 %.
   - 1 MΩ mode: open contacts ≤ 1 pF and coil ≤ 2 pF per relay [DS]. The effective
     added capacitance is perhaps 0.3–1 pF [est]. **Must be measured.**
3. **Omron G6K-2F-RF-S DC5** on the hot side (VIN → COM → NO → 49.9 Ω).
   - Cost: 13.7–14.1 at all three distributors [LCSC, prices.md].
   - RF: return loss about 30 dB at 2 GHz as a relay [DS curve]; in the circuit, Cin
     limited (≈ ideal) [est].
   - 1 MΩ mode: about 0.4–0.6 pF stub [est].
   - The HFD48 would be an alternative if a price ever appears.

The semiconductor routes (PE42020 at 22–26 USD with ±11 V rails, MEMS at 46–100 USD)
are not competitive. A discrete pHEMT on the ground side is the only cheap
semiconductor idea left, and it is unproven.

**Concrete circuit for the on-board option (#2), for reference only**

```
VIN ──┬── R1 100R 0.1% 0603 ── K1 COM-A (pin 4) ; K1 NO-A ── GND via
      └── R2 100R 0.1% 0603 ── K1 COM-B (pin 9) ; K1 NO-B ── GND via
NC-A / NC-B: no connect (leave pads, no traces)
Coil: IM03GR 5 V, 178 Ω, 140 mW [DS]: VBUS(5V) ── coil ── 2N7002 (TERM_50) ; 1N4148W or BAT54 flyback
Footprint: TE IM SMD gull-wing (IM..GR), 10 x 6 mm body
```

- R1 and R2 sit **directly on the VIN trace** with no stub. Their far ends are under
  2 mm from the COM pins.
- The NO pins go to ground through at least 2 vias each, onto a solid ground directly
  under the relay.
- The coil-drive traces are routed away from VIN.
- The pin numbering follows the IM datasheet; check it against the drawing before
  layout.

**What to measure or simulate to confirm (any on-board switch)**

1. **S11 with a VNA, DC to 3 GHz, in both modes**, with the SMA de-embedded, or
   **TDR** to locate each discontinuity. Compare with the ideal-terminator board
   (9.8 / 3.4 dB).
2. **Off-state capacitance at VIN** in 1 MΩ mode:
   - An LCR meter at 1–10 MHz, with the relay fitted and then removed.
   - The relay alone: COM-to-coil and COM-to-NO, both poles.
   - The target increase is 0.5 pF or less.
3. **1 MΩ-mode step** from a 50 Ω pulser (≤ 50 ps edge) and from a 10:1 passive
   probe. Look for a shelf or extra overshoot against no relay.
4. **DC resistance** by 4-wire measurement at VIN in 50 Ω mode, across temperature and
   after a few thousand cycles. The target is ±0.2 Ω.
5. **Simulation:** add the relay as a 2-port, either from a measured S-parameter file
   or as the [est] L/C values above, to `design/lowcost/sim/input/input_stage.py`.
   Sweep the off-state capacitance 0.2–1.5 pF and the contact inductance 1–4 nH.

**Verified versus estimated**

- **Verified from datasheets read here:**
  - The HFD48, G6K-RF and IM RF and capacitance tables.
  - The G6K-RF curves.
  - The PE42020 table.
  - All LCSC prices and stock.
- **Second-hand (search snippets, unverified):**
  - All DigiKey and Mouser prices except those from `prices.md`.
  - The specifications for HF3, Panasonic, Coto, Standex, Pickering, ADGM, Menlo and
    ADG1401.
- **My estimates (unverified):**
  - Every inductance, stub capacitance and return-loss or response number marked
    [est], and all the lumped-model tables (scripts in
    `scratchpad/tools/rl.py`, `tf.py`, `side.py`, `opt.py`).
