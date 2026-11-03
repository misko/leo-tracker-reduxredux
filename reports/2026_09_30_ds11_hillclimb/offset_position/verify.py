"""Verify marginalized-position source bindings, qualification and selection."""
import ast
import hashlib
import json
import math
from pathlib import Path
HERE=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text())
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    plan=read(HERE/'plan.json');selection=read(HERE/'selections.json');outcome=read(HERE/'outcome.json')
    for p,h in plan['sources'].items():assert digest(p)==h
    assert selection['plan_sha256']==outcome['plan_sha256']==digest(HERE/'plan.json')
    assert outcome['selection_sha256']==digest(HERE/'selections.json')
    qualified=0;wall=[];value_errors=[];gradient_errors=[]
    for i,(job,a) in enumerate(zip(plan['jobs'],selection['attempts'],strict=True)):
        receipt=read(HERE/f'runs/{i:02d}.receipt.json')
        assert receipt==a['receipt'] and job==a['job'] and receipt['job_index']==i
        assert receipt['plan_sha256']==digest(HERE/'plan.json');wall.append(receipt['wall_s'])
        if receipt['exit_code']!=0:assert a['result'] is None;continue
        r=read(HERE/f'runs/{i:02d}.json');assert r==a['result'] and r['job']==job and r['plan_sha256']==receipt['plan_sha256']
        e=r['endpoint'];boundary=any(min(x-lo,hi-x)<.001 for x,(lo,hi) in zip(e['x'],[(-12,12),(-12,12),(-5,5)]))
        finite=all(math.isfinite(v) for v in e['x']+[e['score'],e['gradient_max_abs'],e['audit_max_abs'],e['quadrature_value_error'],e['quadrature_gradient_error']])
        q=finite and e['success'] and not boundary and e['gradient_max_abs']<=.01 and e['audit_max_abs']<=.02 and e['quadrature_value_error']<1e-6 and e['quadrature_gradient_error']<1e-3
        assert e['boundary']==boundary and e['qualified']==q;qualified+=q
        value_errors.append(e['quadrature_value_error']);gradient_errors.append(e['quadrature_gradient_error'])
    for index,endpoint in selection['selected'].items():
        valid=[a['result']['endpoint'] for a in selection['attempts'] if str(a['job']['index'])==index and a['result'] and a['result']['endpoint']['qualified']]
        assert endpoint==(max(valid,key=lambda e:e['score']) if valid else None)
    tree=ast.parse((HERE.parent/'harness.py').read_text())
    reference=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='REFERENCE' for t in n.targets))
    def distance(point):
        a,b=map(math.radians,reference);lat,lon=map(math.radians,point)
        h=math.sin((a-lat)/2)**2+math.cos(a)*math.cos(lat)*math.sin((b-lon)/2)**2
        return 2*6371008.8*math.asin(math.sqrt(max(0,min(1,h))))
    for r in outcome['rows']:
        index=str(r['index']);e=selection['selected'][index]
        assert abs(distance(plan['scans'][index]['control']['estimate_deg'])-r['baseline_error_m'])<1e-8
        assert (r['marginal_error_m'] is None)==(e is None)
        if e:assert abs(distance(e['estimate_deg'])-r['marginal_error_m'])<1e-8
    assert outcome['gate_pass']==all(r['marginal_error_m'] is not None and r['marginal_error_m']<r['baseline_error_m'] for r in outcome['rows'])
    result=dict(verification_pass=True,qualified_starts=qualified,total_starts=len(plan['jobs']),maximum_worker_wall_s=max(wall),
                maximum_quadrature_value_error=max(value_errors) if value_errors else None,
                maximum_quadrature_gradient_error=max(gradient_errors) if gradient_errors else None,
                independent_optimizer_replay=False,sources={str(p):digest(p) for p in (Path(__file__),HERE/'plan.json',HERE/'selections.json',HERE/'outcome.json')})
    with (HERE/'verification.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
