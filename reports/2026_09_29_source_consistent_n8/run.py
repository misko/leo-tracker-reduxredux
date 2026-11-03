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


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj)
    return obj


def main(ds):
    started=time.monotonic();plan=read(HERE/'manifest.json')
    for name,h in {**plan['hashes'],**read(HERE/'quality-seal.json')['hashes']}.items():
        assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h,name
    budget=module('budget',REPORTS/'2026_09_29_scan_budget/run.py');helper=budget.helper
    selector=module('selector',REPORTS/'2026_09_29_source_consistent_pilot/selection.py')
    items=[s for s in plan['scans'] if s['real_dataset']==ds]
    docs=helper.baseline.load_documents(dict(config=plan['config'],inputs=[s['input'] for s in items]))
    chosen,selections=[],[]
    for d,item in zip(docs,items,strict=True):
        q=read(Path(item['quality_path']));rows=[]
        for track in d['tracks']:
            points=sorted([r for r in q['rows'] if r['track_id']==track['track_id']],key=lambda r:r['index'])
            assert len(points)==len(track['y']) and [r['index'] for r in points]==list(range(len(points)))
            assert [r['training'] for r in points]==track['mask'].tolist()
            rows.append(dict(track_id=track['track_id'],groups=[r['source_group_id'] for r in points],training_count=int(track['mask'].sum())))
        selected=selector.select(rows);ids=set(selected['track_ids'])
        groups=[g for r in rows if r['track_id'] in ids for g in r['groups']]
        assert len(groups)==len(set(groups))
        dd=dict(d,tracks=[t for t in d['tracks'] if t['track_id'] in ids]);chosen.append(dd)
        selections.append(dict(session_id=d['session_id'],selection=selected,original_tracks=len(d['tracks']),retained_tracks=len(dd['tracks']),original_training=sum(int(t['mask'].sum()) for t in d['tracks']),retained_training=sum(int(t['mask'].sum()) for t in dd['tracks'])))
    def model(items):
        return helper.TrendMixturePosition(items,plan['config'],helper.baseline.Stationary,.2)
    old=read(REPORTS/f'2026_09_29_time_balanced_scans/grid_{ds}_balanced_0.json')
    assert old['sessions']==[d['session_id'] for d in docs] and old['selected']['qualified']
    assert abs(model(docs).evaluate(old['selected']['x'],gradient=False)['score']-old['selected']['score'])<1e-7
    train=model(chosen);singles=[model([d]) for d in chosen];grid=np.array(plan['config']['timing_grid_s']);starts=[]
    for family in ('cold','timing_grid'):
        for east in (-2.,0.,2.):
            x=np.zeros(10);x[0]=east
            if family=='timing_grid':
                for i,one in enumerate(singles):
                    scores,_=budget.training_scores(one,x[:2],grid);k=int(np.argmax(scores));x[i+2]=grid[k]
                    assert abs(scores[k]-one.evaluate([east,0.,grid[k]],gradient=False)['score'])<1e-7
            try:
                fit=dict(helper.fit_model(train,x),family=family,initial=x.tolist())
            except (ValueError,AssertionError) as exc:
                fit=dict(qualified=False,family=family,initial=x.tolist(),exception=repr(exc))
            starts.append(fit)
    valid=[s for s in starts if s['qualified']];best=max(valid,key=lambda s:s['score']) if valid else None
    result=dict(dataset=ds,selections=selections,starts=starts,selected=best,baseline=old['selected'])
    if best:
        best['estimate_deg']=list(train.models[0].coordinates(best['x'][:3]))
        matched={}
        for arm,x in [('all',old['selected']['x']),('consistent',best['x'])]:
            out=train.evaluate(x,gradient=False,held=True);matched[arm]=dict(training=out['score'],held=sum(r['held_log_score'] for r in out['rows']))
        result['matched_scores']=matched
    result['elapsed_seconds']=time.monotonic()-started
    with (HERE/f'{ds}.fit.json').open('x') as out:
        json.dump(result,out,indent=2,allow_nan=False)
    print(ds,best is not None,time.monotonic()-started,flush=True)


if __name__=='__main__':
    main(sys.argv[1])
