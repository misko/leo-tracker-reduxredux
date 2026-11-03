import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
import numpy as np
from exclusive import Exclusive

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent


def read(p):return json.loads(p.read_text())


def main(ds):
    started=time.monotonic()
    for name,h in read(HERE/'manifest.json')['hashes'].items():
        assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h,name
    spec=importlib.util.spec_from_file_location('receiver',REPORTS/'2026_09_29_receiver_holdout/run.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    plan=read(REPORTS/'2026_09_29_source_consistent_n8/manifest.json')
    items=[s for s in plan['scans'] if s['real_dataset']==ds]
    docs=helper.baseline.load_documents(dict(config=plan['config'],inputs=[s['input'] for s in items]))
    groups=[]
    for d,item in zip(docs,items,strict=True):
        q=read(Path(item['quality_path']));gg=[]
        for track in d['tracks']:
            points=sorted([r for r in q['rows'] if r['track_id']==track['track_id']],key=lambda r:r['index'])
            assert len(points)==len(track['y']) and [r['training'] for r in points]==track['mask'].tolist()
            g=[r['source_group_id'] for r in points];assert len(g)==len(set(g));gg.append(g)
        groups.append(gg)
    original=helper.TrendMixturePosition(docs,plan['config'],helper.baseline.Stationary,.2)
    model=Exclusive(original,groups)
    control=read(REPORTS/f'2026_09_29_source_consistent_n8/{ds}.fit.json')
    allfit,hardfit=control['baseline'],control['selected']
    assert allfit['qualified'] and hardfit['qualified']
    independent=Exclusive(original,[[[str(i)] for i in range(len(d['tracks']))] for d in docs])
    a=original.evaluate(allfit['x'],held=True);b=independent.evaluate(allfit['x'],held=True)
    audit=dict(score=abs(a['score']-b['score']),gradient=float(np.max(np.abs(a['gradient']-b['gradient']))),held=abs(sum(r['held_log_score'] for r in a['rows'])-b['held_log_score']))
    assert max(audit.values())<1e-7
    starts=[]
    for label,x in [('all_track',allfit['x']),('hard_consistent',hardfit['x'])]:
        try:
            fit=dict(helper.fit_model(model,x),start=label)
        except (ValueError,AssertionError) as exc:
            fit=dict(qualified=False,start=label,exception=repr(exc))
        starts.append(fit)
    valid=[s for s in starts if s['qualified']];best=max(valid,key=lambda s:s['score']) if valid else None
    result=dict(dataset=ds,starts=starts,selected=best,baseline=allfit,hard_consistent=hardfit,no_conflict_audit=audit,tracks=sum(len(d['tracks']) for d in docs),edges=sum(g.edges for g in model.graphs),component_sizes=[len(ids) for g in model.graphs for ids,_ in g.components])
    if best:
        best['estimate_deg']=list(model.models[0].coordinates(best['x'][:3]))
        scores={}
        for arm,x in [('old',allfit['x']),('new',best['x'])]:
            old=original.evaluate(x,gradient=False,held=True);new=model.evaluate(x,gradient=False,held=True)
            scores[arm]=dict(original=dict(training=old['score'],held=sum(r['held_log_score'] for r in old['rows'])),exclusive=dict(training=new['score'],held=new['held_log_score'],expected_active_tracks=new['expected_active_tracks']))
        result['scores']=scores
    result['elapsed_seconds']=time.monotonic()-started
    with (HERE/f'{ds}.json').open('x') as out:
        json.dump(result,out,indent=2,allow_nan=False)
    print(ds,best is not None,result['elapsed_seconds'],flush=True)


if __name__=='__main__':main(sys.argv[1])
