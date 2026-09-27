import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent


def main():
    first=json.loads((HERE/'results.json').read_text());transfer=json.loads((HERE/'transfer-results.json').read_text());assert first['complete'] and transfer['complete'];rows=[]
    for cohort,data in [('initial',first),('transfer',transfer)]:
        for scan in data['scans']:
            if not scan['windows']:
                rows.append(dict(session_id=scan['session_id'],cohort=cohort,available=False));continue
            a=scan['summary']['equal_weight'];b=scan['summary']['mixture_k16'];dwells=[]
            keys=sorted({(w.get('group','single'),w.get('visit',0)) for w in scan['windows']})
            for group,visit in keys:
                ww=[w for w in scan['windows'] if (w.get('group','single'),w.get('visit',0))==(group,visit)]
                phase={arm:float(np.angle(np.mean([np.exp(1j*w['arms'][arm]['phase_dd_rad']) for w in ww]))) for arm in ['equal_weight','mixture_k16']}
                change=float(np.degrees(np.angle(np.exp(1j*(phase['mixture_k16']-phase['equal_weight'])))))
                dwells.append(dict(group=group,visit=visit,phase_change_deg=change))
            rows.append(dict(session_id=scan['session_id'],cohort=cohort,available=True,windows=len(scan['windows']),
                equal_rms_deg=a['held_pilot_rms_deg'],robust_rms_deg=b['held_pilot_rms_deg'],rms_change_deg=b['held_pilot_rms_deg']-a['held_pilot_rms_deg'],
                held_score_gain=b['common_k4_held_log_score']-a['common_k4_held_log_score'],dwells=dwells))
    valid=[r for r in rows if r['available']];fig,axes=plt.subplots(2,1,figsize=(12,7),sharex=True);x=np.arange(len(valid));colors=['steelblue' if r['cohort']=='initial' else 'darkorange' for r in valid]
    axes[0].bar(x,[r['rms_change_deg'] for r in valid],color=colors);axes[0].axhline(0,color='k',lw=1);axes[0].set_ylabel('Robust − equal RMS (degrees)\nNegative favors robust')
    axes[1].bar(x,[r['held_score_gain'] for r in valid],color=colors);axes[1].axhline(0,color='k',lw=1);axes[1].set_ylabel('Held log-score gain\nPositive favors robust');axes[1].set_xticks(x,[r['session_id'][-8:] for r in valid],rotation=30);fig.suptitle('Fixed robust pilot model: blue initial scans, orange transfer dwells\nAll held pilot samples retained');fig.tight_layout();fig.savefig(HERE/'transfer-comparison.png',dpi=180)
    output=dict(rows=rows,transfer_rms_wins=sum(r['rms_change_deg']<0 for r in valid if r['cohort']=='transfer'),transfer_score_wins=sum(r['held_score_gain']>0 for r in valid if r['cohort']=='transfer'));(HERE/'summary.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output,indent=2))


if __name__=='__main__':main()
