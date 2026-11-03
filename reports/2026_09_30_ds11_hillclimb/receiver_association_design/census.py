"""DS11 paired detector opportunities; no source identity or position inference."""
import hashlib
import inspect
import json
from collections import Counter,defaultdict
from pathlib import Path
HERE=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def classify(probes):
    if len(probes)!=2 or {p['rx'] for p in probes}!={0,1}:return 'unknown'
    a,b=sorted(probes,key=lambda p:p['rx'])
    if any(a[k]!=b[k] for k in ('rf','counter','offset')):return 'unknown'
    return ('neither','rx1_only','rx0_only','both')[2*bool(a['passing'])+bool(b['passing'])]
def main():
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    plan_path=HERE.parents[1]/'2026_09_30_ds11_single10/plan.json';plan=json.loads(plan_path.read_text())
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'));rows=[];sources={str(plan_path):digest(plan_path)}
    try:
        for index in (0,16):
            entry=plan['inputs'][index];raw=store.load(entry['session_id'])
            assert raw.input_manifest_sha256==entry['manifest_sha256'] and raw.qualified and raw.timing.qualified
            groups=defaultdict(list)
            for p in raw.probes:
                groups[(p.visit_index,p.probe_index,p.probe_start_ms)].append(dict(rx=p.receiver_id,rf=p.actual_rf_hz,
                    counter=p.valid_start_counter,offset=p.probe_start_ms,passing=sum(c.passed_fractional_margin_gate for c in p.candidates)))
            opportunities=[dict(visit=key[0],probe=key[1],offset_ms=key[2],state=classify(values),views=values) for key,values in sorted(groups.items())]
            rows.append(dict(index=index,session_id=entry['session_id'],manifest_sha256=raw.input_manifest_sha256,
                analysis_manifest_sha256=raw.analysis_manifest_sha256,probe_ms=raw.probe_ms,
                counts=dict(Counter(o['state'] for o in opportunities)),opportunities=opportunities))
    finally:store.close()
    for p in (Path(__file__),HERE/'test_census.py',Path(inspect.getfile(ScannerTrackingInputStore))):sources[str(p)]=digest(p)
    result=dict(rows=rows,sources=sources,source_identity_assigned=False,position_fits=0,
                interpretation='any passing candidate per receiver; both does not establish the same source')
    with (HERE/'census.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps([{k:v for k,v in r.items() if k!='opportunities'} for r in rows],indent=2))
if __name__=='__main__':main()
