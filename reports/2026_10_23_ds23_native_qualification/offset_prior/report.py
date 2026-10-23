"""Render saved RF-only conditional diagnostics."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_offset import OUT,estimate,m
d=json.loads((OUT/'results.json').read_text())
d['estimates']={a:estimate(d['rows'],a) for a in m.ARMS};m.write(OUT/'results.json',d)
fig,axes=plt.subplots(1,2,figsize=(13,5),sharey=True)
for ax,arm in zip(axes,m.ARMS,strict=True):
    rows=[r for r in d['rows'] if r['arm']==arm];x=np.arange(len(rows))
    y=np.array([r['mean_error_hz'] for r in rows]);shared=np.sqrt([r['shared_mean_variance_hz2'] for r in rows]);noise=np.sqrt([r['noise_mean_variance_hz2'] for r in rows])
    ax.errorbar(x,y,yerr=shared,fmt='o',capsize=3,label='Mean error ± shared calibration SD')
    ax.errorbar(x+.12,y,yerr=noise,fmt='.',color='tab:orange',label='Native noise mean SD')
    ax.axhline(0,color='black',lw=.6);ax.set_xticks(x,[r['case'][-4:]+' / '+str(r['family']) for r in rows],rotation=70,ha='right');ax.set_title(arm);ax.legend(fontsize=8)
axes[0].set_ylabel('Held-source mean CFO prediction error (Hz)')
fig.suptitle('Conditional on frozen full-parent position; one whole source per family')
fig.tight_layout();fig.savefig(OUT/'mean_prediction.png',dpi=160)
print(json.dumps(d['estimates'],indent=2))
