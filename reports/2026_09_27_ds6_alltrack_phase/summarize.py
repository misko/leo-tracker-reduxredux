"""Score frozen searches against the operator coordinate after selection."""
import json,hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parent
authority=json.loads((root.parent/'2026_09_27_ds6_roof/pose-authority.json').read_text());reference=np.radians([authority['latitude_deg'],authority['longitude_deg']])
def distance(row):
    a,b=np.radians([row['latitude'],row['longitude']]);c,d=reference
    return float(6371008.8*2*np.arcsin(np.sqrt(np.sin((a-c)/2)**2+np.cos(a)*np.cos(c)*np.sin((b-d)/2)**2)))
stages=[]
for stage,name in enumerate(['results.json','refine-1.json','refine-2.json','refine-3.json']):
    d=json.loads((root/name).read_text());assert d['complete']
    stages.append(dict(stage=stage,nodes=len(d['rows']),cfo={**d['best_cfo'],'error_m':distance(d['best_cfo'])},joint={**d['best_joint'],'error_m':distance(d['best_joint'])},source_sha256=hashlib.sha256((root/name).read_bytes()).hexdigest()))
summary=dict(status='development_scan_only_not_dataset_accuracy',reference_used_only_for_post_selection_scoring=True,stages=stages,inputs_sha256=hashlib.sha256((root/'inputs.json').read_bytes()).hexdigest())
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
fig,axes=plt.subplots(1,2,figsize=(12,4.7))
for ax,name,title in zip(axes,['results.json','refine-3.json'],['Coarse regional search','Final local refinement']):
    d=json.loads((root/name).read_text());x=np.array([r['longitude'] for r in d['rows']]);y=np.array([r['latitude'] for r in d['rows']]);z=np.array([r['joint_train'] for r in d['rows']]);z-=z.max()
    im=ax.scatter(x,y,c=z,s=65,marker='s');fig.colorbar(im,ax=ax,label='Relative joint training log score')
    ax.scatter([authority['longitude_deg']],[authority['latitude_deg']],marker='*',color='white',edgecolor='black',s=120,label='Operator coordinate (scoring only)')
    b=d['best_joint'];ax.scatter([b['longitude']],[b['latitude']],marker='x',color='red',s=90,label='Selected CFO and phase point')
    ax.set(title=title,xlabel='Longitude',ylabel='Latitude');ax.legend(fontsize=7)
fig.tight_layout();fig.savefig(root/'alltrack-location.png',dpi=160)
for s in stages:print(s['stage'],s['cfo']['latitude'],s['cfo']['longitude'],s['cfo']['error_m'],s['joint']['error_m'])
