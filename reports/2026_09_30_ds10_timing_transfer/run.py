import hashlib
import importlib.util
import json
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'2026_09_29_ds10_geographic'


def read(path):
    return json.loads(path.read_text())


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def main():
    started=time.monotonic()
    plan_path=SOURCE/'plan.json'
    fit_path=SOURCE/'fits/N24_h0/result.json'
    plan,baseline=read(plan_path),read(fit_path)
    hashes={}
    for obj in [plan,baseline]:
        for name,digest in obj['hashes'].items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
            hashes[name]=digest
    assert baseline['selected']['qualified']
    sessions=plan['panels']['N24']
    assert baseline['sessions']==sessions and len(sessions)==24
    by_id={r['session_id']:r for r in plan['captures']}
    inputs=[]
    for sid in sessions:
        p=SOURCE/'exports'/by_id[sid]['unit_id']/'validated.json'
        inputs.append(read(p)['input'])
    budget=module('budget',HERE.parent/'2026_09_29_scan_budget/run.py')
    helper=budget.helper
    docs=helper.baseline.load_documents(dict(config=plan['config'],inputs=inputs))
    grid=np.linspace(-5,5,401)
    x=baseline['selected']['x']
    rows=[]
    folder=HERE/'scans'
    folder.mkdir(exist_ok=True)
    for i,doc in enumerate(docs):
        assert doc['session_id']==sessions[i]
        model=helper.TrendMixturePosition([doc],plan['config'],helper.baseline.Stationary,.2)
        def score(t):
            return model.evaluate([*x[:2],t],gradient=False)['score']
        old=model.evaluate([*x[:2],x[i+2]],gradient=False,held=True)
        scores,_=budget.training_scores(model,x[:2],grid)
        best_grid=int(np.argmax(scores))
        assert abs(scores[best_grid]-score(grid[best_grid]))<1e-7
        indices=[j for j in range(len(grid)) if (j==0 or scores[j]>scores[j-1]) and (j==len(grid)-1 or scores[j]>scores[j+1])]
        peaks=[]
        for j in indices:
            bounds=(grid[max(0,j-1)],grid[min(len(grid)-1,j+1)])
            fit=minimize_scalar(lambda t:-score(t),bounds=bounds,method='bounded',options=dict(xatol=1e-10,maxiter=100))
            out=model.evaluate([*x[:2],fit.x],held=True)
            gradient=float(out['gradient'][2])
            numerical=(score(fit.x+1e-5)-score(fit.x-1e-5))/2e-5
            audit=abs(numerical-gradient)
            qualified=bool(fit.success and abs(fit.x)<4.999 and abs(gradient)<=.01 and audit<=.02 and out['score']>=scores[j]-1e-7)
            peaks.append(dict(tau_s=float(fit.x),score=out['score'],held=sum(r['held_log_score'] for r in out['rows']),
                              qualified=qualified,success=bool(fit.success),message=str(fit.message),gradient=gradient,gradient_audit=audit,grid_index=j))
        inherited=dict(tau_s=x[i+2],score=old['score'],held=sum(r['held_log_score'] for r in old['rows']),source='baseline')
        selected=max([inherited]+[dict(p,source='scalar') for p in peaks if p['qualified']],key=lambda p:p['score'])
        row=dict(session_id=sessions[i],inherited=inherited,selected=selected,peaks=peaks,grid_scores=scores.tolist(),
                 training_gain=selected['score']-inherited['score'],held_gain=selected['held']-inherited['held'])
        with (folder/f'{sessions[i]}.json').open('x') as out:
            json.dump(row,out,indent=2,allow_nan=False)
        rows.append(row)
        print(i+1,len(peaks),row['training_gain'],flush=True)
    assert abs(sum(r['inherited']['score'] for r in rows)-baseline['selected']['score'])<1e-7
    assert abs(sum(r['inherited']['held'] for r in rows)-baseline['selected']['held_score'])<1e-7
    gain=sum(r['training_gain'] for r in rows)
    for p in [plan_path,fit_path,HERE/'run.py',HERE/'PROTOCOL.md',HERE.parent/'2026_09_29_marginal_timing_fit/timing_model.py']:
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(rows=rows,grid_s=grid.tolist(),training_gain=gain,held_gain=sum(r['held_gain'] for r in rows),
                joint_refit_triggered=gain>.01,initial=x[:2]+[r['selected']['tau_s'] for r in rows],
                hashes=hashes,elapsed_seconds=time.monotonic()-started)
    with (HERE/'results.json').open('x') as out:
        json.dump(result,out,indent=2,allow_nan=False)
    print('Complete',result['training_gain'],result['held_gain'],result['joint_refit_triggered'],result['elapsed_seconds'])


if __name__=='__main__':
    main()
