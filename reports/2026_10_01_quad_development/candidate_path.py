"""Exact finite-lattice minimization of a radio-only second-order heuristic."""
import numpy as np


def emission(group):
    m=np.array([p['margin'] for p in group],float)
    if np.any(m<=0) or not np.isfinite(m).all():raise ValueError('positive finite margins required')
    return -.1*np.log(m/m.max())


def edge(a,b):
    dt=b['t']-a['t']
    return dt>0 and abs((b['y']-a['y'])/dt)<=15000


def triple(a,b,c,sigma,acceleration):
    if not edge(a,b) or not edge(b,c):return float('inf')
    d1=b['t']-a['t'];d2=c['t']-b['t'];r=d2/d1
    e=c['y']-(1+r)*b['y']+r*a['y']
    variance=sigma**2*(1+(1+r)**2+r*r)+(acceleration*d2*(d1+d2)/2)**2
    return e*e/variance


def score(groups,path,sigma=100.,acceleration=100.):
    if len(groups)!=len(path) or len(groups)<2:raise ValueError('invalid path size')
    if any(not edge(groups[i-1][path[i-1]],groups[i][path[i]]) for i in range(1,len(groups))):return float('inf')
    return float(sum(emission(g)[k] for g,k in zip(groups,path))+sum(
        triple(groups[i-2][path[i-2]],groups[i-1][path[i-1]],groups[i][path[i]],sigma,acceleration) for i in range(2,len(groups))))


def solve(groups,sigma=100.,acceleration=100.):
    if len(groups)<2 or any(not g for g in groups) or sigma<=0 or acceleration<0:raise ValueError('invalid lattice or scale')
    e=[emission(g) for g in groups]
    costs=np.array([[e[0][a]+e[1][b] if edge(pa,pb) else np.inf for b,pb in enumerate(groups[1])] for a,pa in enumerate(groups[0])])
    back=[]
    for i in range(2,len(groups)):
        nxt=np.full((len(groups[i-1]),len(groups[i])),np.inf);parents=np.zeros(nxt.shape,int)
        for b,pb in enumerate(groups[i-1]):
            for c,pc in enumerate(groups[i]):
                options=[costs[a,b]+triple(pa,pb,pc,sigma,acceleration) for a,pa in enumerate(groups[i-2])]
                a=int(np.argmin(options));parents[b,c]=a;nxt[b,c]=options[a]+e[i][c]
        back.append(parents);costs=nxt
    if not np.isfinite(costs).any():raise ValueError('no feasible path')
    a,b=np.unravel_index(np.argmin(costs),costs.shape);path=[int(a),int(b)]
    for parents in reversed(back):path.insert(0,int(parents[path[0],path[1]]))
    objective=score(groups,path,sigma,acceleration)
    if not np.isclose(objective,costs.min(),atol=1e-9,rtol=1e-12):raise AssertionError('DP reconstruction mismatch')
    return path,objective
