"""Bounded replay of previously selected validation windows, fixed curvature arm."""
import hashlib
import json
import sys
import time
from pathlib import Path
import numpy as np
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from run import fit,evaluate

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'2026_09_27_ds6_dwell_phase'))
from experiment import frames


def main():
    sids=['scan-fw-c78fb2dba2465361','scan-fw-c7e37f65ae9e08b0'];src=ROOT/'2026_09_27_ds6_common_rate_validation';files={sid:{kind:src/(sid+'-'+kind+'.json') for kind in ['plan','replay']} for sid in sids}
    protocol=dict(scans=sids,chirp_bound_hz_per_s=5000.,source_hashes={sid:{k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in fs.items()} for sid,fs in files.items()},
        selection='All previously selected visits and originally jointly qualified windows; no phase-result exclusions',
        validation='Fixed linear and 5000 Hz/s curvature arms; fit/evaluation pilot samples disjoint; these scans were used in earlier analyses, not an untouched blind holdout')
    pp=HERE/'validation-protocol.json';pp.write_text(json.dumps(protocol,indent=2)+'\n');rows=[];started=time.monotonic();store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True)
    try:
        for sid in sids:
            plan=json.loads(files[sid]['plan'].read_text());replay=json.loads(files[sid]['replay'].read_text());assert replay['complete']
            assert replay['plan_sha256']==protocol['source_hashes'][sid]['plan']
            cap=store.inspect(sid);assert cap.manifest_sha256==plan['input_manifest_sha256'];rate=plan['rate_hz'];cached=[];out=[]
            with store.reader(sid,expected=cap) as reader:
                for v in plan['selected']:
                    rr=[r for r in replay['rows'] if r['visit']==v['visit'] and r['group']==v['group'] and r['original']['both_qualified']]
                    if not rr:continue
                    event,raw=reader.read_visit_ci16(v['visit']);assert event.event.valid_start_counter==v['valid_start_counter']
                    iq=raw[...,0].astype(float)+1j*raw[...,1].astype(float)
                    for r in rr:
                        start=round(r['start_ms']*rate/1000);n=round(.007*rate);w=frames(iq[start:start+n],v,rate,start,r['original'])
                        rec=dict(visit=v['visit'],group=v['group'],partition=v['partition'],start_ms=r['start_ms'],arms={})
                        for name,bound in [('linear',0.),('curvature_5000',5000.)]:
                            d=w['data']['fit'];model=fit(d['t'],d['z'],d['s'],bound);d=w['data']['evaluation'];rec['arms'][name]=dict(model=model,**evaluate(model,d['t'],d['z'],d['s']))
                        out.append(rec);cached.append(dict(visit=v['visit'],group=v['group'],start_ms=r['start_ms'],frame=w))
                    print(sid,v['visit'],'windows',len(out),'elapsed',round(time.monotonic()-started,1),flush=True)
            def serial(x):
                if isinstance(x,np.ndarray):return dict(real=x.real.tolist(),imag=x.imag.tolist()) if np.iscomplexobj(x) else x.tolist()
                raise TypeError(type(x))
            cachepath=HERE/(sid+'-frames.json');cachepath.write_text(json.dumps(cached,default=serial)+'\n')
            rows.append(dict(session_id=sid,windows=out,frames_sha256=hashlib.sha256(cachepath.read_bytes()).hexdigest()))
            (HERE/'validation-results.json').write_text(json.dumps(dict(complete=len(rows)==2,protocol_sha256=hashlib.sha256(pp.read_bytes()).hexdigest(),elapsed_s=time.monotonic()-started,scans=rows),indent=2)+'\n')
    finally:store.close()


if __name__=='__main__':main()
