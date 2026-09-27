import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent


def main():
    protocol=json.loads((HERE/'protocol.json').read_text());rows=[]
    for record in protocol['selected']:
        sid=record['session_id'];plan=json.loads((HERE/(sid+'-plan.json')).read_text());replay=json.loads((HERE/(sid+'-replay.json')).read_text());assert replay['complete'];assert replay['plan_sha256']==hashlib.sha256((HERE/(sid+'-plan.json')).read_bytes()).hexdigest()
        qualified=[w for w in replay['rows'] if w['original']['both_qualified']];row=dict(session_id=sid,rate_msps=record['sample_rate_msps'],groups=len(plan['selected_groups']),selected_visits=len(plan['selected']),qualified_windows=len(qualified),examined_windows=len(replay['rows']),
            controls_passed=sum(c['both_qualified'] for c in replay['controls']),control_count=len(replay['controls']),clipped_rows=sum(v['clipped_rows'] for v in replay['audits']),evaluable=bool(qualified),arms={},dwells=[])
        for arm in ['independent','shared']:
            if not qualified:continue
            mse=[np.mean(np.square(w[arm]['held_frame_errors_rad'])) for w in qualified];pooled=np.concatenate([w[arm]['held_frame_errors_rad'] for w in qualified]);row['arms'][arm]=dict(equal_window_mse_rad2=float(np.mean(mse)),equal_window_rms_deg=float(np.degrees(np.sqrt(np.mean(mse)))),pooled_rms_deg=float(np.degrees(np.sqrt(np.mean(pooled**2)))))
        for v in plan['selected']:
            ww=[w for w in qualified if w['visit']==v['visit'] and w['group']==v['group']];d=dict(visit=v['visit'],group=v['group'],partition=v['partition'],qualified_windows=len(ww),arms={})
            if ww:
                for arm in ['independent','shared']:
                    z=np.mean([np.exp(1j*w[arm]['evaluation_dd']) for w in ww]);d['arms'][arm]=dict(phase_rad=float(np.angle(z)),R=float(abs(z)))
            row['dwells'].append(d)
        row['metadata_pair_groups']=len(plan['group_inventory'])
        if not qualified:row['unavailable_reason']='No pair meets the frozen minimum of two training and two held visits' if not plan['selected_groups'] else 'No window passed joint signal qualification'
        rows.append(row)
    valid=[r for r in rows if r['evaluable']];wins=sum(r['arms']['shared']['equal_window_mse_rad2']<r['arms']['independent']['equal_window_mse_rad2'] for r in valid)
    mean={arm:float(np.mean([r['arms'][arm]['equal_window_mse_rad2'] for r in valid])) if valid else None for arm in ['independent','shared']}
    decision=bool(len(valid)>=3 and wins>=3 and mean['shared']<mean['independent']);out=dict(complete=True,scans=rows,evaluable_scans=len(valid),shared_wins=wins,equal_scan_mse_rad2=mean,passes_frozen_extraction_gate=decision)
    (HERE/'summary.json').write_text(json.dumps(out,indent=2)+'\n');fig,axes=plt.subplots(1,2,figsize=(11,4.5));x=np.arange(4)
    axes[0].bar(x,[r['qualified_windows'] for r in rows],color='steelblue');axes[0].set_xticks(x,[f"{r['rate_msps']:g} MS/s" for r in rows]);axes[0].set_ylabel('Qualified windows (no replacements)')
    for i,arm in enumerate(['independent','shared']):axes[1].bar(np.arange(len(valid))+i*.35,[r['arms'][arm]['equal_window_rms_deg'] for r in valid],.35,label=arm)
    axes[1].set_xticks(np.arange(len(valid))+.175,[f"{r['rate_msps']:g} MS/s" for r in valid]);axes[1].set_ylabel('Equal-window held RMS (degrees)');axes[1].legend();fig.suptitle('Four additional DS6 scans: frozen shared-rate extraction');fig.tight_layout();fig.savefig(HERE/'expansion.png',dpi=180)
    print(json.dumps({k:v for k,v in out.items() if k!='scans'},indent=2));print(json.dumps([{k:v for k,v in r.items() if k!='dwells'} for r in rows],indent=2))


if __name__=='__main__':main()
