"""Plot saved DS26-0265 results without fitting or changing decisions."""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parent


def read(path):return json.loads(path.read_text())


def main():
    source=ROOT/'shared-run01'; summary=read(source/'reporting_summary.json')
    seal=read(source/'inference_seal.json')
    assert summary['all_masks_match'] and not summary['recovery_claim']
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in seal['artifacts_sha256'].items())
    fig,axes=plt.subplots(2,2,figsize=(13.2,9),layout='constrained')
    colors={'c0':'#2166ac','fitted_c':'#d97706'}
    labels={'c0':'c = 0','fitted_c':'fitted c'}
    plt.rcParams.update({'font.size':10})
    ax=axes[0,0]
    groups=sorted({r['seed'] for r in summary['annotation']},key=lambda k:[20261029,94721,4081].index(k))
    x=np.arange(len(groups));width=.18
    for i,(arm,limit) in enumerate((('c0',15),('fitted_c',15),('c0',30),('fitted_c',30))):
        values=[next(r for r in summary['annotation'] if r['arm']==arm and r['reference_limit_s']==limit and r['seed']==seed)['final_phase_change_s'] for seed in groups]
        ax.bar(x+(i-1.5)*width,values,width,color=colors[arm],alpha=1 if limit==30 else .35,
            hatch=None if limit==30 else '//',label=f'{labels[arm]}, {limit} s reference')
    ax.axhline(.01,color='#a71930',ls='--',lw=1.3,label='convergence gate: 0.01 s')
    ax.set(yscale='log',ylim=(1e-7,10),xticks=x,xticklabels=[f'Fold {i+1}\nseed {v}' for i,v in enumerate(groups)],
        ylabel='Maximum posterior-to-reference movement (s)',title='A  Broader numerical reference resolves clipping')
    ax.legend(fontsize=8,loc='upper right',ncols=2,frameon=False)
    ax.grid(axis='y',alpha=.17)
    target=read(source/'reference30/inclusion/target_0.json')
    ax=axes[0,1]
    for arm in colors:
        r=target['arms'][arm]['target_diagnostics'][0]
        ax.plot(r['times_s'],r['residual_hz'],'.-',ms=3,lw=1,color=colors[arm],
            label=f"{labels[arm]}: RMS {r['RMS_hz']:.1f} Hz")
    ax.axhline(0,color='#777777',lw=.7)
    ax.axhspan(450,490,color='#a71930',alpha=.12)
    ax.axhspan(-490,-450,color='#a71930',alpha=.12)
    ax.axhline(450,color='#a71930',ls='--',lw=.8)
    ax.axhline(-450,color='#a71930',ls='--',lw=.8)
    ax.text(.02,.03,'Dashed: ±450 Hz RMS scale (not a pointwise gate)',transform=ax.transAxes,fontsize=8,color='#555555')
    ax.set(xlabel='Scan time (s)',ylabel='Profiled target residual (Hz)',ylim=(-550,550),
        title='B  Target 66102: small RMS, structured residual')
    ax.legend(frameon=True,facecolor='white',edgecolor='none',framealpha=1,fontsize=9,loc='upper left')
    audit=read(source/'reference30/inclusion/exact_owner_replay.json')
    prefix=target['arms']['c0']['target_diagnostics'][0]['component']+'/linear/'
    ax=axes[1,0];x=np.arange(3);width=.3;stats={}
    for sign,arm in ((-1,'c0'),(1,'fitted_c')):
        row=next(r for r in audit['rows'] if r['role']=='target_0' and r['arm']==arm)
        exact=next(r for r in row['exact_family_replays'] if r['norad']==66102)
        values=[1-exact['all_gate_slacks'][prefix+k] for k in ('rms','quadratic','step')]
        stats[arm]=dict(RMS_hz=values[0]*450,quadratic_BIC_gain=values[1]*10,maximum_step_z=values[2]*4)
        bars=ax.bar(x+sign*width/2,values,width,color=colors[arm],label=labels[arm])
        for b,value in zip(bars,values,strict=True):ax.text(b.get_x()+b.get_width()/2,b.get_height()+.03,f'{value:.2f}',ha='center',fontsize=9)
    ax.axhline(1,color='#a71930',ls='--',lw=1.3)
    ax.text(-.25,1.02,'failure above 1',ha='left',color='#a71930',fontsize=9)
    ax.set(xticks=x,xticklabels=['RMS / 450 Hz','Quadratic BIC gain / 10','Maximum step z / 4'],
        ylabel='Statistic / unchanged threshold',ylim=(0,1.9),
        title='C  Both c arms fail quadratic and step gates')
    ax.legend(frameon=False,fontsize=9,loc='upper left');ax.grid(axis='y',alpha=.17)
    ax=axes[1,1];x=np.arange(4)
    for sign,arm in ((-1,'c0'),(1,'fitted_c')):
        values=[1000*next(r for r in summary['inclusion'] if r['reference_limit_s']==limit and r['role']==role and r['arm']==arm)['position_error_km']
            for limit,role in ((15,'control'),(15,'target_0'),(30,'control'),(30,'target_0'))]
        bars=ax.bar(x+sign*width/2,values,width,color=colors[arm],label=labels[arm])
        for b,value in zip(bars,values,strict=True):ax.text(b.get_x()+b.get_width()/2,b.get_height()+2,f'{value:.0f}',ha='center',fontsize=9)
    ax.axvline(1.5,color='#aaaaaa',lw=.8)
    ax.set(xticks=x,xticklabels=['Control\n15 s','Proposed addition\n15 s','Control\n30 s','Proposed addition\n30 s'],
        ylabel='Position error versus known site (m)',ylim=(0,205),
        title='D  Position evaluation after inference: no improvement')
    ax.legend(frameon=False,fontsize=9,loc='upper left');ax.grid(axis='y',alpha=.17)
    for ax in axes.ravel():ax.spines[['top','right']].set_visible(False)
    fig.suptitle('DS26-0265: phase convergence repaired; full inclusion still rejected',fontsize=16,weight='bold')
    fig.supxlabel('Matched saved random groups, candidates, priors and budgets • 120 points proposed; 0 newly accepted • GPS used only for panel D',fontsize=10)
    dest=ROOT/'figures';dest.mkdir(exist_ok=True)
    for suffix in ('png','pdf'):fig.savefig(dest/f'DS26-0265-phase-reference.{suffix}',dpi=180,bbox_inches='tight')
    (dest/'figure-data.json').write_text(json.dumps(dict(exact_target_statistics=stats,source_summary_sha256=hashlib.sha256((source/'reporting_summary.json').read_bytes()).hexdigest()),indent=2)+'\n')


if __name__=='__main__':main()
