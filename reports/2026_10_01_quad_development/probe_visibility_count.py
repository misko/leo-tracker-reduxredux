"""Synthetic duplicate-observation sensitivity, not a localization benchmark."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from smooth_visibility_weights import log_weights
from run_constituent_pair import save,digest

HERE=Path(__file__).resolve().parent
rows=[];width=.1;mass=.8
for margin in [-.1,0.,.1,.2]:
    for count in [1,2,4,8,16,32]:
        logs,_=log_weights(np.full((1,count),margin),np.ones((1,count,1)),width,mass)
        shared=1/(1+np.exp(-margin/width))
        rows.append(dict(margin_deg=margin,observations=count,product_visibility=float(np.exp(logs[0])/mass),
            shared_threshold_visibility=float(shared),background_mass=float(np.exp(logs[-1]))))
output=HERE/'visibility-count-probe-v1.json'
save(output,dict(width_deg=width,signal_mass=mass,rows=rows,
    source_sha256={str(Path(__file__).resolve()):digest(__file__),str(HERE/'smooth_visibility_weights.py'):digest(HERE/'smooth_visibility_weights.py')},
    qualification='Synthetic identical repeated elevation margins. Shared-threshold curve uses one logistic gate for the worst margin; this is continuous but only piecewise differentiable when the minimizing observation changes. No radio fitting or geographic tuning.'))
fig,axes=plt.subplots(1,2,figsize=(10,4),constrained_layout=True)
for margin in [-.1,0.,.1,.2]:
    selected=[r for r in rows if r['margin_deg']==margin]
    for ax,key in zip(axes,['product_visibility','shared_threshold_visibility']):
        ax.plot([r['observations'] for r in selected],[r[key] for r in selected],'o-',label=f'{margin:+.1f}°')
for ax,title in zip(axes,['Product of observation gates','One shared threshold for the track']):
    ax.set_xscale('log',base=2);ax.set_ylim(-.03,1.03);ax.set_xlabel('Number of identical observations')
    ax.set_ylabel('Candidate visibility weight');ax.set_title(title);ax.grid(alpha=.2);ax.legend(title='Elevation margin')
fig.suptitle('Duplicating the same geometric evidence should not imply independent visibility events')
fig.savefig(output.with_suffix('.png'),dpi=160)
print(json.dumps([r for r in rows if r['margin_deg']==0],indent=2))
