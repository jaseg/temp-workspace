# Price check, low-cost front end (21 Nov 2026)

Single-unit prices (qty 1; qty 5 where the minimum order is 5), USD.

## How the numbers were obtained

- **LCSC**: live product pages `https://www.lcsc.com/product-detail/Cxxxx.html`. The
  server-rendered HTML carries `productPriceList` and `stockNumber`, which a script read
  out. These are first-hand numbers. The C numbers came from web search. LCSC search and
  the `wmsc` API return 403 or render client-side, so LCSC could not be searched directly.
- **DigiKey, Mouser**: both sites block direct access (DigiKey 403, Mouser "access
  denied"). Their offers were read from the data embedded in Octopart search pages
  (`octopart.com/search?q=...`). Octopart takes these through the distributors' APIs, and
  the offers were timestamped 20 Nov 2026. These numbers are second-hand but recent.
- findchips (timeout) and oemsecrets (403) could not be reached. The JLCPCB parts API
  was not used.
- "n/o" means no offer from that distributor appeared on Octopart, or no LCSC listing
  was found. "0 stk" means listed but out of stock.

## Table

| Part (MPN) | LCSC (C#, stock) | DigiKey (stock) | Mouser (stock) | Lowest | Notes |
|---|---|---|---|---|---|
| BUF802IRGTR | 5.89 (C4370628, 72) | 8.62 (2.6k) | 8.65 (4.3k) | **5.89 LCSC** | 5.29 at 10. The earlier snapshot of 4.83 is no longer valid |
| BAT15-04W (BAT1504WH6327XTSA1) | 0.46 (C5380972, 1.5k) | 0.52 (H2110 type, 12k) | 0.52 (27.8k) | **0.46 LCSC** | 0.37 at 10, 0.32 at 30, 0.27 at 100 |
| BAT15-04R | 0.25 at 5 (C16685, **0 stk**) | E6327 obsolete per DK | 0.82 (E6152 type, 6.6k) | **0.82 Mouser** (in stock) | E6327 is obsolete. Use BAT15-04W (SOT-323) for the tap gates instead |
| BAT15-099 | n/o | n/o | 1.12 (E6327, 4.4k); 0.54 (E6433, 284) | **0.54 Mouser** | Single diode. Not needed if BAT15-04W is used |
| TLV3801DSGR | 5.21 (C3658765, 54) | 5.20 (7.1k) | 5.13 (2.0k) | **5.13 Mouser** | DSGT reel type is about 6.5 |
| TLV3601DBVR | 4.65 (C5213958, 3.1k) | DBVT 6.01 | DBVT 5.98 | **4.65 LCSC** | |
| TLV3604DCKR | 4.23 (C2916042, 170) | 7.01 (2.6k) | 6.96 (4.4k) | **4.23 LCSC** | |
| TRF37D73IDSGR | 1.50 (C2151367, 25) | 1.74 (3.4k) | 1.53 (7.3k) | **1.50 LCSC** / 1.53 Mouser | Mouser has the deep stock |
| TRF37A73IDSGR | not checked | 1.74 (3.2k) | 1.53 (726) | **1.53 Mouser** | |
| GVA-84+ | n/o | 3.35 (4.4k) | 2.99 (3.7k) | **2.99 Mouser** | Mini-Circuits web shop price not checked |
| COS3502SR (COSINE, dual) | 0.36 at 5 (C49304672, 3.7k) | n/o | n/o | **0.36 LCSC** | 0.18 per channel |
| MX7219T (Maxinmicro, single) | 0.40 at 5 (C20882980, 18k) | n/o | n/o | **0.40 LCSC** | |
| MX3502S (Maxinmicro, dual) | 0.33 at 5 (C19269867, 17.5k) | n/o | n/o | **0.33 LCSC** | New find, a TLV3502-class dual. Datasheet not read |
| TLV3502AIDR | 2.07 (C131165, 226) | 5.15 (1.4k) | 5.08 (2.6k) | **2.07 LCSC** | |
| TMUX136MRSER | 1.41 (C2673277, 224) | 1.22 (48k) | 1.25 (247) | **1.22 DigiKey** | |
| TS3USB221ARSER | not checked | 0.91 (16k) | 0.84 (26k) | **0.84 Mouser** | A USB 2.0 switch, about 1 GHz class (bandwidth not re-checked). It is not a >5 GHz part. The TMUX136 (6.1 GHz) stays |
| GW1NZ-LV1QN48C6/I5 | 6.68 (C5799569, 641) | n/o | n/o | **6.68 LCSC** | 5.64 at 10 |
| GW1N-LV1QN48C6/I5 | not found | n/o | 16.00 (103) | **16.00 Mouser** | |
| GW1N-LV4QN48C6/I5 | not found | n/o | 19.60 (3) | **19.60 Mouser** | |
| GW1NR-LV9QN88C6/I5 | not found | n/o | n/o | **unverified** | |
| GW1NSR-LV4CQN48P | 17.88 (C2908250, 440) | - | - | 17.88 LCSC | |
| LCMXO2-1200HC-4TG100C | 14.77 (C453479, 28) | - | - | 14.77 LCSC | The earlier snapshot of 2.55–3.47 was wrong |
| ICE40UP5K-SG48I | 12.75 (C2678152, 165) | n/o | 13.15 (54) | **12.75 LCSC** | The earlier figure of 6.58–8.07 is no longer valid |
| Si5351A-B-GT / -GTR | GT 3.07 (16 stk, via Octopart); GTR 1.26 (C5451727, **0 stk**) | GTR 2.46 (224) | n/o | **2.46 DigiKey** (in stock) | |
| MS5351M (Ruimeng) | 0.91 (C1509083, 212) | n/o | n/o | **0.91 LCSC** | Si5351-compatible clone, up to 200 MHz |
| 26 MHz TCXO ±0.5 ppm, 2016 | ECS-TXO-20CSMV-260 2.04 (C2594511, **0 stk**); KDS 1XXC26000MAA 0.88 (C160426, **0 stk**, stability unverified) | not checked | not checked | **unverified** | No in-stock part was confirmed |
| OPA140AIDBVR | 7.53 (C444867, **0 stk**) | 0 stk (restock May 2027, from opamps.md) | n/o | **out of stock** | |
| OPA197IDBVR | 0.75 (C221351, 71k) | 2.38 (804) | n/o | **0.75 LCSC** | |
| OPA810IDBVR | 3.07 (C2833513, 3.3k) | 3.85 (10.6k) | 3.85 (4.0k) | **3.07 LCSC** | |
| OPA356AIDBVR | 1.44 (C183100, 2.9k) | 2.46 (8.0k) | 2.46 (7.6k) | **1.44 LCSC** | |
| OPA4354AIPWR | not checked | 5.15 (606) | n/o | 5.15 DigiKey | |
| TPH2501-TR (3PEAK) | 0.43 at 5 (C126713, 6.9k) | - | - | 0.43 LCSC | Candidate for the hold amplifier (see opamps.md) |
| TPA1881-TR (3PEAK) | 2.62 (C2930535, 2.5k) | 2.11 (from opamps.md) | - | 2.11 DigiKey | |
| TPS7A2033PDBVR | Tech Public / MSKSemi clones 0.10–0.11 at 5 | 0.35 (9.2k) | 0.37 (23k) | **0.35 DigiKey** (TI part) | Other TPS7A20 voltages not checked |
| LP5907MFX-3.3 | clones 0.08–0.14 at 5 (HXY, Tech Public) | TI part n/o | TI part n/o | **unverified for the TI part** | |
| TPS7A3001DGNR (negative LDO) | not checked | n/o | n/o | **unverified**, possibly no stock | Alternative: TPS72301DBVR, DigiKey 4.01, Mouser 4.25 |
| LT3093EMSE | - | 8.05 | 6.75 (3.2k) | 6.75 Mouser | Too expensive for this budget |
| LM27761DSGR (inverting charge pump with LDO, −1.5 to −5 V, 250 mA) | 1.23 (C129351, 12.9k) | 1.84 (25k) | 1.75 (37k) | **1.23 LCSC** | Replaces the inverter and the negative LDO |
| LTC1983ES6-5 | - | 6.65 | 5.43 | 5.43 Mouser | |
| MCP4728A0T-E/UN | 2.67 (C627341, 200) | n/o | 2.50 (5.4k) | **2.50 Mouser** | 4-channel, 12-bit, I2C |
| DAC60504BRTET | - | 17.97 | 16.77 | 16.77 Mouser | Too expensive |
| HFD3 relay | HFD3/12-SR 1.74 (312); HFD3/24 1.88 (170); **HFD3/5 n/o** | n/o | n/o | 1.74 LCSC (12 V coil) | A 3 V or 5 V coil variant was not found in stock |
| G6K-2F-RF | -S DC5 14.14 | n/o | -S DC4.5 13.72 | 13.72 Mouser | Too expensive for this budget |
| SMA edge mount | LCSC generic **not checked** | TE CONSMA003.062-G 4.47 | 4.47 | 4.47 (branded) | Generic LCSC parts are typically under 1 (unverified) |
| 0402 C0G 0.47 pF / 2.2 pF | not checked | n/o | n/o | **unverified** | Typically under 0.01 at LCSC |
| 0402 thin-film resistors | not checked | n/o | n/o | **unverified** | |

## Rough front-end subtotal (key ICs, lowest in-stock prices, qty 1–16)

| Item | Cost |
|---|---|
| BUF802 | 5.89 |
| 2 × BAT15-04W (bridge) | 0.93 |
| 16 × BAT15-04W (tap gates, at the 10+ price) | 5.85 |
| TLV3801 | 5.13 |
| TMUX136 | 1.22 |
| TRF37D73 (trigger) and TRF37D73 + GVA-84+ (strobe) | 6.0 |
| 8 × COS3502 | 2.9 |
| GW1NZ-1 | 6.68 |
| MS5351M | 0.91 |
| OPA197 + OPA810 (or TPH2501) | 3.8 |
| MCP4728 | 2.50 |
| LM27761 + 2 LDOs | 2.0 |
| 2 relays | 3.5 |
| 3 SMA | 3–13 |
| **Total** | **about 50–60** |

Passives and the TCXO are not counted. That leaves about 20 of the 80 budget for them.

## Observations

- LCSC is now the cheapest source for most TI analog parts (BUF802, OPA810, OPA197,
  TLV3601, TLV3604, TLV3502), often by 30–60 %. Its stock is shallow, though: 72 BUF802,
  54 TLV3801, 25 TRF37D73.
- FPGA prices from earlier snapshots were wrong: the iCE40UP5K is 12.75, not about 7,
  and the MachXO2-1200 is 14.77, not about 3. The GW1NZ-1 at 6.68 is the only FPGA under
  10. A GW1N (non-Z) part with LVDS costs 16–20 at Mouser.
- The BAT15-04R E6327 is obsolete. The SOT-323 BAT15-04W is cheaper and in stock, so use
  it everywhere.
