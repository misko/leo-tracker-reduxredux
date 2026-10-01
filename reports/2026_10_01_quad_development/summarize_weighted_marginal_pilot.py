"""Matched same-objective optimizer comparison, retaining every failure."""
import importlib.util
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_shared_visibility_pilot import HERE,PILOT,sealed,baseline,digest,verify_sources,save


def main():
    previous_path=HERE/'marginal-pilot-summary-v1.json';previous=sealed(previous_path)
    verify_sources(previous['inputs']);verify_sources(previous['source_sha256'])
    lookup={r['unit']:r['marginal'] for r in previous['rows']};rows=[];states={};inputs={str(previous_path):digest(previous_path)}
    for unit in PILOT:
        directory=HERE/'weighted-marginal-pilot-v1'/unit;frozen=sealed(directory/'sources.json')
        verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
        original,_,_=baseline(unit);path=directory/(unit+'.json')
        receipt=sealed(path) if path.exists() else None;evaluation=sealed(directory/'evaluation.json')
        launch=sealed(path.with_suffix('.launch.json'));audit=sealed(directory/'audit-launch.json') if (directory/'audit-launch.json').exists() else {}
        accepted=bool(evaluation['accepted'] and audit.get('returncode')==0 and audit.get('within_budget') and not audit.get('timed_out'))
        old_path=HERE/'marginal-pilot-v1'/unit/(unit+'.json');old=sealed(old_path);inputs[str(old_path)]=digest(old_path)
        best=receipt['best'] if receipt else {};objective_delta=None
        if receipt:
            assert digest(path)==launch['receipt_sha256'] and receipt['source_sha256']==frozen['source_sha256']
            assert old['initial_state']==receipt['initial_state']==original['best']['mean']
            assert old['width_deg']==receipt['width_deg']==.1
            for p,h in original['inputs'].items():assert old['inputs'][p]==receipt['inputs'][p]==h
            for name in ['marginal_visibility_port.py','marginal_window_objective.py']:
                p=str(HERE/name);assert old['source_sha256'][p]==receipt['source_sha256'][p]
            if 'objective' in evaluation:objective_delta=evaluation['objective']-old['best']['objectives'][-1]
        rows.append(dict(unit=unit,leading=lookup[unit],weighted=dict(accepted=accepted,
            reason=best.get('reason',evaluation.get('reason')),iterations=best.get('iterations'),gradient_inf=evaluation.get('scaled_gradient_inf'),
            incremental_seconds=launch['incremental_seconds'],charged_seconds=launch['charged_seconds'],audit_seconds=audit.get('elapsed_seconds'),
            same_model_objective_delta=objective_delta,label_changes=evaluation.get('label_changes_from_baseline'),
            failed_checks=[k for k,v in evaluation.get('checks',{}).items() if not v])))
        states[unit]=(original,receipt);inputs.update({str(p):digest(p) for p in directory.glob('*.json')})
    # Every numerical decision above precedes geography.
    ref_path=HERE/'reference-admission-v1.json';reference=sealed(ref_path);verify_sources(reference['source_sha256'])
    refs={r['unit']:r['reference_latlon'] for r in reference['rows']}
    helper=HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper)=='sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    spec=importlib.util.spec_from_file_location('offline_geo',helper);geo=importlib.util.module_from_spec(spec);spec.loader.exec_module(geo)
    for row in rows:
        original,receipt=states[row['unit']];r=row['weighted'];r['error_m']=None
        if r['accepted']:r['error_m']=geo.distance_m(geo.latlon_from_enu(*receipt['best']['mean'][:2]),refs[original['binding']['scans'][0]])
    save(HERE/'weighted-marginal-pilot-summary-v1.json',dict(rows=rows,inputs=inputs,reference_sha256=digest(ref_path),
        source_sha256={str(Path(__file__).resolve()):digest(__file__),str(helper):digest(helper)},
        qualification='Optimizer-only same-model/state/budget comparison. Original input and model bindings checked. Errors only after acceptance. Historical timings, exposed development.'))
    fig,axes=plt.subplots(1,3,figsize=(12,4));x=np.arange(3)
    for shift,arm,label in [(-.18,'leading','Leading-branch curvature'),(.18,'weighted','Candidate-weighted curvature')]:
        for ax,key in zip(axes,['iterations','charged_seconds','error_m'],strict=True):
            ax.bar(x+shift,[r[arm][key] if r[arm][key] is not None else np.nan for r in rows],.36,label=label)
    for ax,y in zip(axes,['Accepted steps','Charged inference (seconds)','Accepted reference error (m)'],strict=True):
        ax.set_ylabel(y);ax.set_xticks(x,[r['unit'].split('-')[0] for r in rows]);ax.grid(axis='y',alpha=.2)
    axes[0].legend(fontsize=8);axes[1].axhline(90,color='black',ls='--')
    fig.suptitle('Marginal model: fixed three-single curvature ablation')
    fig.tight_layout();fig.savefig(HERE/'weighted-marginal-pilot-v1.png',dpi=160);plt.close(fig)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
