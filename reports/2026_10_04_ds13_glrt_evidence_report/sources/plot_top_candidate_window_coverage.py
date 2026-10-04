"""Window coverage through the highest refined-margin candidate only."""
import json,hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

B=Path('/srv/bulk/leo/ds13-spline-replay.4hywxT/full-scan-A-refinement/top-one')
pool=json.loads((B/'candidate-pool.json').read_text());rows=np.array(pool['original_rows'])
frozen=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_03_ds13_coverage_goal/frozen/A-observations.npz')
with np.load(frozen) as a:rx=a['receiver'][rows];ch=a['channel'][rows];groups=a['group'][rows]
assert len(rows)==len(set(groups))==3837
categories=[('Overall',np.ones(len(rows),bool))]+[(f'RX{r} · CH{c}',(rx==r)&(ch==c)) for r in (0,1) for c in (1,2,3,4)]
fig,axes=plt.subplots(1,2,figsize=(12,6),sharey=True);receipt={}
for ax,arm,color in zip(axes,['fitted-c','zero-c'],['#0072b2','#009e73']):
    result=json.loads((B/f'{arm}.json').read_text());owners={x['row_index'] for x in result['final']['assignments']}
    assigned=np.array([int(r) in owners for r in rows]);stats=[]
    for name,mask in categories:
        n=int(sum(mask));k=int(sum(mask&assigned));stats.append(dict(label=name,assigned_windows=k,eligible_windows=n,percent=100*k/n))
    y=np.arange(len(stats));ax.barh(y,[s['percent'] for s in stats],color=color,height=.65)
    for i,s in enumerate(stats):ax.text(1,i,f"{s['percent']:.1f}%   ({s['assigned_windows']:,}/{s['eligible_windows']:,})",va='center',color='white',fontsize=11)
    ax.set(yticks=y,yticklabels=[s['label'] for s in stats],xlim=(0,100),xlabel='Windows assigned through their top candidate (%)',title='Fitted c' if arm=='fitted-c' else 'c = 0')
    ax.grid(axis='x',alpha=.17);ax.set_axisbelow(True);receipt[arm]=stats
axes[0].invert_yaxis()
fig.suptitle('Scan A · assignment of each window’s highest refined GLRT-margin candidate\nGreedy + replacement · one candidate per receiver/channel/20 ms probe',fontsize=14)
fig.text(.5,.015,'Denominator: 3,837 windows with a retained candidate in the existing originally passing cohort.\nNot all recorded windows; no 0.6 cutoff. Assignments are in-sample, not independently identity-certified.',ha='center',fontsize=10)
fig.tight_layout(rect=(0,.09,1,.91));fig.savefig(B/'top-candidate-window-coverage.png',dpi=170)
(B/'top-candidate-window-coverage.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))
