"""Check internal bank velocity consistency without an orbit-truth claim."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

HERE=Path(__file__).resolve().parent
HILL=HERE.parent


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    results=[];sources={str(Path(__file__)):digest(Path(__file__))}
    for index in (0,16):
        path=HILL/f'pilot_fallback{index:02d}'/'run.py'
        spec=importlib.util.spec_from_file_location(f'velocity_source_{index}',path)
        p=importlib.util.module_from_spec(spec);sys.modules[spec.name]=p;spec.loader.exec_module(p)
        plan_path=path.with_name('plan.json');plan=p.read(plan_path)
        documents,fast,_,_=p.context(plan)
        sources.update(plan['sources']);sources[str(plan_path)]=digest(plan_path)
        grid=np.asarray(plan['config']['timing_grid_s']);assert np.all(np.diff(grid)>0)
        indices=sorted({int(np.argmin(abs(grid))),int(np.argmin(abs(grid-plan['control']['x'][2])))})
        for k in indices:
            assert 0<k<len(grid)-1 and abs(grid[k+1]-grid[k]-(grid[k]-grid[k-1]))<1e-12
            errors=[];speeds=[]
            for track in documents[0]['tracks']:
                position=track['candidate_position_km'];velocity=track['candidate_velocity_km_s']
                finite=(position[:,k+1]-position[:,k-1])/(grid[k+1]-grid[k-1])
                errors.extend((1000*np.linalg.norm(finite-velocity[:,k],axis=-1)).ravel().tolist())
                speeds.extend((1000*np.linalg.norm(velocity[:,k],axis=-1)).ravel().tolist())
            assert np.isfinite(errors).all()
            results.append(dict(scan_index=index,timing_grid_s=float(grid[k]),finite_difference_span_s=float(grid[k+1]-grid[k-1]),
                                bank_state_samples=len(errors),velocity_error_m_s_quantiles=np.quantile(errors,[0,.5,.9,1]).tolist(),
                                median_velocity_m_s=float(np.median(speeds)),
                                maximum_doppler_difference_bound_hz=float(max(errors)*11.2e9/299792458.)))
    output=dict(schema='ds11-bank-velocity-consistency/v1',results=results,position_fits=0,reference_used=False,
                validates_absolute_orbit_accuracy=False,sources=sources)
    with (HERE/'outcome.json').open('x') as stream:json.dump(output,stream,indent=2,allow_nan=False)
    print(json.dumps(results,indent=2))


if __name__=='__main__':
    main()
