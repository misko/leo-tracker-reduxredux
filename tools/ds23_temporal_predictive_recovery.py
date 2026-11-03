"""Temporal proposals for unused GLRT, followed by correlated prediction checks.

The HMM uses marginal emission variances for discovery only. A selected path
must be validated under the full shared Gaussian calibration covariance before
it can enter the existing predictive position likelihood.
"""

import numpy as np
from scipy.special import logsumexp

from ds23_orphan_predictive_mixture import geometry_view
from ds23_height_problem import geometry_features
from leo.analysis.research.retained_track_likelihood import PERIOD,projected_receiver_basis,whitening


def wrapped_density(residual,sigma):
    r=(np.asarray(residual,float)+PERIOD/2)%PERIOD-PERIOD/2
    r,s=np.broadcast_arrays(r,np.asarray(sigma,float))
    if not np.isfinite(r).all() or not np.isfinite(s).all() or np.any(s<=0):raise ValueError('finite residual and positive noise required')
    answer=np.empty(r.shape);small=s<=PERIOD/10
    answer[small]=sum(np.exp(-.5*((r[small]+k*PERIOD)/s[small])**2) for k in [-1,0,1])/(np.sqrt(2*np.pi)*s[small])
    if (~small).any():
        a,b=r[~small],s[~small];value=np.ones(len(a))
        maximum=int(np.ceil(np.sqrt(2*np.log(1e15))*PERIOD/(2*np.pi*b.min())))
        for k in range(1,maximum+1):value+=2*np.exp(-.5*(2*np.pi*b*k/PERIOD)**2)*np.cos(2*np.pi*a*k/PERIOD)
        answer[~small]=np.maximum(0,value)/PERIOD
    return answer


def initial_probabilities(visible,signal_fraction=.5):
    v=np.asarray(visible,bool);p=np.zeros(len(v)+1);p[0]=1-signal_fraction
    if v.any():p[1:]=signal_fraction*v/v.sum()
    else:p[0]=1.
    return p


def transition(previous_visible,next_visible,elapsed,tau,max_gap=10.):
    if elapsed<0 or tau<0:raise ValueError('ordered times and nonnegative persistence required')
    target=initial_probabilities(next_visible)
    stay=0. if tau==0 or elapsed>max_gap else np.exp(-elapsed/tau)
    persistence=np.r_[True,np.asarray(previous_visible,bool)&np.asarray(next_visible,bool)]*stay
    return persistence[:,None]*np.eye(len(target))+(1-persistence[:,None])*target


def hmm(times,signal_density,visible,tau):
    t=np.asarray(times,float);density=np.asarray(signal_density,float);v=np.asarray(visible,bool)
    if t.ndim!=1 or density.ndim!=2 or density.shape!=v.shape or len(t)!=len(density) or not len(t):
        raise ValueError('matching nonempty times and point-by-family density/visibility required')
    if np.any(np.diff(t)<0) or np.any(density<0) or not np.isfinite(density).all():raise ValueError('ordered finite nonnegative emissions required')
    emission=np.column_stack((np.full(len(t),1/PERIOD),density*v))
    with np.errstate(divide='ignore'):
        log_emission=np.log(emission);prior=np.log(initial_probabilities(v[0]));transitions=[
            np.log(transition(v[i-1],v[i],t[i]-t[i-1],tau)) for i in range(1,len(t))]
    alpha=np.empty_like(log_emission);delta=np.empty_like(log_emission);scales=[];backs=[]
    alpha[0]=prior+log_emission[0];scale=logsumexp(alpha[0]);scales.append(scale);alpha[0]-=scale
    delta[0]=prior+log_emission[0]
    for i,step in enumerate(transitions,1):
        alpha[i]=log_emission[i]+logsumexp(alpha[i-1,:,None]+step,axis=0)
        scale=logsumexp(alpha[i]);scales.append(scale);alpha[i]-=scale
        paths=delta[i-1,:,None]+step;backs.append(np.argmax(paths,axis=0));delta[i]=log_emission[i]+np.max(paths,axis=0)
    states=np.empty(len(t),int);states[-1]=np.argmax(delta[-1])
    for i in range(len(t)-2,-1,-1):states[i]=backs[i][states[i+1]]
    beta=np.zeros_like(alpha)
    for i in range(len(t)-2,-1,-1):beta[i]=logsumexp(transitions[i]+log_emission[i+1]+beta[i+1],axis=1)-scales[i+1]
    posterior=np.exp(alpha+beta-logsumexp(alpha+beta,axis=1)[:,None])
    return dict(states=states,posterior=posterior,log_likelihood=float(sum(scales)),
                log_ratio_vs_clutter=float(sum(scales)+len(t)*np.log(PERIOD)))


def path_indices(times,states,minimum_points=8,minimum_span=6.,maximum_gap=10.):
    times,states=np.asarray(times),np.asarray(states);result=[]
    for state in sorted(set(states)-{0}):
        indices=np.flatnonzero(states==state)
        for part in np.split(indices,np.flatnonzero(np.diff(times[indices])>maximum_gap)+1):
            if len(part)>=minimum_points and np.ptp(times[part])>=minimum_span:result.append((int(state),part))
    return result


def calibration(p,x,powers):
    c=p.curved_calculate(x) if hasattr(p,'curved_calculate') else p.calculate(x)
    u=c['features'][p.keep];g=p.noise_groups[p.keep]
    weights=np.asarray(powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
    gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*weights[:,None])
    return c,np.linalg.inv(gram)


def predictions(p,x,powers,observations):
    c,covariance=calibration(p,x,powers);view,active,*_=geometry_view(p,observations)
    geometry=geometry_features(view,x,0.);u=geometry['features']
    mean=view.q*geometry['intercept']+u@c['coefficient'];n=len(observations);f=len(active)
    meta=p.scan.fixed_window_noise
    native_sigma=np.array([meta['per_observation_noise_sigma_hz'][o['observation_id']] if meta['extra_parameter_BIC_gain']>0 else p.scan.radio_sigma_hz for o in observations])
    variance=np.sum((u@covariance)*u,axis=1).reshape(f,n)+300.**2
    return dict(mean=mean.reshape(f,n).T,variance=variance.T,native_sigma=native_sigma,
        visible=(geometry['elevation'].reshape(f,n)>=0).T,active=active,
        features=u.reshape(f,n,-1).transpose(1,0,2),covariance=covariance)


def density_predictions(prediction,values,permutation=None):
    sigma=prediction['native_sigma'] if permutation is None else prediction['native_sigma'][permutation]
    return wrapped_density(np.asarray(values)[:,None]-prediction['mean'],np.sqrt(prediction['variance']+2*sigma[:,None]**2))


def path_identity(prediction,values,indices):
    y=np.asarray(values)[indices];scores=[];aliases=[]
    covariance=prediction['covariance']
    for j in range(len(prediction['active'])):
        mean=prediction['mean'][indices,j]
        alias=np.rint((mean-y)/PERIOD).astype(int);residual=y+alias*PERIOD-mean
        u=prediction['features'][indices,j]
        total=np.diag(2*prediction['native_sigma'][indices]**2)+u@covariance@u.T+300.**2
        score=float(residual@np.linalg.solve(total,residual)+np.linalg.slogdet(total)[1]+len(y)*np.log(2*np.pi))
        if not prediction['visible'][indices,j].all():score=np.inf
        scores.append(score);aliases.append(alias)
    f=len(scores);clutter=-len(y)*np.log(PERIOD)+np.log(.5)
    log_probability=np.r_[clutter,-.5*np.asarray(scores)+np.log(.5/f)]
    probability=np.exp(log_probability-logsumexp(log_probability));best=int(np.argmax(probability[1:]))
    gain=float(2*len(y)*np.log(PERIOD)-scores[best])
    return dict(best_local_index=best,candidate_index=prediction['active'][best],
        probabilities=probability,score=scores[best],gain_vs_clutter=gain,aliases=aliases[best],
        maximum_marginal_SD_hz=float(np.sqrt(prediction['variance'][indices,best]+2*prediction['native_sigma'][indices]**2).max()))


def append_fragments(scan,original_entries,fragments):
    import copy
    changed=copy.copy(scan);changed.tracks=list(scan.tracks);changed.index=list(scan.index)
    changed.white=list(scan.white);changed.rx_basis=list(scan.rx_basis);entries=copy.deepcopy(original_entries)
    occupied={oid for e in entries for oid in e['observation_ids']}
    for fragment in fragments:
        if occupied.intersection(fragment['observation_ids']):raise ValueError('recovered point already belongs to predictive evidence')
        occupied.update(fragment['observation_ids'])
        # Unused winning GLRT can occupy a lane with no graph track. Predictive
        # geometry needs only these explicit physical fields, not a template.
        track=dict(fragment)
        track.update(times=np.asarray(fragment['times']),values=np.asarray(fragment['values']),
            pieces=[],diagnostics={},quality_status='predictive_temporal_recovery',residual_rms_hz=None,
            indices=np.arange(len(fragment['times'])),start_s=min(fragment['times']),end_s=max(fragment['times']))
        index=len(changed.tracks);changed.tracks.append(track);changed.index.append(np.searchsorted(scan.times,track['times']))
        changed.white.append(whitening(track['times']));changed.rx_basis.append(projected_receiver_basis(track['times']))
        entries.append(dict(track_index=index,component=track['key'],candidate_index=fragment['candidate_index'],
            norad=fragment['norad'],alias=0,points=len(track['times']),observation_ids=track['observation_ids'],
            association_source='temporal_unused_GLRT_predictive'))
    if changed.curved!=scan.curved:raise ValueError('temporal paths must not enter calibration')
    return changed,entries
