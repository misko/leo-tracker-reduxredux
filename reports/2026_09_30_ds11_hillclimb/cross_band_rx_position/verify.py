"""Verify frozen corrections, receipts, selection and geographic aggregation."""
import ast
import hashlib
import json
import math
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
HILL=HERE.parent
def read(p):return json.loads(Path(p).read_text())
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def percentile(values,q):
    v=sorted(values);p=(len(v)-1)*q;i=int(p)
    return v[i]+(v[min(i+1,len(v)-1)]-v[i])*(p-i)
def main():
    plan=read(HERE/'plan.json');selection=read(HERE/'selections.json');outcome=read(HERE/'outcome.json')
    for p,h in plan['sources'].items():assert digest(p)==h
    assert selection['plan_sha256']==outcome['plan_sha256']==digest(HERE/'plan.json')
    assert outcome['selection_sha256']==digest(HERE/'selections.json')
    fixed=read(HILL/'cross_band_rx_fixed/outcome.json')
    corrections_checked=0
    for row in fixed['rows']:
        for arm,alpha in (('rx1_fixed',0.),('symmetric',.5),('rx0_fixed',1.)):
            expected={}
            for pair in row['corrections']:
                a,b=pair['tracks']
                expected[a]=[-alpha*v for v in pair['canonical_delta_rx1']]
                expected[b]=[(1-alpha)*v for v in pair['canonical_delta_rx0']]
            assert plan['scans'][str(row['index'])]['corrections'][arm]==expected
            corrections_checked+=sum(len(v) for v in expected.values())
    qualified=0;wall=[]
    for i,(job,attempt) in enumerate(zip(plan['jobs'],selection['attempts'],strict=True)):
        receipt=read(HERE/f'runs/{i:02d}.receipt.json')
        assert receipt==attempt['receipt'] and receipt['job_index']==i and receipt['plan_sha256']==digest(HERE/'plan.json')
        assert job==attempt['job'];wall.append(receipt['wall_s'])
        if receipt['exit_code']==0:
            result=read(HERE/f'runs/{i:02d}.json');assert result==attempt['result'] and result['job']==job
            e=result['endpoint']
            finite=all(math.isfinite(v) for v in e['x']+[e['score'],e['gradient_max_abs'],e['audit_max_abs']])
            boundary=any(min(x-lo,hi-x)<.001 for x,(lo,hi) in zip(e['x'],[(-12,12),(-12,12),(-5,5)]))
            q=e['success'] and finite and not boundary and e['gradient_max_abs']<=.01 and e['audit_max_abs']<=.02
            assert q==e['qualified'];qualified+=q
        else:assert attempt['result'] is None
    for index,arms in selection['selected'].items():
        for arm,selected in arms.items():
            candidates=[a['result']['endpoint'] for a in selection['attempts'] if str(a['job']['index'])==index and a['job']['arm']==arm and a['result'] and a['result']['endpoint']['qualified']]
            assert selected==(max(candidates,key=lambda e:e['score']) if candidates else None)
    tree=ast.parse((HILL/'harness.py').read_text())
    reference=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='REFERENCE' for t in n.targets))
    def distance(point):
        lat,lon=map(math.radians,point);a,b=map(math.radians,reference)
        h=math.sin((lat-a)/2)**2+math.cos(lat)*math.cos(a)*math.sin((lon-b)/2)**2
        return 2*6371008.8*math.asin(math.sqrt(max(0,min(1,h))))
    for row in outcome['rows']:
        index=str(row['index'])
        assert abs(distance(plan['scans'][index]['control']['estimate_deg'])-row['baseline_error_m'])<1e-8
        for arm,error in row['errors_m'].items():
            selected=selection['selected'][index][arm]
            assert (error is None)==(selected is None)
            if selected:assert abs(distance(selected['estimate_deg'])-error)<1e-8
    baseline=[r['baseline_error_m'] for r in outcome['rows']]
    for arm,summary in outcome['summary'].items():
        values=[r['errors_m'][arm] for r in outcome['rows']]
        assert summary['qualified']==sum(v is not None for v in values)
        if None in values:assert not summary['gate_pass'];continue
        assert abs(summary['median_m']-median(values))<1e-8
        assert abs(summary['mean_m']-math.fsum(values)/len(values))<1e-8
        assert abs(summary['p90_m']-percentile(values,.9))<1e-8
        wins=sum(a<b for a,b in zip(values,baseline));assert summary['wins']==wins
        assert summary['gate_pass']==(wins>=6 and median(values)<=.9*median(baseline))
    result=dict(verification_pass=True,qualified_starts=qualified,total_starts=len(plan['jobs']),
                maximum_worker_wall_s=max(wall),correction_values_checked=corrections_checked,
                independent_optimizer_replay=False,sources={str(p):digest(p) for p in (Path(__file__),HERE/'plan.json',HERE/'selections.json',HERE/'outcome.json')})
    write=HERE/'verification.json'
    with write.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
