import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent
result=json.loads((HERE/'results.json').read_text());protocol=json.loads((HERE/'protocol.json').read_text());assert result['complete'];rows=[]
fig,axes=plt.subplots(1,3,figsize=(14,4.5))
for i,s in enumerate(result['scans']):
    baseline=s['scores']['cfo_only']['held_cfo_log_predictive'];gains={a:v['held_cfo_log_predictive']-baseline for a,v in s['scores'].items()};rows.append(dict(session_id=s['session_id'],held_cfo_gain=gains,pair_time_hypotheses=sum(sum(g['pair_counts']) for g in s['groups'])))
    axes[0].bar(np.arange(2)+i*3,[gains['phase_raw'],gains['phase_contamination_10pct']],color=['steelblue','darkorange'])
    for a,v in s['scores'].items():axes[i+1].plot(protocol['timing_s'],v['timing_posterior'],label=a)
    axes[i+1].set_title(s['session_id'][-8:]);axes[i+1].set_xlabel('Scan timing offset (s)');axes[i+1].set_ylabel('Training posterior probability');axes[i+1].legend(fontsize=7)
axes[0].axhline(0,color='k',lw=1);axes[0].set_xticks([.5,3.5],[s['session_id'][-8:] for s in result['scans']]);axes[0].set_ylabel('Held differential-CFO log-score gain');axes[0].set_title('Blue: raw phase; orange: 10% contamination');fig.suptitle('DS6 full-pair association with marginalized pilot phase');fig.tight_layout();fig.savefig(HERE/'association.png',dpi=180)
(HERE/'summary.json').write_text(json.dumps(dict(scans=rows,elapsed_s=result['elapsed_s']),indent=2)+'\n');print(json.dumps(rows,indent=2))
