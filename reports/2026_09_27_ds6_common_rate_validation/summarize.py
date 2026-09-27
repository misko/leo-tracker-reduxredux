"""Evaluate the frozen cross-scan decision rule and illustrate every scan."""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent


def summarize_scan(plan,replay):
    qualified=[r for r in replay['rows'] if r['original']['both_qualified']]
    out=dict(session_id=plan['session_id'],rate_hz=plan['rate_hz'],tracks=len(plan['tracks']),
        metadata_groups=len(plan['group_inventory']),selected_groups=len(plan['selected_groups']),selected_dwells=len(plan['selected']),
        windows=len(replay['rows']),qualified_windows=len(qualified),
        qualified_dwells=len({(r['visit'],r['group']) for r in qualified}),
        controls=len(replay['controls']),controls_qualified=sum(c['both_qualified'] for c in replay['controls']),
        clipped_rows=sum(a['clipped_rows'] for a in replay['audits']),evaluable=bool(qualified))
    out['arms']={};out['dwells']=[]
    if not qualified:
        out['unavailable_reason']='No recurrent exact track pair met the frozen metadata support rule' if not plan['selected'] else 'No joint qualified phase window'
        return out
    for arm in ['independent','shared']:
        mse=float(np.mean([np.mean(np.square(r[arm]['held_frame_errors_rad'])) for r in qualified]))
        out['arms'][arm]=dict(window_mean_mse_rad2=mse,window_mean_rms_deg=float(np.degrees(np.sqrt(mse))))
    out['shared_minus_independent_mse_rad2']=out['arms']['shared']['window_mean_mse_rad2']-out['arms']['independent']['window_mean_mse_rad2']
    out['improved']=out['shared_minus_independent_mse_rad2']<0
    for visit,group in sorted({(r['visit'],r['group']) for r in qualified}):
        rr=[r for r in qualified if (r['visit'],r['group'])==(visit,group)]
        item=dict(visit=visit,group=group,qualified_windows=len(rr),time_s=float(np.mean([r['time_s'] for r in rr])))
        for arm in ['independent','shared']:
            phases=np.array([r[arm]['evaluation_dd'] for r in rr]);train=np.array([r[arm]['train_dd'] for r in rr])
            delta=np.angle(np.exp(1j*(phases-train)))
            item[arm]=dict(R=float(abs(np.mean(np.exp(1j*phases)))),train_R=float(abs(np.mean(np.exp(1j*train)))),
                           phase=float(np.angle(np.mean(np.exp(1j*phases)))),train_evaluation_dd_rms_deg=float(np.degrees(np.sqrt(np.mean(delta**2)))))
        out['dwells'].append(item)
    for arm in ['independent','shared']:
        rs=[d[arm]['R'] for d in out['dwells'] if d['qualified_windows']>1]
        out['arms'][arm]['median_multiwindow_R']=float(np.median(rs)) if rs else None
    # Whole physical visits are resampled jointly across groups, preserving
    # common receiver effects and the original window-weighted statistic.
    visit_ids=sorted({r['visit'] for r in qualified})
    clusters=[np.array([np.mean(np.square(r['shared']['held_frame_errors_rad']))-
                       np.mean(np.square(r['independent']['held_frame_errors_rad']))
                       for r in qualified if r['visit']==v]) for v in visit_ids]
    rng=np.random.default_rng(2026092711)
    draws=[float(np.mean(np.concatenate([clusters[i] for i in rng.integers(len(clusters),size=len(clusters))]))) for _ in range(2000)]
    out['exploratory_visit_bootstrap_mse_difference_95pct']=np.quantile(draws,[.025,.975]).tolist()
    return out


def main():
    protocol=json.loads((HERE/'protocol.json').read_text());scans=[];replays=[]
    for r in protocol['selected']:
        sid=r['session_id'];path=HERE/(sid+'-plan.json');plan=json.loads(path.read_text());replay=json.loads((HERE/(sid+'-replay.json')).read_text())
        assert replay['complete'] and replay['plan_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
        scans.append(summarize_scan(plan,replay));replays.append(replay)
    valid=[s for s in scans if s['evaluable']];improved=sum(s.get('improved',False) for s in scans)
    mean_delta=float(np.mean([s['shared_minus_independent_mse_rad2'] for s in valid])) if valid else None
    result=dict(protocol_sha256=hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest(),scans=scans,
                evaluable_scans=len(valid),improved_scans=improved,equal_scan_mean_mse_difference_rad2=mean_delta,
                frozen_decision_passed=bool(improved>=3 and mean_delta is not None and mean_delta<0),
                interpretation='Extractor prediction only; no geographic or satellite-association accuracy measured. Bootstrap is descriptive with very few visit clusters.')
    (HERE/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    fig,axes=plt.subplots(2,2,figsize=(11,9),layout='constrained')
    for ax,s,replay in zip(axes.flat,scans,replays):
        ax.set_title(f"{s['session_id'][-8:]} — {s['rate_hz']/1e6:g} MS/s\n{s['qualified_windows']}/{s['windows']} windows qualified")
        ax.set(xlabel='Independent-rate held pilot RMS (degrees)',ylabel='Shared-rate held pilot RMS (degrees)',xlim=(0,180),ylim=(0,180))
        ax.plot([0,180],[0,180],color='0.7',ls='--',label='Equal prediction error')
        if s['evaluable']:
            qualified=[r for r in replay['rows'] if r['original']['both_qualified']]
            x=[np.degrees(np.sqrt(np.mean(np.square(r['independent']['held_frame_errors_rad'])))) for r in qualified]
            y=[np.degrees(np.sqrt(np.mean(np.square(r['shared']['held_frame_errors_rad'])))) for r in qualified]
            ax.scatter(x,y,s=18,alpha=.65,label='Qualified window')
            ax.scatter([s['arms']['independent']['window_mean_rms_deg']],[s['arms']['shared']['window_mean_rms_deg']],
                       marker='*',s=180,color='tab:red',label='Scan aggregate')
        else:ax.text(.5,.5,'No eligible recurring pair\nRetained without replacement',ha='center',va='center',transform=ax.transAxes)
        ax.legend(fontsize=8,loc='upper left')
    fig.suptitle('Frozen common-rate phase validation on four additional DS6 scans\nBelow diagonal favors shared rate; separate source phase intercepts preserved')
    fig.savefig(HERE/'cross-scan-validation.png',dpi=160);plt.close(fig)
    print(json.dumps({k:v for k,v in result.items() if k!='scans'},indent=2))
    for s in scans:print(s['session_id'],s['qualified_windows'],s['arms'])


if __name__=='__main__':main()
