"""Paired single-recording errors from audited policy artifacts only."""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


HERE=Path(__file__).resolve().parent
paths=[HERE/'policy-original32-audited.json',HERE/'policy-additional12-audited.json']
documents=[json.loads(path.read_text()) for path in paths]
fig,axes=plt.subplots(1,2,figsize=(10.5,5.2),layout='constrained')
for ax,document,title in zip(axes,documents,['Original 32 · exposed development','Additional 12 · frozen policy']):
    rows=document['rows']
    valid=[row for row in rows if row['qualified']]
    limit=max([1]+[row[key]/1000 for row in valid for key in ('baseline_error_m','error_m')])*1.08
    ax.plot([0,limit],[0,limit],color='#64748b',lw=1,label='Unchanged error')
    for selection,color,marker,label in [('challenger','#0369a1','o','Source-balanced fit'),
                                          ('iid_fallback','#c2410c','s','IID fallback')]:
        subset=[row for row in valid if row['selection']==selection]
        if subset:
            ax.scatter([row['baseline_error_m']/1000 for row in subset],
                       [row['error_m']/1000 for row in subset],c=color,marker=marker,s=35,
                       alpha=.85,label=label,zorder=3)
    ax.set(xlim=(0,limit),ylim=(0,limit),xlabel='Original IID error (km)',
           ylabel='Frozen policy error (km)',title=title)
    ax.set_aspect('equal',adjustable='box')
    ax.grid(alpha=.2)
    ax.spines[['top','right']].set_visible(False)
    wins=sum(row['error_m']<row['baseline_error_m'] for row in valid)
    fallback=sum(row['selection']=='iid_fallback' for row in valid)
    ax.text(.04,.96,f'{wins}/{len(rows)} improved\n{len(valid)}/{len(rows)} outputs · {fallback} fallback',
            transform=ax.transAxes,ha='left',va='top',fontsize=9)
    ax.legend(loc='lower right',fontsize=8)
fig.suptitle('DS11 independent single scans · lower than diagonal is better',fontsize=13)
fig.supxlabel('Distance to unsurveyed roof reference; same-site development, no cross-scan pooling',fontsize=9)
for suffix in ('png','svg'):
    fig.savefig(HERE/f'policy-paired-errors.{suffix}',dpi=170)
with (HERE/'policy-plot-sources.json').open('x') as stream:
    json.dump({str(path):hashlib.sha256(path.read_bytes()).hexdigest()
               for path in [*paths,Path(__file__)]},stream,indent=2)
