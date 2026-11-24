"""BOM for one scope-fe board from the root netlist (export/scope-fe.net, written by gen_all.py).

Writes design/lowcost/docs/bom.csv and bom.md. Lines are grouped by value + footprint + LCSC number (+ DNP); MPN and
LCSC come from the symbol fields (generators, common.py), stock and prices from lcsc_parts.py (verified on lcsc.com,
date in that file) or, where lower, the non-LCSC offers in ALT (docs/research/prices.md, 21 Nov 2026).
Not counted: PCB, assembly. PCB-only items (test pads, net ties, solder jumpers, TLINE stubs) and the footprint-only
programming header J501 (Würth WR-WST 490107671612, no part fitted, not on LCSC) are listed at 0 and not counted.
Usage: python3 gen_bom.py  (after gen_all.py)"""
import csv, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import schlib

NET = os.path.join(schlib.OUTDIR, "export", "scope-fe.net")
DOCS = os.path.abspath(os.path.join(schlib.OUTDIR, "..", "docs"))

# LCSC data (stock, price ladder, MPN) verified on lcsc.com on the date in lcsc_parts.py; the LCSC number of each
# part is the symbol field LCSC (generators / common.py). Unit price = LCSC ladder price at max(board qty, LCSC
# minimum order), unless a non-LCSC offer below is lower.
from lcsc_parts import PARTS, VERIFIED, METHOD
L, PM, ES = "LCSC", "prices.md", "est"
FOOT = "footprint only"
# non-LCSC offers (USD, source) from docs/research/prices.md (21 Nov 2026); used when lower than the LCSC price
ALT = {
    "GVA-84+": (2.99, "Mouser (prices.md)"),
    "TLV3801": (5.13, "Mouser (prices.md)"),
    "TMUX136": (1.22, "DigiKey (prices.md)"),
    "TRF37D73": (1.53, "Mouser (prices.md, 7.3k stock)"),
}
NOTE = {
    "BAT15-03W": "0 at LCSC and JLC (24 Nov 2026): order DigiKey BAT1503WE6327HTSA1CT-ND",
    "STM32G474CBT6": "CET6 C730125 as 2nd choice",
    "0.47u": "FXL0420-R47-M = XR0420 land (a 2.2 / b 5.2 / c 2.5 mm); alt. XR0420-R47M C5307593 (low stock)",
    "220R@100MHz 2A": "BLM21PG221SH1D (SN1D C85840 0 stock)",
    "SIG_IN": "Samtec SMA-J-P-H-ST-EM1 = footprint SMA_Samtec_SMA-J-P-X-ST-EM1",
    "EXT_CLK": "Samtec SMA-J-P-H-ST-EM1 = footprint SMA_Samtec_SMA-J-P-X-ST-EM1",
    "WR-WST 490107671612": "footprint only (Würth Redfit IDC, yanartas J3 pinout), no part; not on LCSC: RS 197-3364",
    "USBLC6-2SC6": "may be left unfitted",
}
PCB_ONLY = ("TP", "NT", "TL", "JP")


def norm(v):
    return {"1.00k": "1k", "10.0k": "10k"}.get(v, v)


def comps():
    tree = schlib.parse_sexpr(open(NET).read())
    for c in schlib.find(schlib.find(tree, "components")[0], "comp"):
        f = lambda k: (str(schlib.find(c, k)[0][1]) if schlib.find(c, k) else "")
        props = {}
        for p in schlib.find(c, "property"):
            v = schlib.find(p, "value")
            props[str(schlib.find(p, "name")[0][1])] = str(v[0][1]) if v else True
        yield dict(ref=f("ref"), value=norm(f("value")), fp=f("footprint").split(":")[-1],
                   mpn=props.get("MPN", ""), lcsc=props.get("LCSC", ""), dnp="dnp" in props)


def ladder_price(code, n):
    lad = PARTS[code]["ladder"]
    price = lad[0][1]
    for q, pr in lad:
        if q <= n:
            price = pr
    return price


def near10(code):
    q, pr = min(PARTS[code]["ladder"], key=lambda x: (abs(x[0] - 10), x[0]))
    return f"{pr:.4f} @{q}"


def main():
    groups = {}
    for c in comps():
        key = (c["value"], c["fp"], c["dnp"], c["ref"].rstrip("0123456789"), c["lcsc"])
        g = groups.setdefault(key, dict(refs=[], mpn="", lcsc=c["lcsc"]))
        g["refs"].append(c["ref"])
        g["mpn"] = g["mpn"] or c["mpn"]
    # board quantity per LCSC number (lines of one part bought together)
    perpart = {}
    for (value, fp, dnp, pre, code), g in groups.items():
        if not dnp:
            perpart[code] = perpart.get(code, 0) + len(g["refs"])
    rows = []
    for (value, fp, dnp, pre, _l), g in groups.items():
        refs = sorted(g["refs"], key=lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r) or 0)))
        qty = len(refs)
        code = g["lcsc"]
        stock, p10 = "", ""
        if pre in PCB_ONLY:
            lcsc = "n/a (PCB feature)"
            p = (0.0, "PCB feature", "n/a", 0, "pad / net tie / jumper / stub, no part")
        elif code in PARTS:
            d = PARTS[code]
            lcsc, stock, p10 = code, d["stock"], near10(code)
            moq = max(d["moq"] or 1, 1)
            n = max(perpart.get(code, qty), moq)
            unit, src = ladder_price(code, n), f"LCSC {code} ({n}+)"
            alt = ALT.get(value)
            if alt and alt[0] < unit:
                unit, src, moq = alt[0], alt[1], 1
            status = "ok" if d["stock"] >= qty else "no stock"
            p = (unit, src, status, moq, NOTE.get(value, ""))
        elif code == "NA":
            lcsc = "not on LCSC"
            p = (0.0, FOOT, "n/a", 0, NOTE.get(value, ""))
        else:
            lcsc = code or "MISSING"
            p = (0.0, "?", "MISSING", 0, "no verified LCSC number")
        unit, src, status, moq, note = p
        if dnp:
            status, note = "DNP", ("not fitted; " + note).strip("; ")
        line = 0.0 if dnp else unit * qty
        first = 0.0 if dnp else unit * max(qty, moq)
        rows.append(dict(qty=qty, refs=" ".join(refs), value=value, footprint=fp, mpn=g["mpn"], lcsc=lcsc,
                         lcsc_stock=stock, lcsc_price_near10=p10, unit=unit, line=line, first_order=first,
                         source=src, status=status, note=note))
    rows.sort(key=lambda r: -r["line"])
    total = sum(r["line"] for r in rows)
    first = sum(r["first_order"] for r in rows)
    est = sum(r["line"] for r in rows if r["status"] in ("est",))
    os.makedirs(DOCS, exist_ok=True)
    cols = ["qty", "refs", "value", "footprint", "mpn", "lcsc", "lcsc_stock", "lcsc_price_near10", "unit", "line",
            "first_order", "source", "status", "note"]
    with open(os.path.join(DOCS, "bom.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({**r, "unit": f"{r['unit']:.4f}", "line": f"{r['line']:.3f}",
                        "first_order": f"{r['first_order']:.3f}"})
    nparts = sum(r["qty"] for r in rows if not r["refs"].startswith(PCB_ONLY) and r["status"] != "DNP"
                 and r["source"] != FOOT)
    write_md(rows, total, first, est, nparts)
    print(f"BOM: {len(rows)} lines, {nparts} fitted parts, total {total:.2f} USD (est part {est:.2f}), "
          f"first order with MOQs {first:.2f} USD")
    return rows, total, first, est, nparts


def write_md(rows, total, first, est, nparts):
    def cat(r):
        v, fp, ref = r["value"], r["footprint"], r["refs"]
        if r["status"] == "DNP":
            return "DNP"
        if ref.startswith(PCB_ONLY) or r["source"] == FOOT:
            return "PCB only"
        if ref[0] in "RC" and not ref.startswith("CON") and r["unit"] < 0.2:
            return "R/C passives"
        return "Parts"
    sums = {}
    for r in rows:
        sums[cat(r)] = sums.get(cat(r), 0) + r["line"]
    top = [r for r in rows if r["line"] > 0][:10]
    notlcsc = [r for r in rows if r["lcsc"] == "not on LCSC"]
    nostock = [r for r in rows if r["status"] == "no stock" or (r["status"] == "DNP" and r["lcsc_stock"] == 0)]
    out = [
        "# scope-fe BOM, one board (generated by `kicad/gen/gen_bom.py`; do not edit by hand)", "",
        f"From the root netlist `kicad/export/scope-fe.net` ({nparts} fitted parts, {len(rows)} lines). Prices in USD "
        "for one board: LCSC ladder price at the board quantity (or the LCSC minimum order), verified on "
        f"{VERIFIED}; a non-LCSC offer (`docs/research/prices.md`) is used where it is lower. `no stock` = listed "
        "but fewer in stock than needed. Full table: `docs/bom.csv`.", "",
        "## Total", "",
        "| | USD |", "|---|---|",
        f"| **Parts total, 1 board** | **{total:.2f}** |",
        f"| of which estimates (`est`) | {est:.2f} |",
        f"| R/C passives (included) | {sums.get('R/C passives', 0):.2f} |",
        "| Budget (SPEC, MCU included, PCB excluded) | 80.00 |",
        f"| **Margin** | **{80 - total:.2f}** ({(80 - total) / 80 * 100:.0f} %) |",
        f"| First order incl. LCSC minimum order quantities | {first:.2f} |", "",
        "Not included: PCB (6-layer JLC06161H-3313, impedance control), assembly, "
        "shipping, USB-C supply.", "",
        "## LCSC verification", "",
        f"- Date: {VERIFIED}. Every line with a part carries an LCSC number (column LCSC); PCB features are `n/a`.",
        f"- How: {METHOD}. Checked per part: MPN, value, tolerance, dielectric / voltage rating, package against the "
        "board footprint, LCSC stock (column Stock) and the price at the ladder step nearest 10 pcs (column P~10).",
        "- Generic passives: UNI-ROYAL 0402WGF 1 % thick film, 0.1 % 25 ppm/K thin film (YAGEO RT0402BRD07 where "
        "stocked), FH / Murata / KEMET C0G, Samsung / FH X5R-X7R; one number per value / package / rating "
        "(`kicad/gen/common.py`).",
        "- Not on LCSC: " + ("; ".join(f"{r['refs']} {r['mpn'] or r['value']} ({r['note']})" for r in notlcsc)
                             or "none") + ".",
        "- On LCSC but short of stock: " + ("; ".join(f"{r['refs']} {r['mpn'] or r['value']} {r['lcsc']} "
                                                       f"(stock {r['lcsc_stock']}): {r['note']}" for r in nostock)
                                             or "none") + ".",
        "- Listed in the task as possibly missing but found on LCSC: GVA-84+ C5445191, BUF802 C4370628, TRF37D73 "
        "C2151367, TLV3801 C3658765, TMUX136 C2673277, TPS63802 C2845237, LM27762 C473398, TPS62A01A C5181455, "
        "GW1NZ-LV1QN48 C5799569, MS5351M C1509083, TPH2501 C126713, COS3502 C49304672, BAT15-04W C5380972, "
        "BAT15-03W C5310874 (0 stock), DLW21SN900HQ2L C97855, SMA Samtec SMA-J-P-H-ST-EM1 C5199907, "
        "USB-C HRO TYPE-C-31-M-12 C165948, STM32G474CBT6 C730123.",
        "- Changes made by the verification (24 Nov 2026), footprints unchanged except where noted (none): "
        "R603 459k -> **499k** and R604 49.9k -> **54.2k** (0.1 %, no stocked 459k 0.1 % 0402; VOUT 5.103 V); "
        "C101 1.5 pF is +/-0.1 pF 100 V (no stocked +/-0.05 pF 100 V 0402); C303 1 nF now C0G as its note asks "
        "(was the X7R C1523); C308 / C311 / C312 1 uF now X7R as their notes ask; C618 -> C29936 25 V X7R and "
        "C619 -> C99229 16 V X5R (C15849 / C19666 had 0 LCSC stock); 0.1 % resistors R117 / R118 / R732 carried "
        "1 % numbers, now 0.1 % parts; R725 / R726 (0603) carried an 0402 number; L601 FXL0420-R47-M (same land as "
        "XR0420); FB601 BLM21PG221SH1D; J101 / J102 Samtec SMA-J-P-H-ST-EM1 (the footprint's own part).", "",
        "## Ten most expensive lines", "",
        "| Line USD | Qty | Part | Source | Status |", "|---|---|---|---|---|"]
    for r in top:
        out.append(f"| {r['line']:.2f} | {r['qty']} | {r['value']} {('(' + r['mpn'] + ')') if r['mpn'] and r['mpn'] != r['value'] and len(r['mpn']) < 30 else ''} | {r['source']} | {r['status']} |")
    out += ["", "## If the budget gets tight: cheapest cuts", "",
            "The board is under budget; these are the options in order of cost per USD saved, should prices move:",
            "",
            "1. **SMA connectors** (2 x 4.68, Samtec SMA-J-P-H-ST-EM1 C5199907): generic LCSC edge-launch SMAs "
            "are 0.5-2.0 (the RF Solutions CON-SMA-EDGE-S C5356059 was out of stock on 24 Nov 2026); saves up to "
            "~8, but needs a footprint check (1.6 mm board fit, >3 GHz rating).",
            "2. **GVA-84+ -> TRF37D73** in the phase-strobe chains: saves ~3, but "
            "sim/strobe/RESULT.md gives only 2.15 V per line (below the 2.75 V the taps need with the 80 ps stub). "
            "Not recommended.",
            "3. **TLV3801 -> TLV3601** (single-ended output): saves ~0.5, needs a redesign of the "
            "LVDS split. Not worth it.",
            "4. **50k trimmer -> fixed 33.2k** (RV101): saves ~0.5 if the VOFS/LF-gain trim is done in software.",
            "5. **300k / 280k 0.1 %** (R114-R116, R613, R605: 0.37-0.38 each, low-stock Vishay / TE parts): "
            "a 0.1 % 50 ppm/K or 0.5 % part would save ~1.5.",
            "", "## All lines", "",
            "| Qty | Refs | Value | Footprint | MPN | LCSC | Stock | P~10 | Unit | Line | Source | Status | Note |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r["refs"]):
        refs = r["refs"] if len(r["refs"]) < 60 else r["refs"].split()[0] + " ... " + r["refs"].split()[-1]
        out.append(f"| {r['qty']} | {refs} | {r['value']} | {r['footprint']} | {r['mpn']} | {r['lcsc']} | "
                   f"{r['lcsc_stock']} | {r['lcsc_price_near10']} | "
                   f"{r['unit']:.4f} | {r['line']:.3f} | {r['source']} | {r['status']} | {r['note']} |")
    open(os.path.join(DOCS, "bom.md"), "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    rows, total, first, est, nparts = main()
    for r in rows[:12]:
        print(f"  {r['line']:7.2f}  {r['qty']:3d} x {r['value']:20s} {r['source']}")
    print("lines without price:", [r["value"] for r in rows if r["status"] == "MISSING"])
