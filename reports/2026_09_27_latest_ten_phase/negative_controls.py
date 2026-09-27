"""Misalignment controls on one already-qualified real window per scan."""
from pathlib import Path
import json
import numpy as np
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from phase import designs_for,extract

HERE=Path(__file__).resolve().parent

def main():
    plan=json.loads((HERE/'plan.json').read_text());store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True);rows=[]
    for scan in plan['scans']:
        sid=scan['session_id'];data=json.loads((HERE/(sid+'.json')).read_text());row=next((r for r in data['rows'] if r['both_qualified']),None)
        if row is None:rows.append(dict(session_id=sid,reason='No qualified two-mode window'));continue
        v=next(v for v in scan['selected'] if v['visit']==row['visit']);cap=store.inspect(sid);assert cap.manifest_sha256==scan['capture_digest'];_,raw=store.read_visit_ci16(cap,v['visit']);rate=scan['rate_hz'];start=round(row['start_ms']*rate/1000);n=round(.007*rate);raw=raw[start:start+n];iq=raw[...,0].astype(float)+1j*raw[...,1].astype(float);d,c=designs_for(v,rate,start,n,row['timing_offsets_samples'])
        baseline=extract(d,c,iq,rate);assert baseline['both_qualified'];arms=[]
        for actual,saved in zip(baseline['modes'],row['modes']):
            assert actual['qualified']==saved['qualified']
            assert abs(actual['evaluation']['phase_rad']-saved['evaluation']['phase_rad'])<1e-10
        for kind in ['rx1_shift_333us','rx1_sample_permutation']:
            altered=iq.copy()
            if kind=='rx1_shift_333us':altered[:,1]=np.roll(altered[:,1],round(rate/3000))
            else:altered[:,1]=altered[np.random.default_rng(2026092707).permutation(n),1]
            result=extract(d,c,altered,rate);arms.append(dict(kind=kind,result=result))
        rows.append(dict(session_id=sid,visit=v['visit'],start_ms=row['start_ms'],arms=arms));print(sid,[(a['kind'],a['result']['both_qualified']) for a in arms],flush=True)
    store.close();(HERE/'negative-controls.json').write_text(json.dumps(dict(protocol='Posthoc diagnostic selection: first qualified two-mode window per scan. Frozen original timing, frequencies and split. Controls disrupt RX1 sample alignment and are not calibrated population false-positive estimates.',rows=rows),indent=2)+'\n')

if __name__=='__main__':main()
