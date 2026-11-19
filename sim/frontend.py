"""ngspice model of one channel of the yanartas-sensors sampling front end.

Builds a transient deck for channel 1 (both halves of the differential pair)
of sensing/yanartas-pillowbox-sensing.kicad_sch, with reference designators
and trace lengths taken from the schematic and layout (see ../extracted/).

Two topologies:
  redriver  as drawn: FPGA -> 10R -> 220n -> PI3HDX12311 -> 220n -> ...
  direct    U2 removed, each RX pad linked to its TX pad, so the FPGA pin
            drives the splitter and the strobe clip lines itself.

Node suffix _p/_n is the half of the differential pair.
"""
from __future__ import annotations

import dataclasses
import os
import re
import subprocess
import tempfile

PS_PER_MM = 6.05e-12   # 0.36 mm microstrip over 0.21 mm 7628, er 4.4 (Hammerstad-Jensen)
Z0 = 50.0              # single-ended trace impedance, odd-mode impedance of the 100 R pairs
GNDS = 1.65            # virtual ground from U17
LS_TD, LS_Z0 = 30.9 * 5.9e-12, 80.0
LS_C, LS_L = LS_TD / LS_Z0, LS_TD * LS_Z0


@dataclasses.dataclass
class Params:
    topology: str = "redriver"      # "redriver" | "direct"
    stim: str = "fpga"              # "fpga" | "ideal" (1 ps step straight into SPL_HS, test bench only)
    ideal_step: float = 0.2         # V, step height of the ideal source (open circuit)

    # FPGA output buffer (GW1NZ bank 1), Thevenin model. See README for where the numbers come from.
    vccio: float = 1.2
    fpga_rout: float = 30.0         # ohm
    fpga_tr: float = 400e-12        # 20-80 % of the unloaded buffer ramp
    fpga_cpin: float = 3e-12        # die + package

    # PI3HDX12311 behavioural model
    rd_gain_db: float = 0.0         # flat gain
    rd_eq_db: float = 0.0           # CTLE peaking at rd_eq_f
    rd_eq_f: float = 6e9
    rd_bw: float = 9e9              # -3 dB of the two output poles together
    rd_vlin: float = 1.0            # differential output swing where it compresses, Vpp
    rd_delay: float = 80e-12

    # Sampling bridge
    vbias: float = 0.30             # VBIAS_K = GNDS + vbias, VBIAS_A = GNDS - vbias
    r_bridge: float = 91.0          # R3..R6
    c_hold: float = 10e-12          # C27 / C48
    c_opamp: float = 3e-12          # OPA4354 input, common-mode + differential

    # What hangs on the TDR port
    mesh_td: float = 1.5e-9
    mesh_term: float = 1e9          # ohm at the far end (open by default)

    # Timing (s)
    t_prep: float = 1e-9            # half-swing edge that puts the AC coupling caps in their mid-swing state
    t_stim: float = 12e-9           # stimulus edge at the FPGA pin
    t_strobe: float = 12e-9         # strobe edge at the FPGA pin
    t_tail: float = 4e-9
    tstep: float = 1e-12
    tmax: float = 2e-12

    # Hold node start voltages for the shooting solver
    v_ls_p: float = GNDS
    v_ls_n: float = GNDS


def tr_full(tr_20_80: float) -> float:
    """0-100 % time of a linear ramp with the given 20-80 % time."""
    return tr_20_80 / 0.6


class Deck:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.n = 0

    def add(self, s: str) -> None:
        self.lines.append(s)

    def uid(self) -> int:
        self.n += 1
        return self.n

    def trace(self, a: str, b: str, mm: float, z0: float = Z0, td: float | None = None, sec: float = 3e-12) -> None:
        """A length of PCB trace as an LC ladder with sections of at most `sec` delay
        (cut-off 1/(pi*sec), about 100 GHz). ngspice's lossless T element would not
        converge next to the diodes."""
        td = mm * PS_PER_MM if td is None else td
        n = max(1, -(-td // sec).__int__())
        i = self.uid()
        l, c = td * z0 / n, td / z0 / n
        prev = a
        for k in range(n):
            nxt = b if k == n - 1 else f"tl{i}_{k}"
            self.add(f"Ctl{i}_{k} {prev} 0 {c / 2 if k == 0 else c:.5g}")
            self.add(f"Ltl{i}_{k} {prev} {nxt} {l:.5g}")
            prev = nxt
        self.add(f"Ctl{i}_e {b} 0 {c / 2:.5g}")

    def cap0402(self, name: str, a: str, b: str, val: str) -> None:
        """MLCC with its mounted inductance."""
        self.add(f"C{name} {a} {name}_x {val}")
        self.add(f"Rdc{name} {a} {name}_x 1g")
        self.add(f"L{name} {name}_x {name}_y 0.4n")
        self.add(f"Resr{name} {name}_y {b} 0.05")


MODELS = r"""
* Infineon BAT15 series chip model D315 v7.0 (2003), one diode of a BAT15-04W
.model bat15 d(is=74n n=1.07 rs=5.0 xti=1.5 eg=0.59 cjo=138.5f m=0.138 vj=0.224 fc=0.5 tt=3p bv=4.2 ibv=100u)

* One diode with its share of the SOT323 package: datasheet LS 1.4 nH over the two
* diodes in series, and C(0 V) 0.3 pF typ of which the chip is 0.14 pF
.subckt dpk a k
Lb a a1 0.7n
D1 a1 k bat15
R1 a1 k 15meg
Cp a k 0.16p
.ends

* PI3HDX12311 channel, behavioural: 50 R input termination, flat gain, one CTLE zero,
* two poles, tanh compression, 50 R source-terminated outputs.
.subckt redrv inp inn outp outn params: g=1 zboost=1 fz=3g fp=9g vlin=1 td=80p
Rtp inp vcmi 50
Rtn inn vcmi 50
Vcmi vcmi 0 2.0
Cip inp 0 0.3p
Cin inn 0 0.3p
* CTLE: (1 + s/wz)/(1 + s/wp) with wz = wp/zboost, realised as an R-(R||C) divider
Ein e1 0 inp inn {g*zboost}
Rz1 e1 e2 {(zboost-1+1e-6)*1k}
Cz1 e1 e2 {1/(6.2832*fz*(zboost-1+1e-6)*1k)}
Rz2 e2 0 1k
* two identical poles
Eb1 e3 0 e2 0 1
Rp1 e3 e4 1k
Cp1 e4 0 {1/(6.2832*fp*1k)}
Eb2 e5 0 e4 0 1
Rp2 e5 e6 1k
Cp2 e6 0 {1/(6.2832*fp*1k)}
* latency
Eb3 e7 0 e6 0 1
Rd1 e7 e8 50
Td e8 0 e9 0 Z0=50 TD={td}
Rd2 e9 0 50
* compression; e9 carries half the signal because of the matched delay line
Bo e10 0 V={vlin/2*tanh(4*v(e9)/vlin)}
Eopc op_ 0 value={v(e10)+2.6}
Eonc on_ 0 value={-v(e10)+2.6}
Rop op_ outp 50
Ron on_ outn 50
Cop outp 0 0.3p
Con outn 0 0.3p
.ends
"""


def build(p: Params, probes: list[str] | None = None, outfile: str | None = None) -> str:
    d = Deck()
    d.add("* yanartas-sensors sampling front end, channel 1")
    d.add(MODELS)
    d.add(f"Vgnds gnds 0 {GNDS}")
    d.add(f"Vbk vbias_k 0 {GNDS + p.vbias}")
    d.add(f"Vba vbias_a 0 {GNDS - p.vbias}")

    trf = tr_full(p.fpga_tr)
    mid, lo, hi = p.vccio / 2, 0.0, p.vccio

    def fpga_src(name: str, node: str, t_edge: float, rising: bool) -> None:
        """Buffer starts mid-swing (so the DC solution leaves the coupling caps where a
        50 % duty waveform would), steps to its idle level at t_prep and makes the
        edge under test at t_edge."""
        a, b = (lo, hi) if rising else (hi, lo)
        d.add(f"V{name} {name}_e 0 pwl(0 {mid} {p.t_prep:.6g} {mid} {p.t_prep + trf / 2:.6g} {a} "
              f"{t_edge:.6g} {a} {t_edge + trf:.6g} {b})")
        d.add(f"R{name} {name}_e {node} {p.fpga_rout}")
        d.add(f"C{name} {node} 0 {p.fpga_cpin}")

    def gz(db: float) -> float:
        return 10 ** (db / 20)

    def redriver(name: str, pre: str) -> None:
        """U2 channel between <pre>_rc_* and <pre>_b_*."""
        if p.topology == "redriver":
            fp = p.rd_bw / 0.6436           # two identical poles: f3dB = fp * sqrt(sqrt(2) - 1)
            zb = gz(p.rd_eq_db)
            d.add(f"X{name} {pre}_rc_p {pre}_rc_n {pre}_b_p {pre}_b_n redrv "
                  f"g={gz(p.rd_gain_db):.4g} zboost={zb:.4g} fz={p.rd_eq_f / max(zb, 1.0):.4g} fp={fp:.4g} "
                  f"vlin={p.rd_vlin} td={p.rd_delay}")
        else:
            # U2 not fitted, RX pad linked to TX pad across the 2.85 mm package
            for h in "pn":
                d.add(f"L{name}{h} {pre}_rc_{h} {pre}_b_{h} 1n")

    # ---------------------------------------------------------------- stimulus
    for h, rising in (("p", True), ("n", False)):
        if p.stim == "fpga":
            fpga_src(f"fs{h}", f"stim_a_{h}", p.t_stim, rising)
            d.trace(f"stim_a_{h}", f"r78_{h}", 8.53)
            d.add(f"R78{h} r78_{h} stim_r_{h} 10")
            d.cap0402(f"c24{h}", f"stim_r_{h}", f"c24o_{h}", "220n")
            d.trace(f"c24o_{h}", f"stim_rc_{h}", 5.72)
    if p.stim == "fpga":
        redriver("u2a", "stim")
    for h, rising in (("p", True), ("n", False)):
        if p.stim == "fpga":
            d.trace(f"stim_b_{h}", f"c1i_{h}", 7.96)
            d.cap0402(f"c1{h}", f"c1i_{h}", f"stim_c_{h}", "220n")
            d.trace(f"stim_c_{h}", f"r7i_{h}", 2.46)
            d.add(f"R7{h} r7i_{h} star_{h} 16")
            d.add(f"R9{h} star_{h} r9o_{h} 16")
            d.trace(f"r9o_{h}", f"hs_{h}", 1.32)
        else:
            a, b = (-p.ideal_step / 2, p.ideal_step / 2) if rising else (p.ideal_step / 2, -p.ideal_step / 2)
            d.add(f"Vid{h} id_{h} gnds pwl(0 {a} {p.t_stim:.6g} {a} {p.t_stim + 1e-12:.6g} {b})")
            d.add(f"Rid{h} id_{h} hs_{h} 50")
        # splitter star point, DC return and TDR port
        d.add(f"R92{h} star_{h} gnds 10k")
        d.add(f"R8{h} star_{h} r8o_{h} 16")
        if p.stim != "fpga":
            # test bench: TDR port simply terminated
            d.add(f"Rtb{h} r8o_{h} gnds 50")
            continue
        d.trace(f"r8o_{h}", f"tdr_cpl_{h}", 8.94)
        d.cap0402(f"c61{h}", f"tdr_cpl_{h}", f"tdr_{h}", "220n")
        d.add(f"R94{h} tdr_{h} gnds 10k")
        d.trace(f"tdr_{h}", f"u10a_{h}", 7.5)
        # U10 TMUXHS4212 channel
        d.add(f"Cu10a{h} u10a_{h} 0 0.5p")
        d.add(f"Ru10{h} u10a_{h} u10b_{h} 8")
        d.add(f"Cu10b{h} u10b_{h} 0 0.5p")
        d.trace(f"u10b_{h}", f"mesh_end_{h}", 0, td=p.mesh_td, sec=5e-12)
        d.add(f"Rterm{h} mesh_end_{h} gnds {p.mesh_term:.6g}")

    # ------------------------------------------------------------------ strobe
    # The bridges conduct when the anode rail (STROBE_C_1N side) goes up and the
    # cathode rail (STROBE_C_1P side) goes down.
    for h, rising in (("p", False), ("n", True)):
        fpga_src(f"fb{h}", f"strobe_a_{h}", p.t_strobe, rising)
        d.trace(f"strobe_a_{h}", f"r80_{h}", 3.49)
        d.add(f"R80{h} r80_{h} strobe_r_{h} 10")
        d.cap0402(f"c50{h}", f"strobe_r_{h}", f"c50o_{h}", "220n")
        d.trace(f"c50o_{h}", f"strobe_rc_{h}", 4.51)
    redriver("u2b", "strobe")
    for h in "pn":
        d.trace(f"strobe_b_{h}", f"c8i_{h}", 12.56)
        d.cap0402(f"c8{h}", f"c8i_{h}", f"strobe_c_{h}", "220n")
        d.trace(f"strobe_c_{h}", f"nt_{h}", 6.41)
        # clip line: shorted stub, 13.3 mm to C69/C71 across the pair, 3 mm more to C73/C74 to ground
        d.trace(f"nt_{h}", f"clip_{h}", 13.3)
        d.trace(f"clip_{h}", f"clipe_{h}", 3.0)
        d.cap0402(f"c74{h}", f"clipe_{h}", "0", "220n")
    d.cap0402("c69", "clip_p", "clip_n", "1n")
    d.cap0402("c71", "clip_p", "clip_n", "220n")
    d.add("R102 clip_p vbias_k 1k")
    d.add("R99 clip_n vbias_a 1k")

    # ----------------------------------------------------------------- bridges
    # one bridge per half: D1/D2 on SPL_*_1P, D3/D4 on SPL_*_1N
    for h, v0 in (("p", p.v_ls_p), ("n", p.v_ls_n)):
        d.trace("nt_p", f"rk_{h}", 1.1)
        d.trace("nt_n", f"ra_{h}", 1.4)
        d.add(f"Rk{h} rk_{h} rko_{h} {p.r_bridge}")
        d.add(f"Ra{h} ra_{h} rao_{h} {p.r_bridge}")
        d.trace(f"rko_{h}", f"kk_{h}", 5.85)
        d.trace(f"rao_{h}", f"ka_{h}", 5.85)
        for side in ("ls", "hs"):
            d.trace(f"kk_{h}", f"kk_{side}_{h}", 1.47)
            d.trace(f"ka_{h}", f"ka_{side}_{h}", 1.47)
            d.add(f"Xda_{side}_{h} ka_{side}_{h} {side}_{h} dpk")
            d.add(f"Xdk_{side}_{h} {side}_{h} kk_{side}_{h} dpk")
        # Hold cap at the bridge, then 30.9 mm of 0.15 mm trace (about 80 R) to U13 as a single
        # pi section. It rings at about 1 GHz after every strobe, which U13 never sees, so the
        # settled hold voltage is taken as the charge-weighted mean of the two ends (see run()).
        d.add(f"Ch{h} ls_{h} 0 {p.c_hold + LS_C / 2}")
        d.add(f"Lls{h} ls_{h} amp_{h} {LS_L}")
        d.add(f"Camp{h} amp_{h} 0 {p.c_opamp + LS_C / 2}")
        d.add(f".ic v(ls_{h})={v0:.9g} v(amp_{h})={v0:.9g}")

    # always stop the same time after the strobe, so every delay point sees the same hold time
    tend = p.t_strobe + p.t_tail
    d.add(".options klu reltol=3e-4 abstol=1e-12 vntol=1e-7")
    d.add(f".tran {p.tstep:.4g} {tend + 5e-12:.6g} 0 {p.tmax:.4g}")
    for h in "pn":
        d.add(f".meas tran end_ls_{h} find v(ls_{h}) at={tend:.6g}")
        d.add(f".meas tran end_amp_{h} find v(amp_{h}) at={tend:.6g}")
    if probes and outfile:
        d.add(".control")
        d.add("set wr_singlescale")
        d.add("set wr_vecnames")
        d.add("run")
        d.add(f"wrdata {outfile} {' '.join(probes)}")
        d.add(".endc")
    d.add(".end")
    return "\n".join(d.lines) + "\n"


def run(p: Params, probes: list[str] | None = None, outfile: str | None = None) -> dict[str, float]:
    """Run one transient; returns the settled hold voltages end_ls_p / end_ls_n.

    ngspice now and then gives up with "timestep too small" on this deck; the run
    is then repeated with a slightly different maximum step, which moves the time
    points and has always been enough."""
    err = ""
    for scale in (1.0, 0.83, 0.71, 0.5):
        deck = build(dataclasses.replace(p, tmax=p.tmax * scale), probes, outfile)
        with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as f:
            f.write(deck)
            path = f.name
        try:
            r = subprocess.run(["ngspice", "-b", path], capture_output=True, text=True, timeout=1800)
        finally:
            os.unlink(path)
        out = {}
        for m in re.finditer(r"^(end_(?:ls|amp)_[pn])\s*=\s*([-+0-9.eE]+)", r.stdout, re.M):
            out[m.group(1)] = float(m.group(2))
        if len(out) == 4:
            c1, c2 = p.c_hold + LS_C / 2, p.c_opamp + LS_C / 2
            return {f"end_ls_{h}": (c1 * out[f"end_ls_{h}"] + c2 * out[f"end_amp_{h}"]) / (c1 + c2) for h in "pn"}
        err = r.stdout[-1500:] + r.stderr[-1500:]
    raise RuntimeError("ngspice failed:\n" + err)


def steady_state(p: Params, dv: float = 0.02) -> dict[str, float]:
    """Hold voltages that a repetitive strobe converges to.

    One strobe moves the hold node by dV = -eff * (V - V_ss). Two transients from
    start voltages `dv` apart give eff and V_ss for each half. eff is the sampling
    efficiency (fraction of the error removed per strobe)."""
    r0 = run(p)
    r1 = run(dataclasses.replace(p, v_ls_p=p.v_ls_p + dv, v_ls_n=p.v_ls_n + dv))
    out = {}
    for h, v0 in (("p", p.v_ls_p), ("n", p.v_ls_n)):
        d0 = r0[f"end_ls_{h}"] - v0
        d1 = r1[f"end_ls_{h}"] - (v0 + dv)
        eff = -(d1 - d0) / dv
        out[f"eff_{h}"] = eff
        out[f"v_{h}"] = v0 + d0 / eff if eff > 1e-4 else float("nan")
    return out
