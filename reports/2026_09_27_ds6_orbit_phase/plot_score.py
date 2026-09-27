"""Post-selection coordinate scoring only; search never loads pose coordinates."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--first-visit',type=int,default=1568);args=parser.parse_args()
base=Path(__file__).resolve().parent;root=base if args.first_visit==1568 else base/f'pair-{args.first_visit}';d=json.loads((root/'results.json').read_text())
authority=json.loads((base.parent/'2026_09_27_ds6_roof/pose-authority.json').read_text());truth=[authority['latitude_deg'],authority['longitude_deg']]
def distance(lat,lon):
    a,b=np.radians([lat,lon]);c,e=np.radians(truth);h=np.sin((a-c)/2)**2+np.cos(a)*np.cos(c)*np.sin((b-e)/2)**2
    return float(6371008.8*2*np.arcsin(np.sqrt(h)))
scored={arm:dict(latitude=d[arm]['latitude'],longitude=d[arm]['longitude'],error_to_operator_coordinate_m=distance(d[arm]['latitude'],d[arm]['longitude'])) for arm in ['best_cfo','best_joint']}
delta=np.array([r['joint_train']-r['cfo_train'] for r in d['rows']]);scored['phase_training_log_factor_range']=[float(delta.min()),float(delta.max())];scored['phase_training_log_factor_contrast']=float(np.ptp(delta));scored['coordinate_used_only_after_search']=True
(root/'coordinate-score.json').write_text(json.dumps(scored,indent=2)+'\n')
fig,axes=plt.subplots(1,2,figsize=(12,4.8));xs=sorted({r['longitude'] for r in d['rows']});ys=sorted({r['latitude'] for r in d['rows']})
for ax,key,title in [(axes[0],'cfo_train','CFO training score (relative)'),(axes[1],'factor','Added phase training log factor')]:
    values=np.array([r[key] if key!='factor' else r['joint_train']-r['cfo_train'] for r in d['rows']]).reshape(len(ys),len(xs))
    if key!='factor':values-=values.max()
    im=ax.pcolormesh(xs,ys,values,shading='nearest');fig.colorbar(im,ax=ax)
    ax.scatter([truth[1]],[truth[0]],marker='*',s=120,color='white',edgecolor='black',label='Operator coordinate (scoring only)')
    ax.scatter([d['best_joint']['longitude']],[d['best_joint']['latitude']],marker='x',s=90,color='red',label='Both selected positions')
    ax.set(xlabel='Longitude',ylabel='Latitude',title=title);ax.legend(fontsize=7)
fig.tight_layout();fig.savefig(root/'location-phase-comparison.png',dpi=160)
print(json.dumps(scored,indent=2))
