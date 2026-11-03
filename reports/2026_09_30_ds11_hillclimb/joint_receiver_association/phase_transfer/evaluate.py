"""Frozen cross-recording curvature calibration and source-shift controls."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from scipy.optimize import least_squares

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'frame_evolution'))
from curvature import curvature
JOBS=[(3,18,20),(4,7,11),(5,4,19),(6,0,10),(7,5,14)]


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relation(training,validation):
    x=np.array([r['orbit'] for r in training]);y=np.array([r['phase'] for r in training])
    design=np.column_stack((np.ones(len(x)),x))
    if min(len(training),len(validation))<5 or np.linalg.matrix_rank(design)<2:
        return dict(passed=False,qualified=False,reason='insufficient_source_groups_or_rank')
    initial=np.linalg.lstsq(design,y,rcond=None)[0]
    fit=least_squares(lambda b:design@b-y,initial,jac=lambda b:design,loss='soft_l1',f_scale=.01,gtol=1e-12,ftol=1e-12,xtol=1e-12,max_nfev=300)
    vx=np.array([r['orbit'] for r in validation]);vy=np.array([r['phase'] for r in validation])
    error=float(np.median(abs(vy-(fit.x[0]+fit.x[1]*vx))))
    constant=float(np.median(abs(vy-np.median(y))))
    shifts=[float(np.median(abs(vy-(fit.x[0]+fit.x[1]*np.roll(vx,k))))) for k in range(1,len(vx))]
    permuted=float(np.median(shifts))
    qualified=bool(fit.success and fit.optimality<1e-4)
    return dict(qualified=qualified,intercept=float(fit.x[0]),beta=float(fit.x[1]),optimality=float(fit.optimality),training_groups=len(x),validation_groups=len(vx),validation_error=error,constant_error=constant,cyclic_shift_median_error=permuted,cyclic_shift_errors=shifts,passed=bool(qualified and fit.x[1]<0 and error<=.95*constant and error<=.95*permuted))


def main():
    paths=[Path(__file__),HERE/'PROTOCOL.md',HERE.parent/'frame_evolution/curvature.py',HERE.parent/'frame_evolution/audit.py',HERE.parent/'acquisition-calibration-inventory.json']
    sources={str(p):digest(p) for p in paths}
    inventory=json.loads(paths[-1].read_text())
    records={}
    for family,cal,val in JOBS:
        expected=next(f for f in inventory['families'] if f['family']==family)
        assert min(r['index'] for r in expected['calibration'])==cal
        assert min(r['index'] for r in expected['validation'])==val
        for index in (cal,val):
            receipt_path=HERE/f'export-{index:02d}.receipt.json'
            receipt=json.loads(receipt_path.read_text());sources[str(receipt_path)]=digest(receipt_path)
            assert digest(HERE/f'export-{index:02d}.log')==receipt['log_sha256']
            for p,h in receipt['sources'].items():assert digest(p)==h,p
            if receipt['exit_code']!=0:
                records[index]=dict(index=index,export_failed=True,exit_code=receipt['exit_code']);continue
            path=HERE/f'input-{index:02d}.json';doc=json.loads(path.read_text());sources[str(path)]=digest(path)
            for p,h in doc['sources'].items():assert digest(p)==h,p
            rows=[];groups=defaultdict(list)
            for track in doc['rows']:
                result=curvature(track['points'],doc['frame_period_us'])
                rows.append(dict(track_id=track['track_id'],norad=track['norad'],**result))
                if result['qualified']:groups[track['norad']].append(result)
            pooled=[dict(norad=n,tracks=len(g),phase=float(np.median([r['phase_curvature_us_per_s2'] for r in g])),orbit=float(np.median([r['range_curvature_us_per_s2'] for r in g]))) for n,g in sorted(groups.items())]
            records[index]=dict(index=index,rows=rows,groups=pooled,unqualified_tracks=sum(not r['qualified'] for r in rows))
    families=[]
    for family,cal,val in JOBS:
        if any(records[i].get('export_failed') for i in (cal,val)):
            result=dict(passed=False,qualified=False,reason='export_failed')
        else:result=relation(records[cal]['groups'],records[val]['groups'])
        families.append(dict(family=family,calibration=cal,validation=val,**result))
    result=dict(families=families,recordings=list(records.values()),sources=sources,position_improvement_established=False,inferred_labels=True)
    with (HERE/'summary.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(families,indent=2))


if __name__=='__main__':main()
