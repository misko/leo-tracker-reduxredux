"""Exploratory coverage-composition diagnostic; no geographic truth."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import signal
import sys
import time
import traceback
import numpy as np

OLD = Path('/srv/bulk/leo/research/ds24-ch78-diagnosis-r02')
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OLD))
import common as c
from scipy.linalg import solve_triangular
oldmatched = c.module('round2_matched_run', OLD/'matched/run.py')
CASE = 'DS24-0012'
VARIANTS = ('full', 'overlap', 'plus_A', 'plus_B', 'plus_AB', 'minus_dominant', 'full_minus_dominant')
REDUCED = ('overlap', 'plus_A', 'plus_B', 'plus_AB', 'minus_dominant')


def nominate(d, prior):
    m = c.metadata(d['base'])
    keep = np.asarray(d['keep'])
    overlap = np.zeros(len(keep), bool)
    for name in ('matched_low_0', 'matched_high_0'):
        overlap[np.asarray(prior['choices'][name])] = True
    families = sorted(set(m['family'][keep]))
    table = [dict(family=int(j), norad=int(d['base'].scan.norads[j]),
                  full=int((keep & (m['family'] == j)).sum()),
                  overlap=int((overlap & (m['family'] == j)).sum())) for j in families]
    dominant = sorted(table, key=lambda r: (-r['overlap'], r['norad']))[0]
    absent = sorted([r for r in table if r['overlap'] == 0], key=lambda r: (-r['full'], r['norad']))[:2]
    assert len(absent) == 2
    a, b = [keep & (m['family'] == r['family']) for r in absent]
    dom = m['family'] == dominant['family']
    masks = dict(full=keep, overlap=overlap, plus_A=overlap|a, plus_B=overlap|b,
                 plus_AB=overlap|a|b, minus_dominant=overlap & ~dom, full_minus_dominant=keep & ~dom)
    held = keep & ~masks['plus_AB']
    assert held.any() and all(not (held & masks[k]).any() for k in REDUCED)
    return masks, held, dict(table=table, dominant=dominant, omitted=absent)


def posterior_root(p, calculated, d):
    f = calculated['features'][p.keep]
    groups = p.noise_groups[p.keep]
    weights = np.asarray(d['powers'])[groups]*calculated['noise_precision'][groups]/p.point_noise[p.keep]**2
    return np.linalg.cholesky(np.diag(calculated['coefficient_prior_precision']) + f.T @ (f*weights[:, None]))


def predictive(p, calculated, d, held):
    root = posterior_root(p, calculated, d)
    uncertainty = solve_triangular(root, calculated['features'][held].T, lower=True).T
    sigma = p.point_noise[held]/np.sqrt(calculated['noise_precision'][p.noise_groups[held]])
    raw = calculated['conditional_residual_hz'][held]
    return raw, uncertainty, sigma


def fixed_posterior(d, arm, packet, x):
    ref = np.zeros(len(d['means']))
    changes = []
    for _ in range(5):
        p = c.frozen.build(d, arm, ref, packet)
        phase = p.state(x)['phases'][p.labels]
        updated = np.clip(phase, -15, 15)
        changes.append(float(np.max(abs(updated-ref))))
        ref = updated
    return p, p.calculate(x), dict(phase_changes=changes,
        maximum_unclipped_phase_s=float(np.max(abs(phase))),
        checks_pass=bool(changes[-1] <= .01 and np.max(abs(phase)) <= 15.000001))


def information(p, calculated, d, x):
    from ds23_height_problem import geometry_features
    columns = []
    for k in range(2):
        step = np.eye(2)[k]*.02
        parts = []
        for xx in (np.asarray(x)+step, np.asarray(x)-step):
            g = geometry_features(p, xx, 0.)
            parts.append(p.q*g['intercept'] + g['features']@calculated['coefficient'])
        columns.append((parts[0]-parts[1])/.04)
    jac = np.column_stack(columns)[p.keep]
    f = calculated['features'][p.keep]
    groups = p.noise_groups[p.keep]
    weights = np.asarray(d['powers'])[groups]*calculated['noise_precision'][groups]/p.point_noise[p.keep]**2
    root = posterior_root(p, calculated, d)
    cross = solve_triangular(root, f.T@(jac*weights[:, None]), lower=True)
    fisher = jac.T@(jac*weights[:, None])-cross.T@cross
    eig, vec = np.linalg.eigh((fisher+fisher.T)/2)
    assert np.all(eig > 0)
    return dict(mean_information_per_km2=fisher, eigenvalues=eig,
                conditional_axis_sigma_km=1/np.sqrt(eig), weak_direction_east_north=vec[:, 0],
                caveat='Local mean information with frozen phase/precisions/identity; excludes covariance derivatives and model discrepancy.')


def freeze():
    d = c.context(CASE)
    old = c.load(OLD/'matched/protocol.json')
    masks, held, selection = nominate(d, old['cases'][CASE])
    meta = c.metadata(d['base'])
    sources = dict(old['sources'])
    sources.update({p: x['sha256'] for p, x in c.load(OLD/'supplemental_provenance.json')['files'].items()})
    for path in [OLD/'matched/protocol.json', OUT/'run.py', OUT/'test_mechanism.py', OUT/'PROTOCOL.md']:
        sources[str(path)] = c.sha(path)
    c.verify(sources)
    c.write(OUT/'protocol.json', dict(case=CASE, sources=sources, selection=selection,
        masks={k: np.flatnonzero(v) for k,v in masks.items()},
        ids={k: meta['ids'][v] for k,v in masks.items()}, held=np.flatnonzero(held), held_ids=meta['ids'][held],
        packet=old['cases'][CASE]['packets'], GPS_used=False, nominated_after_prior_error_inspection=True))


def fitted(job):
    name, arm = job
    began = time.monotonic(); c.cap(300)
    result = dict(case=CASE, method=name, arm=arm, GPS_used=False)
    try:
        protocol = c.load(OUT/'protocol.json'); c.verify(protocol['sources'])
        d = c.context(CASE); keep = np.zeros(len(d['keep']),bool); keep[protocol['masks'][name]] = True
        train = dict(d, keep=keep, entries=[])
        result.update(oldmatched.solve(train,arm,protocol['packet'][arm]))
        p = c.frozen.build(train,arm,result['phase_reference'],protocol['packet'][arm])
        calculated = p.calculate(result['endpoint_east_north_km'])
        result['information'] = information(p,calculated,train,result['endpoint_east_north_km'])
        result['training_checks_pass'] = result['phase_checks_pass'] and all(h['fit']['stopped']!='iteration_budget' for h in result['history'])
        if name == 'full':
            previous = c.load(OLD/'matched/results'/f'{CASE}_full_{arm}.json')
            result['original_full_endpoint_exact'] = np.array_equal(previous['endpoint_east_north_km'],result['endpoint_east_north_km'])
            assert result['original_full_endpoint_exact']
        c.verify(protocol['sources']); result['status']='complete'
    except Exception as exc:
        result.update(status='failed',error=repr(exc),traceback=traceback.format_exc())
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
    result['seconds']=time.monotonic()-began
    c.write(OUT/'fits'/f'{name}_{arm}.json',result)
    print(name,arm,result['status'],round(result['seconds'],2),flush=True)
    return result


def score(job):
    name, arm = job
    began=time.monotonic(); c.cap(300)
    result=dict(method=name,arm=arm,GPS_used=False)
    try:
        protocol=c.load(OUT/'protocol.json'); c.verify(protocol['sources'])
        d=c.context(CASE); keep=np.zeros(len(d['keep']),bool); keep[protocol['masks'][name]]=True
        held=np.zeros(len(keep),bool);held[protocol['held']]=True
        assert not (keep & held).any()
        train=dict(d,keep=keep,entries=[]);meta=c.metadata(d['base'])
        result['endpoints']={}
        for key,filename in [('overlap',f'overlap_{arm}.json'),('own',f'{name}_{arm}.json')]:
            fit=c.load(OUT/'fits'/filename);assert fit['status']=='complete'
            x=fit['endpoint_east_north_km']
            p,calculated,checks=fixed_posterior(train,arm,protocol['packet'][arm],x)
            raw,u,sigma=predictive(p,calculated,train,held)
            groups={str(int(p.scan.norads[j])):c.h.gaussian_score(raw[meta['family'][held]==j],u[meta['family'][held]==j],sigma[meta['family'][held]==j])
                    for j in sorted(set(meta['family'][held]))}
            result['endpoints'][key]=dict(position=x,checks=checks,
                score=c.h.gaussian_score(raw,u,sigma),family_marginals_nonadditive=groups,
                train_held_IDs_disjoint=True,held_IDs_bound_by_protocol_sha256=c.sha(OUT/'protocol.json'))
        aa=result['endpoints']['overlap']['score'];bb=result['endpoints']['own']['score']
        result['movement_gain']=aa['negative_twice_log_density']-bb['negative_twice_log_density']
        result['quadratic_gain']=aa['quadratic']-bb['quadratic'];result['logdet_gain']=aa['logdet']-bb['logdet']
        c.verify(protocol['sources']);result['status']='complete'
    except Exception as exc:result.update(status='failed',error=repr(exc),traceback=traceback.format_exc())
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    result['seconds']=time.monotonic()-began;c.write(OUT/'scores'/f'{name}_{arm}.json',result)
    print('score',name,arm,result['status'],round(result['seconds'],2),flush=True)
    return result


def execute():
    with ProcessPoolExecutor(max_workers=2) as pool:
        fits=list(pool.map(fitted,[(v,a) for v in VARIANTS for a in c.ARMS]))
    with ProcessPoolExecutor(max_workers=2) as pool:
        scores=list(pool.map(score,[(v,a) for v in REDUCED for a in c.ARMS]))
    c.write(OUT/'execution.json',dict(fits=fits,scores=scores,GPS_used=False))
    c.write(OUT/'RF_seal.json',dict(files={str(p):c.sha(p) for p in OUT.rglob('*') if p.suffix in ('.json','.py','.md')},GPS_used=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','run']);args=parser.parse_args()
    freeze() if args.action=='freeze' else execute()
