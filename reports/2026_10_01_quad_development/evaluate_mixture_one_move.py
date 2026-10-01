"""Evaluate all nine one-move-policy outcomes after numerical decisions."""
import importlib.util
from pathlib import Path
import numpy as np
from run_window import prepare_window
from check_receiver_curvature import save
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources
from failure_composition_checks import process_ok

HERE=Path(__file__).resolve().parent


def main():
    inputs={};rows=[]
    def read(path):
        value=sealed(path);inputs[str(path)]=digest(path);return value
    choices=read(HERE/'mixture-one-move-v1/choices.json');verify_sources(choices['sources']);verify_sources(choices['inputs'])
    for choice in choices['rows']:
        unit=choice['unit'];directory=HERE/'mixture-one-move-v1'/unit
        launch=read(directory/'launch.json');r=read(directory/'result.json') if (directory/'result.json').exists() else None
        if r:
            freeze=read(directory/'sources.json');verify_sources(freeze['source_sha256']);verify_sources(freeze['inputs']);assert r['move']==choice['move']
        rows.append(dict(unit=unit,size=choice['size'],changed=choice['move'] is not None,accepted=bool(process_ok(launch) and r and r['audit']['accepted']),result=r,launch=launch))
    # All numeric outcomes verified before admitted reference and previous geographic comparisons enter.
    prior={}
    for name in ('mixture-localization-evaluation-v1.json','mixture-window-evaluation-v1.json'):
        value=read(HERE/name);verify_sources(value['sources']);verify_sources(value['inputs']);prior.update({r['unit']:r for r in value['rows']})
    ref=read(HERE/'reference-admission-v1.json');verify_sources(ref['source_sha256']);locations={r['unit']:r['reference_latlon'] for r in ref['rows']}
    helper=HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper)=='sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    spec=importlib.util.spec_from_file_location('one_move_geo',helper);geo=importlib.util.module_from_spec(spec);spec.loader.exec_module(geo)
    for row in rows:
        old=prior[row['unit']]['errors_m'];error=None
        if row['accepted']:
            r=row['result'];refs=[locations[s] for s in r['binding']['scans']];assert all(v==refs[0] for v in refs)
            error=geo.distance_m(geo.latlon_from_enu(*r['fit']['mean'][:2]),refs[0])
        row['errors_m']=dict(independent=old['independent'],fixed_mixture=old['mixture'],one_move=error)
        row['change_vs_fixed_m']=error-old['mixture'] if error is not None else None
        row['change_vs_independent_m']=error-old['independent'] if error is not None else None
        if row['accepted'] and not row['changed']:assert abs(row['change_vs_fixed_m'])<1e-8
    stats={}
    for size in (1,2,4):
        local=[r for r in rows if r['size']==size];valid=all(r['accepted'] for r in local)
        stats[str(size)]=dict(n=3,accepted=sum(r['accepted'] for r in local),
            median_errors_m={k:float(np.median([r['errors_m'][k] for r in local])) for k in ('independent','fixed_mixture','one_move')} if valid else None,
            median_change_vs_fixed_m=float(np.median([r['change_vs_fixed_m'] for r in local])) if valid else None,
            median_change_vs_independent_m=float(np.median([r['change_vs_independent_m'] for r in local])) if valid else None,
            gate_passed=bool(valid and np.median([r['change_vs_independent_m'] for r in local])<0 and max(r['change_vs_independent_m'] for r in local)<=1))
    result=dict(rows=rows,summary=stats,gate_passed=all(v['gate_passed'] for v in stats.values()),
        planned_new_fits=5,accepted_new_fits=sum(r['changed'] and r['accepted'] for r in rows),
        unchanged_outcomes=sum(not r['changed'] for r in rows),inputs=inputs,sources={str(p):digest(p) for p in (Path(__file__).resolve(),helper)})
    verify_sources(inputs);save(HERE/'mixture-one-move-evaluation-v1.json',result)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(11,4.6),constrained_layout=True)
    for i,arm in enumerate(('independent','fixed_mixture','one_move')):
        ax.bar(np.arange(9)+(i-1)*.25,[r['errors_m'][arm] if r['errors_m'][arm] is not None else np.nan for r in rows],.25,label=arm)
    ax.set_xticks(range(9),[r['unit'].replace('-B01-','\n') for r in rows],fontsize=8);ax.set_ylabel('Horizontal error against operator reference (m)')
    ax.set_title('One score-selected assignment move and refit; four windows unchanged');ax.legend();ax.grid(axis='y',alpha=.2)
    fig.savefig(HERE/'mixture-one-move-evaluation-v1.png',dpi=160)
    for r in rows:print(r['unit'],r['accepted'],r['errors_m'],r['change_vs_fixed_m'])
    print(stats,'gate',result['gate_passed'])


if __name__=='__main__':main()
