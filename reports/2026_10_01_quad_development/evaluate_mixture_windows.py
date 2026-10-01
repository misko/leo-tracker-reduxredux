"""Account for all fixed pair/quad outcomes before geographic scoring."""
import importlib.util
from pathlib import Path
import numpy as np
from run_mixture_windows import UNITS
from check_receiver_curvature import save
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources
from failure_composition_checks import process_ok

HERE=Path(__file__).resolve().parent


def main():
    inputs={};rows=[]
    def read(path):
        value=sealed(path);inputs[str(path)]=digest(path);return value
    for unit in UNITS:
        directory=HERE/'mixture-window-pilot-v1'/unit;launch=read(directory/'launch.json')
        completed=process_ok(launch) and (directory/'completion.json').exists()
        if (directory/'sources.json').exists():
            frozen=read(directory/'sources.json');verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
        if completed:assert read(directory/'completion.json')['verified']
        prerequisite=read(directory/'prerequisite.json') if (directory/'prerequisite.json').exists() else None
        arms={}
        for arm in ('independent','mixture'):
            r=read(directory/(arm+'.json')) if (directory/(arm+'.json')).exists() else None
            arms[arm]=dict(accepted=bool(completed and r and r['audit']['accepted']),result=r)
        rows.append(dict(unit=unit,size=4 if unit.endswith('-Q') else 2,launch=launch,prerequisite=prerequisite,arms=arms))
    ref=read(HERE/'reference-admission-v1.json');verify_sources(ref['source_sha256'])
    locations={r['unit']:r['reference_latlon'] for r in ref['rows']}
    helper=HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper)=='sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    spec=importlib.util.spec_from_file_location('mixture_window_geo',helper);geo=importlib.util.module_from_spec(spec);spec.loader.exec_module(geo)
    for row in rows:
        errors={}
        for arm,record in row['arms'].items():
            r=record['result'];error=None
            if record['accepted']:
                refs=[locations[s] for s in r['binding']['scans']];assert all(v==refs[0] for v in refs)
                error=geo.distance_m(geo.latlon_from_enu(*r['fit']['mean'][:2]),refs[0])
            errors[arm]=error
        row['errors_m']=errors
        row['paired_change_m']=errors['mixture']-errors['independent'] if all(v is not None for v in errors.values()) else None
    stats={}
    for size in (2,4):
        local=[r for r in rows if r['size']==size];valid=all(r['paired_change_m'] is not None and r['arms']['independent']['result']['control_equivalent'] for r in local)
        stats[str(size)]=dict(planned_windows=3,valid_pairs=sum(r['paired_change_m'] is not None for r in local),
            baseline_median_m=float(np.median([r['errors_m']['independent'] for r in local])) if valid else None,
            mixture_median_m=float(np.median([r['errors_m']['mixture'] for r in local])) if valid else None,
            median_paired_change_m=float(np.median([r['paired_change_m'] for r in local])) if valid else None,
            gate_passed=bool(valid and np.median([r['paired_change_m'] for r in local])<0 and max(r['paired_change_m'] for r in local)<=1))
    result=dict(rows=rows,summary=stats,accepted_fits=sum(a['accepted'] for r in rows for a in r['arms'].values()),planned_fits=12,
        gate_passed=all(s['gate_passed'] for s in stats.values()),inputs=inputs,sources={str(p):digest(p) for p in (Path(__file__).resolve(),helper)},
        qualification='Six exposed overlapping pair/quad windows; conditional warm fixed memberships. All outcomes retained. No cold or heldout claim.')
    verify_sources(inputs);save(HERE/'mixture-window-evaluation-v1.json',result)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(9,4.5),constrained_layout=True)
    for i,arm in enumerate(('independent','mixture')):
        ax.bar(np.arange(6)+(i-.5)*.34,[r['errors_m'][arm] if r['errors_m'][arm] is not None else np.nan for r in rows],.34,label=arm)
    ax.set_xticks(range(6),[r['unit'].replace('-B01-','\n') for r in rows]);ax.set_ylabel('Horizontal error against operator reference (m)')
    ax.set_title('Unchanged conditional scale mixture on pairs and quads');ax.legend();ax.grid(axis='y',alpha=.2)
    fig.savefig(HERE/'mixture-window-evaluation-v1.png',dpi=160)
    for r in rows:print(r['unit'],r['errors_m'],r['paired_change_m'])
    print(stats,'accepted',result['accepted_fits'],'gate',result['gate_passed'])


if __name__=='__main__':main()
