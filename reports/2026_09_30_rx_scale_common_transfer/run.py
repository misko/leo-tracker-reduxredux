import hashlib
import importlib.util
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from channels import channels

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'2026_09_30_rx_difference_calibration'


def read(path):
    return json.loads(path.read_text())


def main():
    started=time.monotonic()
    source=BASE/'results.json';prior=read(source)
    for name,digest in prior['hashes'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    spec=importlib.util.spec_from_file_location('calibration',BASE/'core.py')
    calibration=importlib.util.module_from_spec(spec);spec.loader.exec_module(calibration)
    cases={}
    for c in prior['summary']['coverage']:
        for row in read(Path(c['source']))['cases']:
            key=(c['dataset'],row['session_id'],row['track_id'])
            assert key not in cases
            cases[key]=row
    pairs=[];flat=[]
    for old in prior['pairs']:
        ds,sid=old['dataset'],old['session_id']
        a,b=[cases[ds,sid,old[k]] for k in ['track0','track1']]
        result=channels(a,b)
        assert result['feature']==old['feature'] and result['held']['difference']==old['held']
        assert result['training_pairs']==old['training_pairs'] and result['held_pairs']==old['held_pairs']
        pairs.append(dict(result,dataset=ds,session_id=sid,track0=old['track0'],track1=old['track1']))
        flat.extend(dict(dataset=ds,session_id=sid,feature=result['feature'],errors={k:result['held'][k][j] for k in ['rx0','rx1','common']}) for j in range(result['held_pairs']))
    donor=[r for r in flat if r['dataset']!='DS10'];target=[r for r in flat if r['dataset']=='DS10']
    assert len(donor)==17888 and len(target)==7195
    counts=defaultdict(int);scans=defaultdict(set)
    for r in donor:
        counts[r['dataset'],r['session_id']]+=1;scans[r['dataset']].add(r['session_id'])
    weights=np.array([1/(3*len(scans[r['dataset']])*counts[r['dataset'],r['session_id']]) for r in donor])
    assert abs(weights.sum()-1)<1e-12
    donor_features=np.array([r['feature'] for r in donor]);target_features=np.array([r['feature'] for r in target])
    summary={}
    for channel in ['rx0','rx1','common']:
        errors=np.array([r['errors'][channel] for r in donor])
        fits={name:calibration.fit(errors,donor_features,weights,variable) for name,variable in [('constant',False),('paired_scale',True)]}
        result=dict(fits=fits)
        if all(f['qualified'] for f in fits.values()):
            errors=np.array([r['errors'][channel] for r in target])
            scores={name:calibration.density(f['params'],errors,target_features)[0] for name,f in fits.items()}
            delta=scores['paired_scale']-scores['constant']
            rows=[]
            for sid in dict.fromkeys(r['session_id'] for r in target):
                keep=np.array([r['session_id']==sid for r in target])
                rows.append(dict(session_id=sid,observations=int(keep.sum()),mean_score_gain=float(delta[keep].mean())))
            result.update(scan_scores=rows,equal_scan_score_gain=float(np.mean([r['mean_score_gain'] for r in rows])),
                          scans_improved=sum(r['mean_score_gain']>0 for r in rows),target_observations=len(target),
                          constant_scale_hz=float(np.exp(fits['constant']['params'][0])),feature_exponent=fits['paired_scale']['params'][1])
        summary[channel]=result
    paths=[source,BASE/'core.py',HERE/'run.py',HERE/'channels.py',HERE/'test_channels.py',HERE/'PROTOCOL.md']
    result=dict(summary=summary,pairs=pairs,hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},elapsed_seconds=time.monotonic()-started)
    with (HERE/'results.json').open('x') as out:
        json.dump(result,out,indent=2,allow_nan=False)
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:{n:v for n,v in s.items() if n!='scan_scores'} for k,s in summary.items()},indent=2))


if __name__=='__main__':
    main()
