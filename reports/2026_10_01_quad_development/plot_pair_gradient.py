"""Plot the fixed-state diagnostic without changing the acceptance rule."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from build_selection import digest

HERE=Path(__file__).resolve().parent
path=HERE/'pair-gradient-diagnostic-v1.json'
assert digest(path)==path.with_suffix('.sha256').read_text().strip()
data=json.loads(path.read_text());curves=data['curves']
output=path.with_suffix('.png');assert not output.exists()
fig,axes=plt.subplots(1,2,figsize=(10,4),constrained_layout=True)
steps=[c['step'] for c in curves]
axes[0].loglog(steps,[c['disagreement'] for c in curves],'o-')
axes[0].axhline(.005,color='red',linestyle='--',label='Original audit threshold')
axes[0].set_ylabel('Objective derivative disagreement');axes[0].legend()
axes[1].semilogx(steps,[c['tracks'][0]['score_plus']-c['tracks'][0]['score_minus'] for c in curves],'o-')
axes[1].set_ylabel('Track 60 background score: plus minus minus')
for ax in axes:ax.set_xlabel('Perturbation of scan clock (seconds)');ax.grid(alpha=.2)
fig.suptitle('DS11-B03-D2: fixed score jump persists as the time step shrinks\nDiagnostic only; original rejected result remains unchanged')
fig.savefig(output,dpi=160)
