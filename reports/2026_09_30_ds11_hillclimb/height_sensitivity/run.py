"""Conditional local effect of unknown ellipsoidal receiver height."""
import importlib.util
import json
from pathlib import Path
import sys
import time
import numpy as np
from core import project
HERE=Path(__file__).resolve().parent;HILL=HERE.parent
sys.path.insert(0,str(HILL/'joint_orbit_uncertainty'))
spec=importlib.util.spec_from_file_location('height_context',HILL/'joint_orbit_uncertainty/run.py')
context=importlib.util.module_from_spec(spec);spec.loader.exec_module(context)
fast=context.fast

def height_prediction(track,model,x,height):
    receiver,up=fast.baseline.site(*model.coordinates(x));receiver=receiver+height*up
    grid=model.taus;hi=np.searchsorted(grid,x[2],side='right');lo=hi-1
    assert 0<=lo<hi<len(grid)
    w=(x[2]-grid[lo])/(grid[hi]-grid[lo])
    p=track['candidate_position_km'][:,lo]*(1-w)+track['candidate_position_km'][:,hi]*w
    v=track['candidate_velocity_km_s'][:,lo]*(1-w)+track['candidate_velocity_km_s'][:,hi]*w
    unit=p-receiver;unit/=np.linalg.norm(unit,axis=-1)[...,None]
    return -fast.REFERENCE_RF_HZ/fast.baseline.LIGHT_KM_S*np.sum(unit*v,axis=-1)

def main():
    start=time.monotonic();rows=[];sources={}
    metadata=HERE.parents[2]/'deploy/station/gauss-r20-roof-20260926-v1.json'
    assert context.read(metadata)['altitude_m'] is None
    for index in (0,16):
        doc,_,config,_,_,x,_,bound=context.context(index);sources.update(bound)
        model=fast.Stationary(doc,config);data=[];parity=0.;difference=0.
        for t in doc['tracks']:
            prediction,visible=model.prediction(t,x);mask=t['mask']
            parity=max(parity,float(np.max(abs(prediction-height_prediction(t,model,x,0)))))
            score,_,audits,offsets=fast.profile(t['y'][None,:]-prediction,mask)
            assert all(a['converged'] for a in audits)
            k=int(np.argmax(np.where(visible,score,-np.inf)))
            residual=t['y'][mask]-prediction[k,mask]-offsets[k]
            h=(height_prediction(t,model,x,.001)-height_prediction(t,model,x,-.001))/.002
            coarse=(height_prediction(t,model,x,.01)-height_prediction(t,model,x,-.01))/.02
            difference=max(difference,float(np.max(abs(h-coarse))))
            columns=[]
            for axis,step in enumerate((1e-4,1e-4,1e-5)):
                d=np.eye(3)[axis]*step
                columns.append(((model.prediction(t,x+d)[0]-model.prediction(t,x-d)[0])/(2*step))[k,mask])
            data.append((np.column_stack(columns),h[k,mask],5/(4+(residual/100)**2)))
        arms={}
        for arm in ('equal','irls'):
            jj=[];hh=[];ww=[]
            for jac,h,w in data:
                weight=np.ones(len(h)) if arm=='equal' else w
                jj.append(jac-np.average(jac,axis=0,weights=weight));hh.append(h-np.average(h,weights=weight));ww.append(weight)
            result=project(np.concatenate(jj),np.concatenate(hh),np.concatenate(ww))
            c=result['compensation_per_km_height'];result['horizontal_alias_m_per_100m_height']=100*float(np.linalg.norm(c[:2]))
            result['timing_alias_s_per_100m_height']=.1*c[2];arms[arm]=result
        assert parity<1e-8 and difference<.001
        rows.append(dict(index=index,tracks=len(data),training_rows=sum(len(d[1]) for d in data),arms=arms,
                         zero_height_parity_hz=parity,height_derivative_step_difference_hz_per_km=difference))
    for p in (metadata,Path(__file__),HERE/'core.py',HERE/'test_core.py',HERE/'PROTOCOL.md'):sources[str(p)]=context.digest(p)
    result=dict(rows=rows,sources=sources,position_fits=0,reference_used=False,altitude_estimated=False,elapsed_s=time.monotonic()-start)
    with (HERE/'outcome.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
