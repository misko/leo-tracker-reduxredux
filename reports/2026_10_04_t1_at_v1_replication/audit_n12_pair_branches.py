"""Test the confounding timing branch without deleting observations or satellites.

Original saved results are preserved. Reinstate each removed satellite at its
original fitted timing, copy surviving nuisance from the deletion fit, and
optimize the complete original bank/data within the same 4 km disk.
"""
import json
import numpy as np
from characterize_leave_one_out import objective,snapshot,load,OUT as POS,ARMS
from audit_n12_pair_identity import OUT
from convergence_fisher import fit
from leave_one_satellite_out import remap_start,digest,delete_satellite
from resume_position_convergence import best_record


def main():
    full,meta,_=load('N12');baseline=json.loads((POS/'N12/baseline.json').read_text());result={}
    for arm in ARMS:
        obj=objective(full,meta,arm);original=baseline['arms'][arm]['best'];records=[original]
        for n in (62866,62868):
            deleted=json.loads((POS/'N12'/f'drop-{n}.json').read_text());d=deleted['arms'][arm]['best']
            timing=dict(zip(deleted['retained_satellites'],d['parameters'][6:]))
            params=np.r_[d['parameters'][:6],[timing.get(int(cat),original['parameters'][6+j]) for j,cat in enumerate(full.numbers)]]
            start=remap_start(obj,dict(parameters=params,coefficient=d['coefficient']),np.arange(len(full.numbers)),arm)
            rec=fit(obj,start,d['point_km'],12.,False,radius_km=4.);rec['stage']=f'restored-{n}'
            records.append(rec)
        best=best_record(records)
        fixed=fit(obj,best['vector'],best['point_km'],6.,True,radius_km=4.);fixed['stage']='nuisance-polish';records.append(fixed)
        final=fit(obj,fixed['vector'],fixed['point_km'],12.,False,radius_km=4.);final['stage']='final-joint';records.append(final)
        best=best_record(records);snap,res,loss=snapshot(obj,full,best)
        like=obj.likelihood.last_result;p=like['row_association_probability'];mask=full.owners==53045
        row=dict(best=best,records=records,original=original,distance_m=float(np.linalg.norm(best['point_km'])*1000),
                 delta_score=best['objective']-original['objective'],converged=best['success'] and not best['fixed_location'],
                 snapshot=snap,original_53045_windows=int(sum(mask)),
                 original_53045_windows_with_any_posterior_over_half=int(sum(p[mask].max(axis=1)>.5)),
                 original_53045_windows_mean_signal_probability=float(p[mask].sum(axis=1).mean()))
        result[arm]=row
        print(arm,'full bank/data','distance',row['distance_m'],'delta score',row['delta_score'],'converged',row['converged'],
              '53045 ownership probability',snap['parts'][53045]['effective_owner_probability'],flush=True)
    (OUT/'full-bank-timing-branch-check.json').write_text(json.dumps(dict(scope=__doc__,arms=result,
        input_sha256=meta['input_sha256'],source_sha256=digest(POS/'N12/baseline.json'),
        matched_maximum_budgets_s=[12,12,6,12],original_results_modified=False),indent=2))
    matched=[]
    for n in (62866,62868):
        data,keep,ids=delete_satellite(full,n)
        old=json.loads((POS/'N12'/f'drop-{n}.json').read_text())
        for arm in ARMS:
            obj=objective(data,meta,arm);control=result[arm]['best']
            start=remap_start(obj,control,ids,arm)
            records=[old['arms'][arm]['best']]
            r=fit(obj,start,control['point_km'],12.,False,radius_km=4.);r['stage']='new-full-control-start';records.append(r)
            b=best_record(records)
            f=fit(obj,b['vector'],b['point_km'],6.,True,radius_km=4.);f['stage']='nuisance-polish';records.append(f)
            r=fit(obj,f['vector'],f['point_km'],12.,False,radius_km=4.);r['stage']='joint-polish';records.append(r)
            b=best_record(records)
            matched.append(dict(removed_satellite=n,arm=arm,best=b,records=records,
                                distance_m=float(np.linalg.norm(b['point_km'])*1000),
                                new_full_control_distance_m=result[arm]['distance_m'],
                                converged=b['success'] and not b['fixed_location'],
                                old_case_score_change=b['objective']-old['arms'][arm]['best']['objective']))
            print('MATCHED',n,arm,'distance',matched[-1]['distance_m'],'converged',matched[-1]['converged'],flush=True)
    (OUT/'matched-branch-deletions.json').write_text(json.dumps(dict(scope='Revisit the same deletion cases seeded by the better full-bank timing branch. Original artifacts unchanged.',
        rows=matched,matched_maximum_budgets_s=[12,6,12]),indent=2))


if __name__=='__main__':main()
