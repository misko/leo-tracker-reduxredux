"""Re-evaluate fixed cap15 endpoints only; no held-data optimizer or RF refit."""
import copy
import hashlib
import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import sys
import time
import traceback
import numpy as np
from bounded import correct_score

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import predictive as p
from algo07_science import engine as e
CONTEXT=None


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def freeze():
    source=[ROOT/'bounded.py',ROOT/'run.py',ROOT/'test_bounded.py',ROOT.parent/'predictive.py']
    inputfiles=[ROOT.parent/'extended/results.json']+[ROOT.parent/(c+'_protocol.json')for c in ['DS26-0309','DS26-0070']]
    protocol=dict(operation='exact bounded-box conditioning identity within frozen local joint Gaussian only',
        source_sha256={str(f):sha(f)for f in source},input_sha256={str(f):sha(f)for f in inputfiles},
        bounds_km=[[-12.5,12.5],[-12.5,12.5]],cells=48,subsets=['all','target','other'],
        covariance='C=diagonal noise plus nuisance covariance conditional on position; J is derivative of total training posterior mean; S is frozen cap15 position covariance',
        density='original Gaussian density times posterior-box-probability/prior-box-probability; analytic Gaussian position update solely for integration, no nuisance or RF parameter refit',
        quadrature='deterministic one-dimensional conditional-normal scaled quadrature, verified against seeded SciPy bivariate normal rectangle CDF',
        qualification='Preserve all original phase, optimizer, boundary and curvature flags. Box integration does not establish Laplace accuracy, empirical noise calibration, independent nomination or generalization.',
        workers=4,BLAS_threads=1,no_GPS=True,endpoint_optimization=False,
        scope='Post-hoc scientific debug, protocol frozen before bounded corrected scores; original and cap15 results preserved.')
    p.write(ROOT/'protocol.json',protocol);(ROOT/'protocol.sha256').write_text(sha(ROOT/'protocol.json')+'\n')


def job(old):
    d,z,parts=CONTEXT
    try:
        part=next(t for t in parts if t['fold']==old['fold']);ids,families=p.native(d['problems']['fitted_c'][0])
        train=np.isin(ids,part['train_ids']);test=np.isin(ids,part['held_ids'])
        dd=p.family.candidate_context(d,z,old['SD_scale'],family=old['norad']);dd=dict(dd,keep=train,entries=[],families=[])
        zz=copy.deepcopy(z);zz.pop('selected',None);zz.pop('gap_selected',None)
        problem,_=e.build(dd,zz,old['arm'],np.asarray(old['reference']))
        x=np.asarray(old['x_km']);c=problem.calculate(x);u=c['features'];g=problem.noise_groups[train]
        w=np.asarray(d['powers'])[g]*c['noise_precision'][g]/problem.point_noise[train]**2
        gram=np.diag(c['coefficient_prior_precision'])+u[train].T@(u[train]*w[:,None])
        nuisance=np.linalg.solve(np.linalg.cholesky(gram),u.T).T
        mean=problem.q*c['intercept']+u@c['coefficient'];derivatives=[]
        for k in range(2):
            delta=np.eye(2)[k]*.02;cp=problem.calculate(x+delta);cm=problem.calculate(x-delta)
            derivatives.append(((problem.q*cp['intercept']+cp['features']@cp['coefficient'])-
                                (problem.q*cm['intercept']+cm['features']@cm['coefficient']))/.04)
        jacobian=np.column_stack(derivatives);position_covariance=np.asarray(old['position_covariance_km2'])
        precision=c['noise_precision'][problem.noise_groups].copy();precision[precision<=0]=.5
        sigma=problem.point_noise/np.sqrt(precision);raw=problem.values-mean
        scores={};unbounded_checks={}
        for name,use in {'all':test,'target':test&(families==old['norad']),'other':test&(families!=old['norad'])}.items():
            reconstructed=p.normalized_gaussian(raw[use],sigma[use],np.column_stack((nuisance[use],jacobian[use]@np.linalg.cholesky(position_covariance))))
            original=old['scores'][name]['negative_twice_log_density'];unbounded_checks[name]=reconstructed['negative_twice_log_density']-original
            scores[name]=correct_score(original,raw[use],sigma[use],nuisance[use],jacobian[use],x,position_covariance)
            scores[name]['original_unbounded_negative_twice_log_density']=original
            scores[name]['points']=int(use.sum())
        return dict(case=old['case'],arm=old['arm'],fold=old['fold'],solver=old['solver'],SD_scale=old['SD_scale'],norad=old['norad'],
            phase_closed=old['phase_closed'],optimizer_success=old['optimizer_success'],boundary=old['boundary'],
            position_curvature_floored=old['position_curvature_floored'],original_numerical_fit_qualified=old['numerical_fit_qualified'],
            original_unqualified_reasons=old['unqualified_reasons'],scores=scores,reconstructed_unbounded_score_deltas=unbounded_checks,
            train_ids_sha256=old['train_ids_sha256'],held_ids_sha256=old['held_ids_sha256'],
            qualification='Exact box correction for declared local Gaussian only; inherited numerical/scientific limitations persist')
    except Exception:return dict(case=old['case'],arm=old['arm'],fold=old['fold'],solver=old['solver'],SD_scale=old['SD_scale'],error=traceback.format_exc())


def main():
    global CONTEXT
    freeze();p.family.configure();began=time.monotonic();out=[]
    old=json.loads((ROOT.parent/'extended/results.json').read_text())['rows']
    for case in ['DS26-0309','DS26-0070']:
        d,z,_=e.load_case(case);parts=json.loads((ROOT.parent/(case+'_protocol.json')).read_text())['folds'];CONTEXT=(d,z,parts)
        with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('fork'))as pool:
            for future in as_completed([pool.submit(job,r)for r in old if r['case']==case]):
                row=future.result();out.append(row);name=f"{case}_{row['arm']}_f{row['fold']}_{row['solver']}_SD{row['SD_scale']:g}"
                p.write(ROOT/(name+'.json'),row);print(name,'ERROR'if'error'in row else row['scores']['all']['correction_negative_twice_log_density'],flush=True)
    p.write(ROOT/'results.json',dict(protocol_sha256=sha(ROOT/'protocol.json'),rows=out,seconds=time.monotonic()-began))


if __name__=='__main__':main()
