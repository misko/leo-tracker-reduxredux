"""Matched final convergence pass for smooth visibility; no new models or starts.

All 320 cases offered 30 s SLSQP then 20 s Fisher; stop on KKT <= 0.001.
Preserve previous files and select strictly by each model's objective, not truth.
"""
import argparse
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path

import numpy as np
import position_visibility_study as s

BUDGET=dict(slsqp_s=30.,fisher_s=20.)


def run(task):
    scan,arm,gate,weighting=task
    source=s.OUT/'final'/s.name(scan,arm,gate,weighting)
    target=s.OUT/'polished'/source.name
    if target.exists():
        r=json.loads(target.read_text())
        assert r['continuation']['source_sha256']==s.old.previous.digest(source)
        assert r['continuation']['implementation_sha256']==s.old.previous.digest(Path(__file__))
        return
    data,saved,*_=s.inputs(scan);obj=s.objective(data,saved,arm,gate,weighting)
    r=json.loads(source.read_text());records=r['records']
    for algorithm in ('slsqp','fisher'):
        best=s.old.previous.best_record(records)
        if s.metrics(obj,data,best)['converged']:break
        if algorithm=='slsqp':new=s.old.slsqp_fit(obj,best,BUDGET['slsqp_s'])
        else:new=s.old.fitted(obj,best,'matched-continuation',BUDGET['fisher_s'])
        records.append(new)
    best=s.old.previous.best_record(records)
    assert best['objective']<=r['objective']+1e-7
    ref=s.objective(data,saved,arm,'H',weighting)
    common=s.old.metrics(ref,data,s.old.reprice(ref,best,arm,'common-reference'))
    r.update(best=best,**s.metrics(obj,data,best),common_hard_data_nll=common['data_nll'],
        continuation=dict(source_sha256=s.old.previous.digest(source),
            implementation_sha256=s.old.previous.digest(Path(__file__)),maximum_budgets_s=BUDGET))
    s.old.previous.save(target,r)
    print('POLISHED',scan,arm,weighting,gate,round(r['distance_m']),'m','KKT',round(r['kkt'],6),flush=True)


def collect():
    previous=s.collect();rows=[]
    for old in previous:
        source=s.OUT/'final'/s.name(old['scan'],old['arm'],old['gate'],old['weighting'])
        r=json.loads((s.OUT/'polished'/source.name).read_text())
        assert r['continuation']==dict(source_sha256=s.old.previous.digest(source),
            implementation_sha256=s.old.previous.digest(Path(__file__)),maximum_budgets_s=BUDGET)
        for k in ('dependencies','seed_sources','cross_sources','input_sha256','spec','numbers','weights',
                  'roof','maximum_budgets_s','fit_original_rows','evaluation_original_rows','heldout_original_rows'):
            assert r[k]==old[k]
        data,saved,*_=s.inputs(r['scan']);obj=s.objective(data,saved,r['arm'],r['gate'],r['weighting'])
        for k,v in s.metrics(obj,data,r['best']).items():np.testing.assert_allclose(v,r[k],atol=1e-6,rtol=0)
        v=np.asarray(r['best']['vector'])
        assert np.linalg.norm(r['best']['point_km'])<=4.+1e-7
        assert abs(v[6])<=10.+1e-7 and max(abs(np.asarray(r['best']['parameters'])[6:]))<=20.+1e-7
        for x,(lo,hi) in zip(v,obj.bounds):
            assert (lo is None or x>=lo-1e-7) and (hi is None or x<=hi+1e-7)
        assert r['objective']<=old['objective']+1e-7
        assert r['objective']<=min(z['objective'] for z in r['records'])+1e-7
        rows.append(r)
    return rows


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workers',type=int,default=12)
    args=p.parse_args()
    jobs=[(scan,a,g,w) for scan in s.SCANS for w in s.WEIGHTS for g in s.GATES for a in s.ARMS]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for f in as_completed([pool.submit(run,j) for j in jobs]):f.result()
