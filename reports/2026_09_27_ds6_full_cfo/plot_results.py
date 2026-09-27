"""Plot all 43 frozen-baseline errors after every scan has a terminal result."""
import json
import statistics
from datetime import datetime,timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
summary=json.loads((HERE/'summary.json').read_text())
assert summary['pending']==0,'Do not label a partial sweep as full DS6'
dataset=HERE.parent/'2026_09_27_ds6_cfo_dataset'
fig,ax=plt.subplots(figsize=(11,5))
colors={2.5:'#0072B2',5.:'#E69F00',7.5:'#009E73',10.:'#CC79A7'}
flagged_label_used=False
for rate,color in colors.items():
    rows=[r for r in summary['results'] if r['state']=='complete' and r['rate_msps']==rate]
    times=[datetime.fromtimestamp(json.loads((dataset/f"{r['session_id']}-plan.json").read_text())['start_utc_ns']/1e9,timezone.utc) for r in rows]
    ax.scatter(times,[r['error_m']/1000 for r in rows],c=color,label=f'{rate:g} MS/s',s=38)
    for t,r in zip(times,rows,strict=True):
        if not r['success'] or r['bound_hit']:
            ax.scatter([t],[r['error_m']/1000],marker='x',c='black',s=90,
                label=None if flagged_label_used else 'Optimizer warning / boundary')
            flagged_label_used=True
ax.axhline(1.,color='black',linestyle='--',linewidth=1,label='1 km target')
ax.set_ylabel('Horizontal error to operator reference (km)')
ax.set_xlabel('Capture start (UTC)')
ax.set_title('DS6: fixed-model local CFO baseline — all 43 scans')
ax.grid(alpha=.2);ax.legend(ncol=3,fontsize=8)
fig.autofmt_xdate();fig.tight_layout()
fig.savefig(HERE/'baseline-errors.png',dpi=160);plt.close(fig)
errors=[r['error_m'] for r in summary['results'] if r['state']=='complete']
metrics=dict(completed=summary['completed'],unavailable=summary['unavailable'],sub_km=summary['sub_km'],
    mean_error_m=statistics.mean(errors),median_error_m=statistics.median(errors),max_error_m=max(errors),
    optimizer_warning_count=sum(r.get('success') is False for r in summary['results']),
    boundary_count=sum(r.get('bound_hit',False) for r in summary['results']))
(HERE/'metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
print(json.dumps(metrics,indent=2))
