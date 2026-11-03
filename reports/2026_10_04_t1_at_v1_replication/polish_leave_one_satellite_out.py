"""Bounded paired-arm continuation for deletion cases with unfinished fits."""
import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from leave_one_satellite_out import OUT,ARMS,load,delete_satellite,digest
from subset_positions import enable_research_model
from convergence_fisher import fit
from resume_position_convergence import best_record


def run(path):
    enable_research_model()
    from rf_calibration_diagnostic import CalibrationObjective
    saved=json.loads(path.read_text())
    radius=saved.get('radius_km',2.)
    output=path.parent.parent
    if 'continuation' in saved:return
    original=output/'initial-receipts'/saved['scan']/path.name
    original.parent.mkdir(exist_ok=True,parents=True)
    assert not original.exists()
    original.write_text(path.read_text())
    full,meta,_=load(saved['scan']);data,_,_=delete_satellite(full,saved['removed_satellite'])
    for arm in ARMS:
        obj=CalibrationObjective(data,data.initial,np.arange(len(data.numbers)),False,100.)
        obj.center=meta['rf_center_hz'];obj.features=((data.rf-obj.center)/1e9)[:,None]
        obj.likelihood.features=obj.features
        obj.base.minimum_shift_s=max(obj.base.minimum_shift_s,-20.)
        obj.base.maximum_shift_s=min(obj.base.maximum_shift_s,20.)
        if arm=='zero-c':obj.bounds[-1]=(0.,0.)
        obj.base.deadline=float('inf')
        result=saved['arms'][arm];records=result['records']
        for stage,seconds,fixed in [('continue-joint',12.,False),('continue-nuisance',10.,True),('continue-final-joint',12.,False)]:
            best=best_record(records)
            fitted=fit(obj,best['vector'],best['point_km'],seconds,fixed,radius_km=radius)
            fitted['stage']=stage;records.append(fitted)
        best=best_record(records);obj.base.deadline=float('inf')
        score=obj.evaluate(np.array(best['vector']))[0]
        assert abs(score-best['objective'])<1e-7
        joint=[r for r in records if r['success'] and not r['fixed_location']]
        result.update(best=best,distance_m=1000*float(np.linalg.norm(best['point_km'])),
                      boundary=bool(np.linalg.norm(best['point_km'])>radius-.001),
                      converged=bool(best['success'] and not best['fixed_location']),
                      ambiguous=any(np.linalg.norm(np.array(r['point_km'])-best['point_km'])>.1 and abs(r['objective']-best['objective'])<1 for r in joint),
                      delta_score_to_roof=best['objective']-result['roof']['objective'],score_reconstruction_error=score-best['objective'])
    saved['continuation']=dict(paired_maximum_budgets_s=[12,10,12],implementation_sha256=digest(Path(__file__)),
                               reason='At least one RF arm unfinished; both arms receive the same continuation budget.',original_sha256=digest(original))
    path.write_text(json.dumps(saved,indent=2))
    print(saved['scan'],saved['removed_satellite'],[(a,round(v['distance_m']),v['converged']) for a,v in saved['arms'].items()],flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--radius-km',type=float,choices=(2.,4.),default=2.)
    radius=parser.parse_args().radius_km
    output=OUT if radius==2. else OUT.with_name(OUT.name+f'-{radius:g}km')
    paths=[]
    for scan in ('N12','N15'):
        for path in (output/scan).glob('*.json'):
            saved=json.loads(path.read_text())
            if any(not v['converged'] for v in saved['arms'].values()) and 'continuation' not in saved:paths.append(path)
    print('Paired continuation cases',len(paths),flush=True)
    with ProcessPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(run,p) for p in paths]):future.result()


if __name__=='__main__':main()
