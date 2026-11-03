import importlib.util
import hashlib
import json
import sys
import time
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent


def main(ds):
    started=time.monotonic()
    plan=json.loads((HERE/'plan.json').read_text())
    for name,h in plan['hashes'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
    spec=importlib.util.spec_from_file_location('budget',HERE.parent/'2026_09_29_scan_budget/run.py')
    budget=importlib.util.module_from_spec(spec);spec.loader.exec_module(budget);helper=budget.helper
    unit=next(s for s in plan['sets'] if s['dataset']==ds)
    docs=helper.baseline.load_documents(dict(config=plan['config'],inputs=[s['input'] for s in unit['scans']]))
    def model(dd):return helper.TrendMixturePosition(dd,plan['config'],helper.baseline.Stationary,.2)
    m=model(docs);singles=[model([d]) for d in docs];grid=np.array(plan['config']['timing_grid_s']);starts=[]
    folder=HERE/ds;folder.mkdir(exist_ok=True)
    plan_hash=hashlib.sha256((HERE/'plan.json').read_bytes()).hexdigest()
    for family in ['cold','timing_grid']:
        for east in [-2.,0.,2.]:
            path=folder/f'{family}_{int(east)}.json'
            if path.exists():
                previous=json.loads(path.read_text());assert previous['plan_sha256']==plan_hash
                starts.append(previous['fit']);continue
            x=np.zeros(26);x[0]=east
            if family=='timing_grid':
                for i,one in enumerate(singles):
                    scores,_=budget.training_scores(one,x[:2],grid);x[i+2]=grid[int(np.argmax(scores))]
            fit=dict(helper.fit_model(m,x),family=family,initial=x.tolist())
            with path.open('x') as out:json.dump(dict(fit=fit,plan_sha256=plan_hash),out,indent=2)
            starts.append(fit);print(ds,family,east,fit['qualified'],flush=True)
    valid=[s for s in starts if s['qualified']];best=dict(max(valid,key=lambda s:s['score'])) if valid else None
    if best:
        scored=m.evaluate(best['x'],gradient=False,held=True)
        best.update(estimate_deg=list(m.models[0].coordinates(best['x'][:3])),held_score=sum(r['held_log_score'] for r in scored['rows']))
    result=dict(dataset=ds,selected=best,starts=starts,sessions=[d['session_id'] for d in docs],tracks=sum(len(d['tracks']) for d in docs),observations=sum(len(t['y']) for d in docs for t in d['tracks']),plan_sha256=plan_hash,elapsed_seconds=time.monotonic()-started)
    with (folder/'result.json').open('x') as out:json.dump(result,out,indent=2,allow_nan=False)
    print('Complete',ds,best is not None,result['elapsed_seconds'],flush=True)


if __name__=='__main__':main(sys.argv[1])
