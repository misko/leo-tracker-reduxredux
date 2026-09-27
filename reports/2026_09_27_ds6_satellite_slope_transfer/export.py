"""Training-selected residual traces at frozen randomized-subset positions."""
import argparse
import json
import sys
from pathlib import Path
import numpy as np
from scipy.special import logsumexp

HERE=Path(__file__).resolve().parent;REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_stationary_joint43'))
from run_stationary_joint import load_model, digest, catalogues, TleArchiveReader
from fast_solver import profile


def freeze():
    parent=REPORTS/'2026_09_27_ds6_stationary_joint43'
    p=json.loads((parent/'protocol.json').read_text())
    files=[parent/'protocol.json',parent/'run_stationary_joint.py']+[REPORTS/f for f in p['files']]
    files += [parent/f'{name}{suffix}.json' for name in ['A','B'] for suffix in ['', '-gradient']]
    protocol=dict(source_sha256=digest(HERE/'export.py'),files={str(f.relative_to(REPORTS)):digest(f) for f in files},
        splits={name:p['splits'][name] for name in ['A','B']},center=p['center'],
        eligibility='Training MAP posterior >=0.95 and training time span >=30 seconds',
        correction='Median training OLS slope per satellite per donor scan, then median across at least two donor scans in opposite subset; zero correction otherwise',
        evaluation='Frozen target training-MAP identity and subset position; refit target constant offset on training visits after applying donor slope; compare held-out t4 log density',
        limitations='Conditional diagnostic, no geographic refit; reused data and candidate identities; different subset locations can affect slopes; not physical calibration or proof of global accuracy')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def run(name):
    output=HERE/f'{name}.json'
    if output.exists():raise FileExistsError(output)
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert digest(HERE/'export.py')==protocol['source_sha256']
    for path,value in protocol['files'].items():assert digest(REPORTS/path)==value
    fit=json.loads((REPORTS/'2026_09_27_ds6_stationary_joint43'/f'{name}.json').read_text())
    x=np.array(fit['best']['x']);rows=[]
    assert fit['sessions']==protocol['splits'][name]
    for i,session in enumerate(fit['sessions']):
        model,_,banks=load_model(session,protocol['center']);point=np.array([x[0],x[1],x[i+2]])
        exact=banks(np.array([point[2]]))
        data=json.loads((REPORTS/'2026_09_27_ds6_cfo_dataset'/f'{session}-plan.json').read_text())
        _,cat,_=catalogues(TleArchiveReader(Path('/var/lib/leo/tle')),data['start_utc_ns'],data['snapshot_digest'])
        count=0
        for t in model.base.tracks:
            pred,visible=model.prediction(t,point,exact)
            residual=t['y'][None,:]-pred;a,_,checks,_=profile(residual,t['mask'])
            assert all(c['converged'] for c in checks)
            a=np.where(visible,a,-np.inf);winner=int(np.argmax(a));mass=float(np.exp(a[winner]-logsumexp(a)))
            mask=t['mask'];centered=t['t']-t['t'][mask].mean();span=float(np.ptp(t['t'][mask]))
            if mass<.95 or span<30:continue
            r=residual[winner];slope=float(centered[mask]@r[mask]/(centered[mask]@centered[mask]))
            candidate=int(exact[t['track_id']][2][winner])
            rows.append(dict(session_id=session,track_id=t['track_id'],receiver_id=t['receiver_id'],
                norad=int(cat.satellite_numbers[candidate]),posterior_mass=mass,training_span_s=span,training_slope_hz_s=slope,
                centered_times_s=centered.tolist(),residual_hz=r.tolist(),training_mask=mask.tolist()))
            count+=1
        print(json.dumps(dict(subset=name,completed_scans=i+1,eligible_tracks=count)),flush=True)
    with output.open('x') as f:json.dump(dict(subset=name,complete=True,protocol_sha256=digest(HERE/'protocol.json'),tracks=rows),f)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--freeze',action='store_true');p.add_argument('--subset',choices=['A','B']);a=p.parse_args()
    if a.freeze:freeze()
    else:run(a.subset)
