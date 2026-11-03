"""Display audited errors and actual cold runtimes for one quad."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from build_selection import digest

HERE=Path(__file__).resolve().parent
path=HERE/'independent-v2/DS9-B01/evaluation.json'
assert digest(path)==path.with_suffix('.sha256').read_text().strip()
rows=json.loads(path.read_text())['rows']
labels=['A','B','C','D','AB','CD','ABCD']
fig,axes=plt.subplots(1,2,figsize=(10,4),constrained_layout=True)
colors=['#3178a8']*4+['#df8535']*2+['#37936b']
for i,(row,label) in enumerate(zip(rows,labels)):
    if row['accepted']:
        axes[0].bar(label,row['error_m'],color=colors[i])
        axes[0].text(i,row['error_m'],f"{row['error_m']:.0f}",ha='center',va='bottom',fontsize=9)
    else:
        axes[0].text(i,0,'FAILED',rotation=90,ha='center',va='bottom')
    axes[1].bar(label,row['runtime_s'],color=colors[i])
axes[0].set_ylabel('Horizontal error (m)')
axes[1].set_ylabel('Cold wall time (s)')
for ax in axes:
    ax.grid(axis='y',alpha=.2)
    ax.margins(y=.2)
fig.suptitle('DS9 first quad: shared position, independent scan nuisance parameters\nOne development block; nested windows are correlated')
fig.savefig(HERE/'pilot-ds9-v1.png',dpi=160)
