"""Minimal KiCad schematic netlister (flat, single sheet). Geometry based."""
import re, sys, math, collections

def parse(s):
    tok = re.compile(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+')
    stack=[[]]
    for m in tok.finditer(s):
        t=m.group(0)
        if t=='(': stack.append([])
        elif t==')':
            l=stack.pop(); stack[-1].append(l)
        elif t[0]=='"': stack[-1].append(('S',t[1:-1].replace('\\n','\n').replace('\\"','"')))
        else: stack[-1].append(t)
    return stack[0][0]
def sv(x): return x[1] if isinstance(x,tuple) else x
def kids(n,name): return [c for c in n if isinstance(c,list) and c and c[0]==name]
def kid(n,name):
    k=kids(n,name); return k[0] if k else None
def P(x,y): return (round(float(x)*100),round(float(y)*100))

class UF:
    def __init__(s): s.p={}
    def f(s,a):
        s.p.setdefault(a,a)
        while s.p[a]!=a:
            s.p[a]=s.p[s.p[a]]; a=s.p[a]
        return a
    def u(s,a,b): s.p[s.f(a)]=s.f(b)

def load(path):
    root=parse(open(path).read())
    libs={}
    for ls in kids(kid(root,'lib_symbols'),'symbol'):
        name=sv(ls[1]); pins=collections.defaultdict(list)
        for sub in kids(ls,'symbol'):
            m=re.match(r'.*_(\d+)_(\d+)$',sv(sub[1])); unit=int(m.group(1))
            for p in kids(sub,'pin'):
                at=kid(p,'at'); pins[unit].append((sv(kid(p,'number')[1]),sv(kid(p,'name')[1]),float(at[1]),float(at[2])))
        ispower = kid(ls,'power') is not None
        libs[name]=(pins,ispower)
    uf=UF(); segs=[]; pts=[]  # pts: (pos, tag)
    for w in kids(root,'wire')+kids(root,'bus'):
        if w[0]=='bus': continue
        xy=kids(kid(w,'pts'),'xy'); a=P(xy[0][1],xy[0][2]); b=P(xy[1][1],xy[1][2])
        segs.append((a,b)); uf.u(a,b)
    labels=[]
    for kind in ('label','global_label','hierarchical_label'):
        for l in kids(root,kind):
            at=kid(l,'at'); labels.append((sv(l[1]),P(at[1],at[2])))
    comps={}; pinpos=[]
    for s in kids(root,'symbol'):
        lib=sv(kid(s,'lib_id')[1]); ln=kid(s,'lib_name'); lname=sv(ln[1]) if ln else lib
        at=kid(s,'at'); x0,y0,rot=float(at[1]),float(at[2]),float(at[3]) if len(at)>3 else 0
        mir=kid(s,'mirror'); mir=mir[1] if mir else None
        unit=int(kid(s,'unit')[1]) if kid(s,'unit') else 1
        props={sv(p[1]):sv(p[2]) for p in kids(s,'property')}
        ref=props['Reference']; pins,ispower=libs[lname]
        dnp = kid(s,'dnp') and kid(s,'dnp')[1]=='yes'
        c=comps.setdefault(ref,dict(ref=ref,value=props.get('Value',''),lib=lib,props=props,dnp=dnp,pins={},at=(x0,y0),power=ispower))
        for num,name,px,py in pins.get(unit,[])+pins.get(0,[]):
            py=-py  # lib y up
            r=math.radians(rot); # KiCad rotation: counter-clockwise on screen (y down)
            qx= px*math.cos(r)+py*math.sin(r); qy=-px*math.sin(r)+py*math.cos(r)
            if mir=='x': qy=-qy
            if mir=='y': qx=-qx
            pos=P(x0+qx,y0+qy); pinpos.append((pos,ref,num,name))
            if ispower: labels.append((props['Value'],pos))
    def onseg(p,a,b):
        (x,y),(x1,y1),(x2,y2)=p,a,b
        if (x2-x1)*(y-y1)!=(y2-y1)*(x-x1): return False
        return min(x1,x2)<=x<=max(x1,x2) and min(y1,y2)<=y<=max(y1,y2)
    allpts=set([p for p,*_ in pinpos]+[p for _,p in labels]+[e for s in segs for e in s])
    for j in kids(root,'junction'):
        at=kid(j,'at'); allpts.add(P(at[1],at[2]))
    # index segments by bbox naive
    for p in allpts:
        uf.f(p)
        for a,b in segs:
            if onseg(p,a,b): uf.u(p,a)
    names=collections.defaultdict(set)
    for n,p in labels: names[uf.f(p)].add(n)
    # merge same-name labels
    byname={}
    for r,ns in list(names.items()):
        for n in ns:
            if n in byname: uf.u(r,byname[n])
            byname[n]=uf.f(r)
    names=collections.defaultdict(set)
    for n,p in labels: names[uf.f(p)].add(n)
    netpins=collections.defaultdict(list)
    for pos,ref,num,name in pinpos: netpins[uf.f(pos)].append((ref,num,name))
    nets={}; auto=0
    for r,pl in netpins.items():
        if r in names: nm=sorted(names[r],key=lambda n:(len(n),n))[0]
        else:
            real=[x for x in pl if not x[0].startswith('#')]
            if not real: continue
            x=sorted(real)[0]; nm=f'Net-({x[0]}-{x[1]})'
        nets[nm]=sorted(pl)
        for ref,num,name in pl: comps[ref]['pins'][num]=(name,nm)
    return comps,nets
if __name__=='__main__':
    comps,nets=load(sys.argv[1])
    for n in sorted(nets):
        print(n, ' '.join(f'{r}.{p}({nm})' for r,p,nm in nets[n] if not r.startswith('#')))
    print('---')
    for r in sorted(comps):
        c=comps[r]
        if c['power']: continue
        print(r,c['value'],c['lib'],'DNP' if c['dnp'] else '',c['at'],{k:v for k,v in c['props'].items() if k not in('Reference','Value','Footprint','Datasheet','Description') and v})
