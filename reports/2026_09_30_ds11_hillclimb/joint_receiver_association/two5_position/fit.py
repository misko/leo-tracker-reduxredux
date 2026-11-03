"""Training-only starts and exact partition/derivative preflight."""
import json
import sys
import time
import numpy as np
from scipy.optimize import minimize
from common import HERE,digest
from load import load
from position_run import audit


def main(cohort,index,arm,seed):
    start=time.monotonic();model,starts,original,sources=load(cohort,index,arm);initial=starts[seed]
    initial_score=model.evaluate(initial)['score']
    def objective(x):
        r=model.evaluate(x);return -r['score'],-r['gradient']
    fit=minimize(objective,initial,jac=True,method='L-BFGS-B',bounds=[(-12,12),(-12,12),(-5,5)],
                 options=dict(maxiter=100,ftol=1e-13,gtol=1e-6,maxls=25))
    final=model.evaluate(fit.x);checked=audit(model,fit.x,final['gradient'])
    margin=float(np.min(np.array([12,12,5])-abs(fit.x)));gradient=float(np.max(abs(final['gradient'])))
    result=dict(cohort=cohort,index=index,arm=arm,seed=seed,x=fit.x.tolist(),initial_x=initial.tolist(),
                coordinates_deg=model.geometry.coordinates(fit.x),score=final['score'],initial_score=initial_score,
                qualified=bool(fit.success and margin>=.001 and gradient<=.01 and checked['discrepancy']<=.02),
                bound_margin=margin,gradient_max=gradient,derivative_audit=checked,
                optimizer=dict(success=bool(fit.success),message=str(fit.message),evaluations=int(fit.nfev)),
                original_iid_qualified=original is not None and original['qualified'],reference_used=False,
                elapsed_s=time.monotonic()-start,sources={**sources,str(HERE/'fit.py'):digest(HERE/'fit.py')})
    with (HERE/f'fit-{cohort}-{index:02d}-{arm}-{seed}.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k!='sources'}),flush=True)


def preflight(cohort,index):
    start=time.monotonic();control,seeds,_,sources=load(cohort,index,'doppler');model,_,_,more=load(cohort,index,'signed');x=seeds[0]
    a=control.evaluate(x);b=control.evaluate(x,force_partition=True);r=model.evaluate(x);checked=audit(model,x,r['gradient'])
    parity=dict(score=abs(a['score']-b['score']),gradient=float(np.max(abs(a['gradient']-b['gradient']))))
    assert parity['score']<1e-8 and parity['gradient']<1e-7 and checked['discrepancy']<=.02
    result=dict(cohort=cohort,index=index,passed=True,parity=parity,derivative_audit=checked,elapsed_s=time.monotonic()-start,
                sources={**sources,**more,str(HERE/'fit.py'):digest(HERE/'fit.py')})
    with (HERE/f'preflight-{cohort}-{index:02d}.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k!='sources'}),flush=True)


if __name__=='__main__':
    if sys.argv[1]=='preflight':preflight(sys.argv[2],int(sys.argv[3]))
    else:main(sys.argv[1],int(sys.argv[2]),sys.argv[3],int(sys.argv[4]))
