"""Reference scoring after frozen training selection, with coverage bounds."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run import HERE,ROOT,joint
fits={a:json.loads((HERE/f'{a}.json').read_text()) for a in ['cfo_only','phase']}
assert all(r['complete'] and r['best']==max(r['runs'],key=lambda x:x['train']) for r in fits.values())
reference=json.loads((ROOT/'2026_09_27_ds6_roof/pose-authority.json').read_text())
def distance(a,b):
    la,lo=np.radians(a);x,y=np.radians(b)
    return float(2*6371008.8*np.arcsin(np.sqrt(np.sin((la-x)/2)**2+np.cos(la)*np.cos(x)*np.sin((lo-y)/2)**2)))
inputs=json.loads((ROOT/'2026_09_27_ds6_expanded_association/inputs.json').read_text())
summary={}
for arm,r in fits.items():
    audit=json.loads((HERE/f'{arm}-coverage.json').read_text());assert audit['complete'] and audit['fit_sha256']==joint.sha(HERE/f'{arm}.json')
    losses={(v['session_id'],v['track_id']):v['log_evidence_loss'] for v in audit['rows']};upper=sum(losses.values())
    for s in inputs['scans']:
        for g in s['groups']:
            loss=sum(losses[(s['session_id'],tid)] for tid in g['track_ids']);maximum=.81*max(g['correlation'])+.19
            upper+=float(np.log1p(np.expm1(loss)*maximum/.19))-loss
    summary[arm]=dict(error_m=distance(r['best']['coordinates'],[reference['latitude_deg'],reference['longitude_deg']]),coordinates=r['best']['coordinates'],x=r['best']['x'],held=r['best']['held'],exact_held=r['exact']['held'],converged=r['best']['success'],bound_hit=r['bound_hit'],minimum_candidate_mass=audit['minimum_mass'],cfo_evidence_loss=audit['cfo_log_evidence_loss'],phase_evidence_loss_upper=upper,maximum_interpolation_error_hz=r['maximum_interpolation_error_hz'])
summary['phase_shift_m']=distance(fits['cfo_only']['best']['coordinates'],fits['phase']['best']['coordinates'])
summary['held_gain']=summary['phase']['held']-summary['cfo_only']['held']
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
fig,axes=plt.subplots(1,2,figsize=(10,4),constrained_layout=True)
for arm,color in [('cfo_only','tab:blue'),('phase','tab:orange')]:
    r=fits[arm];axes[0].scatter([v['x'][0] for v in r['runs']],[v['x'][1] for v in r['runs']],label=arm,color=color,s=100,marker='x' if arm=='phase' else 'o')
    coverage=json.loads((HERE/f'{arm}-coverage.json').read_text());loss=np.sort([v['log_evidence_loss'] for v in coverage['rows']])[::-1];axes[1].plot(np.arange(1,len(loss)+1),loss,label=arm,color=color)
center=json.loads((ROOT/'2026_09_27_ds6_joint_phase/protocol.json').read_text())['grid']['center_from_cfo'];rx=np.radians(reference['longitude_deg']-center[1])*6371.0088*np.cos(np.radians(center[0]));ry=np.radians(reference['latitude_deg']-center[0])*6371.0088
axes[0].scatter(rx,ry,marker='*',s=130,color='black',label='Operator reference');axes[0].set(xlabel='East of CFO center (km)',ylabel='North (km)',title='Two starts reach different local optima');axes[0].legend(fontsize=8)
axes[1].set(xlabel='Track rank',ylabel='Omitted training log evidence',title='Full-catalogue proposal audit');axes[1].legend();fig.savefig(HERE/'continuous.png',dpi=160)
print(json.dumps(summary,indent=2))
