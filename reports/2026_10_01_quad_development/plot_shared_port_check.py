import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from build_selection import digest

here=Path(__file__).resolve().parent;fig,axes=plt.subplots(1,2,figsize=(11,4),constrained_layout=True)
for ax,name,title in zip(axes,['visibility-state-gradient-check-v1','shared-visibility-port-check-v1'],['Association weights','Full residual plus association score']):
    p=here/(name+'.json');assert digest(p)==p.with_suffix('.sha256').read_text().strip()
    rows=json.loads(p.read_text())['rows']
    ax.bar(range(len(rows)),[max(c['max_error'] for c in r['checks']) for r in rows])
    ax.set_xticks(range(len(rows)),[r['unit'] for r in rows],rotation=25,ha='right')
    ax.set_yscale('log');ax.set_ylabel('Maximum absolute gradient discrepancy');ax.set_title(title);ax.grid(axis='y',alpha=.2)
fig.suptitle('Four recorded tracks; selected signal branches and background\nFixed states only, no localization fit')
output=here/'shared-port-gradient-check-v1.png';assert not output.exists();fig.savefig(output,dpi=160)
