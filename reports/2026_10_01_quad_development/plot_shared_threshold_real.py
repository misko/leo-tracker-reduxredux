"""Compare one background track's score change before and after weighting change."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from build_selection import digest

here=Path(__file__).resolve().parent
def load(name):
    p=here/name;assert digest(p)==p.with_suffix('.sha256').read_text().strip()
    return json.loads(p.read_text())
old=load('pair-gradient-diagnostic-v1.json');new=load('shared-threshold-real-probe-v1.json')
output=here/'shared-threshold-real-probe-v1.png';assert not output.exists()
fig,ax=plt.subplots(figsize=(7,4),constrained_layout=True)
ax.loglog([r['step'] for r in old['curves']],
    [abs(r['tracks'][0]['score_plus']-r['tracks'][0]['score_minus']) for r in old['curves']],
    'o-',label='Original hard count')
ax.loglog([r['step_s'] for r in new['rows']],[abs(r['score_jump']) for r in new['rows']],
    'o-',label='Shared threshold, illustrative width 0.1°')
ax.set_xlabel('Clock perturbation (seconds)');ax.set_ylabel('Absolute background score change')
ax.set_title('One fixed track: the alternative removes the observed jump\nNo location refit or complete-model validation')
ax.grid(alpha=.2);ax.legend();fig.savefig(output,dpi=160)
