"""Compare marginal versus hard association with identical warm starts and budgets."""
import importlib.util
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_shared_visibility_pilot import HERE,PILOT,sealed,baseline,verify_sources,digest,save


def main():
    prior_path=HERE/'shared-curvature-pilot-summary-v1.json';prior=sealed(prior_path)
    verify_sources(prior['inputs']);verify_sources(prior['source_sha256'])
    lookup={r['unit']:r['curvature'] for r in prior['rows']};inputs={str(prior_path):digest(prior_path)}
    rows=[];states={}
    for unit in PILOT:
        directory=HERE/'marginal-pilot-v1'/unit;frozen=sealed(directory/'sources.json')
        verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
        original,_,_=baseline(unit);evaluation=sealed(directory/'evaluation.json')
        path=directory/(unit+'.json');receipt=sealed(path) if path.exists() else None
        launch=sealed(path.with_suffix('.launch.json'))
        audit=sealed(directory/'audit-launch.json') if (directory/'audit-launch.json').exists() else {}
        accepted=bool(evaluation['accepted'] and audit.get('returncode')==0 and audit.get('within_budget') and not audit.get('timed_out'))
        if receipt:assert digest(path)==launch['receipt_sha256'] and receipt['source_sha256']==frozen['source_sha256']
        best=receipt['best'] if receipt else {}
        rows.append(dict(unit=unit,hard=lookup[unit],marginal=dict(accepted=accepted,
            reason=best.get('reason',evaluation.get('reason')),iterations=best.get('iterations'),
            gradient_inf=evaluation.get('scaled_gradient_inf'),incremental_seconds=launch['incremental_seconds'],
            charged_seconds=launch['charged_seconds'],audit_seconds=audit.get('elapsed_seconds'),
            objective_improvement=evaluation['initial_objective']-evaluation['objective'] if 'objective' in evaluation else None,
            label_changes=evaluation.get('label_changes_from_baseline'),
            max_derivative_error=max((r['error'] for r in evaluation.get('finite_differences',[])),default=None),
            failed_checks=[k for k,v in evaluation.get('checks',{}).items() if not v])))
        states[unit]=(original,receipt);inputs.update({str(p):digest(p) for p in directory.glob('*.json')})
    ref_path=HERE/'reference-admission-v1.json';reference=sealed(ref_path);verify_sources(reference['source_sha256'])
    refs={r['unit']:r['reference_latlon'] for r in reference['rows']}
    helper=HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper)=='sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    spec=importlib.util.spec_from_file_location('offline_geo',helper);geo=importlib.util.module_from_spec(spec);spec.loader.exec_module(geo)
    for row in rows:
        original,receipt=states[row['unit']];m=row['marginal'];m['error_m']=None;m['position_change_m']=None
        if m['accepted']:
            pos=geo.latlon_from_enu(*receipt['best']['mean'][:2]);old=geo.latlon_from_enu(*original['best']['mean'][:2])
            m['error_m']=geo.distance_m(pos,refs[original['binding']['scans'][0]]);m['position_change_m']=geo.distance_m(pos,old)
    save(HERE/'marginal-pilot-summary-v1.json',dict(rows=rows,inputs=inputs,reference_sha256=digest(ref_path),
        source_sha256={str(Path(__file__).resolve()):digest(__file__),str(helper):digest(helper)},
        qualification='Same baseline states and curvature optimizer; full-catalogue marginal versus hard association. All failure denominators preserved, reference read after numerical decisions.'))
    fig,axes=plt.subplots(1,3,figsize=(12,4));x=np.arange(3)
    for shift,arm,label in [(-.18,'hard','Hard association'),(.18,'marginal','Marginal association')]:
        for ax,key in zip(axes,['error_m','charged_seconds','gradient_inf'],strict=True):
            ax.bar(x+shift,[r[arm][key] if r[arm][key] is not None else np.nan for r in rows],.36,label=label)
    axes[0].set_ylabel('Accepted horizontal reference error (m)');axes[0].legend(fontsize=8)
    axes[1].set_ylabel('Charged inference (seconds)');axes[1].axhline(90,color='black',ls='--')
    axes[2].set_ylabel('Maximum scaled gradient');axes[2].set_yscale('log');axes[2].axhline(1e-4,color='black',ls='--')
    for ax in axes:ax.set_xticks(x,[r['unit'].split('-')[0] for r in rows]);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Matched marginal pilot: horizontal errors omitted for unresolved fits')
    fig.tight_layout();fig.savefig(HERE/'marginal-pilot-v1.png',dpi=160);plt.close(fig)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
