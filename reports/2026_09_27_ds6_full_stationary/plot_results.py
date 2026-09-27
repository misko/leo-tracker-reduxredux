"""Standalone before/after geographic errors for completed stationary refits."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent
s=json.loads((HERE/'summary.json').read_text());rows=s['results']
before=np.array([r['baseline_error_m']/1000 for r in rows]);after=np.array([r['stationary_error_m']/1000 for r in rows])
fig,ax=plt.subplots(figsize=(7,6),constrained_layout=True)
for rate,marker in [(2.5,'o'),(5.,'s'),(7.5,'^'),(10.,'D')]:
    mask=np.array([r['rate_msps']==rate for r in rows]);ax.scatter(before[mask],after[mask],label=f'{rate:g} MS/s',marker=marker,s=45,alpha=.8)
limit=max(1.,float(max(before.max(),after.max())))*1.08
ax.plot([0,limit],[0,limit],color='gray',linestyle='--',linewidth=1)
ax.axhline(1,color='black',linestyle=':',linewidth=1);ax.axvline(1,color='black',linestyle=':',linewidth=1)
ax.set(xlim=(0,limit),ylim=(0,limit),xlabel='Original 12-step offset error (km)',ylabel='All-track stationary offset error (km)',
    title=f'DS6: {s["completed"]}/{s["expected"]} scans completed\nBelow diagonal = improved horizontal error')
ax.grid(alpha=.2);ax.legend();fig.savefig(HERE/'errors.png',dpi=160);plt.close(fig)
