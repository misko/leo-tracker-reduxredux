"""Audit guided RX0 recovery without dropping unsupported measurement windows."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent/'long-overlap'

def main():
    plan=json.loads((HERE/'plan.json').read_text());summary=[]
    fig,axes=plt.subplots(2,3,figsize=(13,7),constrained_layout=True);column=0
    for scan in plan['scans']:
        if not scan['selected']:
            summary.append(dict(session_id=scan['session_id'],status=scan['status']));continue
        d=json.loads((HERE/(scan['session_id']+'.json')).read_text());rows=d['rows']
        origin=min(r['utc_ns'] for r in rows);time=np.array([(r['utc_ns']-origin)/1e9 for r in rows])
        error=np.array([np.angle(np.exp(1j*(r['coefficients']['held']['phase_rad']-r['coefficients']['train']['phase_rad']))) for r in rows])
        ratios=np.array([r['held_exact_control_ratios'] for r in rows]);R=np.array([r['coefficients']['full']['R'] for r in rows])
        both=np.min(ratios,axis=1)>2
        qualified=both & (R>=.15) & (abs(error)<=np.pi/6)
        pairs=[]
        for visit in scan['selected']:
            for start in plan['starts_ms']:
                pair=[next((r for r in rows if r['visit']==visit['visit'] and r['start_ms']==start and r['mode']==m),None) for m in (0,1)]
                if any(r is None for r in pair):continue
                dd=float(np.angle(np.exp(1j*(pair[1]['coefficients']['full']['phase_rad']-pair[0]['coefficients']['full']['phase_rad']))))
                indices=[rows.index(r) for r in pair]
                pairs.append(dict(visit=visit['visit'],start_ms=start,time_s=(pair[0]['utc_ns']-origin)/1e9,dd_phase_rad=dd,both_modes_supported=bool(np.all(qualified[indices]))))
        row=dict(session_id=scan['session_id'],status='extracted',span_s=scan['common_span_s'],selected_visits=len(scan['selected']),windows=len(rows),errors=d['errors'],median_R=float(np.median(R)),median_disagreement_deg=float(np.degrees(np.median(abs(error)))),rms_disagreement_deg=float(np.degrees(np.sqrt(np.mean(error**2)))),rx0_held_exact_control_gt2=int(np.sum(ratios[:,0]>2)),rx1_held_exact_control_gt2=int(np.sum(ratios[:,1]>2)),both_rx_held_exact_control_gt2=int(both.sum()),quality_supported_windows=int(qualified.sum()),paired_windows=len(pairs),both_modes_supported_pairs=sum(p['both_modes_supported'] for p in pairs),pairs=pairs)
        summary.append(row)
        for mode,color in [(0,'tab:blue'),(1,'tab:red')]:
            keep=np.array([r['mode']==mode for r in rows]);axes[column,0].scatter(time[keep],R[keep],s=12,color=color,label=f'Mode {mode}')
            axes[column,1].scatter(time[keep],np.degrees(error[keep]),s=12,color=color)
        for supported,marker,color in [(False,'x','gray'),(True,'o','tab:green')]:
            selected=[p for p in pairs if p['both_modes_supported']==supported]
            axes[column,2].scatter([p['time_s'] for p in selected],[np.degrees(p['dd_phase_rad']) for p in selected],s=14,marker=marker,color=color,label='Both modes supported' if supported else 'Unsupported retained')
        axes[column,0].set_ylabel(scan['metadata']['capture_start_utc'][11:16]+' UTC\ncoherence R');axes[column,0].legend(fontsize=8)
        axes[column,1].set_ylabel('Held−train phase (deg)');axes[column,2].set_ylabel('Mode1−mode0 phase (deg)');axes[column,2].legend(fontsize=7)
        for ax in axes[column]:ax.set_xlabel('Time from first selected midpoint (s)');ax.grid(alpha=.2)
        column+=1
    axes[0,0].set_title('RX1-guided RX0 recovery');axes[0,1].set_title('Pilot support consistency');axes[0,2].set_title('Longer-overlap double differences')
    fig.savefig(HERE/'overview.png',dpi=160);plt.close(fig)
    (HERE/'summary.json').write_text(json.dumps(dict(quality_definition='descriptive only: both RX held exact/control >2, full R>=.15, abs held−train phase<=30deg; unsupported windows retained; not a calibrated association gate',scans=summary),indent=2)+'\n')
    print(json.dumps([{k:v for k,v in s.items() if k!='pairs'} for s in summary],indent=2))

if __name__=='__main__':main()
