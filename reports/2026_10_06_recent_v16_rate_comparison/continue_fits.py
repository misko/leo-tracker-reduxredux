"""Optimizer-only continuation; retain the frozen factorial baseline unchanged.

Offer every arm the same maximum continuation, stopping only on checked KKT.
No new starts, data, priors, selection, cone settings, or radius. Never select
by distance to the known roof. Results belong to a separate experiment.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import factorial as study

OUT=study.OUT/'continuation-v1'
REPORT=study.REPORT/'continuation-v1'
BUDGETS=dict(slsqp_first_s=30.,fisher_s=60.,slsqp_last_s=30.)


def choose(records):
    from resume_position_convergence import best_record
    return best_record(records)


def run(label,refinement,model,cone,arm):
    from position_score_sweep import Objective,SPECS,finish
    from polish_position_score_sweep import slsqp_fit
    from convergence_fisher import fit
    study.freeze()
    folder=study.OUT/'positions'/label/refinement/model/cone
    source=folder/f'{arm}.json'
    target=OUT/label/refinement/model/cone/f'{arm}.json'
    signature=dict(source_sha256=study.stage.sha(source),
        implementation_sha256=study.stage.sha(__file__),maximum_budgets_s=BUDGETS)
    if target.exists():
        result=json.loads(target.read_text())
        assert result['continuation']==signature
        return result
    previous=json.loads(source.read_text())
    assert previous['input_sha256']==study.stage.sha(folder/'input.npz')
    with np.load(folder/'input.npz',allow_pickle=False) as z:
        data=SimpleNamespace(**{k:z[k].copy() for k in z.files})
    factory=Objective
    if cone=='on':
        from factorial_objective import Objective as ConeObjective
        factory=ConeObjective
    obj=factory(data,previous['input_metadata']['rf_center_hz'],arm,SPECS[study.MODELS[model]])
    original=finish(obj,data,previous['best'])
    assert abs(original['objective']-previous['objective'])<1e-7
    assert original['converged']==previous['converged']
    records=[previous['best']]
    for name,budget in BUDGETS.items():
        best=choose(records)
        if finish(obj,data,best)['converged']:break
        if name.startswith('slsqp'):
            candidate=slsqp_fit(obj,best,budget,radius_km=4.)
        else:
            candidate=fit(obj,np.asarray(best['vector']),best['point_km'],budget,False,radius_km=4.)
        candidate['stage']='continuation-v1-'+name
        records.append(candidate)
    best=choose(records)
    metrics=finish(obj,data,best)
    assert metrics['objective']<=original['objective']+1e-7
    result=dict(scan=label,refinement=refinement,model=model,cone=cone,arm=arm,
        continuation=signature,source=str(source),input_sha256=previous['input_sha256'],
        original=original,best=best,records=records,**metrics)
    study.stage.save(target,result)
    print(json.dumps(dict(scan=label,refinement=refinement,model=model,cone=cone,arm=arm,
        before_m=original['distance_m'],after_m=metrics['distance_m'],
        converged=metrics['converged'],kkt=metrics['kkt'])),flush=True)
    return result


def report():
    from build_report import table
    rows=[json.loads(p.read_text()) for p in sorted(OUT.glob('*/*/*/*/*.json'))]
    REPORT.mkdir(parents=True,exist_ok=True)
    changed=[r for r in rows if not r['original']['converged']]
    summary=dict(saved=len(rows),initially_unconverged=len(changed),
        newly_converged=sum(r['converged'] for r in changed),
        remaining_unconverged=sum(not r['converged'] for r in rows))
    body=['# Optimizer continuation of recent scan fits',
        'This experiment tests optimization convergence, not a new physical model. '
        'All original factorial results are preserved. Every processed arm is offered the same '
        'maximum 30 s SLSQP, 60 s Fisher, and 30 s SLSQP continuation, stopping early '
        'at checked KKT ≤ 0.001. Already-converged fits are reconstructed and retained. '
        'No starts, observations, satellite sets, priors, receiver calibration, cone settings, '
        'or 4 km search bounds change. Both RF arms are included.',
        f"{summary['saved']} cases processed. Of {summary['initially_unconverged']} initially "
        f"unconverged cases, {summary['newly_converged']} now pass convergence; "
        f"{summary['remaining_unconverged']} remain provisional.",
        'A lower objective establishes numerical improvement for the same loss, not better '
        'position accuracy. The table reports both independently. Convergence does not prove '
        'a global minimum. Results are provisional until the intended cohort is processed.',
        table(['Scan','Measurements','Model','Cone','RF','Before m','After m','Objective change','KKT','Converged','Boundary'],
              [[r['scan'],r['refinement'],r['model'],r['cone'],r['arm'],
                f"{r['original']['distance_m']:.1f}",f"{r['distance_m']:.1f}",
                f"{r['objective']-r['original']['objective']:+.6f}",f"{r['kkt']:.6g}",
                r['converged'],r['boundary']] for r in rows]),
        '## Reproduction',
        'Run `continue_fits.py --labels LABEL ...` using the scientific Python environment. '
        'The script requires all 16 baseline cases for each requested scan. Each output records '
        'the immutable baseline hash, input hash, implementation hash, solver records, and budgets. '
        'Run with `--report-only` to refresh this report without fitting.']
    (REPORT/'report.md').write_text('\n\n'.join(body)+'\n')
    (REPORT/'summary.json').write_text(json.dumps(summary,indent=2))
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--labels',nargs='+',default=[])
    p.add_argument('--report-only',action='store_true')
    args=p.parse_args()
    if not args.report_only:
        labels={r['label'] for r in json.loads(study.stage.COHORT.read_text())['scans']}
        if not set(args.labels)<=labels:raise ValueError('Unknown labels')
        for label in args.labels:
            # Check complete input set before starting; never selectively skip a bad arm.
            for refinement,model,cone in study.cases():
                for arm in study.stage.ARMS:
                    if not (study.OUT/'positions'/label/refinement/model/cone/f'{arm}.json').exists():
                        raise FileNotFoundError(f'{label}: baseline factorial incomplete')
            for refinement,model,cone in study.cases():
                for arm in study.stage.ARMS:
                    run(label,refinement,model,cone,arm)
                    report()
    print(json.dumps(report()),flush=True)
