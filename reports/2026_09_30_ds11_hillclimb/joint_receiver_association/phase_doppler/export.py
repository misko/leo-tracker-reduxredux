"""Replay causal bank predictions and attach training/held residual slopes."""
from collections import defaultdict
import inspect
import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy.special import logsumexp
HERE=Path(__file__).resolve().parent;PARENT=HERE.parent
sys.path.insert(0,str(PARENT))
from doppler_pilot import fast,read,digest
from model import slope
JOBS=[(2,16,17),(3,18,20),(4,7,11),(5,4,19),(6,0,10),(7,5,14)]


def main(index):
    started=time.monotonic();family,cal,val=next(r for r in JOBS if index in r[1:])
    phase_path=PARENT/('frame_evolution/curvature.json' if family==2 else 'phase_transfer/summary.json')
    phase=read(phase_path);record=next(r for r in phase['recordings'] if r['index']==index)
    relation=phase['training_relation'] if family==2 else next(r for r in phase['families'] if r['family']==family)
    intercept=relation['common_clock_curvature_us_per_s2'] if family==2 else relation['intercept']
    beta=relation['orbital_coefficient'] if family==2 else relation['beta']
    donor_path=PARENT/f'acquisition_calibration/donor-{index:02d}.json';donor=read(donor_path)
    geometry_path=PARENT/'causal-calibration-geometry.polished.json';geometry=read(geometry_path)
    plan_path=PARENT.parents[1]/'2026_09_30_ds10_scale_weighting/plan.json';plan=read(plan_path)
    for obj in (phase,donor):
        for p,h in obj['sources'].items():assert digest(p)==h,p
    doc=fast.load_documents(dict(config=geometry['config'],inputs=[plan['inputs'][index]]))[0]
    engine=fast.Stationary(doc,geometry['config']);x=np.array(donor['fixed_geometry_x'])
    tracks={t['track_id']:t for t in doc['tracks']};rows=[];groups=defaultdict(list)
    for r in record['rows']:
        if not r['qualified']:
            rows.append(dict(track_id=r['track_id'],qualified=False,reason='phase_fit_failed'));continue
        t=tracks[r['track_id']];pred,visible=engine.prediction(t,x)
        scores,_,audits,_=fast.profile(t['y'][None]-pred,t['mask'])
        assert all(a['converged'] for a in audits)
        scores=np.where(visible,scores,-np.inf);slot=int(np.argmax(scores))
        assert np.exp(scores[slot]-logsumexp(scores))>=.9
        residual=t['y']-pred[slot]
        train=slope(t['times_s'],residual,t['mask']);held=slope(t['times_s'],residual,~np.asarray(t['mask'],bool))
        row=dict(track_id=r['track_id'],norad=r['norad'],qualified=bool(train['qualified'] and held['qualified']),training=train,held=held,phase_residual=r['phase_curvature_us_per_s2']-intercept-beta*r['range_curvature_us_per_s2'])
        rows.append(row)
        if row['qualified']:groups[row['norad']].append(row)
    pooled=[dict(norad=n,tracks=len(g),phase_residual=float(np.median([r['phase_residual'] for r in g])),training_slope=float(np.median([r['training']['slope_hz_per_s'] for r in g])),held_slope=float(np.median([r['held']['slope_hz_per_s'] for r in g]))) for n,g in sorted(groups.items())]
    paths=[Path(__file__),HERE/'model.py',HERE/'PROTOCOL.md',phase_path,donor_path,geometry_path,plan_path,Path(inspect.getfile(fast)),Path(inspect.getfile(fast.baseline))]
    result=dict(index=index,family=family,role='calibration' if index==cal else 'validation',rows=rows,groups=pooled,sources={str(p):digest(p) for p in paths},elapsed_s=time.monotonic()-started)
    with (HERE/f'input-{index:02d}.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(index=index,tracks=len(rows),qualified=sum(r['qualified'] for r in rows),groups=len(pooled),elapsed_s=result['elapsed_s'])),flush=True)


if __name__=='__main__':main(int(sys.argv[1]))
