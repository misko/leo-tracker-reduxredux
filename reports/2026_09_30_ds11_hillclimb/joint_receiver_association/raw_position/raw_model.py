"""Conditional raw-match geometry averaged per hypothesized physical source."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import numpy as np

PARENT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(PARENT))
sys.path.insert(0,str(PARENT/'detection_evidence'))
from epoch_pairs import delta_us
from source_partition_fast import partition
from doppler_pilot import fast


def source_average(k,windows,values,derivatives):
    """Windows contain (local track bit, point index, stable raw-anchor rank)."""
    subsets=np.arange(1<<k);scores=np.zeros(len(subsets));gradient=np.zeros((len(subsets),derivatives[0].shape[-1]));count=np.zeros(len(subsets))
    for points in windows:
        claimed=np.zeros(len(subsets),bool)
        for track,point,rank in sorted(set(points),key=lambda r:r[2]):
            take=((subsets>>track)&1).astype(bool)&~claimed
            scores[take]+=values[track][point];gradient[take]+=derivatives[track][point]
            claimed|=take
        count+=claimed
    divisor=np.maximum(1,count)
    return scores/divisor,gradient/divisor[:,None]


def build(doc,config,bound,calibration,threshold,strength=1.):
    spec=importlib.util.spec_from_file_location('isolated_raw_source',PARENT/'whole_source_position.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    model=module.WholeSourcePosition(doc,config,bound,{},'doppler')
    raw={};hits={}
    for o in bound['opportunities']:
        for rx in (0,1):
            opposite=o['receivers'][f'rx{1-rx}']['candidates']
            for c in o['receivers'][f'rx{rx}']['candidates']:
                cid=c['projected_candidate_id']
                if cid is None:continue
                raw[cid]=hashlib.sha256(cid.encode()).digest()
                hits[cid]=any(b['passed_fractional_margin_gate'] and abs(delta_us(c,b,o['source_window']['sample_rate_hz'],750.))<=threshold for b in opposite)
    frequencies=sorted({t['rf_hz'] for t in model.tracks.values()})
    signed=np.array(calibration['arms']['signed']['selected']['parameters'])
    null=np.array(calibration['arms']['receiver']['selected']['parameters'])
    observed={t:np.array([hits[c] for c in m['candidate_ids']],float) for t,m in model.meta.items()}
    contexts=[]
    for lane in model.lanes:
        tids=sorted(lane['left']+lane['right'])
        candidates=sorted({c for t in tids for c in model.meta[t]['candidate_norad']})
        for branch in lane['ownership_alternatives']:
            templates=[]
            for candidate in candidates:
                selected=[t for t in tids if candidate in model.meta[t]['candidate_norad']]
                windows={}
                for local,tid in enumerate(selected):
                    meta=model.meta[tid]
                    for point,cid in enumerate(meta['candidate_ids']):
                        if not model.tracks[tid]['mask'][point] or branch['assignment'].get(cid,tid)!=tid:continue
                        windows.setdefault(meta['window_ids'][point],[]).append((local,point,raw[cid]))
                templates.append((selected,[model.meta[t]['candidate_norad'].index(candidate) for t in selected],list(windows.values())))
            contexts.append(templates)

    def terms(tid,x):
        track=model.tracks[tid];meta=model.meta[tid]
        rec,_=fast.baseline.site(*model.geometry.coordinates(x))
        tau=model.geometry.taus;hi=min(max(int(np.searchsorted(tau,x[2],side='right')),1),len(tau)-1);lo=hi-1
        fraction=(x[2]-tau[lo])/(tau[hi]-tau[lo])
        pos=track['candidate_position_km'][:,lo]*(1-fraction)+track['candidate_position_km'][:,hi]*fraction
        direction=pos-rec;direction/=np.linalg.norm(direction,axis=-1)[...,None]
        lat,lon=np.radians(model.geometry.coordinates(x))
        up=np.array([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)])
        east=np.array([-np.sin(lon),np.cos(lon),0.])
        other=1-meta['receiver'];rf=frequencies.index(meta['rf_hz']);h=observed[tid]
        eta=signed[2*rf+other]+signed[-1]*(np.cos(np.radians(10))*(direction@up)+np.sin(np.radians(10))*(2*other-1)*(direction@east))
        eta0=null[2*rf+other]
        return strength*(h*eta-np.logaddexp(0.,eta)-(h*eta0-np.logaddexp(0.,eta0)))

    original=model.evaluate
    def evaluate(x,gradient=True,held=False):
        if held:raise ValueError('This source-averaged composite has no held predictive-density interpretation')
        x=np.asarray(x,float);values={};derivatives={}
        for tid in model.tracks:
            values[tid]=terms(tid,x);derivatives[tid]=np.zeros(values[tid].shape+(4 if gradient else 1,))
            if gradient:
                for axis,step in enumerate((1e-4,1e-4,1e-5)):
                    plus=x.copy();minus=x.copy();plus[axis]+=step;minus[axis]-=step
                    if axis==2:plus[axis]=min(5.,plus[axis]);minus[axis]=max(-5.,minus[axis])
                    derivatives[tid][...,axis]=(terms(tid,plus)-terms(tid,minus))/(plus[axis]-minus[axis])
        queue=iter(contexts)
        def modified(n,factors):
            templates=next(queue);adjusted=[]
            assert len(templates)==len(factors)
            for (support,score,grad),(selected,indices,windows) in zip(factors,templates,strict=True):
                extra,dextra=source_average(len(selected),windows,[values[t][i] for t,i in zip(selected,indices,strict=True)],[derivatives[t][i] for t,i in zip(selected,indices,strict=True)])
                adjusted.append((support,score+extra,grad+dextra))
            return partition(n,adjusted)
        module.partition=modified
        result=original(x,gradient=gradient,force_partition=True)
        assert next(queue,None) is None
        return result
    model.evaluate=evaluate
    return model
