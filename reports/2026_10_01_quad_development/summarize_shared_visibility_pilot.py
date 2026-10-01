"""Report every frozen pilot outcome; reference scoring follows numerical decisions."""
import importlib.util
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_shared_visibility_pilot import HERE, PILOT, sealed, baseline, digest, verify_sources, save


def main():
    rows=[]; inputs={}; states={}
    for unit in PILOT:
        directory=HERE/'shared-visibility-pilot-v1'/unit
        frozen=sealed(directory/'sources.json')
        verify_sources(frozen['source_sha256']); verify_sources(frozen['inputs'])
        original,cost,_=baseline(unit)
        audit=sealed(directory/'evaluation.json')
        launch=sealed(directory/(unit+'.launch.json'))
        path=directory/(unit+'.json')
        receipt=sealed(path) if path.exists() else None
        audit_launch=sealed(directory/'audit-launch.json') if (directory/'audit-launch.json').exists() else None
        accepted=bool(audit['accepted'] and audit_launch and audit_launch['returncode']==0
                      and audit_launch['within_budget'] and not audit_launch['timed_out'])
        if receipt:
            assert digest(path)==launch['receipt_sha256']
            assert receipt['source_sha256']==frozen['source_sha256']
        for p in directory.glob('*.json'): inputs[str(p)]=digest(p)
        best=receipt['best'] if receipt else {}
        rows.append(dict(unit=unit,accepted=accepted,reason=best.get('reason',audit.get('reason')),
            original_cost_s=cost,incremental_seconds=launch['incremental_seconds'],
            charged_seconds=launch['charged_seconds'],audit_seconds=audit_launch['elapsed_seconds'] if audit_launch else None,
            iterations=best.get('iterations'),gradient_inf=audit.get('scaled_gradient_inf'),
            objective_improvement=audit.get('initial_objective',0)-audit.get('objective',0) if 'objective' in audit else None,
            label_changes=audit.get('label_changes_from_baseline'),
            failed_checks=[k for k,v in audit.get('checks',{}).items() if not v],
            max_derivative_error=max((r['error'] for r in audit.get('finite_differences',[])),default=None)))
        states[unit]=(original,receipt)
    # All acceptance decisions above are fixed before loading geographic references.
    ref_path=HERE/'reference-admission-v1.json'; reference=sealed(ref_path)
    verify_sources(reference['source_sha256']); refs={r['unit']:r['reference_latlon'] for r in reference['rows']}
    helper=HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper)=='sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    spec=importlib.util.spec_from_file_location('offline_geo',helper)
    geo=importlib.util.module_from_spec(spec);spec.loader.exec_module(geo)
    for row in rows:
        original,receipt=states[row['unit']]; truth=refs[original['binding']['scans'][0]]
        old=geo.latlon_from_enu(*original['best']['mean'][:2])
        row['baseline_error_m']=geo.distance_m(old,truth)
        row['error_m']=None; row['position_change_m']=None
        if row['accepted']:
            new=geo.latlon_from_enu(*receipt['best']['mean'][:2])
            row['error_m']=geo.distance_m(new,truth); row['position_change_m']=geo.distance_m(old,new)
    save(HERE/'shared-visibility-pilot-summary-v1.json',dict(rows=rows,inputs=inputs,
        reference_sha256=digest(ref_path),source_sha256={str(Path(__file__).resolve()):digest(__file__),str(helper):digest(helper)},
        qualification='Three preselected exposed development singles. Warm refinement with original cost charged; audit time separate. Both model and optimizer changed. Errors only for numerically accepted outputs; operator reference unsurveyed.'))
    fig,axes=plt.subplots(1,3,figsize=(13,4)); x=np.arange(len(rows))
    axes[0].bar(x-.18,[r['baseline_error_m'] for r in rows],.36,label='Baseline')
    axes[0].bar(x+.18,[r['error_m'] if r['error_m'] is not None else np.nan for r in rows],.36,label='New model accepted')
    axes[0].set_ylabel('Horizontal reference error (m)');axes[0].legend(fontsize=8)
    axes[1].bar(x,[r['original_cost_s'] for r in rows],label='Charged original fit')
    axes[1].bar(x,[r['incremental_seconds'] for r in rows],bottom=[r['original_cost_s'] for r in rows],label='New refinement')
    axes[1].axhline(90,color='black',ls='--',lw=1);axes[1].set_ylabel('Inference time (s)');axes[1].legend(fontsize=8)
    axes[2].bar(x,[r['gradient_inf'] if r['gradient_inf'] is not None else np.nan for r in rows])
    axes[2].axhline(1e-4,color='black',ls='--',lw=1,label='Stopping threshold');axes[2].set_yscale('log')
    axes[2].set_ylabel('Maximum scaled gradient');axes[2].legend(fontsize=8)
    for ax in axes:
        ax.set_xticks(x,[r['unit'].split('-')[0]+'\n'+('accepted' if r['accepted'] else 'unresolved') for r in rows]);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Shared-threshold visibility: fixed three-single warm pilot')
    fig.tight_layout();fig.savefig(HERE/'shared-visibility-pilot-v1.png',dpi=160);plt.close(fig)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
