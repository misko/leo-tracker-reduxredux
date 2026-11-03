"""Verify seed provenance and original-objective replacement decisions."""
import hashlib
import json
import math
from pathlib import Path
HERE=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text())
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    plan=read(HERE/'plan.json');s=read(HERE/'selections.json');outcome=read(HERE/'outcome.json')
    for p,h in plan['sources'].items():assert digest(p)==h
    assert s['plan_sha256']==outcome['plan_sha256']==digest(HERE/'plan.json')
    assert outcome['selection_sha256']==digest(HERE/'selections.json')
    original=read(HERE.parent/'cross_band_rx_position/selections.json');expected=[]
    for i,a in enumerate(original['attempts']):
        if not a['result'] or not a['result']['endpoint']['qualified']:continue
        x=a['result']['endpoint']['x'];index=a['job']['index']
        duplicate=any(j['index']==index and math.hypot(j['seed'][0]-x[0],j['seed'][1]-x[1])<=.001 and abs(j['seed'][2]-x[2])<=.001 for j in expected)
        if not duplicate:expected.append(dict(index=index,seed=x,parent_job=i))
    assert expected==plan['jobs']
    qualified=0
    for i,(job,a) in enumerate(zip(plan['jobs'],s['attempts'],strict=True)):
        receipt=read(HERE/f'runs/{i:02d}.receipt.json')
        assert receipt==a['receipt'] and receipt['job_index']==i and receipt['plan_sha256']==digest(HERE/'plan.json')
        assert job==a['job']
        if receipt['exit_code']==0:
            result=read(HERE/f'runs/{i:02d}.json');assert result==a['result'] and result['job']==job
            e=result['endpoint'];q=e['success'] and not e['boundary'] and e['gradient_max_abs']<=.01 and e['audit_max_abs']<=.02
            assert q==e['qualified'];qualified+=q
        else:assert a['result'] is None
    max_gain=0.
    for index,scan in plan['scans'].items():
        best=scan['control'];replacement=False
        for a in s['attempts']:
            if str(a['job']['index'])!=index or not a['result']:continue
            e=a['result']['endpoint']
            if e['qualified'] and e['score']>best['score']+1e-6:best=e;replacement=True
        chosen=s['selected'][index]
        assert chosen['endpoint']==best and chosen['replacement']==replacement
        assert abs(chosen['score_gain']-(best['score']-scan['control']['score']))<1e-9
        max_gain=max(max_gain,chosen['score_gain'])
        row=next(r for r in outcome['rows'] if str(r['index'])==index)
        if not replacement:assert row['baseline_error_m']==row['selected_error_m']
    result=dict(verification_pass=True,qualified_starts=qualified,total_starts=len(expected),
                maximum_selected_score_gain=max_gain,replacements=outcome['replacements'],
                independently_replays_optimizer=False,
                sources={str(p):digest(p) for p in (Path(__file__),HERE/'plan.json',HERE/'selections.json',HERE/'outcome.json')})
    with (HERE/'verification.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
