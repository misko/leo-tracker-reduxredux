"""Replay fixed selected dwells and retain individual pilot phasors."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
import numpy as np
from leo.storage.adaptive_hop import AdaptiveHopIqStore
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'2026_09_27_ds6_position_linked_phase'))
from common_rate import estimate
sys.path.insert(0,str(ROOT/'2026_09_27_ds6_dwell_phase'))
from experiment import frames,phase


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--scan',type=int,required=True);args=ap.parse_args();protocol=json.loads((HERE/'protocol.json').read_text());sid=protocol['selected'][args.scan]['session_id'];path=HERE/(sid+'-plan.json');plan=json.loads(path.read_text());assert plan['protocol_sha256']==sha(HERE/'protocol.json')
    for name,digest in protocol['source_sha256'].items():assert sha(ROOT/name)==digest
    output=HERE/(sid+'-replay.json')
    if output.exists():
        previous=json.loads(output.read_text())
        if previous['complete'] and previous['plan_sha256']==sha(path):print('Already complete',sid);return
        raise RuntimeError('Partial replay exists; inspect rather than restart')
    store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True);rows=[];cache=[];controls=[];audits=[];start_time=time.monotonic();rate=plan['rate_hz']
    def serial(x):
        if isinstance(x,np.ndarray):return dict(real=x.real.tolist(),imag=x.imag.tolist()) if np.iscomplexobj(x) else x.tolist()
        raise TypeError(type(x))
    def save(complete):
        (HERE/(sid+'-frames.json')).write_text(json.dumps(cache,default=serial)+'\n')
        output.write_text(json.dumps(dict(session_id=sid,complete=complete,protocol_sha256=sha(HERE/'protocol.json'),plan_sha256=sha(path),elapsed_s=time.monotonic()-start_time,rows=rows,controls=controls,audits=audits),indent=2)+'\n')
    try:
        cap=store.inspect(sid);assert cap.manifest_sha256==plan['input_manifest_sha256'];assert len(plan['selected'])<=32
        with store.reader(sid,expected=cap) as reader:
            for v in plan['selected']:
                event,raw=reader.read_visit_ci16(v['visit']);assert event.event.valid_start_counter==v['valid_start_counter'] and len(raw)==v['valid_samples'];iq=raw[...,0].astype(float)+1j*raw[...,1].astype(float)
                audits.append(dict(visit=v['visit'],group=v['group'],clipped_rows=int(np.count_nonzero(np.any(abs(raw.astype(np.int32))>=32767,axis=(1,2))))))
                for ms in protocol['starts_ms']:
                    start=round(rate*ms/1000);n=round(rate*protocol['width_ms']/1000);assert start+n<=len(iq);chunk=iq[start:start+n];original=phase.analyze(chunk,v,rate,start)
                    row=dict(visit=v['visit'],group=v['group'],partition=v['partition'],start_ms=ms,time_s=(v['valid_start_counter']-plan['timing']['session_start_device_sample_counter']+start+n/2)/rate,original=original)
                    if original['both_qualified']:
                        frame=frames(chunk,v,rate,start,original);row.update(shared=estimate(frame['data'],True),independent=estimate(frame['data'],False));cache.append(dict(visit=v['visit'],group=v['group'],start_ms=ms,frame=frame))
                    rows.append(row)
                    if ms==0:
                        shifted=chunk.copy();shifted[:,1]=np.roll(shifted[:,1],round(rate*.000173));control=phase.analyze(shifted,v,rate,start);controls.append(dict(visit=v['visit'],group=v['group'],both_qualified=control['both_qualified']))
                save(False);print(sid,'visits',len(audits),'qualified',len(cache),'elapsed',round(time.monotonic()-start_time,1),flush=True)
        save(True)
    finally:store.close()


if __name__=='__main__':main()
