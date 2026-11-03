"""Frozen raw-timing visibility position experiment; no reference access."""
import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy.optimize import minimize
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'acquisition_position'))
from common import base,read,digest,verify_sources
from fit import load
from position_run import audit
from raw_model import build


def main(cohort,index,arm,verify=False):
    assert (cohort,index) in (('original',0),('additional',1))
    started=time.monotonic();old,initial,sources=load(cohort,index,'doppler')
    bound=read(HERE.parent/'acquisition_position'/f'input-{cohort}-{index:02d}.json')
    calpath=HERE.parent/'raw_visibility/fit.json';calibration=read(calpath);verify_sources(calibration)
    assert calibration['screen']['passed']
    threshold_path=HERE.parent/'detection_evidence/soft-calibration.json';threshold=read(threshold_path)['threshold_us']
    config=read(base(cohort)/'plan.json')['config']
    model=build(old.geometry.document,config,bound,calibration,threshold,0. if arm=='doppler' else 1.)
    paths=[Path(__file__),HERE/'raw_model.py',HERE/'test_raw_model.py',HERE/'PROTOCOL.md',calpath,threshold_path,HERE.parent/'detection_evidence/epoch_pairs.py']
    sources.update({str(p):digest(p) for p in paths})
    first=model.evaluate(initial)
    if verify:
        zero=build(old.geometry.document,config,bound,calibration,threshold,0.).evaluate(initial)
        baseline=old.evaluate(initial)
        parity={k:float(np.max(abs(np.asarray(zero[k])-baseline[k]))) for k in ('score','gradient','expected_sources')}
        assert max(parity.values())<1e-7
        checked=audit(model,initial,first['gradient']);assert checked['discrepancy']<=.02
        result=dict(verified=True,parity=parity,derivative_audit=checked)
    else:
        def objective(x):
            value=model.evaluate(x);return -value['score'],-value['gradient']
        fit=minimize(objective,initial,method='L-BFGS-B',jac=True,bounds=[(-12.,12.),(-12.,12.),(-5.,5.)],options=dict(maxiter=100,ftol=1e-13,gtol=.001,maxls=25))
        final=model.evaluate(fit.x);checked=audit(model,fit.x,final['gradient'])
        margin=float(np.min(np.array([12.,12.,5.])-abs(fit.x)));gradient=float(np.max(abs(final['gradient'])))
        result=dict(x=fit.x.tolist(),coordinates_deg=model.geometry.coordinates(fit.x),initial_x=initial.tolist(),score=final['score'],expected_sources=final['expected_sources'],qualified=bool(fit.success and margin>=.001 and gradient<=.01 and checked['discrepancy']<=.02),derivative_audit=checked,bound_margin=margin,gradient_max=gradient,optimizer=dict(success=bool(fit.success),message=str(fit.message),iterations=int(fit.nit),evaluations=int(fit.nfev)))
    result.update(cohort=cohort,index=index,arm=arm,sources=sources,elapsed_s=time.monotonic()-started,reference_used=False,scope='conditional raw-match geometry; source-average composite, not physical visibility likelihood')
    prefix='verify' if verify else 'fit'
    with (HERE/f'{prefix}-{cohort}-{index:02d}-{arm}.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k!='sources'}),flush=True)


if __name__=='__main__':main(sys.argv[1],int(sys.argv[2]),sys.argv[3],'--verify' in sys.argv)
