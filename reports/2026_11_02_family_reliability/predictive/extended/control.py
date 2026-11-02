"""Cap15 control, all 48 original cells rerun; no original artifact mutation."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor,as_completed
import multiprocessing
import numpy as np

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import predictive as p
from algo07_science import engine as e

FROZEN=p.module('extended_frozen_solver',ROOT/'frozen_solver.py')
CONTEXT=None
LAST_FIT=None


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def traced_fit(*args,**kw):
    global LAST_FIT
    LAST_FIT=FROZEN.fit(*args,**kw)
    return LAST_FIT


def qualification(row):
    reasons=[]
    if not row['phase_closed']:reasons.append('phase_not_closed')
    if not row['optimizer_success']:reasons.append('position_optimizer_failed')
    if row['boundary']:reasons.append('position_at_regional_boundary_untruncated_Laplace')
    eig=np.asarray(row['position_precision_eigenvalues'])
    if np.any(eig<=0):reasons.append('nonpositive_position_precision')
    if row['position_curvature_floored']:reasons.append('position_curvature_floored')
    for subset,s in row['scores'].items():
        if not np.isfinite(s['negative_twice_log_density']):reasons.append('nonfinite_predictive_density_'+subset)
        if s['quadratic'] < -1e-8:reasons.append('negative_predictive_quadratic_'+subset)
    return dict(numerical_fit_qualified=not reasons,unqualified_reasons=reasons,
        scope='Numerical approximation checks only; empirical preprocessing, nomination leakage and omitted ancillary likelihoods prevent generalization/production qualification even when these pass.')


def covariance_audit(d,z,row,part):
    """Reconstruct full held covariance and compare dense normalized density."""
    dd=p.family.candidate_context(d,z,row['SD_scale'],family=row['norad'])
    ids,_=p.native(d['problems']['fitted_c'][0]);train=np.isin(ids,part['train_ids']);test=np.isin(ids,part['held_ids'])
    dd=dict(dd,keep=train,entries=[],families=[]);zz=copy.deepcopy(z);zz.pop('selected',None);zz.pop('gap_selected',None)
    problem,_=e.build(dd,zz,row['arm'],np.asarray(row['reference']))
    x=np.asarray(row['x_km']);c=problem.calculate(x);u=c['features'];g=problem.noise_groups[train]
    w=np.asarray(d['powers'])[g]*c['noise_precision'][g]/problem.point_noise[train]**2
    gram=np.diag(c['coefficient_prior_precision'])+u[train].T@(u[train]*w[:,None])
    nuisance=np.linalg.solve(np.linalg.cholesky(gram),u[test].T).T
    mean=problem.q*c['intercept']+u@c['coefficient'];derivatives=[]
    for k in range(2):
        delta=np.eye(2)[k]*.02;cp=problem.calculate(x+delta);cm=problem.calculate(x-delta)
        derivatives.append(((problem.q*cp['intercept']+cp['features']@cp['coefficient'])-
                            (problem.q*cm['intercept']+cm['features']@cm['coefficient']))[test]/.04)
    position=np.column_stack(derivatives)@np.linalg.cholesky(np.asarray(row['position_covariance_km2']))
    precision=c['noise_precision'][problem.noise_groups].copy();precision[precision<=0]=.5
    sigma=problem.point_noise[test]/np.sqrt(precision[test])
    covariance=np.diag(sigma*sigma)+nuisance@nuisance.T+position@position.T
    raw=(problem.values-mean)[test];root=np.linalg.cholesky(covariance)
    white=np.linalg.solve(root,raw);dense_quad=float(white@white)
    dense_logdet=float(2*np.log(np.diag(root)).sum())
    dense=dense_quad+dense_logdet+len(raw)*np.log(2*np.pi)
    delta=dense-row['scores']['all']['negative_twice_log_density']
    return dict(dense_minus_lowrank_negative_twice_log_density=float(delta),dense_quadratic=dense_quad,
        dense_logdet_hz2=dense_logdet,noise_min_sigma_hz=float(sigma.min()),
        minimum_covariance_cholesky_pivot_hz=float(np.diag(root).min()),
        nuisance_trace_hz2=float(np.sum(nuisance*nuisance)),position_trace_hz2=float(np.sum(position*position)),
        dense_normalization_pass=bool(abs(delta)<1e-5),positive_definite_held_covariance=True,
        covariance_construction='E[Cov(y|x,train)] approximated at xhat + Cov(E[y|x,train]) via derivative of total posterior mean; separate conditional nuisance and marginal-position terms')


def job(spec):
    d,z=CONTEXT;case,old,part=spec
    try:
        p.solver=type('TracedSolver',(),{'fit':staticmethod(traced_fit)})
        row=p.evaluate_context(d,z,old['norad'],old['SD_scale'],old['solver'],dict(part,arm=old['arm']),
            budget=dict(max_rounds=15,maxiter=25,maxfun=100))
        row['case']=case;row['original_cap8_negative_twice_log_density']=old['scores']['all']['negative_twice_log_density']
        row['cap15_minus_cap8_negative_twice_log_density']=row['scores']['all']['negative_twice_log_density']-row['original_cap8_negative_twice_log_density']
        row['reuse']=False;row['solver_history']=LAST_FIT['history'];row.update(qualification(row))
        row['covariance_audit']=covariance_audit(d,z,row,part)
        if not row['covariance_audit']['dense_normalization_pass']:
            row['numerical_fit_qualified']=False;row['unqualified_reasons'].append('dense_density_normalization_disagreement')
        return row
    except Exception:return dict(case=case,arm=old['arm'],fold=old['fold'],solver=old['solver'],SD_scale=old['SD_scale'],error=traceback.format_exc())


def freeze():
    oldpaths=[ROOT.parent/(case+'_results.json') for case in ['DS26-0309','DS26-0070']]
    sourcepaths=[ROOT/'control.py',ROOT/'frozen_solver.py',ROOT.parent/'predictive.py',ROOT.parent.parent/'family/prototype.py']
    for oldpath in oldpaths:
        case=oldpath.name.removesuffix('_results.json');inventory=json.loads((ROOT.parent/(case+'_inventory.json')).read_text())
        assert sha(ROOT/'frozen_solver.py')==next(v for k,v in inventory['source_sha256'].items() if k.endswith('/solver/solver.py'))
        for f in sourcepaths[2:]:assert sha(f)==inventory['source_sha256'][str(f)]
    protocol=dict(control='All original48cells cap15, no reuse',changed_parameter='phase cap8→15 only',
        original_results_sha256={str(f):sha(f)for f in oldpaths},
        original_protocol_sha256={str(ROOT.parent/(c+'_protocol.json')):sha(ROOT.parent/(c+'_protocol.json'))for c in ['DS26-0309','DS26-0070']},
        source_sha256={str(f):sha(f)for f in sourcepaths},
        models=p.MODELS,fold_policy='exact original native train/held IDs, guard, seeds',
        position_and_reference_starts='same frozen fitted_c full-data RF endpoint/reference for all arms as original',
        solver_budget=dict(max_rounds=15,maxiter=25,maxfun=100),workers=4,BLAS_threads=1,
        qualification='phase_closed AND optimizer_success AND no boundary AND positive unfloored position curvature AND positive normalized predictive covariance. Numerical pass is not generalization/production qualification.',
        no_GPS=True,scope='Same conditional base-curved-family model and empirical-development leakage as original; no model selection or preprocessing refit claim.')
    p.write(ROOT/'protocol.json',protocol);(ROOT/'protocol.sha256').write_text(sha(ROOT/'protocol.json')+'\n')


def main():
    global CONTEXT
    freeze();p.family.configure();began=time.monotonic();allrows=[]
    for case in ['DS26-0309','DS26-0070']:
        d,z,_=e.load_case(case);CONTEXT=(d,z)
        old=json.loads((ROOT.parent/(case+'_results.json')).read_text())
        parts=json.loads((ROOT.parent/(case+'_protocol.json')).read_text())['folds']
        jobs=[(case,r,next(t for t in parts if t['fold']==r['fold']))for r in old['rows']]
        with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('fork')) as pool:
            for fut in as_completed([pool.submit(job,j)for j in jobs]):
                row=fut.result();allrows.append(row)
                name=f"{case}_{row['arm']}_f{row['fold']}_{row['solver']}_SD{row['SD_scale']:g}"
                p.write(ROOT/(name+'.json'),row)
                print(name,'ERROR'if'error'in row else dict(closed=row['phase_closed'],qualified=row['numerical_fit_qualified'],score=row['scores']['all']['negative_twice_log_density']),flush=True)
    p.write(ROOT/'results.json',dict(protocol_sha256=sha(ROOT/'protocol.json'),rows=allrows,seconds=time.monotonic()-began))


if __name__=='__main__':main()
