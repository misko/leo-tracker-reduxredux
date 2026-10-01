"""Full-catalogue marginal gradients on entropy-selected recorded tracks, no fit."""
import time
from pathlib import Path
import sys
import numpy as np
from run_association_ambiguity import HERE,OUT,source,baseline,setup,sealed,digest,verify_sources,save
from marginal_visibility_port import MarginalVisibilityPort


def main():
    rows=[];inputs={}
    for dataset in ['DS9','DS10','DS11']:
        begun=time.monotonic();unit=dataset+'-B01-S1';masspath=OUT/(unit+'.json');mass=sealed(masspath)
        track=max(mass['rows'],key=lambda r:r['entropy'])['track']
        receipt,bindings=source(unit);inputs.update(bindings);inputs[str(masspath)]=digest(masspath)
        original,_,_=baseline(unit);model=setup(unit,original)
        base=model.ports[track];columns=model.columns[track]
        port=MarginalVisibilityPort(base.original,.1);state=np.asarray(receipt['best']['mean'])[columns]
        started=time.monotonic();value,gradient=port.marginal_score_gradient(state);gradient_seconds=time.monotonic()-started
        order=np.argsort(-port.score_all(state));epochs=[5+int(i) for i in order if i<port.candidate_count][:2]
        checks=[]
        for i in [0,1,2,3,4]+epochs:
            d=np.eye(1,len(state),i)[0]*1e-4
            numeric=(port.marginal_score(state+d)-port.marginal_score(state-d))/2e-4
            error=abs(numeric-gradient[i]);assert error<.002,(unit,i,error)
            checks.append(dict(coordinate=i,analytic=float(gradient[i]),numeric=numeric,error=float(error)))
        rows.append(dict(unit=unit,track=track,selection='largest conditional entropy among tracks, no geography',
            value=value,checks=checks,gradient_seconds=gradient_seconds,seconds=time.monotonic()-begun))
        print(unit,track,max(r['error'] for r in checks),gradient_seconds,flush=True)
    sources={str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])}
    verify_sources(inputs)
    save(HERE/'marginal-visibility-gradient-check-v1.json',dict(rows=rows,inputs=inputs,source_sha256=sources,
        qualification='Full catalogue logsumexp gradients, three entropy-selected single-scan tracks, seven coordinates each. No fitting, window-level validation or geographic scoring.'))


if __name__=='__main__':main()
