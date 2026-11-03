"""Signed orbital-shape forecasts qualified on strictly pre-RF TLE transitions."""

import argparse
from pathlib import Path
import numpy as np
from sgp4.api import Satrec
from analyze_dsx01_fixed_site import ecef_states
from probe_ds23_history_calibrated_phase import HISTORY
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha
from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S
from leo.sky.propagation import ElementSetCatalogue

OUT=ROOT/'reports/2026_10_19_ds23_causal_shape_forecast'
BETAS=np.arange(-1.,1.01,.25)


def states(satellite,origin_ns,times):
    p,v,good=ecef_states(ElementSetCatalogue(('orbit',),(int(satellite.satnum),),(satellite,)),origin_ns,times)
    if not good.all():raise ValueError('causal validation propagation failed')
    return p[0],v[0]


def aligned_difference(older,position,velocity,origin_ns,times):
    p,v=states(older,origin_ns,times);inertial=velocity.copy()
    inertial[:,0]-=EARTH_ROTATION_RAD_S*position[:,1]
    inertial[:,1]+=EARTH_ROTATION_RAD_S*position[:,0]
    phase=float(np.median(np.sum((p-position)*inertial,axis=1)/np.sum(inertial*inertial,axis=1)))
    if not np.isfinite(phase) or abs(phase)>120:raise ValueError('phase alignment exceeds fixed 120 s diagnostic bound')
    p,v=states(older,origin_ns-int(round(phase*1e9)),times)
    angle=-EARTH_ROTATION_RAD_S*phase;cs,sn=np.cos(angle),np.sin(angle)
    for a in (p,v):
        x,y=a[:,0].copy(),a[:,1].copy();a[:,0]=cs*x-sn*y;a[:,1]=sn*x+cs*y
    return p-position,v-velocity,phase


def prefix_selection(rows):
    events=sorted({r['validation_time_ns'] for r in rows})
    if len(events)<3:return dict(qualified=False,beta=0.,reason='fewer than three causal publication events')
    cutoff=events[max(0,int(.7*len(events))-1)]
    train=[r for r in rows if r['validation_time_ns']<=cutoff];test=[r for r in rows if r['validation_time_ns']>cutoff]
    def loss(records,beta):
        return float(np.mean([np.log1p(np.sum((np.array(r['target_shape'])-beta*np.array(r['predictor_shape']))**2)/r['scale_km']**2) for r in records])) if records else 0.
    candidates=[dict(beta=float(b),loss=loss(train,b)) for b in BETAS]
    fitted=min(candidates,key=lambda r:(r['loss'],abs(r['beta'])))['beta']
    zero,proposed=loss(test,0),loss(test,fitted);improvement=(zero-proposed)/max(zero,1e-12)
    qualified=len(train)>=30 and len(test)>=30 and improvement>=.01
    return dict(qualified=qualified,beta=fitted if qualified else 0.,trained_beta=fitted,
        train_count=len(train),validation_count=len(test),publication_split_ns=cutoff,
        validation_zero_loss=zero,validation_forecast_loss=proposed,relative_improvement=improvement,
        training_candidates=candidates,minimum_relative_validation_gain=.01,
        no_future_publication_enters_earlier_training=True,validation_is_later_causal_TLE_not_orbit_truth=True)


def run(case):
    OUT.mkdir(parents=True,exist_ok=True);path=HISTORY/(case+'.json');history=read(path)
    assert history['latest_elements_sha256']==sha(SOURCE/case/'nominal_elements.json')
    cutoff=history['cutoff_utc_ns'];times=np.array([0.,150.,300.]);rows=[];skipped={}
    for number,versions in history['past_versions'].items():
        assert all(v['epoch']<=cutoff and v['collected_utc_ns']<=cutoff for v in versions)
        versions=sorted(versions,key=lambda r:r['epoch']);satellites=[Satrec.twoline2rv(*v['lines']) for v in versions]
        for k in range(2,len(versions)):
            a,b,c=versions[k-2:k+1];target=c['collected_utc_ns'];gap=(b['epoch']-a['epoch'])/1e9
            if gap<=0 or not a['collected_utc_ns']<=b['collected_utc_ns']<=target or any(v['epoch']>target for v in (a,b,c)):
                skipped['chronology']=skipped.get('chronology',0)+1;continue
            try:
                p,v=states(satellites[k-1],target,times)
                dp,dv,phase_a=aligned_difference(satellites[k-2],p,v,target,times)
                tp,tv,phase_c=aligned_difference(satellites[k],p,v,target,times)
            except ValueError as error:
                key=str(error);skipped[key]=skipped.get(key,0)+1;continue
            innovation=np.r_[dp.ravel(),150*dv.ravel()];observed=np.r_[tp.ravel(),150*tv.ravel()]
            ratio=float(np.clip((target-b['epoch'])/1e9/gap,0,2))
            rows.append(dict(norad=int(number),validation_time_ns=target,version_epochs=[a['epoch'],b['epoch'],c['epoch']],
                predictor_shape=ratio*innovation,target_shape=observed,scale_km=max(.05,float(np.linalg.norm(innovation))),
                age_gap_ratio=ratio,previous_phase_s=phase_a,later_phase_s=phase_c))
    selection=prefix_selection(rows)
    write(OUT/(case+'.json'),dict(case=case,selection=selection,transitions=rows,skipped=skipped,
        candidates=len(history['past_versions']),history_sha256=sha(path),cutoff_utc_ns=cutoff,
        signed_coefficients=BETAS,existing_phase_prior_unchanged=True,
        shape_is_position_and_150s_scaled_velocity_after_phase_alignment=True,
        no_GPS_RF_or_post_scan_TLE_used=True,source_sha256=sha(Path(__file__))))
    print(case,'shape forecast',selection,'rows',len(rows),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True);run(parser.parse_args().case)
