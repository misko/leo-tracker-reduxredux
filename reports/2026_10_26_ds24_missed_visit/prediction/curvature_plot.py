"""Offline donor residual plot; selected histories are not independent holdout."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import study

HERE=Path(__file__).resolve().parent
d=study.read(HERE/'curvature_diagnosis.json');rows=d['rows']
fig,axes=plt.subplots(1,2,figsize=(11,4.4),layout='constrained')
xx=[];yy=[]
for r in rows:
    t=np.array(r['donor_times_s']);x=t/t[-1];y=r['donor_linear_residual_samples']
    axes[0].plot(x,y,c='tab:blue',alpha=.035,lw=.7);xx.extend(x);yy.extend(y)
xx=np.asarray(xx);yy=np.asarray(yy);centers=[];medians=[];low=[];high=[]
for left,right in zip(np.linspace(0,1,9)[:-1],np.linspace(0,1,9)[1:]):
    values=yy[(xx>=left)&(xx<(right if right<1 else right+1e-9))]
    if len(values):
        q=np.quantile(values,[.25,.5,.75]);centers.append((left+right)/2);low.append(q[0]);medians.append(q[1]);high.append(q[2])
axes[0].fill_between(centers,low,high,color='tab:blue',alpha=.18)
axes[0].plot(centers,medians,c='navy',lw=2,label='Pooled median / IQR')
axes[0].axhline(0,c='.5',ls='--');axes[0].set(xlabel='Earlier donor position within selected history (normalized time)',
    ylabel='Residual from frozen linear timing fit (samples)',title='Earlier donor residual shape: 362 primary histories')
axes[0].legend(fontsize=8)
held=[r for r in rows if r['held_last_linear_error_samples']is not None]
for field,label in [('held_last_linear_error_samples','Linear older-donor fit'),('held_last_quadratic_error_samples','Quadratic older-donor fit')]:
    values=np.sort(abs(np.array([r[field]for r in held])))
    axes[1].plot(np.maximum(values,.001),np.arange(1,len(values)+1)/len(values),label=label)
axes[1].axvline(2,c='.5',ls='--');axes[1].set(xscale='log',xlabel='Absolute latest-donor prediction error (samples)',
    ylabel='Fraction of 319 selected histories',title='Coefficients exclude last donor; membership already exposed')
axes[1].legend(fontsize=8)
fig.suptitle('Donor-only curvature diagnosis; no target correction or independent validation')
for ext in ['png','pdf']:fig.savefig(HERE/f'earlier_donor_curvature.{ext}',dpi=180,bbox_inches='tight')
