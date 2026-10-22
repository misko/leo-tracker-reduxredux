"""Joint prediction for new families; original curved calibration stays fixed.

New-family phase uncertainty is a declared Gaussian moment approximation of
the causal forecast. Three Gaussian physical orbit modes use existing causal
TLE scales. No new measurement enters the curved calibration normal equations.
"""

import numpy as np
from scipy.linalg import block_diag
from scipy.special import logsumexp

from build_dsx01_orbit_modes import build_modes
from ds23_conditioned_relative_nomination import unresolved_curve_score
from ds23_predictive_linear import linear_geometry,predictive_residual
from ds23_height_problem import geometry_features
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.retained_track_likelihood import PERIOD,profile
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from prototype_dsx01_continuous_position import latlon


def wrapped_curve_score(times,values,sigma):
    """Proper broad curve density summed over common whole-fragment aliases."""
    y=np.asarray(values,float);center=np.rint(np.mean(y)/PERIOD)*PERIOD;y=y-center
    scores=[unresolved_curve_score(times,y+k*PERIOD,sigma) for k in range(-4,5)]
    return float(-2*logsumexp(-.5*np.asarray(scores)))


def joint_prediction(old_raw,old_design,new_raw,new_design,new_modes,curved_gram,sigma,groups):
    old_raw,new_raw=np.asarray(old_raw),np.asarray(new_raw)
    old_design,new_design,new_modes=map(np.asarray,(old_design,new_design,new_modes))
    if old_design.shape[1]!=new_design.shape[1] or new_modes.shape[0]!=len(new_raw):raise ValueError('shared calibration coordinates required')
    width=new_modes.shape[1]
    design=np.vstack((np.column_stack((old_design,np.zeros((len(old_raw),width)))),np.column_stack((new_design,new_modes))))
    gram=block_diag(curved_gram,np.eye(width))
    return predictive_residual(np.r_[old_raw,new_raw],design,gram,np.asarray(sigma),np.asarray(groups,int))


def attach_new_families(p,d,old_entries,new_entries,references,*,physical_modes=True):
    if not new_entries:raise ValueError('new predictive family entries required')
    if hasattr(p,'curved_calculate'):raise ValueError('attach to the curved model once; old prediction is integrated jointly here')
    active={r['candidate_index'] for r,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()}
    families=sorted({e['candidate_index'] for e in new_entries})
    if set(families)&(active|{e['candidate_index'] for e in old_entries}):raise ValueError('new-family prediction must not duplicate an incumbent family')
    refs=np.asarray(references,float)
    if refs.shape!=(len(families),):raise ValueError('one linearization reference per new family')
    all_ids=[o for e in old_entries+new_entries for o in e['observation_ids']]
    curved_ids={o for i,sl in zip(p.members,p.slices,strict=True) for o,keep in zip(p.scan.tracks[i]['observation_ids'],p.keep[sl],strict=True) if keep}
    if len(all_ids)!=len(set(all_ids)) or curved_ids&set(all_ids):raise ValueError('physical predictive observations must be disjoint from each other and calibration')
    if old_entries:old_view,old_values,old_sigma,old_groups,old_slices=linear_geometry(p,old_entries)
    else:old_view=None;old_values=np.array([]);old_sigma=np.array([]);old_groups=np.array([],int);old_slices=[]
    dummy=[dict(e,candidate_index=p.labels[0]) for e in new_entries]
    new_view,new_values,new_sigma,new_groups,new_slices=linear_geometry(p,dummy)
    family_points=np.concatenate([np.full(e['points'],families.index(e['candidate_index']),int) for e in new_entries])
    nb=p.hardware.shape[1]+p.smooth.shape[1];width_per_family=4 if physical_modes else 1
    banks={};modes={};metadata={}
    for j in families:
        banks[j]=dict(time_s=p.scan.sky['time_s'],position_km=p.scan.sky['position_km'][[j]],velocity_km_s=p.scan.sky['velocity_km_s'][[j]])
        if physical_modes:modes[j],record=build_modes(p.scan,[j],[j],'physical');metadata[j]=record[j]
    curved=p.calculate
    def calculate(position):
        c=curved(position);g=p.noise_groups[p.keep];u=c['features'][p.keep]
        w=np.asarray(d['powers'])[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*w[:,None]);dimension=len(c['coefficient'])
        old_geometry=geometry_features(old_view,position,0.) if old_entries else None
        old_design=old_geometry['features'] if old_entries else np.zeros((0,dimension))
        old_mean=old_view.q*old_geometry['intercept']+old_design@c['coefficient'] if old_entries else np.array([])
        radio=geometry_features(new_view,position,0.)['features'].copy();radio[:,nb:]=0.
        mean=radio@c['coefficient'];extra=np.zeros((len(new_values),width_per_family*len(families)));elevation=np.zeros(len(new_values))
        for local,j in enumerate(families):
            use=np.flatnonzero(family_points==local);times=new_view.flat_times[use];reference=refs[local]
            freq,el=paired_phase_frequency(banks[j],times,np.zeros(len(times),int),np.array([reference]),*latlon(position))
            plus=paired_phase_frequency(banks[j],times,np.zeros(len(times),int),np.array([reference+.01]),*latlon(position))[0]
            minus=paired_phase_frequency(banks[j],times,np.zeros(len(times),int),np.array([reference-.01]),*latlon(position))[0]
            derivative=(plus[0]-minus[0])/.02;q=new_view.q[use];prior_mean=float(d['all_means'][j]);sd=float(d['widths'][j])
            mean[use]+=q*(freq[0]+derivative*(prior_mean-reference));elevation[use]=el[0]
            extra[use,width_per_family*local]=q*derivative*sd
            if physical_modes:
                mode=paired_frequency_modes(banks[j],modes[j],times,np.zeros(len(times),int),np.array([reference]),*latlon(position))
                extra[np.ix_(use,np.arange(width_per_family*local+1,width_per_family*(local+1)))]=q[:,None]*mode
        prediction=joint_prediction(old_values-old_mean,old_design,new_values-mean,radio,extra,gram,
            np.r_[old_sigma,new_sigma]*np.sqrt(2),np.r_[old_groups,new_groups+len(old_entries)])
        coefficient=prediction['coefficient'][dimension:dimension+extra.shape[1]]
        phases=np.array([d['all_means'][j]+d['widths'][j]*coefficient[width_per_family*k] for k,j in enumerate(families)])
        c.update(curved_negative_twice_elbo=c['negative_twice_elbo'],linear_predictive_objective=prediction['objective'])
        c['negative_twice_elbo']+=prediction['objective'];c['normalization_constant']+=prediction['normalization_constant']
        c['residual']=np.r_[c['residual'],prediction['residual'],np.maximum(0,-elevation)/2]
        c['linear_raw_prediction_residual_hz']=old_values-old_mean;c['linear_elevation']=old_geometry['elevation'] if old_entries else np.array([])
        c['new_raw_prediction_residual_hz']=new_values-mean-extra@coefficient
        c['new_prediction_elevation']=elevation;c['new_family_phases_s']=phases
        c['new_family_coefficient']=coefficient;c['new_prediction_objective']=prediction['objective']
        c['new_radio_calibration_unchanged']=True
        c['new_prediction_audit']=dict(raw=np.r_[old_values-old_mean,new_values-mean],
            design=np.vstack((np.column_stack((old_design,np.zeros((len(old_values),extra.shape[1])))),np.column_stack((radio,extra)))),
            gram=block_diag(gram,np.eye(extra.shape[1])),sigma=np.r_[old_sigma,new_sigma]*np.sqrt(2),
            groups=np.r_[old_groups,new_groups+len(old_entries)])
        return c
    p.calculate=calculate;p.curved_calculate=curved;p.linear_entries=old_entries;p.linear_slices=old_slices
    p.new_entries=new_entries;p.new_slices=new_slices;p.new_family_indices=families;p.new_references=refs
    p.new_physical_modes=physical_modes;p.new_mode_metadata=metadata
    return p


def new_gates(p,x):
    c=p.calculate(x);result=[]
    for e,sl in zip(p.new_entries,p.new_slices,strict=True):
        track=p.scan.tracks[e['track_index']];raw=c['new_raw_prediction_residual_hz'][sl]
        terms=profile(raw,np.zeros(len(raw)),*p.scan.white[e['track_index']],bias_sigma=300.)
        noise=batch_noise_screen(terms['innovations'],track['times'])
        result.append(dict(component=e['component'],norad=e['norad'],candidate_index=e['candidate_index'],points=len(raw),observation_ids=e['observation_ids'],
            compatible=bool(terms['rms'][0]<=450 and abs(terms['bias'][0])<=3000 and int(terms['alias'][0])==0
                and noise['noise_screen_pass'][0] and c['new_prediction_elevation'][sl].min()>=0),
            rms_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0]),noise={k:v[0] for k,v in noise.items()}))
    return result
