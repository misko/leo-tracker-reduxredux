import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def read(path):
    return json.loads(path.read_text())


def timing_fit(model, position, initial):
    def objective(tau):
        out = model.evaluate(np.r_[position, tau])
        return -out['score'], -out['gradient'][2:]
    fit = minimize(objective, initial, jac=True, method='L-BFGS-B', bounds=[(-5.,5.)]*len(initial), options=dict(maxiter=100,maxfun=160,ftol=1e-13,gtol=1e-6,maxls=25))
    x = np.r_[position,fit.x]
    errors = []
    for i in range(len(initial)):
        d = np.zeros_like(x);d[i+2]=1e-5
        numerical=(model.evaluate(x+d,gradient=False)['score']-model.evaluate(x-d,gradient=False)['score'])/2e-5
        errors.append(abs(numerical+fit.jac[i]))
    pg=float(np.max(np.abs(fit.jac)))
    boundary=bool(np.any(np.abs(fit.x)>4.999))
    return dict(x=x.tolist(),score=-float(fit.fun),success=bool(fit.success),message=str(fit.message),gradient_audit=max(errors),projected_gradient=pg,boundary=boundary,qualified=bool(fit.success and not boundary and pg<=.01 and max(errors)<=.02))


def main(ds):
    started=time.monotonic()
    for name,h in read(HERE/'manifest.json')['hashes'].items():
        assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h,name
    budget=module('budget',REPORTS/'2026_09_29_scan_budget/run.py')
    helper=budget.helper
    frozen_class=module('frozen_donor_model',REPORTS/'2026_09_29_frozen_association/frozen_model.py').FrozenAssociation
    manifest=read(REPORTS/'2026_09_29_scan_budget/manifest.json')
    config=manifest['config']
    pool=next(s for s in manifest['sets'] if s['dataset']==ds and s['count']==24)
    docs=helper.baseline.load_documents(dict(config=config,inputs=[s['input'] for s in pool['scans']]))
    by_id={d['session_id']:d for d in docs}
    panels={w:read(REPORTS/f'2026_09_29_time_balanced_scans/grid_{ds}_contiguous_{w}.json') for w in ('early','middle','late')}
    def model(items):
        return helper.TrendMixturePosition(items,config,helper.baseline.Stationary,.2)
    results=[]
    for donor_name,target_name in [('early','middle'),('early','late'),('middle','late')]:
        donor,target=panels[donor_name],panels[target_name]
        assert donor['selected']['qualified'] and target['selected']['qualified']
        assert not set(donor['sessions'])&set(target['sessions'])
        assert max(by_id[s]['start_utc_ns'] for s in donor['sessions'])+300_000_000_000 < min(by_id[s]['start_utc_ns'] for s in target['sessions'])
        subset=[by_id[s] for s in target['sessions']]
        original=model(subset)
        position=np.array(donor['selected']['x'][:2])
        grid=np.array(config['timing_grid_s'])
        initial=[]
        for d in subset:
            one=model([d]);scores,_=budget.training_scores(one,position,grid)
            k=int(np.argmax(scores));initial.append(grid[k])
            assert abs(scores[k]-one.evaluate([*position,grid[k]],gradient=False)['score'])<1e-7
        result=dict(dataset=ds,donor=donor_name,target=target_name,donor_sessions=donor['sessions'],target_sessions=target['sessions'],donor_estimate_deg=donor['selected']['estimate_deg'],target_estimate_deg=target['selected']['estimate_deg'])
        try:
            timed=timing_fit(original,position,initial)
            result['timing_fit']=timed
            if not timed['qualified']:
                raise ValueError('Fixed-position target timing did not qualify')
            frozen=frozen_class(original,timed['x'])
            a,b=original.evaluate(timed['x']),frozen.evaluate(timed['x'])
            audit=max(abs(a['score']-b['score']),float(np.max(np.abs(a['gradient']-b['gradient']))))
            assert audit<1e-7
            result['tangency_audit']=audit
            starts=[]
            for label,x in [('target',target['selected']['x']),('donor_position',timed['x'])]:
                try:
                    fit=dict(helper.fit_model(frozen,x),start=label)
                except (ValueError,AssertionError) as exc:
                    fit=dict(qualified=False,start=label,exception=repr(exc))
                starts.append(fit)
            result['starts']=starts
            valid=[s for s in starts if s['qualified']]
            selected=max(valid,key=lambda s:s['score']) if valid else None
            result['selected']=selected
            if selected is None:
                raise ValueError('No qualified constrained fit')
            selected['estimate_deg']=list(original.models[0].coordinates(selected['x'][:3]))
            scores={}
            for arm,x in [('target',target['selected']['x']),('donor_position',timed['x']),('frozen_fit',selected['x'])]:
                out=original.evaluate(x,gradient=False,held=True)
                scores[arm]=dict(training=out['score'],held=sum(r['held_log_score'] for r in out['rows']))
            assert selected['score']<=scores['frozen_fit']['training']+1e-7
            result.update(scores=scores,qualified=True)
        except (ValueError,AssertionError) as exc:
            result.update(qualified=False,exception=repr(exc))
        results.append(result)
        with (HERE/f'{ds}_{donor_name}_{target_name}.json').open('x') as out:
            json.dump(result,out,indent=2,allow_nan=False)
    with (HERE/f'{ds}.json').open('x') as out:
        json.dump(dict(pairs=results,elapsed_seconds=time.monotonic()-started),out,indent=2,allow_nan=False)
    print(ds,time.monotonic()-started,flush=True)


if __name__=='__main__':
    main(sys.argv[1])
