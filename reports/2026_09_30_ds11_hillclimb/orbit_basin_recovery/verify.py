"""Verify provenance and training selections independently of the runner."""
import hashlib
import json
import math
from pathlib import Path
HERE=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text())
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    plan=read(HERE/'plan.json');sealed=read(HERE/'selections.json');outcome=read(HERE/'outcome.json')
    ph=digest(HERE/'plan.json')
    for p,h in plan['sources'].items():assert digest(p)==h
    assert sealed['plan_sha256']==outcome['plan_sha256']==ph
    assert outcome['selection_sha256']==digest(HERE/'selections.json')
    expected=[]
    for i,a in enumerate(read(HERE.parent/'joint_orbit_position/selections.json')['attempts']):
        if not a['result'] or not a['result']['endpoint']['qualified']:continue
        x=a['result']['endpoint']['x'];index=a['job']['index']
        duplicate=any(j['index']==index and math.hypot(j['seed'][0]-x[0],j['seed'][1]-x[1])<=.001
                      and abs(j['seed'][2]-x[2])<=.001 for j in expected)
        if not duplicate:expected.append(dict(index=index,seed=x,parent_job=i))
    assert expected==plan['jobs'];qualified=0
    for i,(job,a) in enumerate(zip(expected,sealed['attempts'],strict=True)):
        receipt=read(HERE/f'runs/{i:02d}.receipt.json')
        assert receipt==a['receipt'] and receipt['job_index']==i and receipt['plan_sha256']==ph
        assert job==a['job']
        if receipt['exit_code']!=0:assert a['result'] is None;continue
        result=read(HERE/f'runs/{i:02d}.json');assert result==a['result'] and result['job']==job and result['plan_sha256']==ph
        e=result['endpoint'];boundary=any(b-abs(x)<.001 for b,x in zip((12,12,5),e['x']))
        finite=all(math.isfinite(v) for v in e['x']+[e['score'],e['gradient_max_abs'],e['audit_max_abs']])
        good=e['success'] and finite and not boundary and e['gradient_max_abs']<=.01 and e['audit_max_abs']<=.02
        assert good==e['qualified'] and boundary==e['boundary'];qualified+=good
    replacements=0
    for index,scan in plan['scans'].items():
        best=scan['control'];replacement=False
        for a in sealed['attempts']:
            if str(a['job']['index'])!=index or not a['result']:continue
            e=a['result']['endpoint']
            if e['qualified'] and e['score']>best['score']+1e-6:best=e;replacement=True
        chosen=sealed['selected'][index];assert chosen['endpoint']==best and chosen['replacement']==replacement
        assert abs(chosen['score_gain']-(best['score']-scan['control']['score']))<1e-9
        row=next(r for r in outcome['rows'] if str(r['index'])==index)
        if not replacement:assert row['baseline_error_m']==row['selected_error_m']
        replacements+=replacement
    assert replacements==outcome['replacements']
    result=dict(passed=True,attempts=len(expected),qualified=qualified,replacements=replacements,
                optimizer_replayed=False,plan_sha256=ph,outcome_sha256=digest(HERE/'outcome.json'),
                verifier_sha256=digest(Path(__file__)))
    with (HERE/'verification.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
