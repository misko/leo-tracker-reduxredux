"""Bounded real-input score parity and alternating microtimings."""
import json
from pathlib import Path
import time
import numpy as np
from acquisition_blas import BlasTrackLikelihood
from window_inputs import prepare_scan
from acquisition_dot import DotTrackLikelihood, fibonacci_disk
from regression_batch import digest

HERE=Path(__file__).resolve().parent
scan,height,_=prepare_scan('DS9-F001');points=fibonacci_disk(128,250.)
families={}
for name,cls in [('original',DotTrackLikelihood),('blas',BlasTrackLikelihood)]:
    cache={}
    families[name]=[cls(t,scan.bank,scan.config,height,4.,geometry_cache=cache) for _,t in scan.tracks]

def score(ports):
    return np.stack([np.concatenate([p(points[i:i+32],np.empty((1,0)))[:,0,:]
                                    for i in range(0,len(points),32)]) for p in ports])

reference=score(families['original']);candidate=score(families['blas'])
assert np.array_equal(np.isfinite(reference),np.isfinite(candidate))
mask=np.isfinite(reference);error=float(np.max(abs(reference[mask]-candidate[mask])))
assert error<1e-6, error
timings={'original':[],'blas':[]}
for repetition in range(4):
    for name in (['original','blas'] if repetition%2==0 else ['blas','original']):
        start=time.monotonic();values=score(families[name]);timings[name].append(time.monotonic()-start)
        assert np.array_equal(np.isfinite(values),np.isfinite(reference))
        np.testing.assert_allclose(values[mask],reference[mask],atol=1e-6,rtol=0.)
result=dict(unit=scan.unit_id,points=len(points),tracks=len(families['original']),max_branch_score_error=error,
    timings_s=timings,speedup=float(np.median(timings['original'])/np.median(timings['blas'])),
    source_sha256={str(p):digest(p) for p in [Path(__file__),HERE/'acquisition_blas.py',
        HERE.parents[1]/'src/leo/analysis/localization_geometry_blas.py']},input_sha256=scan.inputs,
    qualification='128regional points, all50selected tracks, four alternating warm-cache repetitions. First parity pass fills both caches and is excluded from microtimings. Same branch support on these points; no claim of full-grid seed parity, cold-pipeline speedup or changed localization accuracy.')
out=HERE/'acquisition-blas-micro-v1.json'
with out.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
out.with_suffix('.sha256').write_text(digest(out)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['input_sha256','source_sha256']},indent=2))
