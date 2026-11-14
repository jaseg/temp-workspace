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
