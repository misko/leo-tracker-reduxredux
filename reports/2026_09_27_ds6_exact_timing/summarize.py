"""Post-selection scoring and plots; never consumed by the search."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parent
pose=json.loads((root.parent/'2026_09_27_ds6_roof/pose-authority.json').read_text())
def error(row):
    a,b,c,d=np.radians([row['latitude'],row['longitude'],pose['latitude_deg'],pose['longitude_deg']])
    return float(6371008.8*2*np.arcsin(np.sqrt(np.sin((a-c)/2)**2+np.cos(a)*np.cos(c)*np.sin((b-d)/2)**2)))
rows=[];results={}
for name,folder in [('gaussian',root),('student_t4',root/'robust'),('student_t4_extended',root/'robust-extended')]:
    d=json.loads((folder/'results.json').read_text());assert d['complete'];results[name]=d
    protocol=json.loads((folder/'protocol.json').read_text());lat=[x[0] for x in protocol['coordinates']];lon=[x[1] for x in protocol['coordinates']]
    for timing in ['integer','quarter']:
        for arm in ['cfo','joint']:
            r=d['best'][timing][arm];rows.append(dict(model=name,timing=timing,score_arm=arm,**r,error_m=error(r),grid_boundary=r['latitude'] in [min(lat),max(lat)] or r['longitude'] in [min(lon),max(lon)]))
diagnostics=json.loads((root/'track-diagnostics.json').read_text())
summary=dict(status='sub_km_not_established',coordinate_only_used_after_selection=True,results=rows,gaussian_residual_audit=dict(tracks=len(diagnostics),median_training_rms_hz=float(np.median([r['train_rms_hz'] for r in diagnostics])),median_held_rms_hz=float(np.median([r['held_rms_hz'] for r in diagnostics])),training_over_300_hz=sum(r['train_rms_hz']>300 for r in diagnostics),maximum_training_rms_hz=max(r['train_rms_hz'] for r in diagnostics)))
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
fig,axes=plt.subplots(1,3,figsize=(16,4.8))
for ax,(name,d) in zip(axes,results.items()):
    r=[v for v in d['rows'] if v['arm']=='quarter'];x=np.array([v['longitude'] for v in r]);y=np.array([v['latitude'] for v in r]);z=np.array([v['joint_train'] for v in r]);z-=z.max()
    im=ax.scatter(x,y,c=z,marker='s',s=70);fig.colorbar(im,ax=ax,label='Relative joint training score')
    b=d['best']['quarter']['joint'];ax.scatter([b['longitude']],[b['latitude']],marker='x',color='red',s=100,label='Joint selected')
    ax.scatter([pose['longitude_deg']],[pose['latitude_deg']],marker='*',s=150,color='white',edgecolor='black',label='Reference: scoring only')
    ax.set(title=name+' / exact, 0.25 s timing',xlabel='Longitude',ylabel='Latitude');ax.legend(fontsize=8)
fig.tight_layout();fig.savefig(root/'exact-timing-comparison.png',dpi=160)
print(json.dumps(summary,indent=2))
