import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
rows={a:json.loads((HERE/f'all-{a}.json').read_text()) for a in ['cfo_only','phase']};assert all(r['complete'] for r in rows.values())
reference=json.loads((ROOT/'2026_09_27_ds6_roof/pose-authority.json').read_text());location=[reference['latitude_deg'],reference['longitude_deg']]
def distance(a,b):
    la,lo=np.radians(a);x,y=np.radians(b)
    return float(2*6371008.8*np.arcsin(np.sqrt(np.sin((la-x)/2)**2+np.cos(la)*np.cos(x)*np.sin((lo-y)/2)**2)))
summary={a:dict(error_m=distance(r['coordinates'],location),train=r['train'],held=r['held'],converged=r['success'],message=r['message'],boundary=r['bound_hit'],nfev=r['nfev'],elapsed_s=r['elapsed_s']) for a,r in rows.items()}
summary['phase_shift_m']=distance(rows['cfo_only']['coordinates'],rows['phase']['coordinates']);summary['held_gain']=rows['phase']['held']-rows['cfo_only']['held']
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
old=json.loads((ROOT/'2026_09_27_ds6_cohort_phase/all.json').read_text())['results'];fig,axes=plt.subplots(1,2,figsize=(10,4),constrained_layout=True);x=np.arange(2)
axes[0].bar(x-.17,[distance(old[a]['coordinates'],location) for a in rows],.34,label='Old profiler');axes[0].bar(x+.17,[summary[a]['error_m'] for a in rows],.34,label='Corrected profiler');axes[0].axhline(1000,color='black',ls='--',label='1 km');axes[0].set(xticks=x,xticklabels=['CFO only','CFO + phase'],ylabel='Distance to operator reference (m)',title='All 43 scans, one stationary position');axes[0].legend(fontsize=8)
axes[1].bar(x,[summary[a]['held']-old[a]['held'] for a in rows]);axes[1].set(xticks=x,xticklabels=['CFO only','CFO + phase'],ylabel='Held log-score change from old profiler',title='Held frequency prediction; not position error')
fig.savefig(HERE/'cohort.png',dpi=160);print(json.dumps(summary,indent=2))
