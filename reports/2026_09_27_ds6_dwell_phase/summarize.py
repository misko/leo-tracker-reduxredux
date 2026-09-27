"""Compare arms on identical qualified training and held-window support."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from experiment import evaluate
HERE=Path(__file__).resolve().parent
def load_frames(path):
    windows=json.loads(path.read_text())
    for w in windows:
        for d in w['data'].values():
            d['z']=np.array(d['z']['real'])+1j*np.array(d['z']['imag'])
            d['t']=np.array(d['t']);d['s']=np.array(d['s'])
    return windows
before=json.loads((HERE/'results.json').read_text())['results']
after={r['session_id']:r for r in json.loads((HERE/'refined/results.json').read_text())['results']}
rows=[]
for a in before:
    sid=a['session_id'];b=after[sid];train=sorted(set(a['train_windows'])&set(b['train_windows']));held=sorted(set(a['held_windows'])&set(b['held_windows']))
    if len(train)<2 or not held:continue
    row=dict(session_id=sid,visit=a['visit'],train_windows=train,held_windows=held)
    for label,folder in [('original',HERE),('refined',HERE/'refined')]:
        windows=load_frames(folder/f'{sid}-frames.json')
        row[label]={str(bound):evaluate(windows,train,held,bound) for bound in [.2,20.]}
    rows.append(row)
out=dict(selected_dwells=10,evaluable_dwells=len(rows),nonevaluable_dwells=6,comparison='Identical qualified train/held window intersection; per-pilot angular RMS, not position error',rows=rows)
(HERE/'matched-summary.json').write_text(json.dumps(out,indent=2)+'\n')
fig,ax=plt.subplots(figsize=(10,5))
labels=['Original independent','Refined independent','Refined pooled ±0.2 Hz','Refined pooled ±20 Hz']
for row in rows:
    y=[row['original']['0.2']['baseline_held_rms_deg'],row['refined']['0.2']['baseline_held_rms_deg'],row['refined']['0.2']['held_rms_deg'],row['refined']['20.0']['held_rms_deg']]
    ax.plot(range(4),y,'o-',label=row['session_id'][-8:]+f" / visit {row['visit']}")
    print(row['session_id'],[round(v,3) for v in y])
ax.set_xticks(range(4),labels,rotation=12);ax.set_ylabel('Held per-pilot receiver-phase RMS (degrees)');ax.set_title('DS6: matched-window comparison; lower is better');ax.legend();ax.grid(alpha=.3);fig.tight_layout();fig.savefig(HERE/'matched-comparison.png',dpi=160)
