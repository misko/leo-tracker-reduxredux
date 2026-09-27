import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
fits={name:json.loads((HERE/f'{name}.json').read_text()) for name in ['all','A','B']}
assert all(r['complete'] for r in fits.values())
ref=json.loads((ROOT/'2026_09_27_ds6_roof/pose-authority.json').read_text());reference=[ref['latitude_deg'],ref['longitude_deg']]
def distance(a,b):
    la,lo=np.radians(a);x,y=np.radians(b)
    return float(2*6371008.8*np.arcsin(np.sqrt(np.sin((la-x)/2)**2+np.cos(la)*np.cos(x)*np.sin((lo-y)/2)**2)))
rows=[]
for name,r in fits.items():
    a,b=r['results']['cfo_only'],r['results']['phase'];p=json.loads((HERE/f'{name}-protocol.json').read_text())
    rows.append(dict(fit=name,scans=len(p['sessions']),phase_scans=len(p['phase_sessions']),cfo_error_m=distance(a['coordinates'],reference),phase_error_m=distance(b['coordinates'],reference),phase_shift_m=distance(a['coordinates'],b['coordinates']),held_gain=b['held']-a['held'],both_converged=a['success'] and b['success']))
(HERE/'summary.json').write_text(json.dumps(rows,indent=2)+'\n')
fig,axes=plt.subplots(1,2,figsize=(10,4),constrained_layout=True);x=np.arange(3)
axes[0].bar(x-.17,[r['cfo_error_m'] for r in rows],.34,label='CFO only');axes[0].bar(x+.17,[r['phase_error_m'] for r in rows],.34,label='CFO + phase');axes[0].axhline(1000,color='black',ls='--',label='1 km');axes[0].set(xticks=x,xticklabels=['All 43','Subset A','Subset B'],ylabel='Distance to operator reference (m)',title='Pooled location is already sub-km without phase');axes[0].legend(fontsize=8)
axes[1].bar(x,[r['phase_shift_m']*100 for r in rows]);axes[1].set(xticks=x,xticklabels=['All 43','Subset A','Subset B'],ylabel='Numerical position shift (cm)',title='Tiny phase shifts are not physical precision')
fig.savefig(HERE/'cohort.png',dpi=160);print(json.dumps(rows,indent=2))
