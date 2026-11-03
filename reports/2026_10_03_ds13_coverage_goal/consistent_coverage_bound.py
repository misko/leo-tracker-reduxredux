"""Maximum-coverage relaxation enforcing one global timing mode per satellite.

Ignores timing priors, residual quality within the 600 Hz gate, final segment
coherence, and identity ambiguity. Thus a proven upper bound limits only this
fixed-calibration discrete proposal bank, not all physical models or timings.
"""
import argparse,json,time
import numpy as np
from scipy.optimize import milp,Bounds,LinearConstraint
from scipy.sparse import coo_matrix
from benchmark import ROOT,digest


def solve(proposals,groups,budget_s=30.):
    costs=[];integrality=[];edges=[];row_edges={};sat_modes={};constraints=[]
    def variable(cost,integer):
        costs.append(cost);integrality.append(integer);return len(costs)-1
    def limit(values):constraints.append(values)
    for pi,p in enumerate(proposals):
        rr=sorted({int(r) for s in p['segments'] for r in s['eligible_rows']})
        if not rr:continue
        y=variable(0.,1);sat_modes.setdefault(int(p['catalog_number']),[]).append(y);bygroup={}
        for row in rr:
            x=variable(-1.,0);edges.append((x,row,int(p['catalog_number']),pi))
            row_edges.setdefault(row,[]).append(x);bygroup.setdefault(int(groups[row]),[]).append(x)
        for xs in bygroup.values():limit(({**{x:1. for x in xs},y:-1.},0.))
    for xs in list(row_edges.values())+list(sat_modes.values()):limit(({x:1. for x in xs},1.))
    if not costs:return dict(status=0,optimal=True,incumbent_count=0,upper_bound=0.,assignments=[],variables=0,constraints=0)
    ii=[];jj=[];vv=[]
    for i,(values,_) in enumerate(constraints):
        for j,v in values.items():ii.append(i);jj.append(j);vv.append(v)
    matrix=coo_matrix((vv,(ii,jj)),shape=(len(constraints),len(costs))).tocsc()
    result=milp(np.array(costs),integrality=np.array(integrality),bounds=Bounds(0,1),
        constraints=LinearConstraint(matrix,np.full(len(constraints),-np.inf),np.array([hi for _,hi in constraints])),
        options={'time_limit':budget_s,'mip_rel_gap':0.})
    # With integer modes fixed, remaining edges form per-probe bipartite
    # matching polytopes. Still verify numerical integrality before exporting.
    records=[];count=None
    if result.x is not None:
        values=np.array([result.x[x] for x,_,_,_ in edges]);integral=bool(np.all(abs(values-np.rint(values))<1e-5))
        if integral:
            records=[dict(row_index=row,catalog_number=n,proposal=pi) for x,row,n,pi in edges if result.x[x]>.5]
            count=len(records)
            assert count==len({r['row_index'] for r in records})
            assert count==len({(int(groups[r['row_index']]),r['catalog_number']) for r in records})
            for n in {r['catalog_number'] for r in records}:assert len({r['proposal'] for r in records if r['catalog_number']==n})==1
    bound=getattr(result,'mip_dual_bound',None)
    return dict(status=int(result.status),message=str(result.message),optimal=bool(result.success),
        incumbent_count=count,upper_bound=-float(bound) if bound is not None and np.isfinite(bound) else None,
        assignments=records,variables=len(costs),constraints=len(constraints))


def main():
    p=argparse.ArgumentParser();p.add_argument('--scan',choices=['A','B'],required=True);args=p.parse_args()
    sources=[ROOT/'development-expanded'/f'{args.scan}-proposals.json',ROOT/'coarse-fallback'/f'{args.scan}.json',ROOT/'extended-coarse-fallback'/f'{args.scan}.json']
    files=[json.loads(s.read_text()) for s in sources]
    proposals=files[0]['proposals']+files[1]['new_proposals']+files[2]['new_proposals']
    with np.load(ROOT/'frozen'/f'{args.scan}-observations.npz') as a:groups=a['group'].copy();denominator=len(a['canonical_rows'])
    target=ROOT/'consistent-coverage-bound'/f'{args.scan}.json';target.parent.mkdir(exist_ok=True)
    if target.exists():raise FileExistsError(target)
    started=time.monotonic();result=solve(proposals,groups)
    result.update(scope=__doc__,scan=args.scan,denominator=denominator,target_count=int(np.ceil(.9*denominator)),
        upper_bound_fraction=result['upper_bound']/denominator if result['upper_bound'] is not None else None,
        optimistic_mode_inconsistent_count=files[2]['summary']['optimistic_exclusive_bound'],
        elapsed_s=time.monotonic()-started,sources={str(s):digest(s) for s in sources})
    target.write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='assignments'}),flush=True)


if __name__=='__main__':main()
