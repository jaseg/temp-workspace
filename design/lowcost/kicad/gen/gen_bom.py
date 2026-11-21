"""BOM for one scope-fe board from the root netlist (export/scope-fe.net, written by gen_all.py).

Writes design/lowcost/docs/bom.csv and bom.md. Lines are grouped by value + footprint (+ DNP); MPN and
LCSC come from the symbol fields, prices from the PRICE table below (USD, qty 1 board).

Price sources (21 Nov 2026): lcsc.com product pages read in this session ("LCSC"), docs/research/prices.md
(LCSC / DigiKey / Mouser via Octopart), docs/research/opamps.md, kicad/README.md. "est" = estimate (typical
LCSC price for the class or an out-of-stock listing), not a quote. Not counted: PCB, assembly. The STM32G474CBT6
is on the board since 21 Nov 2026 and counted. PCB-only items (test pads, net ties, solder jumper, TLINE stubs) and the footprint-only programming
header J501 (Würth WR-WST 490107671612, no part fitted) are listed at 0 and not counted as fitted parts.
Usage: python3 gen_bom.py  (after gen_all.py)"""
import csv, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import schlib

NET = os.path.join(schlib.OUTDIR, "export", "scope-fe.net")
DOCS = os.path.abspath(os.path.join(schlib.OUTDIR, "..", "docs"))

# key: MPN-ish value (symbol value) -> (unit USD at the qty used on one board, source, status, MOQ, note)
L, PM, ES = "LCSC", "prices.md", "est"
FOOT = "footprint only"
PRICE = {
    "BUF802IRGTR": (5.89, "LCSC C4370628", "ok", 1, "72 in stock"),
    "GW1NZ-LV1QN48C6/I5": (6.68, "LCSC C5799569", "ok", 1, ""),
    "TLV3801": (5.13, "Mouser (prices.md)", "ok", 1, "LCSC 5.21, 54 in stock"),
    "TRF37D73": (1.50, "LCSC C2151367", "ok", 1, "LCSC stock 25: buy at Mouser 1.53 (7.3k)"),
    "GVA-84+": (2.99, "Mouser (prices.md)", "ok", 1, "no LCSC listing"),
    "TMUX136": (1.22, "DigiKey (prices.md)", "ok", 1, "LCSC 1.41"),
    "BAT15-04W": (0.3655, "LCSC C5380972 (10+)", "ok", 1, "1.5k in stock"),
    "COS3502": (0.3588, "LCSC C49304672 (5+)", "ok", 5, ""),
    "MS5351M": (0.91, "LCSC C1509083", "ok", 1, ""),
    "OPA197IDBVR": (0.75, "LCSC C221351", "ok", 1, ""),
    "TPH2501": (0.4311, "LCSC C126713 (5+)", "ok", 5, ""),
    "TP2272": (0.5044, "LCSC C39487549 TP2272-SO1R (5+)", "ok", 5, "TP2272-SR C95871 out of stock"),
    "SN65LVDS2": (1.01, "LCSC C38204", "ok", 1, ""),
    "LM27761": (1.231, "LCSC C129351", "ok", 1, ""),
    "BAT15-03W": (0.5388, "LCSC C5310874", "no stock", 1, "0 in stock; C533623 (E6327) 0.28 at 5+"),
    "AMS1117-3.3": (0.2032, "LCSC C6186 (5+)", "ok", 5, ""),
    "AP2112K-1.2": (0.2383, "LCSC C460310 (5+)", "ok", 5, ""),
    "LP2985-5.0": (0.291, "LCSC C74511 (5+)", "ok", 5, ""),
    "LP5907MFX-2.5": (0.337, "LCSC C165132", "ok", 1, ""),
    "LM337": (0.4359, "LCSC C19267471 (XBLW LM337S)", "ok", 1, "check SOT-223 pinout vs TI"),
    "MT3608": (0.0639, "LCSC C84817", "ok", 1, ""),
    "DLW21SN900HQ2L": (0.1479, "LCSC C97855 (5+)", "ok", 5, ""),
    "25MHz": (0.0946, "LCSC C9006 (5+)", "ok", 5, ""),
    "SS14 / B5819W": (0.0254, "LCSC C8598", "ok", 20, ""),
    "SMAJ5.0A": (0.0338, "LCSC C353442", "ok", 20, ""),
    "1.5A hold PTC": (0.0784, "LCSC C118413 1206L150THWR", "ok", 10, ""),
    "220R@100MHz 2A": (0.0277, "LCSC C85840", "no stock", 20, "BLM21PG221SN1D, 0 in stock"),
    "600R@100MHz 1A": (0.02, ES, "est", 50, "0805 1 A bead, LCSC # to assign"),
    "4.7uH 2A": (0.10, ES, "est", 5, "SRN4018-class, LCSC # to assign"),
    # programming header J501: plated holes only, the WR-WST cable connector plugs into the board (no part)
    "WR-WST 490107671612": (0.0, FOOT, "n/a", 0, "footprint only (Würth Redfit IDC, yanartas J3 pinout), no part"),
    "STM32G474CBT6": (4.11, "LCSC C730123 (search snapshot)", "ok", 1,
                      "2.64-4.11 at 1 pc in LCSC listings, ~3-5k in stock; CET6 C730125 11.27, 704 in stock"),
    "USBLC6-2SC6": (0.10, ES, "est", 5, "LCSC C7519 from memory, price not re-checked"),
    "green": (0.02, ES, "est", 20, "0603 green LED, LCSC # to assign"),
    "USB-C 16P": (0.20, ES, "est", 5, "HRO TYPE-C-31-M-12, LCSC C165948 from memory, price not re-checked"),
    "SIG_IN": (1.99, "LCSC C5356059 CON-SMA-EDGE-S", "est", 1, "0 in stock; Samtec/TE branded 4.47 (prices.md)"),
    "EXT_CLK": (1.99, "LCSC C5356059 CON-SMA-EDGE-S", "est", 1, "as SIG_IN"),
    "50k": (1.50, ES, "est", 1, "Bourns 3314J trimmer, distributor price not checked"),
    ("1k", "L_0402_1005Metric"): (0.0197, "LCSC C21516 BLM15HD102SN1D", "ok", 50, ""),
    ("47u", "L_1210_3225Metric"): (0.1632, "LCSC C701189 LQH32CN470K23L (5+)", "ok", 5, ""),
    ("2.2u", "L_0805_2012Metric"): (0.3667, "LCSC C341781 LQM21PN2R2MGHL (5+)", "ok", 5, ""),
    ("47u", "L_1008_2520Metric"): (0.10, ES, "est", 5, "1008 47 uH, LCSC # to assign"),
    ("120n", "L_0402_1005Metric"): (0.02, ES, "est", 50, "0402 high-SRF inductor, LCSC # to assign"),
}
# passive classes: (unit USD, MOQ) typical LCSC (verified on several C numbers in this session)
CLASS = {"R_0402": (0.0012, 100), "R_0603": (0.0018, 100), "R_0805": (0.003, 100),
         "C_0402_X7R": (0.0025, 100), "C_0402_C0G": (0.0019, 100), "C_0402_1u": (0.0056, 100),
         "C_0402_2.2u": (0.01, 50), "C_0603": (0.01, 50), "C_0805_10u": (0.0313, 20), "C_0805_22u": (0.1094, 20)}
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


def passive_price(ref, value, fp):
    size = re.search(r"_(\d{4})_", fp)
    size = size.group(1) if size else ""
    if ref.startswith("R"):
        return CLASS.get("R_" + size, (0.003, 100))
    if ref.startswith("C"):
        if size == "0402":
            if value.endswith("p"):
                return CLASS["C_0402_C0G"] if value != "47p" else (0.0044, 100)
            if value == "1u":
                return CLASS["C_0402_1u"]
            if value == "2.2u":
                return CLASS["C_0402_2.2u"]
            return CLASS["C_0402_X7R"]
        if size == "0603":
            return CLASS["C_0603"]
        if size == "0805":
            return CLASS["C_0805_22u"] if value == "22u" else CLASS["C_0805_10u"]
    return None


def main():
    groups = {}
    for c in comps():
        key = (c["value"], c["fp"], c["dnp"], c["ref"].rstrip("0123456789"))
        g = groups.setdefault(key, dict(refs=[], mpn="", lcsc=""))
        g["refs"].append(c["ref"])
        g["mpn"] = g["mpn"] or c["mpn"]
        g["lcsc"] = g["lcsc"] or c["lcsc"]
    rows = []
    for (value, fp, dnp, pre), g in groups.items():
        refs = sorted(g["refs"], key=lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r) or 0)))
        qty = len(refs)
        if pre in PCB_ONLY:
            p = (0.0, "PCB feature", "n/a", 0, "pad / net tie / jumper / stub, no part")
        else:
            p = PRICE.get((value, fp)) or PRICE.get(value)
            if p is None:
                pc = passive_price(refs[0], value, fp)
                if pc is None:
                    p = (0.0, "?", "MISSING", 0, "")
                else:
                    src = ("LCSC " + g["lcsc"] + " (class price)") if g["lcsc"] else "LCSC class price"
                    p = (pc[0], src, "ok" if g["lcsc"] else "est", pc[1], "" if g["lcsc"] else "LCSC # to assign")
        unit, src, status, moq, note = p
        if dnp:
            status, note = "DNP", ("not fitted; " + note).strip("; ")
        line = 0.0 if dnp else unit * qty
        first = 0.0 if dnp else unit * max(qty, moq)
        rows.append(dict(qty=qty, refs=" ".join(refs), value=value, footprint=fp, mpn=g["mpn"], lcsc=g["lcsc"],
                         unit=unit, line=line, first_order=first, source=src, status=status, note=note))
    rows.sort(key=lambda r: -r["line"])
    total = sum(r["line"] for r in rows)
    first = sum(r["first_order"] for r in rows)
    est = sum(r["line"] for r in rows if r["status"] in ("est",))
    os.makedirs(DOCS, exist_ok=True)
    cols = ["qty", "refs", "value", "footprint", "mpn", "lcsc", "unit", "line", "first_order", "source", "status",
            "note"]
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
    out = [
        "# scope-fe BOM, one board (generated by `kicad/gen/gen_bom.py`; do not edit by hand)", "",
        f"From the root netlist `kicad/export/scope-fe.net` ({nparts} fitted parts, {len(rows)} lines). Prices in USD "
        "for one board at the single-board quantity (unit price x quantity), lowest of LCSC / DigiKey / Mouser as "
        "found on 21 Nov 2026: LCSC product pages read on that date, the rest from `docs/research/prices.md` and "
        "`docs/research/opamps.md`. Status `est` = estimate (class price or out-of-stock listing), `no stock` = "
        "listed price but 0 in stock. Full table: `docs/bom.csv`.", "",
        "## Total", "",
        "| | USD |", "|---|---|",
        f"| **Parts total, 1 board** | **{total:.2f}** |",
        f"| of which estimates (`est`) | {est:.2f} |",
        f"| R/C passives (included) | {sums.get('R/C passives', 0):.2f} |",
        "| Budget (SPEC, MCU included, PCB excluded) | 80.00 |",
        f"| **Margin** | **{80 - total:.2f}** ({(80 - total) / 80 * 100:.0f} %) |",
        f"| First order incl. minimum order quantities (passives 20-100 pcs, ICs 5 pcs) | {first:.2f} |", "",
        "Not included: PCB (4-layer JLC04161H-7628, impedance control), assembly, "
        "shipping, USB-C supply.", "",
        "## Ten most expensive lines", "",
        "| Line USD | Qty | Part | Source | Status |", "|---|---|---|---|---|"]
    for r in top:
        out.append(f"| {r['line']:.2f} | {r['qty']} | {r['value']} {('(' + r['mpn'] + ')') if r['mpn'] and r['mpn'] != r['value'] and len(r['mpn']) < 30 else ''} | {r['source']} | {r['status']} |")
    out += ["", "## If the budget gets tight: cheapest cuts", "",
            "The board is under budget; these are the options in order of cost per USD saved, should prices move:",
            "",
            "1. **SMA connectors** (2 x ~2.0 est.): generic LCSC edge-launch SMAs are 0.5-1.0; saves ~2. Check "
            "the 1.6 mm board fit and >3 GHz rating.",
            "2. **GVA-84+ -> TRF37D73** in the phase-strobe chains (2 x 2.99 -> 2 x 1.50): saves ~3, but "
            "sim/strobe/RESULT.md gives only 2.15 V per line (below the 2.75 V the taps need with the 80 ps stub). "
            "Not recommended.",
            "3. **TLV3801 -> TLV3601** (LCSC 4.65, single-ended output): saves ~0.5, needs a redesign of the "
            "LVDS split. Not worth it.",
            "4. **50k trimmer -> fixed 33.2k** (RV101): saves ~1.5 if the VOFS/LF-gain trim is done in software.",
            "", "## All lines", "",
            "| Qty | Refs | Value | Footprint | MPN | LCSC | Unit | Line | Source | Status | Note |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r["refs"]):
        refs = r["refs"] if len(r["refs"]) < 60 else r["refs"].split()[0] + " ... " + r["refs"].split()[-1]
        out.append(f"| {r['qty']} | {refs} | {r['value']} | {r['footprint']} | {r['mpn']} | {r['lcsc']} | "
                   f"{r['unit']:.4f} | {r['line']:.3f} | {r['source']} | {r['status']} | {r['note']} |")
    open(os.path.join(DOCS, "bom.md"), "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    rows, total, first, est, nparts = main()
    for r in rows[:12]:
        print(f"  {r['line']:7.2f}  {r['qty']:3d} x {r['value']:20s} {r['source']}")
    print("lines without price:", [r["value"] for r in rows if r["status"] == "MISSING"])
