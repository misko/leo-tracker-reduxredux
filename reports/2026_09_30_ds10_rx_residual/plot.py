import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
d=json.loads((HERE/'results.json').read_text())
for name,digest in d['hashes'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
scans=list(d['summary']['scans'].values())
values=[s['candidate']['median_gain_hz'] for s in scans]
fig,axes=plt.subplots(1,2,figsize=(11,4.6),layout='constrained')
axes[0].bar(range(1,25),values,color=['#197b77' if v>0 else '#bc5449' for v in values])
axes[0].axhline(0,color='black',lw=.8)
axes[0].set(xlabel='Fixed N24 scan order',ylabel='Median paired held-error reduction (Hz)',title='Same-candidate cross-RX transfer\nSupported targets; 21/24 scan medians positive')
m=d['summary']['matched']
axes[1].bar(['Same candidate','Other candidate'],[m['candidate']['median_gain_hz'],m['other']['median_gain_hz']],color=['#197b77','#bc5449'])
axes[1].axhline(0,color='black',lw=.8)
axes[1].set(ylabel='Median paired held-error reduction (Hz)',title='Matched control: 132 targets\nPositive means improvement over zero slope')
fig.suptitle('DS10 conditional residual transfer — not a geographic accuracy measurement')
fig.savefig(HERE/'transfer.png',dpi=160)
