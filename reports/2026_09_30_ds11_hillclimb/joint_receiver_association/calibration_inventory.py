"""Find pre-DS11 numerical calibration inputs without inspecting accuracy."""
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPORTS=HERE.parents[1]
def read(p):return json.loads(Path(p).read_text())
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    ds10path=REPORTS/'2026_09_30_ds10_scale_weighting/plan.json';ds10=read(ds10path)
    ds11path=REPORTS/'2026_09_30_ds11_single10/plan.json';ds11=read(ds11path)
    manifestpath=REPORTS/'2026_09_29_ds10_post_ds9/local/manifest.json';manifest=read(manifestpath)
    captures={r['session_id']:r for r in manifest['captures']};sources={str(p):digest(p) for p in (ds10path,ds11path,manifestpath,Path(__file__))}
    targets=[]
    for index in (0,16):
        entry=ds11['inputs'][index];artifact=next(a for a in entry['artifacts'] if a['kind']=='observations')
        assert digest(artifact['path'])==artifact['sha256'].removeprefix('sha256:')
        d=read(artifact['path']);sources[artifact['path']]=digest(artifact['path'])
        targets.append(dict(index=index,session_id=entry['session_id'],sample_rate_hz=d['sample_rate_hz'],
                            rf_hz=sorted({t['rf_hz'] for t in d['tracks']}),start_utc_ns=d['start_utc_ns']))
    assert targets[0]['sample_rate_hz']==targets[1]['sample_rate_hz'] and targets[0]['rf_hz']==targets[1]['rf_hz']
    target=targets[0];cutoff=min(t['start_utc_ns'] for t in targets);eligible=[];excluded=[]
    for i,entry in enumerate(ds10['inputs']):
        for a in entry['artifacts']:
            assert digest(a['path'])==a['sha256'].removeprefix('sha256:');sources[a['path']]=digest(a['path'])
        d=read(next(a['path'] for a in entry['artifacts'] if a['kind']=='observations'));capture=captures[entry['session_id']]
        reasons=[]
        if d['sample_rate_hz']!=target['sample_rate_hz']:reasons.append('sample_rate')
        if sorted({t['rf_hz'] for t in d['tracks']})!=target['rf_hz']:reasons.append('exact_rf_set')
        if capture['capture_end_utc_ns']>=cutoff or capture['finalized_utc_ns']>=cutoff:reasons.append('not_available_before_first_target')
        if capture['radio_id']!='radio_pluto_5d4d':reasons.append('radio')
        row=dict(index=i,session_id=entry['session_id'],reasons=reasons,input=entry,capture_end_utc_ns=capture['capture_end_utc_ns'])
        (excluded if reasons else eligible).append(row)
    result=dict(targets=targets,eligible=eligible,excluded=excluded,sources=sources,
                scope='24 existing DS10 numerical exports; not all 187 DS10 captures',
                measured_beam_calibration=False,reference_error_used=False,
                availability_limit='capture completion checked; historical beam-model publication is not claimed')
    with (HERE/'calibration-inventory.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(dict(eligible=[dict(index=e['index'],session_id=e['session_id']) for e in eligible],excluded=len(excluded)),indent=2))
if __name__=='__main__':main()
