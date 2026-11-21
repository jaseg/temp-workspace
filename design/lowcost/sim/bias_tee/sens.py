"""Sensitivity of the corrected TRF tee: 47 uH SRF (15/18/22 MHz), In1 cut-out under the 1210, damping value,
bead derating, and cold-end damping above 5.5 GHz (ESR in the 100 nF, RC snubber). python3 sens.py"""
import sys
import numpy as np
sys.path.insert(0,'.')
import models as m, tees, ac
base_pad=m.LAYOUT_CONST['pad1210']
def go(label, srf=18e6, pad=None, R='1k', d=1.0):
    m.PARTS['LQH32CN470K23L']=(47e-6,1.3,1.69,srf,15e3,170,'')
    m.LAYOUT_CONST['pad1210']=base_pad if pad is None else pad
    src=tees.tee('corr_trf').replace('Rd n2 n3 1k',f'Rd n2 n3 {R}')
    lib=m.library(d)+'\n'+src+'\n'
    L=[f"* line\n{lib}Vs s 0 dc 0 ac 2","Rs s a 50","Rl a 0 50","Xt a 0 TEE_corr_trf"]
    f,(va,)=ac.run("\n".join(L)+"\n"+ac.AC,["v(a)"])
    db=20*np.log10(abs(va)); msk=f>2e6
    print(f"{label:40s} worst {db[msk].min():.3f} dB at {f[msk][np.argmin(db[msk])]/1e6:.1f} MHz; at 3.125 MHz {np.interp(3.125e6,f,db):.3f}")
go('nominal')
go('SRF 15 MHz', srf=15e6)
go('SRF 22 MHz', srf=22e6)
go('In1 cut-out under 1210 pads', pad=0.15)
go('R 820', R='820'); go('R 1.2k',R='1.2k'); go('R 1.5k',R='1.5k')
go('SRF15 + derate 0.85', srf=15e6, d=0.85)
go('SRF15 + derate 0.85 + cutout', srf=15e6, d=0.85, pad=0.15)

def go2(lbl, srf=15e6, esr=0.03, extra=""):
    m.LAYOUT_CONST['pad1210'] = base_pad
    m.PARTS['LQH32CN470K23L']=(47e-6,1.3,1.69,srf,15e3,170,'')
    lib=m.library(1.0).replace(".subckt C100N a b\nC1 a x 1e-07\nL1 x y 4.5e-10\nR1 y b 0.03",f".subckt C100N a b\nC1 a x 1e-07\nL1 x y 4.5e-10\nR1 y b {esr}")
    t=tees.tee('corr_trf')
    if extra: t=t.replace(".ends",extra+"\n.ends")
    lib+='\n'+t+'\n'
    L=[f"* line\n{lib}Vs s 0 dc 0 ac 2","Rs s a 50","Rl a 0 50","Xt a 0 TEE_corr_trf"]
    f,(va,)=ac.run("\n".join(L)+"\n"+ac.AC,["v(a)"])
    db=20*np.log10(abs(va))
    for lo,hi in ((2e6,3e9),(3e9,5.5e9),(5.5e9,8e9)):
        k=(f>lo)&(f<hi); print(f"{lbl:34s} {lo/1e9:4.1f}-{hi/1e9:3.1f} GHz worst {db[k].min():.3f} dB at {f[k][np.argmin(db[k])]/1e6:.0f} MHz")
go2('SRF15 esr .03')
go2('SRF15 esr 1', esr=1)
go2('SRF15 esr 2.2', esr=2.2)
go2('SRF15 + 0402 47R+22p snub at n3', extra="Rsn n3 sn 47\nCsn sn 0 22p")
go2('SRF15 + 0402 10R+100p snub at n2', extra="Rsn n2 sn 10\nCsn sn 0 100p")
go2('SRF18 esr 1', srf=18e6, esr=1)
go2('SRF22 esr 1', srf=22e6, esr=1)
