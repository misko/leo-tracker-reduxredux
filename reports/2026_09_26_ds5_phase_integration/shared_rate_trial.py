"""Bounded raw replay: a common receiver rate within each qualified window."""
from pathlib import Path
import json,hashlib
import numpy as np
import zstandard
from joint_phase_run import build
from joint_phase import extract

HERE=Path(__file__).resolve().parent
OUT=HERE/'shared-rate'

def main():
    OUT.mkdir(exist_ok=True);plan=json.loads((HERE/'long-overlap/plan.json').read_text());out=[]
    protocol=dict(selection='Every previously both-qualified joint-phase window; no new qualification threshold or selection. Other windows remain neutral as before.',model='One shared training-fitted residual receiver rate per simultaneous window, separate per-mode phase intercepts. No phase trend across dwells is removed.',limits='Within-window geometric rate differences are approximated as small. Same prior acquisition/timing conditioning. This is retrospective development.')
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    for scan in plan['scans']:
        if not scan['selected']:continue
        sid=scan['session_id'];prior=json.loads((HERE/'joint-phase'/f'{sid}.json').read_text())['rows'];old=json.loads((HERE/'long-overlap'/f'{sid}.json').read_text())['rows'];selected=[r for r in prior if r['both_qualified']];root=Path(scan['metadata']['recording_manifest_path']).parent;payload=(root/'manifest.json').read_bytes();assert 'sha256:'+hashlib.sha256(payload).hexdigest()==scan['metadata']['recording_manifest_file_sha256'];manifest=json.loads(payload)['manifest'];rows=[]
        for visit in scan['selected']:
            windows=[r for r in selected if r['visit']==visit['visit']]
            if not windows:continue
            chunk=manifest['chunks'][visit['visit']];buf=zstandard.ZstdDecompressor().decompress((root/chunk['relative_path']).read_bytes(),max_output_size=chunk['uncompressed_bytes']);assert 'sha256:'+hashlib.sha256(buf).hexdigest()==chunk['uncompressed_sha256'];a=np.frombuffer(buf,dtype='<i2').reshape(-1,2,2);iq=a[...,0].astype(float)+1j*a[...,1].astype(float)
            for previous in windows:
                start=previous['start_ms']*10000;designs,controls=build(visit,old,previous['start_ms']);new=extract(designs,controls,iq[start:start+70000],shared_frequency=True)
                assert new['both_qualified'] and new['metrics']==previous['metrics']
                rows.append(dict(visit=visit['visit'],start_ms=previous['start_ms'],independent=previous,shared=new))
        out.append(dict(session_id=sid,rows=rows));print(sid,'replayed',len(rows),flush=True)
        (OUT/'results.json').write_text(json.dumps(dict(protocol=protocol,scans=out),indent=2)+'\n')

if __name__=='__main__':main()
