"""Expose predictive posterior satellite moments while preserving receiver means.

The existing marginal likelihood is unchanged. This opt-in research projection
changes only requested satellite phase/orbit means used by residual diagnostics
and phase relinearization. Every existing observation must pass the new gates.
"""
import numpy as np
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from leo.analysis.research.predictive_track import selected_predictive_coordinates


def attach_shared_satellite_refresh(p,entries,powers,families):
    if not entries:return p
    families=sorted(set(families));begin=p.hardware.shape[1]+p.smooth.shape[1]
    if not set(families)<=set(p.labels):raise ValueError('shared family missing from model')
    indices=[begin+p.labels.index(j) for j in families]
    for j in families:
        if j in p.supported:
            start=begin+len(p.labels)+3*p.supported.index(j);indices.extend(range(start,start+3))
    view,_,sigma,groups,_=linear_geometry(p,entries)
    noise=np.diag(2*sigma*sigma)+300.**2*(groups[:,None]==groups[None,:])
    original=p.calculate
    def calculate(x):
        base=original(x);c=dict(base);h=geometry_features(view,x,0.)['features']
        g=p.noise_groups[p.keep];w=np.asarray(powers)[g]*base['noise_precision'][g]/p.point_noise[p.keep]**2
        u=base['features'][p.keep];gram=np.diag(base['coefficient_prior_precision'])+u.T@(u*w[:,None])
        covariance=np.linalg.solve(gram,np.eye(len(gram)))
        adjusted=selected_predictive_coordinates(base['coefficient'],covariance,h,
            base['linear_raw_prediction_residual_hz'],noise,indices)
        delta=adjusted-base['coefficient'];c['coefficient']=adjusted
        c['conditional_residual_hz']=base['conditional_residual_hz']-base['features']@delta
        c['linear_raw_prediction_residual_hz']=base['linear_raw_prediction_residual_hz']-h@delta
        c['shared_satellite_receiver_change']=float(np.max(abs(delta[:begin])))
        c['shared_satellite_coefficient_change']=delta
        c['shared_satellite_allowed_coordinates']=indices
        c['shared_satellite_original_coefficient']=base['coefficient']
        return c
    p.calculate=calculate;p.shared_satellite_families=families
    return p


def exact_shared_replay(p,x,entries):
    from investigate_ds23_0268_remaining_tracks import family_frequency
    c=p.calculate(x);begin=p.hardware.shape[1]+p.smooth.shape[1];stop=begin+len(p.labels)+3*len(p.supported)
    families=getattr(p,'shared_satellite_families',[]);phases=p.state(x)['phases'];maximum=0.
    all_entries=list(entries)+[dict(track_index=i,candidate_index=r['candidate_index'],alias=a)
        for r,i,a in zip(p.rows,p.members,p.alias,strict=True)]
    for e in all_entries:
        j=e['candidate_index']
        if j not in families:continue
        view,*_=linear_geometry(p,[e]);geometry=geometry_features(view,x,0.);t=p.scan.tracks[e['track_index']]
        exact,_=family_frequency(p,x,j,times=t['times'])
        linear=view.q*geometry['intercept']+geometry['features'][:,begin:stop]@c['coefficient'][begin:stop]
        maximum=max(maximum,float(np.max(abs(view.q*exact-linear))))
    return dict(families=families,phases_s={j:float(phases[j]) for j in families},
        phases_in_bounds=all(abs(phases[j])<=15 for j in families),maximum_phase_linearization_error_hz=maximum,
        receiver_coefficient_change=c.get('shared_satellite_receiver_change',0.))
