"""Show the actual one-rate support without inventing sample-rate variation."""
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parent
rows=list(csv.DictReader((ROOT/'position-errors.csv').open()))
audit=json.loads((ROOT/'capture-audit.json').read_text())
datasets=['DS24','DS26','DS27','DS28']
colors=['#d55e00','#0072b2','#009e73','#aa4499']
fig,axes=plt.subplots(2,4,figsize=(13,7),sharex=True,sharey=True)
for col,(ds,color) in enumerate(zip(datasets,colors)):
    rates={v['sample_rate_hz'] for v in audit[ds]['configurations'].values()}
    assert rates=={10000000}, (ds,rates)
    for row,arm in enumerate(['fitted_c','c0']):
        ax=axes[row,col]
        for method,marker,c in [('ALGO05','o',color),('72h_30s','x','#111111')]:
            errors=np.array([float(r['error_m'])/1000 for r in rows if (r['dataset'],r['arm'],r['method'])==(ds,arm,method)])
            ax.scatter(np.full(len(errors),10.),errors,s=22,alpha=.55,marker=marker,c=c,label='ALGO06' if method=='72h_30s' else method)
            if method=='ALGO05':
                ax.set_title(f'{ds}: n={len(errors)}\nmedian {np.median(errors):.3f} km')
                ax.plot([9.85,10.15],[np.median(errors)]*2,color=color,lw=3)
        ax.axhline(.5,color='gray',ls=':',lw=1)
        ax.set_xlim(9.5,10.5);ax.set_xticks([10]);ax.grid(alpha=.2)
        if col==0:ax.set_ylabel(('Fitted c' if row==0 else 'c = 0')+'\nPosition error (km)')
        if row==1:ax.set_xlabel('Sample rate (MS/s)')
axes[0,0].legend(fontsize=8)
fig.suptitle('Error versus recorded sample rate — all four cohorts use 10 MS/s\nNo horizontal jitter or fitted trend: these data cannot estimate a sample-rate effect')
fig.tight_layout();fig.savefig(ROOT/'error_vs_sample_rate.png',dpi=170)
