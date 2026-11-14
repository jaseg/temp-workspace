# Claude Code break-even: one work hour and one PCBA order

*Decision aid, 2026-11-14. Claude Opus 5.5 in Claude Code at API list prices, inference only (no training).*
- **Where the numbers come from:** the script in Appendix C, `claude-breakeven.py`; its output is in Appendix D.
- **How to read the values:** "central" is the Monte Carlo median; "low" and "high" are the 5th and 95th percentiles.
- **Tags:** [S#] are sources in section 5; ASSUMPTION marks inputs no source states.

**Two AI estimates.** Anthropic discloses no energy, emissions or water figures [S1, S2], so the AI footprint is estimated in two independent ways:
- **Top-down** converts Anthropic's compute spend per list-price dollar into kWh. Result: **13.5 g CO2e, 26 Wh and 0.07 L per $** (range 7.6–25 g).
- **Bottom-up** applies published per-token energy estimates to the Claude Code token mix. Result: **35 g CO2e, 68 Wh and 0.19 L per $** (range 16–88 g).
- Bottom-up is 2.6× higher at the median (range 1.0–7.4×).

## 1. Answer: CO2e break-even

| Equivalent of… | Footprint (central) | AI estimate | $ list price (low / central / high) | Million tokens* (low / central / high) | Pro 5-h windows at $66 (low / central / high) |
|---|---|---|---|---|---|
| (a) 1 work hour, full footprint | 5.0 kg | top-down | 196 / **369** / 663 | 518 / **975** / 1,751 | 3.0 / **5.6** / 10.0 |
| | | bottom-up | 56 / **143** / 319 | 149 / **377** / 842 | 0.85 / **2.2** / 4.8 |
| (a) 1 work hour, basic living | 3.9 kg | top-down | 151 / **285** / 514 | 399 / **754** / 1,358 | 2.3 / **4.3** / 7.8 |
| | | bottom-up | 43 / **110** / 247 | 114 / **292** / 652 | 0.66 / **1.7** / 3.7 |
| (a) 1 work hour, marginal | 0.37 kg | top-down | 9.7 / **27** / 65 | 26 / **71** / 171 | 0.15 / **0.41** / 0.98 |
| | | bottom-up | 3.1 / **10** / 29 | 8.2 / **27** / 77 | 0.05 / **0.16** / 0.44 |
| (b) 1 PCBA order (5 boards) | 21 kg | top-down | 800 / **1,582** / 3,015 | 2,114 / **4,181** / 7,967 | 12 / **24** / 46 |
| | | bottom-up | 234 / **611** / 1,430 | 618 / **1,615** / 3,778 | 3.5 / **9.3** / 22 |

\*Token counts use the Claude Code mix measured in this session: 97.6% cache reads, 0.4% output, $0.378 per million tokens [M1]. Your own `/usage` line has the same shape [U2]. The notes' mix ($1.12 per million tokens) gives 2.96× fewer tokens.

**What the footprints cover**
- **Full footprint:** the EU average footprint of 8.94 t CO2e per person per year [S21], spread over 1,821 working hours (40 h/week).
- **Basic living:** the full footprint minus holidays and air travel, leisure driving, restaurants, recreation and discretionary goods. It is 77% of the full footprint.
- **Marginal:** what one hour less work actually avoids: the computer, 25% of the hour's office energy, and 50% of an average commute (17.2 km one way).
- **PCBA order:** in the mode case, 3.6 kg bare boards, 5.3 kg ICs, 1.9 kg other parts, 2.8 kg assembly, 0.4 kg packaging and 4.5 kg express air.

**Energy and water.**
- **One work hour:** 12.8 kWh of final energy and 71 L of blue water.
- **PCBA order:** 34 kWh and 150 L. That water is fab withdrawal, so it does not compare directly with the AI's water consumption.
- **Break-even by energy instead of CO2e:** $483 / $187 for the full hour (top-down / bottom-up), $47 / $18 for the marginal hour and $1,276 / $493 for the PCBA order.

**Your earlier $229.58 session:** 3.1 kg CO2e top-down (1.7–5.8) or 8.0 kg bottom-up (3.6–20). The notes said 4.5 kg.

## 2. Decision rules

1. **Use the marginal row for your own choices.** You keep living and heating whether or not Claude does the work. On the marginal row, Claude has the smaller footprint only if:
   - **top-down: $10 of Claude replaces ≥ 22 min of your work** (P5–P95: 9–62 min), or one Pro window replaces ≥ 2.5 h (1–7 h);
   - **bottom-up: $10 replaces ≥ 58 min** (21–193 min), or one Pro window replaces ≥ 6.4 h.
2. **Working from home without a commute, footprint is no reason to use Claude.** The avoided footprint is 0.014 kg per hour, the computer's power, which matches only $1.1 (top-down) or $0.4 (bottom-up) of Claude per hour saved. Your computer also stays on while you supervise Claude. Use it for the value of the output, not to save CO2. For an office commuter who really skips the trip and the office space, break-even rises to $60 / $24 per hour.
3. **For productivity accounting (person-hour vs AI for a deliverable)**, the full-footprint row applies:
   - top-down: $10 must replace ≥ 1.6 min (0.9–3.1 min), and a Pro window ≥ 11 min (6–20 min);
   - bottom-up: $10 must replace ≥ 4.2 min, and a Pro window ≥ 28 min (12–70 min).
   - On the basic-living footprint, a Pro window must replace 14 min (top-down) or 36 min (bottom-up).
4. **PCBA: an avoided prototype re-spin is worth 9 (bottom-up) to 24 (top-down) Pro windows** of Claude use, at central values.
   - In 95% of the Monte Carlo draws it is worth more than 3.5 windows.
   - Multiply by the chance that the session really prevents a re-spin. For example, schematic and footprint review with a 30% chance of catching a re-spin-causing error is worth about 3–7 windows.
5. **Spend is a good proxy for footprint only if cache reads are as cheap to serve as their price suggests.** Top-down is proportional to $ by construction. Bottom-up gives 32–128 Wh per $ on the measured, cache-heavy mix, depending on the unmeasured energy of a cache read. Long agent loops that re-read large contexts may therefore cost more per $ than short, output-heavy chats.

**When the conclusion flips**
- **Bottom-up instead of top-down:** thresholds are 2.6× stricter at the median, and up to 7.4× in the 95th percentile.
- **If every token earned the full list price:** the top-down footprint rises from 13.5 to 21.6 g per $, and the marginal break-even falls to $16.5. This happens when no subscription usage is worth more than its fee.
- **Inference on gas-fired power:** SpaceX's Colossus relies on gas turbines [S4], and Anthropic plans sites with on-site gas generation [S2]. Then the top-down footprint is 17.9 g per $ and the marginal break-even $20.
- **One FPGA-class part (1 cm² die) per board:** the order rises to 27.5 kg and the break-even to $2,043 / $792.

**Biggest drivers of the spread** (tornado: ratio of the result with the input at high vs at low)
- **Top-down:** $ of compute per kWh ×3.8, value of subscription usage ×2.7, grid intensity ×1.6.
- **Bottom-up:** energy per output token ×5.8, cache-read energy ×4.0, input-token energy ×2.9.
- **Marginal hour:** whether the commute and office energy are really avoided, ×3.8 and ×3.5.
- **PCBA:** footprint per IC ×2.1.

## 3. Key assumptions

The full list of 42 inputs, with all bases and the notes' values, is in Appendix A.

| Input | Low / mode / high | Basis |
|---|---|---|
| Cost of revenue per revenue $ | 0.1448 | $4,812M / $33,242M for the nine months to Sep 2026 [S1] |
| Realised revenue per list-price $ | 0.32 / 0.61 / 1.00 | Revenue is 79% consumption and 21% subscription [S1]. ASSUMPTION: consumption earns 0.75–1.0 of list; subscriptions earn 0.1–1.0, because heavy users exceed their fee |
| $ of compute per facility kWh | 1.46 / 3.76 / 5.63 | SpaceX $1.25B/month for ~325k GPUs at 422–500 MW nameplate IT power [S4, S5], with ASSUMPTION utilisation 0.6–0.7 and PUE 1.2–1.3. The low is an owner's cost of $35B/GW [S6] over 5 years (ASSUMPTION) |
| Wh per 1k output tokens, net of input | 0.40 / 0.69 / 2.30 | Derived from Oviedo 0.31 Wh per 300+500 tokens [S7] and Jegham 2.99 Wh per 1k+1k [S9]. The low is an ASSUMPTION below Epoch's ~0.6 [S11] |
| Input / cache-read token energy | input 0.15 / 0.30 / 0.60 of an output token; cache read 0.02 / 0.05 / 0.20 of an input token | Input: 0.23 measured [S10], ~0.4 [S11]. Cache read: ASSUMPTION, mode equal to the price ratio [S3], no measurement found |
| Long-context multiplier | 1 / 1.5 / 3 | ASSUMPTION: Claude Code contexts of 50–200k tokens make each output token cost more |
| Grid intensity, kg CO2e/kWh | 0.38 / 0.40 / 0.60 | eGRID direct emissions [S12] × 1.147 upstream [S35]. High: ASSUMPTION 50/50 blend with on-site open-cycle gas at 0.725 [S67, S14] |
| Embodied hardware and water | ×1.05 / 1.11 / 1.25; 0.96 / 3.50 / 5.67 L/kWh | ~10% embodied [S15]. Water = on-site + power-plant water [S8, S9, S17, S18, S19] |
| Work hours per year | 1,821 (1,767–1,871) | 40 h/week [U3], less 24.3 days of leave and 9 public holidays [S31, S32] |
| Basic-living share of footprint | 0.67 / 0.77 / 0.85 | Leisure share of the household footprint: air 3–9%, leisure land travel 5–10%, discretionary 9–19% [S22–S29]; government spending counts as basic [S22] |
| Marginal hour | computer 30 W; office 21 m² at 140 + 60 kWh/m²·a; commute 17.2 km at 118 g/pkm; 25% of office and 50% of commute avoided | [S37–S41, S68, S33, S34]; avoided shares are ASSUMPTION |
| PCBA | PCB 35 / 60 / 120 kg/m²; IC 0.03 / 0.07 / 0.25 kg; R/C 0.04–0.6 g; express air 0.629 / 0.817 / 1.035 kg/t·km for 0.6 kg | [S44–S61]; board make-up is ASSUMPTION |
| Pro window | $66 | Your measurement [U1] |

## 4. Caveats

- **The AI numbers are estimates.**
  - Per-token energy is modelled from H100-era benchmarks of other vendors' models [S7, S9].
  - The top-down method rests on an undisclosed revenue ratio and on rental prices, which pay for reserved capacity rather than energy [S4].
  - Grid intensity is location-based, so renewable-energy purchases are ignored. Inference may run "in any available geography" [S20].
- **Training is excluded,** as the brief asked. Allocating all compute per $ would raise the top-down footprint 4.1× (3.9–4.3×) [S1].
- **The full and basic footprints are accounting allocations.** They count only if Claude reduces total human time needed. Time you save and spend elsewhere has its own footprint.
- **Basic-living shares are dated and partly judgement.** They rest on 2007–2010 studies [S23–S25] and the split is a judgement call. The same share is also applied to energy and water.
- **Water is not like-for-like.**
  - AI water is consumption (evaporation), both on site and at the power plant.
  - Human water is the 1996–2005 blue water footprint [S43].
  - PCBA water is fab withdrawal.
- **The PCBA estimate depends on the bill of materials.** Small-IC footprints are extrapolated from logic-node data [S50, S51], and per-IC footprint and die area are sampled independently. Sanity check: a Raspberry Pi 4/5 is 6.5 kg [S66], against 3.7 kg per board here.
- **Pro windows scale linearly from your $66 measurement.** Plan accounting may not weight tokens at list-price ratios.
- **The Monte Carlo treats inputs as independent.** P5–P95 shows spread, not a confidence interval. The comparison with the earlier notes is in Appendix B.

## 5. Sources

All sources were read on 2026-11-14. A research agent opened each one and found the quoted figure; that is the status VERIFIED unless marked otherwise.
- **Re-checked by a second, sceptical agent:** S1–S9, S12–S15, S17, S18, S21, S22, S30–S35, S41, S44, S45, S50, S51, S53, S56–S59, S66 and S68.
- **Corrected by that re-check:** S31, S33 and S58.
- "Secondary" marks news, blogs, mirrors and figures quoted from another source.

**Own data**
- [U1] Your measurement: one Pro 5-hour window ≈ $66 at list price.
- [U2] Your earlier `/usage` report: $229.58; 16.7M cache read / 293.6k cache write / 1.3k output tokens.
- [U3] Your brief: full-time means 40 h per week.
- [M1] This session's Claude Code transcripts (local JSONL files), summed by request:
  - 99.3M tokens: cache read 96.93M, 5-minute write 1.77M, 1-hour write 0.17M, output 0.40M, input 1.5k.

**Anthropic, compute and prices**
- [S1] Anthropic, PBC, *Form S-1/A Amendment No. 2*, SEC EDGAR, 2026-11-10. https://www.sec.gov/Archives/edgar/data/2130357/000162828026072484/anthropicpbc-sx1ax2.htm
  - Nine months 2026: revenue $33,242M; cost of revenue $4,812M; compute and infrastructure $18,808M.
  - "Substantially all of cost of revenue consists of compute and infrastructure costs associated with customer-serving workloads."
  - Consumption-based revenue $26.3B (79%); subscription $6.9B (21%). Revenue through cloud partners is recognised "on a gross basis".
- [S2] Anthropic, PBC, *Form S-1*, SEC EDGAR, 2026-10-26. https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm
  - H1 2026 revenue $16,286M; cost of revenue $2,380M.
  - No MW, GW, energy, emissions or water figures.
  - "certain of our planned data center facilities rely on dedicated on-site natural gas-fired generation".
- [S3] Anthropic, *Pricing*, Claude Platform Docs (no date on the page). https://platform.claude.com/docs/en/about-claude/pricing
  - Opus 5.5 per million tokens: input $4, 5-minute write $5, 1-hour write $8, cache read $0.20, output $20.
- [S4] Space Exploration Technologies Corp., *Form S-1/A*, SEC EDGAR, 2026-06-03. https://www.sec.gov/Archives/edgar/data/1181412/000162828026040364/spaceexplorationtechnologib.htm
  - "approximately 325,000 NVIDIA GPUs … $1.25 billion per month through May 2029".
  - "approximately 100,000 H100 … approximately 130 megawatts"; "approximately 110,000 GB200 … approximately 210 megawatts".
  - Nameplate Compute Draw "does not include power … such as cooling systems".
  - "We currently rely significantly on natural gas and gas turbine technology".
- [S5] Anthropic, *Higher usage limits and a SpaceX compute deal*, 2026-05-06. https://www.anthropic.com/news/higher-limits-spacex
  - "more than 300 megawatts of new capacity (over 220,000 NVIDIA GPUs)".
- [S6] M. Mantel, heise online, 2026-04-07. https://heise.de/-11247457
  - One GW "around 35 billion to 50 billion US dollars". Secondary; the estimate is unattributed.

**AI energy, grid and water**
- [S7] Oviedo et al. (Microsoft), arXiv:2509.20241, v1 2025-09-24, v2 2026-06-09 (Joule 2026, doi:10.1016/j.joule.2026.102430). https://arxiv.org/abs/2509.20241
  - "median energy of 0.31 Wh/query (IQR 0.16–0.60)" for models over 200B parameters on H100, with a median of 300 output and 500 input tokens.
  - Long reasoning queries: 3.91 Wh.
  - A modelled estimate, not a measurement.
- [S8] Elsworth et al. (Google), arXiv:2508.15734, 2025-08-21. https://arxiv.org/abs/2508.15734
  - 0.24 Wh per median Gemini Apps prompt; on-site WUE "1.15 L/kWh".
- [S9] Jegham et al., *How Hungry is AI?*, arXiv:2505.09598v6, 2025-11-24. https://arxiv.org/abs/2505.09598
  - Claude-3.7 Sonnet: 0.950 Wh (100 in / 300 out) and 2.989 Wh (1k / 1k); AWS on-site WUE 0.18 L/kWh.
  - Model-based estimate.
- [S10] Caravaca et al., *From Prompts to Power*, arXiv:2511.05597, 2025-11-05. https://arxiv.org/abs/2511.05597
  - opt-30b: 100/100 tokens 0.0137 Wh; 900/100 0.08 Wh; 100/900 0.3 Wh (in/out).
  - Derived: an input token uses about 0.23 of an output token's energy.
- [S11] J. You, Epoch AI, 2025-02-07. https://epoch.ai/gradient-updates/how-much-energy-does-chatgpt-use
  - "roughly 0.3 watt-hours" for 500 output tokens; about 2.5 Wh with a 10k-token input. Secondary.
- [S12] US EPA, *eGRID2023 rev2 summary data*, 2025-06-12. https://www.epa.gov/egrid/summary-data
  - Total output CO2e rate: US 770.884 lb/MWh, SRTV 903.306, ERCT 736.629.
  - Pre-combustion emissions are excluded (Technical Guide).
- [S13] IPCC, *AR5 WGIII Annex III*, Table A.III.2, 2014. https://www.ipcc.ch/site/assets/uploads/2018/02/ipcc_wg3_ar5_annex-iii.pdf
  - Gas combined cycle, lifecycle median 490 gCO2e/kWh.
- [S14] Nicholson & Heath, NREL/FS-6A50-80580, Sep 2021. https://www.nrel.gov/docs/fy21osti/80580.pdf
  - Natural gas 486 g CO2e/kWh total, of which 389 g combustion. Read from a local copy; the live site was unreachable.
- [S15] Schneider et al. (Google), arXiv:2502.01671, 2025-02-01. https://arxiv.org/abs/2502.01671
  - "embodied emissions are ∼10% and operational emissions are ∼90%".
- [S16] NVIDIA, *HGX H100 PCF Summary*, Aug 2025. https://images.nvidia.com/aem-dam/Solutions/documents/HGX-H100-PCF-Summary.pdf
  - "1,312 kg CO2e" cradle-to-gate per baseboard.
- [S17] Shehabi et al., *2024 United States Data Center Energy Usage Report*, LBNL-2001637, Dec 2024. https://eta-publications.lbl.gov/sites/default/files/2024-12/us_data_center_energy_usage_report_lbnl-2001637.pdf
  - Indirect water "4.52 L/kWh"; on-site WUE "just over 0.36 L/kWh".
- [S18] Li et al., arXiv:2304.03271v5, 2025-03-26. https://arxiv.org/abs/2304.03271
  - US electricity water intensity 3.142 L/kWh. Secondary: taken from WRI (Reig et al. 2020).
- [S19] Macknick et al., Environ. Res. Lett. 7 045802, 2012. https://doi.org/10.1088/1748-9326/7/4/045802
  - Gas combined cycle with cooling tower: 205 gal/MWh (0.78 L/kWh).
- [S20] Anthropic, *Prompt caching* (Claude Code Docs) and *Data residency* (Claude Platform Docs), no date on the pages. https://code.claude.com/docs/en/prompt-caching ; https://platform.claude.com/docs/en/manage-claude/data-residency
  - Subscription main conversation uses a 1-hour cache.
  - "Inference may run in any available geography".

**Human footprint, work time and commute**
- [S21] Eurostat, *cli_gge_foot*, updated 2026-10-30. https://ec.europa.eu/eurostat/databrowser/view/cli_gge_foot/default/table
  - 2024: EU 8,942 kg CO2e per capita; Germany 10,404. 2023: EU 9,003.
- [S22] Eurostat, *env_ac_ghgfp*, updated 2026-10-30. https://ec.europa.eu/eurostat/databrowser/view/env_ac_ghgfp/default/table
  - EU 2024 (derived shares): households 69.56%, government 9.25%, non-profits 0.54%, capital formation 19.78%.
  - Air transport (H51) is 2.6% of the household footprint.
- [S23] Ivanova et al., J. Ind. Ecol. 20(3):526, 2016. doi:10.1111/jiec.12371 (open preprint https://zenodo.org/record/1134811)
  - EU, Fig. 3: mobility 27.0%, shelter 26.2%, services 17.2%, manufactured products 16.6%, food 9.5%, clothing 3.5%. Read from the figure.
- [S24] Ivanova et al., Environ. Res. Lett., 2017. https://doi.org/10.1088/1748-9326/aa6da9
  - "Transport contributes to about 30% of EU household emissions".
- [S25] Ivanova & Wood, Global Sustainability, 2020. https://doi.org/10.1017/sus.2020.12
  - Air travel of all but the top 10% "below 0.1 tCO2eq/cap". Derived: about 4–5% of the household footprint.
- [S26] JRC, *Consumption Footprint Monitoring Report 2024* (JRC138470), 2025-03-04. https://publications.jrc.ec.europa.eu/repository/handle/JRC138470
  - Climate change: food 38%. Cross-check only.
- [S27] Umweltbundesamt, *Durchschnittlicher CO₂-Fußabdruck pro Kopf* (as of 2026). https://www.umweltbundesamt.de/bild/durchschnittlicher-co2-fussabdruck-pro-kopf-in
  - 9.8 t; Wohnen (housing) 1.9, Strom (electricity) 0.6, Mobilität (mobility) 2.1, Ernährung (food) 1.6, sonstiger Konsum (other consumption) 2.5, öffentliche Infrastruktur (public infrastructure) 1.1.
  - Derived cross-check: 71–78% basic.
- [S28] Bohmann & Küçük, *DIW Wochenbericht 27/2024*. https://www.diw.de/documents/publikationen/73/diw_01.c.906978.de/24-27-2.pdf
  - Mobility "2,0 tCO2e", mostly flights. Derived: flights 8–9% of the footprint.
- [S29] infas et al., *MiD 2023 Kurzbericht*. https://www.mobilitaet-in-deutschland.de/pdf/MiD2023_ZusammenfassungKurzbericht.pdf
  - Freizeit (leisure) 37% of passenger-km. The column alignment was not re-checked.
- [S30] Eurostat, *nrg_ind_eff* (updated 2026-04-21) and *demo_gind* (updated 2026-10-27), via https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/
  - EU final energy consumption 2024 (EED definition) 900.41 Mtoe; population 1 Jan 2024 450,054,483.
- [S31] Eurofound, *Working time in 2021–2022*, 2023; PDF revised 2024-05-21. https://assets.eurofound.europa.eu/f/279033/356ff40090/ef23007en.pdf
  - EU27 full-time "1,726 hours in 2022"; leave 24.3 days; 9.0 public holidays (those not falling on Sundays); 38.1 h/week; Germany 30 days of leave.
- [S32] Directive 2003/88/EC, Art. 7(1), OJ L 299, 2003-11-18. https://publications.europa.eu/resource/celex/32003L0088
  - "paid annual leave of at least four weeks".
- [S33] Destatis, *Erwerbstätige nach … Entfernung, Zeitaufwand und benutztem Verkehrsmittel*, Mikrozensus 2024, as of 2026-10-30, employees column. https://www.destatis.de/DE/Themen/Arbeit/Arbeitsmarkt/Pendeln-Arbeitsbedingungen/Tabellen/pendler1.html
  - Mode shares: car 65.2%, bicycle 10.2%, walking 7.2%, bus 5.7%, tram/U-Bahn 5.5%, rail 4.8%.
  - Distance classes: 26.6 / 22.4 / 29.4 / 14.5 / 5.3%.
- [S34] Umweltbundesamt, *Vergleich der durchschnittlichen Emissionen einzelner Verkehrsmittel im Personenverkehr 2024* (TREMOD 6.71B), 2025-12-10. https://www.umweltbundesamt.de/system/files/medien/366/bilder/dateien/vtv_2024_pv_tab_pdf.pdf
  - g CO2e/pkm: car 164, bus 90, local rail 44, tram/U-Bahn 42.
- [S35] Icha & Lauf, UBA Climate Change 16/2026, Mar 2026. https://www.umweltbundesamt.de/system/files/medien/11850/publikationen/2026-03/16_2026_CC.pdf
  - German electricity mix 2024: 361 g CO2e/kWh without upstream, 414 g with upstream.
- [S36] Umweltbundesamt, *Liste Emissionsfaktoren zur THG-Bilanzierung* v2.1, 2026-02-28. https://www.umweltbundesamt.de/system/files/document/uba_liste_ef_f%C3%BCr_thg_bilanzierung_v2.1.xlsx
  - Natural gas 0.2423 kg CO2e/kWh including upstream.
- [S37] US EPA, *ENERGY STAR certified computers and displays* datasets, 2026-11-13. https://data.energystar.gov/resource/rxdj-2c88.json ; https://data.energystar.gov/resource/qbg3-d468.json
  - Derived medians: notebook short idle 4.9 W; desktop 10.5 W; 24" display 12.9 W.
- [S38] BAuA, *ASR A1.2*, 2013, amended 2022. https://www.baua.de/DE/Angebote/Regelwerk/ASR/pdf/ASR-A1-2.pdf
  - "mindestens 8 m2 für einen Arbeitsplatz zuzüglich mindestens 6 m2 für jeden weiteren" (at least 8 m² for one workplace plus at least 6 m² for each further one); worked example 9.54 m² per workplace (3-person office).
- [S39] Catella Research, 2023. https://www.catella.com/globalassets/documents/germany-property-funds/02_research/03_market-tracker/buroflache_02_2506.pdf
  - European city average 20.88 m² per office employee. Secondary (industry).
- [S40] dena, *Fokusthemen Büro- und Verwaltungsgebäude*, Dec 2023. https://www.gebaeudeforum.de/fileadmin/gebaeudeforum/Downloads/Gebaeudereport/Gebaeudeforum_GR24_Fokusthemen_Buerogebaeude.pdf
  - 395M m²; 12.8M office employees; heat 55.3 TWh (derived 140 kWh/m²·a); "Nutzerstrom … 60 kWh/m²" (user electricity).
- [S41] BMWi/BMI, BAnz AT 03.05.2021 B1. https://www.gebaeudeforum.de/fileadmin/gebaeudeforum/Downloads/Rechtsvorschrift/2021-04-15_Bekanntmachung_Energieverbrauchswerte_NWG.pdf
  - Bürogebäude (office buildings): heating 49.0 and hot water 8.1 kWh/(m²·a); electricity components sum to 25.5. Mirror of the Bundesanzeiger page.
- [S43] Mekonnen & Hoekstra, *Value of Water Research Report 50*, UNESCO-IHE, 2011, data 1996–2005. https://ayhoekstra.nl/pubs/Report50-WaterFootprintNations-Vol2.pdf
  - Germany: blue water footprint 85.1 m³ per capita per year. EU-27 142 (derived, population-weighted).
- [S68] BBSR, press release, 2025-10-10. https://www.bbsr.bund.de/BBSR/DE/presse/presseinformationen/2025/pendeln-2024.html
  - "Der durchschnittliche einfache Arbeitsweg betrug 17,2 Kilometer" (the average one-way commute was 17.2 km; 2024).
- [S69] visitBerlin, *Brückentage und Feiertage Berlin 2026*. https://www.visitberlin.de/de/brueckentage-feiertage-berlin-2026
  - Berlin has 10 public holidays, 7 of them on weekdays in 2026. Secondary.

**PCBA**
- [S44] Dynamic Electronics (Huangshi), *PCB (10 Layer) Report for Product Carbon Footprint Assessment (ISO 14067)*, 2023-07-24. https://www.dynaholding.com/en/file/2024/ (file "8.PCB(10L) Report for product carbon footprint assemsent…pdf")
  - Per square foot: 16.6347 kg CO2e, 10.993 kWh, 0.10571 t water.
  - Board mass 0.112 kg at 167×185 mm (3.6 kg/m²).
  - Data year 2022; not third-party verified; grid factor about 0.82 kg/kWh.
- [S45] VHK for the EC, *MEErP 2011 Part 2*, Table 17. https://www.eceee.org/static/media/uploads/site-2/ecodesign/products/ecodesign-directive-evaluation-methodology/meerp-methodology-part-2-final.pdf
  - 6-layer PWB 4.5 kg/m² at 16 kg CO2e/kg; SMD/LED average 167 kg CO2e/kg.
- [S46] Nassajfar et al., Sustainability 13:12126, 2021. https://doi.org/10.3390/su132112126
  - "34.8" kg CO2e per m² of 4-layer PCB.
- [S47] Victory Giant Technology, *2025 ESG report*. https://pdf.dfcfw.com/pdf/H2_AN202604281821694722_1.pdf
  - Derived: 0.0846 t CO2e/m², Scope 1+2 only. Exchange-filing mirror.
- [S48] Pirson & Bol, arXiv:2105.02082, 2021. https://arxiv.org/abs/2105.02082
  - 4-layer PCB block about 160 kg/m² including assembly; MCU of 5–17 mm²: 0.08–0.29 kg.
- [S49] China MEE, *HJ 450-2008 清洁生产标准 印制电路板制造业* (clean production standard, PCB manufacturing). https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/other/qjscbz/200811/W020111114391492039465.pdf
  - Multilayer board with 2+n layers: water from ≤(0.5+0.3n) (grade 1) to ≤(1.3+0.5n) m³/m² (grade 3); electricity from ≤(45+20n) to ≤(75+30n) kWh/m²; +15% for prototype makers.
  - For 4 layers, n = 2: water 1.1–2.3 m³/m², electricity 85–135 kWh/m².
- [S50] Chen et al., *CarbonClarity*, arXiv:2507.01145v2, 2026-01-15. https://arxiv.org/abs/2507.01145
  - "1.18 kgCO2 per cm2" at 28 nm.
- [S51] Gupta et al., *ACT*, ISCA 2022. https://hsienhsinlee.github.io/MARS/pub/isca2022.pdf (author copy)
  - Packaging "0.15kg CO2" per IC; fab energy "0.8-3.5 kWh per cm2".
- [S52] Andersen, Walnum & Andrae, Vestlandsforsking report 6/2010. https://www.vestforsk.no/sites/default/files/migrate_files/sluttrapport-conpart-6-10.pdf
  - Small IC (SOD6): "0.058" kg CO2e per unit.
- [S53] Smith et al., Applied Energy 220:496, 2018. https://eprints.whiterose.ac.uk/id/eprint/130419/
  - 670,630 0402 MLCCs per kg; 97.00 kg CO2e per kg.
- [S54] Zhang et al., *DeltaLCA*, Proc. ACM IMWUT 8(1), 2024. https://doi.org/10.1145/3643561
  - Resistor 0402: 0.040 g; capacitor 0603: 0.611 g CO2e.
- [S55] Weidmüller, EPDs for PCB connectors SL 5.00, LSF-SMD 3.50 and B2CF 3.50, 2025–2026. https://assets.dam.weidmueller.com/assets/api/e02a0daa-702e-4dab-a6ab-189ecb618991/original/EPD_PCB_connector_series_SL_5_00.pdf (and sibling files)
  - Manufacturing stage (A1–A3): 6.3, 18.6 and 46.1 g CO2e per piece.
- [S56] Nordelöf, Int J LCA 24:694, 2019. https://research.chalmers.se/publication/504321/file/504321_Fulltext.pdf
  - SMT assembly of 1 m²: "Electricity 46 kWh", "Nitrogen 64 kg". Automotive board, includes conformal coating.
- [S57] China MEE/NBS, Announcement 2025 No. 47, 2025-12-31. https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202512/W020251231726284332528.pdf
  - 2023, kg CO2/kWh: Guangdong 0.4419; Hubei 0.4044; national 0.5306.
- [S58] China MEE/NBS/NEA, Announcement 2025 No. 19, 2025-10-24. https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202510/W020251024569470952545.pdf
  - 2024 national "0.5777" kg CO2e/kWh (lifecycle).
- [S59] UK DESNZ, *GHG conversion factors 2025*, 2025-06-10. https://assets.publishing.service.gov.uk/media/6846b6ea57f3515d9611f0dd/ghg-conversion-factors-2025-flat-format.xlsx
  - International freight flights: 0.89939 kg CO2e/t·km with radiative forcing, plus 0.13516 well-to-tank.
- [S60] Smart Freight Centre, *GLEC Framework v3.0*, Sep 2023, Module 2, Table 1. https://knowledgeplatform.ecta.com/wp-content/uploads/2023/09/2023_GLEC_FRAMEWORK_v3.0_September.pdf
  - Long-haul, g CO2e/t·km well-to-wheel: freighter 629, unknown aircraft 817; unknown aircraft tank-to-wheel 646.
  - Copy hosted by ECTA.
- [S61] DHL GoGreen Plus certificate, reproduced by Böcker, 2026-07-24. https://www.boecker.de/en/company/boecker-goes-green/articles/artikel/24/07/2026/emissionsreduktion-bei-lufttransporten
  - "837.80 grams per tkm" (cross-check only). Secondary.
- [S62] Wang et al., Water Cycle 4:47, 2023. https://doi.org/10.1016/j.watcyc.2023.01.004
  - "8.22 L/cm2, 1.15 kWh/cm2". Read from the abstract only.
- [S63] GlobalFoundries, *2026 Sustainability Report* (https://gf.com/wp-content/uploads/2026/08/GlobalFoundries-2026-Sustainability-Report.pdf) and FY2025 10-K (https://www.sec.gov/Archives/edgar/data/1709048/000170904826000022/gfs-20251231.htm)
  - 13,864,993 GJ; 25,960 thousand m³ of water withdrawn; 2.3M wafers.
  - Derived: 2.37 kWh/cm² and 16.0 L/cm².
- [S64] Uptime Institute, *Global Data Center Survey 2026*, Jul 2026. https://datacenter.uptimeinstitute.com/rs/711-RIA-145/images/UptimeInstitute.GlobalDataCenterSurvey.2026.pdf
  - "2026 industry average PUE is 1.52".
- [S65] S. Altman, *The Gentle Singularity*, 2025-06-10. https://blog.samaltman.com/the-gentle-singularity
  - "about 0.34 watt-hours" per query. Cited only because the notes used it. Secondary (blog).
- [S66] E. Upton, Raspberry Pi blog, 2025-01-09. https://www.raspberrypi.com/news/16gb-raspberry-pi-5-on-sale-now-at-120/
  - "6.5kg of CO₂ equivalent". Secondary (blog).
- [S67] US EIA, *Electric Power Annual* Table 8.2 (https://www.eia.gov/electricity/annual/html/epa_08_02.html) and *CO2 emissions coefficients* (https://www.eia.gov/environment/emissions/co2_vol_mass.php)
  - Open-cycle gas turbine heat rate 10,975 Btu/kWh; natural gas 52.91 kg CO2/MMBtu.

**Not verified or not used:** Jensen Huang's "$50–60B per GW" (UNVERIFIED); GLEC v3.2 (returned 403); ecoinvent datasets (licence required); WRI 2020 water guidance (not opened).

## Appendix A: All inputs

"Derived" means calculated from the cited sources. The last column shows the notes' value where it differs.

| Input | Low / mode / high | Basis | Notes had |
|---|---|---|---|
| Cost of revenue / revenue | 0.1448 | [S1] | 0.146 (H1) |
| Compute share of cost of revenue | 0.90 / 0.95 / 1.00 | ASSUMPTION: "substantially all", plus some personnel and overhead [S1] | 1.0 |
| Realised / list, consumption revenue | 0.75 / 0.85 / 1.00 | ASSUMPTION: metered per token at list or committed price lists; Q3 price cuts and discounts were about 3.5% of revenue [S1] | 1.0 |
| Realised / list, subscriptions | 0.10 / 0.30 / 1.00 | ASSUMPTION: fixed fees with usage caps; heavy Claude Code subscribers use several times their fee | 1.0 |
| → r (harmonic mix, 79/21) | 0.32 / 0.61 / 1.00 | Derived | — |
| $ per facility kWh | 1.46 / 3.76 / 5.63 | Derived. **High:** $1.25B/month [S4] ÷ (422 MW = 325k GPUs × 1.3 kW for H100 [S4], ×0.6 utilisation × PUE 1.2). **Mode:** 500 MW (300 MW Colossus 1 [S5] + 105k GB200 × 1.91 kW [S4]), ×0.7 × 1.3. **Low:** $35B/GW [S6] ÷ (5 years × 75% utilisation) × 1.3 for opex and financing + $0.08/kWh. Utilisation, PUE, life and uplift are ASSUMPTIONs; PUE is set below the industry average of 1.52 [S64] for new AI sites | 1.7 / 3.6 / 7.6 |
| Wh per 1k output tokens, net of input | 0.40 / 0.69 / 2.30 | Derived from [S7, S9] using an input/output energy ratio of 0.3. Low: ASSUMPTION below about 0.6 [S11] | 0.34 Wh per query [S65] |
| Long-context multiplier | 1 / 1.5 / 3 | ASSUMPTION: long Claude Code contexts make decoding costlier | — |
| Input / output token energy | 0.15 / 0.30 / 0.60 | 0.23, derived from three data points [S10]; about 0.42 (2.5 Wh per 10k input vs 0.3 Wh per 500 output) [S11] | — |
| Cache-read / input token energy | 0.02 / 0.05 / 0.20 | ASSUMPTION: mode equal to the price ratio [S3] | — |
| Grid, kg CO2e/kWh | 0.383 / 0.401 / 0.598 | eGRID direct: Texas 0.334, US 0.350 [S12], × 1.147 upstream (German mix ratio as a proxy [S35]). High: ASSUMPTION 50/50 blend of Tennessee 0.410 × 1.147 and open-cycle gas 10,975 Btu/kWh × 52.91 kg/MMBtu [S67] × 486/389 [S14] = 0.725 | 0.35 / 0.40 / 0.45 |
| Embodied uplift | 1.05 / 1.11 / 1.25 | ~10% [S15]; ~2–3% for the baseboard alone (derived [S16]); <25% [S15] | 1.1 / 1.2 / 1.3 |
| Water, L/kWh | 0.96 / 3.50 / 5.67 | 0.18 [S9] + 0.78 [S19]; 0.36 [S17] + 3.14 [S18]; 1.15 [S8] + 4.52 [S17] | 1.5 / 2.5 / 4.0 |
| Token mix → $/MTok | measured 0.378 | [M1]; notes' mix 1.12 | 1.12 |
| Pro window | $66 | [U1] | $71 or $7.40 |
| Footprint, kg/person/year | 8,048 / 8,942 / 10,404 | EU and Germany 2024 [S21]; low: ASSUMPTION −10% model uncertainty | 9,000 |
| Hours per week | 40 | [U3]; the EU collective average is 38.1 [S31] | 40 |
| Leave / holidays, days | 20 / 24.3 / 30; 7 / 9 / 10 | [S32], [S31]; Berlin 2026 [S69] | none → 2,080 h |
| Air travel, leisure land travel, discretionary (share of household footprint) | 2.6 / 5 / 9%; 5 / 8 / 10%; 9.3 / 13.1 / 18.7% | H51 [S22]; [S25] derived; [S28] derived. Land travel (20–25% [S23, S24]) × 37% leisure [S29]. Discretionary: ASSUMPTION 25–50% of manufactured goods, services and clothing (37.3% [S23]) | — |
| → basic share | 0.67 / 0.77 / 0.85 | × 0.877 household share of consumption [S22]; consistent with UBA 71–78% [S27] | — |
| Final energy, MWh/person/year | 23.27 | [S30] | 23.3 |
| Blue water, m³/person/year | 85.1 / 142 / 170 | [S43]; high: ASSUMPTION +20% | — |
| Workstation, kW | 0.015 / 0.030 / 0.100 | Idle values [S37]; ASSUMPTION active-use uplift | — |
| Office area, m² per employee | 9.5 / 20.9 / 30.9 | [S38] worked example; [S39] (secondary, preferred for occupied area); [S40] derived from total stock | — |
| Office heat / electricity, kWh/m²·a | 57.1 / 140 / 140; 25.5 / 60 / 60 | Benchmark [S41]; stock average [S40] | — |
| Office energy avoided | 0 / 0.25 / 1 | ASSUMPTION: fixed in the short run; floor space follows hours in the long run | — |
| Commute avoided | 0 / 0.5 / 1 | ASSUMPTION: only when saved hours become days not commuted | — |
| One-way commute, km | 8 / 17.2 / 25 | [S68]; distance classes give 16.4 [S33]. Low and high: ASSUMPTION, short urban to long suburban | — |
| Commute EF | 0 / 1 / 1.4 × 118 g/pkm | [S33] × [S34]; 0 = cycling or walking, 1.4 ≈ car only | — |
| Electricity / gas heat EF, kg/kWh | 0.414 / 0.242 | [S35], [S36] | — |
| Commute energy, kWh/pkm | car 0.45; public transport 0.15 | ASSUMPTION: 7 L/100 km at 1.4 occupants; public transport about ⅓ of car | — |
| Board make-up | 5 × (15 IC, 255 R/C/L, 24 discretes, 6 connectors) | ASSUMPTION: typical mixed-signal prototype | — |
| Area incl. panel waste, m² | 0.05 / 0.06 / 0.07 | ASSUMPTION | 0.07 |
| PCB, kg CO2e/m² | 35 / 60 / 120 | 34.8 [S46]; ~72 [S45]; [S44] 179 for 10 layers → ~72 for 4 layers at its 0.82 grid factor, ~40 at Hubei 0.40 [S57] (derived); 85 Scope 1+2 only [S47]. Mode and high: ASSUMPTION (high excludes assembly, which is counted separately) | 25 / 50 / 100 |
| PCB fab energy / water | 85 / 110 / 155 kWh/m²; 1,100 / 1,700 / 2,600 L/m² | [S49] grade 1 to grade 3 +15%; [S44] | — |
| Per IC, kg CO2e | 0.03 / 0.07 / 0.25 | Die 2–15 mm² × 0.0118 kg/mm² [S50] + package (ASSUMPTION 0.01 for small packages, up to 0.15 [S51]); [S48]; [S52] | 0.04 / 0.10 / 0.5 |
| Die area per IC, mm² | 2 / 5 / 15 | ASSUMPTION | — |
| Fab energy / water per cm² | 1.15 / 1.6 / 2.37 kWh; 8.2 / 12 / 16 L | [S62], [S63]; mode: ASSUMPTION midpoint | — |
| R/C/L, discrete, connector, g CO2e each | 0.04 / 0.15 / 0.60; 1.5 / 9 / 58; 5 / 20 / 50 | [S53, S54]; 167 kg/kg [S45] × ASSUMPTION 9 mg, up to [S52]; [S55] | 1.5 / 4 / 10 for all |
| SMT, kWh/m²; set-up, kWh | 46 / 46 / 65.2; 0 / 2 / 8 | [S56] + ASSUMPTION 0.3 kWh/kg for 64 kg N2; set-up: ASSUMPTION, pooled line vs dedicated oven warm-up | 3 / 5 / 10 kg CO2e |
| China grid, kg/kWh | 0.44 / 0.58 / 0.82 | Guangdong CO2 only [S57]; national lifecycle [S58]; [S44] | — |
| Packaging, kg CO2e | 0.15 / 0.43 / 1.0 | ASSUMPTION: 0.10–0.25 kg of carton and foam × 1.5–4 kg CO2e/kg | 0.3 / 0.5 / 1.0 |
| Shipment, kg | 0.4 / 0.6 / 1.0 | 3.6 kg/m² [S44] → ~33 g per board, plus parts and packaging (ASSUMPTION) | 1.0 |
| Air EF, kg/t·km (well-to-wheel) | 0.629 / 0.817 / 1.035 | GLEC freighter and unknown aircraft [S60]; DESNZ with radiative forcing + well-to-tank [S59]; DHL 0.838 [S61] as cross-check | 0.65–0.8 |
| Distance; air energy | 8,855 km + 340 km road at 0.6 kg/t·km; 2.43 kWh/t·km | Derived great circle; road: ASSUMPTION; energy: 0.646 [S60] ÷ 3.16 × 11.9 (ASSUMPTION: standard fuel constants) | 9,100 km |

## Appendix B: Differences from the earlier notes

1. **$ per kWh.** The notes paired $1.25B/month with 300 MW. In fact the $1.25B buys about 325k GPUs across Colossus and Colossus II [S4], and the 300 MW is Colossus 1 only [S5]. The MW figures are IT nameplate power without cooling [S4].
2. **List price ≠ revenue.** 21% of revenue is subscriptions [S1], so the footprint per list $ is lower (r = 0.61).
3. **Bottom-up method.** The notes' per-token cross-check used 0.34 Wh per query, which is Altman's figure [S65]. Oviedo et al. give 0.31 Wh [S7], and it includes 500 input tokens, which are now netted out.
4. **Human inputs.** 2024 footprint 8.94 t instead of 9.0 t for 2023 [S21]. 1,821 h instead of 2,080 h, because leave and public holidays are subtracted [S31].
5. **Token mix.** Measured Claude Code use is 97.6% cache reads [M1], against the notes' 90%. This makes tokens about 3× cheaper ($0.378 vs $1.12 per million), so about 3× more tokens per $.
6. **PCBA is 18.4 kg (mode) / 21 kg (median) instead of ~30.** ICs 5.3 kg instead of 7.5; passives and other parts 1.9 kg instead of 5.7 (measured per-part LCAs are 10–100× lower [S53–S55]); express air 4.5 kg instead of 7.3; assembly 2.8 kg instead of 5.0 [S56]; bare boards 3.6 kg instead of 3.5.
7. **Net effect.**
   - One full work hour: **$369** (top-down) / **$143** (bottom-up), against the notes' $222.
   - The PCBA order: **$1,582 / $611**, against $1,513.
   - The marginal view, which the notes did not quantify: **$27 / $10** per hour.

## Appendix C: Script

Run with `python3 claude-breakeven.py`. It needs only the Python standard library and runs in about 8 s.

```python
#!/usr/bin/env python3
"""Break-even between Claude Code use and (a) one EU work hour, (b) one PCBA prototype order.

Every input is listed below with its source tag ([S..] = claude-breakeven.md section 5,
[U..] = the user's own data, [M1] = transcripts measured in this session). Uncertain
inputs are triples (low, mode, high). The Monte Carlo draws each one independently from a
triangular distribution - over log(low)..log(high) when low > 0, otherwise linear - and
reports P5 / P50 / P95. The report quotes P50 as "central". The tornado swings one input
from low to high with all others at their mode.

Standard library only. Run:  python3 claude-breakeven.py
"""
import math
import random

# ---------------------------------------------------------------------------
# 1. Fixed, sourced constants
# ---------------------------------------------------------------------------
# [S1] Anthropic S-1/A No.2, nine months to 30 Sep 2026, $M
REV_9M, COR_9M, COMPUTE_9M = 33_242, 4_812, 18_808
COR_SHARE = COR_9M / REV_9M            # cost of revenue per revenue $
CONSUMPTION_SHARE = 0.79               # [S1] consumption-based share of revenue (21% subscription)
# [S3] Opus 5.5 list prices, $/MTok
PRICE = dict(inp=4.0, w5=5.0, w1h=8.0, cr=0.20, out=20.0)
# [M1] token mix measured in this session's Claude Code transcripts (99.3M tokens, 792 requests)
MIX = dict(cr=0.9764, w5=0.0179, w1h=0.0017, inp=0.0000155, out=0.0040)
# Earlier notes' mix (unsourced): 90% cache read, 6% write, 1% input, 3% output
MIX_NOTES = dict(cr=0.90, w5=0.06, w1h=0.0, inp=0.01, out=0.03)
PRO_WINDOW_USD = 66.0                  # [U1] user's measured Pro 5-h window, list-price $
SESSION_USD = 229.58                   # [U2] user's earlier /usage session cost
HOURS_PER_WEEK = 40                    # [U3] brief: full-time 40 h/week
# [S4] SpaceX S-1/A: $1.25B per month for ~325,000 GPUs (Colossus + Colossus II);
#      nameplate IT power per GPU (excludes cooling): 130 MW/100k H100, 210 MW/110k GB200
SPACEX_USD_MONTH, SPACEX_GPUS = 1.25e9, 325_000
KW_PER_GPU = dict(h100=130e3 / 100e3, gb200=210e3 / 110e3)
COLOSSUS1_MW, COLOSSUS1_GPUS = 300.0, 220_000    # [S5] ">300 MW", ">220,000 GPUs"
CAPEX_PER_GW = (35e9, 50e9)            # [S6] $ per GW (secondary)
HOURS_PER_MONTH = 8766 / 12
# Grid factors
EGRID = dict(us=0.3497, srtv=0.4097, erct=0.3341)   # [S12] kg CO2e/kWh direct (770.884 lb/MWh etc.)
UPSTREAM_GRID = 0.414 / 0.361          # [S35] German mix with/without upstream, used as proxy
UPSTREAM_GAS = 486 / 389               # [S14] gas lifecycle / combustion
GT_HEAT_RATE, GAS_KG_PER_MMBTU = 10_975, 52.91   # [S67] Btu/kWh open-cycle; kg CO2/MMBtu
OPEN_CYCLE = GT_HEAT_RATE / 1e6 * GAS_KG_PER_MMBTU * UPSTREAM_GAS
# Water
WATER = dict(lo=0.18 + 0.78, c=0.36 + 3.14, hi=1.15 + 4.52)  # on-site [S9,S17,S8] + generation [S19,S18,S17]
# Human
FP_EU, FP_DE = 8_942, 10_404           # [S21] kg CO2e per capita 2024
FEC_MTOE, POP_EU, MWH_PER_TOE = 900.41, 450_054_483, 11.63    # [S30]
WEEKDAYS_PER_YEAR = 365.25 / 7 * 5
# [S22] EU 2024 footprint shares: households 69.56%, government 9.25%, NPISH 0.54%
HH_SHARE_OF_CONSUMPTION = 0.6956 / (0.6956 + 0.0925 + 0.0054)
# [S33] Destatis Mikrozensus 2024, employees: mode shares (%) and distance classes (%)
MODE_SHARE = dict(car=65.2, bike=10.2, walk=7.2, bus=5.7, tram=5.5, rail=4.8)
DIST_CLASS = [(2.5, 26.6), (7.5, 22.4), (17.5, 29.4), (37.5, 14.5), (60.0, 5.3)]  # (km, %); 60 = ASSUMPTION
EF_PKM = dict(car=164, bike=0, walk=0, bus=90, tram=42, rail=44)   # [S34] g CO2e/pkm
CI_DE, EF_GAS = 0.414, 0.242           # [S35], [S36] kg CO2e/kWh incl. upstream
CAR_KWH_PKM, PT_KWH_PKM = 0.45, 0.15   # ASSUMPTION: ~7 L/100 km / 1.4 occupants; PT ~1/3 of car
# PCBA
BOARDS, N_IC, N_RC, N_DISC, N_CONN = 5, 15, 255, 24, 6    # ASSUMPTION board make-up (300 placements)
AIR_KM, ROAD_KM, ROAD_EF = 8_855, 340, 0.6   # derived great circle HKG-LEJ; road legs + van EF ASSUMPTION
AIR_KWH_TKM = 0.646 / 3.16 * 11.9      # [S60] TTW kg/t-km / 3.16 kg CO2 per kg fuel x 11.9 kWh/kg (ASSUMPTION)
SMT_N2_KWH_M2 = 64 * 0.3               # [S56] 64 kg N2/m2 x ASSUMPTION 0.3 kWh/kg
FPGA_KG = 1.0 * 1.18 + 0.15            # 1 cm2 die x [S50] 1.18 kg/cm2 + [S51] 0.15 kg package

# ---------------------------------------------------------------------------
# 2. Derived input ranges
# ---------------------------------------------------------------------------
def spacex_usd_per_kwh(mw_it, util, pue):
    """Rental price per facility kWh: monthly fee / (nameplate IT MW x utilisation x PUE x hours)."""
    return SPACEX_USD_MONTH / (mw_it * 1e3 * HOURS_PER_MONTH * util * pue)

def tco_usd_per_kwh(capex_per_gw, life_yr=5, util=0.75, opex_uplift=1.3, power_price=0.08):
    """Owner's cost per kWh: amortised capex x uplift (opex, financing) + electricity."""
    return capex_per_gw / (1e6 * 8766 * life_yr * util) * opex_uplift + power_price

MW_ALL_H100 = SPACEX_GPUS * KW_PER_GPU['h100'] / 1e3
MW_MIX = COLOSSUS1_MW + (SPACEX_GPUS - COLOSSUS1_GPUS) * KW_PER_GPU['gb200'] / 1e3
USD_KWH = (tco_usd_per_kwh(CAPEX_PER_GW[0]),           # most kWh per $ (owner's cost, no margin)
           spacex_usd_per_kwh(MW_MIX, 0.70, 1.30),       # ASSUMPTION util 0.70, PUE 1.30
           spacex_usd_per_kwh(MW_ALL_H100, 0.60, 1.20))  # fewest kWh per $
CI_AI = (EGRID['erct'] * UPSTREAM_GRID, EGRID['us'] * UPSTREAM_GRID,
         0.5 * EGRID['srtv'] * UPSTREAM_GRID + 0.5 * OPEN_CYCLE)   # high: ASSUMPTION 50/50 blend
# Energy per 1k output tokens, net of the input tokens in each benchmark (k_in = 0.3)
E_OUT = (0.4,                                  # ASSUMPTION: newer accelerators, below Epoch's ~0.6 [S11]
         0.31 / (0.300 + 0.500 * 0.3),         # [S7] 0.31 Wh per 300 out + 500 in
         2.989 / (1.0 + 1.0 * 0.3))            # [S9] 2.989 Wh per 1k out + 1k in

# ---------------------------------------------------------------------------
# 3. Uncertain inputs: name -> (low, mode, high, basis)
# ---------------------------------------------------------------------------
PARAMS = {
    # --- AI, top-down ---
    'compute_frac': (0.90, 0.95, 1.00, 'compute share of cost of revenue [S1; ASSUMPTION]'),
    'r_cons':       (0.75, 0.85, 1.00, 'realised/list on consumption revenue [S1; ASSUMPTION]'),
    'r_subs':       (0.10, 0.30, 1.00, 'realised/list on subscriptions [ASSUMPTION]'),
    'usd_per_kwh':  (*USD_KWH, '$ of compute per facility kWh [S4,S5,S6; ASSUMPTION]'),
    # --- AI, bottom-up ---
    'e_out':        (*E_OUT, 'Wh per 1k output tokens net of input [S7,S9,S11]'),
    'm_ctx':        (1.0, 1.5, 3.0, 'long-context decode multiplier [ASSUMPTION]'),
    'k_in':         (0.15, 0.30, 0.60, 'uncached input / output token energy [S10,S11]'),
    'k_cr':         (0.02, 0.05, 0.20, 'cache-read / uncached input token energy [S3; ASSUMPTION]'),
    # --- AI, both ---
    'ci_ai':        (*CI_AI, 'grid kg CO2e/kWh [S12,S14,S35,S67; ASSUMPTION]'),
    'emb':          (1.05, 1.11, 1.25, 'embodied hardware uplift [S15,S16]'),
    'water_ai':     (WATER['lo'], WATER['c'], WATER['hi'], 'L/kWh on-site + generation [S8,S9,S17,S18,S19]'),
    # --- Human ---
    'fp':           (FP_EU * 0.9, FP_EU, FP_DE, 'kg CO2e per capita per year [S21; ASSUMPTION low]'),
    'leave':        (20.0, 24.3, 30.0, 'paid leave days [S31,S32]'),
    'holidays':     (7.0, 9.0, 10.0, 'public holidays on weekdays [S31,S69]'),
    'leis_air':     (0.026, 0.05, 0.09, 'air travel, share of household footprint [S22,S25,S28]'),
    'leis_land':    (0.05, 0.08, 0.10, 'leisure land travel, share of household footprint [S23,S24,S29]'),
    'leis_disc':    (0.25 * 0.373, 0.35 * 0.373, 0.50 * 0.373, 'discretionary goods/services [S23; ASSUMPTION]'),
    'water_cap':    (85.1, 142.0, 170.0, 'blue water footprint m3/cap/yr [S43; ASSUMPTION high]'),
    'dev_kw':       (0.015, 0.030, 0.100, 'workstation kW in use [S37; ASSUMPTION]'),
    'office_m2':    (9.5, 20.9, 30.9, 'office m2 per employee [S38,S39,S40]'),
    'office_heat':  (57.1, 140.0, 140.0, 'office heat kWh/m2a [S41,S40]'),
    'office_el':    (25.5, 60.0, 60.0, 'office electricity kWh/m2a [S41,S40]'),
    'office_avoid': (0.0, 0.25, 1.0, 'share of office energy avoided [ASSUMPTION]'),
    'commute_avoid':(0.0, 0.5, 1.0, 'share of average commute avoided [ASSUMPTION]'),
    'commute_km':   (8.0, 17.2, 25.0, 'one-way commute km [S68; ASSUMPTION low/high]'),
    'commute_ef':   (0.0, 1.0, 1.4, 'multiplier on Destatis mode-mix EF [S33,S34]'),
    # --- PCBA ---
    'panel_m2':     (0.05, 0.06, 0.07, 'board area incl. panel waste, m2 [ASSUMPTION]'),
    'pcb_kg_m2':    (35.0, 60.0, 120.0, 'kg CO2e per m2, 4-layer PCB [S44-S47; ASSUMPTION mode]'),
    'pcb_kwh_m2':   (85.0, 110.0, 155.0, 'PCB fab kWh/m2 [S44,S49]'),
    'pcb_l_m2':     (1100.0, 1700.0, 2600.0, 'PCB fab fresh water L/m2 [S44,S49]'),
    'ic_kg':        (0.03, 0.07, 0.25, 'kg CO2e per IC incl. package [S48,S50,S51,S52]'),
    'ic_die_mm2':   (2.0, 5.0, 15.0, 'mean die area per IC, mm2 [ASSUMPTION]'),
    'fab_kwh_cm2':  (1.15, 1.6, 2.37, 'fab kWh per cm2 [S62,S63; ASSUMPTION mode]'),
    'fab_l_cm2':    (8.2, 12.0, 16.0, 'fab water withdrawal L/cm2 [S62,S63; ASSUMPTION mode]'),
    'rc_g':         (0.04, 0.15, 0.60, 'g CO2e per R/C/L [S53,S54]'),
    'disc_g':       (1.5, 9.0, 58.0, 'g CO2e per discrete [S45,S52; ASSUMPTION mass]'),
    'conn_g':       (5.0, 20.0, 50.0, 'g CO2e per connector [S55]'),
    'smt_kwh_m2':   (46.0, 46.0, 46.0 + SMT_N2_KWH_M2, 'SMT kWh/m2 [S56; ASSUMPTION N2]'),
    'smt_setup_kwh':(0.0, 2.0, 8.0, 'prototype set-up kWh [ASSUMPTION]'),
    'ci_cn':        (0.44, 0.58, 0.82, 'China grid kg CO2e/kWh [S44,S57,S58]'),
    'pack_kg':      (0.15, 0.43, 1.0, 'packaging kg CO2e [ASSUMPTION]'),
    'ship_kg':      (0.4, 0.6, 1.0, 'shipment mass kg [S44; ASSUMPTION]'),
    'air_ef':       (0.629, 0.817, 1.035, 'air kg CO2e per t-km WTW [S59,S60]'),
}
MODE = {k: v[1] for k, v in PARAMS.items()}

# ---------------------------------------------------------------------------
# 4. Model
# ---------------------------------------------------------------------------
def usd_per_mtok(mix=MIX):
    return sum(mix[k] * PRICE[k] for k in mix)

def r_list(v):
    """Realised revenue per list-price $, revenue-weighted harmonic mix."""
    return 1 / (CONSUMPTION_SHARE / v['r_cons'] + (1 - CONSUMPTION_SHARE) / v['r_subs'])

def ai_topdown(v, mix=MIX):
    """Per list-price $: (kWh, kg CO2e, L). Independent of token mix by construction."""
    kwh = COR_SHARE * v['compute_frac'] * r_list(v) / v['usd_per_kwh']
    return kwh, kwh * v['ci_ai'] * v['emb'], kwh * v['water_ai']

def bottomup_wh_per_mtok(v, mix=MIX):
    e_in = v['e_out'] * v['k_in']
    uncached_in = mix['inp'] + mix['w5'] + mix['w1h']
    return 1000 * (mix['out'] * v['e_out'] * v['m_ctx'] + uncached_in * e_in + mix['cr'] * e_in * v['k_cr'])

def ai_bottomup(v, mix=MIX):
    kwh = bottomup_wh_per_mtok(v, mix) / 1000 / usd_per_mtok(mix)
    return kwh, kwh * v['ci_ai'] * v['emb'], kwh * v['water_ai']

def work_hours(v):
    return HOURS_PER_WEEK / 5 * (WEEKDAYS_PER_YEAR - v['leave'] - v['holidays'])

def basic_share(v):
    return 1 - (v['leis_air'] + v['leis_land'] + v['leis_disc']) * HH_SHARE_OF_CONSUMPTION

def commute_ef_mix():
    tot = sum(MODE_SHARE.values())
    return sum(MODE_SHARE[m] * EF_PKM[m] for m in MODE_SHARE) / tot

def commute_per_hour(v):
    """(kg CO2e, kWh) of the commute allocated to one work hour (8-h day)."""
    tot = sum(MODE_SHARE.values())
    kwh_pkm = (MODE_SHARE['car'] * CAR_KWH_PKM
               + (MODE_SHARE['bus'] + MODE_SHARE['tram'] + MODE_SHARE['rail']) * PT_KWH_PKM) / tot
    day_km = 2 * v['commute_km'] * v['commute_avoid']
    return day_km * commute_ef_mix() / 1000 * v['commute_ef'] / 8, day_km * kwh_pkm / 8

def human(v):
    """Per work hour: view -> (kg CO2e, kWh, L)."""
    h = work_hours(v)
    fec_kwh = FEC_MTOE * 1e6 * MWH_PER_TOE * 1e3 / POP_EU
    full = (v['fp'] / h, fec_kwh / h, v['water_cap'] * 1000 / h)
    basic = tuple(x * basic_share(v) for x in full)   # same share applied to energy and water
    heat = v['office_m2'] * v['office_heat'] / h * v['office_avoid']
    elec = v['office_m2'] * v['office_el'] / h * v['office_avoid']
    com_kg, com_kwh = commute_per_hour(v)
    marg = (v['dev_kw'] * CI_DE + heat * EF_GAS + elec * CI_DE + com_kg,
            v['dev_kw'] + heat + elec + com_kwh, float('nan'))
    return {'full': full, 'basic': basic, 'marginal': marg}

def pcba(v, detail=False, fpga_per_board=0):
    """One order: (kg CO2e, kWh, L withdrawal) and optional item breakdown."""
    a = v['panel_m2']
    n_ic = BOARDS * N_IC
    die_cm2 = n_ic * v['ic_die_mm2'] / 100
    smt_kwh = v['smt_kwh_m2'] * a + v['smt_setup_kwh']
    t = v['ship_kg'] / 1000
    ic_kg = n_ic * v['ic_kg'] + BOARDS * fpga_per_board * (FPGA_KG - v['ic_kg'])
    items = {
        'bare boards':        (v['pcb_kg_m2'] * a, v['pcb_kwh_m2'] * a, v['pcb_l_m2'] * a),
        'ICs (75)':           (ic_kg, die_cm2 * v['fab_kwh_cm2'], die_cm2 * v['fab_l_cm2']),
        'R/C/L (1,275)':      (BOARDS * N_RC * v['rc_g'] / 1000, 0.0, 0.0),
        'discretes (120)':    (BOARDS * N_DISC * v['disc_g'] / 1000, 0.0, 0.0),
        'connectors (30)':    (BOARDS * N_CONN * v['conn_g'] / 1000, 0.0, 0.0),
        'SMT assembly':       (smt_kwh * v['ci_cn'], smt_kwh, 0.0),
        'packaging':          (v['pack_kg'], 0.0, 0.0),
        'express air + road': (t * (AIR_KM * v['air_ef'] + ROAD_KM * ROAD_EF), t * AIR_KM * AIR_KWH_TKM, 0.0),
    }
    tot = tuple(sum(x[i] for x in items.values()) for i in range(3))
    return (tot, items) if detail else tot

TARGETS = {
    '(a) work hour, full footprint': lambda v: human(v)['full'],
    '(a) work hour, basic living':   lambda v: human(v)['basic'],
    '(a) work hour, marginal':       lambda v: human(v)['marginal'],
    '(b) PCBA order':                lambda v: pcba(v),
}
AI = {'top-down': ai_topdown, 'bottom-up': ai_bottomup}

def breakeven_usd(v, target, ai):
    return TARGETS[target](v)[0] / AI[ai](v)[1]

# ---------------------------------------------------------------------------
# 5. Monte Carlo and tornado
# ---------------------------------------------------------------------------
def sample(rng, over):
    v = {}
    for k, (lo, c, hi, _) in PARAMS.items():
        if k in over:
            v[k] = over[k]
        elif lo == hi:
            v[k] = c
        elif lo <= 0:
            v[k] = rng.triangular(lo, hi, c)
        else:
            v[k] = math.exp(rng.triangular(math.log(lo), math.log(hi), math.log(c)))
    return v

def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(round(p / 100 * (len(xs) - 1)))))]

def run_mc(fns, n=40_000, seed=20261114, over=None):
    rng = random.Random(seed)
    out = {k: [] for k in fns}
    for _ in range(n):
        v = sample(rng, over or {})
        for k, f in fns.items():
            out[k].append(f(v))
    return {k: (pct(x, 5), pct(x, 50), pct(x, 95)) for k, x in out.items()}

def tornado(f, top=4):
    base = f(MODE)
    rows = []
    for k, (lo, c, hi, _) in PARAMS.items():
        vals = [f({**MODE, k: x}) for x in (lo, hi)]
        if min(vals) > 0 and max(vals) / min(vals) > 1.0001:
            rows.append((max(vals) / min(vals), k, vals[0] / base, vals[1] / base))
    return sorted(rows, reverse=True)[:top]

# ---------------------------------------------------------------------------
# 6. Report
# ---------------------------------------------------------------------------
def fmt(x):
    if x != x:
        return 'n/a'
    if abs(x) >= 100:
        return f'{x:,.0f}'
    return f'{x:.1f}' if abs(x) >= 10 else f'{x:.2g}'

def tri(t):
    return ' / '.join(fmt(x) for x in t)

def main():
    m = MODE
    print('== Derived inputs (mode values) ==')
    print(f'cost of revenue / revenue (9M 2026) = {COR_SHARE:.4f}; total compute / revenue = {COMPUTE_9M / REV_9M:.3f}')
    print(f'training uplift if all compute allocated per $: {COMPUTE_9M / (COR_9M * 1.00):.2f}x .. '
          f'{COMPUTE_9M / (COR_9M * m["compute_frac"]):.2f}x (mode) .. {COMPUTE_9M / (COR_9M * 0.90):.2f}x')
    print(f'r_list low/mode/high: {r_list({**m, "r_cons": 0.75, "r_subs": 0.10}):.3f} / {r_list(m):.3f} / '
          f'{r_list({**m, "r_cons": 1.0, "r_subs": 1.0}):.3f}')
    print(f'SpaceX IT MW: all-H100 {MW_ALL_H100:.0f}, Colossus-1 + GB200 mix {MW_MIX:.0f}')
    print(f'$/facility kWh low/mode/high: {USD_KWH[0]:.2f} / {USD_KWH[1]:.2f} / {USD_KWH[2]:.2f}')
    print(f'grid kg/kWh low/mode/high: {CI_AI[0]:.3f} / {CI_AI[1]:.3f} / {CI_AI[2]:.3f} '
          f'(upstream x{UPSTREAM_GRID:.3f}; open cycle lifecycle {OPEN_CYCLE:.3f})')
    print(f'e_out net of input low/mode/high: {E_OUT[0]:.2f} / {E_OUT[1]:.2f} / {E_OUT[2]:.2f} Wh per 1k')
    print(f'water L/kWh low/mode/high: {WATER["lo"]:.2f} / {WATER["c"]:.2f} / {WATER["hi"]:.2f}')
    print(f'$/MTok: measured mix {usd_per_mtok(MIX):.3f}; notes mix {usd_per_mtok(MIX_NOTES):.3f} '
          f'(ratio {usd_per_mtok(MIX_NOTES) / usd_per_mtok(MIX):.2f}x)')
    print(f'work hours/yr mode {work_hours(m):.0f}; basic share mode {basic_share(m):.3f} '
          f'(low {basic_share({**m, "leis_air": .09, "leis_land": .10, "leis_disc": .5 * .373}):.3f}, '
          f'high {basic_share({**m, "leis_air": .026, "leis_land": .05, "leis_disc": .25 * .373}):.3f})')
    print(f'commute: Destatis class mean {sum(k * w for k, w in DIST_CLASS) / sum(w for _, w in DIST_CLASS):.1f} km; '
          f'mode-mix EF {commute_ef_mix():.1f} g/pkm')

    print('\n== Mode case (all inputs at mode) ==')
    for a, f in AI.items():
        kwh, kg, l = f(m)
        print(f'AI {a}: {kwh * 1000:.1f} Wh/$, {kg * 1000:.2f} g CO2e/$, {l:.3f} L/$')
    print(f'AI bottom-up on notes mix: {ai_bottomup(m, MIX_NOTES)[0] * 1000:.1f} Wh/$; '
          f'measured mix with k_cr 0.02 / 0.20: {ai_bottomup({**m, "k_cr": .02})[0] * 1000:.1f} / '
          f'{ai_bottomup({**m, "k_cr": .2})[0] * 1000:.1f} Wh/$ (notes mix {ai_bottomup({**m, "k_cr": .02}, MIX_NOTES)[0] * 1000:.1f} / '
          f'{ai_bottomup({**m, "k_cr": .2}, MIX_NOTES)[0] * 1000:.1f})')
    for t, f in TARGETS.items():
        kg, kwh, l = f(m)
        print(f'{t:32s} {kg:7.3f} kg CO2e {kwh:7.2f} kWh {fmt(l):>5s} L')
    tot, items = pcba(m, detail=True)
    for name, (kg, kwh, l) in items.items():
        print(f'   PCBA {name:20s} {kg:6.2f} kg {kwh:6.2f} kWh {l:6.1f} L')
    print(f'   PCBA per board {tot[0] / BOARDS:.2f} kg; with one 1-cm2 FPGA-class part per board '
          f'{pcba(m, fpga_per_board=1)[0]:.1f} kg (+{pcba(m, fpga_per_board=1)[0] / tot[0] - 1:.0%})')

    # --- Monte Carlo
    fns = {}
    for a, g in AI.items():
        fns[('ai kg/$', a)] = (lambda g: lambda v: g(v)[1])(g)
        fns[('ai kWh/$', a)] = (lambda g: lambda v: g(v)[0])(g)
        fns[('ai L/$', a)] = (lambda g: lambda v: g(v)[2])(g)
    fns[('ratio bu/td', '')] = lambda v: ai_bottomup(v)[1] / ai_topdown(v)[1]
    for t, f in TARGETS.items():
        fns[('target', t)] = (lambda f: lambda v: f(v)[0])(f)
        fns[('target kWh', t)] = (lambda f: lambda v: f(v)[1])(f)
        fns[('target L', t)] = (lambda f: lambda v: f(v)[2])(f)
        for a in AI:
            fns[(t, a)] = (lambda t, a: lambda v: breakeven_usd(v, t, a))(t, a)
            fns[('e-be', t, a)] = (lambda t, a: lambda v: TARGETS[t](v)[1] / AI[a](v)[0])(t, a)
    mc = run_mc(fns)
    print('\n== Monte Carlo P5 / P50 / P95 (P50 = "central" in the report) ==')
    for a in AI:
        print(f'AI {a:9s}: g CO2e/$ {tri([x * 1000 for x in mc[("ai kg/$", a)]])}; Wh/$ '
              f'{tri([x * 1000 for x in mc[("ai kWh/$", a)]])}; L/$ {tri(mc[("ai L/$", a)])}')
    print(f'bottom-up / top-down g/$ ratio: {tri(mc[("ratio bu/td", "")])}')
    for t in TARGETS:
        print(f'{t:32s} kg {tri(mc[("target", t)])}; kWh {tri(mc[("target kWh", t)])}; L {tri(mc[("target L", t)])}')

    print('\n== ANSWER: CO2e break-even, P5 / P50 / P95 ==')
    upm = usd_per_mtok(MIX)
    for t in TARGETS:
        for a in AI:
            lo, med, hi = mc[(t, a)]
            print(f'{t:32s} {a:9s} | $ {tri((lo, med, hi)):>22s} | MTok {tri((lo / upm, med / upm, hi / upm)):>22s} '
                  f'| Pro windows {tri((lo / PRO_WINDOW_USD, med / PRO_WINDOW_USD, hi / PRO_WINDOW_USD))}')
    print(f'(MTok at the measured mix, {upm:.3f} $/MTok)')

    print('\n== Energy-based break-even $ (P5 / P50 / P95) ==')
    for t in TARGETS:
        print(f'{t:32s} ' + ' | '.join(f'{a} {tri(mc[("e-be", t, a)])}' for a in AI))

    print('\n== Decision rules: minutes of work that $10 / one Pro window must replace (P50 [P5-P95]) ==')
    for t in list(TARGETS)[:3]:
        for a in AI:
            lo, med, hi = mc[(t, a)]
            per10 = lambda usd: 600 / usd
            perw = lambda usd: PRO_WINDOW_USD / usd * 60
            print(f'{t:32s} {a:9s}: $10 -> {per10(med):.1f} min [{per10(hi):.1f}-{per10(lo):.1f}]; '
                  f'window -> {perw(med):.0f} min [{perw(hi):.0f}-{perw(lo):.0f}]')

    print('\n== Scenarios (Monte Carlo P50 with the stated inputs fixed) ==')
    scen = {
        'home office, no commute, office energy not avoided': dict(commute_avoid=0.0, office_avoid=0.0),
        'office worker, full commute and office energy avoided': dict(commute_avoid=1.0, office_avoid=1.0),
        'every token earns list price (r_cons = r_subs = 1)': dict(r_cons=1.0, r_subs=1.0),
        'inference on gas blend (ci at high value)': dict(ci_ai=CI_AI[2]),
    }
    sf = {('m', a): (lambda a: lambda v: breakeven_usd(v, '(a) work hour, marginal', a))(a) for a in AI}
    sf['kg'] = lambda v: human(v)['marginal'][0]
    sf['td'] = lambda v: ai_topdown(v)[1]
    for name, over in scen.items():
        r = run_mc(sf, n=20_000, over=over)
        print(f'{name}: marginal {r["kg"][1]:.3f} kg/h; break-even top-down ${r[("m", "top-down")][1]:.1f}, '
              f'bottom-up ${r[("m", "bottom-up")][1]:.1f}; top-down {r["td"][1] * 1000:.2f} g/$')
    r = run_mc({'p': lambda v: pcba(v, fpga_per_board=1)[0],
                'td': lambda v: pcba(v, fpga_per_board=1)[0] / ai_topdown(v)[1],
                'bu': lambda v: pcba(v, fpga_per_board=1)[0] / ai_bottomup(v)[1]}, n=20_000)
    print(f'PCBA with one 1-cm2 FPGA-class part per board: {r["p"][1]:.1f} kg; break-even top-down '
          f'${r["td"][1]:,.0f}, bottom-up ${r["bu"][1]:,.0f}')
    print(f'earlier ${SESSION_USD} session: top-down {tri([SESSION_USD * x for x in mc[("ai kg/$", "top-down")]])} kg, '
          f'bottom-up {tri([SESSION_USD * x for x in mc[("ai kg/$", "bottom-up")]])} kg CO2e')

    print('\n== Tornado (one input low->high, others at mode): ratio, factor at low .. at high ==')
    for t in ('(a) work hour, full footprint', '(a) work hour, marginal', '(b) PCBA order'):
        for a in AI:
            print(f'{t} / {a}:')
            for ratio, k, flo, fhi in tornado(lambda v: breakeven_usd(v, t, a)):
                print(f'   {k:14s} x{ratio:5.2f}  ({flo:.2f} .. {fhi:.2f})  {PARAMS[k][3]}')

    print('\n== Earlier notes reproduced ==')
    g = 2.38 / 16.29 / 3.6 * 0.40 * 1.2
    print(f'notes: {g * 1000:.1f} g/$; work hour 9000/2080 = {9000 / 2080:.2f} kg -> ${9000 / 2080 / g:.0f}')

if __name__ == '__main__':
    main()
```

## Appendix D: Output of the run used here

```text
== Derived inputs (mode values) ==
cost of revenue / revenue (9M 2026) = 0.1448; total compute / revenue = 0.566
training uplift if all compute allocated per $: 3.91x .. 4.11x (mode) .. 4.34x
r_list low/mode/high: 0.317 / 0.614 / 1.000
SpaceX IT MW: all-H100 422, Colossus-1 + GB200 mix 500
$/facility kWh low/mode/high: 1.46 / 3.76 / 5.63
grid kg/kWh low/mode/high: 0.383 / 0.401 / 0.598 (upstream x1.147; open cycle lifecycle 0.725)
e_out net of input low/mode/high: 0.40 / 0.69 / 2.30 Wh per 1k
water L/kWh low/mode/high: 0.96 / 3.50 / 5.67
$/MTok: measured mix 0.378; notes mix 1.120 (ratio 2.96x)
work hours/yr mode 1821; basic share mode 0.772 (low 0.670, high 0.852)
commute: Destatis class mean 16.4 km; mode-mix EF 118.1 g/pkm

== Mode case (all inputs at mode) ==
AI top-down: 22.5 Wh/$, 10.00 g CO2e/$, 0.079 L/$
AI bottom-up: 48.3 Wh/$, 21.50 g CO2e/$, 0.169 L/$
AI bottom-up on notes mix: 48.9 Wh/$; measured mix with k_cr 0.02 / 0.20: 32.3 / 128.3 Wh/$ (notes mix 43.9 / 73.8)
(a) work hour, full footprint      4.911 kg CO2e   12.78 kWh  78.0 L
(a) work hour, basic living        3.789 kg CO2e    9.86 kWh  60.2 L
(a) work hour, marginal            0.435 kg CO2e    1.30 kWh   n/a L
(b) PCBA order                    18.375 kg CO2e   30.29 kWh   147 L
   PCBA bare boards            3.60 kg   6.60 kWh  102.0 L
   PCBA ICs (75)               5.25 kg   6.00 kWh   45.0 L
   PCBA R/C/L (1,275)          0.19 kg   0.00 kWh    0.0 L
   PCBA discretes (120)        1.08 kg   0.00 kWh    0.0 L
   PCBA connectors (30)        0.60 kg   0.00 kWh    0.0 L
   PCBA SMT assembly           2.76 kg   4.76 kWh    0.0 L
   PCBA packaging              0.43 kg   0.00 kWh    0.0 L
   PCBA express air + road     4.46 kg  12.93 kWh    0.0 L
   PCBA per board 3.68 kg; with one 1-cm2 FPGA-class part per board 24.7 kg (+34%)

== Monte Carlo P5 / P50 / P95 (P50 = "central" in the report) ==
AI top-down : g CO2e/$ 7.6 / 13.5 / 25.4; Wh/$ 15.2 / 26.4 / 48.6; L/$ 0.03 / 0.072 / 0.16
AI bottom-up: g CO2e/$ 15.7 / 34.9 / 88.3; Wh/$ 31.5 / 68.2 / 168; L/$ 0.066 / 0.19 / 0.53
bottom-up / top-down g/$ ratio: 0.98 / 2.6 / 7.4
(a) work hour, full footprint    kg 4.6 / 5 / 5.5; kWh 12.6 / 12.8 / 13.0; L 53.5 / 71.1 / 86.3
(a) work hour, basic living      kg 3.5 / 3.9 / 4.3; kWh 9.4 / 9.9 / 10.4; L 41.2 / 55.0 / 67.2
(a) work hour, marginal          kg 0.16 / 0.37 / 0.69; kWh 0.61 / 1.3 / 2.2; L n/a / n/a / n/a
(b) PCBA order                   kg 16.5 / 21.3 / 28.9; kWh 27.1 / 33.6 / 42.3; L 110 / 150 / 208

== ANSWER: CO2e break-even, P5 / P50 / P95 ==
(a) work hour, full footprint    top-down  | $        196 / 369 / 663 | MTok      518 / 975 / 1,751 | Pro windows 3 / 5.6 / 10.0
(a) work hour, full footprint    bottom-up | $       56.2 / 143 / 319 | MTok        149 / 377 / 842 | Pro windows 0.85 / 2.2 / 4.8
(a) work hour, basic living      top-down  | $        151 / 285 / 514 | MTok      399 / 754 / 1,358 | Pro windows 2.3 / 4.3 / 7.8
(a) work hour, basic living      bottom-up | $       43.3 / 110 / 247 | MTok        114 / 292 / 652 | Pro windows 0.66 / 1.7 / 3.7
(a) work hour, marginal          top-down  | $      9.7 / 26.9 / 64.7 | MTok      25.6 / 71.0 / 171 | Pro windows 0.15 / 0.41 / 0.98
(a) work hour, marginal          bottom-up | $      3.1 / 10.3 / 29.2 | MTok      8.2 / 27.2 / 77.2 | Pro windows 0.047 / 0.16 / 0.44
(b) PCBA order                   top-down  | $    800 / 1,582 / 3,015 | MTok  2,114 / 4,181 / 7,967 | Pro windows 12.1 / 24.0 / 45.7
(b) PCBA order                   bottom-up | $      234 / 611 / 1,430 | MTok    618 / 1,615 / 3,778 | Pro windows 3.5 / 9.3 / 21.7
(MTok at the measured mix, 0.378 $/MTok)

== Energy-based break-even $ (P5 / P50 / P95) ==
(a) work hour, full footprint    top-down 262 / 483 / 839 | bottom-up 75.8 / 187 / 405
(a) work hour, basic living      top-down 203 / 374 / 651 | bottom-up 58.5 / 145 / 314
(a) work hour, marginal          top-down 18.6 / 46.8 / 105 | bottom-up 5.8 / 18.0 / 48.2
(b) PCBA order                   top-down 667 / 1,276 / 2,305 | bottom-up 196 / 493 / 1,102

== Decision rules: minutes of work that $10 / one Pro window must replace (P50 [P5-P95]) ==
(a) work hour, full footprint    top-down : $10 -> 1.6 min [0.9-3.1]; window -> 11 min [6-20]
(a) work hour, full footprint    bottom-up: $10 -> 4.2 min [1.9-10.7]; window -> 28 min [12-70]
(a) work hour, basic living      top-down : $10 -> 2.1 min [1.2-4.0]; window -> 14 min [8-26]
(a) work hour, basic living      bottom-up: $10 -> 5.4 min [2.4-13.9]; window -> 36 min [16-91]
(a) work hour, marginal          top-down : $10 -> 22.3 min [9.3-62.0]; window -> 147 min [61-409]
(a) work hour, marginal          bottom-up: $10 -> 58.2 min [20.5-193.1]; window -> 384 min [135-1275]

== Scenarios (Monte Carlo P50 with the stated inputs fixed) ==
home office, no commute, office energy not avoided: marginal 0.014 kg/h; break-even top-down $1.1, bottom-up $0.4; top-down 13.56 g/$
office worker, full commute and office energy avoided: marginal 0.835 kg/h; break-even top-down $60.3, bottom-up $23.5; top-down 13.56 g/$
every token earns list price (r_cons = r_subs = 1): marginal 0.371 kg/h; break-even top-down $16.5, bottom-up $10.3; top-down 21.64 g/$
inference on gas blend (ci at high value): marginal 0.369 kg/h; break-even top-down $20.0, bottom-up $7.8; top-down 17.92 g/$
PCBA with one 1-cm2 FPGA-class part per board: 27.5 kg; break-even top-down $2,043, bottom-up $792
earlier $229.58 session: top-down 1.7 / 3.1 / 5.8 kg, bottom-up 3.6 / 8 / 20.3 kg CO2e

== Tornado (one input low->high, others at mode): ratio, factor at low .. at high ==
(a) work hour, full footprint / top-down:
   usd_per_kwh    x 3.84  (0.39 .. 1.50)  $ of compute per facility kWh [S4,S5,S6; ASSUMPTION]
   r_subs         x 2.66  (1.86 .. 0.70)  realised/list on subscriptions [ASSUMPTION]
   ci_ai          x 1.56  (1.05 .. 0.67)  grid kg CO2e/kWh [S12,S14,S35,S67; ASSUMPTION]
   fp             x 1.29  (0.90 .. 1.16)  kg CO2e per capita per year [S21; ASSUMPTION low]
(a) work hour, full footprint / bottom-up:
   e_out          x 5.75  (1.72 .. 0.30)  Wh per 1k output tokens net of input [S7,S9,S11]
   k_cr           x 3.97  (1.50 .. 0.38)  cache-read / uncached input token energy [S3; ASSUMPTION]
   k_in           x 2.89  (1.63 .. 0.56)  uncached input / output token energy [S10,S11]
   ci_ai          x 1.56  (1.05 .. 0.67)  grid kg CO2e/kWh [S12,S14,S35,S67; ASSUMPTION]
(a) work hour, marginal / top-down:
   usd_per_kwh    x 3.84  (0.39 .. 1.50)  $ of compute per facility kWh [S4,S5,S6; ASSUMPTION]
   commute_avoid  x 3.81  (0.42 .. 1.58)  share of average commute avoided [ASSUMPTION]
   office_avoid   x 3.53  (0.61 .. 2.16)  share of office energy avoided [ASSUMPTION]
   commute_ef     x 2.97  (0.42 .. 1.23)  multiplier on Destatis mode-mix EF [S33,S34]
(a) work hour, marginal / bottom-up:
   e_out          x 5.75  (1.72 .. 0.30)  Wh per 1k output tokens net of input [S7,S9,S11]
   k_cr           x 3.97  (1.50 .. 0.38)  cache-read / uncached input token energy [S3; ASSUMPTION]
   commute_avoid  x 3.81  (0.42 .. 1.58)  share of average commute avoided [ASSUMPTION]
   office_avoid   x 3.53  (0.61 .. 2.16)  share of office energy avoided [ASSUMPTION]
(b) PCBA order / top-down:
   usd_per_kwh    x 3.84  (0.39 .. 1.50)  $ of compute per facility kWh [S4,S5,S6; ASSUMPTION]
   r_subs         x 2.66  (1.86 .. 0.70)  realised/list on subscriptions [ASSUMPTION]
   ic_kg          x 2.07  (0.84 .. 1.73)  kg CO2e per IC incl. package [S48,S50,S51,S52]
   ci_ai          x 1.56  (1.05 .. 0.67)  grid kg CO2e/kWh [S12,S14,S35,S67; ASSUMPTION]
(b) PCBA order / bottom-up:
   e_out          x 5.75  (1.72 .. 0.30)  Wh per 1k output tokens net of input [S7,S9,S11]
   k_cr           x 3.97  (1.50 .. 0.38)  cache-read / uncached input token energy [S3; ASSUMPTION]
   k_in           x 2.89  (1.63 .. 0.56)  uncached input / output token energy [S10,S11]
   ic_kg          x 2.07  (0.84 .. 1.73)  kg CO2e per IC incl. package [S48,S50,S51,S52]

== Earlier notes reproduced ==
notes: 19.5 g/$; work hour 9000/2080 = 4.33 kg -> $222
```
