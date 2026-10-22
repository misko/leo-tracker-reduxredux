"""Native GLRT prediction using the exact receiver basis of a recovered graph.

This research adapter changes no saved observation or calibration contract.
It extends the existing temporal discovery helper to the fine receiver basis.
"""

from types import SimpleNamespace

import numpy as np

from ds23_temporal_predictive_recovery import calibration,append_fragments
from ds23_receiver_family_search import fine_receiver_basis
from ds23_height_problem import geometry_features
from ds23_exact_native_time_union import exact_time_union
from leo.analysis.research.retained_track_likelihood import PERIOD,projected_receiver_basis


def receiver_basis(scan):
    """Identify a known basis by numerical parity, rather than width alone."""
    for basis in [projected_receiver_basis,fine_receiver_basis]:
        if all(np.asarray(saved).shape==basis(track['times']).shape and
               np.allclose(saved,basis(track['times']),rtol=1e-12,atol=1e-12)
               for track,saved in zip(scan.tracks,scan.rx_basis,strict=True)):
            return basis
    raise ValueError('unrecognized receiver basis; do not approximate orphan geometry')


def geometry_view(p,observations,basis):
    active=sorted({r['candidate_index'] for r,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()})
    if not active or not observations:raise ValueError('active curved families and native GLRT required')
    t=np.array([o['time_s'] for o in observations]);rf=np.array([o['actual_rf_hz'] for o in observations]);n=len(t)
    hardware=np.zeros((n,p.hardware.shape[1]));smooth=np.zeros((n,p.smooth.shape[1]));width=p.smooth.shape[1]//2
    b=basis(t)
    if b.shape!=(n,width):raise ValueError('receiver basis width differs from current calibration')
    for k,o in enumerate(observations):
        rx=o['receiver']-1;band=int(o['channel']>4)
        hardware[k,2*rx+band]=PERIOD/np.sqrt(12)
        hardware[k,4+2*rx]=t[k]-150
        hardware[k,5+2*rx]=(t[k]-150)*(-1 if band==0 else 1)*.5
        if p.fitted_c:hardware[k,8]=(rf[k]/1e9-11.5)*200000
        smooth[k,rx*width:(rx+1)*width]=(rf[k]/11.5e9)*b[k]
    fields=dict(vars(p));fields.update(flat_times=np.tile(t,len(active)),
        flat_labels=np.repeat([p.labels.index(j) for j in active],n),q=np.tile(rf/11.5e9,len(active)),
        hardware=np.tile(hardware,(len(active),1)),smooth=np.tile(smooth,(len(active),1)),
        constants=np.zeros((len(active)*n,p.constants.shape[1])))
    return SimpleNamespace(**fields),active


def predictions(p,x,powers,observations,basis):
    c,covariance=calibration(p,x,powers);view,active=geometry_view(p,observations,basis)
    geometry=geometry_features(view,x,0.);u=geometry['features'];n=len(observations);f=len(active)
    mean=view.q*geometry['intercept']+u@c['coefficient'];meta=p.scan.fixed_window_noise
    sigma=np.array([meta['per_observation_noise_sigma_hz'][o['observation_id']]
        if meta['extra_parameter_BIC_gain']>0 else p.scan.radio_sigma_hz for o in observations])
    return dict(mean=mean.reshape(f,n).T,variance=(np.sum((u@covariance)*u,axis=1).reshape(f,n)+300.**2).T,
        native_sigma=sigma,visible=(geometry['elevation'].reshape(f,n)>=0).T,active=active,
        features=u.reshape(f,n,-1).transpose(1,0,2),covariance=covariance)


def append_native_paths(scan,old_entries,fragments,basis):
    changed,entries=append_fragments(scan,old_entries,fragments)
    for i in range(len(scan.tracks),len(changed.tracks)):
        changed.rx_basis[i]=basis(changed.tracks[i]['times'])
    if changed.curved!=scan.curved:raise ValueError('native paths must not calibrate')
    return exact_time_union(changed),entries
