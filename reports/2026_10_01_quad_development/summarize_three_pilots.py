"""Summarize the fixed three-block baseline, retaining all planned outcomes."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from build_selection import digest

HERE=Path(__file__).resolve().parent
rows=[];sources={};prefixes=[]
for block in ['DS9-B01','DS10-B01','DS11-B01']:
    path=HERE/'independent-v2'/block/'evaluation.json'
    assert digest(path)==path.with_suffix('.sha256').read_text().strip()
    sources[str(path)]=digest(path)
    data=json.loads(path.read_text())['rows'];assert len(data)==7
    rows.extend(data)
    prefixes.append(dict(block=block,rows=[next(r for r in data if r['unit']==block+suffix)
                                         for suffix in ['-S1','-D1','-Q']]))
summary={}
for size in [1,2,4]:
    chosen=[r for r in rows if r['size']==size];errors=[r['error_m'] for r in chosen if r['accepted']]
    summary[str(size)]=dict(planned=len(chosen),accepted=len(errors),median_error_m=float(np.median(errors)),
        p90_error_m=float(np.percentile(errors,90)),maximum_error_m=max(errors),
        within1000m=sum(e<=1000 for e in errors),within3000m=sum(e<=3000 for e in errors),
        median_runtime_s=float(np.median([r['runtime_s'] for r in chosen])),
        median_cpu_s=float(np.median([r['cpu_s'] for r in chosen])))
document=dict(summary=summary,matched_prefixes=prefixes,source_sha256=sources,
    summarizer_sha256=digest(__file__),
    qualification='Only3development blocks, not the64scan panel. Nested units and nearby scans are correlated. Quantiles conditional on acceptance; all planned units remain in threshold denominators. No uncertainty calibration or heldout claim.')
out=HERE/'three-pilot-baseline-v1.json'
with out.open('x') as stream:json.dump(document,stream,indent=2,allow_nan=False)
out.with_suffix('.sha256').write_text(digest(out)+'\n')
fig,axes=plt.subplots(1,2,figsize=(11,4.5),constrained_layout=True)
colors=['#3178a8','#df8535','#37936b']
for entry,color in zip(prefixes,colors):
    values=[r['error_m'] if r['accepted'] else np.nan for r in entry['rows']]
    axes[0].plot([0,1,2],values,'-o',label=entry['block'],color=color)
    blockrows=[r for r in rows if r['block_id']==entry['block']]
    for r in blockrows:
        if r['accepted']:
            axes[1].scatter(r['runtime_s'],r['error_m'],color=color,
                            marker={1:'o',2:'s',4:'^'}[r['size']],s=65)
axes[0].set_xticks([0,1,2],['A: one scan','AB: two scans','ABCD: four scans'])
axes[0].set_ylabel('Horizontal error (m)');axes[0].legend()
axes[1].set_xlabel('Cold wall time (s)');axes[1].set_ylabel('Horizontal error (m, logarithmic scale)')
axes[1].set_yscale('log');axes[1].set_title('All21 outcomes: circle=single, square=dual, triangle=quad',fontsize=9)
for ax in axes:ax.grid(alpha=.2)
fig.suptitle('Fixed three-block development pilot · independent scan clocks\nMatched prefixes improve in2/3 blocks; this is not full-panel validation')
fig.savefig(HERE/'three-pilot-baseline-v1.png',dpi=160)
print(json.dumps(summary,indent=2))
