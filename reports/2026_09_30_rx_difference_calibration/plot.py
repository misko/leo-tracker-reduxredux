import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import NullLocator, ScalarFormatter

HERE=Path(__file__).resolve().parent
d=json.loads((HERE/'results.json').read_text());s=d['summary']
fig,axes=plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
scores=s['scan_scores']
axes[0].bar(range(1,len(scores)+1),[r['mean_score_gain'] for r in scores],color='#197b77')
axes[0].axhline(0,color='black',lw=.8)
axes[0].set(xlabel='DS10 scan order in evaluation',ylabel='Mean held log-score gain (nats)',title='Transfer to DS10: 24/24 scans improve')
features=[p['feature'] for p in d['pairs'] if p['dataset']=='DS10']
x=np.geomspace(min(features),max(features),200)
a,b=s['fits']['paired_scale']['params']
axes[1].loglog(x,np.exp(a)*x**b,label='DS7–9 fitted difference scale',color='#197b77')
axes[1].axhline(s['constant_scale_hz'],color='#bc5449',linestyle='--',label='Constant baseline')
axes[1].set(xlabel='Training RX-difference MAD feature (Hz)',ylabel='Predicted Student-t4 scale (Hz)',title='Predicting paired disagreement, not absolute CFO error')
axes[1].legend()
axes[1].set_xticks([30,100,300])
axes[1].xaxis.set_major_formatter(ScalarFormatter())
axes[1].xaxis.set_minor_locator(NullLocator())
fig.suptitle('Cross-receiver difference calibration; no geographic weighting applied')
fig.savefig(HERE/'calibration.png',dpi=160)
