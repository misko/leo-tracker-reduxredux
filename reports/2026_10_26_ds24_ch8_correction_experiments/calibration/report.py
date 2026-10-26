"""Summarize the frozen RF prediction screen without geographic evaluation."""
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from run import write

OUT=Path(__file__).resolve().parent
rows=[]; sources={}
for case in ('DS24-0010','DS24-0011'):
    arms={}
    for arm in ('c0','fitted_c'):
        path=OUT/f'{case}_{arm}.json'; d=json.loads(path.read_text()); arms[arm]=d
        sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        assert d['baseline_objective_delta']==0
        old=d['results']['RF_scaled']; new=d['results']['native_Hz']
        for group in ('all','RX1','RX2'):
            a=old['held'][group];b=new['held'][group]
            rows.append(dict(case=case,arm=arm,group=group,points=a['points'],
                baseline_density=a['negative_twice_log_density'],native_density=b['negative_twice_log_density'],
                delta_density=b['negative_twice_log_density']-a['negative_twice_log_density'],
                baseline_RMS_hz=a['RMS_hz'],native_RMS_hz=b['RMS_hz'],
                both_training_checks=old['training_checks_pass'] and new['training_checks_pass']))
    for field in ('train_curved_IDs','held_CH8_IDs','train_predictive_IDs'):
        assert arms['c0'][field]==arms['fitted_c'][field]
allrows=[r for r in rows if r['group']=='all']
gain=-sum(r['delta_density'] for r in allrows)
old_energy=sum(r['points']*r['baseline_RMS_hz']**2 for r in allrows)
new_energy=sum(r['points']*r['native_RMS_hz']**2 for r in allrows)
qualified=all(r['delta_density']<0 and r['both_training_checks'] for r in allrows) and gain>=10 and new_energy<=old_energy
write(OUT/'summary.json',dict(rows=rows,aggregate_predictive_gain=gain,
    total_unique_held_points=sum(r['points'] for r in allrows if r['arm']=='c0'),
    pooled_RMS_before=float(np.sqrt(old_energy/sum(r['points'] for r in allrows))),
    pooled_RMS_after=float(np.sqrt(new_energy/sum(r['points'] for r in allrows))),
    advance_native_Hz=qualified,all_c_memberships_exact=True,no_GPS_evaluation=True,
    source_sha256=sources,decision='Do not advance this native-Hz replacement; the fixed prediction screen fails.'))

fig,ax=plt.subplots(1,2,figsize=(11,4.3),constrained_layout=True)
x=np.arange(4);labels=[r['case'].replace('DS24-','')+'\n'+r['arm'] for r in allrows]
ax[0].bar(x,[r['delta_density'] for r in allrows],color=['#447ca0' if r['delta_density']<0 else '#bb6c55' for r in allrows])
ax[0].axhline(0,color='black',lw=.8);ax[0].set(xticks=x,xticklabels=labels,ylabel='Native − RF-scaled predictive loss',title='Held CH8: negative change is better')
ax[1].bar(x-.17,[r['baseline_RMS_hz'] for r in allrows],width=.34,label='RF-scaled')
ax[1].bar(x+.17,[r['native_RMS_hz'] for r in allrows],width=.34,label='Native Hz')
ax[1].set(xticks=x,xticklabels=labels,ylabel='Raw held-prediction RMS (Hz)',title='Whole CH8 fragments excluded from training');ax[1].legend()
fig.suptitle('Receiver drift comparison: conditional on original identities; no GPS used')
fig.savefig(OUT/'held_CH8_comparison.png',dpi=180);fig.savefig(OUT/'held_CH8_comparison.pdf')
print('Advance:',qualified,'aggregate predictive gain:',gain)
