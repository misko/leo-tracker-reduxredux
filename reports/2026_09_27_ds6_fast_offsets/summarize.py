import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent
out={}
for name,path in [('rejected_v1',HERE/'rejected-v1/validation.json'),('bracket_checked',HERE/'validation.json')]:
    r=json.loads(path.read_text());assert r['complete'];tracks=[t for s in r['scans'] for t in s['tracks']];differences=[v for t in tracks for v in t['score_differences']]
    out[name]=dict(candidates=sum(t['candidates'] for t in tracks),score_mismatches=sum(abs(v)>1e-6 for v in differences),minimum_score_difference=min(differences),maximum_score_difference=max(differences),maximum_gradient=max(t['max_gradient'] for t in tracks),fallbacks=r['fallbacks'],solve_seconds=r['solve_seconds'],elapsed_s=r['elapsed_s'])
(HERE/'summary.json').write_text(json.dumps(out,indent=2)+'\n')
fig,axes=plt.subplots(1,2,figsize=(9,3.5),constrained_layout=True);names=list(out)
axes[0].bar(range(2),[out[n]['score_mismatches'] for n in names]);axes[0].set(xticks=range(2),xticklabels=['Initial prototype','Bracket check'],ylabel='Candidates differing by >1e-6 log units',title='Agreement with stationary scalar solver')
axes[1].bar(range(2),[out[n]['solve_seconds'] for n in names]);axes[1].set(xticks=range(2),xticklabels=['Initial prototype','Bracket check'],ylabel='Offset solving time (s)',title='5,052 candidate offsets; excludes data loading')
fig.savefig(HERE/'validation.png',dpi=160);print(json.dumps(out,indent=2))
