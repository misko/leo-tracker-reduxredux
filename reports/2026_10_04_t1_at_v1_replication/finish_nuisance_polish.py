"""Matched fixed-site nuisance polish followed by full constrained re-audit."""
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from diagnose_convergence import objective_for
from resume_position_convergence import OUT,best_record
from convergence_fisher import fit


def run(path):
    r=json.loads(Path(path).read_text())
    target=OUT/'final'/Path(path).name
    if target.exists():
        saved=json.loads(target.read_text())
        records=saved['records']
    else:
        records=None
    start=r['best']
    cached=records is not None
    if not cached:records=[start]
    if not cached and not start['success']:
        obj,_=objective_for(r['scan'],r['arm'])
        fixed=fit(obj,start['vector'],start['point_km'],15.,True)
        fixed['stage']='fixed-nuisance-15s'
        joint=fit(obj,fixed['vector'],fixed['point_km'],15.,False)
        joint['stage']='joint-audit-15s'
        records.extend([fixed,joint])
    best=best_record(records)
    original=json.loads((OUT/Path(path).name).read_text())['original']
    result=dict(scan=r['scan'],arm=r['arm'],best=best,records=records,
                converged=bool(best['success'] and not best['fixed_location']),
                distance_m=1000*float(np.linalg.norm(best['point_km'])),boundary=bool(np.linalg.norm(best['point_km'])>1.999),
                delta_score_vs_original=best['objective']-original['objective'],
                movement_m_vs_original=1000*float(np.linalg.norm(np.array(best['point_km'])-original['point_km'])))
    (OUT/'final'/Path(path).name).write_text(json.dumps(result,indent=2))
    print(r['scan'],r['arm'],'converged',result['converged'],'KKT',best['kkt_residual'],flush=True)


if __name__=='__main__':
    (OUT/'final').mkdir(exist_ok=True)
    with ProcessPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(run,str(p)) for p in sorted((OUT/'polished').glob('N*-*.json'))]):future.result()
