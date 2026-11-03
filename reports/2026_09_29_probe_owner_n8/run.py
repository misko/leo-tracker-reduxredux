import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
import numpy as np
from ownership import resolve

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent


def read(p):return json.loads(p.read_text())


def main(ds):
    started=time.monotonic()
    for name,h in read(HERE/'manifest.json')['hashes'].items():
        assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h,name
    spec=importlib.util.spec_from_file_location('budget',REPORTS/'2026_09_29_scan_budget/run.py')
    budget=importlib.util.module_from_spec(spec);spec.loader.exec_module(budget);helper=budget.helper
    plan=read(REPORTS/'2026_09_29_source_consistent_n8/manifest.json');items=[s for s in plan['scans'] if s['real_dataset']==ds]
    docs=helper.baseline.load_documents(dict(config=plan['config'],inputs=[s['input'] for s in items]))
    kept=[];ledgers=[]
    for d,item in zip(docs,items,strict=True):
        dd,ledger=resolve(d,read(Path(item['quality_path']))['rows']);kept.append(dd)
        ledgers.append(dict(session_id=d['session_id'],original_tracks=len(d['tracks']),retained_tracks=len(dd['tracks']),original_training=sum(int(t['mask'].sum()) for t in d['tracks']),retained_training=sum(int(t['mask'].sum()) for t in dd['tracks']),original_observations=sum(len(t['y']) for t in d['tracks']),retained_observations=sum(len(t['y']) for t in dd['tracks']),**ledger))
    def model(items):return helper.TrendMixturePosition(items,plan['config'],helper.baseline.Stationary,.2)
    controls=read(REPORTS/f'2026_09_29_source_consistent_n8/{ds}.fit.json')
    old,hard=controls['baseline'],controls['selected'];assert old['qualified'] and hard['qualified']
    assert abs(model(docs).evaluate(old['x'],gradient=False)['score']-old['score'])<1e-7
    train=model(kept);singles=[model([d]) for d in kept];grid=np.array(plan['config']['timing_grid_s']);starts=[]
    for family in ('cold','timing_grid'):
        for east in (-2.,0.,2.):
            x=np.zeros(10);x[0]=east
            if family=='timing_grid':
                for i,one in enumerate(singles):
                    scores,_=budget.training_scores(one,x[:2],grid);k=int(np.argmax(scores));x[i+2]=grid[k]
                    assert abs(scores[k]-one.evaluate([east,0.,grid[k]],gradient=False)['score'])<1e-7
            try:fit=dict(helper.fit_model(train,x),family=family,initial=x.tolist())
            except (ValueError,AssertionError) as exc:fit=dict(qualified=False,family=family,initial=x.tolist(),exception=repr(exc))
            starts.append(fit)
    valid=[s for s in starts if s['qualified']];best=max(valid,key=lambda s:s['score']) if valid else None
    result=dict(dataset=ds,ledgers=ledgers,starts=starts,selected=best,baseline=old,hard=hard)
    if best:
        best['estimate_deg']=list(train.models[0].coordinates(best['x'][:3]));matched={}
        for arm,fit in [('all',old),('hard',hard),('owner',best)]:
            out=train.evaluate(fit['x'],gradient=False,held=True);matched[arm]=dict(training=out['score'],held=sum(r['held_log_score'] for r in out['rows']))
        result['matched_scores']=matched
    result['elapsed_seconds']=time.monotonic()-started
    with (HERE/f'{ds}.json').open('x') as out:json.dump(result,out,indent=2,allow_nan=False)
    print(ds,best is not None,result['elapsed_seconds'],flush=True)


if __name__=='__main__':main(sys.argv[1])
