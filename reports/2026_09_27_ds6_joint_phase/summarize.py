"""Training-only location selection followed by operator-reference scoring."""
import json
import argparse
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
parser=argparse.ArgumentParser();parser.add_argument('--quarter',action='store_true');args=parser.parse_args()
if args.quarter:HERE=HERE/'quarter'
r=json.loads((HERE/'results.json').read_text());assert r['complete'];rows=r['points']
winners={arm:max(rows,key=lambda r:r['scores'][arm]['train']) for arm in ['cfo_only','phase']}
reference=json.loads((ROOT/'2026_09_27_ds6_roof/pose-authority.json').read_text())
def distance(r):
    la,lo=np.radians([r['latitude_deg'],r['longitude_deg']]);a,b=np.radians([reference['latitude_deg'],reference['longitude_deg']])
    return float(2*6371.0088*np.arcsin(np.sqrt(np.sin((la-a)/2)**2+np.cos(la)*np.cos(a)*np.sin((lo-b)/2)**2)))
summary={arm:dict(point=r['point'],reference_distance_km=distance(r),boundary=max(abs(r['point'][k]) for k in ['east_km','north_km'])==2,**r['scores'][arm]) for arm,r in winners.items()}
summary['held_gain_at_own_winners']=summary['phase']['held']-summary['cfo_only']['held']
summary['phase_increment_range']=float(np.ptp([r['scores']['phase']['train']-r['scores']['cfo_only']['train'] for r in rows]))
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
fig,axes=plt.subplots(1,2,figsize=(10,4),constrained_layout=True)
for ax,arm in zip(axes,['cfo_only','phase']):
    values=np.array([r['scores'][arm]['train'] for r in rows]);values-=values.max()
    sc=ax.scatter([r['point']['east_km'] for r in rows],[r['point']['north_km'] for r in rows],c=values,cmap='viridis',s=500)
    for r,v in zip(rows,values):ax.annotate(f'{v:.2f}',(r['point']['east_km'],r['point']['north_km']),ha='center',va='center',fontsize=8,color='black',bbox=dict(facecolor='white',alpha=.85,edgecolor='none',pad=1))
    w=winners[arm]['point'];ax.scatter(w['east_km'],w['north_km'],s=680,facecolors='none',edgecolors='red',linewidths=2)
    ax.set(title='CFO only' if arm=='cfo_only' else 'CFO + phase',xlabel='East of CFO center (km)',ylabel='North (km)',xlim=(-2.7,2.7),ylim=(-2.7,2.7));fig.colorbar(sc,ax=ax,label='Training log score below maximum')
fig.suptitle('All-track frequency evidence with candidate-pair phase factors')
fig.savefig(HERE/'joint.png',dpi=160)
print(json.dumps(summary,indent=2))
