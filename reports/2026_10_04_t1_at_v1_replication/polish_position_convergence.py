"""Matched 30 s roundoff-aware polish, preserving original retry receipts."""
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from diagnose_convergence import objective_for
from resume_position_convergence import OUT,best_record
from convergence_fisher import fit


def run(path):
    data=json.loads(Path(path).read_text())
    obj,_=objective_for(data['scan'],data['arm'])
    start=data['best']
    record=fit(obj,start['vector'],start['point_km'],30.,False)
    record['stage']='roundoff-aware-polish-30s'
    obj.base.deadline=float('inf')
    score=obj.evaluate(np.array(record['vector']))[0]
    assert abs(score-record['objective'])<1e-7
    best=best_record([start,record])
    result=dict(scan=data['scan'],arm=data['arm'],previous=start,best=best,record=record,
                success=bool(best['success']),boundary=bool(np.linalg.norm(best['point_km'])>1.999),
                distance_m=1000*float(np.linalg.norm(best['point_km'])),
                delta_score_vs_original=best['objective']-data['original']['objective'],
                movement_m_vs_original=1000*float(np.linalg.norm(np.array(best['point_km'])-data['original']['point_km'])))
    target=OUT/'polished'/Path(path).name
    target.write_text(json.dumps(result,indent=2))
    print(result['scan'],result['arm'],record['status'],'KKT',best['kkt_residual'],
          'converged',result['success'],'movement_m',result['movement_m_vs_original'],flush=True)
    return str(target)


if __name__=='__main__':
    (OUT/'polished').mkdir(exist_ok=True)
    paths=[p for p in OUT.glob('N*-*.json') if '.partial.' not in p.name]
    with ProcessPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(run,str(p)) for p in paths]):future.result()
