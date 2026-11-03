"""Plot each training timing profile relative to its own sampled maximum."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent
d=json.loads((HERE/'results.json').read_text())
fig,axes=plt.subplots(3,1,figsize=(9,8),sharex=True,layout='constrained')
sessions=list(dict.fromkeys(r['session_id'] for r in d['rows']))
for ax,sid in zip(axes,sessions):
    for r in [r for r in d['rows'] if r['session_id']==sid]:
        y=np.array(r['grid_scores'])
        line,=ax.plot(d['grid_s'],y-y.max(),label=r['arm']+' location')
        ax.axvline(r['inherited_tau_s'],color=line.get_color(),linestyle=':',alpha=.7)
    ax.set_title(sid)
    ax.set_ylim(-35,1)
    ax.set_xlim(-1.2,.9)
    ax.set_ylabel('Training log score\nrelative to own grid maximum')
    ax.grid(alpha=.2)
axes[0].legend()
axes[-1].set_xlabel('Scan timing offset (seconds); dotted lines show inherited timings')
fig.suptitle('DS8 competing timing peaks at two fixed locations\nZoomed view; full −5 to +5 second profiles retained in results.json')
fig.savefig(HERE/'timing-profiles.png',dpi=160)
