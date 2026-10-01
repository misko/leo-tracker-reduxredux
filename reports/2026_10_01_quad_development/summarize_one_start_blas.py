"""Verify and summarize the fixed cold one-start acquisition composition pilot."""
import json
from pathlib import Path
import numpy as np
from screen_seed_prefix import sealed,digest
from summarize_cold_seed_limits import arm_row

HERE=Path(__file__).resolve().parent


def main():
    output=HERE/'one-start-blas-cold-summary-v1.json'
    if output.exists():raise FileExistsError(output)
    inputs={};frozen={};rows=[]
    def read(path):
        data=sealed(path);inputs[str(path)]=digest(path);return data
    for ds in ('DS9','DS10','DS11'):
        unit=ds+'-B01-S1';directory=HERE/'one-start-blas-cold-v1'/unit
        comparison=read(directory/'comparison.json');arms={}
        for name in ('original','blas'):
            arm=directory/name;outcome=comparison['results'][name]
            freeze=read(arm/'sources.json')
            for key in ('source_sha256','inputs'):
                for p,h in freeze[key].items():
                    if p in frozen:assert frozen[p]==h
                    frozen[p]=h
            launch=read(arm/(unit+'.launch.json'));audit=read(arm/'audit-launch.json')
            assert launch==outcome['launch'] and audit==outcome['audit_launch']
            assert launch['freeze_sha256']==digest(arm/'sources.json')
            if (arm/'evaluation.json').exists():assert read(arm/'evaluation.json')==outcome['evaluation']
            path=arm/(unit+'.json')
            if path.exists():
                receipt=read(path);assert digest(path)==launch['receipt_sha256']
            row=arm_row(unit,name,outcome);row['arm']=row.pop('seed_limit');arms[name]=row
        valid=all(a['accepted'] for a in arms.values()) and bool(comparison['equivalence_checks']) and all(comparison['equivalence_checks'].values())
        row=dict(unit=unit,arms=arms,equivalence_checks=comparison['equivalence_checks'],both_accepted_equivalent=valid)
        if valid:
            row.update(observed_wall_saving_fraction=1-arms['blas']['wall_seconds']/arms['original']['wall_seconds'],
                observed_cpu_saving_fraction=1-arms['blas']['cpu_seconds']/arms['original']['cpu_seconds'],
                error_change_m=arms['blas']['error_m']-arms['original']['error_m'])
        rows.append(row)
    for p,h in frozen.items():assert digest(p)==h,p
    result=dict(rows=rows,inputs=inputs,frozen_sources_and_inputs=frozen,
        sources={str(p):digest(p) for p in (Path(__file__).resolve(),HERE/'summarize_cold_seed_limits.py')},
        qualification='Six cold single-scan outcomes with one-start policy fixed. Same physical model and acquired proposals checked. One measurement per arm, fixed alternating order, exposed development scans; no stable speed guarantee or full-panel claim.')
    with output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(10,4),constrained_layout=True)
    for name,label,offset,color in (('original','Original acquisition',-.18,'tab:blue'),('blas','BLAS acquisition',.18,'tab:orange')):
        axes[0].bar(np.arange(3)+offset,[r['arms'][name]['wall_seconds'] for r in rows],.36,label=label,color=color)
        for j,r in enumerate(rows):
            a=r['arms'][name]
            if a['accepted']:axes[1].bar(j+offset,a['error_m'],.36,color=color)
            else:axes[1].text(j+offset,0,'failed',rotation=90,ha='center')
    axes[0].legend();axes[0].set_ylabel('Fresh inference wall time (s)');axes[1].set_ylabel('Accepted reference error (m)')
    for ax in axes:ax.set_xticks(range(3),['DS9','DS10','DS11']);ax.grid(axis='y',alpha=.2)
    fig.suptitle('One-start policy fixed: acquisition implementation only')
    fig.savefig(output.with_suffix('.png'),dpi=160)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
