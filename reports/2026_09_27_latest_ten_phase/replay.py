"""Bounded raw-IQ replay through the verified storage reader."""
from pathlib import Path
import argparse,json,hashlib,time
import numpy as np
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from phase import analyze

HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--scan',type=int,required=True);a=p.parse_args();plan=json.loads((HERE/'plan.json').read_bytes());scan=plan['scans'][a.scan];sid=scan['session_id'];output=HERE/(sid+'.json')
    frozen=dict(protocol={k:v for k,v in plan.items() if k!='scans'},scan=scan);payload=json.dumps(frozen,sort_keys=True,indent=2)+'\n';digest=hashlib.sha256(payload.encode()).hexdigest();(HERE/(sid+'-plan.json')).write_text(payload)
    if output.exists():
        assert json.loads(output.read_text())['scan_plan_sha256']==digest;print('already completed',sid);return
    store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True);cap=store.inspect(sid);assert cap.manifest_sha256==scan['capture_digest'];rows=[];audits=[];errors=[];started=time.monotonic();rate=scan['rate_hz'];timing=scan['timing']
    with store.reader(sid,expected=cap) as reader:
        for v in scan['selected']:
            event,raw=reader.read_visit_ci16(v['visit']);assert event.event.valid_start_counter==v['valid_start_counter'];assert len(raw)==v['valid_samples'];iq=raw[...,0].astype(float)+1j*raw[...,1].astype(float)
            audits.append(dict(visit=v['visit'],sample_count=len(raw),clipped_rows=int(np.count_nonzero(np.any(abs(raw.astype(np.int32))>=32767,axis=(1,2)))),integrity='Compressed and uncompressed chunk digests verified by AdaptiveHopIqReader'))
            for ms in plan['starts_ms']:
                start=round(ms*rate/1000);n=round(plan['width_ms']*rate/1000)
                if start+n>len(iq):continue
                try:
                    out=analyze(iq[start:start+n],v,rate,start);relative=v['valid_start_counter']-timing['session_start_device_sample_counter']+start+n/2;out.update(visit=v['visit'],start_ms=ms,time_s=relative/rate,utc_ns=timing['first_sample_estimate_utc_ns']+round(relative*1e9/rate),channel=v['channel'],edge=v['edge'],group=v['group'],partition=v['partition']);rows.append(out)
                except Exception as e:errors.append(dict(visit=v['visit'],start_ms=ms,error=repr(e)))
            print(sid,v['visit'],'windows',len(rows),'qualified pairs',sum(x['both_qualified'] for x in rows),'errors',len(errors),flush=True)
    store.close();output.write_text(json.dumps(dict(session_id=sid,scan_plan_sha256=digest,rows=rows,audits=audits,errors=errors,elapsed_s=time.monotonic()-started),indent=2)+'\n')

if __name__=='__main__':main()
