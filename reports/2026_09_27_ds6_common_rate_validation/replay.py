"""Bounded real-IQ validation of the frozen common-rate extractor."""
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


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',type=int,required=True);args=parser.parse_args()
    protocol=json.loads((HERE/'protocol.json').read_text());sid=protocol['selected'][args.scan]['session_id']
    for name,digest in protocol['source_sha256'].items():assert sha(ROOT/name)==digest
    plan_path=HERE/(sid+'-plan.json');plan=json.loads(plan_path.read_text())
    assert plan['protocol_sha256']==sha(HERE/'protocol.json')
    output=HERE/(sid+'-replay.json')
    if output.exists():
        old=json.loads(output.read_text())
        assert old['plan_sha256']==sha(plan_path)
        if old['complete']:
            print('Already complete',sid);return
        raise RuntimeError('Partial replay exists; inspect before explicitly resuming')
    store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True)
    cap=store.inspect(sid);assert cap.manifest_sha256==plan['input_manifest_sha256']
    rows=[];controls=[];audits=[];started=time.monotonic();rate=plan['rate_hz']
    def write(complete):
        output.write_text(json.dumps(dict(session_id=sid,plan_sha256=sha(plan_path),protocol_sha256=sha(HERE/'protocol.json'),
            complete=complete,elapsed_s=time.monotonic()-started,rows=rows,controls=controls,audits=audits),indent=2)+'\n')
    try:
        with store.reader(sid,expected=cap) as reader:
            for v in plan['selected']:
                event,raw=reader.read_visit_ci16(v['visit'])
                assert event.event.valid_start_counter==v['valid_start_counter'] and len(raw)==v['valid_samples']
                iq=raw[...,0].astype(float)+1j*raw[...,1].astype(float)
                audits.append(dict(visit=v['visit'],group=v['group'],samples=len(raw),
                    clipped_rows=int(np.count_nonzero(np.any(abs(raw.astype(np.int32))>=32767,axis=(1,2)))),
                    integrity='Compressed and uncompressed hashes verified by public reader'))
                for ms in protocol['starts_ms']:
                    start=round(rate*ms/1000);n=round(rate*protocol['width_ms']/1000)
                    assert start+n<=len(iq)
                    chunk=iq[start:start+n]
                    original=phase.analyze(chunk,v,rate,start)
                    relative=(v['valid_start_counter']-plan['timing']['session_start_device_sample_counter']+start+n/2)/rate
                    row=dict(visit=v['visit'],group=v['group'],partition=v['partition'],start_ms=ms,time_s=relative,original=original)
                    if original['both_qualified']:
                        data=frames(chunk,v,rate,start,original)['data']
                        row.update(shared=estimate(data,True),independent=estimate(data,False))
                    rows.append(row)
                    if ms==0:
                        shifted=chunk.copy();shifted[:,1]=np.roll(shifted[:,1],round(rate*.000173))
                        control=phase.analyze(shifted,v,rate,start)
                        controls.append(dict(visit=v['visit'],group=v['group'],rx1_roll_samples=round(rate*.000173),
                                             both_qualified=control['both_qualified'],metrics=control['metrics']))
                write(False)
                print(sid,'visits',len(audits),'windows',len(rows),'qualified',sum(r['original']['both_qualified'] for r in rows),flush=True)
        write(True)
    finally:store.close()


if __name__=='__main__':main()
