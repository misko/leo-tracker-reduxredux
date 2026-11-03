"""Bounded profile of existing acquisition on a response-free regional grid."""
import cProfile
import json
from pathlib import Path
import pstats
import time
import numpy as np
from window_inputs import prepare_scan
from acquisition_dot import DotTrackLikelihood, fibonacci_disk
from regression_batch import digest

HERE=Path(__file__).resolve().parent
scan,height,_=prepare_scan('DS9-F001')
cache={}
ports=[DotTrackLikelihood(t,scan.bank,scan.config,height,4.,geometry_cache=cache) for _,t in scan.tracks]
points=fibonacci_disk(128,250.)

def score():
    totals=np.zeros(len(points))
    for start in range(0,len(points),32):
        for port in ports:
            values=port(points[start:start+32],np.empty((1,0)))[:,0,:]
            maximum=values.max(axis=1)
            totals[start:start+32]+=maximum+np.log(np.exp(values-maximum[:,None]).sum(axis=1))
    return totals

profiler=cProfile.Profile();started=time.monotonic();profiler.enable();values=score();profiler.disable()
elapsed=time.monotonic()-started
stats=pstats.Stats(profiler)
rows=[dict(file=k[0],line=k[1],function=k[2],primitive_calls=v[0],calls=v[1],self_s=v[2],cumulative_s=v[3])
      for k,v in stats.stats.items()]
result=dict(unit=scan.unit_id,points=len(points),tracks=len(ports),wall_s=elapsed,
    scores_finite=bool(np.all(np.isfinite(values))),top_self_time=sorted(rows,key=lambda r:r['self_s'],reverse=True)[:20],
    top_cumulative_time=sorted(rows,key=lambda r:r['cumulative_s'],reverse=True)[:20],
    input_sha256=scan.inputs,source_sha256=digest(__file__),
    qualification='One128point microprofile on the unmodified scorer; includes first orbit/geometry cache fills but excludes preparation and the full adaptive grid search. Profiling overhead and host load apply. No algorithm change, model fit or GPS used.')
out=HERE/'acquisition-profile-v1.json'
with out.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
out.with_suffix('.sha256').write_text(digest(out)+'\n')
print(json.dumps(dict(wall_s=elapsed,top_self_time=result['top_self_time'][:8]),indent=2))
