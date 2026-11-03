"""Score all windows and a time/object-disjoint validation partition."""
import json
from pathlib import Path
import numpy as np
from states import digest
from model import metrics
HERE=Path(__file__).resolve().parent


def main():
    cp=HERE/'calibration.json';cal=json.loads(cp.read_text());assert cal['qualified']
    for p,h in cal['sources'].items():assert digest(p)==h,p
    sources={str(p):digest(p) for p in (Path(__file__),HERE/'model.py',HERE/'PROTOCOL.md',cp)};all_rows=[];windows=[]
    for i in range(12):
        p=HERE/f'center-{i:02d}.json';doc=json.loads(p.read_text());sources[str(p)]=digest(p)
        for q,h in doc['sources'].items():assert digest(q)==h,q
        rp=p.with_suffix('.receipt.json');receipt=json.loads(rp.read_text());assert receipt['exit_code']==0 and digest(p.with_suffix('.log'))==receipt['log_sha256'];sources[str(rp)]=digest(rp)
        rows=[dict(r,ordinal=i) for r in doc['rows']];all_rows+=rows
        x=np.array([r['previous_revision'] for r in rows]);y=np.array([r['next_revision'] for r in rows])
        windows.append(dict(ordinal=i,cases=len(rows),metrics={name:metrics(x,y,a)[0] for name,a in [('zero',0.),('fitted',cal['alpha']),('repeat',1.)]}))
    train={r['norad'] for r in all_rows if r['split']=='training'};validation=[r for r in all_rows if r['split']=='validation'];assert not train & {r['norad'] for r in validation}
    x=np.array([r['previous_revision'] for r in validation]);y=np.array([r['next_revision'] for r in validation]);out={};errors={}
    for name,a in [('zero',0.),('fitted',cal['alpha']),('repeat',1.)]:out[name],errors[name]=metrics(x,y,a)
    wins=int(np.sum(errors['fitted']<errors['zero']));passed=bool(wins>len(validation)/2 and out['fitted']['median_position_km']<=.95*out['zero']['median_position_km'] and out['fitted']['mean_position_km']<=.95*out['zero']['mean_position_km'] and out['fitted']['median_velocity_m_s']<=out['zero']['median_velocity_m_s'])
    summary=dict(cases=len(validation),physical_objects=len({r['norad'] for r in validation}),wins=wins,metrics=out,passed=passed)
    result=dict(alpha=cal['alpha'],validation=summary,windows=windows,sources=sources,independent_orbit_truth=False,causal_position_improvement_established=False)
    with (HERE/'summary.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(alpha=cal['alpha'],validation=summary),indent=2))


if __name__=='__main__':main()
