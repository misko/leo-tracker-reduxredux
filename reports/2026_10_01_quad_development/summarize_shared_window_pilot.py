"""Summarize all seven predeclared windows; keep targeted diagnosis separate."""
import importlib.util
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_shared_window_pilot import HERE,PILOT,BOUNDARY,admit,sealed,save,digest,verify_sources


def main():
    rows=[];inputs={};states={}
    for unit in PILOT:
        directory=HERE/'shared-window-pilot-v1'/unit;frozen=sealed(directory/'sources.json')
        verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
        original,cost,_=admit(unit)
        failure=directory/'policy-failure.json'
        evaluation=sealed(directory/'evaluation.json') if not failure.exists() else dict(accepted=False,reason=sealed(failure)['reason'])
        path=directory/(unit+'.json');receipt=sealed(path) if path.exists() else None
        launch=sealed(path.with_suffix('.launch.json')) if path.with_suffix('.launch.json').exists() else {}
        audit=sealed(directory/'audit-launch.json') if (directory/'audit-launch.json').exists() else {}
        accepted=bool(evaluation['accepted'] and audit.get('returncode')==0 and audit.get('within_budget') and not audit.get('timed_out'))
        if receipt:
            assert digest(path)==launch['receipt_sha256'] and receipt['source_sha256']==frozen['source_sha256']
        best=receipt['best'] if receipt else {}
        rows.append(dict(unit=unit,size=original['binding']['size'],role=frozen['role'],accepted=accepted,
            reason=best.get('reason',evaluation.get('reason')),iterations=best.get('iterations'),
            original_cost_s=cost,incremental_seconds=launch.get('incremental_seconds'),charged_seconds=launch.get('charged_seconds'),
            audit_seconds=audit.get('elapsed_seconds'),gradient_inf=evaluation.get('scaled_gradient_inf'),
            objective_improvement=evaluation['initial_objective']-evaluation['objective'] if 'objective' in evaluation else None,
            label_changes=evaluation.get('label_changes_from_source'),
            max_derivative_error=max((r['error'] for r in evaluation.get('finite_differences',[])),default=None),
            failed_checks=[k for k,v in evaluation.get('checks',{}).items() if not v]))
        states[unit]=(original,receipt);inputs.update({str(p):digest(p) for p in directory.glob('*.json')})
    # All numerical decisions are fixed above, before loading the reference.
    ref_path=HERE/'reference-admission-v1.json';ref=sealed(ref_path);verify_sources(ref['source_sha256'])
    refs={r['unit']:r['reference_latlon'] for r in ref['rows']}
    helper=HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper)=='sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    spec=importlib.util.spec_from_file_location('offline_geo',helper);geo=importlib.util.module_from_spec(spec);spec.loader.exec_module(geo)
    for row in rows:
        original,receipt=states[row['unit']];locations=[refs[s] for s in original['binding']['scans']]
        assert all(p==locations[0] for p in locations)
        old=geo.latlon_from_enu(*original['best']['mean'][:2])
        row['source_error_m']=geo.distance_m(old,locations[0]) if row['unit']!=BOUNDARY else None
        row['error_m']=None;row['position_change_m']=None
        if row['accepted']:
            pos=geo.latlon_from_enu(*receipt['best']['mean'][:2]);row['error_m']=geo.distance_m(pos,locations[0])
            row['position_change_m']=geo.distance_m(pos,old)
    save(HERE/'shared-window-pilot-summary-v1.json',dict(rows=rows,inputs=inputs,reference_sha256=digest(ref_path),
        source_sha256={str(Path(__file__).resolve()):digest(__file__),str(helper):digest(helper)},
        qualification='Six metadata-first pair/quad warm pilots, one separate failure-selected diagnostic. No geographic score for rejected source or failed new output. Not cold acquisition or independent held-out evidence.'))
    ordinary=[r for r in rows if r['role']=='metadata_first'];x=np.arange(len(ordinary))
    fig,axes=plt.subplots(1,2,figsize=(12,4))
    axes[0].bar(x-.18,[r['source_error_m'] for r in ordinary],.36,label='Original baseline')
    axes[0].bar(x+.18,[r['error_m'] if r['error_m'] is not None else np.nan for r in ordinary],.36,label='New model accepted')
    axes[0].set_ylabel('Horizontal reference error (m)');axes[0].legend(fontsize=8)
    axes[1].bar(x,[r['original_cost_s'] for r in ordinary],label='Charged original work')
    axes[1].bar(x,[r['incremental_seconds'] or 0 for r in ordinary],bottom=[r['original_cost_s'] for r in ordinary],label='Refinement')
    axes[1].scatter(x,[90*r['size'] for r in ordinary],marker='_',color='black',label='Budget')
    axes[1].set_ylabel('Charged inference seconds');axes[1].legend(fontsize=8)
    labels=[r['unit'].replace('-B01-','\n')+('' if r['accepted'] else '\nunresolved') for r in ordinary]
    for ax in axes:ax.set_xticks(x,labels);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Metadata-first pair/quad pilot; targeted boundary case reported separately')
    fig.tight_layout();fig.savefig(HERE/'shared-window-pilot-v1.png',dpi=160);plt.close(fig)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
