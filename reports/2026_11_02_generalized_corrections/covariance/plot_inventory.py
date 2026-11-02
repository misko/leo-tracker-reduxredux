"""Scientific figures from sealed orbit-only metadata; no model fitting."""
from collections import Counter
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parent


def main():
    source=ROOT/'derived_inventory.json'
    data=json.loads(source.read_text())
    rows=data['rows'];ready=[r for r in rows if r['status']=='ready']
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(12.6,4.7),layout='constrained')
    cohorts=['DS24','DS26','DS27','DS28','FRSH']
    states=[('ready','Ready','#2878b5'),('history_insufficient','Insufficient history','#f2ba54'),
            ('projection_unsupported','Poor projection','#c96464'),('invalid_or_missing','Alignment over 120 s','#8064a2'),
            ('no_RF_target','No prior target','#cccccc')]
    bottom=np.zeros(len(cohorts))
    for state,label,color in states:
        counts=np.array([sum(r['status']==state and r['dataset']==d for r in rows) for d in cohorts])
        bars=axes[0].bar(cohorts,counts,bottom=bottom,label=label,color=color,width=.72)
        for bar,count in zip(bars,counts):
            if count>=3:
                axes[0].text(bar.get_x()+bar.get_width()/2,bar.get_y()+bar.get_height()/2,str(count),ha='center',va='center',fontsize=9)
        bottom+=counts
    for i,total in enumerate(bottom):axes[0].text(i,total+2,str(int(total)),ha='center',va='bottom',fontweight='bold')
    axes[0].set(title='Causal-history support over all 205 scans',ylabel='Scans',ylim=(0,162))
    axes[0].legend(loc='upper right',frameon=False,fontsize=8)
    axes[0].grid(axis='y',alpha=.16);axes[0].set_axisbelow(True)
    eig=np.asarray([r['bounded_eigenvalues'] for r in ready])
    for k,(label,color) in enumerate([('Smallest','#8e8e8e'),('Middle','#36a088'),('Largest','#2878b5')]):
        values=np.sort(eig[:,k])
        axes[1].step(values,np.arange(1,len(values)+1)/len(values),where='post',label=label,color=color,lw=1.8)
    axes[1].axvline(1,color='black',ls=':',lw=1)
    axes[1].axvline(16,color='black',ls=':',lw=1)
    axes[1].set(title='Anisotropic covariance in 96 ready contexts',xlabel='Coefficient covariance eigenvalue (baseline = 1)',
                ylabel='Fraction of ready contexts',xscale='log',xlim=(.85,18.8),ylim=(0,1.03),xticks=[1,2,4,8,16])
    axes[1].set_xticklabels(['1','2','4','8','16'])
    axes[1].legend(frameon=False,fontsize=9,loc='lower right')
    axes[1].text(.03,.92,'55 largest eigenvalues reach the fixed ceiling\nTwo contexts retain the identity covariance',
                 transform=axes[1].transAxes,fontsize=9,va='top',bbox=dict(facecolor='white',edgecolor='none',alpha=.9))
    axes[1].grid(alpha=.16)
    fig.suptitle('Pre-scan TLE disagreement supplies a bounded uncertainty proxy',fontsize=13)
    fig.supxlabel('Prior frozen generic RF target ledger; no position fitting or evaluation coordinate. TLE histories are correlated, not orbit truth.',fontsize=9)
    for extension in ['png','pdf']:fig.savefig(ROOT/('history_covariance_inventory.'+extension),dpi=180)
    plt.close(fig)
    print(ROOT/'history_covariance_inventory.png')


if __name__=='__main__':main()
