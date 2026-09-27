"""Exact finite-history accuracy gate for the approximate quality filter."""
from itertools import product
import json
import numpy as np
from scipy.special import logsumexp
from causal_quality import run_filter
from causal_quality_trial import OUT

def exact_evidence(residual,scales,times,flags,kind):
    residual=np.asarray(residual);scales=np.asarray(scales);paths=[]
    if len(scales)**len(residual)>100000:raise ValueError('exact audit is deliberately bounded')
    for states in product(range(len(scales)),repeat=len(residual)):
        logp=-np.log(len(scales))
        for i in range(1,len(residual)):
            h=0. if kind=='stationary' else -np.expm1(-(times[i]-times[i-1])/20)
            if kind=='timing_informed' and flags[i-1]:h=1-(1-h)*.5
            transition=h/len(scales)+(1-h)*(states[i]==states[i-1])
            if transition==0:logp=-np.inf;break
            logp+=np.log(transition)
        if not np.isfinite(logp):continue
        variance=scales[list(states)]**2;w=1/variance;W=w.sum();mean=w@residual/W
        ll=-.5*(len(residual)*np.log(2*np.pi)+np.log(variance).sum()+np.log1p(1e12*W)+np.sum(w*(residual-mean)**2)+mean**2/(1e12+1/W))
        paths.append(logp+ll)
    return float(logsumexp(paths))

def main():
    residual=np.array([0.,3.,1.,60.,40.,15.]);scales=np.array([5.,50.]);times=np.arange(6.);flags=np.zeros(6,bool);flags[2]=True
    rows=[]
    for kind in ('stationary','generic','timing_informed'):
        exact=exact_evidence(residual,scales,times,flags,kind)
        approximate=sum(r['log_predictive'] for r in run_filter(residual[None,None,:],np.zeros((1,1)),scales,times,flags,kind,warmup=0))
        rows.append(dict(model=kind,exact_log_evidence=exact,approximate_log_evidence=approximate,error_nats=approximate-exact,accuracy_gate_passed=abs(approximate-exact)<.05))
    result=dict(residual_hz=residual.tolist(),scales_hz=scales.tolist(),times_s=times.tolist(),flags=flags.tolist(),required_tolerance_nats=.05,comparisons=rows,overall_accuracy_gate_passed=all(r['accuracy_gate_passed'] for r in rows),meaning='An accuracy failure blocks treating real-data approximate gains as validated inference. This small case is not an error bound for longer real tracks.')
    (OUT/'accuracy-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
