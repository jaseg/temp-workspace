"""Pad-to-pad routed path lengths per net from a KiCad PCB (tracks only, Dijkstra)."""
import re,math,collections,sys,heapq
from kinet import parse,kids,kid,sv
def load(path):
    root=parse(open(path).read())
    G=collections.defaultdict(lambda: collections.defaultdict(list)) # net -> node -> [(node,len,layer)]
    def K(x,y,l): return (round(float(x)*1000),round(float(y)*1000),l)
    for s in kids(root,'segment')+kids(root,'arc'):
        n=sv(kid(s,'net')[-1]); a=kid(s,'start'); b=kid(s,'end'); lay=sv(kid(s,'layer')[1])
        if s[0]=='arc':
            m=kid(s,'mid'); d=math.hypot(float(a[1])-float(m[1]),float(a[2])-float(m[2]))+math.hypot(float(m[1])-float(b[1]),float(m[2])-float(b[2]))
        else: d=math.hypot(float(a[1])-float(b[1]),float(a[2])-float(b[2]))
        A=K(a[1],a[2],lay);B=K(b[1],b[2],lay)
        G[n][A].append((B,d,lay)); G[n][B].append((A,d,lay))
    for v in kids(root,'via'):
        n=sv(kid(v,'net')[-1]); at=kid(v,'at'); ls=[sv(x) for x in kid(v,'layers')[1:]]
        for l1 in ('F.Cu','In1.Cu','In2.Cu','B.Cu'):
            for l2 in ('F.Cu','In1.Cu','In2.Cu','B.Cu'):
                if l1<l2:
                    G[n][K(at[1],at[2],l1)].append((K(at[1],at[2],l2),0.0,'via')); G[n][K(at[1],at[2],l2)].append((K(at[1],at[2],l1),0.0,'via'))
    pads=collections.defaultdict(list)
    for f in kids(root,'footprint'):
        at=kid(f,'at')
        if at: fx,fy=float(at[1]),float(at[2]); rot=float(at[3]) if len(at)>3 else 0
        else:
            t=kid(f,'transform'); tr=kid(t,'translate'); fx,fy=float(tr[1]),float(tr[2]); rot=float(kid(t,'rotate')[1])
        ref=[sv(p[2]) for p in kids(f,'property') if isinstance(p[1],tuple) and sv(p[1])=='Reference'][0]; flay=sv(kid(f,'layer')[1])
        for p in kids(f,'pad'):
            n=kid(p,'net')
            if not n: continue
            pa=kid(p,'at'); px,py=float(pa[1]),float(pa[2]); r=math.radians(rot)
            x=fx+px*math.cos(r)+py*math.sin(r); y=fy-px*math.sin(r)+py*math.cos(r)
            sz=kid(p,'size'); rad=max(float(sz[1]),float(sz[2]))/2
            pads[sv(n[-1])].append((f'{ref}.{sv(p[1])}',x,y,flay,rad))
    return G,pads
def paths(G,pads,net):
    g=G[net]; out={}
    # attach pads to nearest track nodes within pad radius on same layer
    att={}
    for name,x,y,lay,rad in pads[net]:
        c=[(math.hypot(k[0]/1000-x,k[1]/1000-y),k) for k in g if k[2]==lay]
        c=[t for t in c if t[0]<=rad+0.05]
        att[name]=c
    names=list(att)
    for a in names:
        dist={}
        pq=[(d,k) for d,k in att[a]]; heapq.heapify(pq)
        while pq:
            d,k=heapq.heappop(pq)
            if k in dist: continue
            dist[k]=d
            for k2,l,_ in g[k]:
                if k2 not in dist: heapq.heappush(pq,(d+l,k2))
        for b in names:
            if a<b:
                c=[dist[k]+d for d,k in att[b] if k in dist]
                out[(a,b)]=round(min(c),2) if c else None
    return out
if __name__=='__main__':
    G,pads=load(sys.argv[1])
    for net in sys.argv[2:]:
        print(net, {f'{a}-{b}':v for (a,b),v in paths(G,pads,net).items()})
