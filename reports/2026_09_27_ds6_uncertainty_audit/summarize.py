"""Recompute uncertainty quadrature and illustrate held prediction results."""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from run import score_banks


def main():
    result=json.loads((HERE/'results.json').read_text());protocol=json.loads((HERE/'protocol.json').read_text())
    times=np.array(protocol['fine_timing_s']);kap=np.array(protocol['kappa_grid']);out=[]
    fig,axes=plt.subplots(2,3,figsize=(15,9),layout='constrained')
    for row,s in enumerate(result['scans']):
        banks={arm:[{k:np.array(v) for k,v in b.items()} for b in bb] for arm,bb in json.loads((HERE/(s['session_id']+'-banks.json')).read_text()).items()}
        item=dict(session_id=s['session_id'],scales_hz=[t['learned_student_t_scale_hz'] for t in s['track_audits']],arms={},quadrature={})
        for arm in ['fixed','learned']:
            fixed=s['arms'][arm]['fixed_kappa']['geometry'];learned=s['arms'][arm]['learned_kappa']['geometry'];null=s['arms'][arm]['learned_kappa']['response_only']
            item['arms'][arm]=dict(cfo_only_held_score=fixed['cfo_only_held_log_predictive'],
                fixed_kappa_phase_score=fixed['held_phase_log_predictive'],learned_kappa_phase_score=learned['held_phase_log_predictive'],
                learned_kappa_null_phase_score=null['held_phase_log_predictive'],
                geometry_minus_null=learned['held_phase_log_predictive']-null['held_phase_log_predictive'],
                phase_gain_in_held_cfo=learned['held_cfo_log_predictive']-learned['cfo_only_held_log_predictive'])
            kappa=np.geomspace(.1,1e4,257);w=np.ones(257);w[[0,-1]]=.5;w/=w.sum()
            check=score_banks(banks[arm],kappa,w)
            item['quadrature'][arm]={key:check[key]-learned[key] for key in ['training_log_evidence','held_phase_log_predictive','held_cfo_log_predictive']}
            axes[row,1].plot(times,fixed['cfo_only_time_posterior'],marker='.',label=arm+' CFO scale')
        worst=max(s['track_audits'],key=lambda t:t['old_train_rms_hz'])
        mask=np.array(worst['training_mask']);t=np.array(worst['times_s']);residual=np.array(worst['old_residual_hz'])
        axes[row,0].scatter(t[mask],residual[mask],s=20,label='Training')
        axes[row,0].scatter(t[~mask],residual[~mask],s=25,marker='x',label='Held')
        axes[row,0].axhspan(-100,100,alpha=.15,color='tab:red',label='Original ±100 Hz scale')
        for sign in [-1,1]:axes[row,0].axhline(sign*worst['learned_student_t_scale_hz'],ls='--',color='0.4')
        axes[row,0].set(title=f"{s['session_id'][-8:]}: largest original training RMS track",xlabel='Seconds since capture start',ylabel='CFO residual after frozen training offset (Hz)')
        axes[row,0].legend(fontsize=8)
        axes[row,1].set(title='Quarter-second timing weights',xlabel='Scan time offset (seconds)',ylabel='Conditional probability')
        axes[row,1].legend(fontsize=8)
        for index,(geo,null) in enumerate(zip(s['arms']['learned']['learned_kappa']['geometry']['kappa_posteriors'],s['arms']['learned']['learned_kappa']['response_only']['kappa_posteriors'])):
            axes[row,2].semilogx(kap,geo,label=f'Pair {index+1}, geometry')
            axes[row,2].semilogx(kap,null,ls='--',label=f'Pair {index+1}, constant response')
        axes[row,2].set(title='Training-only phase concentration',xlabel='Von Mises kappa (larger = narrower)',ylabel='Mass per log-spaced grid point')
        axes[row,2].legend(fontsize=8)
        item['cfo_scale_held_gain']=item['arms']['learned']['cfo_only_held_score']-item['arms']['fixed']['cfo_only_held_score']
        out.append(item)
    fig.suptitle('DS6 uncertainty audit: one CFO track needs far more than 100 Hz noise allowance\nLearned phase precision improves prediction, but does not validate the geometric model')
    fig.savefig(HERE/'uncertainty-audit.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10,4),layout='constrained')
    x=np.arange(len(out))
    axes[0].bar(x,[o['cfo_scale_held_gain'] for o in out],color='tab:blue')
    axes[0].set(xticks=x,xticklabels=[o['session_id'][-8:] for o in out],ylabel='Held CFO log score gain',title='Learned CFO scale versus fixed 100 Hz')
    for dx,field,label in [(-.25,'fixed_kappa_phase_score','Geometry, kappa = 1'),(0,'learned_kappa_phase_score','Geometry, uncertain kappa'),(.25,'learned_kappa_null_phase_score','Constant response, uncertain kappa')]:
        axes[1].bar(x+dx,[o['arms']['learned'][field] for o in out],width=.25,label=label)
    axes[1].set(xticks=x,xticklabels=[o['session_id'][-8:] for o in out],ylabel='Held phase log score relative to uniform',title='Phase models with learned CFO scale')
    axes[1].legend(fontsize=7)
    fig.savefig(HERE/'held-prediction.png',dpi=160);plt.close(fig)
    (HERE/'summary.json').write_text(json.dumps(dict(scans=out,scope='Conditional predictive scores; not geographic accuracy'),indent=2)+'\n')
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()
