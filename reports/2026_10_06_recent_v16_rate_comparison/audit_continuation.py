"""Reconstruct responsibility changes caused by optimizer-only continuation."""
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import factorial as study
from continue_fits import OUT,REPORT


def changes(before,after):
    before=np.asarray(before,float);after=np.asarray(after,float)
    if before.shape!=after.shape or before.ndim!=2:raise ValueError('Mismatched responsibility arrays')
    if not np.all(np.isfinite(before)) or not np.all(np.isfinite(after)):raise ValueError('Nonfinite probabilities')
    if np.min(before)<-1e-9 or np.min(after)<-1e-9:raise ValueError('Negative probability')
    if np.max(before.sum(axis=1))>1+1e-8 or np.max(after.sum(axis=1))>1+1e-8:
        raise ValueError('Satellite probabilities exceed one')
    a=np.column_stack([before,np.maximum(0,1-before.sum(axis=1))])
    b=np.column_stack([after,np.maximum(0,1-after.sum(axis=1))])
    sa=a.argmax(axis=1);sb=b.argmax(axis=1);clutter=before.shape[1]
    return dict(windows=len(before),most_probable_state_changed=int(np.sum(sa!=sb)),
        satellite_to_other_satellite=int(np.sum((sa!=sb)&(sa!=clutter)&(sb!=clutter))),
        satellite_to_clutter=int(np.sum((sa!=clutter)&(sb==clutter))),
        clutter_to_satellite=int(np.sum((sa==clutter)&(sb!=clutter))),
        mean_total_variation=float(np.mean(np.sum(abs(a-b),axis=1)/2)),
        before_signal_mass=float(before.sum()),after_signal_mass=float(after.sum()))


def audit(path):
    from position_score_sweep import Objective,SPECS,finish
    result=json.loads(path.read_text());source=Path(result['source'])
    assert result['continuation']['source_sha256']==study.stage.sha(source)
    old=json.loads(source.read_text())
    assert result['input_sha256']==old['input_sha256']==study.stage.sha(source.parent/'input.npz')
    with np.load(source.parent/'input.npz',allow_pickle=False) as z:
        data=SimpleNamespace(**{k:z[k].copy() for k in z.files})
    factory=Objective
    if result['cone']=='on':
        from factorial_objective import Objective as Cone
        factory=Cone
    obj=factory(data,old['input_metadata']['rf_center_hz'],result['arm'],SPECS[study.MODELS[result['model']]])
    before=finish(obj,data,old['best']);pa=obj.likelihood.last_result['row_association_probability'].copy()
    after=finish(obj,data,result['best']);pb=obj.likelihood.last_result['row_association_probability'].copy()
    assert abs(before['objective']-old['objective'])<1e-7
    assert abs(after['objective']-result['objective'])<1e-7
    return dict(**{k:result[k] for k in ('scan','refinement','model','cone','arm')},
        source=str(path),source_sha256=study.stage.sha(path),
        before_error_m=before['distance_m'],after_error_m=after['distance_m'],
        objective_change=after['objective']-before['objective'],
        before_rms_hz=before['posterior_weighted_residual_rms_hz'],
        after_rms_hz=after['posterior_weighted_residual_rms_hz'],
        **changes(pa,pb))


def main():
    from build_report import table
    study.freeze()
    rows=[]
    for path in sorted(OUT.glob('*/*/*/*/*.json')):
        result=json.loads(path.read_text())
        if not result['original']['converged']:rows.append(audit(path))
    REPORT.mkdir(parents=True,exist_ok=True)
    (REPORT/'responsibility-audit.json').write_text(json.dumps(rows,indent=2))
    text=['# Responsibility changes after optimizer continuation',
        'The same observations, satellite set, model, and priors are evaluated at the saved original '
        'and continued solutions. Satellite responsibilities are reconstructed from the likelihood; '
        'clutter probability is one minus their sum. The most probable state includes clutter. '
        'These diagnostic state changes are not a rerun of greedy association.',
        'Only initially unconverged cases with saved continuation results are included. '
        'A small change in position error can conceal a substantial change in soft associations. '
        'Posterior RMS changes can also reflect changed responsibilities rather than improvement '
        'on a fixed set of hard satellite owners.',
        table(['Scan','Measurements','Model','Cone','RF','Windows','Changed states','Sat to sat','Sat to clutter',
               'Clutter to sat','Mean TV','RMS before Hz','RMS after Hz','Error before m','Error after m'],
              [[r['scan'],r['refinement'],r['model'],r['cone'],r['arm'],r['windows'],
                r['most_probable_state_changed'],r['satellite_to_other_satellite'],r['satellite_to_clutter'],
                r['clutter_to_satellite'],f"{r['mean_total_variation']:.6f}",
                f"{r['before_rms_hz']:.2f}",f"{r['after_rms_hz']:.2f}",
                f"{r['before_error_m']:.1f}",f"{r['after_error_m']:.1f}"] for r in rows]),
        'Mean TV is the average total-variation distance between each window\'s before/after '
        'satellite-plus-clutter probability vectors. Zero means unchanged responsibilities. '
        'Reproduce with `audit_continuation.py` in the scientific Python environment. '
        'The companion JSON contains exact source hashes and unrounded statistics.']
    (REPORT/'responsibility-audit.md').write_text('\n\n'.join(text)+'\n')
    print(json.dumps(rows),flush=True)


if __name__=='__main__':main()
