import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent
data=json.loads((HERE/'results.json').read_text());assert data['complete'];rows=[]
for s in data['scans']:
    if not s['evaluable']:rows.append(dict(session_id=s['session_id'],evaluable=False,reason=s['reason']));continue
    baseline=s['scores']['cfo_only']['held_cfo_log_predictive'];rows.append(dict(session_id=s['session_id'],evaluable=True,cfo_only_held=baseline,gains={a:v['held_cfo_log_predictive']-baseline for a,v in s['scores'].items() if a!='cfo_only'},paired_visits=sum(g['paired_visits'] for g in s['groups']),pair_time_hypotheses=sum(sum(g['pair_counts']) for g in s['groups'])))
valid=[r for r in rows if r['evaluable']];fig,ax=plt.subplots(figsize=(10,4.5));names=['nominal','uniform_baseline','transferred_baseline'];x=np.arange(len(valid))
for i,name in enumerate(names):ax.bar(x+(i-1)*.25,[r['gains'][name] for r in valid],.25,label=name)
ax.axhline(0,color='gray',lw=1);ax.set_xticks(x,[r['session_id'][-8:] for r in valid]);ax.set_ylabel('Held differential-CFO log-score gain');ax.legend();ax.set_title('Expanded DS6 phase association: three evaluable scans\nFourth selected scan retained as unavailable');fig.tight_layout();fig.savefig(HERE/'expanded-association.png',dpi=180)
out=dict(rows=rows,total_gain={name:sum(r['gains'][name] for r in valid) for name in names},elapsed_s=data['elapsed_s']);(HERE/'summary.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
