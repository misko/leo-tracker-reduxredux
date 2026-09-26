"""Acquisition-only audit of pilot epoch continuity within CFO tracklets."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.application.scanner_trajectory import project_scanner_candidates

HERE=Path(__file__).resolve().parent
OUT=HERE/'cfo-scale-mixture'

def causal_breaks(times,epochs,threshold=44.):
    history=[];innovations=[];breaks=[]
    for i,(t,y) in enumerate(zip(times,epochs)):
        error=None
        if len(history)>=3:
            indices=history[-5:];x=times[indices]-t;coefficient=np.polyfit(x,epochs[indices],2);error=float(y-coefficient[-1])
            if abs(error)>threshold:breaks.append(i);history=[]
        innovations.append(error);history.append(i)
    return innovations,breaks

def main():
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'));output=[];fig,axes=plt.subplots(2,2,figsize=(12,7),constrained_layout=True)
    try:
        for scan,sid in enumerate(['scan-fw-f7515a5fdb02cda5','scan-fw-888fc1e1e005ded3']):
            source=store.load(sid);points={c.candidate_id:c for c in project_scanner_candidates(source)};raw={(p.visit_index,p.receiver_id,p.probe_index,c.candidate_rank):(p,c) for p in source.probes for c in p.candidates};members=json.loads((HERE/'timing-trial'/f'{sid}-f1-q65-b161-membership.json').read_text())['tracks']
            for mode,m in enumerate(members):
                rows=[]
                for cid,t,cfo in zip(m['candidate_ids'],m['times_s'],m['measured_hz']):
                    point=points[cid];p,c=raw[point.visit_index,point.receiver_id,point.probe_index,point.candidate_rank];relative=p.valid_start_counter-source.timing.session_start_device_sample_counter+p.probe_start_ms*source.sample_rate_hz/1000;epoch=c.integer_epoch_sample+c.fractional_epoch_offset_samples;scale=11.2e9/point.actual_rf_hz
                    rows.append(dict(candidate_id=cid,visit=p.visit_index,time_s=t,frame_phase_cycles=float(((relative+epoch)*750/source.sample_rate_hz)%1),raw_cfo_hz=c.fractional_tracking_cfo_hz,normalized_cfo_hz=cfo,relative_alias_index=round((cfo-c.fractional_tracking_cfo_hz*scale)/(scale/4.4e-6)),margin=c.fractional_margin,exact_control_ratio=c.fractional_exact_score/max(c.fractional_control_score,1e-30)))
                times=np.array([r['time_s'] for r in rows]);epochs=np.unwrap(np.array([r['frame_phase_cycles'] for r in rows])*2*np.pi)/(2*np.pi)*source.sample_rate_hz/750;innovations,breaks=causal_breaks(times,epochs)
                for r,q,e in zip(rows,epochs,innovations):r.update(unwrapped_epoch_samples=float(q),causal_epoch_innovation_samples=e)
                output.append(dict(session_id=sid,mode=mode,track_id=m['track_id'],rows=rows,breaks=[rows[i] for i in breaks]))
                color=['tab:blue','tab:red'][mode];axes[scan,0].scatter(times,epochs-epochs[0],s=12,color=color,label=f'Mode {mode}');valid=[i for i,e in enumerate(innovations) if e is not None];axes[scan,1].scatter(times[valid],np.array(innovations,dtype=float)[valid],s=12,color=color)
                print(sid,mode,'breaks',[(rows[i]['visit'],rows[i]['time_s'],innovations[i]) for i in breaks],flush=True)
            axes[scan,0].set_ylabel('Unwrapped frame epoch change (samples)');axes[scan,0].legend(fontsize=8);axes[scan,1].set_ylabel('Causal epoch innovation (samples)');axes[scan,1].axhline(44,color='gray',ls='--');axes[scan,1].axhline(-44,color='gray',ls='--')
            for ax,title in zip(axes[scan],['Pilot timing within CFO tracklets','Quadratic prediction from up to five past points']):ax.set_xlabel('Time since scan start (s)');ax.set_title(['09:50','12:00'][scan]+' UTC\n'+title,fontsize=10);ax.grid(alpha=.2)
    finally:store.close()
    fig.savefig(OUT/'pilot-epochs.png',dpi=160);plt.close(fig)
    (OUT/'pilot-epoch-audit.json').write_text(json.dumps(dict(meaning='Descriptive acquisition-only reference-break detector, threshold one nominal 4.4us symbol =44 samples. Reset after a detected break. No points removed or association scores changed. A break is not proof of satellite identity change.',threshold_samples=44,tracks=output),indent=2)+'\n')

if __name__=='__main__':main()
