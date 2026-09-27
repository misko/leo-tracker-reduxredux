"""Choose training winners before loading the operator reference for scoring."""
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
protocol = json.loads((HERE/'protocol.json').read_text())
rows = [json.loads((HERE/f"point-{p['index']}.json").read_text()) for p in protocol['points']]
assert len(rows) == 9 and all(r['complete'] for r in rows)
assert all(r['protocol_sha256'] == hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest() for r in rows)
winners = {arm:max(rows,key=lambda r:r['scores'][arm]['train']) for arm in ['cfo_only','phase']}
spec = importlib.util.spec_from_file_location('geographic',HERE/'run.py')
model = importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
leave_one_out = []
for excluded in [s['session_id'] for s in rows[0]['scans']]:
    scores = [model.combine([s for s in r['scans'] if s['session_id'] != excluded]) for r in rows]
    selected = {arm:int(np.argmax([s[arm]['train'] for s in scores])) for arm in ['cfo_only','phase']}
    leave_one_out.append(dict(excluded=excluded,selected=selected))
# Reference is only loaded after training selection above.
reference = json.loads((HERE.parent/'2026_09_27_ds6_roof/pose-authority.json').read_text())
def distance(r):
    lat,lon = np.radians([r['latitude_deg'],r['longitude_deg']])
    la,lo = np.radians([reference['latitude_deg'],reference['longitude_deg']])
    return float(2*6371.0088*np.arcsin(np.sqrt(np.sin((lat-la)/2)**2+np.cos(lat)*np.cos(la)*np.sin((lon-lo)/2)**2)))
out = {arm:dict(point=r['point'],latitude_deg=r['latitude_deg'],longitude_deg=r['longitude_deg'],
                 reference_distance_km=distance(r),boundary=abs(r['point']['east_km'])==2 or abs(r['point']['north_km'])==2,
                 **r['scores'][arm]) for arm,r in winners.items()}
out['phase_held_gain_at_own_winners'] = out['phase']['held']-out['cfo_only']['held']
out['leave_one_scan_out'] = [dict(excluded=item['excluded'],winners={arm:dict(point=rows[i]['point'],reference_distance_km=distance(rows[i])) for arm,i in item['selected'].items()}) for item in leave_one_out]
out['scope'] = 'Nine-point local screen; neither a continuous optimum nor an accuracy validation.'
(HERE/'summary.json').write_text(json.dumps(out,indent=2)+'\n')
fig,axes=plt.subplots(1,3,figsize=(13,4.5),constrained_layout=True)
lat0,lon0=protocol['center_from_cfo']
refx=np.radians(reference['longitude_deg']-lon0)*6371.0088*np.cos(np.radians(lat0))
refy=np.radians(reference['latitude_deg']-lat0)*6371.0088
for ax,arm,title in zip(axes[:2],['cfo_only','phase'],['CFO only','CFO + phase (shared baseline)']):
    values=np.array([r['scores'][arm]['train'] for r in rows]);values-=values.max()
    sc=ax.scatter([r['point']['east_km'] for r in rows],[r['point']['north_km'] for r in rows],c=values,s=420,cmap='viridis')
    for r,v in zip(rows,values):ax.annotate(f'{v:.2f}',(r['point']['east_km'],r['point']['north_km']),ha='center',va='center',color='black' if v>-.25 else 'white',fontsize=9)
    w=winners[arm]['point'];ax.scatter(w['east_km'],w['north_km'],s=600,facecolors='none',edgecolors='red',linewidths=2,label='Training winner')
    ax.scatter(refx,refy,marker='*',s=130,color='orange',edgecolors='black',label='Operator reference')
    ax.set(title=title,xlabel='East of CFO starting point (km)',ylabel='North (km)',xlim=(-2.7,2.7),ylim=(-2.7,2.7));ax.legend(fontsize=7,loc='upper center',bbox_to_anchor=(.5,-.2),ncol=2,markerscale=.45);fig.colorbar(sc,ax=ax,label='Training log score below maximum')
gain=np.array([r['scores']['phase']['train']-r['scores']['cfo_only']['train'] for r in rows])
axes[2].plot(range(9),gain-gain[4],'o-');axes[2].axhline(0,color='gray',lw=.8);axes[2].set(title='Geographic contribution of phase',xlabel='Grid index (rows south to north)',ylabel='Phase log-score increment relative to center');axes[2].grid(alpha=.2)
fig.suptitle('DS6: three scans, five source pairs; nine fixed locations')
fig.savefig(HERE/'geographic.png',dpi=160);plt.close(fig)
print(json.dumps(out,indent=2))
