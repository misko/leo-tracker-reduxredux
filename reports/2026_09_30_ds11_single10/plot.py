"""Static scientific figure generated only from sealed benchmark summaries."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from tables import LABELS
HERE=Path(__file__).resolve().parent
rows=sorted(json.loads((HERE/'summary.json').read_text())['summary'],key=lambda r:r['median_m'] if r['median_m'] is not None else float('inf'))
fig,ax=plt.subplots(figsize=(10,6.5),layout='constrained')
for i,r in enumerate(rows):
    if r['median_m'] is None:continue
    ax.plot([r['median_m']/1000,r['p90_m']/1000],[i,i],color='#94a3b8',lw=2)
    ax.scatter(r['median_m']/1000,i,color='#0369a1',s=48,label='Median' if i==0 else None,zorder=3)
    ax.scatter(r['p90_m']/1000,i,color='#64748b',marker='|',s=150,label='P90' if i==0 else None,zorder=3)
ax.axvline(1,color='#b45309',ls='--',lw=1.2,label='1 km')
ax.set_yticks(range(len(rows)),[f"{LABELS[r['method']]} ({r['qualified']}/32)" for r in rows]);ax.invert_yaxis()
ax.set_xlabel('Distance to unsurveyed roof reference (km)');ax.set_xlim(left=0)
ax.set_title('DS11 · 32 independent single scans · unchanged ten-method benchmark',loc='left',fontsize=12,pad=16)
ax.grid(axis='x',alpha=.2);ax.spines[['top','right']].set_visible(False);fig.legend(loc='outside lower center',ncol=3)
fig.savefig(HERE/'single-scan-errors.png',dpi=170);fig.savefig(HERE/'single-scan-errors.svg')
