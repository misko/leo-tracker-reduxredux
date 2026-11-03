"""Matched cross-start polish to distinguish timing bounds from local-mode switches.

Each bound gets the other bound's best solution as an additional start, followed
by the same maximum polish budget. Original multistart receipts are unchanged.
"""
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np
import timing_bound_comparison as experiment
from subset_positions import enable_research_model,serial
from leave_one_satellite_out import load
from convergence_fisher import fit
from resume_position_convergence import best_record

SOURCE=experiment.OUT
OUT=SOURCE/'cross-start-polish'


def run(task):
    scan,arm=task
    enable_research_model()
    from rf_calibration_diagnostic import CalibrationObjective
    data,meta,_=load(scan)
    originals={limit:json.loads((SOURCE/f'{scan}-{arm}-{limit}s.json').read_text()) for limit in (20,10)}
    for limit in (20,10):
        target=OUT/f'{scan}-{arm}-{limit}s.json'
        if target.exists():continue
        original=originals[limit];other=originals[30-limit]
        obj=CalibrationObjective(data,data.initial,np.arange(len(data.numbers)),False,60.)
        obj.center=meta['rf_center_hz'];obj.features=((data.rf-obj.center)/1e9)[:,None]
        obj.likelihood.features=obj.features
        obj.base.minimum_shift_s=max(obj.base.minimum_shift_s,-limit)
        obj.base.maximum_shift_s=min(obj.base.maximum_shift_s,limit)
        if arm=='zero-c':obj.bounds[-1]=(0.,0.)
        records=list(original['records'])
        cross=experiment.feasible_start(obj,other['best'],limit,arm)
        # Include the feasible seed as evidence even if optimization times out.
        if limit==20:
            obj.base.deadline=float('inf');score,_=obj.evaluate(np.array(other['best']['vector']))
            assert abs(score-other['best']['objective'])<1e-7
            seed=dict(other['best'],stage='feasible-10s-seed',success=False,status='stationarity-not-audited-under-20s')
            records.append(seed)
        r=fit(obj,cross,other['best']['point_km'],15.,False,radius_km=4.)
        r['stage']='cross-bound-start';records.append(r)
        start=best_record(records)
        r=fit(obj,experiment.feasible_start(obj,start,limit,arm),start['point_km'],10.,False,radius_km=4.)
        r['stage']='cross-bound-polish';records.append(r)
        best=best_record(records)
        obj.base.deadline=float('inf');score,_=obj.evaluate(np.asarray(best['vector']))
        assert abs(score-best['objective'])<1e-7
        penalty,_=obj.base.penalty(np.asarray(best['vector'])[:obj.size])
        probability=obj.likelihood.last_result['row_association_probability']
        total=np.asarray(best['parameters'])[6:]
        assert max(abs(total))<=limit+1e-7
        result=dict(original,best=best,records=records,
            cross_start_scope=__doc__,cross_start_maximum_budgets_s=[15.,10.],
            original_source_sha256=experiment.digest(SOURCE/f'{scan}-{arm}-{limit}s.json'),
            cross_source_sha256=experiment.digest(SOURCE/f'{scan}-{arm}-{30-limit}s.json'),
            distance_m=1000*np.linalg.norm(best['point_km']),
            converged=bool(best['success'] and not best['fixed_location']),
            boundary=bool(np.linalg.norm(best['point_km'])>=4.-1e-4),
            timing_boundary_count=int(sum(abs(total)>=limit-1e-3)),
            maximum_absolute_timing_s=float(max(abs(total))),timing_prior_nll=penalty,
            data_nll=score-penalty,objective=score,
            strong_soft_windows=int(sum(np.max(probability,axis=1)>.5)),
            elapsed_s=sum(r['elapsed_s'] for r in records if r['stage']!='feasible-10s-seed'))
        target.write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
        print('POLISH',scan,arm,limit,round(result['distance_m']),best['status'],
              'score gain',round(original['objective']-score,3),flush=True)
    return scan,arm


if __name__=='__main__':
    OUT.mkdir(exist_ok=True)
    with ProcessPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(run,(s,a)) for s in experiment.SCANS for a in experiment.ARMS]):
            print('PAIR DONE',future.result(),flush=True)
    experiment.OUT=OUT
    experiment.render()
