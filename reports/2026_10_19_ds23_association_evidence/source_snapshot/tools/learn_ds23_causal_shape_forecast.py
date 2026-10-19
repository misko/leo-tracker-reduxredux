"""Learn a signed phase-aligned orbit-shape forecast using only past TLE triples."""

import argparse
from pathlib import Path
import numpy as np
from sgp4.api import Satrec

from analyze_dsx01_fixed_site import ecef_states
from run_algo01_ds23_sample import read,write,sha
from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S,phase_shifted_states
from leo.sky.propagation import ElementSetCatalogue

SAMPLE_TIMES=np.array([-150.,0.,150.])
CANDIDATES=(0.,.25,.5,.75,1.)


def inertial_velocity(position,velocity):
    result=np.array(velocity,copy=True)
    result[...,0]-=EARTH_ROTATION_RAD_S*position[...,1]
    result[...,1]+=EARTH_ROTATION_RAD_S*position[...,0]
    return result


def rtn_axes(position,velocity):
    radial=position/np.linalg.norm(position,axis=-1,keepdims=True)
    normal=np.cross(position,inertial_velocity(position,velocity))
    normal/=np.linalg.norm(normal,axis=-1,keepdims=True)
    tangential=np.cross(normal,radial)
    return np.stack((radial,tangential,normal),axis=-2)


def align_shape(satellite,origin,times,reference_p,reference_v):
    cat=ElementSetCatalogue(('STARLINK',),(satellite.satnum,),(satellite,))
    other_p,_,good=ecef_states(cat,origin,times)
    if not good.all():raise ValueError('unaligned propagation failed')
    vi=inertial_velocity(reference_p,reference_v)
    phase=float(np.median(np.sum((other_p[0]-reference_p)*vi,axis=-1)/np.sum(vi*vi,axis=-1)))
    shifted=times-phase
    positions,velocities,good=ecef_states(cat,origin,shifted)
    if not good.all():raise ValueError('phase-aligned propagation failed')
    p,v=phase_shifted_states(dict(time_s=shifted,position_km=positions,velocity_km_s=velocities),times,-phase)
    return p[0]-reference_p,v[0]-reference_v,phase


def transition(a,b,c):
    target=c['collected_utc_ns']
    if not (a['collected_utc_ns']<=b['collected_utc_ns']<=target and a['epoch']<b['epoch']<c['epoch']<=target):
        return None,'noncausal_or_unordered'
    gap=(b['epoch']-a['epoch'])/1e9
    if gap<1:return None,'near_duplicate_epoch'
    satellites=[Satrec.twoline2rv(*r['lines']) for r in (a,b,c)]
    cat=ElementSetCatalogue(('STARLINK',),(satellites[1].satnum,),(satellites[1],))
    p,v,good=ecef_states(cat,target,SAMPLE_TIMES)
    if not good.all():return None,'reference_propagation_failed'
    try:
        old_p,old_v,old_phase=align_shape(satellites[0],target,SAMPLE_TIMES,p[0],v[0])
        next_p,next_v,next_phase=align_shape(satellites[2],target,SAMPLE_TIMES,p[0],v[0])
    except ValueError:return None,'aligned_propagation_failed'
    axes=rtn_axes(p[0],v[0])
    old=np.concatenate((np.einsum('tij,tj->ti',axes,old_p),150*np.einsum('tij,tj->ti',axes,old_v)),axis=1)
    innovation=np.concatenate((np.einsum('tij,tj->ti',axes,next_p),150*np.einsum('tij,tj->ti',axes,next_v)),axis=1)
    floor=np.array([.05,.05,.025,.05,.05,.025])
    scale=np.maximum(abs(old),floor)
    ratio=float(np.clip((target-b['epoch'])/1e9/gap,0,2))
    return dict(validation_time_ns=target,old_shape=old,next_shape=innovation,scale=scale,
        age_gap_ratio=ratio,old_phase_s=old_phase,next_phase_s=next_phase),None


def loss(rows,rho):
    if not rows:return None
    scores=[]
    for r in rows:
        residual=(np.array(r['next_shape'])+rho*r['age_gap_ratio']*np.array(r['old_shape']))/np.array(r['scale'])
        scores.append(np.log1p(float(np.mean(residual*residual))))
    return float(np.sum(scores))


def select(rows):
    if not rows:return dict(shrinkage=0.,scores=[],transitions=0)
    scores=[loss(rows,r) for r in CANDIDATES];k=int(np.argmin(scores))
    if 2*(scores[0]-scores[k])<=np.log(len(rows)):k=0
    return dict(shrinkage=CANDIDATES[k],scores=scores,transitions=len(rows))


def run(path):
    history=read(path);forecast=read(path.with_name(path.stem+'_forecast.json'))
    assert forecast['history_sha256']==sha(path)
    cutoff=history['cutoff_utc_ns'];rows=[];rejected={};attempted=0
    for number,versions in history['past_versions'].items():
        assert all(v['epoch']<=cutoff and v['collected_utc_ns']<=cutoff for v in versions)
        for k in range(2,len(versions)):
            attempted+=1;row,reason=transition(*versions[k-2:k+1])
            if row:rows.append(dict(norad=int(number),**row))
            else:rejected[reason]=rejected.get(reason,0)+1
    boundary=forecast['temporal_split_boundary_ns']
    training=[r for r in rows if r['validation_time_ns']<=boundary]
    validation=[r for r in rows if r['validation_time_ns']>boundary]
    prefix=select(training);full=select(rows)
    old,new=loss(validation,0),loss(validation,prefix['shrinkage'])
    gain=2*(old-new) if old is not None else 0.
    qualified=len(validation)>=30 and gain>np.log(len(validation))
    chosen=full['shrinkage'] if qualified else 0.
    output=path.with_name(path.stem+'_shape_forecast.json')
    write(output,dict(case=history['case'],chosen_shrinkage=chosen,qualified=qualified,
        prefix_selection=prefix,all_past_selection=full,validation_transitions=len(validation),validation_gain=gain,
        baseline_validation_loss=old,forecast_validation_loss=new,attempted_triples=attempted,rejected=rejected,
        history_sha256=sha(path),phase_forecast_sha256=sha(path.with_name(path.stem+'_forecast.json')),
        source_sha256=sha(Path(__file__)),GPS_or_radio_used=False,strictly_pre_RF=True,
        selector_is_robust_state_prediction_proxy_not_calibrated_probability=True,
        transitions=rows))
    print(history['case'],'shape shrinkage',chosen,'qualified',qualified,'validation gain',gain,'valid',len(rows),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('history',type=Path)
    run(parser.parse_args().history)
