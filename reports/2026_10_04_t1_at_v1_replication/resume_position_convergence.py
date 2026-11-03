"""Bounded optimizer-only continuation of unconverged all-window scan pairs.

No data, assignments, priors, search radius or convergence tolerance changes.
Preserves original artifacts. Both RF arms of each affected scan get the same
maximum sequence: 60 s Fisher, 30 s SLSQP, 30 s Fisher, stopping early on success.
"""
import csv
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import subset_positions as positions

HERE=Path(__file__).resolve().parent
OUT=HERE/'convergence-retry'


def best_record(records):
    lowest=min(records,key=lambda r:r['objective'])
    stationary=[r for r in records if r['success'] and not r['fixed_location']
                and r['objective']<=lowest['objective']+1e-7]
    if stationary:return min(stationary,key=lambda r:r['objective'])
    joint=[r for r in records if not r['fixed_location'] and r['objective']<=lowest['objective']+1e-7]
    return min(joint,key=lambda r:r['objective']) if joint else lowest


def run(task):
    scan,arm=task
    target=OUT/f'{scan}-{arm}.json'
    if target.exists(): return str(target)
    positions.enable_research_model()
    from rf_calibration_diagnostic import CalibrationObjective
    from fisher_position import fit as fisher
    from position_direct import fit as direct
    root=positions.ROOT/scan
    meta=json.loads((root/'input.json').read_text())
    raw=(root/'input.npz').read_bytes()
    assert 'sha256:'+hashlib.sha256(raw).hexdigest()==meta['input_sha256']
    with np.load(root/'input.npz') as z:
        data=SimpleNamespace(**{k:z[k].copy() for k in z.files})
    original=json.loads((root/'all-100.json').read_text())
    previous=original['arms'][arm]['best']
    objective=CalibrationObjective(data,data.initial,np.arange(len(data.numbers)),False,120.)
    objective.center=meta['rf_center_hz']
    objective.features=((data.rf-objective.center)/1e9)[:,None]
    objective.likelihood.features=objective.features
    objective.base.minimum_shift_s=max(objective.base.minimum_shift_s,-20.)
    objective.base.maximum_shift_s=min(objective.base.maximum_shift_s,20.)
    objective.base.deadline=float('inf')
    if arm=='zero-c':objective.bounds[-1]=(0.,0.)
    reconstructed=objective.evaluate(np.array(previous['vector']))[0]
    assert abs(reconstructed-previous['objective'])<1e-7,(scan,arm,reconstructed,previous['objective'])
    records=[previous]
    for stage,solver,budget in [('fisher-60s',fisher,60.),('slsqp-30s',direct,30.),('fisher-polish-30s',fisher,30.)]:
        start=best_record(records)
        if len(records)>1 and start['success'] and not start['fixed_location']:break
        record=solver(objective,start['vector'],start['point_km'],budget,False)
        record['stage']=stage
        objective.base.deadline=float('inf')
        check=objective.evaluate(np.array(record['vector']))[0]
        assert abs(check-record['objective'])<1e-7
        records.append(record)
        print(scan,arm,stage,record['status'],'KKT',record['kkt_residual'],
              'delta',record['objective']-previous['objective'],flush=True)
        target.with_suffix('.partial.json').write_text(json.dumps(dict(scan=scan,arm=arm,records=records),indent=2))
    best=best_record(records)
    result=dict(scan=scan,arm=arm,scope=__doc__,original=previous,best=best,records=records,
                input_sha256=meta['input_sha256'],source=str(root/'all-100.json'),
                source_sha256=hashlib.sha256((root/'all-100.json').read_bytes()).hexdigest(),
                original_score_reconstruction_error=reconstructed-previous['objective'],
                old_distance_m=1000*float(np.linalg.norm(previous['point_km'])),
                distance_m=1000*float(np.linalg.norm(best['point_km'])),
                position_change_m=1000*float(np.linalg.norm(np.array(best['point_km'])-previous['point_km'])),
                delta_score=best['objective']-previous['objective'],converged=bool(best['success'] and not best['fixed_location']),
                boundary=bool(np.linalg.norm(best['point_km'])>1.999),
                elapsed_s=sum(r['elapsed_s'] for r in records[1:]))
    target.write_text(json.dumps(result,indent=2))
    return str(target)


def main():
    OUT.mkdir(exist_ok=True)
    with (HERE/'cohort-positions.csv').open(newline='') as f: rows=list(csv.DictReader(f))
    scans=sorted({r['scan'] for r in rows if r['case']=='all-100' and r['converged']=='False'})
    jobs=[(s,a) for s in scans for a in ['fitted-c','zero-c']]
    with ProcessPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(run,job) for job in jobs]):print('DONE',future.result(),flush=True)
    summaries=[]
    for scan,arm in jobs:
        r=json.loads((OUT/f'{scan}-{arm}.json').read_text())
        summaries.append(dict(scan=scan,arm=arm,old_distance_m=r['old_distance_m'],distance_m=r['distance_m'],
                              position_change_m=r['position_change_m'],delta_score=r['delta_score'],
                              old_kkt=r['original']['kkt_residual'],new_kkt=r['best']['kkt_residual'],
                              old_status=r['original']['status'],new_status=r['best']['status'],
                              converged=r['converged'],boundary=r['boundary'],elapsed_s=r['elapsed_s']))
    with (OUT/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(summaries[0]));w.writeheader();w.writerows(summaries)
    print('FINISHED',sum(r['converged'] for r in summaries),'/',len(summaries),flush=True)


if __name__=='__main__':main()
