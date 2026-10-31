"""Post-inference evaluation; the known site is used only here for reporting."""
import csv
import json
import math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from leo.contracts.fast_graph_position_v4 import owners,incumbent_proof,validate_terminal

OUT=Path(__file__).resolve().parent
ROOT=Path('/srv/bulk/leo/research/algo05-promotion-20261031')
def read(p):return json.loads(Path(p).read_text())
def write(p,d):Path(p).write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')
def error(ll):
    lat,lon,tlat,tlon=map(math.radians,(*ll,37.849061591561885,-122.48574968092912))
    a=math.sin((lat-tlat)/2)**2+math.cos(lat)*math.cos(tlat)*math.sin((lon-tlon)/2)**2
    return 12742017.6*math.atan2(math.sqrt(a),math.sqrt(max(0,1-a)))
def old_position(t,a):
    p=incumbent_proof(t)
    return (p['selected']['arms'] if p.get('selected') else p['baseline']['arms'])[a]['endpoint_latlon']

def main():
    rows=[]
    with Path('/srv/bulk/leo-dev/fast-algo02-production-v1/reports/2026_10_31_ds26_confident_recovery/per-case.csv').open() as f:
        for r in csv.DictReader(f):
            if r['state']=='complete' and r['method'] in ('ALGO04','gap_conditional'):
                rows.append(dict(dataset='DS26',case=r['case'],arm=r['arm'],method='ALGO05 policy' if r['method']=='gap_conditional' else 'ALGO04',
                    error_m=float(r['error_m']),associated=int(r['associated']),total=int(r['glrt_points']),basis='sealed cached paired evaluation'))
    selections={r['case']:r['selected'] for r in read(ROOT/'residuals/selections.json')};checks=[]
    for p in sorted((ROOT/'installed-ds27-v2').glob('DS27-*/terminal.json')):
        t=read(p);validate_terminal(t,input_sha256=t['input_sha256']);case=p.parent.name;old=t['incumbent'];candidate=t['candidate']
        before=owners(old);after={a:candidate['trial']['arms'][a]['proposed_owners'] if candidate else before[a] for a in before}
        cached=selections[case];expected=read(Path(cached['path'])/'target_0.json')['arms'] if cached else None
        for arm in before:
            assert after[arm]==(expected[arm]['proposed_owners'] if expected else before[arm])
            old_ll=old_position(old,arm);new_ll=candidate['trial']['arms'][arm]['endpoint_latlon'] if candidate else old_ll
            n=len(candidate['observation_ids']) if candidate else len(read(p.parent/'current/snapshot/inference/SCAN/observations.json')) if (p.parent/'current/snapshot/inference/SCAN/observations.json').exists() else None
            if n is None:
                index=next(e for e in read('/srv/bulk/leo/research/ds27-algo04-20261031/analysis-index.json')['cases'] if e['case']==case)
                n=len(read(index['observations_path']))
            for name,ll,owned in [('ALGO04',old_ll,before[arm]),('ALGO05 policy',new_ll,after[arm])]:
                rows.append(dict(dataset='DS27',case=case,arm=arm,method=name,error_m=error(ll),associated=len(owned),total=n,basis='fresh installed full-cohort replay'))
        checks.append(dict(case=case,owner_sets_exactly_match_cached_ranking=True,decision=t['decision'],failure=t['failure'],seconds=t['recovery_seconds'],read_audit=t['read_audit']))
    assert len(checks)==13
    write(OUT/'installed-ds27-results.json',checks)
    with (OUT/'position-errors.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summary=[]
    fig,axs=plt.subplots(2,2,figsize=(11,8),constrained_layout=True)
    for di,ds in enumerate(('DS26','DS27')):
        for ai,arm in enumerate(('c0','fitted_c')):
            ax=axs[di,ai]
            for method,color in [('ALGO04','#777'),('ALGO05 policy','#225acb')]:
                subset=[r for r in rows if r['dataset']==ds and r['arm']==arm and r['method']==method]
                errors=np.sort([r['error_m'] for r in subset]);ax.step(errors/1000,np.arange(1,len(errors)+1)/len(errors),where='post',color=color,label=method)
                summary.append(dict(dataset=ds,arm=arm,method=method,usable=len(subset),mean_m=float(np.mean(errors)),median_m=float(np.median(errors)),p95_m=float(np.quantile(errors,.95)),
                    associated=sum(r['associated'] for r in subset),total_GLRT=sum(r['total'] for r in subset),associated_percent=100*sum(r['associated'] for r in subset)/sum(r['total'] for r in subset)))
            ax.axvline(.5,color='#aaa',ls=':');ax.set(title=f'{ds} · {arm}',xlabel='Position error (km)',ylabel='Fraction of usable fast scans');ax.legend();ax.grid(alpha=.2)
    fig.savefig(OUT/'position-error-cdf.png',dpi=160);plt.close(fig);write(OUT/'summary.json',summary)
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
