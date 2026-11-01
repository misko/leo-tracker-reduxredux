"""Render the isolated predictive family at matched RF-best endpoints."""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.special import logsumexp
import ablate as a


def main():
    (a.OUT/'plots').mkdir(exist_ok=True)
    d,hd,z,_,_=a.contexts();rows=[]
    for cell in ('original','predictive','complete'):
        dd=a.mixed(d,hd,z,a.CELLS[cell])
        best=a.e.paired(a.e.read(a.OUT/'fits'/f'{cell}.json'))
        for arm,r in best.items():
            p,_=a.e.build(dd,z,arm,np.asarray(r['reference']))
            score,details=a.e.position.family_score(dd['families'],dd,p,np.asarray(r['x']),details=True)
            f=dd['families'][0]
            rows.append(dict(cell=cell,arm=arm,RF_endpoint_km=r['x'],score=score,details=details,
                phase_prior_density=np.exp(f.logprior-logsumexp(f.logprior))/(f.phases[1]-f.phases[0])))
    a.e.write(a.OUT/'family_diagnostic.json',rows)
    fig,axes=plt.subplots(3,2,figsize=(12,11),gridspec_kw=dict(height_ratios=[1,1,1.4]))
    colors=dict(original='#2d7595',predictive='#c47935',complete='#658048')
    for col,arm in enumerate(('c0','fitted_c')):
        for row in rows:
            if row['arm']!=arm:continue
            detail=row['details'][0];phase=np.array(detail['phase_grid_s']);w=np.array(detail['phase_weights'])
            axes[0,col].plot(phase,row['phase_prior_density'],color=colors[row['cell']],label=row['cell'])
            axes[1,col].plot(phase,w/(phase[1]-phase[0]),color=colors[row['cell']],label=row['cell'])
            for k,tr in enumerate(detail['diagnostics']):
                t=np.array(tr['times_s']);res=np.array(tr['raw_residual_hz'])
                axes[2,col].plot(t,res,'.-',markersize=3,lw=.8,color=colors[row['cell']],label=row['cell'] if k==0 else None)
        axes[0,col].set_title(arm+' — NORAD 64938');axes[0,col].set_xlabel('Family phase (s)')
        axes[0,col].set_ylabel('Prior phase density (1/s)');axes[0,col].set_xlim(-30,30)
        axes[1,col].set_xlabel('Family phase (s)');axes[1,col].set_ylabel('Posterior phase density (1/s)')
        center=np.mean([r['details'][0]['phase_mean_s'] for r in rows if r['arm']==arm])
        axes[1,col].set_xlim(center-.3,center+.3)
        axes[2,col].set_xlabel('Scan time (s)');axes[2,col].set_ylabel('Raw native CFO residual (Hz)')
        axes[2,col].axhline(0,color='black',lw=.6)
        for ax in axes[:,col]:ax.legend();ax.grid(alpha=.2)
    fig.suptitle('Standalone predictive family before and after causal prior completion\nRF-best matched starts; native evidence and shared receiver uncertainty retained')
    fig.tight_layout();fig.savefig(a.OUT/'plots/family_phase_residuals.png',dpi=170);plt.close(fig)


if __name__=='__main__':main()
