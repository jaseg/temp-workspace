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
