"""Offline coefficient-coupling plot, all primary donor histories retained."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import study

HERE=Path(__file__).resolve().parent
d=study.read(HERE/'coupling_diagnosis.json');rows=d['rows']
fig,axes=plt.subplots(1,2,figsize=(11,4.4),layout='constrained')
x=np.array([r['positive_scaled_CFO_slope_samples_per_s2']for r in rows]);y=np.array([r['timing_acceleration_samples_per_s2']for r in rows])
axes[0].scatter(x,y,s=14,alpha=.5)
limits=[min(x.min(),y.min()),max(x.max(),y.max())]
axes[0].plot(limits,limits,'k--',label='Empirical positive-sign unit relation')
axes[0].set(xlabel='(sample rate / actual RF) × donor CFO slope (samples/s²)',
    ylabel='Donor timing acceleration (samples/s²)',title='All 362 primary histories; outliers preserved')
axes[0].legend(fontsize=8)
for field,label in [('timing_acceleration_floor_SE','Timing acceleration'),('positive_difference_floor_SE','Difference from RF-scaled CFO slope')]:
    values=np.sort(np.array([r[field]for r in rows]))
    axes[1].plot(values,np.arange(1,len(values)+1)/len(values),label=label)
axes[1].set(xscale='log',xlabel='Coefficient SE with engineering noise floors (samples/s²)',
    ylabel='Fraction of 362 histories',title='Conditional regression uncertainty; RF scale uncalibrated')
axes[1].legend(fontsize=8)
fig.suptitle('Earlier-donor coupling is suggestive; RF sign and physical mechanism remain unverified')
for ext in ['png','pdf']:fig.savefig(HERE/f'timing_CFO_coupling.{ext}',dpi=180,bbox_inches='tight')
