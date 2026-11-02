"""Scientific metadata figures; no inference or parameter selection."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parent


def main():
    inventory=json.loads((ROOT/'derived_inventory.json').read_text())
    density=json.loads((ROOT/'causal_density_diagnostic.json').read_text())
    rows=inventory['rows'];cohorts=['DS24','DS26','DS27','DS28','FRSH']
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,3,figsize=(15,4.7),layout='constrained')
    categories=[('Primary ready',lambda r:r['status']=='ready' and r['pair_count']>=3,'#2878b5'),
        ('Exploratory-only ready',lambda r:r['status']=='ready' and r['pair_count']==2,'#36a088'),
        ('Projection/alignment fallback',lambda r:r['status'] in ['projection_fallback','invalid'],'#c96464'),
        ('Fewer than two pairs',lambda r:r['status']=='insufficient_history','#f2ba54'),
        ('No prior nomination',lambda r:r['status']=='no_prior_target','#cccccc')]
    bottom=np.zeros(len(cohorts))
    for name,select,color in categories:
        counts=np.array([sum(select(r) and r['dataset']==d for r in rows) for d in cohorts])
        axes[0].bar(cohorts,counts,bottom=bottom,color=color,label=name)
        bottom+=counts
    axes[0].set(title='All 205 scans retain explicit decisions',ylabel='Scans')
    axes[0].legend(frameon=False,fontsize=7)
    for r in rows:
        for pair in r.get('selected_pairs',[]):
            axes[1].scatter(r['nominal_horizon_hours'],pair['horizon_hours'],s=18,
                color='#2878b5' if r.get('pair_count',0)>=3 else '#36a088',alpha=.55)
    h=np.linspace(0,60,201);tolerance=np.maximum(2,.25*h)
    axes[1].plot(h,h,color='black',lw=1)
    axes[1].fill_between(h,h-tolerance,h+tolerance,color='black',alpha=.06)
    axes[1].set(title='Matching precedes coefficient estimation',xlabel='Current nominal propagation age (h)',
        ylabel='Historical older→newer forecast horizon (h)',xlim=(0,60),ylim=(0,75))
    complete=[r for r in density['rows'] if r['status']=='complete']
    gains=np.array([r['age2_gain_over_oldB'] for r in complete])
    poor=np.array([r['held_represented_energy_fraction']<.5 for r in complete])
    axes[2].axhline(0,color='black',lw=.8)
    axes[2].scatter(np.flatnonzero(~poor)+1,gains[~poor],color='#2878b5',s=28,label='Held energy ≥50% represented')
    axes[2].scatter(np.flatnonzero(poor)+1,gains[poor],color='#c96464',marker='^',s=38,label='Held energy <50% represented')
    axes[2].set(title='25 dependent descriptive forecasts',xlabel='Forecast in fixed ledger order',
        ylabel='OldB − Age2 normalized coefficient score')
    axes[2].text(.03,.04,f'Age2 wins {sum(gains>0)}/25; summed gain {gains.sum():.2f}\nOne shared-snapshot group; no independent validation',
        transform=axes[2].transAxes,fontsize=8,bbox=dict(facecolor='white',edgecolor='none',alpha=.9))
    axes[2].legend(frameon=False,fontsize=7,loc='upper right')
    for ax in axes:ax.grid(alpha=.14);ax.set_axisbelow(True)
    fig.suptitle('Age-matched revision covariance: sparse support and limited archive evidence',fontsize=13)
    fig.supxlabel('Orbit-only metadata and conditional three-coordinate densities; no RF fitting, GPS selection or calibrated orbit-error claim.',fontsize=9)
    for ext in ['png','pdf']:fig.savefig(ROOT/('orbit_covariance_inventory.'+ext),dpi=180)
    plt.close(fig)


if __name__=='__main__':main()
