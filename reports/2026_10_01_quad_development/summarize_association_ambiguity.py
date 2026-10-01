"""Aggregate sealed conditional association evidence, retaining failed windows."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_association_ambiguity import HERE,OUT,UNITS,sealed,digest,verify_sources,save


def aggregate(rows):
    if not rows:return dict(tracks=0)
    return dict(tracks=len(rows),top_probability_median=float(np.median([r['top_probability'] for r in rows])),
        top_probability_below95=sum(r['top_probability']<.95 for r in rows),
        top_probability_below50=sum(r['top_probability']<.5 for r in rows),
        background_winners=sum(r['top_index']==r['branches']-1 for r in rows),
        entropy_median=float(np.median([r['entropy'] for r in rows])),
        effective_branches_max=max(r['effective_branches'] for r in rows),
        marginal_correction_sum=sum(r['marginal_correction'] for r in rows),
        omitted_mass_mean={str(k):float(np.mean([r['omitted_mass'][str(k)] for r in rows])) for k in [1,2,4]},
        omitted_mass_max={str(k):max(r['omitted_mass'][str(k)] for r in rows) for k in [1,2,4]})


def main():
    frozen=sealed(OUT/'sources.json');verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
    windows=[];inputs={str(OUT/'sources.json'):digest(OUT/'sources.json')};allrows=[]
    for unit in UNITS:
        path=OUT/(unit+'.json');launchpath=path.with_suffix('.launch.json');launch=sealed(launchpath)
        inputs[str(launchpath)]=digest(launchpath)
        if launch['returncode']!=0 or not launch['within_budget'] or launch['timed_out']:
            windows.append(dict(unit=unit,accepted=False,reason='failed_or_timed_out'));continue
        receipt=sealed(path);assert digest(path)==launch['receipt_sha256']
        assert receipt['freeze_sha256']==digest(OUT/'sources.json')
        inputs[str(path)]=digest(path)
        for r in receipt['rows']:r.update(unit=unit,size=receipt['size'],dataset=unit.split('-')[0])
        allrows.extend(receipt['rows']);windows.append(dict(unit=unit,size=receipt['size'],accepted=True,
            seconds=launch['elapsed_seconds'],**aggregate(receipt['rows'])))
    groups={}
    for field,values in [('size',[1,2,4]),('dataset',['DS9','DS10','DS11'])]:
        groups[field]={str(v):aggregate([r for r in allrows if r[field]==v]) for v in values}
    save(HERE/'association-ambiguity-summary-v1.json',dict(windows=windows,groups=groups,rows=allrows,inputs=inputs,
        source_sha256={str(Path(__file__).resolve()):digest(__file__)},
        qualification='Conditional fitted-state mass; same observations recur across single/pair/quad windows. No calibrated posterior claim, refit, or geographic selection.'))
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    for size in [1,2,4]:
        rows=[r for r in allrows if r['size']==size];p=np.sort([r['top_probability'] for r in rows])
        if len(p):axes[0].plot(p,np.arange(1,len(p)+1)/len(p),label=f'{size} scans, {len(p)} track instances')
        if rows:axes[1].plot([1,2,4],[groups['size'][str(size)]['omitted_mass_mean'][str(k)] for k in [1,2,4]],'.-',label=f'{size} scans')
    axes[0].set_xlabel('Probability of highest-scoring branch');axes[0].set_ylabel('Cumulative track-instance fraction')
    axes[1].set_xlabel('Number of retained branches');axes[1].set_ylabel('Mean omitted conditional mass');axes[1].set_xticks([1,2,4])
    for ax in axes:ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Conditional association ambiguity at fitted states; not calibrated posterior probabilities')
    fig.tight_layout();fig.savefig(HERE/'association-ambiguity-v1.png',dpi=160);plt.close(fig)
    print(json.dumps(dict(windows=windows,groups=groups),indent=2))


if __name__=='__main__':main()
