from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parent
rows=json.loads((root/'results.json').read_text());detail=json.loads((root/'uncertainty.json').read_text())
fig,axes=plt.subplots(1,2,figsize=(12,4.7))
for arm,marker in [(0,'o'),(1,'s')]:
    r=[x for x in rows if x['arms']]
    a=[x['arms'][arm]['unweighted']['held_rms_deg'] for x in r];b=[x['arms'][arm]['weighted']['held_rms_deg'] for x in r]
    axes[0].scatter(a,b,marker=marker,label=['±0.2 Hz','±20 Hz'][arm])
    for x,y,row in zip(a,b,r):axes[0].annotate(row['session_id'][-4:],(x,y),xytext=(3,3),textcoords='offset points',fontsize=8)
axes[0].plot([0,60],[0,60],'k--',alpha=.4);axes[0].set(xlabel='Unweighted held RMS (degrees)',ylabel='Weighted held RMS (degrees)',title='Below diagonal = improvement');axes[0].legend();axes[0].grid(alpha=.2)
sigma=[];error=[]
for d in detail:
    if d['qualified']:
        sigma.extend(d['sigma_deg']);error.extend(np.abs(d['fit_eval_difference_deg']))
axes[1].scatter(sigma,error,s=12,alpha=.45);axes[1].set(xlabel='Fit-only phase standard error (degrees)',ylabel='Absolute fit/evaluation phase difference (degrees)',title='265 qualified pilot pairs; errors are dependent');axes[1].grid(alpha=.2)
fig.tight_layout();fig.savefig(root/'weighted-comparison.png',dpi=160)
(root/'summary.json').write_text(json.dumps(dict(selected_dwells=len(rows),evaluable_dwells=sum(bool(r['arms']) for r in rows),qualified_pilot_pairs=len(sigma),median_fit_standard_error_deg=float(np.median(sigma)),median_absolute_fit_evaluation_difference_deg=float(np.median(error)),maximum_gram_condition=max(max(d['gram_condition']) for d in detail),wins_by_rate_bound={str(bound):sum(r['arms'][i]['weighted']['held_rms_deg']<r['arms'][i]['unweighted']['held_rms_deg'] for r in rows if r['arms']) for i,bound in enumerate([.2,20.])}),indent=2)+'\n')
