"""Preserve the failed reference case and broaden finite-history accuracy checks."""
from pathlib import Path
import json
import numpy as np
from quality_mixture import run_mixture
from causal_quality_accuracy import exact_evidence
from segment_catalogue_trial import SCALES

HERE=Path(__file__).resolve().parent
OUT=HERE/'quality-mixture'

def main():
    OUT.mkdir(exist_ok=True);rng=np.random.default_rng(20260927);cases=[np.array([0.,3.,1.,60.,40.,15.])]
    cases.extend(rng.normal(size=6)*np.array([5,5,5,50,50,50]) for _ in range(8))
    rows=[];times=np.arange(6.);flags=np.array([0,0,1,0,0,0],bool)
    for case,r in enumerate(cases):
        for kind in ('generic','timing_informed'):
            exact=exact_evidence(r,[5.,50.],times,flags,kind)
            for k in (1,2,4,8,16,32):
                approximate=sum(x['log_predictive'] for x in run_mixture(r[None,None,:],np.zeros((1,1)),[5.,50.],times,flags,kind,warmup=0,components=k))
                rows.append(dict(case=case,model=kind,components=k,exact=exact,approximate=approximate,error_nats=approximate-exact,passes=abs(approximate-exact)<.05))
    summaries=[dict(components=k,max_absolute_error_nats=max(abs(r['error_nats']) for r in rows if r['components']==k),all_cases_pass=all(r['passes'] for r in rows if r['components']==k)) for k in (1,2,4,8,16,32)]
    full_r=np.array([0.,1.,50.,100.]);full_t=np.arange(4.);full_flags=np.array([0,1,0,0],bool);full_rows=[]
    for kind in ('generic','timing_informed'):
        exact=exact_evidence(full_r,SCALES,full_t,full_flags,kind)
        for k in (2,4,8,16,32):
            approximate=sum(x['log_predictive'] for x in run_mixture(full_r[None,None,:],np.zeros((1,1)),SCALES,full_t,full_flags,kind,warmup=0,components=k))
            full_rows.append(dict(model=kind,components=k,exact=exact,approximate=approximate,error_nats=approximate-exact,passes=abs(approximate-exact)<.05))
    result=dict(seed=20260927,cases=[r.tolist() for r in cases],scales_hz=[5,50],times_s=times.tolist(),flags=flags.tolist(),tolerance_nats=.05,summaries=summaries,comparisons=rows,full_scale_case=dict(residual_hz=full_r.tolist(),times_s=full_t.tolist(),flags=full_flags.tolist(),scales_hz=SCALES,comparisons=full_rows),meaning='Exact finite-history validation on declared small cases; not a bound for long real tracks.')
    (OUT/'accuracy-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(two_state=summaries,ten_state=full_rows),indent=2))

if __name__=='__main__':main()
