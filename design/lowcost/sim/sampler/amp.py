"""Behavioural TPH2501 (3PEAK) model from datasheet numbers; no vendor SPICE model used.

GBW 120 MHz (A0 100 dB, dominant pole), slew 180 V/us (tanh-limited input stage into
1 pF), second pole 300 MHz (unity-gain stable, ~68 deg at G=1), 10 ohm output, output
limited 50 mV inside the rails. Input capacitances are added outside the subcircuit.
Bias current (0.3 pA typ / 3 pA max) is added outside where it matters.
Not modelled: input stage nonlinearity beyond slew, output current limit, overload recovery.
"""
import math

GBW, SR, C1, A0, F2 = 120e6, 180e6, 1e-12, 1e5, 300e6
IMAX = SR * C1
GM = 2 * math.pi * GBW * C1
SUBCKT = f"""
.subckt tph2501 inp inn out vp vn
Bgm 0 n1 I={{{IMAX:.4g}*tanh({GM / IMAX:.5g}*(v(inp)-v(inn)))}}
C1 n1 0 {C1}
R1 n1 0 {A0 / GM:.5g}
E2 n2x 0 n1 0 1
R2 n2x n2 1k
C2 n2 0 {1 / (2 * math.pi * F2 * 1e3):.4g}
Bo o1 0 V={{max(min(v(n2), v(vp)-0.05), v(vn)+0.05)}}
Ro o1 out 10
.ends
"""
