"""Quantify classical travel-time correction using immutable causal banks."""
import importlib.util
import json
from pathlib import Path
import sys
import time
import numpy as np
from core import retarded,C
HERE=Path(__file__).resolve().parent
HILL=HERE.parent
sys.path.insert(0,str(HILL/'joint_orbit_uncertainty'))
spec=importlib.util.spec_from_file_location('light_time_context',HILL/'joint_orbit_uncertainty/run.py')
context=importlib.util.module_from_spec(spec);spec.loader.exec_module(context)
fast=context.fast
def quantiles(v):return np.quantile(np.abs(np.concatenate(v)),[0,.5,.9,.99,1]).tolist()
def main():
    started=time.monotonic();rows=[];sources={}
    for index in (0,16):
        doc,_,config,_,_,x,_,bound=context.context(index);sources.update(bound)
        model=fast.Stationary(doc,config);receiver,_=fast.baseline.site(*model.coordinates(x))
        grid=np.array(config['timing_grid_s']);hi=np.searchsorted(grid,x[2],side='right');lo=hi-1
        assert 0<=lo<hi<len(grid);weight=(x[2]-grid[lo])/(grid[hi]-grid[lo])
        all_delta=[];all_shape=[];map_delta=[];map_shape=[];delays=[];tracks=[]
        for t in doc['tracks']:
            pp=t['candidate_position_km'];vv=t['candidate_velocity_km_s']
            p=pp[:,lo]*(1-weight)+pp[:,hi]*weight;v=vv[:,lo]*(1-weight)+vv[:,hi]*weight
            acceleration=(vv[:,hi]-vv[:,lo])/(grid[hi]-grid[lo])
            rate,delay,_=retarded(p,v,acceleration,receiver)
            original,visible=model.prediction(t,x);corrected=-11.2e9/C*rate
            delta=corrected-original;shape=delta-delta[:,t['mask']].mean(axis=1)[:,None]
            score,_,audits,_=fast.profile(t['y'][None,:]-original,t['mask'])
            assert all(a['converged'] for a in audits)
            selected=int(np.argmax(np.where(visible,score,-np.inf)))
            all_delta.append(delta.ravel());all_shape.append(shape.ravel());delays.append(delay.ravel())
            map_delta.append(delta[selected]);map_shape.append(shape[selected])
            tracks.append(dict(track_id=t['track_id'],map_slot=selected,
                               map_shape_rms_hz=float(np.sqrt(np.mean(shape[selected]**2)))))
        rows.append(dict(index=index,tracks=tracks,all_absolute_hz=quantiles(all_delta),all_centered_hz=quantiles(all_shape),
                         map_absolute_hz=quantiles(map_delta),map_centered_hz=quantiles(map_shape),delay_s=quantiles(delays)))
    for p in (Path(__file__),HERE/'core.py',HERE/'test_core.py',HERE/'PROTOCOL.md'):sources[str(p)]=context.digest(p)
    result=dict(rows=rows,quantile_levels=[0,.5,.9,.99,1],sources=sources,position_fits=0,reference_used=False,elapsed_s=time.monotonic()-started)
    with (HERE/'outcome.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps([{k:v for k,v in row.items() if k!='tracks'} for row in rows],indent=2))
if __name__=='__main__':main()
