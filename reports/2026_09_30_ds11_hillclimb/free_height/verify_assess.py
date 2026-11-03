"""Verify frozen training selections, then read out geographic effects."""
import json
from pathlib import Path
import numpy as np
from run import read,write,digest,util,HERE,Model,fast,BOUNDS
def main():
    p=read(HERE/'plan.json');util.verify(p);s=read(HERE/'selections.json');o=read(HERE/'outcome.json')
    ph=digest(HERE/'plan.json');assert s['plan_sha256']==o['plan_sha256']==ph
    assert o['selection_sha256']==digest(HERE/'selections.json') and o['gate_pass']
    for i,(job,a) in enumerate(zip(p['jobs'],s['attempts'],strict=True)):
        receipt=read(HERE/f'runs/{i:02d}.receipt.json');assert receipt==a['receipt'] and receipt['plan_sha256']==ph
        assert job==a['job'] and receipt['job_index']==i
        if receipt['exit_code']!=0:assert a['result'] is None;continue
        r=read(HERE/f'runs/{i:02d}.json');assert r==a['result'] and r['plan_sha256']==ph
        boundary=any(min(x-lo,hi-x)<.001 for x,(lo,hi) in zip(r['x'],BOUNDS))
        good=r['success'] and not boundary and np.isfinite(r['x']).all() and np.isfinite(r['score']) and r['gradient_max_abs']<=.01 and r['audit_max_abs']<=.02
        assert good==r['qualified'] and boundary==r['boundary']
    _,_,harness,_=util.dependencies();rows=[]
    for index,scan in p['scans'].items():
        valid=[a['result'] for a in s['attempts'] if str(a['job']['index'])==index and a['result'] and a['result']['qualified']]
        best=max(valid,key=lambda r:r['score']);assert best==s['selected'][index]
        doc=fast.load_documents(dict(config=p['config'],inputs=[scan['input']]))[0];m=Model(doc,p['config'])
        base=m.evaluate(scan['control_x'],False);new=m.evaluate(best['x'],False)
        row=next(r for r in o['rows'] if str(r['index'])==index)
        assert abs(new['score']-best['score'])<1e-6 and abs(new['held']-base['held']-row['held_gain'])<1e-6
        rows.append(dict(index=int(index),height_m=row['height_m'],baseline_error_m=harness.distance(m.model.coordinates(scan['control_x'])),
                         free_height_error_m=harness.distance(m.model.coordinates(best['x']))))
    result=dict(rows=rows,geographic_gate_pass=all(r['free_height_error_m']<r['baseline_error_m'] for r in rows),
                verified_sources_receipts_qualification_selection_and_score_replay=True,optimizer_replayed=False,
                sources={str(path):digest(path) for path in (HERE/'plan.json',HERE/'selections.json',HERE/'outcome.json',
                  HERE/'GEOGRAPHIC_PROTOCOL.md',Path(__file__),HERE.parent/'harness.py')})
    write(HERE/'geographic.json',result);print(json.dumps({k:v for k,v in result.items() if k!='sources'},indent=2))
if __name__=='__main__':main()
