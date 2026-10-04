"""Frequency separation of all within-probe candidate pairs after refinement."""
import json,itertools,collections,hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

base=Path('/srv/bulk/leo/ds13-spline-replay.4hywxT/full-scan-A-refinement')
source=base/'refined.json';r=json.loads(source.read_text());groups=collections.defaultdict(list)
for row in r['records']:groups[tuple(row['probe_key'])].append(row)
period=1/4.4e-6
dist=lambda a,b:abs((a-b+period/2)%period-period/2)
values=np.array([dist(a['output_hz'],b['output_hz']) for rows in groups.values() for a,b in itertools.combinations(rows,2)])
assert len(values)==5901
edges=[0,10,50,100,300,1000,np.inf];counts=np.histogram(values,edges)[0]
labels=['<10 Hz','10–50 Hz','50–100 Hz','100–300 Hz','300–1,000 Hz','≥1,000 Hz']
fig,ax=plt.subplots(figsize=(10,5.5));x=np.arange(len(counts));bars=ax.bar(x,counts/len(values)*100,color='#0072b2',width=.7)
for bar,count in zip(bars,counts):ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+.8,f'{count:,} pairs\n{count/len(values):.1%}',ha='center',va='bottom',fontsize=11)
ax.set(xticks=x,xticklabels=labels,ylim=(0,64),ylabel='Share of within-window candidate pairs (%)',xlabel='Alias-aware frequency separation after refinement',title='Scan A · after candidate-guided GLRT refinement\n5,901 pairs across 1,946 multi-candidate 20 ms windows')
ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
fig.text(.5,.025,'Every pair within the same probe is counted; a window with n candidates contributes n(n−1)/2 pairs.\nSeparation is modulo 227.273 kHz. No consolidation; five failed refinements retain original frequencies.\nLarge separations can be different signals. Frequency proximity alone does not establish duplicates.',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.13,1,1));fig.savefig(base/'after-refinement-pair-distribution.png',dpi=170)
summary=dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),pair_count=len(values),multi_candidate_probes=sum(len(v)>1 for v in groups.values()),bins=labels,counts=counts.tolist(),percent=(counts/len(values)*100).tolist(),median_hz=float(np.median(values)),under100=int(sum(values<100)),max_hz=float(max(values)))
(base/'after-refinement-pair-distribution.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
