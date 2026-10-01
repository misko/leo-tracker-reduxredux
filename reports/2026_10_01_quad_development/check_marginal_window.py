"""Complete marginal objective checks at fixed single, pair and quad states."""
import time
from pathlib import Path
import sys
import numpy as np
from run_association_ambiguity import HERE,source,baseline,setup,digest,verify_sources,save
from marginal_visibility_port import MarginalVisibilityPort
from marginal_window_objective import MarginalWindowObjective


def main():
    rows=[];inputs={}
    for unit in ['DS9-B01-S1','DS10-B01-D1','DS11-B01-Q']:
        begun=time.monotonic();receipt,bindings=source(unit);inputs.update(bindings)
        original,_,_=baseline(unit);hard=setup(unit,original)
        model=MarginalWindowObjective([MarginalVisibilityPort(p.original,.1) for p in hard.ports],hard.columns,hard.precision)
        state=np.asarray(receipt['best']['mean']);start=time.monotonic();value,g,labels=model.evaluate(state)
        gradient_seconds=time.monotonic()-start
        directions=[np.eye(1,len(state),i)[0] for i in [0,1]];rng=np.random.default_rng(402)
        for _ in range(3):
            d=rng.normal(size=len(state));d[:2]=0;d/=np.linalg.norm(d);directions.append(d)
        checks=[]
        for i,d in enumerate(directions):
            for h in [.0005,.0001]:
                # Always marginalize all branches; no fixed-label derivative.
                numeric=(model.evaluate(state+h*d,gradient=False)[0]-model.evaluate(state-h*d,gradient=False)[0])/(2*h)
                error=abs(numeric-float(g@d));assert error<.002,(unit,i,h,error)
                checks.append(dict(direction=i,step=h,analytic=float(g@d),numeric=numeric,error=error))
        rows.append(dict(unit=unit,value=value,gradient_norm=float(np.linalg.norm(g)),gradient_seconds=gradient_seconds,
            seconds=time.monotonic()-begun,checks=checks))
        print(unit,max(r['error'] for r in checks),gradient_seconds,flush=True)
    sources={str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])}
    verify_sources(inputs)
    save(HERE/'marginal-window-gradient-check-v1.json',dict(rows=rows,inputs=inputs,source_sha256=sources,
        qualification='Fixed accepted hard-model states, full-catalogue marginal objective plus Gaussian priors; five directions/two steps. No fitting or geographic scoring.'))


if __name__=='__main__':main()
