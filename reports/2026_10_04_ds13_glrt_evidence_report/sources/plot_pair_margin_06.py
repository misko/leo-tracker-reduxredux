"""Same retained-cohort pair histogram at post-refinement margin >=0.6."""
import json,itertools,collections,hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

base=Path('/srv/bulk/leo/ds13-spline-replay.4hywxT/full-scan-A-refinement')
source=base/'refined.json';records=json.loads(source.read_text())['records']
retained=[r for r in records if (r['refinement']['margin'] if r['refinement']['status']=='refined' else r['original_margin'])>=.6]
groups=collections.defaultdict(list)
for r in retained:groups[tuple(r['probe_key'])].append(r)
period=1/4.4e-6
values=[abs((a['output_hz']-b['output_hz']+period/2)%period-period/2) for group in groups.values() for a,b in itertools.combinations(group,2)]
counts=np.histogram(values,[0,10,50,100,300,1000,np.inf])[0];assert sum(counts)==len(values)
labels=['<10 Hz','10–50 Hz','50–100 Hz','100–300 Hz','300–1,000 Hz','≥1,000 Hz']
summary=dict(cutoff=.6,candidates=len(retained),pairs=len(values),multi_candidate_probes=sum(len(v)>1 for v in groups.values()),counts=counts.tolist(),percent=(counts/len(values)*100).tolist(),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
fig,ax=plt.subplots(figsize=(11,6))
bars=ax.bar(np.arange(6),summary['percent'],color='#0072b2',width=.7)
for bar,n,p in zip(bars,counts,summary['percent']):ax.text(bar.get_x()+bar.get_width()/2,p+.8,f'{n:,} pairs\n{p:.1f}%',ha='center',va='bottom',fontsize=11)
ax.set(xticks=np.arange(6),xticklabels=labels,ylim=(0,65),ylabel='Share of retained pairs (%)',xlabel='Alias-aware frequency separation after refinement',title=f"Scan A · GLRT margin ≥ 0.6 · {len(retained):,} candidates\n{len(values):,} pairs in {summary['multi_candidate_probes']:,} multi-candidate 20 ms windows")
ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
fig.text(.5,.025,'Both candidates must have margin ≥ 0.6. Every within-probe pair is counted; no consolidation.\nSame refined cohort originally passing margin ≥ 0.025; separation modulo 227.273 kHz.\nFrequency proximity alone does not establish duplicate detections.',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.12,1,1));fig.savefig(base/'pair-distribution-margin-0p6.png',dpi=160)
(base/'pair-distribution-margin-0p6.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
