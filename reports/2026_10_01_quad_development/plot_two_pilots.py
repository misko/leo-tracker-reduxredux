"""Frozen two-block comparison; log error axis exposes the poor single scan."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from build_selection import digest

HERE=Path(__file__).resolve().parent
fig,axes=plt.subplots(1,2,figsize=(11,4.5),constrained_layout=True)
labels=['A','B','C','D','AB','CD','ABCD']
for block,color,offset in [('DS9-B01','#3178a8',-.10),('DS10-B01','#df8535',.10)]:
    path=HERE/'independent-v2'/block/'evaluation.json'
    assert digest(path)==path.with_suffix('.sha256').read_text().strip()
    rows=json.loads(path.read_text())['rows']
    assert all(r['accepted'] for r in rows)
    x=[i+offset for i in range(7)]
    axes[0].scatter(x,[r['error_m'] for r in rows],color=color,label=block,s=45)
    axes[1].scatter(x,[r['runtime_s'] for r in rows],color=color,label=block,s=45)
    axes[0].plot([x[i] for i in [0,4,6]],[rows[i]['error_m'] for i in [0,4,6]],color=color,alpha=.5)
axes[0].set_yscale('log');axes[0].set_ylabel('Horizontal error (m, logarithmic scale)')
axes[1].set_ylabel('Cold wall time (s)')
for ax in axes:
    ax.set_xticks(range(7),labels);ax.grid(alpha=.2);ax.legend()
fig.suptitle('Two development quads · shared position, independent scan nuisances\nLines connect matched A → AB → ABCD; all 14 fits pass numerical audit')
fig.savefig(HERE/'pilot-two-blocks-v1.png',dpi=160)
