"""Re-filter existing refined candidates; not a new zero-gate acquisition."""
import json,itertools,collections,hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

base=Path('/srv/bulk/leo/ds13-spline-replay.4hywxT/full-scan-A-refinement')
source=base/'refined.json';records=json.loads(source.read_text())['records']
assert len(records)==7382
edges=[0,10,50,100,300,1000,np.inf]
labels=['<10 Hz','10–50 Hz','50–100 Hz','100–300 Hz','300–1,000 Hz','≥1,000 Hz']
period=1/4.4e-6
def score(r):
    return r['refinement']['margin'] if r['refinement']['status']=='refined' else r['original_margin']
summaries=[]
for cutoff in [0.,.025,.2]:
    retained=[r for r in records if score(r)>=cutoff];groups=collections.defaultdict(list)
    for r in retained:groups[tuple(r['probe_key'])].append(r)
    differences=[abs((a['output_hz']-b['output_hz']+period/2)%period-period/2) for group in groups.values() for a,b in itertools.combinations(group,2)]
    counts=np.histogram(differences,edges)[0];assert sum(counts)==len(differences)
    summaries.append(dict(cutoff=cutoff,candidates=len(retained),pairs=len(differences),multi_candidate_probes=sum(len(v)>1 for v in groups.values()),counts=counts.tolist(),percent=(counts/max(1,len(differences))*100).tolist(),fallback_candidates=sum(r['refinement']['status']!='refined' for r in retained)))
assert all(a['candidates']>=b['candidates'] and a['pairs']>=b['pairs'] for a,b in zip(summaries,summaries[1:]))
fig,axes=plt.subplots(3,1,figsize=(11,12),sharex=True,sharey=True)
for ax,s in zip(axes,summaries):
    bars=ax.bar(np.arange(6),s['percent'],color='#0072b2',width=.7)
    for bar,n,p in zip(bars,s['counts'],s['percent']):
        ax.text(bar.get_x()+bar.get_width()/2,p+.8,f'{n:,} pairs\n{p:.1f}%',ha='center',va='bottom',fontsize=10)
    ax.set(ylim=(0,65),ylabel='Share of retained pairs (%)',title=f"GLRT margin ≥ {s['cutoff']:g} · {s['candidates']:,} candidates\n{s['pairs']:,} pairs in {s['multi_candidate_probes']:,} multi-candidate windows")
    ax.set_xticks(np.arange(6),labels);ax.tick_params(axis='x',labelbottom=True);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
axes[-1].set_xlabel('Alias-aware frequency separation after refinement')
fig.suptitle('Scan A · candidate-pair separation at different GLRT margin cutoffs\nExisting refined cohort only: originally passing margin ≥ 0.025',fontsize=15)
fig.text(.5,.012,'Both candidates must pass the cutoff; every within-probe pair is counted. Percentages use each panel’s retained-pair total.\nMargin = exact score − control score. Five failed refinements use original frequency/margin. No consolidation.\nCutoff 0 does NOT include originally rejected candidates; this is not a full zero-threshold detector rerun.',ha='center',fontsize=10)
fig.tight_layout(rect=(0,.065,1,.94));fig.savefig(base/'pair-distribution-margin-cutoffs.png',dpi=160)
(base/'pair-distribution-margin-cutoffs.json').write_text(json.dumps(dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),summaries=summaries,bins=labels,scope=__doc__),indent=2))
print(json.dumps(summaries,indent=2))
