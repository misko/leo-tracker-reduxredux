import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from core import pair,fit,density

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
ROOT=REPORTS.parent


def read(path):
    return json.loads(path.read_text())


def main():
    started=time.monotonic()
    donor_receipt=REPORTS/'2026_09_29_candidate_rx_transfer/results.json'
    target_path=REPORTS/'2026_09_30_ds10_rx_residual/results.json'
    for name,digest in read(donor_receipt)['hashes'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    target=read(target_path)
    for name,digest in target['hashes'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    donors=sorted((REPORTS/'2026_09_29_donor_residual_transfer/runs').glob('DS*_*_8/result.json'))
    assert len(donors)==9
    sources=[(p,read(p)['cases']) for p in donors]+[(target_path,target['cases'])]
    pairs=[];coverage=[]
    for path,cases in sources:
        ds='DS10' if path==target_path else cases[0]['unit_id'].split('_')[0]
        grouped=defaultdict(list)
        for c in cases:
            grouped[c['session_id'],c['rf_hz'],c['number']].append(c)
        attempted=accepted=0
        for group in grouped.values():
            for a in group:
                if a['receiver_id']!=0:continue
                for b in group:
                    if b['receiver_id']!=1:continue
                    attempted+=1
                    result=pair(a,b)
                    if result is None:continue
                    accepted+=1
                    pairs.append(dict(result,dataset=ds,session_id=a['session_id'],track0=a['track_id'],track1=b['track_id']))
        coverage.append(dict(source=str(path),dataset=ds,eligible_tracks=len(cases),attempted_pairs=attempted,accepted_pairs=accepted))
    flat=[]
    for p in pairs:
        flat.extend((p['dataset'],p['session_id'],p['feature'],e) for e in p['held'])
    donor=[r for r in flat if r[0]!='DS10'];held=[r for r in flat if r[0]=='DS10']
    assert set(r[0] for r in donor)=={'DS7','DS8','DS9'} and held
    counts=defaultdict(int);scans=defaultdict(set)
    for ds,sid,_,_ in donor:
        counts[ds,sid]+=1;scans[ds].add(sid)
    weights=np.array([1/(3*len(scans[ds])*counts[ds,sid]) for ds,sid,_,_ in donor])
    assert abs(weights.sum()-1)<1e-12
    features=np.array([r[2] for r in donor]);errors=np.array([r[3] for r in donor])
    fits={name:fit(errors,features,weights,variable) for name,variable in [('constant',False),('paired_scale',True)]}
    summary=dict(coverage=coverage,donor_held_pairs=len(donor),target_held_pairs=len(held),fits=fits)
    scores=[]
    if all(f['qualified'] for f in fits.values()):
        features=np.array([r[2] for r in held]);errors=np.array([r[3] for r in held])
        values={name:density(f['params'],errors,features)[0] for name,f in fits.items()}
        delta=values['paired_scale']-values['constant']
        for sid in dict.fromkeys(r[1] for r in held):
            keep=np.array([r[1]==sid for r in held])
            scores.append(dict(session_id=sid,observations=int(keep.sum()),mean_score_gain=float(delta[keep].mean())))
        summary.update(target_scans=len(scores),scans_improved=sum(r['mean_score_gain']>0 for r in scores),
                       equal_scan_score_gain=float(np.mean([r['mean_score_gain'] for r in scores])),
                       constant_scale_hz=float(np.exp(fits['constant']['params'][0])),
                       feature_exponent=fits['paired_scale']['params'][1],scan_scores=scores)
    paths=[p for p,_ in sources]+[donor_receipt,HERE/'run.py',HERE/'core.py',HERE/'test_core.py',HERE/'PROTOCOL.md']
    result=dict(summary=summary,pairs=pairs,hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},elapsed_seconds=time.monotonic()-started)
    with (HERE/'results.json').open('x') as out:
        json.dump(result,out,indent=2,allow_nan=False)
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['coverage','scan_scores']},indent=2))


if __name__=='__main__':
    main()
