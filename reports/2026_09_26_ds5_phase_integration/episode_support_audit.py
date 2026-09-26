"""Check acquisition break support without consulting phase or CFO fit errors."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
OUT=HERE/'phase-episodes'

def supported_breaks(times,epochs,threshold=44.):
    """Require five past points and extrapolation no longer than their span."""
    history=[];rows=[];breaks=[]
    for i,(t,y) in enumerate(zip(times,epochs)):
        record=dict(index=i,innovation_samples=None,supported=False)
        if len(history)>=5:
            indices=history[-5:];span=times[indices[-1]]-times[indices[0]];gap=t-times[indices[-1]]
            record.update(history_span_s=float(span),forecast_gap_s=float(gap))
            if span>0 and gap<=span:
                coefficient=np.polyfit(times[indices]-t,epochs[indices],2)
                error=float(y-coefficient[-1]);record.update(innovation_samples=error,supported=True)
                if abs(error)>threshold:breaks.append(i);history=[]
        rows.append(record);history.append(i)
    return rows,breaks

def main():
    source=json.loads((HERE/'cfo-scale-mixture/pilot-epoch-audit.json').read_text());out=[]
    fig,axes=plt.subplots(1,2,figsize=(11,4),constrained_layout=True)
    for track in source['tracks']:
        t=np.array([r['time_s'] for r in track['rows']]);y=np.array([r['unwrapped_epoch_samples'] for r in track['rows']]);rows,breaks=supported_breaks(t,y)
        out.append(dict(session_id=track['session_id'],mode=track['mode'],supported_breaks=[track['rows'][i] for i in breaks],prediction_support=rows))
        ax=axes[0 if 'f751' in track['session_id'] else 1];valid=[i for i,r in enumerate(rows) if r['supported']]
        ax.scatter(t[valid],[rows[i]['innovation_samples'] for i in valid],s=15,label=f"Mode {track['mode']}")
        print(track['session_id'],track['mode'],[(track['rows'][i]['visit'],t[i]) for i in breaks],flush=True)
    for ax,title in zip(axes,['09:50 UTC','12:00 UTC']):
        ax.set_title(title);ax.set_xlabel('Time since scan start (s)');ax.set_ylabel('Supported epoch innovation (samples)');ax.axhline(44,color='gray',ls='--');ax.axhline(-44,color='gray',ls='--');ax.legend();ax.grid(alpha=.2)
    fig.savefig(OUT/'supported-innovations.png',dpi=160);plt.close(fig)
    (OUT/'support-audit.json').write_text(json.dumps(dict(protocol='Five past points; gap no longer than past span; 44 sample threshold; reset after flag. Retrospective diagnostic, not calibrated false-alarm model.',tracks=out),indent=2)+'\n')

if __name__=='__main__':main()
