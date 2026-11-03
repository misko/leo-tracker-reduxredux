"""Hard horizon versus four smooth visibility models on all N01--N16 scans.

Independent 4 km searches, Gaussian 200 Hz residual kernel, ordinary/time-balanced
weights, matched fitted-c/c=0 arms. Full frozen associated top-one windows; no
new calibration, candidate selection, ephemerides, RF or held-out subsets.
Known-roof development cohort, not blind validation. Truth never selects fits.
"""
import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor,as_completed
from functools import lru_cache
from pathlib import Path

import numpy as np
import position_interaction_study as prior
from joint_inputs import FRAME_LATITUDE_DEG,FRAME_LONGITUDE_DEG
from soft_solvers import _parameter_map
from smooth_visibility_model import GATES,SmoothLikelihood,horizon_geometry

old=prior.old
HERE=Path(__file__).resolve().parent;OUT=HERE/'position-visibility-study'
SCANS=old.SCANS;ARMS=old.ARMS;WEIGHTS=('ordinary','time-balanced')
FRAME=(FRAME_LATITUDE_DEG,FRAME_LONGITUDE_DEG)
BUDGET=dict(roof_s=3.,search_starts=3,search_s=4.,initial_polish_s=8.,
            final_slsqp_s=20.,final_fisher_s=20.)


class Objective(old.Objective):
    def __init__(self,data,center,arm,gate,weighting):
        super().__init__(data,center,arm,'C1' if weighting=='ordinary' else 'A03')
        self.gate=gate;self.data=data;self.geometry=None;self.geometry_vector=None
        if gate!='H':
            self.likelihood=SmoothLikelihood(data,self.features,self.likelihood.weights,gate)
            self.base.likelihood=self.likelihood

    def get_geometry(self,vector):
        physical=self.base.state(np.asarray(vector[:self.size]))['parameters']
        relevant=np.r_[physical[:2],physical[6:]]
        if self.geometry_vector is None or not np.array_equal(relevant,self.geometry_vector):
            self.geometry=horizon_geometry(self.data,physical,FRAME)
            self.geometry_vector=relevant.copy()
        return self.geometry

    def evaluate(self,vector):
        if self.gate=='H':return super().evaluate(vector)
        self.base.check_deadline()
        if not self.base.state(np.asarray(vector[:self.size]))['ephemeris_valid']:
            return super().evaluate(vector)
        sine,jac=self.get_geometry(vector);self.likelihood.sine=sine
        value,gradient=super().evaluate(vector)
        physical=jac.transpose_multiply(-self.likelihood.last_result['elevation_gradient'].ravel())
        gradient[:self.size]+=self.base.vector_gradient(physical,np.asarray(vector[:self.size]))
        return value,gradient

    def curvature(self,vector):
        h=super().curvature(vector)
        if self.gate!='H':
            _,jac=self.get_geometry(vector);mapping=_parameter_map(self.base)
            extra=jac.normal_matrix(self.likelihood.last_result['elevation_precision'].ravel())
            h[:self.size,:self.size]+=mapping.T@extra@mapping
        return h


@lru_cache(maxsize=1)
def dependencies():
    paths=[Path(__file__),HERE/'smooth_visibility_model.py']
    import prediction_jacobian,prediction_plan
    paths += [Path(prediction_jacobian.__file__),Path(prediction_plan.__file__)]
    return dict(prior.dependencies(),**{str(p):old.previous.digest(p) for p in paths})


@lru_cache(maxsize=2)
def inputs(scan):
    data,saved,source,_,_=prior.inputs(scan)
    paths=[prior.OUT/'polished'/f'{scan}-{a}-{m}.json' for a in prior.ARMS for m in prior.MODES]
    pool=[json.loads(p.read_text()) for p in paths]
    assert all(r['input_sha256']==saved['input_sha256'] for r in pool)
    return data,saved,source,pool,{str(p):old.previous.digest(p) for p in paths}


def objective(data,saved,arm,gate,weighting):
    return Objective(data,saved['input_metadata']['rf_center_hz'],arm,gate,weighting)


def metrics(obj,data,best):
    result=old.metrics(obj,data,best)
    probabilities=obj.likelihood.last_result['row_association_probability'].copy()
    sine,_=obj.get_geometry(best['vector'])
    below=sine<0
    result.update(coefficient_hz_per_ghz=best['vector'][obj.size],
        below_horizon_expected_windows=float(probabilities[below].sum()),
        below_horizon_signal_fraction=float(probabilities[below].sum()/probabilities.sum()),
        below_horizon_strong_windows=int(np.sum(np.any((probabilities>.5)&below,axis=1))))
    return result


def name(scan,arm,gate,weighting):return f'{scan}-{arm}-{weighting}-{gate}.json'


def run(task):
    scan,arm,gate,weighting,stage=task
    target=OUT/stage/name(scan,arm,gate,weighting)
    data,saved,source,pool,hashes=inputs(scan)
    if target.exists():
        r=json.loads(target.read_text());assert r['dependencies']==dependencies()
        assert r['input_sha256']==saved['input_sha256'];return str(target)
    begun=time.monotonic();obj=objective(data,saved,arm,gate,weighting)
    if stage=='initial':
        records=[old.reprice(obj,r['best'],arm,f'previous-{r["arm"]}-{r["mode"]}') for r in pool]
        seeds=[old.reprice(obj,r['roof'],arm,'roof-seed') for r in pool if r['mode']=='G' and r['arm']!='prior-c']
        roofs=[old.fitted(obj,s,'roof',BUDGET['roof_s'],True) for s in seeds]
        roof=min(roofs,key=lambda r:r['objective']);ordered=sorted(records,key=lambda r:r['objective'])
        second=next((r for r in ordered[1:] if np.linalg.norm(np.array(r['point_km'])-ordered[0]['point_km'])>.1),ordered[1])
        records+=roofs
        for i,s in enumerate([ordered[0],second,roof]):
            records.append(old.fitted(obj,s,f'search-{i}',BUDGET['search_s']))
        best=old.previous.best_record(records)
        if not metrics(obj,data,best)['converged']:
            records.append(old.fitted(obj,best,'initial-polish',BUDGET['initial_polish_s']))
        r=dict(scope=__doc__,scan=scan,arm=arm,gate=gate,weighting=weighting,spec=GATES[gate],
            source=str(source),source_sha256=old.previous.digest(source),input_sha256=saved['input_sha256'],
            dependencies=dependencies(),seed_sources=hashes,maximum_budgets_s=BUDGET,
            fit_original_rows=data.original_rows,evaluation_original_rows=data.original_rows,heldout_original_rows=[],
            numbers=data.numbers,windows=len(data.times),radius_km=4.,weights=obj.likelihood.weights,
            roof=roof,records=records)
    else:
        paths=[OUT/'initial'/name(scan,a,g,w) for w in WEIGHTS for g in GATES for a in ARMS]
        cross=[json.loads(p.read_text()) for p in paths]
        r=next(x for x in cross if (x['arm'],x['gate'],x['weighting'])==(arm,gate,weighting))
        records=r['records'];records += [old.reprice(obj,x['best'],arm,'cross-seed') for x in cross]
        r['cross_sources']={str(p):old.previous.digest(p) for p in paths}
        for algorithm in ('slsqp','fisher'):
            best=old.previous.best_record(records)
            if metrics(obj,data,best)['converged']:break
            if algorithm=='slsqp':new=old.slsqp_fit(obj,best,BUDGET['final_slsqp_s'])
            else:new=old.fitted(obj,best,'final-fisher',BUDGET['final_fisher_s'])
            records.append(new)
    best=old.previous.best_record(records)
    ref=objective(data,saved,arm,'H',weighting)
    common=old.metrics(ref,data,old.reprice(ref,best,arm,'common-hard-reference'))
    r.update(best=best,**metrics(obj,data,best),stage=stage,elapsed_stage_s=time.monotonic()-begun,
        common_hard_data_nll=common['data_nll'])
    old.previous.save(target,r)
    print(stage.upper(),scan,arm,weighting,gate,round(r['distance_m']),'m','KKT',round(r['kkt'],6),flush=True)
    return str(target)


def check():
    errors=[];parity=[]
    for scan in ('N01','N08'):
        data,saved,_,pool,_=inputs(scan)
        for arm in ARMS:
            for weighting in WEIGHTS:
                seed=next(r['best'] for r in pool if r['arm']==arm and r['mode']==('G' if weighting=='ordinary' else 'GT'))
                for gate in GATES:
                    obj=objective(data,saved,arm,gate,weighting);v=old.seed_vector(obj,seed,arm)
                    j,g=obj.evaluate(v)
                    sine,_=obj.get_geometry(v)
                    np.testing.assert_array_equal(sine>=0,obj.base.predict(v[:obj.size])[1])
                    if gate=='H':
                        ref=old.make_objective(data,saved,arm,'C1' if weighting=='ordinary' else 'A03')
                        j0,g0=ref.evaluate(v);np.testing.assert_allclose(j,j0,atol=1e-8,rtol=0)
                        np.testing.assert_allclose(g,g0,atol=1e-8,rtol=0);parity.append(True)
                        continue
                    for i in (0,1,2,3,6,7,obj.size):
                        h=1e-3 if i in (2,obj.size) else 2e-5
                        l,r=v.copy(),v.copy();l[i]-=h;r[i]+=h
                        numeric=(obj.evaluate(r)[0]-obj.evaluate(l)[0])/(2*h)
                        errors.append(abs(numeric-g[i]))
                        np.testing.assert_allclose(numeric,g[i],atol=2e-3,rtol=3e-4,err_msg=f'{scan} {arm} {gate} {weighting} index {i}')
                    obj.evaluate(v);h=obj.curvature(v)
                    np.testing.assert_allclose(h,h.T,atol=1e-8,rtol=1e-8)
                    assert np.linalg.eigvalsh(h).min()>-1e-6
    old.previous.save(OUT/'self-check.json',dict(status='passed',gradient_checks=len(errors),
        max_absolute_error=max(errors),hard_control_parity_checks=len(parity),
        note='Includes the formerly discontinuous N08 timing/position neighborhood'))


def collect(stage='final'):
    rows=[]
    for scan in SCANS:
        data,saved,source,_,hashes=inputs(scan)
        for weighting in WEIGHTS:
            for gate in GATES:
                for arm in ARMS:
                    r=json.loads((OUT/stage/name(scan,arm,gate,weighting)).read_text())
                    assert r['dependencies']==dependencies() and r['seed_sources']==hashes
                    assert r['input_sha256']==saved['input_sha256'] and r['source_sha256']==old.previous.digest(source)
                    assert r['maximum_budgets_s']==BUDGET and r['spec']==GATES[gate]
                    assert r['fit_original_rows']==r['evaluation_original_rows']==data.original_rows.tolist()
                    assert not r['heldout_original_rows'] and r['numbers']==data.numbers.tolist()
                    obj=objective(data,saved,arm,gate,weighting)
                    np.testing.assert_array_equal(r['weights'],obj.likelihood.weights)
                    checked=metrics(obj,data,r['best'])
                    for k,value in checked.items():np.testing.assert_allclose(value,r[k],atol=1e-6,rtol=0)
                    v=np.asarray(r['best']['vector'])
                    assert np.linalg.norm(r['best']['point_km'])<=4.+1e-7
                    assert abs(v[6])<=10.+1e-7 and max(abs(np.asarray(r['best']['parameters'])[6:]))<=20.+1e-7
                    for z,(lo,hi) in zip(v,obj.bounds):
                        assert (lo is None or z>=lo-1e-7) and (hi is None or z<=hi+1e-7)
                    if arm=='zero-c':assert v[obj.size]==0.
                    assert r['objective']<=min(z['objective'] for z in r['records'])+1e-7
                    if stage=='final':
                        paths=[OUT/'initial'/name(scan,a,g,w) for w in WEIGHTS for g in GATES for a in ARMS]
                        assert r['cross_sources']=={str(p):old.previous.digest(p) for p in paths}
                    rows.append(r)
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','check','initial','final','audit'])
    parser.add_argument('--scans',nargs='+',default=SCANS,choices=SCANS)
    parser.add_argument('--workers',type=int,default=12);args=parser.parse_args()
    if args.action=='prepare':old.previous.save(OUT/'protocol.json',dict(scope=__doc__,gates=GATES,
        weightings=WEIGHTS,arms=ARMS,budgets=BUDGET,baseline=old.previous.BASE,dependencies=dependencies(),
        warning='Centered gates permit small below-horizon probability; Q1 forbids it. Geometric horizon, not RX beam pattern.',
        seed_pool='All 12 preceding polished solutions per scan; all 20 new initial fits shared in final stage'))
    elif args.action=='check':check()
    elif args.action=='audit':
        rows=collect();old.previous.save(OUT/'final'/'audit.json',dict(status='passed',cases=len(rows),
            converged=sum(r['converged'] for r in rows),boundary=sum(r['boundary'] for r in rows)))
    else:
        jobs=[(s,a,g,w,args.action) for s in args.scans for w in WEIGHTS for g in GATES for a in ARMS]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for f in as_completed([pool.submit(run,j) for j in jobs]):f.result()
