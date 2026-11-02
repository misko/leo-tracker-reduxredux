"""Report-local guarded native conditional prediction; never reads evaluation GPS.

The training posterior is the existing generalized variational posterior.
Prediction is a normalized Gaussian approximation conditional on its fitted
Gamma precisions, with linear nuisance and local position uncertainty retained.
Full-data nomination, masks, aliases, powers, point-noise and RF starts persist.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import numpy as np
from algo07_science import engine as e
from algo07_science.validation import clean

ROOT=Path(__file__).resolve().parent
SEED=2026110207
MODELS=(('legacy',1.),('damped_half',1.),('damped_half',2.),('damped_half',4.))


def module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


family=module('report_family',ROOT.parent/'family/prototype.py')
solver=module('report_solver',ROOT.parent/'solver/solver.py')


def write(path,value):
    Path(path).write_text(json.dumps(clean(value),indent=2,allow_nan=False)+'\n')


def native(p):
    ids=np.asarray([o for i in p.members for o in p.scan.tracks[i]['observation_ids']])
    families=np.repeat([r['candidate_norad'] for r in p.rows],[sl.stop-sl.start for sl in p.slices])
    assert len(ids)==len(set(ids))==len(p.keep)
    return ids,families


def partitions(p,count=3):
    """Synchronize ALL channels in native five-second groups, with 5 s guards."""
    ids,families=native(p);blocks=np.floor(p.flat_times/5).astype(int)
    available=np.unique(blocks[p.keep]);rng=np.random.default_rng(SEED);seen=set();out=[]
    for fold in range(count):
        for retry in range(10000):
            held=np.sort(rng.choice(available,max(1,round(.2*len(available))),replace=False))
            if tuple(held) in seen:continue
            test=p.keep & np.isin(blocks,held)
            guard=np.unique(np.r_[held-1,held,held+1]);train=p.keep & ~np.isin(blocks,guard)
            if all(np.sum(train&(families==g))>=5 and np.sum(test&(families==g))>=2
                   for g in np.unique(families[p.keep])):break
        else:raise ValueError('Cannot construct preregistered grouped partition')
        seen.add(tuple(held));out.append(dict(fold=fold,held_blocks=held,guard_blocks=guard,
            train_ids=ids[train],held_ids=ids[test],train=train,test=test,retries=retry))
    return out


def seal(case,d,z):
    """Write split/protocol artifacts before evaluating any candidate outcome."""
    p=d['problems']['fitted_c'][0];parts=partitions(p)
    protocol=dict(case=case,seed=SEED,models=MODELS,folds=parts,
        native_group_seconds=5,guard_seconds_each_side=5,held_fraction_groups=.2,
        solver_budget=dict(max_rounds=8,maxiter=25,maxfun=100),
        position_prior_km=[-12.5,12.5],position_uncertainty='local Laplace covariance, inverse half-Hessian of training -2 ELBO; delta method for posterior prediction mean',
        predictive_density='normalized diagonal-plus-low-rank Gaussian; training generalized variational coefficient posterior, fitted Gamma precisions; no held nuisance update; no likelihood power on held observations',
        limitations=['Fixed full-data native nomination, mask, alias branches, empirical point noise and likelihood powers; RF position/reference initialization inherited.',
            'Causal phase-prior development inherited; training Gamma precisions re-estimated from train observations only.',
            'Ancillary linear/family predictive likelihoods omitted to avoid synchronized held-data leakage. Conditional base-curved-family evidence only.',
            'Gaussian approximation conditions on fitted Gamma precisions; Gamma hyperparameter uncertainty is not integrated.',
            'Local Laplace position approximation is diagnostic near boundaries/nonpositive curvature; not a calibrated coverage claim.',
            'No GPS/position error accessed; nomination and tested model roster are development-selected.'])
    write(ROOT/(case+'_protocol.json'),protocol)
    digest=hashlib.sha256((ROOT/(case+'_protocol.json')).read_bytes()).hexdigest()
    (ROOT/(case+'_protocol.sha256')).write_text(digest+'\n')
    return parts,digest


def normalized_gaussian(raw,sigma,uncertainty):
    """Exact normalized log density for diag(sigma²)+U U' (Woodbury)."""
    y=np.asarray(raw)/sigma;u=np.asarray(uncertainty)/sigma[:,None]
    gram=np.eye(u.shape[1])+u.T@u;root=np.linalg.cholesky(gram)
    rhs=u.T@y;solution=np.linalg.solve(root,rhs)
    quadratic=float(y@y-solution@solution)
    logdet=float(2*np.log(sigma).sum()+2*np.log(np.diag(root)).sum())
    return dict(negative_twice_log_density=quadratic+logdet+len(y)*np.log(2*np.pi),
                quadratic=quadratic,logdet_hz2=logdet,points=len(y))


def evaluate_context(d,z,norad,scale,solver_variant,split,*,budget=None):
    """Reusable remapped-context API. IDs define matching train/test observations.

    Caller may remap nominations before invocation. All nuisance fitting and
    regional optimization use train IDs. Ancillary families are excluded.
    """
    began=time.monotonic();budget=budget or dict(max_rounds=8,maxiter=25,maxfun=100)
    dd=family.candidate_context(d,z,scale,family=int(norad))
    p0=d['problems']['fitted_c'][0];ids,families=native(p0)
    train=np.isin(ids,split['train_ids']);test=np.isin(ids,split['held_ids'])
    if np.any(train&test) or not train.any() or not test.any():raise ValueError('Invalid native split')
    dd=dict(dd,keep=train,entries=[],families=[])
    zz=copy.deepcopy(z);zz.pop('selected',None);zz.pop('gap_selected',None)
    # Same frozen RF starts and solver budgets across both arms and hypotheses.
    arm=split['arm'];fitted=solver.fit(dd,zz,arm,variant=solver_variant,**budget)
    p,_=e.build(dd,zz,arm,np.asarray(fitted['reference']))
    x=np.asarray(fitted['x']);c=p.calculate(x);features=c['features']
    g=p.noise_groups[train]
    weights=np.asarray(d['powers'])[g]*c['noise_precision'][g]/p.point_noise[train]**2
    gram=np.diag(c['coefficient_prior_precision'])+features[train].T@(features[train]*weights[:,None])
    root=np.linalg.cholesky(gram)
    coefficient_uncertainty=np.linalg.solve(root,features.T).T
    mean=p.q*c['intercept']+features@c['coefficient']
    # Profile posterior mean derivatives include training nuisance adjustment.
    step=.02;gradient=[];hessian=np.zeros((2,2));f0=c['negative_twice_elbo']
    objective=lambda at:float(p.calculate(at)['negative_twice_elbo'])
    for j in range(2):
        delta=np.eye(2)[j]*step;cp=p.calculate(x+delta);cm=p.calculate(x-delta)
        mp=p.q*cp['intercept']+cp['features']@cp['coefficient']
        mm=p.q*cm['intercept']+cm['features']@cm['coefficient']
        gradient.append((mp-mm)/(2*step))
        hessian[j,j]=(cp['negative_twice_elbo']+cm['negative_twice_elbo']-2*f0)/step**2
    d0=np.array([step,0]);d1=np.array([0,step])
    hessian[0,1]=hessian[1,0]=(objective(x+d0+d1)-objective(x+d0-d1)-objective(x-d0+d1)+objective(x-d0-d1))/(4*step**2)
    eigen,vectors=np.linalg.eigh(hessian/2)
    # The finite regional prior bounds prevent an unbounded curvature fallback.
    floored=np.maximum(eigen,1/(25**2/12))
    position_covariance=(vectors/floored)@vectors.T
    position_uncertainty=np.column_stack(gradient)@np.linalg.cholesky(position_covariance)
    uncertainty=np.column_stack((coefficient_uncertainty,position_uncertainty))
    # Unpowered normalized sampling distribution: generalized training powers
    # affect posterior width but are never mistaken for held-data densities.
    precision=c['noise_precision'][p.noise_groups].copy()
    # A wholly withheld fragment has no fitted Gamma precision: its prior
    # Gamma(2,2) inverse-precision expectation is 2, never a test-fitted scale.
    unseen=precision<=0;precision[unseen]=.5
    sigma=p.point_noise/np.sqrt(precision)
    scores={}
    subsets={'all':test,'target':test&(families==norad),'other':test&(families!=norad)}
    subsets.update({f'family_{n}':test&(families==n) for n in np.unique(families[test])})
    for name,use in subsets.items():
        if use.any():
            scores[name]=dict(normalized_gaussian((p.values-mean)[use],sigma[use],uncertainty[use]),
                held_rms_hz=float(np.sqrt(np.mean((p.values-mean)[use]**2))))
    return dict(arm=arm,fold=split['fold'],norad=int(norad),SD_scale=scale,solver=solver_variant,
        scores=scores,x_km=x,reference=fitted['reference'],position_covariance_km2=position_covariance,
        position_precision_eigenvalues=eigen,position_curvature_floored=bool(np.any(eigen!=floored)),
        phase_closed=fitted['phase_closed'],phase_change_s=fitted['phase_change_s'],boundary=fitted['boundary'],
        unseen_noise_group_held_points=int(np.sum(unseen&test)),
        optimizer_success=fitted['optimizer_success'],evaluations=fitted['total_position_evaluations'],
        train_points=int(train.sum()),held_points=int(test.sum()),seconds=time.monotonic()-began,
        train_ids_sha256=hashlib.sha256('\n'.join(ids[train]).encode()).hexdigest(),
        held_ids_sha256=hashlib.sha256('\n'.join(ids[test]).encode()).hexdigest())
