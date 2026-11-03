import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
s=json.loads((HERE/'summary.json').read_text())
keys=['rx0','rx1','common']
fig,ax=plt.subplots(figsize=(8,4.5),layout='constrained')
values=[s[k]['equal_scan_score_gain'] for k in keys]
bars=ax.bar(['RX0 residual','RX1 residual','Shared residual mean'],values,color=['#197b77','#308ca9','#8067a8'])
for bar,key in zip(bars,keys):
    ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+.0006,f"{s[key]['scans_improved']}/24 scans improve",ha='center')
ax.set_ylim(0,.025)
ax.set_ylabel('Equal-scan mean held log-score gain (nats)')
ax.set_title('DS7–9 scale calibration transfers to DS10\nSame 7,195 held pairs per channel; no geographic fit')
fig.savefig(HERE/'transfer.png',dpi=160)
