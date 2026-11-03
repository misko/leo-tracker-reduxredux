"""Post-hoc matched 10-second Fisher polish of all four scaling pilot arms."""
import json
from types import SimpleNamespace
import numpy as np
import factorial as study
import scaled_optimizer_trial as pilot


def main():
    from position_score_sweep import Objective,SPECS,finish
    from convergence_fisher import fit
    from resume_position_convergence import best_record
    from build_report import table
    study.freeze();rows=[]
    for arm in study.stage.ARMS:
        for mode in ('ordinary','per-window'):
            source=pilot.OUT/f'{arm}-{mode}.json';previous=json.loads(source.read_text())
            target=pilot.OUT/'polished'/source.name
            signature=dict(source_sha256=study.stage.sha(source),
                implementation_sha256=study.stage.sha(__file__),maximum_fisher_s=10.)
            if target.exists():
                result=json.loads(target.read_text());assert result['signature']==signature
            else:
                baseline=study.Path(previous['source']);old=json.loads(baseline.read_text())
                assert old['input_sha256']==study.stage.sha(baseline.parent/'input.npz')
                with np.load(baseline.parent/'input.npz',allow_pickle=False) as z:
                    data=SimpleNamespace(**{k:z[k].copy() for k in z.files})
                obj=Objective(data,old['input_metadata']['rf_center_hz'],arm,SPECS['C0'])
                records=[previous['best']]
                if not finish(obj,data,records[0])['converged']:
                    records.append(fit(obj,np.asarray(records[0]['vector']),records[0]['point_km'],
                                       10.,False,radius_km=4.))
                best=best_record(records);metrics=finish(obj,data,best)
                assert metrics['objective']<=previous['after']['objective']+1e-7
                result=dict(signature=signature,arm=arm,mode=mode,best=best,metrics=metrics,
                            before=previous['after'],records=records)
                study.stage.save(target,result)
            rows.append(result)
            print(json.dumps(dict(arm=arm,mode=mode,**result['metrics'])),flush=True)
    body=['# Matched Fisher polish after optimizer scaling',
        'This is a post-hoc extension of the equal-budget scaling pilot, motivated by the '
        'scaled c = 0 solution narrowly missing the original KKT tolerance. All four '
        'optimizer/RF combinations are offered up to 10 additional seconds of Fisher '
        'polishing, stopping immediately if already converged. The original 60-second '
        'pilot remains unchanged. No tolerance, objective, observation, prior, satellite '
        'set, or search-boundary change is made.',
        table(['RF','SLSQP scaling','KKT before','KKT after','Loss change','Position error m','Converged','Boundary'],
              [[r['arm'],r['mode'],f"{r['before']['kkt']:.6g}",f"{r['metrics']['kkt']:.6g}",
                f"{r['metrics']['objective']-r['before']['objective']:+.6f}",
                f"{r['metrics']['distance_m']:.1f}",r['metrics']['converged'],r['metrics']['boundary']]
               for r in rows]),
        'This targeted single-scan optimizer study cannot establish a general localization '
        'improvement. Boundary solutions are constrained results, not unconstrained minima. '
        'Run `polish_scaled_trial.py` after the four `scaled_optimizer_trial.py` outputs exist. '
        'Receipts preserve both before and after diagnostics and source hashes.']
    (pilot.REPORT/'polished-report.md').write_text('\n\n'.join(body)+'\n')


if __name__=='__main__':main()
