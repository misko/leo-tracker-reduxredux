"""Render completed, audited engineering and random-cohort results only."""

import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent


def main():
    engineering=json.loads((HERE/'position/evaluation.json').read_text())
    cohort=json.loads((HERE/'random20/position/evaluation.json').read_text())
    for folder in [HERE/'position',HERE/'random20/position']:
        assert json.loads((folder/'independent_numerical_audit.json').read_text())['all_passed']
    fig,axes=plt.subplots(2,2,figsize=(13,9),layout='constrained')
    cases=['DS23-0268','DS23-0405','DS23-0240'];x=np.arange(3)
    rows=[next(r for r in engineering['rows'] if (r['case'],r['arm'],r['policy'])==(c,'fitted_c','equal_assignment_priors')) for c in cases]
    axes[0,0].bar(x-.18,[r['original_error_km'] for r in rows],.36,color='.45',label='Signed-prior incumbent')
    axes[0,0].bar(x+.18,[r['policy_error_km'] for r in rows],.36,color='#168b91',label='Family-excluded replacement + fallback')
    axes[0,0].set_xticks(x,['268','405','240']);axes[0,0].set(xlabel='DS23 engineering scan',ylabel='Position error (km)',title='One strong repair; one unchanged; one worse')
    axes[0,0].legend(fontsize=8)
    ax=axes[0,1];stats=cohort['statistics'];base=stats['equal_assignment_priors']['fitted_c']
    methods=['Incumbent','Equal priors','Incumbent preference'];means=[base['original_mean_km']]+[stats[k]['fitted_c']['policy_mean_km'] for k in ['equal_assignment_priors','incumbent_sticky_prior']]
    medians=[base['original_median_km']]+[stats[k]['fitted_c']['policy_median_km'] for k in ['equal_assignment_priors','incumbent_sticky_prior']]
    ax.bar(x-.18,means,.36,color='#3d648e',label='Mean');ax.bar(x+.18,medians,.36,color='#c17c42',label='Median')
    ax.set_xticks(x,methods,fontsize=8);ax.set(ylabel='Position error (km)',title='Frozen random20 cohort · fitted c')
    ax.axhline(.5,c='seagreen',ls='--',lw=1,label='Goal');ax.legend(fontsize=8)
    ax.set_ylim(0,1.45)
    ax.text(.02,.97,'Only 3 / 1 changes accepted; uncertainty includes no gain',transform=ax.transAxes,va='top',fontsize=8)
    ax=axes[1,0];ax.bar([0,1],[35.003,18.779],color='#8765b4')
    ax.set_xticks([0,1],['268','405']);ax.set(xlabel='DS23 scan',ylabel='Reference minus endpoint normalized loss',title='The conditional objective prefers the wrong location')
    ax.set_ylim(0,44)
    ax.text(.02,.97,'After nuisance and phase refresh; fixed labels / aliases\nRMS differences are only +2.189 Hz and +0.216 Hz',transform=ax.transAxes,va='top',fontsize=9)
    ax=axes[1,1];ax.bar([-.18,.82],[5.318602601,4.544332356],.36,color='.45',label='Original ALGO02')
    ax.bar([.18,1.18],[3.880,3.809],.36,color='#c17c42',label='Lowest-error passing family deletion')
    ax.set_xticks([0,1],['268','405']);ax.set(xlabel='DS23 scan',ylabel='Position error (km)',title='Single-family deletion does not explain all the bias')
    ax.set_ylim(0,6.5)
    ax.text(.02,.97,'Retrospective influence diagnostic, not an adoption rule\nDeletion masks differ; raw likelihoods are not ranked',transform=ax.transAxes,va='top',fontsize=8);ax.legend(fontsize=8,loc='lower right')
    for ax in axes.flat:ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    fig.suptitle('DS23: association, model preference and weak position information\nCompleted engineering and pilot diagnostics · evaluation GPS is report-only',fontsize=14)
    fig.savefig(HERE/'two_scan_interpretation.png',dpi=170);plt.close(fig)


if __name__=='__main__':main()
