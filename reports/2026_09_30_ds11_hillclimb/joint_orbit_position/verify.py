"""Independent receipt/selection/geometry audit; does not replay optimization."""
import hashlib
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
def read(path):return json.loads(path.read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def distance(point):
    lat,lon=map(math.radians,point);a,b=map(math.radians,(37.849056280893684,-122.48575489722863))
    half=math.sin((lat-a)/2)**2+math.cos(lat)*math.cos(a)*math.sin((lon-b)/2)**2
    return 2*6371008.8*math.atan2(math.sqrt(half),math.sqrt(1-half))

def main():
    plan=read(HERE/'plan.json');sealed=read(HERE/'selections.json');outcome=read(HERE/'outcome.json')
    ph=digest(HERE/'plan.json');assert sealed['plan_sha256']==outcome['plan_sha256']==ph
    assert outcome['selection_sha256']==digest(HERE/'selections.json')
    for path,h in plan['sources'].items():assert digest(Path(path))==h,path
    assert len(sealed['attempts'])==len(plan['jobs'])==12
    qualified=0
    for i,(job,attempt) in enumerate(zip(plan['jobs'],sealed['attempts'])):
        assert attempt['job']==job
        receipt=read(HERE/f'runs/{i:02d}.receipt.json');assert receipt==attempt['receipt']
        assert receipt['plan_sha256']==ph and receipt['job_index']==i
        if receipt['exit_code']!=0:
            assert attempt['result'] is None;continue
        result=read(HERE/f'runs/{i:02d}.json');assert result==attempt['result'] and result['plan_sha256']==ph
        e=result['endpoint'];bounds=[12,12,5]
        boundary=any(bounds[j]-abs(e['x'][j])<.001 for j in range(3))
        good=e['success'] and not boundary and e['gradient_max_abs']<=.01 and e['audit_max_abs']<=.02
        good=good and all(math.isfinite(v) for v in e['x']+[e['score'],e['gradient_max_abs'],e['audit_max_abs']])
        assert good==e['qualified'] and boundary==e['boundary'];qualified+=good
    max_error=0
    for row in outcome['rows']:
        index=str(row['index']);scan=plan['scans'][index]
        max_error=max(max_error,abs(distance(scan['control']['estimate_deg'])-row['errors_m']['iid']))
        for arm in ('zero','orbit','linear'):
            eligible=[a['result']['endpoint'] for a in sealed['attempts']
                      if a['job']['index']==int(index) and a['job']['arm']==arm and a['result'] and a['result']['endpoint']['qualified']]
            selected=max(eligible,key=lambda e:e['score']) if eligible else None
            assert selected==sealed['selected'][index][arm]
            if selected:max_error=max(max_error,abs(distance(selected['estimate_deg'])-row['errors_m'][arm]))
            else:assert row['errors_m'][arm] is None
    gate=all(all(r['errors_m'][a] is not None for a in ('zero','orbit','linear')) and
             all(r['errors_m']['orbit']<r['errors_m'][a] for a in ('iid','zero','linear')) for r in outcome['rows'])
    assert gate==outcome['gate_pass'] and max_error<1e-8
    result=dict(passed=True,qualified_starts=qualified,attempts=12,maximum_distance_discrepancy_m=max_error,
                optimization_replayed=False,plan_sha256=ph,outcome_sha256=digest(HERE/'outcome.json'),
                verifier_sha256=digest(Path(__file__)))
    with (HERE/'verification.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
