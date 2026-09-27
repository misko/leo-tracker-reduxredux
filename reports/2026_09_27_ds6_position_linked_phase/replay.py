"""Bounded raw phase replay and fixed RX1 misalignment controls."""
import sys,json,hashlib,time
from pathlib import Path
import numpy as np
from leo.storage.adaptive_hop import AdaptiveHopIqStore
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'2026_09_27_ds6_dwell_phase'))
from experiment import phase,refine_window

def main():
    payload=(HERE/'plan.json').read_bytes();plan=json.loads(payload);sid=plan['session_id'];rate=plan['rate_hz'];started=time.monotonic()
    store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True);cap=store.inspect(sid);assert cap.manifest_sha256==plan['input_manifest_sha256'];rows=[];controls=[];audits=[]
    with store.reader(sid,expected=cap) as reader:
        for v in plan['selected']:
            event,raw=reader.read_visit_ci16(v['visit']);assert event.event.valid_start_counter==v['valid_start_counter'];iq=raw[...,0].astype(float)+1j*raw[...,1].astype(float)
            audits.append(dict(visit=v['visit'],group=v['group'],samples=len(iq),clipped_rows=int(np.count_nonzero(np.any(abs(raw.astype(np.int32))>=32767,axis=(1,2)))),integrity='Compressed and uncompressed chunk hashes verified by public reader'))
            for ms in plan['starts_ms']:
                start=round(rate*ms/1000);n=round(rate*plan['width_ms']/1000);assert start+n<=len(iq)
                result=phase.analyze(iq[start:start+n],v,rate,start);_,refined=refine_window(iq[start:start+n],v,rate,start,result)
                relative=(v['valid_start_counter']-plan['timing']['session_start_device_sample_counter']+start+n/2)/rate
                rows.append(dict(visit=v['visit'],group=v['group'],partition=v['partition'],start_ms=ms,time_s=relative,utc_ns=plan['timing']['first_sample_estimate_utc_ns']+round(relative*1e9),original=result,refined=refined))
                if ms==0:
                    disrupted=iq[:n].copy();disrupted[:,1]=np.roll(disrupted[:,1],round(rate*.000173));control=phase.analyze(disrupted,v,rate,0)
                    controls.append(dict(visit=v['visit'],group=v['group'],rx1_roll_samples=round(rate*.000173),both_qualified=control['both_qualified'],metrics=control['metrics']))
            (HERE/'replay.json').write_text(json.dumps(dict(plan_sha256=hashlib.sha256(payload).hexdigest(),rows=rows,controls=controls,audits=audits,complete=False,elapsed_s=time.monotonic()-started),indent=2)+'\n')
            print('visits',len(audits),'windows',len(rows),'qualified',sum(r['original']['both_qualified'] for r in rows),'controls passed',sum(r['both_qualified'] for r in controls),flush=True)
    store.close();(HERE/'replay.json').write_text(json.dumps(dict(plan_sha256=hashlib.sha256(payload).hexdigest(),rows=rows,controls=controls,audits=audits,complete=True,elapsed_s=time.monotonic()-started),indent=2)+'\n')
if __name__=='__main__':main()
