"""Failure-preserving matched pair/quad comparison after all numerical outcomes."""
import importlib.util
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_marginal_window_pilot import PILOT
from run_shared_window_pilot import HERE,admit,sealed,digest,verify_sources,save


def main():
    prior_path=HERE/'shared-window-pilot-summary-v1.json';prior=sealed(prior_path)
    verify_sources(prior['inputs']);verify_sources(prior['source_sha256'])
    lookup={r['unit']:r for r in prior['rows']};inputs={str(prior_path):digest(prior_path)};rows=[];states={}
    for unit in PILOT:
        directory=HERE/'marginal-window-pilot-v1'/unit;frozen=sealed(directory/'sources.json')
        verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
        original,_,_=admit(unit);policy=directory/'policy-failure.json'
        evaluation=sealed(directory/'evaluation.json') if not policy.exists() else dict(accepted=False,reason=sealed(policy)['reason'])
        path=directory/(unit+'.json');receipt=sealed(path) if path.exists() else None
        launch=sealed(path.with_suffix('.launch.json')) if path.with_suffix('.launch.json').exists() else {}
        audit=sealed(directory/'audit-launch.json') if (directory/'audit-launch.json').exists() else {}
        accepted=bool(evaluation['accepted'] and audit.get('returncode')==0 and audit.get('within_budget') and not audit.get('timed_out'))
        if receipt:assert digest(path)==launch['receipt_sha256'] and receipt['source_sha256']==frozen['source_sha256']
        best=receipt['best'] if receipt else {}
        rows.append(dict(unit=unit,size=original['binding']['size'],hard=lookup[unit],marginal=dict(accepted=accepted,
            reason=best.get('reason',evaluation.get('reason')),iterations=best.get('iterations'),gradient_inf=evaluation.get('scaled_gradient_inf'),
            incremental_seconds=launch.get('incremental_seconds'),charged_seconds=launch.get('charged_seconds'),audit_seconds=audit.get('elapsed_seconds'),
            objective_improvement=evaluation['initial_objective']-evaluation['objective'] if 'objective' in evaluation else None,
            label_changes=evaluation.get('label_changes_from_source'),
            max_derivative_error=max((r['error'] for r in evaluation.get('finite_differences',[])),default=None),
            failed_checks=[k for k,v in evaluation.get('checks',{}).items() if not v])))
        states[unit]=(original,receipt);inputs.update({str(p):digest(p) for p in directory.glob('*.json')})
    # Numerical decisions for every planned window precede reference access.
    ref_path=HERE/'reference-admission-v1.json';reference=sealed(ref_path);verify_sources(reference['source_sha256'])
    refs={r['unit']:r['reference_latlon'] for r in reference['rows']}
    helper=HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper)=='sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    spec=importlib.util.spec_from_file_location('offline_geo',helper);geo=importlib.util.module_from_spec(spec);spec.loader.exec_module(geo)
    for row in rows:
        original,receipt=states[row['unit']];m=row['marginal'];m['error_m']=None;m['position_change_m']=None
        locations=[refs[s] for s in original['binding']['scans']];assert all(p==locations[0] for p in locations)
        if m['accepted']:
            pos=geo.latlon_from_enu(*receipt['best']['mean'][:2]);old=geo.latlon_from_enu(*original['best']['mean'][:2])
            m['error_m']=geo.distance_m(pos,locations[0]);m['position_change_m']=geo.distance_m(pos,old)
    save(HERE/'marginal-window-pilot-summary-v1.json',dict(rows=rows,inputs=inputs,reference_sha256=digest(ref_path),
        source_sha256={str(Path(__file__).resolve()):digest(__file__),str(helper):digest(helper)},
        qualification='Six predeclared warm pair/quad windows, same original states and curvature optimizer; full marginal vs hard association. No geographic replacement; failures have no scored error.'))
    fig,axes=plt.subplots(1,2,figsize=(12,4));x=np.arange(len(rows))
    for shift,arm,label in [(-.18,'hard','Hard association'),(.18,'marginal','Marginal association')]:
        for ax,key in zip(axes,['error_m','charged_seconds'],strict=True):
            ax.bar(x+shift,[r[arm][key] if r[arm][key] is not None else np.nan for r in rows],.36,label=label)
    axes[0].set_ylabel('Accepted horizontal reference error (m)');axes[0].legend(fontsize=8)
    axes[1].set_ylabel('Charged inference seconds');axes[1].scatter(x,[90*r['size'] for r in rows],marker='_',color='black',label='Budget')
    axes[1].legend(fontsize=8)
    labels=[r['unit'].replace('-B01-','\n')+('' if r['marginal']['accepted'] else '\nunresolved') for r in rows]
    for ax in axes:ax.set_xticks(x,labels);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Matched marginal pairs/quads: failed outputs retain no geographic score')
    fig.tight_layout();fig.savefig(HERE/'marginal-window-pilot-v1.png',dpi=160);plt.close(fig)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
