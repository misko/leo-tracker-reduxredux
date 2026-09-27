"""Read the same ten raw dwells to estimate fit-only coefficient covariance."""
import sys,json,copy,hashlib
from pathlib import Path
import numpy as np
from model import phase_covariance,weights,evaluate
HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'2026_09_27_ds6_dwell_phase'
sys.path.insert(0,str(OLD))
from experiment import phase

def decode(windows):
    for w in windows:
        for d in w['data'].values():
            d['z']=np.array(d['z']['real'])+1j*np.array(d['z']['imag'])
            d['t']=np.array(d['t']);d['s']=np.array(d['s'])
    return windows

def main():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    protocol=json.loads((OLD/'refined/protocol.json').read_text())
    plan=json.loads((OLD.parent/'2026_09_27_latest_ten_phase/plan.json').read_text());scans={s['session_id']:s for s in plan['scans']}
    results={r['session_id']:r for r in json.loads((OLD/'refined/results.json').read_text())['results']}
    (HERE/'protocol.json').write_text(json.dumps(dict(source_protocol_sha256=hashlib.sha256((OLD/'refined/protocol.json').read_bytes()).hexdigest(),selection='Same ten dwells and frozen train/held assignments as preceding refined replay',covariance='Paired-RX 20us cluster sandwich on fitting samples; per-pilot delta method; diagonal weights only',floor_deg=.5,relative_weight_cap=100,normalization='Median precision per window',score='Unweighted per-pilot held RMS on unchanged support',arms_hz=[.2,20.]),indent=2)+'\n')
    store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True);rows=[];details=[]
    for item in protocol['scans']:
        sid=item['session_id'];v=item['visit'];scan=scans[sid];cap=store.inspect(sid);assert cap.manifest_sha256==scan['capture_digest']
        with store.reader(sid,expected=cap) as reader:_,raw=reader.read_visit_ci16(v['visit'])
        iq=raw[...,0].astype(float)+1j*raw[...,1].astype(float);rate=scan['rate_hz']
        windows=decode(json.loads((OLD/'refined'/f'{sid}-frames.json').read_text()))
        for i,(ms,w) in enumerate(zip(plan['starts_ms'],windows)):
            start=round(ms*rate/1000);n=round(plan['width_ms']*rate/1000);adjusted=copy.deepcopy(v)
            for mode in adjusted['modes']:mode['seeds'][1]['cfo_hz']+=w['result']['common_cfo_refinement_hz']
            designs,_=phase.designs_for(adjusted,rate,start,n,w['result']['timing_offsets_samples'],False)
            mask,groups=phase.masks(n,rate);X=[np.column_stack(d) for d in designs]
            covariance,condition=phase_covariance(X,iq[start:start+n],mask[0],groups);w['weight']=weights(covariance)
            sigma=np.sqrt(np.maximum(np.diag(covariance),0));err=np.angle(w['data']['evaluation']['z']*np.conj(w['data']['fit']['z']))
            details.append(dict(session_id=sid,visit=v['visit'],window=i,qualified=w['result']['both_qualified'],sigma_deg=np.degrees(sigma).tolist(),weight=w['weight'].tolist(),fit_eval_difference_deg=np.degrees(err).tolist(),covariance_rad2=covariance.tolist(),gram_condition=condition))
        r=results[sid];row=dict(session_id=sid,visit=v['visit'],train_windows=r['train_windows'],held_windows=r['held_windows'],arms=[])
        if r['arms']:
            for bound in [.2,20.]:
                row['arms'].append(dict(bound_hz=bound,unweighted=evaluate(windows,r['train_windows'],r['held_windows'],bound,False),weighted=evaluate(windows,r['train_windows'],r['held_windows'],bound,True)))
        rows.append(row)
        (HERE/'results.json').write_text(json.dumps(rows,indent=2)+'\n');(HERE/'uncertainty.json').write_text(json.dumps(details,indent=2)+'\n')
        print(json.dumps(row),flush=True)
    store.close()
if __name__=='__main__':main()
