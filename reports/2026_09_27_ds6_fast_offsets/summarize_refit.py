import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent
rows={arm:json.loads((HERE/'refit'/f'{arm}.json').read_text()) for arm in ['cfo_only','phase']}
assert all(r['complete'] for r in rows.values())
ref=json.loads((HERE.parent/'2026_09_27_ds6_roof/pose-authority.json').read_text())
def distance(a,b):
    la,lo=np.radians(a);x,y=np.radians(b)
    return float(2*6371008.8*np.arcsin(np.sqrt(np.sin((la-x)/2)**2+np.cos(la)*np.cos(x)*np.sin((lo-y)/2)**2)))
summary={arm:dict(error_m=distance(r['best']['coordinates'],[ref['latitude_deg'],ref['longitude_deg']]),held=r['best']['held'],train=r['best']['train'],success=r['best']['success'],bound_hit=r['bound_hit'],interpolation_error_hz=r['maximum_interpolation_error_hz'],elapsed_s=r['elapsed_s']) for arm,r in rows.items()}
summary['shift_m']=distance(rows['cfo_only']['best']['coordinates'],rows['phase']['best']['coordinates'])
(HERE/'refit/summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
old={arm:json.loads((HERE.parent/'2026_09_27_ds6_continuous_phase'/f'{arm}.json').read_text()) for arm in rows}
fig,ax=plt.subplots(figsize=(7,4),constrained_layout=True)
x=np.arange(2)
ax.bar(x-.17,[distance(old[a]['best']['coordinates'],[ref['latitude_deg'],ref['longitude_deg']]) for a in rows],.34,label='Old offset profiler')
ax.bar(x+.17,[summary[a]['error_m'] for a in rows],.34,label='Stationary offset solver')
ax.axhline(1000,color='black',ls='--',label='1 km');ax.set(xticks=x,xticklabels=['CFO only','CFO + phase'],ylabel='Distance to operator reference (m)',title='Matched three-scan refit: no sub-km recovery');ax.legend(fontsize=8)
fig.savefig(HERE/'refit/location.png',dpi=160)
