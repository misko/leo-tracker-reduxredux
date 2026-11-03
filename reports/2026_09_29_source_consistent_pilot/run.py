import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
from selection import select

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
    quality=read(REPORTS/f'2026_09_29_quality_metadata_corrected/{ds}.json')
    pool=next(s for s in manifest['sets'] if s['dataset']==ds and s['count']==24)
    source=next(s for s in pool['scans'] if s['session_id']==quality['session_id'])
    config=manifest['config']
    doc=helper.baseline.load_documents(dict(config=config,inputs=[source['input']]))[0]
    rows=[]
    for track in doc['tracks']:
        q=sorted([r for r in quality['rows'] if r['track_id']==track['track_id']],key=lambda r:r['index'])
        assert len(q)==len(track['y']) and [r['index'] for r in q]==list(range(len(q)))
        assert [r['training'] for r in q]==track['mask'].tolist()
        rows.append(dict(track_id=track['track_id'],groups=[r['source_group_id'] for r in q],training_count=int(track['mask'].sum())))
    selection=select(rows)
    ids=set(selection['track_ids'])
    chosen=dict(doc,tracks=[t for t in doc['tracks'] if t['track_id'] in ids])
    groups=[g for r in rows if r['track_id'] in ids for g in r['groups']]
    assert len(groups)==len(set(groups))
    def model(d):
        return helper.TrendMixturePosition([d],config,helper.baseline.Stationary,.2)
    engines={'all':model(doc),'consistent':model(chosen)}
    arms={}
    for name,engine in engines.items():
        starts=[]
        for family in ('cold','timing_grid'):
            for east in (-2.,0.,2.):
                x=np.array([east,0.,0.])
                if family=='timing_grid':
                    grid=np.array(config['timing_grid_s']);scores,_=budget.training_scores(engine,x[:2],grid)
                    k=int(np.argmax(scores));x[2]=grid[k]
                    assert abs(scores[k]-engine.evaluate(x,gradient=False)['score'])<1e-7
                try:
                    fit=dict(helper.fit_model(engine,x),family=family,initial=x.tolist())
                except (ValueError,AssertionError) as exc:
                    fit=dict(qualified=False,family=family,initial=x.tolist(),exception=repr(exc))
                starts.append(fit)
        valid=[s for s in starts if s['qualified']]
        best=max(valid,key=lambda s:s['score']) if valid else None
        if best:
            best['estimate_deg']=list(engine.models[0].coordinates(best['x']))
        arms[name]=dict(starts=starts,selected=best)
    result=dict(dataset=ds,session_id=doc['session_id'],selection=selection,original_tracks=len(doc['tracks']),retained_tracks=len(chosen['tracks']),original_training=sum(int(t['mask'].sum()) for t in doc['tracks']),retained_training=sum(int(t['mask'].sum()) for t in chosen['tracks']),original_observations=sum(len(t['y']) for t in doc['tracks']),retained_observations=sum(len(t['y']) for t in chosen['tracks']),arms=arms)
    if all(a['selected'] for a in arms.values()):
        matched={}
        for arm,a in arms.items():
            out=engines['consistent'].evaluate(a['selected']['x'],gradient=False,held=True)
            matched[arm]=dict(training=out['score'],held=sum(r['held_log_score'] for r in out['rows']))
        result['matched_selected_scores']=matched
    result['elapsed_seconds']=time.monotonic()-started
    with (HERE/f'{ds}.json').open('x') as out:
        json.dump(result,out,indent=2,allow_nan=False)
    print(ds,result['original_tracks'],result['retained_tracks'],{k:v['selected'] is not None for k,v in arms.items()},flush=True)


if __name__=='__main__':
    main(sys.argv[1])
