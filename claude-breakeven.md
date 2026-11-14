# Claude Code break-even: one work hour and one PCBA order

*Decision aid, 2026-11-14. Claude Opus 5.5 in Claude Code at API list prices. Inference only, no training. Every figure comes from the script in the appendix (`claude-breakeven.py`), using the inputs in section 3 and the sources in section 5. "Low / central / high" means: central uses every input at its central value; low and high are the 5th and 95th percentiles of a Monte Carlo run over all inputs. The tag "ASSUMPTION" marks inputs that no source states.*

**Two AI results.** The Anthropic S-1 discloses no energy, emissions or water figures [S1, S2], so there are two independent ways to estimate the AI footprint, and both are reported:
- **Top-down (financial).** This estimates how much compute Anthropic buys per list-price dollar of usage, then converts that compute spend into kWh. Central: **22 Wh, 10 g CO2e and 0.08 L per list-price $.**
- **Bottom-up (per token).** This applies published per-token energy measurements of large models to the Claude Code token mix. Central: **66 Wh, 30 g CO2e and 0.23 L per $.**

The two estimates differ by 2.9×. That gap is the biggest single uncertainty in this document.

## 1. Answer: break-even for CO2e

| Equivalent of… | Footprint (central) | AI estimate | $ list price (low / central / high) | Million tokens* (low / central / high) | Pro 5-h windows at $66 (low / central / high) |
|---|---|---|---|---|---|
| (a) 1 work hour, full footprint | 4.9 kg | top-down | 262 / **483** / 786 | 216 / **399** / 650 | 4.0 / **7.3** / 11.9 |
| | | bottom-up | 58 / **164** / 242 | 48 / **136** / 200 | 0.87 / **2.5** / 3.7 |
| (a) 1 work hour, basic living only | 3.8 kg | top-down | 198 / **372** / 602 | 164 / **308** / 498 | 3.0 / **5.6** / 9.1 |
| | | bottom-up | 44 / **126** / 185 | 36 / **105** / 153 | 0.66 / **1.9** / 2.8 |
| (a) 1 work hour, marginal (what is actually avoided) | 0.43 kg | top-down | 13 / **42** / 77 | 10 / **35** / 63 | 0.19 / **0.64** / 1.2 |
| | | bottom-up | 3.0 / **14** / 23 | 2.5 / **12** / 19 | 0.05 / **0.22** / 0.35 |
| (b) 1 PCBA order (5 boards) | 18.5 kg | top-down | 1,079 / **1,819** / 3,659 | 891 / **1,504** / 3,024 | 16 / **28** / 55 |
| | | bottom-up | 242 / **618** / 1,118 | 200 / **511** / 924 | 3.7 / **9.4** / 17 |

\*Tokens are counted with the notes' token mix, which costs $1.21 per million tokens. This session's measured Claude Code mix (97.6% cache reads, 0.4% output) costs only $0.378 per million tokens. On that mix every token count is 3.20× higher: a full work hour is 1,277M tokens (top-down) or 434M (bottom-up), and the PCBA order is 4,808M or 1,634M. The dollar and window columns do not depend on the mix.

**What each target contains**
- **Full footprint.** The EU average consumption footprint (8.94 t CO2e per person in 2024), spread over 1,821 working hours a year.
- **Basic living.** The same footprint without leisure: holidays and air travel, leisure driving, restaurants, recreation and discretionary goods. It is 77% of the total (range 67–86%).
- **Marginal.** Only what one hour less work avoids: the workstation (30 W), 25% of the hour's share of office heat and electricity, and 50% of an average German commute (17.2 km one way, mode mix 118 g/pkm).
- **PCBA order.** 3.6 kg bare boards, 5.3 kg ICs, 1.9 kg passives, discretes and connectors, 2.8 kg assembly, 0.4 kg packaging and 4.6 kg express air. The Monte Carlo range is 16.7–29.5 kg.

**Energy and water at the CO2e break-even** (central)
- **Full work hour:** the AI uses 10.8 kWh and 38 L. The human hour uses 12.8 kWh of final energy and 78 L of blue water.
- **PCBA order:** the AI uses 41 kWh and 142 L. The order uses 30 kWh and 147 L, but that water is fab withdrawal, so it does not compare directly with the AI's consumption.
- **On an energy basis** the break-evens are $572 / $195 for the full work hour (top-down / bottom-up), $57 / $19 for the marginal hour and $1,357 / $461 for the PCBA order.

**Your earlier $229.58 session:** 2.3 kg CO2e top-down or 6.9 kg bottom-up. The notes said 4.5 kg.

## 2. Decision rules

1. **For your own choices, use the marginal row.** You keep living, eating and heating whether or not Claude does the work. By this measure, Claude has the smaller footprint only when:
   - top-down: **$10 of Claude replaces at least 14 minutes of your work** (range 8–48 min), or one Pro window ($66) replaces at least 94 min (52–315 min);
   - bottom-up: $10 replaces at least 42 minutes (26–201 min), or one window replaces at least 275 min (173–1,324 min).
2. **If you work from home and don't commute, footprint is no reason to use Claude.** The avoided footprint is then only the computer's power: 0.012 kg per hour, which equals $1.2 of Claude (top-down) or $0.4 (bottom-up). Justify that use by its value, not by CO2. **For an office worker who would avoid the full average commute and office energy** (1.2 kg per hour), break-even rises to $116 per hour (top-down) or $39 (bottom-up).
3. **Accounting view (full or basic footprint per hour):** this suits productivity comparisons such as "a person-hour versus AI for this deliverable". Claude has the smaller footprint when $10 replaces at least 1.2 min of work (0.8–2.3 min) top-down, or 3.7 min (2.5–10 min) bottom-up. A Pro window must replace 8–24 min of work, or 11–31 min on the basic-living footprint.
4. **PCBA: an avoided prototype re-spin is worth 9–28 Pro windows.** A Claude session that prevents one re-spin, for example through schematic review, checks of footprints and the bill of materials, or simulation, has the smaller footprint:
   - always, up to 3.7 windows ($242) of use;
   - in the central case, up to 9.4 windows (bottom-up) or 28 windows (top-down);
   - never beyond 55 windows ($3,659).
5. **The $ counter (or your window %) is a fair proxy for footprint.** Footprint per $ is similar whether the spend goes to cache reads or to output: 66 Wh per $ on the notes' mix and 70 Wh per $ on the measured mix (bottom-up). The way to cut AI footprint is to cut spend, for example on aimless agent loops, unnecessary subagents and repeated re-reads of large contexts.

**When the conclusion flips**
- **Bottom-up instead of top-down:** the AI footprint per $ is 2.9× larger, so every threshold above is 2.9× stricter.
- **Realised revenue per list $ (r):** if every token earned the full list price (r = 1), the top-down AI footprint rises from 10.2 to 16.7 g per $, and the marginal break-even falls from $42 to $26.
- **Gas-fired inference:** SpaceX's Colossus runs on gas turbines [S4], and Anthropic's own planned sites use on-site gas [S2]. If inference ran on dedicated gas generation (0.55 kg/kWh), the AI footprint would be 13.6 g per $ and the marginal break-even $32.
- **Marginal view:** whether saved hours really mean fewer commuting days or less office space swings the result by up to 3.9× (see the tornado in the appendix output).
- **PCBA:** an FPGA, large BGAs or advanced-node chips (0.5–1.5 kg per IC) would make the order several times larger and the case for avoiding a re-spin stronger.

**The 2–3 inputs that cause most of the spread** (tornado: ratio of the result with the input at high vs at low)
- **Top-down:** realised revenue per list $ (×3.1), then $ of compute per kWh (×2.7), then grid intensity (×1.6).
- **Bottom-up:** energy per output token (×6.0), then the long-context multiplier (×1.9).
- **Marginal target:** commute and office-energy avoidance (×3.9 and ×3.5).
- **PCBA:** per-IC footprint (×2.1).

## 3. Assumptions

Notes' values are given only where this document differs. "Derived" means calculated from the cited sources.

| Input | Low / central / high | Basis | Notes had |
|---|---|---|---|
| **AI, top-down** | | | |
| Cost of revenue / revenue | 0.1448 | $4,812M / $33,242M, nine months 2026 [S1] | 0.146 (H1) |
| Compute share of cost of revenue | 0.90 / 0.95 / 1.00 | ASSUMPTION: "Substantially all … compute and infrastructure", but also includes some personnel and overhead [S1] | 1.0 |
| r = realised revenue per list-price $ | 0.32 / 0.61 / 1.00 | ASSUMPTION. Consumption revenue is 79%, metered per token and booked gross even via clouds; subscriptions are 21% [S1]. Consumption is taken at r 0.75–1.0, subscriptions at 0.1–1.0 because usage can exceed the fee | 1.0 (implicit) |
| $ of compute per facility kWh | 2.06 / 3.76 / 5.63 | Derived. **High:** SpaceX $1.25B/month for ~325k GPUs [S4]; nameplate IT power 422–650 MW (130 MW/100k H100, 210 MW/110k GB200 [S4]; Colossus 1 >300 MW/220k GPUs [S5]); ASSUMPTION utilisation 0.6–0.7 and PUE 1.2–1.3 (industry average 1.52 [S64]). Nameplate excludes cooling [S4]. **Low:** owner's cost at $50B/GW [S6], ASSUMPTION 5-year life, 75% utilisation, ×1.3 for opex and financing, +$0.08/kWh electricity | 1.7 / 3.6 / 7.6, from mixing $1.25B with 300 MW |
| **AI, bottom-up** | | | |
| Wh per 1k output tokens, incl. PUE | 0.5 / 1.0 / 3.0 | Epoch ≈0.6 [S11]; Oviedo 0.31 Wh per query of ~300 output tokens [S7]; Jegham ≈3 for Claude 3.7 Sonnet [S9] | 0.34 Wh (Altman's figure, misattributed to [S7]) |
| Long-context decode multiplier | 1 / 1.5 / 3 | ASSUMPTION: Claude Code contexts of 50–200k tokens make each output token costlier than in 500-token benchmarks | — |
| Uncached input token / output token energy | 0.15 / 0.30 / 0.60 | About ¼ in a measured test [S10]; 0.4–0.7 at 10k context (derived from [S11]) | — |
| Cache-read token / uncached input energy | 0.02 / 0.05 / 0.20 | ASSUMPTION: central equals the price ratio [S3]; no measurement found | — |
| **AI, both methods** | | | |
| Grid intensity, kg CO2e/kWh | 0.35 / 0.41 / 0.55 | US eGRID 0.350 direct [S12]; +~15% upstream (gas 486 lifecycle vs 389 combustion [S14]); high includes on-site gas [S2, S4]: combined cycle 0.49 [S13], open cycle ~0.65 (derived [S67]) | 0.35 / 0.40 / 0.45 |
| Embodied hardware uplift | 1.05 / 1.11 / 1.25 | ~10% embodied [S15]; baseboard alone ~2–3% (derived [S16]); manufacturing <25% [S15] | 1.1 / 1.2 / 1.3 |
| Water, L/kWh (on-site + generation) | 1.0 / 3.5 / 5.7 | Low: on-site 0.18 [S9] + gas combined cycle 0.78 [S19]. Central: 0.36 [S17] + 3.14 [S18]. High: 1.15 [S8] + 4.52 [S17] | 1.5 / 2.5 / 4.0 |
| Prices, $/MTok | 4 in, 5 (5-min write), 8 (1-h write), 0.20 cache read, 20 out | Opus 5.5 [S3] | no 1-h write |
| Share of cache writes at the 1-h price | 0 / 0.5 / 1 | ASSUMPTION: on a subscription the main conversation uses a 1-h cache and subagents 5 min [S20] | 0 |
| Token mix | 90 / 6 / 1 / 3% (cache read / write / input / output) → $1.21/MTok | Notes (unsourced). Measured in this session: 97.6 / 2.0 / 0.0 / 0.4% → $0.378/MTok, from 99.3M tokens in local transcripts | $1.12 |
| Pro window | $66 | User's measurement | $71 or $7.40 |
| **Human** | | | |
| Footprint, kg CO2e per person per year | 8,048 / 8,942 / 10,404 | EU 2024 and Germany 2024 [S21]. Low: ASSUMPTION −10% model uncertainty | 9,000 (2023) |
| Work hours per year | 1,767 / 1,821 / 1,871 | 40 h/week × (260.9 weekdays − leave − holidays). Leave 20 days (minimum [S32]) / 24.3 (EU average) / 30 (Germany) [S31]. Holidays 7 / 9.0 / 10 (EU average 9.0 [S31]; Berlin 10, some fall on weekends). Cross-check: EU collectively agreed time is 1,726 h at 38.1 h/week [S31] | 2,080 |
| Basic-living share of the footprint | 0.67 / 0.77 / 0.86 | Derived. Leisure share of the household footprint: air travel 3/5/9%, leisure land travel 5/8/10%, restaurants, recreation and discretionary goods 8/13/19% [S23–S29]. Government consumption counts as basic; capital formation is split pro rata [S22]. Cross-check against UBA's split: 71–78% [S27] | — |
| Final energy, MWh per person per year | 23.27 | 900.41 Mtoe / 450.05M people [S30] | 23.3 |
| Blue water footprint, m³ per person per year | 85 / 142 / 170 | Germany 85.1; EU-27 142 (population-weighted, derived) [S43]. High: ASSUMPTION +20% | — |
| Workstation power in use, kW | 0.015 / 0.030 / 0.100 | Idle notebook 4.9 W, 24" display 12.9 W, idle desktop 10.5 W [S37]. ASSUMPTION: extra power in active use | — |
| Office area per employee, m² | 10 / 20.9 / 30.9 | Legal minimum 8 m² + 6 m² per extra desk [S38]; European cities 20.88 [S39, secondary]; German stock 395M m² / 12.8M employees [S40] | — |
| Office heat / electricity, kWh/m²·a | heat 57 / 133 / 140; electricity 25.5 / 60 / 60 | Benchmark values [S41]; stock averages [S40, S42] | — |
| Share of office energy avoided per hour not worked | 0 / 0.25 / 1 | ASSUMPTION: fixed in the short run; office space follows hours in the long run | — |
| Share of commute avoided per hour not worked | 0 / 0.5 / 1 | ASSUMPTION: avoided only when saved hours turn into fewer office days | — |
| One-way commute, km | 8 / 17.2 / 25 | Germany 2024 average 17.2 km [S68]; Destatis distance classes give 16.4 (derived; ≥50 km taken as 60 km) [S33]. Low and high: ASSUMPTION | — |
| Commute emissions | 0 / 1 / 1.4 × 118 g CO2e/pkm | Destatis mode mix for employees [S33] × UBA emission factors (car 164, bus 90, rail 44, tram 42) [S34]; 1.4 ≈ car only | — |
| Emission factors, Germany | electricity 0.414, gas heat 0.242 kg CO2e/kWh | Both including upstream [S35, S36] | — |
| Commute energy, kWh per pkm | car 0.45, public transport 0.15 | ASSUMPTION: about 7 L/100 km at 1.4 occupants | — |
| **PCBA** | | | |
| Board make-up | 5 boards × (15 ICs, 255 R/C/L, 24 discretes, 6 connectors) | ASSUMPTION: a typical mixed-signal prototype | 300 parts incl. 15 ICs |
| Board area incl. panel waste, m² | 0.05 / 0.06 / 0.07 | ASSUMPTION: 5 × 100 cm² plus rails | 0.07 |
| 4-layer PCB, kg CO2e/m² | 35 / 60 / 160 | 4-layer LCA 34.8 [S46]; 6-layer 2011 value ~72 [S45]; 10-layer 179 [S44], which scales to ~72 for 4 layers at that report's ~0.82 kg/kWh grid factor or ~40 at Hubei's official 0.40 (derived); a high-layer-count maker's Scope 1+2 alone is 85 [S47]; ~160 including assembly [S48]. Central: ASSUMPTION, between these values | 25 / 50 / 100 |
| PCB fab energy, kWh/m² | 85 / 110 / 155 | Chinese clean-production standard for 4 layers: grade 1 ≤85, grade 3 ≤135, +15% for prototypes [S49]; 118 for 10 layers [S44] | — |
| PCB fab water, L/m² (withdrawal) | 1,100 / 1,700 / 2,600 | [S49]; 1,140 for 10 layers [S44] | — |
| Per IC, kg CO2e | 0.03 / 0.07 / 0.25 | Die 1–20 mm² × 0.0118 kg/mm² at 28 nm [S50] + package 0.01–0.15 [S51]; MCU 0.08–0.29 [S48]; small IC 0.058 [S52] | 0.04 / 0.10 / 0.5 |
| Mean die area per IC, mm² | 2 / 5 / 15 | ASSUMPTION: mostly small analog and MCU dies | — |
| Fab energy, kWh/cm² / fab water withdrawal, L/cm² | 1.15 / 1.6 / 2.37; 8.2 / 12 / 16 | 28-company average [S62]; GlobalFoundries (derived) [S63] | — |
| Per R/C/L, g CO2e | 0.04 / 0.15 / 0.60 | 0402 resistor 0.040, 0603 capacitor 0.611 [S54]; 0402 MLCC 0.145 [S53] | 1.5 / 4 / 10 (all non-IC parts) |
| Per discrete, g CO2e | 1.5 / 9 / 58 | 167 kg/kg [S45] × ~9 mg (ASSUMPTION mass); small IC package 58 g [S52]; central is the geometric mean | (included above) |
| Per connector, g CO2e | 5 / 20 / 50 | Weidmüller product declarations: 6.3, 18.6 and 46.1 g [S55] | (included above) |
| SMT assembly, kWh/m² | 46 / 46 / 66 | 46 kWh/m² [S56]; high adds nitrogen production (64 kg/m² [S56] × ASSUMPTION 0.3 kWh/kg) | — |
| Prototype set-up, kWh | 0 / 2 / 8 | ASSUMPTION: a pooled line versus a dedicated reflow warm-up | — |
| China grid, kg CO2e/kWh | 0.44 / 0.58 / 0.82 | Guangdong 2023, CO2 only [S57]; national lifecycle 2024 [S58]; implied by [S44] | (in 3–10 kg) |
| Packaging, kg CO2e | 0.15 / 0.43 / 1.0 | ASSUMPTION: 0.10–0.25 kg of carton and foam × 1.5–4 kg CO2e/kg | 0.3 / 0.5 / 1.0 |
| Shipment mass, kg | 0.4 / 0.6 / 1.0 | ASSUMPTION: boards ~33 g each at 3.3–3.6 kg/m² [S44, S45] plus parts and packaging | 1.0 |
| Express air, kg CO2e/t·km (well-to-wheel) | 0.629 / 0.838 / 1.035 | Long-haul freighter [S60]; DHL reference [S61, secondary]; DESNZ with radiative forcing + well-to-tank [S59] | 0.65–0.8 (×2 high) |
| Distance | 8,855 km air + 340 km road | Great-circle Hong Kong–Leipzig (derived); road at 0.6 kg/t·km (ASSUMPTION; <1% of the total) | 9,100 km |
| Air freight energy, kWh/t·km | 2.43 | Derived: 0.646 kg/t·km tank-to-wheel [S60] ÷ 3.16 kg CO2 per kg fuel × 11.9 kWh/kg (ASSUMPTION: standard fuel factors) | — |

## 4. Caveats

- **The AI numbers are estimates, not measurements.** Anthropic publishes no energy or emissions figures [S1, S2]. The top-down and bottom-up methods disagree by 2.9×. Bottom-up per-token data are modelled from H100-era benchmarks of other models [S7, S9]. For long agentic queries, Oviedo et al. give 3.91 Wh per ~5,000 output tokens, about 0.8 Wh per 1k (derived), which is inside the range used [S7]. Top-down relies on an undisclosed revenue ratio (r) and on rental prices that pay for reserved capacity, not for energy [S4].
- **Grid intensity is location-based.** Renewable-energy purchases are ignored. Inference may run "in any available geography" [S20] (Claude data-residency docs), not only in the US.
- **Training is excluded,** as defined. Total compute is 56.6% of revenue, against 14.5% for cost of revenue [S1]. Allocating all of it per $ would raise the top-down AI footprint by up to 3.9×.
- **The full footprint is an accounting allocation, not an avoided emission.** It applies only if Claude lets less human time be needed in total. Time you save and spend on something else carries a rebound.
- **Basic-living shares** come from studies with data years 2007–2010 [S23–S25], cross-checked against UBA 2026 [S27]. The split between leisure and basic is a judgement.
- **Water is not like-for-like.** AI water is consumption (evaporation on site and at power plants). Human water is the blue water footprint from 1996–2005 [S43]. PCBA water is fab withdrawal, most of which is returned. The marginal hour's water use is not estimated.
- **PCBA results depend on the bill of materials.** IC data come from logic nodes [S50, S51]. Passive-part data come from one LCA of an MLCC [S53, S54]. Connector factors come from one manufacturer [S55]. Express parcels may be allocated by volume rather than weight, which would raise the freight share. Sanity check: a Raspberry Pi 4/5 is 6.5 kg CO2e including shipping and disposal [S66], about 3.7 kg per board here.
- **Windows** use your measured $66 Pro window, and the conversion is linear: rescale by 66 / your value. Plan accounting may not weight token types at list-price ratios.
- **The Monte Carlo treats inputs as independent.** P5 and P95 show spread; they are not confidence intervals.

**Where this differs from the earlier notes, and why**
1. **The notes' $/kWh was built on a mismatch.** The $1.25B/month buys about 325k GPUs across Colossus and Colossus II [S4], not 300 MW of Colossus 1 [S5]. The megawatt figures are nameplate IT power without cooling [S4].
2. **List price ≠ revenue.** 21% of revenue is subscriptions [S1], so the footprint per list $ is lower: r = 0.61.
3. **Updated human inputs.** The footprint is now 8.94 t for 2024, not 9.0 t for 2023 [S21]. Hours are 1,821 instead of 2,080, because leave and holidays are counted [S31].
4. **Oviedo et al. report 0.31 Wh per query** [S7]. The 0.34 Wh in the notes is Sam Altman's blog figure.
5. **The PCBA total is 18.5 kg instead of ~30.**
   - Passives and other parts are 1.9 kg instead of 5.7, because measured per-part LCAs are 10–100× below the notes' values [S53–S55].
   - Air freight is 4.6 kg instead of 7.3, from a lighter shipment and verified freight factors.
   - SMT assembly is 2.8 kg instead of 5.0 [S56].
   - Bare boards are 3.6 kg instead of 3.5: a higher kg/m² on a smaller panel area.
6. **Net effect:** one work hour (full footprint) is **$483** top-down / **$164** bottom-up, against the notes' $222. The notes' marginal view was not quantified; here it is $42 / $14. The PCBA order is $1,819 / $618, against the notes' $1,513.

## 5. Sources

All were read on 2026-11-14 by a research agent, which opened each one and found the quoted figure. Key figures were independently re-checked by a second agent: [S1–S8], [S9], [S12–S15], [S17], [S18], [S21], [S22], [S30–S35], [S41], [S44], [S45], [S50], [S51], [S53], [S56–S59] and [S66]. The re-check corrected [S31] and [S58] and the labels of [S33]. "Secondary" marks news, blogs and mirrors. Status is VERIFIED unless stated otherwise.

- [S1] Anthropic, PBC, *Form S-1/A, Amendment No. 2*. SEC EDGAR, 2026-11-10. https://www.sec.gov/Archives/edgar/data/2130357/000162828026072484/anthropicpbc-sx1ax2.htm
  - Nine months to 30 Sep 2026: revenue $33,242M; cost of revenue $4,812M.
  - "Substantially all of cost of revenue consists of compute and infrastructure costs associated with customer-serving workloads."
  - Consumption-based revenue $26.3B (79%); subscription $6.9B (21%). Cloud-partner revenue is recognised "on a gross basis".
  - Q3 2026: compute $9,863M against revenue $16,956M ("58%"). Nine-month compute and infrastructure $18,808M.
- [S2] Anthropic, PBC, *Form S-1*. SEC EDGAR, 2026-10-26. https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm
  - H1 2026 revenue $16,286M; cost of revenue $2,380M.
  - No MW, GW, energy, emissions or water figures.
  - "certain of our planned data center facilities rely on dedicated on-site natural gas-fired generation".
- [S3] Anthropic, *Pricing*, Claude Platform Docs (undated). https://platform.claude.com/docs/en/about-claude/pricing
  - Opus 5.5: "$4 / MTok | $20 / MTok | $5 / MTok | $8 / MTok | $0.20 / MTok" (input, output, 5-minute write, 1-hour write, cache read).
- [S4] Space Exploration Technologies Corp., *Form S-1/A*. SEC EDGAR, 2026-06-03. https://www.sec.gov/Archives/edgar/data/1181412/000162828026040364/spaceexplorationtechnologib.htm
  - "approximately 325,000 NVIDIA GPUs … $1.25 billion per month through May 2029".
  - "approximately 100,000 H100 … approximately 130 megawatts"; "approximately 110,000 GB200 … approximately 210 megawatts"; "110,000 GB300 … 220 megawatts".
  - Nameplate Compute Draw "does not include power … such as cooling systems".
  - "We currently rely significantly on natural gas and gas turbine technology".
- [S5] Anthropic, *Higher usage limits and a SpaceX compute deal*, 2026-05-06. https://www.anthropic.com/news/higher-limits-spacex
  - "more than 300 megawatts of new capacity (over 220,000 NVIDIA GPUs)".
- [S6] M. Mantel, *Anthropic wants over 3.5 gigawatts of computing capacity with Google's TPUs*, heise online, 2026-04-07. https://heise.de/-11247457
  - "around 35 billion to 50 billion US dollars" per GW.
  - Secondary; the estimate is unattributed.
- [S7] Oviedo et al. (Microsoft), *Energy Use of AI Inference, Efficiency Pathways, and Test-Time Scaling*, arXiv:2509.20241 (v1 2025-09-24, v2 2026-06-09; Joule 2026, doi:10.1016/j.joule.2026.102430). https://arxiv.org/abs/2509.20241
  - "median energy of 0.31 Wh/query (IQR 0.16–0.60)" for models over 200B parameters on H100, with a median of 300 output tokens and 500 input tokens.
  - Long reasoning queries: "3.91 Wh" for a median of 5,000 output tokens.
  - This is a modelled estimate, not a measurement.
- [S8] Elsworth et al. (Google), *Measuring the environmental impact of delivering AI at Google scale*, arXiv:2508.15734, Aug 2025. https://arxiv.org/abs/2508.15734
  - 0.24 Wh per median Gemini Apps text prompt.
  - "WUE … 1.15 L/kWh"; fleet PUE 1.09.
- [S9] Jegham et al., *How Hungry is AI?*, arXiv:2505.09598v6, 2025-11-24. https://arxiv.org/abs/2505.09598
  - Claude-3.7 Sonnet: 0.950 Wh (100 tokens in / 300 out) and 2.989 Wh (1k in / 1k out); AWS on-site WUE 0.18 L/kWh.
  - This is a model-based estimate, not a measurement.
- [S10] Caravaca et al., *From Prompts to Power*, arXiv:2511.05597, 2025-11-05. https://arxiv.org/abs/2511.05597
  - opt-30b: 900 in / 100 out = 0.08 Wh; 100 in / 900 out = 0.3 Wh.
- [S11] J. You, *How much energy does ChatGPT use?*, Epoch AI, 2025-02-07. https://epoch.ai/gradient-updates/how-much-energy-does-chatgpt-use
  - "roughly 0.3 watt-hours" for 500 output tokens; about 2.5 Wh with a 10k-token input.
  - Secondary.
- [S12] US EPA, *eGRID2023 rev2 summary data*, 2025-06-12. https://www.epa.gov/egrid/summary-data
  - US total output emission rate 770.884 lb CO2e/MWh (350 g/kWh); SRTV 903.306.
- [S13] IPCC, *AR5 WGIII Annex III*, Table A.III.2, 2014. https://www.ipcc.ch/report/ar5/wg3/
  - Natural gas combined cycle, lifecycle median 490 gCO2e/kWh.
- [S14] NREL, *Life Cycle Greenhouse Gas Emissions from Electricity Generation: Update*, NREL/FS-6A50-80580, Sep 2021. https://www.nrel.gov/docs/fy21osti/80580.pdf
  - Natural gas: 486 g CO2e/kWh total, of which 389 g is combustion.
- [S15] Schneider et al. (Google), *Life-cycle emissions of AI hardware*, arXiv:2502.01671, 2025-02-01. https://arxiv.org/abs/2502.01671
  - "embodied emissions are ∼10% and operational emissions are ∼90%"; "manufacturing emissions under 25%".
- [S16] NVIDIA, *HGX H100 Product Carbon Footprint Summary*, Aug 2025.
  - "1,312 kg CO2e" cradle-to-gate per baseboard.
- [S17] Shehabi et al., *2024 United States Data Center Energy Usage Report*, LBNL-2001637, Dec 2024. https://eta.lbl.gov/publications/2024-lbnl-data-center-energy-usage-report
  - Indirect water "4.52 L/kWh"; on-site WUE "just over 0.36 L/kWh".
  - Read via a mirror; lbl.gov returned 403.
- [S18] Li et al., *Making AI Less Thirsty*, arXiv:2304.03271v5, Mar 2025. https://arxiv.org/abs/2304.03271
  - US electricity water intensity factor 3.142 L/kWh, taken from WRI, so secondary for this figure.
- [S19] Macknick et al., *Operational water consumption and withdrawal factors for electricity generating technologies*, Environ. Res. Lett. 7 045802, 2012. https://doi.org/10.1088/1748-9326/7/4/045802
  - Gas combined cycle with cooling tower: 205 gal/MWh.
- [S20] Anthropic, *Prompt caching* (Claude Code Docs) and *Data residency* (Claude Platform Docs), undated. https://code.claude.com/docs/en/prompt-caching , https://platform.claude.com/docs/en/manage-claude/data-residency
  - On a subscription the main conversation uses a one-hour cache lifetime; subagents use five minutes.
  - "Inference may run in any available geography".
- [S21] Eurostat, *cli_gge_foot* (GHG footprint, FIGARO), updated 2026-10-30. https://ec.europa.eu/eurostat/databrowser/view/cli_gge_foot/default/table
  - EU 2024: 8,942 kg CO2e per person; Germany 10,404; EU 2023: 9,003.
- [S22] Eurostat, *env_ac_ghgfp*, updated 2026-10-30. https://ec.europa.eu/eurostat/databrowser/view/env_ac_ghgfp/default/table
  - EU 2024 shares (derived): households 69.6%, government 9.2%, gross fixed capital formation 19.8%.
- [S23] Ivanova et al., *Environmental Impact Assessment of Household Consumption*, J. Ind. Ecol. 20(3):526, 2016. doi:10.1111/jiec.12371 (open preprint: https://zenodo.org/record/1134811)
  - Fig. 3, EU: mobility 27.0%, shelter 26.2%, services 17.2%, manufactured products 16.6%, food 9.5%, clothing 3.5%.
  - VERIFIED (read from the figure).
- [S24] Ivanova et al., *Mapping the carbon footprint of EU regions*, Environ. Res. Lett., 2017. doi:10.1088/1748-9326/aa6da9
  - "Transport contributes to about 30% of EU household emissions".
- [S25] Ivanova & Wood, *The unequal distribution of household carbon footprints in Europe*, Global Sustainability, 2020. doi:10.1017/sus.2020.12
  - "the EU top 10% of households … fly"; for the rest of the population, air travel is "below 0.1 tCO2eq/cap".
- [S26] JRC, *Consumption Footprint Monitoring Report 2024* (JRC138470), 2025-03-04. https://publications.jrc.ec.europa.eu/repository/handle/JRC138470
  - Climate change: food 38%, mobility 24%, housing 21% (Fig. 14).
  - VERIFIED (read from the figure).
- [S27] Umweltbundesamt, *Durchschnittlicher CO₂-Fußabdruck pro Kopf in Deutschland* (Stand 2026). https://www.umweltbundesamt.de/bild/durchschnittlicher-co2-fussabdruck-pro-kopf-in
  - 9.8 t in total: Wohnen 1.9, Strom 0.6, Mobilität 2.1, Ernährung 1.6, sonstiger Konsum 2.5, öffentliche Infrastruktur 1.1.
- [S28] Bohmann & Küçük, *DIW Wochenbericht 27/2024*, 2024. https://www.diw.de/
  - Mobility "2,0 tCO2e"; "Der größte Teil … ist auf Flüge zurückzuführen" (most of it is due to flights).
- [S29] infas et al., *Mobilität in Deutschland 2023, Kurzbericht*. https://www.mobilitaet-in-deutschland.de
  - Freizeit (leisure) is 37% of passenger-km.
  - The column alignment is worth re-checking.
- [S30] Eurostat, *nrg_ind_eff* (updated 2026-04-21) and *demo_gind*.
  - Final energy consumption 2024: 900.41 Mtoe. Population on 1 Jan 2024: 450,054,483.
- [S31] Eurofound, *Working time in 2021–2022*, 2023; PDF revised 2024-05-21. doi:10.2806/677895 https://assets.eurofound.europa.eu/f/279033/356ff40090/ef23007en.pdf
  - "1,726 hours in 2022"; annual leave "24.3 days"; 9.0 public holidays (those not falling on Sundays); 38.1 h/week; Germany 30 days of leave.
  - Earlier versions of the PDF said 1,714 h.
- [S32] Directive 2003/88/EC, Art. 7(1), OJ L 299, 18 Nov 2003. https://eur-lex.europa.eu/eli/dir/2003/88/oj
  - "paid annual leave of at least four weeks".
- [S33] Destatis, *Erwerbstätige nach … Entfernung, Zeitaufwand und benutztem Verkehrsmittel* (Mikrozensus 2024, employees column), as of 2026-10-30. https://www.destatis.de/DE/Themen/Arbeit/Arbeitsmarkt/Pendeln-Arbeitsbedingungen/Tabellen/pendler1.html
  - Mode shares: car 65.2%, bicycle 10.2%, walking 7.2%, bus 5.7%, tram/U-Bahn 5.5%, rail 4.8%.
  - Distance classes: <5 km 26.6%, 5–10 km 22.4%, 10–25 km 29.4%, 25–50 km 14.5%, ≥50 km 5.3%.
- [S34] Umweltbundesamt, *Vergleich der durchschnittlichen Emissionen einzelner Verkehrsmittel im Personenverkehr 2024* (TREMOD 6.71B), 2025-12-10. https://www.umweltbundesamt.de/system/files/medien/366/bilder/dateien/vtv_2024_pv_tab_pdf.pdf
  - g CO2e/pkm: car 164, bus 90, local rail 44, tram/U-Bahn 42.
- [S35] Icha & Lauf, *Entwicklung der spezifischen Treibhausgas-Emissionen des deutschen Strommix 1990–2025*, UBA Climate Change 16/2026, Mar 2026. https://www.umweltbundesamt.de/system/files/medien/11850/publikationen/2026-03/16_2026_CC.pdf
  - 2024: 414 g CO2e/kWh including upstream.
- [S36] Umweltbundesamt, *Liste Emissionsfaktoren zur THG-Bilanzierung* v2.1, 2026-02-28.
  - Natural gas: 0.2423 kg CO2e/kWh in total (including upstream).
- [S37] US EPA, *ENERGY STAR Certified Computers / Displays* datasets, 2026-11-13. https://data.energystar.gov/
  - Medians (derived): notebook short idle 4.9 W; desktop short idle 10.5 W; 24" display on-mode 12.9 W.
- [S38] BAuA, *ASR A1.2 Raumabmessungen und Bewegungsflächen*, 2013, last amended 2022. https://www.baua.de/DE/Angebote/Regelwerk/ASR/pdf/ASR-A1-2.pdf
  - "mindestens 8 m2 für einen Arbeitsplatz zuzüglich mindestens 6 m2 für jeden weiteren" (at least 8 m² for one workplace plus at least 6 m² for each additional one).
- [S39] Catella Research, *Der europäische Büroflächenmarkt – shrink to fit?*, 2023. https://www.catella.com/
  - European city average 20.88 m² per office employee.
  - Secondary (real-estate industry).
- [S40] dena, *Fokusthemen Büro- und Verwaltungsgebäude*, Dec 2023. https://www.gebaeudeforum.de/fileadmin/gebaeudeforum/Downloads/Gebaeudereport/Gebaeudeforum_GR24_Fokusthemen_Buerogebaeude.pdf
  - "Ca. 395 Mio. m² Nutzungsfläche"; 12.8 M office employees; space heating and hot water 55.3 TWh; "Nutzerstrom … 60 kWh/m²".
- [S41] BMWi/BMI, *Bekanntmachung der Regeln für Energieverbrauchswerte … im Nichtwohngebäudebestand*, BAnz AT 03.05.2021 B1.
  - Bürogebäude (office buildings): heating 49.0, hot water 8.1 kWh/(m²·a); electricity components sum to 25.5.
- [S42] dena / IW Köln, *Energieeffizienz bei Büroimmobilien*, Mar 2016 (secondary host: tab.de).
  - "durchschnittliche Energieverbrauchskennwert bei 133,4 kWh/(m²·a)" (average energy consumption of 133.4 kWh/(m²·a)).
- [S43] Mekonnen & Hoekstra, *National water footprint accounts*, Value of Water Research Report 50, UNESCO-IHE, 2011. https://ayhoekstra.nl/pubs/Report50-WaterFootprintNations-Vol2.pdf
  - Germany: blue 85.1 m³ per person per year.
  - EU-27: 142, derived as a population-weighted average.
- [S44] Dynamic Electronics (Huangshi), *PCB (10 Layer) Report for Product Carbon Footprint Assessment (ISO 14067)*, 2023-07-24 (dynaholding.com).
  - Per square foot: 16.6347 kg CO2e; electricity 10.993 kWh; tap water 0.10571 t.
  - Data year 2022; not third-party verified; ecoinvent Central China grid at ~0.82 kg/kWh.
- [S45] VHK for the European Commission, *MEErP 2011 Methodology Part 2*, Table 17. https://www.eceee.org/static/media/uploads/site-2/ecodesign/products/ecodesign-directive-evaluation-methodology/meerp-methodology-part-2-final.pdf
  - 6-layer printed wiring board: 4.5 kg/m², 16 kg CO2e/kg. SMD/LED average: 167 kg CO2e/kg.
- [S46] Nassajfar et al., *Alternative Materials for Printed Circuit Board Production*, Sustainability 13:12126, 2021. doi:10.3390/su132112126
  - "34.8" kg CO2e per m² of 4-layer PCB.
- [S47] Victory Giant Technology, *2025 ESG report* (exchange-filing mirror at pdf.dfcfw.com).
  - 0.0846 t CO2e per m² (Scope 1+2; unit derived).
  - Secondary host.
- [S48] Pirson & Bol, *Assessing the embodied carbon footprint of IoT edge devices*, arXiv:2105.02082, 2021 (J. Cleaner Prod.).
  - 4-layer PCB block 0.13–0.24 kg for 8–15 cm²; MCU of 5–17 mm²: 0.08–0.29 kg.
- [S49] China MEE, *HJ 450-2008 清洁生产标准 印制电路板制造业* (clean production standard for PCB manufacturing), 2008. https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/other/qjscbz/200811/W020111114391492039465.pdf
  - Multilayer boards: water ≤(0.5+0.3n) to ≤(1.3+0.5n) m³/m²; electricity ≤(45+20n) to ≤(75+30n) kWh/m²; +15% for prototype makers.
- [S50] Chen et al., *CarbonClarity*, arXiv:2507.01145v2, 2026-01-15.
  - "1.18 kgCO2 per cm2" at 28 nm.
- [S51] Gupta et al., *ACT*, ISCA 2022. doi:10.1145/3470496.3527408
  - Packaging "0.15kg CO2" per IC; fab energy "0.8-3.5 kWh per cm2".
- [S52] Andersen, Walnum & Andrae, *Conpart final report*, Vestlandsforsking 6/2010.
  - Small IC in an SOD6 package: "0.058" kg CO2e per unit.
- [S53] Smith et al., *Applied Energy* 220:496, 2018 (open copy: eprints.whiterose.ac.uk/130419).
  - 1 kg of inventory = 670,630 0402 MLCCs; 97.00 kg CO2e per kg.
- [S54] Zhang et al., *DeltaLCA*, Proc. ACM IMWUT 8(1), 2024. doi:10.1145/3643561
  - Resistor 0402: 0.040 g CO2e; capacitor 0603: 0.611 g.
- [S55] Weidmüller, *EPDs, PCB connector series SL 5.00, LSF-SMD 3.50, B2CF 3.50*, 2025–2026 (assets.dam.weidmueller.com).
  - A1–A3: 6.30E-03, 1.86E-02 and 4.61E-02 kg CO2e per piece.
- [S56] Nordelöf, *Int. J. LCA* 24:694, 2019. doi:10.1007/s11367-018-1491-3
  - Assembly of 1 m² of surface-mounted PCB: "Electricity 46 kWh", "Nitrogen 64 kg".
- [S57] China MEE/NBS, *Announcement 2025 No. 47*, 2025-12-31. https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202512/W020251231726284332528.pdf
  - Guangdong 0.4419; national 0.5306 kg CO2/kWh (2023).
- [S58] China MEE/NBS/NEA, *Announcement 2025 No. 19* (2024 electricity carbon-footprint factors), released 2025-10-24. https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202510/W020251024569470952545.pdf
  - National "0.5777" kg CO2e/kWh, lifecycle, including transmission and distribution losses.
- [S59] UK DESNZ, *Greenhouse gas reporting: conversion factors 2025*, 2025-06-10. https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting
  - International freight flights with radiative forcing: 0.89939 kg CO2e/t·km; well-to-tank: 0.13516.
- [S60] Smart Freight Centre, *GLEC Framework v3.0*, Sep 2023, Module 2, Table 1 (copy hosted by ECTA).
  - Long-haul freighter: 498 g CO2e/t·km tank-to-wheel, 629 g well-to-wheel; unknown aircraft type: 646 g tank-to-wheel.
- [S61] DHL GoGreen Plus certificate for Böcker, data year 2025, reproduced at boecker.de, 2026-07-24.
  - "837.80 grams per tkm".
  - Secondary.
- [S62] Wang et al., *Water Cycle* 4:47, 2023. doi:10.1016/j.watcyc.2023.01.004
  - "8.22 L/cm2, 1.15 kWh/cm2".
  - VERIFIED from the abstract only.
- [S63] GlobalFoundries, *2026 Sustainability Report* and *FY2025 10-K*, 2026.
  - 13,864,993 GJ; 25,960 thousand m³ withdrawn; 2.3M wafers.
  - Derived: 2.37 kWh/cm² and 16.0 L/cm².
- [S64] Uptime Institute, *Global Data Center Survey 2026*, Jul 2026.
  - "2026 industry average PUE is 1.52".
- [S66] E. Upton, Raspberry Pi blog, 2025-01-09.
  - "6.5kg of CO₂ equivalent" for a Raspberry Pi 4 or 5.
- [S67] US EIA, *Electric Power Annual*, Table 8.2.
  - Heat rates: gas turbine 10,975 and combined cycle 7,535 Btu/kWh. Derived: about 0.58 kg CO2/kWh direct for an open-cycle turbine.
- [S68] BBSR, *Mehr Pendlerinnen und Pendler in Deutschland*, press release, 2025-10-10. https://www.bbsr.bund.de/BBSR/DE/presse/presseinformationen/2025/pendeln-2024.html
  - "Der durchschnittliche einfache Arbeitsweg betrug 17,2 Kilometer" (2024, employees subject to social insurance; mode not recorded).

Not verified or not used:
- Jensen Huang's "$50–60B per GW" (UNVERIFIED).
- GLEC v3.2 (403).
- ecoinvent PCB and SMT datasets (licence required).
- Teehan & Kandlikar 2013 and Ochoa et al. 2019 (paywalled).

## 6. Appendix: script

Run with `python3 claude-breakeven.py`. It needs only the Python standard library and takes about 3 s.

```python
#!/usr/bin/env python3
"""Break-even between Claude Code use and (a) one EU work hour, (b) one PCBA prototype order.

All inputs are listed in the PARAMS / constants blocks with their source tag (see
claude-breakeven.md, "Sources" and "Assumptions"). Each uncertain input is a triple
(low value, central value, high value). The central result uses all central values.
Low/high results are the 5th/95th percentiles of a Monte Carlo run in which every
uncertain input is drawn independently from a triangular distribution over
log(low)..log(high) with mode log(central). The tornado ranks inputs by how much
swinging each one from low to high (others central) changes a result.

Standard library only. Run:  python3 claude-breakeven.py
"""
import math
import random

# ---------------------------------------------------------------------------
# 1. Fixed, sourced constants
# ---------------------------------------------------------------------------
# [S1] Anthropic S-1/A No.2, nine months to 30 Sep 2026, $M
REV_9M, COR_9M = 33_242, 4_812
COR_SHARE = COR_9M / REV_9M                      # cost of revenue per revenue $
COMPUTE_9M = 18_808                              # [S1] total compute & infrastructure, nine months 2026, $M
# [S3] Opus 5.5 list prices, $/MTok
PRICE = dict(inp=4.0, w5=5.0, w1h=8.0, cr=0.20, out=20.0)
# Token mix from the earlier notes (share of all tokens)
MIX = dict(cr=0.90, w=0.06, inp=0.01, out=0.03)
# [M1] Measured mix of this research session (Claude Code transcripts, 99.3M tokens, 2026-11-14)
MIX_MEASURED = dict(cr=0.9764, w5=0.0179, w1h=0.0017, inp=0.0000155, out=0.0040)
USD_PER_MTOK_MEASURED = sum(MIX_MEASURED[k] * PRICE[k] for k in MIX_MEASURED)
PRO_WINDOW_USD = 66.0                            # [U1] user's measured Pro 5-h window, list-price $
SESSION_USD = 229.58                             # [U2] user's earlier /usage session cost
# [S4] SpaceX S-1/A: $1.25B per month for ~325,000 GPUs (Colossus + Colossus II)
SPACEX_USD_MONTH, SPACEX_GPUS = 1.25e9, 325_000
HOURS_PER_MONTH = 8766 / 12
# [S4] nameplate all-in kW per GPU: H100 130 MW/100k, GB200 210 MW/110k, GB300 220 MW/110k
KW_PER_GPU = dict(h100=130e3 / 100e3, gb200=210e3 / 110e3, gb300=220e3 / 110e3)
# [S5] Anthropic: Colossus 1 = ">300 MW", ">220,000 GPUs"
COLOSSUS1_MW, COLOSSUS1_GPUS = 300.0, 220_000
# [S6] heise: $35-50B capex per GW
CAPEX_PER_GW = (35e9, 50e9)
# [S21] Eurostat cli_gge_foot 2024, kg CO2e per capita
FP_EU, FP_DE = 8_942, 10_404
# [S30] Eurostat nrg_ind_eff FEC 2024 (Mtoe) and demo_gind population 1 Jan 2024
FEC_MTOE, POP_EU = 900.41, 450_054_483
MWH_PER_TOE = 11.63
# [S31] Eurofound: EU27 leave 24.3 days, 9.0 public holidays not on Sundays (2022)
WEEKDAYS_PER_YEAR = 365.25 / 7 * 5
# [S33] Destatis Mikrozensus 2024, employees: commute mode shares (%) and distance classes (%)
MODE_SHARE = dict(car=65.2, bike=10.2, walk=7.2, bus=5.7, tram=5.5, rail=4.8)
DIST_CLASS = [(2.5, 26.6), (7.5, 22.4), (17.5, 29.4), (37.5, 14.5), (60.0, 5.3)]  # (midpoint km, %)
# [S34] UBA TREMOD 2024, g CO2e per passenger-km (well-to-wheel)
EF_PKM = dict(car=164, bike=0, walk=0, bus=90, tram=42, rail=44)
# [S35] UBA German grid 2024 incl. upstream, kg CO2e/kWh
CI_DE = 0.414
# [S36] UBA emission factor list v2.1: natural gas incl. upstream, kg CO2e/kWh
EF_GAS = 0.242
# Great-circle HKG-LEJ (km, derived from airport coordinates) ; road legs Zhuhai-HKG + LEJ-Berlin (km, ASSUMPTION)
AIR_KM, ROAD_KM = 8_855, 340

# ---------------------------------------------------------------------------
# 2. Derived $ per facility kWh (three derivations -> one uncertain input)
# ---------------------------------------------------------------------------
def spacex_usd_per_kwh(mw_it, util, pue):
    """Rental price per facility kWh: monthly fee / (nameplate IT MW x util x PUE x h)."""
    return SPACEX_USD_MONTH / (mw_it * 1e3 * HOURS_PER_MONTH * util * pue)

# IT nameplate MW behind the 325k GPUs (not disclosed): all-H100-class, Colossus-1 + GB200 mix, all-GB300
MW_LO = SPACEX_GPUS * KW_PER_GPU['h100'] / 1e3
MW_C = COLOSSUS1_MW + (SPACEX_GPUS - COLOSSUS1_GPUS) * KW_PER_GPU['gb200'] / 1e3
MW_HI = SPACEX_GPUS * KW_PER_GPU['gb300'] / 1e3
USD_KWH_SPACEX_C = spacex_usd_per_kwh(MW_C, 0.70, 1.30)     # ASSUMPTION util 0.70, PUE 1.30
USD_KWH_SPACEX_HI = spacex_usd_per_kwh(MW_LO, 0.60, 1.20)   # fewest kWh per $
def tco_usd_per_kwh(capex_per_gw, life_yr=5, util=0.75, opex_uplift=1.3, power_price=0.08):
    """Owner's cost per facility kWh: amortised capex x uplift (opex, financing) + electricity."""
    return capex_per_gw / (1e6 * 8766 * life_yr * util) * opex_uplift + power_price
USD_KWH_TCO = tco_usd_per_kwh(CAPEX_PER_GW[1])               # most kWh per $ (no provider margin)

# ---------------------------------------------------------------------------
# 3. Uncertain inputs: name -> (low, central, high, source tag)
# ---------------------------------------------------------------------------
PARAMS = {
    # --- AI, top-down (financial) ---
    'compute_frac': (0.90, 0.95, 1.00, 'A1 "substantially all" of cost of revenue is compute [S1]'),
    'r_list':       (0.32, 0.61, 1.00, 'A2 realised revenue per list-price $ [S1 revenue mix + assumption]'),
    'usd_per_kwh':  (USD_KWH_TCO, USD_KWH_SPACEX_C, USD_KWH_SPACEX_HI, 'A3 $ of compute per facility kWh [S4,S5,S6]'),
    # --- AI, bottom-up (per token) ---
    'e_out':        (0.5, 1.0, 3.0, 'A4 Wh per 1k output tokens incl. PUE [S7,S9,S11]'),
    'm_ctx':        (1.0, 1.5, 3.0, 'A5 long-context decode multiplier (Claude Code ~50-200k ctx)'),
    'k_in':         (0.15, 0.30, 0.60, 'A6 uncached input token energy / output token [S10,S11]'),
    'k_cr':         (0.02, 0.05, 0.20, 'A7 cache-read token energy / uncached input token'),
    # --- AI, common ---
    'ci_ai':        (0.35, 0.41, 0.55, 'A8 grid kg CO2e/kWh for inference [S4,S12,S13,S14]'),
    'emb':          (1.05, 1.11, 1.25, 'A9 embodied hardware uplift [S15,S16]'),
    'water_ai':     (1.0, 3.5, 5.7, 'A10 L/kWh on-site + generation water [S8,S17,S18,S19]'),
    'w1h_frac':     (0.0, 0.5, 1.0, 'A11 share of cache writes at 1-hour price [S3,S20]'),
    # --- Human ---
    'fp':           (FP_EU * 0.9, FP_EU, FP_DE, 'H1 kg CO2e per capita per year [S21]'),
    'leave':        (20.0, 24.3, 30.0, 'H2 paid leave days [S31,S32]'),
    'holidays':     (7.0, 9.0, 10.0, 'H3 weekday public holidays [S31]'),
    'basic_share':  (0.67, 0.77, 0.86, 'H4 basic-living share of total footprint [S22-S29 + derivation]'),
    'water_cap':    (85.1, 142.0, 170.0, 'H5 blue water footprint m3/cap/yr [S43]'),
    'dev_kw':       (0.015, 0.030, 0.100, 'H6 workstation kW in use [S37]'),
    'office_m2':    (10.0, 20.9, 30.9, 'H7 office m2 per employee [S38,S39,S40]'),
    'office_heat':  (57.1, 133.4, 140.0, 'H8 office heat kWh/m2a [S40,S41,S42]'),
    'office_el':    (25.5, 60.0, 60.0, 'H9 office electricity kWh/m2a [S40,S41]'),
    'office_avoid': (0.0, 0.25, 1.0, 'H10 share of office energy avoided per hour not worked'),
    'commute_avoid':(0.0, 0.5, 1.0, 'H11 share of average commute avoided per hour not worked'),
    'commute_km':   (8.0, 17.2, 25.0, 'H12 one-way commute km [S68; S33 classes give 16.1]'),
    'commute_ef':   (0.0, 1.0, 1.4, 'H13 commute EF multiplier on Destatis mode mix (1.4 ~ car only) [S33,S34]'),
    # --- PCBA ---
    'panel_m2':     (0.05, 0.06, 0.07, 'P1 board area incl. panel waste, m2'),
    'pcb_kg_m2':    (35.0, 60.0, 160.0, 'P2 kg CO2e per m2 4-layer PCB [S44-S48]'),
    'pcb_kwh_m2':   (85.0, 110.0, 155.0, 'P3 PCB fab kWh/m2 [S44,S49]'),
    'pcb_l_m2':     (1100.0, 1700.0, 2600.0, 'P4 PCB fab fresh water L/m2 (withdrawal) [S44,S49]'),
    'ic_kg':        (0.03, 0.07, 0.25, 'P5 kg CO2e per IC incl. package [S48,S50,S51,S52]'),
    'ic_die_mm2':   (2.0, 5.0, 15.0, 'P6 mean die area per IC, mm2'),
    'fab_kwh_cm2':  (1.15, 1.6, 2.37, 'P7 fab kWh per cm2 wafer [S51,S62,S63]'),
    'fab_l_cm2':    (8.2, 12.0, 16.0, 'P8 fab water withdrawal L/cm2 [S62,S63]'),
    'rc_g':         (0.04, 0.15, 0.60, 'P9 g CO2e per R/C/L [S53,S54]'),
    'disc_g':       (1.5, 9.0, 58.0, 'P10 g CO2e per discrete (diode, transistor, LED, crystal) [S45,S52]'),
    'conn_g':       (5.0, 20.0, 50.0, 'P11 g CO2e per connector [S55]'),
    'smt_kwh_m2':   (46.0, 46.0, 66.0, 'P12 SMT assembly kWh/m2 (46 + optional N2 energy) [S56]'),
    'smt_setup_kwh':(0.0, 2.0, 8.0, 'P13 prototype set-up/warm-up kWh'),
    'ci_cn':        (0.44, 0.58, 0.82, 'P14 China grid kg CO2e/kWh [S44,S57,S58]'),
    'pack_kg':      (0.15, 0.43, 1.0, 'P15 packaging kg CO2e'),
    'ship_kg':      (0.4, 0.6, 1.0, 'P16 shipment mass kg'),
    'air_ef':       (0.629, 0.838, 1.035, 'P17 air kg CO2e per t-km WTW [S59,S60,S61]'),
}
# Board composition per board (ASSUMPTION): 300 placements = 15 ICs + 255 R/C/L + 24 discretes + 6 connectors
BOARDS, N_IC, N_RC, N_DISC, N_CONN = 5, 15, 255, 24, 6
ROAD_EF = 0.6               # kg CO2e per t-km, small van (ASSUMPTION; road legs are <1% of total)
AIR_KWH_TKM = 0.646 / 3.16 * 11.9   # GLEC 'unknown' TTW kg/t-km / kg CO2 per kg fuel x kWh per kg fuel (derived)
CAR_KWH_PKM, PT_KWH_PKM = 0.45, 0.15  # final energy per passenger-km (ASSUMPTION)

CENTRAL = {k: v[1] for k, v in PARAMS.items()}

# ---------------------------------------------------------------------------
# 4. Model
# ---------------------------------------------------------------------------
def usd_per_mtok(v):
    w = v['w1h_frac'] * PRICE['w1h'] + (1 - v['w1h_frac']) * PRICE['w5']
    return MIX['cr'] * PRICE['cr'] + MIX['w'] * w + MIX['inp'] * PRICE['inp'] + MIX['out'] * PRICE['out']

def ai_topdown(v):
    """Per list-price $: (kWh, kg CO2e, L)."""
    kwh = COR_SHARE * v['compute_frac'] * v['r_list'] / v['usd_per_kwh']
    return kwh, kwh * v['ci_ai'] * v['emb'], kwh * v['water_ai']

MIX_MEASURED_SIMPLE = dict(cr=MIX_MEASURED['cr'], w=MIX_MEASURED['w5'] + MIX_MEASURED['w1h'],
                           inp=MIX_MEASURED['inp'], out=MIX_MEASURED['out'])

def bottomup_wh_per_mtok(v, mix):
    e_in = v['e_out'] * v['k_in']
    return 1000 * (mix['out'] * v['e_out'] * v['m_ctx'] + (mix['inp'] + mix['w']) * e_in + mix['cr'] * e_in * v['k_cr'])

def ai_bottomup(v):
    """Per list-price $: (kWh, kg CO2e, L) from per-token energy on the token mix."""
    wh_per_mtok = bottomup_wh_per_mtok(v, MIX)
    kwh = wh_per_mtok / 1000 / usd_per_mtok(v)
    return kwh, kwh * v['ci_ai'] * v['emb'], kwh * v['water_ai']

def work_hours(v):
    return 8 * (WEEKDAYS_PER_YEAR - v['leave'] - v['holidays'])

def commute_per_hour(v):
    """(kg CO2e, kWh) of the average commute allocated to one work hour."""
    tot = sum(MODE_SHARE.values())
    ef = sum(MODE_SHARE[m] * EF_PKM[m] for m in MODE_SHARE) / tot / 1000 * v['commute_ef']
    car_share = MODE_SHARE['car'] / tot
    pt_share = (MODE_SHARE['bus'] + MODE_SHARE['tram'] + MODE_SHARE['rail']) / tot
    kwh_pkm = car_share * CAR_KWH_PKM + pt_share * PT_KWH_PKM
    day_km = 2 * v['commute_km']
    return v['commute_avoid'] * day_km * ef / 8, v['commute_avoid'] * day_km * kwh_pkm / 8

def human(v):
    """Per work hour: dict of view -> (kg CO2e, kWh, L)."""
    h = work_hours(v)
    fec_kwh = FEC_MTOE * 1e6 * MWH_PER_TOE * 1e3 / POP_EU      # kWh per capita per year
    full = (v['fp'] / h, fec_kwh / h, v['water_cap'] * 1000 / h)
    basic = tuple(x * v['basic_share'] for x in full)
    dev_kwh = v['dev_kw']
    off_kwh_h = v['office_m2'] * v['office_heat'] / h * v['office_avoid']
    off_kwh_e = v['office_m2'] * v['office_el'] / h * v['office_avoid']
    com_kg, com_kwh = commute_per_hour(v)
    marg_kg = dev_kwh * CI_DE + off_kwh_h * EF_GAS + off_kwh_e * CI_DE + com_kg
    marg_kwh = dev_kwh + off_kwh_h + off_kwh_e + com_kwh
    return {'full': full, 'basic': basic, 'marginal': (marg_kg, marg_kwh, float('nan'))}

def pcba(v, detail=False):
    """One order: (kg CO2e, kWh, L withdrawal) and optional item breakdown."""
    a = v['panel_m2']
    n_ic = BOARDS * N_IC
    die_cm2 = n_ic * v['ic_die_mm2'] / 100
    smt_kwh = v['smt_kwh_m2'] * a + v['smt_setup_kwh']
    tkm = v['ship_kg'] / 1000
    items = {
        'bare boards':        (v['pcb_kg_m2'] * a, v['pcb_kwh_m2'] * a, v['pcb_l_m2'] * a),
        'ICs (75)':           (n_ic * v['ic_kg'], die_cm2 * v['fab_kwh_cm2'], die_cm2 * v['fab_l_cm2']),
        'R/C/L (1,275)':      (BOARDS * N_RC * v['rc_g'] / 1000, 0.0, 0.0),
        'discretes (120)':    (BOARDS * N_DISC * v['disc_g'] / 1000, 0.0, 0.0),
        'connectors (30)':    (BOARDS * N_CONN * v['conn_g'] / 1000, 0.0, 0.0),
        'SMT assembly':       (smt_kwh * v['ci_cn'], smt_kwh, 0.0),
        'packaging':          (v['pack_kg'], 0.0, 0.0),
        'express air + road': (tkm * (AIR_KM * v['air_ef'] + ROAD_KM * ROAD_EF), tkm * AIR_KM * AIR_KWH_TKM, 0.0),
    }
    tot = tuple(sum(x[i] for x in items.values()) for i in range(3))
    return (tot, items) if detail else tot

TARGETS = {
    '(a) work hour, full footprint':  lambda v: human(v)['full'],
    '(a) work hour, basic living':    lambda v: human(v)['basic'],
    '(a) work hour, marginal':        lambda v: human(v)['marginal'],
    '(b) PCBA order':                 lambda v: pcba(v),
}
AI = {'top-down': ai_topdown, 'bottom-up': ai_bottomup}

def breakeven_usd(v, target, ai):
    return TARGETS[target](v)[0] / AI[ai](v)[1]

# ---------------------------------------------------------------------------
# 5. Monte Carlo and tornado
# ---------------------------------------------------------------------------
def sample(rng):
    v = {}
    for k, (lo, c, hi, _) in PARAMS.items():
        if lo == hi:
            v[k] = c
        elif lo <= 0:      # zero lower bound: plain triangular
            v[k] = rng.triangular(lo, hi, c)
        else:
            v[k] = math.exp(rng.triangular(math.log(lo), math.log(hi), math.log(c)))
    return v

def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(round(p / 100 * (len(xs) - 1)))))]

def run_mc(n=40_000, seed=20261114):
    rng = random.Random(seed)
    out = {}
    for _ in range(n):
        v = sample(rng)
        for t in TARGETS:
            for a in AI:
                out.setdefault((t, a), []).append(breakeven_usd(v, t, a))
        for a in AI:
            out.setdefault(('ai kg/$', a), []).append(AI[a](v)[1])
            out.setdefault(('ai kWh/$', a), []).append(AI[a](v)[0])
        for t in TARGETS:
            out.setdefault(('target kg', t), []).append(TARGETS[t](v)[0])
    return {k: (pct(x, 5), pct(x, 50), pct(x, 95)) for k, x in out.items()}

def tornado(f, top=4):
    base = f(CENTRAL)
    rows = []
    for k, (lo, c, hi, _) in PARAMS.items():
        vals = []
        for x in (lo, hi):
            v = dict(CENTRAL); v[k] = x
            vals.append(f(v))
        if min(vals) > 0 and max(vals) / min(vals) > 1.0001:
            rows.append((max(vals) / min(vals), k, vals[0] / base, vals[1] / base))
    return sorted(rows, reverse=True)[:top]

# ---------------------------------------------------------------------------
# 6. Report
# ---------------------------------------------------------------------------
def fmt(x, d=0):
    if x != x:
        return 'n/a'
    if abs(x) >= 100:
        return f'{x:,.0f}'
    return f'{x:,.{d}f}' if d else (f'{x:.1f}' if abs(x) >= 10 else f'{x:.2g}')

def main():
    c = CENTRAL
    print('== Derived inputs ==')
    print(f'cost of revenue / revenue (9M 2026) = {COR_SHARE:.4f}')
    print(f'$/MTok: central {usd_per_mtok(c):.3f}  (all 5-min writes {usd_per_mtok({**c, "w1h_frac": 0}):.3f}, '
          f'all 1-h writes {usd_per_mtok({**c, "w1h_frac": 1}):.3f})')
    print(f'SpaceX IT MW behind 325k GPUs: lo {MW_LO:.0f}, central {MW_C:.0f}, hi {MW_HI:.0f}')
    print(f'$/facility kWh: TCO (most kWh/$) {USD_KWH_TCO:.2f}, SpaceX central {USD_KWH_SPACEX_C:.2f}, '
          f'SpaceX fewest kWh/$ {USD_KWH_SPACEX_HI:.2f}')
    print(f'work hours/yr central {work_hours(c):.0f} (lo {work_hours({**c, "leave": 30, "holidays": 10}):.0f}, '
          f'hi {work_hours({**c, "leave": 20, "holidays": 7}):.0f})')
    print(f'Destatis distance-class mean one-way km (cross-check): {sum(k * w for k, w in DIST_CLASS) / sum(w for _, w in DIST_CLASS):.1f}')
    tot = sum(MODE_SHARE.values())
    print(f'commute mode-mix EF: {sum(MODE_SHARE[m] * EF_PKM[m] for m in MODE_SHARE) / tot:.1f} g CO2e/pkm')
    ck, ckwh = commute_per_hour(c)
    print(f'commute per work hour (central): {ck:.3f} kg CO2e, {ckwh:.3f} kWh')
    for a, f in AI.items():
        kwh, kg, l = f(c)
        print(f'AI {a}: {kwh * 1000:.1f} Wh/$, {kg * 1000:.2f} g CO2e/$, {l:.3f} L/$ (central)')
    print(f'measured mix: ${USD_PER_MTOK_MEASURED:.3f}/MTok; bottom-up on measured mix: '
          f'{bottomup_wh_per_mtok(c, MIX_MEASURED_SIMPLE) / USD_PER_MTOK_MEASURED:.1f} Wh/$')
    print(f'bottom-up / top-down g per $: {ai_bottomup(c)[1] / ai_topdown(c)[1]:.2f}x; '
          f'notes-mix / measured-mix $ per MTok: {usd_per_mtok(c) / USD_PER_MTOK_MEASURED:.2f}x')
    print(f'total compute / revenue (9M 2026) = {COMPUTE_9M / REV_9M:.3f}; '
          f'vs cost of revenue: {COMPUTE_9M / COR_9M:.2f}x (upper bound for adding training)')
    print(f'earlier session ${SESSION_USD}: top-down {SESSION_USD * ai_topdown(c)[1]:.2f} kg, '
          f'bottom-up {SESSION_USD * ai_bottomup(c)[1]:.2f} kg CO2e (central)')

    print('\n== Targets (central) ==')
    for t, f in TARGETS.items():
        kg, kwh, l = f(c)
        print(f'{t:34s} {kg:8.3f} kg CO2e  {kwh:8.2f} kWh  {fmt(l)} L')
    tot, items = pcba(c, detail=True)
    for name, (kg, kwh, l) in items.items():
        print(f'   PCBA {name:20s} {kg:6.2f} kg  {kwh:6.2f} kWh  {l:6.1f} L')
    print(f'   PCBA per board (central): {tot[0] / BOARDS:.2f} kg CO2e')
    for case, i in (('low', 0), ('high', 2)):
        v = {k: p[i] for k, p in PARAMS.items()}
        print(f'   PCBA all-{case} inputs: {pcba(v)[0]:.1f} kg CO2e')

    mc = run_mc()
    print('\n== Monte Carlo P5 / P50 / P95 ==')
    for a in AI:
        lo, med, hi = mc[('ai kg/$', a)]
        print(f'AI {a:9s} g CO2e/$: {lo * 1000:.2f} / {med * 1000:.2f} / {hi * 1000:.2f}')
    for t in TARGETS:
        lo, med, hi = mc[('target kg', t)]
        print(f'{t:34s} kg CO2e: {lo:.3f} / {med:.3f} / {hi:.3f}')

    print('\n== ANSWER: break-even (CO2e). central = all-central inputs; low/high = MC P5/P95 ==')
    print(f'{"target":34s} {"AI":9s} | {"$ low":>7s} {"$ c":>7s} {"$ high":>7s} | '
          f'{"MTok lo":>7s} {"MTok c":>7s} {"MTok hi":>7s} {"MTok m":>7s} | {"Pro win lo":>10s} {"c":>6s} {"hi":>6s}')
    upm = usd_per_mtok(c)
    for t in TARGETS:
        for a in AI:
            cen = breakeven_usd(c, t, a)
            lo, _, hi = mc[(t, a)]
            print(f'{t:34s} {a:9s} | {fmt(lo):>7s} {fmt(cen):>7s} {fmt(hi):>7s} | {fmt(lo / upm):>7s} {fmt(cen / upm):>7s} {fmt(hi / upm):>7s} {fmt(cen / USD_PER_MTOK_MEASURED):>7s} | '
                  f'{fmt(lo / PRO_WINDOW_USD):>10s} {fmt(cen / PRO_WINDOW_USD):>6s} {fmt(hi / PRO_WINDOW_USD):>6s}')
    print(f'(MTok c = notes mix at ${upm:.2f}/MTok; MTok m = measured session mix at ${USD_PER_MTOK_MEASURED:.3f}/MTok)')
    print(f'(token-mix price alone ranges {usd_per_mtok({**c, "w1h_frac": 0}):.2f}-'
          f'{usd_per_mtok({**c, "w1h_frac": 1}):.2f} $/MTok with the notes mix)')

    print('\n== Energy and water at the CO2e break-even (central; identical for both AI methods) ==')
    for t, f in TARGETS.items():
        kg, kwh, l = f(c)
        usd = breakeven_usd(c, t, 'top-down')
        akwh, _, al = ai_topdown(c)
        e_be = '  '.join(f'{a} ${kwh / g(c)[0]:,.0f}' for a, g in AI.items())
        print(f'{t:34s}: AI {usd * akwh:6.2f} kWh {usd * al:6.1f} L | target {kwh:6.2f} kWh {fmt(l):>5s} L | '
              f'energy-based break-even: {e_be}')

    print('\n== Decision rules (central, with MC P5-P95) ==')
    for t in list(TARGETS)[:3]:
        for a in AI:
            cen = breakeven_usd(c, t, a)
            lo, _, hi = mc[(t, a)]
            m = lambda usd: 600 / usd          # minutes of work per $10 to break even
            print(f'{t:34s} {a:9s}: break even if $10 replaces >= {m(cen):.2f} min '
                  f'[{m(hi):.2f}-{m(lo):.2f}]; one Pro window ($66) needs >= {66 / cen * 60:.1f} min '
                  f'[{66 / hi * 60:.1f}-{66 / lo * 60:.1f}]')

    print('\n== Scenarios (central otherwise) ==')
    for name, over in (('home office, no commute, office energy not avoided', dict(commute_avoid=0.0, office_avoid=0.0)),
                       ('office worker, full average commute and office energy avoided', dict(commute_avoid=1.0, office_avoid=1.0)),
                       ('top-down with r_list = 1 (every token earns list price)', dict(r_list=1.0)),
                       ('top-down with inference on dedicated gas (ci 0.55)', dict(ci_ai=0.55))):
        v = {**c, **over}
        kg = human(v)['marginal'][0]
        print(f'{name}: marginal {kg:.3f} kg/h -> top-down ${breakeven_usd(v, "(a) work hour, marginal", "top-down"):.1f}, '
              f'bottom-up ${breakeven_usd(v, "(a) work hour, marginal", "bottom-up"):.1f} per hour; '
              f'top-down g/$ {ai_topdown(v)[1] * 1000:.2f}')

    print('\n== Tornado: biggest drivers (ratio high/low of result; factor vs central at input low, high) ==')
    for t in ('(a) work hour, full footprint', '(a) work hour, marginal', '(b) PCBA order'):
        for a in AI:
            print(f'{t} / {a}:')
            for ratio, k, flo, fhi in tornado(lambda v: breakeven_usd(v, t, a)):
                print(f'   {k:14s} x{ratio:5.2f}  ({flo:.2f} .. {fhi:.2f})   {PARAMS[k][3]}')

    print('\n== Notes method reproduced (for comparison) ==')
    notes_g = 2.38 / 16.29 / 3.6 * 0.40 * 1.2
    print(f'notes: {notes_g * 1000:.1f} g/$; work hour 9000/2080 = {9000 / 2080:.2f} kg -> ${9000 / 2080 / notes_g:.0f}')

if __name__ == '__main__':
    main()
```

Output of the run used for this document:

```text
== Derived inputs ==
cost of revenue / revenue (9M 2026) = 0.1448
$/MTok: central 1.210  (all 5-min writes 1.120, all 1-h writes 1.300)
SpaceX IT MW behind 325k GPUs: lo 422, central 500, hi 650
$/facility kWh: TCO (most kWh/$) 2.06, SpaceX central 3.76, SpaceX fewest kWh/$ 5.63
work hours/yr central 1821 (lo 1767, hi 1871)
Destatis distance-class mean one-way km (cross-check): 16.4
commute mode-mix EF: 118.1 g CO2e/pkm
commute per work hour (central): 0.254 kg CO2e, 0.692 kWh
AI top-down: 22.3 Wh/$, 10.16 g CO2e/$, 0.078 L/$ (central)
AI bottom-up: 65.7 Wh/$, 29.90 g CO2e/$, 0.230 L/$ (central)
measured mix: $0.378/MTok; bottom-up on measured mix: 70.1 Wh/$
bottom-up / top-down g per $: 2.94x; notes-mix / measured-mix $ per MTok: 3.20x
total compute / revenue (9M 2026) = 0.566; vs cost of revenue: 3.91x (upper bound for adding training)
earlier session $229.58: top-down 2.33 kg, bottom-up 6.86 kg CO2e (central)

== Targets (central) ==
(a) work hour, full footprint         4.911 kg CO2e     12.78 kWh  78.0 L
(a) work hour, basic living           3.782 kg CO2e      9.84 kWh  60.1 L
(a) work hour, marginal               0.430 kg CO2e      1.28 kWh  n/a L
(b) PCBA order                       18.487 kg CO2e     30.29 kWh  147 L
   PCBA bare boards            3.60 kg    6.60 kWh   102.0 L
   PCBA ICs (75)               5.25 kg    6.00 kWh    45.0 L
   PCBA R/C/L (1,275)          0.19 kg    0.00 kWh     0.0 L
   PCBA discretes (120)        1.08 kg    0.00 kWh     0.0 L
   PCBA connectors (30)        0.60 kg    0.00 kWh     0.0 L
   PCBA SMT assembly           2.76 kg    4.76 kWh     0.0 L
   PCBA packaging              0.43 kg    0.00 kWh     0.0 L
   PCBA express air + road     4.57 kg   12.93 kWh     0.0 L
   PCBA per board (central): 3.70 kg CO2e
   PCBA all-low inputs: 7.9 kg CO2e
   PCBA all-high inputs: 59.9 kg CO2e

== Monte Carlo P5 / P50 / P95 ==
AI top-down  g CO2e/$: 6.40 / 11.01 / 18.91
AI bottom-up g CO2e/$: 20.77 / 40.41 / 86.46
(a) work hour, full footprint      kg CO2e: 4.578 / 4.970 / 5.473
(a) work hour, basic living        kg CO2e: 3.364 / 3.800 / 4.304
(a) work hour, marginal            kg CO2e: 0.161 / 0.371 / 0.686
(b) PCBA order                     kg CO2e: 16.668 / 21.728 / 29.485

== ANSWER: break-even (CO2e). central = all-central inputs; low/high = MC P5/P95 ==
target                             AI        |   $ low     $ c  $ high | MTok lo  MTok c MTok hi  MTok m | Pro win lo      c     hi
(a) work hour, full footprint      top-down  |     262     483     786 |     216     399     650   1,277 |          4    7.3   11.9
(a) work hour, full footprint      bottom-up |    57.5     164     242 |    47.5     136     200     434 |       0.87    2.5    3.7
(a) work hour, basic living        top-down  |     198     372     602 |     164     308     498     983 |          3    5.6    9.1
(a) work hour, basic living        bottom-up |    43.8     126     185 |    36.2     105     153     334 |       0.66    1.9    2.8
(a) work hour, marginal            top-down  |    12.6    42.4    76.8 |    10.4    35.0    63.4     112 |       0.19   0.64    1.2
(a) work hour, marginal            bottom-up |       3    14.4    23.0 |     2.5    11.9    19.0    38.0 |      0.045   0.22   0.35
(b) PCBA order                     top-down  |   1,079   1,819   3,659 |     891   1,504   3,024   4,808 |       16.3   27.6   55.4
(b) PCBA order                     bottom-up |     242     618   1,118 |     200     511     924   1,634 |        3.7    9.4   16.9
(MTok c = notes mix at $1.21/MTok; MTok m = measured session mix at $0.378/MTok)
(token-mix price alone ranges 1.12-1.30 $/MTok with the notes mix)

== Energy and water at the CO2e break-even (central; identical for both AI methods) ==
(a) work hour, full footprint     : AI  10.79 kWh   37.8 L | target  12.78 kWh  78.0 L | energy-based break-even: top-down $572  bottom-up $195
(a) work hour, basic living       : AI   8.31 kWh   29.1 L | target   9.84 kWh  60.1 L | energy-based break-even: top-down $441  bottom-up $150
(a) work hour, marginal           : AI   0.95 kWh    3.3 L | target   1.28 kWh   n/a L | energy-based break-even: top-down $57  bottom-up $19
(b) PCBA order                    : AI  40.62 kWh  142.2 L | target  30.29 kWh   147 L | energy-based break-even: top-down $1,357  bottom-up $461

== Decision rules (central, with MC P5-P95) ==
(a) work hour, full footprint      top-down : break even if $10 replaces >= 1.24 min [0.76-2.29]; one Pro window ($66) needs >= 8.2 min [5.0-15.1]
(a) work hour, full footprint      bottom-up: break even if $10 replaces >= 3.65 min [2.48-10.43]; one Pro window ($66) needs >= 24.1 min [16.4-68.8]
(a) work hour, basic living        top-down : break even if $10 replaces >= 1.61 min [1.00-3.03]; one Pro window ($66) needs >= 10.6 min [6.6-20.0]
(a) work hour, basic living        bottom-up: break even if $10 replaces >= 4.74 min [3.24-13.71]; one Pro window ($66) needs >= 31.3 min [21.4-90.5]
(a) work hour, marginal            top-down : break even if $10 replaces >= 14.17 min [7.82-47.80]; one Pro window ($66) needs >= 93.5 min [51.6-315.4]
(a) work hour, marginal            bottom-up: break even if $10 replaces >= 41.69 min [26.14-200.65]; one Pro window ($66) needs >= 275.2 min [172.5-1324.3]

== Scenarios (central otherwise) ==
home office, no commute, office energy not avoided: marginal 0.012 kg/h -> top-down $1.2, bottom-up $0.4 per hour; top-down g/$ 10.16
office worker, full average commute and office energy avoided: marginal 1.176 kg/h -> top-down $115.8, bottom-up $39.3 per hour; top-down g/$ 10.16
top-down with r_list = 1 (every token earns list price): marginal 0.430 kg/h -> top-down $25.8, bottom-up $14.4 per hour; top-down g/$ 16.66
top-down with inference on dedicated gas (ci 0.55): marginal 0.430 kg/h -> top-down $31.6, bottom-up $10.7 per hour; top-down g/$ 13.63

== Tornado: biggest drivers (ratio high/low of result; factor vs central at input low, high) ==
(a) work hour, full footprint / top-down:
   r_list         x 3.12  (1.91 .. 0.61)   A2 realised revenue per list-price $ [S1 revenue mix + assumption]
   usd_per_kwh    x 2.73  (0.55 .. 1.50)   A3 $ of compute per facility kWh [S4,S5,S6]
   ci_ai          x 1.57  (1.17 .. 0.75)   A8 grid kg CO2e/kWh for inference [S4,S12,S13,S14]
   fp             x 1.29  (0.90 .. 1.16)   H1 kg CO2e per capita per year [S21]
(a) work hour, full footprint / bottom-up:
   e_out          x 6.00  (2.00 .. 0.33)   A4 Wh per 1k output tokens incl. PUE [S7,S9,S11]
   m_ctx          x 1.93  (1.23 .. 0.64)   A5 long-context decode multiplier (Claude Code ~50-200k ctx)
   k_in           x 1.83  (1.28 .. 0.70)   A6 uncached input token energy / output token [S10,S11]
   k_cr           x 1.68  (1.11 .. 0.66)   A7 cache-read token energy / uncached input token
(a) work hour, marginal / top-down:
   commute_avoid  x 3.88  (0.41 .. 1.59)   H11 share of average commute avoided per hour not worked
   office_avoid   x 3.46  (0.62 .. 2.14)   H10 share of office energy avoided per hour not worked
   r_list         x 3.12  (1.91 .. 0.61)   A2 realised revenue per list-price $ [S1 revenue mix + assumption]
   commute_ef     x 3.02  (0.41 .. 1.24)   H13 commute EF multiplier on Destatis mode mix (1.4 ~ car only) [S33,S34]
(a) work hour, marginal / bottom-up:
   e_out          x 6.00  (2.00 .. 0.33)   A4 Wh per 1k output tokens incl. PUE [S7,S9,S11]
   commute_avoid  x 3.88  (0.41 .. 1.59)   H11 share of average commute avoided per hour not worked
   office_avoid   x 3.46  (0.62 .. 2.14)   H10 share of office energy avoided per hour not worked
   commute_ef     x 3.02  (0.41 .. 1.24)   H13 commute EF multiplier on Destatis mode mix (1.4 ~ car only) [S33,S34]
(b) PCBA order / top-down:
   r_list         x 3.13  (1.91 .. 0.61)   A2 realised revenue per list-price $ [S1 revenue mix + assumption]
   usd_per_kwh    x 2.73  (0.55 .. 1.50)   A3 $ of compute per facility kWh [S4,S5,S6]
   ic_kg          x 2.07  (0.84 .. 1.73)   P5 kg CO2e per IC incl. package [S48,S50,S51,S52]
   ci_ai          x 1.57  (1.17 .. 0.75)   A8 grid kg CO2e/kWh for inference [S4,S12,S13,S14]
(b) PCBA order / bottom-up:
   e_out          x 6.00  (2.00 .. 0.33)   A4 Wh per 1k output tokens incl. PUE [S7,S9,S11]
   ic_kg          x 2.07  (0.84 .. 1.73)   P5 kg CO2e per IC incl. package [S48,S50,S51,S52]
   m_ctx          x 1.93  (1.23 .. 0.64)   A5 long-context decode multiplier (Claude Code ~50-200k ctx)
   k_in           x 1.83  (1.28 .. 0.70)   A6 uncached input token energy / output token [S10,S11]

== Notes method reproduced (for comparison) ==
notes: 19.5 g/$; work hour 9000/2080 = 4.33 kg -> $222
```
