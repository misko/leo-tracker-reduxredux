import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
from dedup import deduplicate

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent


def read(p):
    return json.loads(p.read_text())


def main(ds):
    started=time.monotonic()
    for name,h in read(HERE/'manifest.json')['hashes'].items():
        assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h,name
    spec=importlib.util.spec_from_file_location('receiver',REPORTS/'2026_09_29_receiver_holdout/run.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    manifest=read(REPORTS/'2026_09_29_scan_budget/manifest.json')
    pool=next(s for s in manifest['sets'] if s['dataset']==ds and s['count']==24)
    docs=helper.baseline.load_documents(dict(config=manifest['config'],inputs=[s['input'] for s in pool['scans']]))
    prior=read(REPORTS/f'2026_09_29_scan_budget/{ds}_n24_0.json')
    assert prior['selected']['qualified'] and prior['sessions']==[d['session_id'] for d in docs]
    transformed,removals=[],[]
    for d in docs:
        dd,rr=deduplicate(d);transformed.append(dd)
        removals.extend(dict(session_id=d['session_id'],**r) for r in rr)
    audit=read(REPORTS/f'2026_09_29_track_overlap_audit/{ds}.json')
    assert len(removals)==sum(s['excess_cross_track_copies'] for s in audit['scans'])
    expected_train=sum(any(u[1] for u in x['uses']) for s in audit['scans'] for x in s['duplicates'])
    assert sum(r['training'] for r in removals)==expected_train
    def model(items):
        return helper.TrendMixturePosition(items,manifest['config'],helper.baseline.Stationary,.2)
    original,reduced=model(docs),model(transformed)
    x=prior['selected']['x']
    before=original.evaluate(x)
    assert abs(before['score']-prior['selected']['score'])<1e-7
    changed=reduced.evaluate(x)
    result=dict(dataset=ds,removals=removals,tracks=sum(len(d['tracks']) for d in docs),original=prior['selected'],original_score_replay=abs(before['score']-prior['selected']['score']),gradient_change_at_original=(changed['gradient']-before['gradient']).tolist(),deduplicated_score_at_original=changed['score'])
    fit=helper.fit_model(reduced,x)
    result['fit']=fit
    if fit['qualified']:
        fit['estimate_deg']=list(reduced.models[0].coordinates(fit['x'][:3]))
        scores={}
        for support,engine in [('original',original),('deduplicated',reduced)]:
            scores[support]={}
            for arm,z in [('old',x),('new',fit['x'])]:
                out=engine.evaluate(z,gradient=False,held=True)
                scores[support][arm]=dict(training=out['score'],held=sum(r['held_log_score'] for r in out['rows']))
        result['scores']=scores
        result['position_shift_m']=float(np.linalg.norm(np.array(fit['x'][:2])-np.array(x[:2]))*1000)
    result['elapsed_seconds']=time.monotonic()-started
    with (HERE/f'{ds}.json').open('x') as out:
        json.dump(result,out,indent=2,allow_nan=False)
    print(ds,fit['qualified'],result.get('position_shift_m'),flush=True)


if __name__=='__main__':
    main(sys.argv[1])
