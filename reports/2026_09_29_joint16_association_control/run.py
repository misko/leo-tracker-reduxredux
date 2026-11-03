import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent


def read(p):
    return json.loads(p.read_text())


def main(ds):
    started=time.monotonic()
    for name,h in read(HERE/'manifest.json')['hashes'].items():
        assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h,name
    spec=importlib.util.spec_from_file_location('budget',REPORTS/'2026_09_29_scan_budget/run.py')
    budget=importlib.util.module_from_spec(spec);spec.loader.exec_module(budget)
    helper=budget.helper
    manifest=read(REPORTS/'2026_09_29_scan_budget/manifest.json')
    config=manifest['config']
    pool=next(s for s in manifest['sets'] if s['dataset']==ds and s['count']==24)
    docs=helper.baseline.load_documents(dict(config=config,inputs=[s['input'] for s in pool['scans']]))
    by_id={d['session_id']:d for d in docs}
    def model(items):
        return helper.TrendMixturePosition(items,config,helper.baseline.Stationary,.2)
    results=[]
    for donor,target in [('early','middle'),('early','late'),('middle','late')]:
        control=read(REPORTS/f'2026_09_29_disjoint_frozen_association/{ds}_{donor}_{target}.json')
        assert control['qualified']
        sessions=control['donor_sessions']+control['target_sessions']
        assert len(sessions)==len(set(sessions))==16
        subset=[by_id[s] for s in sessions]
        assert [d['start_utc_ns'] for d in subset]==sorted(d['start_utc_ns'] for d in subset)
        joint=model(subset)
        if (donor,target)==('early','middle'):
            prior=read(REPORTS/f'2026_09_29_temporal_forecast/{ds}.json')
            assert prior['source_sessions']==sessions
            selected=prior['arms']['cumulative']
            assert selected['qualified']
            assert abs(joint.evaluate(selected['x'],gradient=False)['score']-selected['score'])<1e-7
            starts=[]
            reused=True
        else:
            singles=[model([d]) for d in subset]
            grid=np.array(config['timing_grid_s'])
            starts=[]
            for family in ('cold','timing_grid'):
                for east in (-2.,0.,2.):
                    x=np.zeros(18);x[0]=east
                    if family=='timing_grid':
                        for i,one in enumerate(singles):
                            scores,_=budget.training_scores(one,x[:2],grid)
                            k=int(np.argmax(scores));x[i+2]=grid[k]
                            assert abs(scores[k]-one.evaluate([east,0.,grid[k]],gradient=False)['score'])<1e-7
                    try:
                        fit=dict(helper.fit_model(joint,x),family=family,initial=x.tolist())
                    except (ValueError,AssertionError) as exc:
                        fit=dict(qualified=False,family=family,initial=x.tolist(),exception=repr(exc))
                    starts.append(fit)
            valid=[s for s in starts if s['qualified']]
            selected=max(valid,key=lambda s:s['score']) if valid else None
            if selected:
                selected['estimate_deg']=list(joint.models[0].coordinates(selected['x'][:3]))
            reused=False
        result=dict(dataset=ds,donor=donor,target=target,sessions=sessions,reused=reused,starts=starts,selected=selected)
        if selected:
            target_model=model([by_id[s] for s in control['target_sessions']])
            timed=dict(zip(sessions,selected['x'][2:],strict=True))
            x=[*selected['x'][:2],*[timed[s] for s in control['target_sessions']]]
            out=target_model.evaluate(x,gradient=False,held=True)
            result.update(target_score=dict(training=out['score'],held=sum(r['held_log_score'] for r in out['rows'])),control_scores=control['scores'],control_estimates=dict(donor=control['donor_estimate_deg'],target=control['target_estimate_deg'],frozen=control['selected']['estimate_deg']))
            old=read(REPORTS/f'2026_09_29_time_balanced_scans/grid_{ds}_contiguous_{target}.json')
            replay=target_model.evaluate(old['selected']['x'],gradient=False,held=True)
            assert abs(replay['score']-control['scores']['target']['training'])<1e-7
            assert abs(sum(r['held_log_score'] for r in replay['rows'])-control['scores']['target']['held'])<1e-7
        with (HERE/f'{ds}_{donor}_{target}.json').open('x') as f:
            json.dump(result,f,indent=2,allow_nan=False)
        results.append(result)
    with (HERE/f'{ds}.json').open('x') as f:
        json.dump(dict(pairs=results,elapsed_seconds=time.monotonic()-started),f,indent=2,allow_nan=False)
    print(ds,time.monotonic()-started,flush=True)


if __name__=='__main__':
    main(sys.argv[1])
