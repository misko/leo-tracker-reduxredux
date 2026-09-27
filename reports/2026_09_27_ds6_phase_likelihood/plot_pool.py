import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent
data=json.loads((HERE/'pool-results.json').read_text());assert data['complete'];rows=[r for r in data['rows'] if 'held_log_score_gain' in r]
fig,axes=plt.subplots(2,1,figsize=(11,6),sharex=True);x=np.arange(len(rows));colors=['steelblue' if r['session_id'].endswith('a2465361') else 'darkorange' for r in rows]
axes[0].bar(x,[r['credible95_radius_deg'] for r in rows],color=colors);axes[0].set_ylabel('Training phase 95% radius (degrees)')
axes[1].bar(x,[r['held_log_score_gain'] for r in rows],color=colors);axes[1].axhline(0,color='k',lw=1);axes[1].set_ylabel('Held-window log-score gain');axes[1].set_xticks(x,[str(r['visit']) for r in rows]);axes[1].set_xlabel('Visit index (four unavailable dwells retained in JSON)')
fig.suptitle('DS6 pooled phase likelihood: blue 5 MS/s, orange 7.5 MS/s\nκ=16, within-dwell DD slope integrated over ±0.2 Hz');fig.tight_layout();fig.savefig(HERE/'pooled-phase.png',dpi=180)
