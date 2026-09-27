import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent
p=json.loads((HERE/'protocol.json').read_text());rows=[]
for record in p['selected']:
    sid=record['session_id'];plan=json.loads((HERE/f'{sid}-plan.json').read_text());r=json.loads((HERE/f'{sid}-replay.json').read_text());assert r['complete'] and r['plan_sha256']==hashlib.sha256((HERE/f'{sid}-plan.json').read_bytes()).hexdigest();qualified=[w for w in r['rows'] if w['original']['both_qualified']];train=[v for v in plan['selected'] if v['partition']=='train'];phases=[]
    for v in plan['selected']:
        windows=[w for w in qualified if w['visit']==v['visit']];z=np.mean([np.exp(1j*w['shared']['evaluation_dd']) for w in windows]) if windows else None
        phases.append(dict(visit=v['visit'],time_s=(v['valid_start_counter']-plan['timing']['session_start_device_sample_counter'])/plan['rate_hz'],partition=v['partition'],windows=len(windows),R=float(abs(z)) if z is not None else None,phase_deg=float(np.degrees(np.angle(z))) if z is not None else None))
    pair_entropy=sum(p['track_entropy'][sid].get(m['rx0_track_id'],0.) for m in plan['selected'][0]['modes']) if plan['selected'] else None
    row=dict(session_id=sid,rate_msps=record['sample_rate_msps'],scan_max_entropy=max(p['track_entropy'][sid].values()),eligible_pair_groups=sum(g['train']>=2 and g['held']>=2 for g in plan['group_inventory']),selected_pair_entropy=pair_entropy,selected_visits=len(plan['selected']),qualified_windows=len(qualified),examined_windows=len(r['rows']),controls_qualified=sum(c['both_qualified'] for c in r['controls']),controls=len(r['controls']),train_span_s=(max(v['valid_start_counter'] for v in train)-min(v['valid_start_counter'] for v in train))/plan['rate_hz'] if train else None,phase_visits=phases,train_phase_available=bool(train) and all(any(w['visit']==v['visit'] for w in qualified) for v in train))
    for arm in ['independent','shared']:
        row[arm+'_rms_deg']=float(np.degrees(np.sqrt(np.mean([np.mean(np.square(w[arm]['held_frame_errors_rad'])) for w in qualified])))) if qualified else None
    rows.append(row)
(HERE/'summary.json').write_text(json.dumps(dict(complete=True,scans=rows),indent=2)+'\n')
fig,axes=plt.subplots(1,2,figsize=(12,4),constrained_layout=True);x=np.arange(len(rows));labels=[r['session_id'][-8:] for r in rows]
axes[0].bar(x-.17,[r['scan_max_entropy'] for r in rows],.34,label='Most ambiguous track in scan');axes[0].bar(x+.17,[r['selected_pair_entropy'] or 0 for r in rows],.34,label='Selected eligible pair');axes[0].set(xticks=x,xticklabels=labels,ylabel='Training association entropy (nats)',title='Ambiguous tracks do not overlap usable phase pairs');axes[0].legend(fontsize=8)
axes[1].bar(x,[r['qualified_windows'] for r in rows]);axes[1].set(xticks=x,xticklabels=labels,ylabel='Qualified 7 ms windows',title='Frozen replay: unavailable scans retained');fig.savefig(HERE/'opportunity.png',dpi=160)
print(json.dumps(rows,indent=2))
valid=[r for r in rows if r['qualified_windows']];fig,axes=plt.subplots(1,len(valid),figsize=(10,4),constrained_layout=True)
for ax,r in zip(np.atleast_1d(axes),valid):
    points=[v for v in r['phase_visits'] if v['phase_deg'] is not None];origin=min(v['time_s'] for v in r['phase_visits'])
    for part,marker in [('train','o'),('held','x')]:
        take=[v for v in points if v['partition']==part];ax.scatter([v['time_s']-origin for v in take],[v['phase_deg'] for v in take],marker=marker,label=part)
    ax.set(title=r['session_id'][-8:]+f" ({r['rate_msps']:g} MS/s)",xlabel='Time from first selected visit (s)',ylabel='Source-pair phase double difference (degrees)');ax.legend();ax.grid(alpha=.2)
fig.suptitle('Measured pilot phase: geometric attribution not yet established');fig.savefig(HERE/'phase_visits.png',dpi=160)
