"""Joint local-tracklet selection with peak, group and satellite-timing exclusivity.

MILP is over generated proposals only; development calibration, no validation claim.
"""
import argparse,json,time
import numpy as np
from scipy.optimize import milp,Bounds,LinearConstraint
from scipy.sparse import coo_matrix
from benchmark import ROOT,ALIAS_HZ,digest


def prune_nonpositive(proposals,groups,pdet):
    """Safe upper-bound pruning: competition can only lower these rewards."""
    kept=[];penalty=.5*np.log(len(np.unique(groups)))
    for p in proposals:
        segments=[];total=0.
        for segment in p['segments']:
            per_group={}
            for row,residual in zip(segment['eligible_rows'],segment['eligible_residual_native_hz']):
                gain=np.log(pdet/(1-pdet))-np.log(200*np.sqrt(2*np.pi))-.5*(residual/200)**2-np.log(2/ALIAS_HZ)
                group=int(groups[row]);per_group[group]=max(per_group.get(group,0.),gain)
            bound=sum(per_group.values())-7.
            if bound>0:segments.append(segment);total+=bound
        if total>penalty+.5*p['offset_s']**2:kept.append({**p,'segments':segments})
    return kept


def solve(proposals,groups,pdet,budget_s=20.):
    costs=[];constraints=[];bounds=[];edges=[];mode_vars={};segment_vars=[]
    row_vars={};group_vars={};sat_modes={}
    def variable(cost):
        costs.append(float(cost));return len(costs)-1
    def constraint(values,lo=-np.inf,hi=np.inf):
        constraints.append(values);bounds.append((lo,hi))
    penalty=.5*np.log(len(np.unique(groups)))
    for pi,proposal in enumerate(proposals):
        n=proposal['catalog_number']
        y=variable(penalty+.5*proposal['offset_s']**2);mode_vars[pi]=y;sat_modes.setdefault(n,[]).append(y)
        mode_segments=[]
        for si,segment in enumerate(proposal['segments']):
            z=variable(7.);segment_vars.append(z);mode_segments.append(z)
            constraint({z:1,y:-1},hi=0)
            members=[]
            for row,residual in zip(segment['eligible_rows'],segment['eligible_residual_native_hz']):
                gain=np.log(pdet/(1-pdet))-np.log(200*np.sqrt(2*np.pi))-.5*(residual/200)**2-np.log(2/ALIAS_HZ)
                x=variable(-gain);members.append(x)
                edges.append((x,int(row),n,pi,si,float(residual)))
                row_vars.setdefault(row,[]).append(x)
                group_vars.setdefault((int(groups[row]),n),[]).append(x)
            constraint({**{x:1 for x in members},z:-len(members)},hi=0)
            constraint({**{x:1 for x in members},z:-10},lo=0)
        constraint({y:1,**{z:-1 for z in mode_segments}},hi=0)
    for variables in list(row_vars.values())+list(group_vars.values())+list(sat_modes.values()):
        constraint({x:1 for x in variables},hi=1)
    ii=[];jj=[];vv=[]
    for i,values in enumerate(constraints):
        for j,value in values.items():ii.append(i);jj.append(j);vv.append(value)
    matrix=coo_matrix((vv,(ii,jj)),shape=(len(constraints),len(costs))).tocsc()
    b=np.array(bounds)
    result=milp(np.array(costs),integrality=np.ones(len(costs)),bounds=Bounds(0,1),
                constraints=LinearConstraint(matrix,b[:,0],b[:,1]),
                options={'time_limit':budget_s,'mip_rel_gap':.001})
    chosen=[] if result.x is None else [dict(row_index=r,catalog_number=n,proposal=pi,segment=si,residual_native_hz=res)
                                      for x,r,n,pi,si,res in edges if result.x[x]>.5]
    assert len(chosen)==len({r['row_index'] for r in chosen})
    assert len(chosen)==len({(int(groups[r['row_index']]),r['catalog_number']) for r in chosen})
    for n in {r['catalog_number'] for r in chosen}:
        assert len({r['proposal'] for r in chosen if r['catalog_number']==n})==1
    return dict(status=int(result.status),message=str(result.message),optimal=bool(result.success),
                mip_gap=None if result.x is None else float(result.mip_gap),
                objective=None if result.x is None else float(result.fun),assignments=chosen,
                variables=len(costs),constraints=len(constraints))


def main():
    p=argparse.ArgumentParser();p.add_argument('--scan',choices=['A','B'],required=True);p.add_argument('--prune',action='store_true');a=p.parse_args()
    source=ROOT/'development-expanded'/f'{a.scan}-proposals.json'
    data=json.loads(source.read_text());arrays=np.load(ROOT/'frozen'/f'{a.scan}-observations.npz')
    started=time.monotonic();pdet=.8/(13 if a.scan=='A' else 15)
    proposals=prune_nonpositive(data['proposals'],arrays['group'],pdet) if a.prune else data['proposals']
    result=solve(proposals,arrays['group'],pdet)
    result['retained_proposals']=len(proposals)
    result['selected_timing_modes']={r['catalog_number']:proposals[r['proposal']]['total_timing_s'] for r in result['assignments']}
    result.update(scan=a.scan,scope=__doc__,source_sha256=digest(source),elapsed_s=time.monotonic()-started,
                  assigned_count=len(result['assignments']),distinct_denominator=len(arrays['canonical_rows']),
                  warning='Raw model assignments. Identity ambiguity, final segment coherence, held-out prediction and negative controls have NOT been validated.')
    out=ROOT/'development-tracklets';out.mkdir(exist_ok=True)
    (out/f'{a.scan}-{"pruned-" if a.prune else ""}result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='assignments'}),flush=True)


if __name__=='__main__':main()
