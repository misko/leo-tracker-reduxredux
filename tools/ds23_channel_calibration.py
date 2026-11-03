"""Shared nonlinear channel calibration, orthogonal to band offset/RF slope.

Only curved observations learn the new Gaussian modes. Predictive tracks use
the same conditional covariance, without updating any calibration coefficient.
"""

import copy
import numpy as np

from ds23_predictive_linear import linear_geometry, predictive_residual
from ds23_height_problem import geometry_features
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_receiver_smooth_prior import scale_posterior


def nonlinear_channel_basis(frequencies, observed):
    """Polynomial channel contrasts, normalized on observed channel centers."""
    f, active = np.asarray(frequencies, float), np.asarray(observed, bool)
    if f.shape != (4,) or active.shape != (4,) or not np.isfinite(f).all() or np.ptp(f) <= 0:
        raise ValueError('four finite frequency centers and matching channel-presence flags required')
    result = np.zeros((4, 2))
    if active.sum() < 3:
        return result
    x = (f-f.mean())/np.ptp(f)
    affine = np.column_stack((np.ones(4), x))
    polynomial = np.column_stack((x*x, x*x*x))
    residual = polynomial-affine@np.linalg.lstsq(affine[active], polynomial[active], rcond=None)[0]
    _, singular, right = np.linalg.svd(residual[active], full_matrices=False)
    rank = int(active.sum())-2
    if np.any(singular[:rank] < 1e-12):
        raise ValueError('distinct observed channel frequencies required')
    result[:,:rank] = residual@right[:rank].T/singular[:rank]
    return result


def calibration_lookup(scan, p):
    """Enable a band only with at least three curved families and channels."""
    lookup = np.zeros((2, 8, 8))
    receipts = []
    for rx in (1,2):
        for band in (0,1):
            members = [(r,scan.tracks[i]) for r,i,sl in zip(p.rows,p.members,p.slices,strict=True)
                       if p.keep[sl].any() and scan.tracks[i]['receiver']==rx
                       and int(scan.tracks[i]['channel']>4)==band]
            families = {r['candidate_norad'] for r,t in members}
            channels = {t['channel'] for r,t in members}
            observed = np.array([1+4*band+k in channels for k in range(4)])
            frequencies = []
            for ch in range(1+4*band,5+4*band):
                known = [t['rf_hz'] for t in scan.tracks if t['receiver']==rx and t['channel']==ch]
                frequencies.append(float(np.median(known)) if known else (10.71+.25*(ch-1))*1e9)
            enabled = len(families)>=3 and observed.sum()>=3
            basis = nonlinear_channel_basis(frequencies, observed) if enabled else np.zeros((4,2))
            begin = 2*(2*(rx-1)+band)
            lookup[rx-1,4*band:4*band+4,begin:begin+2] = basis
            receipts.append(dict(receiver=rx,band=band,curved_families=sorted(families),
                curved_channels=sorted(channels),enabled=bool(enabled),RF_centers_hz=frequencies,
                basis=basis,mode_count=int(observed.sum())-2 if enabled else 0))
    return lookup, receipts


def track_design(track, lookup):
    return np.broadcast_to(lookup[track['receiver']-1,track['channel']-1],(len(track['times']),8))


def make_channel_problem(scan,node,keep,arm,reference,powers,means,model,sigma_hz):
    if not np.isfinite(sigma_hz) or sigma_hz<0:
        raise ValueError('finite nonnegative channel-mode prior SD required')
    p = make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
    lookup,receipt = calibration_lookup(scan,p)
    p.channel_sigma_hz = float(sigma_hz);p.channel_lookup=lookup;p.channel_receipt=receipt;p.events=[]
    if sigma_hz==0:
        return p
    design = np.concatenate([track_design(scan.tracks[i],lookup) for i in p.members])*sigma_hz
    begin = p.hardware.shape[1]+p.smooth.shape[1]
    old_width = begin+len(p.labels)+3*len(p.supported)+len(p.members)
    width = old_width+8
    mean = np.zeros(width);mean[begin:begin+len(p.labels)] = means/p.phase_sigma
    prior_groups = np.full(width,-1,int)
    if model['nu'] is not None:prior_groups[begin:begin+len(p.labels)] = np.arange(len(p.labels))
    scales = np.ones(width);scales[old_width-len(p.members):old_width]=.3
    original_state=p.state
    def calculate(x):
        geometry=JointMarginal.calculate(p,x)
        features=np.column_stack((geometry['features'],design))
        raw=p.values-p.q*geometry['intercept']-features@mean
        present=np.unique(p.noise_groups[keep])
        bound=hierarchical_bound(raw[keep],(features*scales)[keep],p.point_noise[keep],p.noise_groups[keep],
            powers=np.asarray(powers)[present],prior_groups=None if model['nu'] is None else prior_groups,
            prior_nu=4 if model['nu'] is None else model['nu'])
        bound=scale_posterior(bound,scales)
        bound['latent_coefficient']=bound['coefficient'].copy();bound['coefficient']+=mean
        precision=np.zeros(len(p.members));precision[present]=bound['noise_precision'];bound['noise_precision']=precision
        bound['conditional_residual_hz']=p.values-p.q*geometry['intercept']-features@bound['coefficient']
        volume=float(2*np.sum(np.asarray(powers)[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        bound['residual']=np.r_[bound['residual'],np.sqrt(volume)]
        geometry.update(bound,features=features,channel_amplitudes_hz=sigma_hz*bound['coefficient'][old_width:])
        return geometry
    p.calculate=calculate;p.scan=copy.copy(scan)
    base_hardware=scan.hardware;nb=p.hardware.shape[1]
    p.scan.hardware=lambda t,beta:base_hardware(t,np.asarray(beta)[:nb])+track_design(t,lookup)@np.asarray(beta)[nb:]
    def state(x):
        result=original_state(x);amplitudes=p.calculate(x)['channel_amplitudes_hz']
        result['channel_amplitudes_hz']=amplitudes;result['beta']=np.r_[result['beta'],amplitudes]
        return result
    p.state=state
    return p


def attach_channel_predictive(p,entries,powers):
    if not entries:return p
    view,values,sigma,groups,slices=linear_geometry(p,entries)
    design=(np.concatenate([track_design(p.scan.tracks[e['track_index']],p.channel_lookup) for e in entries])*p.channel_sigma_hz
            if p.channel_sigma_hz else np.zeros((len(values),0)))
    curved=p.calculate
    def calculate(x):
        c=curved(x);g=p.noise_groups[p.keep]
        weight=np.asarray(powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        u=c['features'][p.keep];gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*weight[:,None])
        geometry=geometry_features(view,x,0.)
        features=np.column_stack((geometry['features'],design))
        predicted=view.q*geometry['intercept']+features@c['coefficient']
        prediction=predictive_residual(values-predicted,features,gram,sigma*np.sqrt(2),groups)
        c['curved_negative_twice_elbo']=c['negative_twice_elbo'];c['linear_predictive_objective']=prediction['objective']
        c['negative_twice_elbo']+=prediction['objective'];c['normalization_constant']+=prediction['normalization_constant']
        c['residual']=np.r_[c['residual'],prediction['residual']]
        c['linear_raw_prediction_residual_hz']=values-predicted;c['linear_elevation']=geometry['elevation']
        return c
    p.calculate=calculate;p.curved_calculate=curved;p.linear_slices=slices;p.linear_entries=entries
    return p
