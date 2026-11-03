"""Focused density-weighting x robust-error x RF-shrinkage experiment.

N01--N16 independently, all frozen full-data associated top-one windows. Four
likelihood/weight combinations, three RF arms: free c, c~N(0,100^2) Hz/GHz,
and c=0. The zero-c arm is the identical control for both fitted-c priors, so
it is computed once. No observation removal, new calibration or RF collection.
Known-roof development cohort, not blind validation. Objective-only selection.
"""
import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

import numpy as np

import position_structure_study as old
from position_direct import coordinate_jacobian

HERE = Path(__file__).resolve().parent
OUT = HERE/'position-interaction-study'
SCANS = old.SCANS
ARMS = ('fitted-c', 'prior-c', 'zero-c')
MODES = {
    'G': dict(label='Gaussian', kernel='C1', weights='C1'),
    'GT': dict(label='Gaussian + time balance', kernel='C1', weights='A03'),
    'M': dict(label='Robust mixture', kernel='A06', weights='C1'),
    'MT': dict(label='Robust mixture + time balance', kernel='A06', weights='A03'),
}
PRIOR_SIGMA = 100.  # 1-sigma channel-to-channel correction over .75 GHz is 75 Hz.
BUDGET = dict(roof_s=4., search_s=4., search_starts=3, polish_s=8.,
              final_slsqp_s=15., final_fisher_s=12.)


def solver_arm(arm):
    if arm not in ARMS: raise ValueError('Unknown RF arm')
    return 'zero-c' if arm == 'zero-c' else 'fitted-c'


class Objective(old.Objective):
    def __init__(self, data, center, arm, mode):
        spec = MODES[mode]
        super().__init__(data, center, solver_arm(arm), spec['kernel'])
        self.likelihood.weights = old.row_weights(data, spec['weights'])
        self.rf_prior_sigma = PRIOR_SIGMA if arm == 'prior-c' else None

    def extra_penalty(self, vector):
        v = np.asarray(vector)
        h = np.zeros((len(v), len(v)))
        if self.rf_prior_sigma is not None:
            h[self.size, self.size] = 1./self.rf_prior_sigma**2
        return float(.5*v@h@v), h@v, h


@lru_cache(maxsize=1)
def dependencies():
    paths = [Path(__file__), Path(old.__file__), HERE/'polish_position_score_sweep.py']
    return dict(old.previous.dependencies(), **{str(p): old.previous.digest(p) for p in paths})


@lru_cache(maxsize=2)
def inputs(scan):
    data, saved, source, _, _ = old.inputs(scan)
    paths = [old.OUT/'polished'/f'{scan}-{a}-{m}.json' for a in old.ARMS for m in old.MODES]
    pool = [json.loads(p.read_text()) for p in paths]
    assert all(r['input_sha256'] == saved['input_sha256'] for r in pool)
    return data, saved, source, pool, {str(p):old.previous.digest(p) for p in paths}


def objective(data, saved, arm, mode):
    return Objective(data, saved['input_metadata']['rf_center_hz'], arm, mode)


def satellite_gradients(obj, data, record):
    """Data-gradient attribution by modelled satellite, all responsibilities.

    Timing/RF priors have no direct position derivative. At a nuisance-stationary
    roof fit this sum is the envelope/profile gradient; otherwise label it as
    a conditional gradient, never claim a converged profile gradient.
    """
    v = np.asarray(record['vector'])
    obj.base.deadline = float('inf')
    _, g = obj.evaluate(v)
    pg = obj.likelihood.last_result['prediction_gradient'].copy()
    probs = obj.likelihood.last_result['row_association_probability'].copy()
    _, _, jac = obj.base.predict(v[:obj.size], with_jacobian=True)
    transform = coordinate_jacobian(np.asarray(record['point_km']))
    contributions = []
    for j, number in enumerate(data.numbers):
        mask = np.zeros_like(pg); mask[:, j] = -pg[:, j]
        physical = jac.transpose_multiply(mask.ravel())
        mapped = obj.base.vector_gradient(physical, v[:obj.size])
        grad = .1*transform.T@mapped[:2]
        contributions.append(dict(norad=int(number), gradient_per_100m=grad,
            gradient_norm_per_100m=float(np.linalg.norm(grad)),
            original_windows=int(sum(data.owners == number)),
            soft_expected_windows=float(probs[:, j].sum())))
    total = .1*transform.T@g[:2]
    np.testing.assert_allclose(np.sum([r['gradient_per_100m'] for r in contributions],axis=0),
                               total,atol=1e-7,rtol=1e-8)
    return dict(gradient_per_100m=total, norm_per_100m=float(np.linalg.norm(total)),
                nuisance_converged=bool(record.get('success', False)), satellites=contributions)


def finish(obj, data, best):
    result = old.metrics(obj, data, best)
    v = np.asarray(best['vector'])
    result['coefficient_hz_per_ghz'] = float(v[obj.size])
    result['rx0_extra_slope_hz_s'] = float(v[3])
    result['rx1_extra_slope_hz_s'] = float(v[5])
    result['timing'] = old.previous.old.previous.timing_and_gradient(obj, best)
    return result


def run(task):
    scan, arm, mode, stage = task
    target = OUT/stage/f'{scan}-{arm}-{mode}.json'
    data, saved, source, pool, hashes = inputs(scan)
    if target.exists():
        result = json.loads(target.read_text())
        assert result['dependencies'] == dependencies()
        assert result['input_sha256'] == saved['input_sha256']
        return str(target)
    begun = time.monotonic()
    obj = objective(data, saved, arm, mode)
    a = solver_arm(arm)
    if stage == 'initial':
        records = [old.reprice(obj, r['best'], a, f'previous-{r["arm"]}-{r["mode"]}') for r in pool]
        # Identical two roof starts in every case, selected by objective only.
        seeds = [old.reprice(obj, r['roof'], a, 'roof-seed') for r in pool
                 if r['mode'] == 'C1']
        roofs = [old.fitted(obj, s, 'roof', BUDGET['roof_s'], True) for s in seeds]
        roof = min(roofs, key=lambda r:r['objective'])
        ordered = sorted(records, key=lambda r:r['objective'])
        second = next((r for r in ordered[1:] if np.linalg.norm(np.array(r['point_km'])-
                        ordered[0]['point_km']) > .1), ordered[1])
        records += roofs
        for i, seed in enumerate([ordered[0], second, roof]):
            records.append(old.fitted(obj, seed, f'search-{i}', BUDGET['search_s']))
        best = old.previous.best_record(records)
        if not old.metrics(obj, data, best)['converged']:
            records.append(old.fitted(obj, best, 'polish', BUDGET['polish_s']))
        result = dict(scope=__doc__, scan=scan, arm=arm, mode=mode, spec=MODES[mode],
            rf_prior_sigma_hz_per_ghz=obj.rf_prior_sigma, source=str(source),
            source_sha256=old.previous.digest(source), dependencies=dependencies(), seed_sources=hashes,
            input_sha256=saved['input_sha256'], maximum_budgets_s=BUDGET,
            fit_original_rows=data.original_rows, evaluation_original_rows=data.original_rows,
            heldout_original_rows=[], windows=len(data.times), numbers=data.numbers,
            radius_km=4., weights=obj.likelihood.weights, roof=roof, records=records)
    else:
        paths = [OUT/'initial'/f'{scan}-{aa}-{m}.json' for aa in ARMS for m in MODES]
        cross = [json.loads(p.read_text()) for p in paths]
        result = next(r for r in cross if (r['arm'],r['mode']) == (arm,mode))
        records = result['records']
        records += [old.reprice(obj, r['best'], a, f'cross-{r["arm"]}-{r["mode"]}') for r in cross]
        result['cross_sources'] = {str(p):old.previous.digest(p) for p in paths}
        for algorithm in ('slsqp','fisher'):
            best = old.previous.best_record(records)
            if old.metrics(obj, data, best)['converged']: break
            if algorithm == 'slsqp':
                r = old.slsqp_fit(obj, best, BUDGET['final_slsqp_s'])
                r['stage'] = 'final-slsqp'
            else: r = old.fitted(obj, best, 'final-fisher', BUDGET['final_fisher_s'])
            records.append(r)
    best = old.previous.best_record(records)
    reference = objective(data, saved, 'fitted-c', 'G')
    common = old.metrics(reference, data, old.reprice(reference, best, 'fitted-c', 'common-reference'))
    result.update(best=best, **finish(obj,data,best), stage=stage,
        common_reference_data_nll=common['data_nll'], elapsed_stage_s=time.monotonic()-begun)
    if stage == 'final':
        result['roof_gradients'] = satellite_gradients(obj,data,result['roof'])
    old.previous.save(target,result)
    print(stage.upper(),scan,arm,mode,round(result['distance_m']),'m',
          'KKT',round(result['kkt'],5),flush=True)
    return str(target)


def check():
    data,saved,_,pool,_ = inputs('N01')
    errors=[]
    for arm in ARMS:
        for mode,spec in MODES.items():
            obj=objective(data,saved,arm,mode)
            v=old.seed_vector(obj,pool[0]['best'],solver_arm(arm))
            _,g=obj.evaluate(v)
            for i in (0,1,3,6,7,obj.size):
                eps=1e-3 if i==obj.size else 2e-5
                l,r=v.copy(),v.copy();l[i]-=eps;r[i]+=eps
                num=(obj.evaluate(r)[0]-obj.evaluate(l)[0])/(2*eps)
                errors.append(abs(num-g[i]))
                np.testing.assert_allclose(num,g[i],atol=2e-3,rtol=2e-4)
            if arm!='prior-c' and mode!='MT':
                oldmode={'G':'C1','GT':'A03','M':'A06'}[mode]
                ref=old.make_objective(data,saved,arm,oldmode)
                a,ag=obj.evaluate(v);b,bg=ref.evaluate(v)
                np.testing.assert_allclose(a,b,atol=1e-8,rtol=0)
                np.testing.assert_allclose(ag,bg,atol=1e-8,rtol=0)
                np.testing.assert_allclose(obj.curvature(v),ref.curvature(v),atol=1e-8,rtol=1e-9)
    old.previous.save(OUT/'self-check.json',dict(status='passed',checks=len(errors),
        maximum_gradient_error=max(errors),controls_score_gradient_curvature_parity=True))


def collect():
    rows=[]
    for scan in SCANS:
        data,saved,source,_,hashes=inputs(scan)
        for arm in ARMS:
            for mode in MODES:
                r=json.loads((OUT/'final'/f'{scan}-{arm}-{mode}.json').read_text())
                assert r['dependencies']==dependencies() and r['seed_sources']==hashes
                assert r['input_sha256']==saved['input_sha256']
                assert r['source_sha256']==old.previous.digest(source)
                assert r['maximum_budgets_s']==BUDGET and r['spec']==MODES[mode]
                assert r['fit_original_rows']==r['evaluation_original_rows']==data.original_rows.tolist()
                assert not r['heldout_original_rows'] and r['numbers']==data.numbers.tolist()
                paths=[OUT/'initial'/f'{scan}-{a}-{m}.json' for a in ARMS for m in MODES]
                assert r['cross_sources']=={str(p):old.previous.digest(p) for p in paths}
                obj=objective(data,saved,arm,mode)
                assert r['rf_prior_sigma_hz_per_ghz']==obj.rf_prior_sigma
                np.testing.assert_array_equal(r['weights'],obj.likelihood.weights)
                checked=finish(obj,data,r['best'])
                for k,value in checked.items():
                    if k=='timing':
                        for kk,vv in value.items():np.testing.assert_allclose(vv,r[k][kk],atol=1e-6,rtol=0)
                    else:np.testing.assert_allclose(value,r[k],atol=1e-6,rtol=0)
                v=np.asarray(r['best']['vector'])
                assert np.linalg.norm(r['best']['point_km'])<=4.+1e-7
                assert abs(v[6])<=10.+1e-7
                assert max(abs(np.asarray(r['best']['parameters'])[6:]))<=20.+1e-7
                for z,(lo,hi) in zip(v,obj.bounds):
                    assert (lo is None or z>=lo-1e-7) and (hi is None or z<=hi+1e-7)
                if arm=='zero-c':assert v[obj.size]==0.
                assert r['best']['objective']<=min(z['objective'] for z in r['records'])+1e-7
                rows.append(r)
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','check','initial','final','audit'])
    parser.add_argument('--scans',nargs='+',default=SCANS,choices=SCANS)
    parser.add_argument('--workers',type=int,default=12)
    args=parser.parse_args()
    if args.action=='prepare':
        old.previous.save(OUT/'protocol.json',dict(scope=__doc__,modes=MODES,arms=ARMS,
            rf_prior_sigma_hz_per_ghz=PRIOR_SIGMA,maximum_budgets_s=BUDGET,
            baseline=old.previous.BASE,dependencies=dependencies(),
            seed_pool='All 22 structural-study polished solutions per scan; all 12 initial solutions in final stage',
            limitations='Local 4 km search, all-data known-roof development, no new raw RF; not global or blind',
            controls='Zero-c computed once: it is the same model for both RF prior conditions'))
    elif args.action=='check':check()
    elif args.action=='audit':
        rows=collect()
        old.previous.save(OUT/'final'/'audit.json',dict(status='passed',cases=len(rows),
            converged=sum(r['converged'] for r in rows),boundary=sum(r['boundary'] for r in rows),
            dependencies=dependencies()))
    else:
        jobs=[(s,a,m,args.action) for s in args.scans for m in MODES for a in ARMS]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for f in as_completed([pool.submit(run,j) for j in jobs]):f.result()
