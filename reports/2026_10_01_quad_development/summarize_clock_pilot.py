"""Complete three-block clock ablation, with paired outcomes and no selection."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from build_selection import digest

HERE=Path(__file__).resolve().parent
rows=[];sources={}
for block in ['DS9-B01','DS10-B01','DS11-B01']:
    path=HERE/('clock-comparison-'+block+'-v1.json')
    assert digest(path)==path.with_suffix('.sha256').read_text().strip()
    sources[str(path)]=digest(path);rows.extend(json.loads(path.read_text())['comparisons'])
summary={}
for size in [2,4]:
    selected=[r for r in rows if r['independent']['size']==size]
    summary[str(size)]={}
    for arm in ['independent','common']:
        accepted=[r[arm] for r in selected if r[arm]['accepted']];errors=[r['error_m'] for r in accepted]
        summary[str(size)][arm]=dict(planned=len(selected),accepted=len(accepted),
            median_error_m=float(np.median(errors)),p90_error_m=float(np.percentile(errors,90)),
            within1000m=sum(e<=1000 for e in errors),within3000m=sum(e<=3000 for e in errors),
            median_runtime_s=float(np.median([r[arm]['runtime_s'] for r in selected])))
    summary[str(size)]['paired_improvements']=sum(r['error_change_m'] is not None and r['error_change_m']<0 for r in selected)
result=dict(rows=rows,summary=summary,source_sha256=sources,summarizer_sha256=digest(__file__),
    decision='Retain independent scan clocks; all3quads worsen and doubles split3/6. Do not promote common clocks or tune a per-block selector from GPS.',
    qualification='Complete nine-window ablation on only three exposed development blocks. Singles mathematically identical and reused. All planned failures retained. Not a full64scan evaluation or uncertainty calibration.')
out=HERE/'clock-pilot-v1.json'
with out.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
out.with_suffix('.sha256').write_text(digest(out)+'\n')
fig,ax=plt.subplots(figsize=(9,5),constrained_layout=True)
for i,row in enumerate(rows):
    if row['independent']['accepted'] and row['common']['accepted']:
        a,b=row['independent']['error_m'],row['common']['error_m']
        ax.plot([a,b],[i,i],color='#aaaaaa',linewidth=2)
        ax.scatter(a,i,color='#3178a8',label='Independent scan clocks' if i==0 else None)
        ax.scatter(b,i,color='#df8535',label='Common clock' if i==0 else None)
    else:ax.text(0,i,'FAILED: see full denominator')
ax.set_yticks(range(len(rows)),[r['unit'].replace('-B01','') for r in rows]);ax.invert_yaxis()
ax.set_xlabel('Horizontal error (m)');ax.grid(axis='x',alpha=.2);ax.legend()
ax.set_title('Common-clock ablation: all three quads worsen\nAll nine new fits accepted; six doubles split evenly between improvement and regression')
fig.savefig(HERE/'clock-pilot-v1.png',dpi=160)
print(json.dumps(summary,indent=2))
