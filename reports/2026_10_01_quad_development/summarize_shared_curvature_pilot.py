"""Sealed optimizer-only pilot comparison, including every failed case."""
import importlib.util
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_shared_visibility_pilot import HERE,PILOT,sealed,baseline,verify_sources,digest,save


def main():
    rows=[];inputs={};states={}
    old_path=HERE/'shared-visibility-pilot-summary-v1.json'
    old=sealed(old_path);lookup={r['unit']:r for r in old['rows']};inputs[str(old_path)]=digest(old_path)
    verify_sources(old['inputs']);verify_sources(old['source_sha256'])
    for unit in PILOT:
        directory=HERE/'shared-curvature-pilot-v1'/unit
        frozen=sealed(directory/'sources.json');verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
        original,_,_=baseline(unit);audit=sealed(directory/'evaluation.json')
        path=directory/(unit+'.json');receipt=sealed(path) if path.exists() else None
        launch=sealed(directory/(unit+'.launch.json'))
        audit_launch=sealed(directory/'audit-launch.json') if (directory/'audit-launch.json').exists() else None
        accepted=bool(audit['accepted'] and audit_launch and audit_launch['returncode']==0 and audit_launch['within_budget'] and not audit_launch['timed_out'])
        if receipt:
            assert digest(path)==launch['receipt_sha256']
            assert receipt['source_sha256']==frozen['source_sha256']
        best=receipt['best'] if receipt else {}
        rows.append(dict(unit=unit,lbfgs=lookup[unit],curvature=dict(accepted=accepted,
            reason=best.get('reason',audit.get('reason')),gradient_inf=audit.get('scaled_gradient_inf'),
            iterations=best.get('iterations'),incremental_seconds=launch['incremental_seconds'],
            charged_seconds=launch['charged_seconds'],audit_seconds=audit_launch['elapsed_seconds'] if audit_launch else None,
            objective_improvement=audit['initial_objective']-audit['objective'] if 'objective' in audit else None,
            label_changes=audit.get('label_changes_from_baseline'),
            failed_checks=[k for k,v in audit.get('checks',{}).items() if not v])))
        states[unit]=(original,receipt)
        inputs.update({str(p):digest(p) for p in directory.glob('*.json')})
    # Decisions above fixed before geographic reference access.
    ref_path=HERE/'reference-admission-v1.json';reference=sealed(ref_path);verify_sources(reference['source_sha256'])
    refs={r['unit']:r['reference_latlon'] for r in reference['rows']}
    helper=HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper)=='sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    spec=importlib.util.spec_from_file_location('offline_geo',helper);geo=importlib.util.module_from_spec(spec);spec.loader.exec_module(geo)
    for row in rows:
        original,receipt=states[row['unit']];r=row['curvature'];r['error_m']=None;r['position_change_m']=None
        if r['accepted']:
            pos=geo.latlon_from_enu(*receipt['best']['mean'][:2]);oldpos=geo.latlon_from_enu(*original['best']['mean'][:2])
            r['error_m']=geo.distance_m(pos,refs[original['binding']['scans'][0]])
            r['position_change_m']=geo.distance_m(pos,oldpos)
    save(HERE/'shared-curvature-pilot-summary-v1.json',dict(rows=rows,inputs=inputs,
        reference_sha256=digest(ref_path),source_sha256={str(Path(__file__).resolve()):digest(__file__),str(helper):digest(helper)},
        qualification='Same three baseline states and visibility model; direction-computation ablation. Warm exposed development, charged original work. No output selected between arms.'))
    fig,axes=plt.subplots(1,3,figsize=(12,4));x=np.arange(3)
    for offset,arm,label in [(-.18,'lbfgs','L-BFGS'),(.18,'curvature','Residual curvature')]:
        for ax,key in zip(axes,['error_m','charged_seconds','gradient_inf'],strict=True):
            ax.bar(x+offset,[r[arm][key] if r[arm][key] is not None else np.nan for r in rows],.36,label=label)
    axes[0].set_ylabel('Accepted horizontal reference error (m)')
    axes[1].set_ylabel('Charged inference (seconds)');axes[1].axhline(90,color='black',ls='--')
    axes[2].set_ylabel('Maximum scaled gradient');axes[2].set_yscale('log');axes[2].axhline(1e-4,color='black',ls='--')
    for ax in axes:ax.set_xticks(x,[r['unit'].split('-')[0] for r in rows]);ax.grid(axis='y',alpha=.2)
    axes[0].legend(fontsize=8);fig.suptitle('Optimizer-only comparison: horizontal error omitted for unresolved fits')
    fig.tight_layout();fig.savefig(HERE/'shared-curvature-pilot-v1.png',dpi=160);plt.close(fig)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
