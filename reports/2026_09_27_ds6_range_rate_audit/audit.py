"""Compare state-velocity Doppler against exact propagated range derivatives."""
import argparse
import json
import sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_full_stationary'))
from run_full import Stationary,load_model,digest,site,REFERENCE_RF_HZ,LIGHT_KM_S
from fast_solver import profile


def range_doppler(positions,receiver,step):
    ranges=np.linalg.norm(positions-receiver,axis=-1)
    return -REFERENCE_RF_HZ/LIGHT_KM_S*(ranges[:,1]-ranges[:,0])/(2*step)


def freeze():
    base=REPORTS/'2026_09_27_ds6_full_stationary';p=json.loads((base/'protocol.json').read_text())
    files=[base/'protocol.json',base/'run_full.py']+[REPORTS/f for f in p['files']]
    files += [base/f'{s}.json' for s in p['development_sessions']]
    protocol=dict(source_sha256=digest(HERE/'audit.py'),files={str(f.relative_to(REPORTS)):digest(f) for f in files},
        center=p['center'],sessions=p['development_sessions'],steps_s=[.1,.05],
        selection='All included tracks; candidate is stationary baseline training-MAP at exact fitted state; no reference',
        metric='Exact range central difference versus exact state-velocity Doppler; raw and training-mean-centered differences; step-halving convergence',
        scope='Four pre-existing development scans; numerical consistency audit, not new geographic fit')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def run(session):
    output=HERE/f'{session}.json'
    if output.exists():raise FileExistsError(output)
    p=json.loads((HERE/'protocol.json').read_text());assert session in p['sessions']
    assert digest(HERE/'audit.py')==p['source_sha256']
    for name,value in p['files'].items():assert digest(REPORTS/name)==value
    result=json.loads((REPORTS/'2026_09_27_ds6_full_stationary'/f'{session}.json').read_text())
    base,_,banks=load_model(session,p['center']);model=Stationary(base);x=np.array(result['best']['x'])
    rec,_=site(*base.coordinates(x));exact=banks(np.array([x[2]]))
    derivatives={h:banks(np.array([x[2]-h,x[2]+h])) for h in p['steps_s']};rows=[]
    for t in base.tracks:
        tid=t['track_id'];pred,visible=model.prediction(t,x,exact)
        a,_,_,_=profile(t['y'][None,:]-pred,t['mask']);a=np.where(visible,a,-np.inf);winner=int(np.argmax(a))
        controls=[]
        for h in p['steps_s']:
            pos,_,ids=derivatives[h][tid];assert np.array_equal(ids,exact[tid][2])
            controls.append(range_doppler(pos,rec,h)[winner])
        difference=controls[-1]-pred[winner];shape=difference-difference[t['mask']].mean()
        rows.append(dict(track_id=tid,candidate_row=int(exact[tid][2][winner]),observations=len(difference),
            maximum_raw_difference_hz=float(np.max(np.abs(difference))),
            maximum_shape_difference_hz=float(np.max(np.abs(shape))),shape_rms_hz=float(np.sqrt(np.mean(shape**2))),
            maximum_step_halving_difference_hz=float(np.max(np.abs(controls[1]-controls[0])))))
    summary=dict(session_id=session,complete=True,protocol_sha256=digest(HERE/'protocol.json'),tracks=rows,
        maximum_raw_difference_hz=max(r['maximum_raw_difference_hz'] for r in rows),
        maximum_shape_difference_hz=max(r['maximum_shape_difference_hz'] for r in rows),
        maximum_step_halving_difference_hz=max(r['maximum_step_halving_difference_hz'] for r in rows))
    with output.open('x') as f:json.dump(summary,f,indent=2)
    print(json.dumps({k:v for k,v in summary.items() if k!='tracks'}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--freeze',action='store_true');p.add_argument('--session');a=p.parse_args()
    if a.freeze:freeze()
    else:run(a.session)
