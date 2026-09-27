import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent


def main():
    data=json.loads((HERE/'validation-results.json').read_text());assert data['complete'];rows=[]
    fig,axes=plt.subplots(1,2,figsize=(10,4.5))
    for i,s in enumerate(data['scans']):
        row=dict(session_id=s['session_id'],windows=len(s['windows']),arms={},dwells=[])
        for arm in ['linear','curvature_5000']:
            e=np.concatenate([w['arms'][arm]['errors_rad'] for w in s['windows']]);row['arms'][arm]=dict(held_pilot_rms_deg=float(np.degrees(np.sqrt(np.mean(e*e)))),boundary_windows=sum(w['arms'][arm]['model']['curvature_boundary'] for w in s['windows']))
        for group,visit in sorted({(w['group'],w['visit']) for w in s['windows']}):
            ww=[w for w in s['windows'] if w['group']==group and w['visit']==visit];d=dict(group=group,visit=visit,windows=len(ww),arms={})
            for arm in row['arms']:
                z=np.mean([np.exp(1j*w['arms'][arm]['phase_dd_rad']) for w in ww]);d['arms'][arm]=dict(R=float(abs(z)),phase_rad=float(np.angle(z)))
            d['phase_change_deg']=float(np.degrees(np.angle(np.exp(1j*(d['arms']['curvature_5000']['phase_rad']-d['arms']['linear']['phase_rad'])))));row['dwells'].append(d)
        row['median_abs_dwell_phase_change_deg']=float(np.median([abs(d['phase_change_deg']) for d in row['dwells']]))
        row['held_rms_change_deg']=row['arms']['curvature_5000']['held_pilot_rms_deg']-row['arms']['linear']['held_pilot_rms_deg'];rows.append(row)
        axes[0].bar(np.array([0,1])+i*3,[row['arms'][a]['held_pilot_rms_deg'] for a in row['arms']],color=['steelblue','darkorange'])
        axes[1].scatter([d['visit'] for d in row['dwells']],[d['phase_change_deg'] for d in row['dwells']],label=s['session_id'][-8:])
    axes[0].set_xticks([.5,3.5],[s['session_id'][-8:] for s in data['scans']]);axes[0].set_ylabel('Held pilot RMS (degrees)');axes[0].set_title('Blue: linear; orange: curvature ±5000 Hz/s');axes[1].set_xlabel('Visit index');axes[1].set_ylabel('Change in mean source DD (degrees)');axes[1].axhline(0,color='gray',lw=1);axes[1].legend();fig.suptitle('Fixed curvature arm on two additional DS6 scans');fig.tight_layout();fig.savefig(HERE/'validation.png',dpi=180)
    out=dict(scans=rows,scope='No position fit; phase changes are estimator differences, not known corrections');(HERE/'summary.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps([{k:v for k,v in r.items() if k!='dwells'} for r in rows],indent=2))


if __name__=='__main__':main()
