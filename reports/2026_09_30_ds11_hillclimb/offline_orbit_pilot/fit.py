import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy.optimize import minimize
from orbit_model import load,digest
from position_run import audit
HERE=Path(__file__).resolve().parent


def main(index,arm,start):
    started=time.monotonic();model,initial,sources=load(index,arm)
    seed=initial if start=='iid' else np.zeros(3)
    def objective(x):
        value=model.evaluate(x);return -value['score'],-value['gradient']
    fit=minimize(objective,seed,method='L-BFGS-B',jac=True,bounds=[(-12.,12.),(-12.,12.),(-5.,5.)],options=dict(maxiter=100,ftol=1e-13,gtol=.001,maxls=25))
    final=model.evaluate(fit.x);checked=audit(model,fit.x,final['gradient'])
    margin=float(np.min(np.array([12.,12.,5.])-abs(fit.x)));gradient=float(np.max(abs(final['gradient'])))
    diagnostic=model.diagnostics(fit.x);assert abs(diagnostic['training_score']-final['score'])<1e-8
    sources[str(Path(__file__))]=digest(Path(__file__))
    result=dict(index=index,arm=arm,start=start,x=fit.x.tolist(),coordinates_deg=model.engine.coordinates(fit.x),score=final['score'],qualified=bool(fit.success and margin>=.001 and gradient<=.01 and checked['discrepancy']<=.02),bound_margin=margin,gradient_max=gradient,derivative_audit=checked,optimizer=dict(success=bool(fit.success),message=str(fit.message),iterations=int(fit.nit),evaluations=int(fit.nfev)),diagnostics=diagnostic,offline_only=arm=='offline',reference_used=False,sources=sources,elapsed_s=time.monotonic()-started)
    with (HERE/f'fit-{index:02d}-{arm}-{start}.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k not in ('sources','diagnostics')}),flush=True)


if __name__=='__main__':main(int(sys.argv[1]),sys.argv[2],sys.argv[3])
