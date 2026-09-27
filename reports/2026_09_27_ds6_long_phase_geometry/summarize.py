import importlib.util
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('mechanism',HERE/'run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
r=json.loads((HERE/'results.json').read_text());assert r['complete'];obs=r['observations'];times=np.array([o['time_s'] for o in obs]);times-=times[0];prob=[o['probability'] for o in obs];train=np.array([o['partition']=='train' for o in obs]);audit=[]
for limit in [.02,.2]:
    shifts=2*np.pi*np.linspace(-limit,limit,3201)[:,None]*times;weights=np.ones(3201);weights[[0,-1]]=.5;weights/=weights.sum();refined=m.evidence(prob,shifts,train,weights);name=f'linear_drift_{limit:g}Hz';audit.append(dict(model=name,held_change=refined['held']-r['models'][name]['held'],train_change=refined['train']-r['models'][name]['train']))
summary=dict(models={k:dict(train=v['train'],held=v['held']) for k,v in r['models'].items()},geometry_vs_constant_held=r['models']['geometry_42_baselines']['held']-r['models']['constant_response']['held'],geometry_vs_slow_drift_held=r['models']['geometry_42_baselines']['held']-r['models']['linear_drift_0.02Hz']['held'],quadrature_audit=audit)
geometry=np.array(r['geometry_shifts_rad']);ends=np.flatnonzero(train);fraction=(times-times[ends[0]])/(times[ends[1]]-times[ends[0]]);line=geometry[:,ends[0],None]+(geometry[:,ends[1]]-geometry[:,ends[0]])[:,None]*fraction[None,:];departure=geometry[:,~train]-line[:,~train];weights=np.array(r['models']['geometry_42_baselines']['hypothesis_posterior'])
summary['training_weighted_geometry_departure_from_endpoint_line_rms_deg']=float(np.degrees(np.sqrt(np.sum(weights*np.mean(departure**2,axis=1)))))
summary['held_visit_conditional_circular_std_deg']=[float(np.degrees(np.sqrt(-2*np.log(o['R'])))) for o in obs if o['partition']=='held']
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
fig,axes=plt.subplots(1,2,figsize=(12,4),constrained_layout=True)
for part,marker in [('train','o'),('held','x')]:
    idx=[i for i,o in enumerate(obs) if o['partition']==part];axes[0].scatter(times[idx],[obs[i]['mean_phase_deg'] for i in idx],marker=marker,color='black',label=part,zorder=5)
for name,label in [('constant_response','Constant response'),('geometry_42_baselines','Geometry mixture'),('linear_drift_0.02Hz','Slow linear drift')]:axes[0].plot(times,r['predictions'][name]['mean_deg'],'--',label=label)
axes[0].set(xlabel='Time from first visit (s)',ylabel='Pilot source-pair double difference (degrees)',title='Training-conditioned mean predictions');axes[0].legend(fontsize=7)
names=list(r['models']);labels=['Constant','Geometry','Slow drift','Broad drift'];axes[1].bar(range(4),[r['models'][n]['held'] for n in names]);axes[1].set(xticks=range(4),xticklabels=labels,ylabel='Joint held phase log predictive score',title='Geometry and slow drift predict equally well')
fig.suptitle('18-second real-data mechanism check; fixed CFO site, no reference fit');fig.savefig(HERE/'mechanism.png',dpi=160);print(json.dumps(summary,indent=2))
