"""Conditional satellite-label uncertainty for one predictive graph bundle.

Candidate priors are uniform over the RF-nominated family set, not the full
catalogue. The mixture is conditional on the bundle and contains no clutter
component; a separate physical audit must prevent automatic acceptance.
"""
import numpy as np
from scipy.linalg import cho_solve
from scipy.special import logsumexp
from leo.analysis.research.predictive_track import condition_coefficients,gaussian_log_density
from leo.analysis.research.retained_track_likelihood import profile
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from predictive_new_family import NewFamily
from investigate_ds23_0268_remaining_tracks import family_frequency


def mixture_score(scores,log_prior):
    score,lp=np.asarray(scores,float),np.asarray(log_prior,float)
    if score.ndim!=1 or score.shape!=lp.shape or not len(score) or not np.isfinite(lp).all() or np.isnan(score).any() or np.isneginf(score).any():
        raise ValueError('matching finite priors and valid component scores required')
    joint=lp-logsumexp(lp)-.5*score;evidence=logsumexp(joint)
    return dict(negative_twice_log_density=float(-2*evidence),weights=np.exp(joint-evidence) if np.isfinite(evidence) else np.zeros(len(score)))


def candidate_set(folds,margin=20.):
    """Freeze the union of plausible RF hypotheses before position evaluation."""
    eligible=set();aliases={};evidence=[]
    for fold in folds:
        proposed=fold['proposals'];near=[]
        for arm in ('c0','fitted_c'):
            best=min(q['arms'][arm]['scores']['conditional_target']['negative_twice_log_density'] for q in proposed)
            ids=set()
            for q in proposed:
                a=q['arms'][arm];s=a['scores']['conditional_target'];gap=s['negative_twice_log_density']-best
                good=np.isfinite([gap,s['rms_hz'],a['final_phase_change_s'],a['minimum_target_elevation_deg']]).all()
                if good and gap<=margin and s['rms_hz']<=450 and a['final_phase_change_s']<=.01 and a['minimum_target_elevation_deg']>=0:ids.add(q['norad'])
            near.append(ids)
        keep=near[0]&near[1];eligible.update(keep);evidence.append(dict(seed=fold['seed'],eligible_norads=sorted(keep)))
        for q in proposed:aliases.setdefault(q['norad'],set()).add(int(q['alias']))
    return [dict(norad=n,aliases=sorted(aliases[n])) for n in sorted(eligible)],evidence


def incumbent_posterior(p,x,powers,entries):
    c=p.curved_calculate(x) if entries else p.calculate(x);coef=c['coefficient'];u=c['features'][p.keep];groups=p.noise_groups[p.keep]
    w=np.asarray(powers)[groups]*c['noise_precision'][groups]/p.point_noise[p.keep]**2
    gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*w[:,None])
    covariance=cho_solve((np.linalg.cholesky(gram),True),np.eye(len(gram)));mean=coef.copy()
    if entries:
        view,y,sigma,g,_=linear_geometry(p,entries);geo=geometry_features(view,x,0.);h=geo['features']
        noise=np.diag(2*sigma*sigma)+300.**2*(g[:,None]==g[None,:])
        mean,covariance=condition_coefficients(coef,covariance,h,y-view.q*geo['intercept']-h@coef,noise)
    return c,mean,covariance


class SharedComponent:
    def __init__(self,entry):self.entry=entry

    def evaluate(self,p,x,powers,entries,*,details=False,refine_phase=False):
        c,mean,cov=incumbent_posterior(p,x,powers,entries)
        view,y,sigma,g,_=linear_geometry(p,[self.entry]);geo=geometry_features(view,x,0.);h=geo['features']
        noise=np.diag(2*sigma*sigma)+300.**2*(g[:,None]==g[None,:])
        result=-2*gaussian_log_density(y-view.q*geo['intercept']-h@mean,noise+h@cov@h.T)
        if not details:return result
        track=p.scan.tracks[self.entry['track_index']];j=self.entry['candidate_index'];pred=view.q*geo['intercept']+h@c['coefficient'];elevation=geo['elevation']
        approximate=pred.copy()
        if refine_phase:
            f,elevation=family_frequency(p,x,j,times=track['times']);begin=p.hardware.shape[1]+p.smooth.shape[1]
            pred=h[:,:begin]@c['coefficient'][:begin]+view.q*f
        terms=profile(y-pred,np.zeros(len(y)),*p.scan.white[self.entry['track_index']],bias_sigma=300.)
        screen=batch_noise_screen(terms['innovations'],track['times']);noise={k:v[0].item() for k,v in screen.items()}
        passed=bool(terms['rms'][0]<=450 and abs(terms['bias'][0])<=3000 and terms['alias'][0]==0 and noise['noise_screen_pass'] and elevation.min()>=0)
        return dict(negative_twice_log_density=float(result),phase_boundary_mass=0.,receiver_calibration_change=0.,
            gates=[dict(component=track['key'],norad=self.entry['norad'],compatible=passed)],
            maximum_exact_mean_change_hz=float(max(abs(pred-approximate))),
            diagnostics=[dict(component=track['key'],times_s=track['times'],CFO_hz=track['values'],
                raw_residual_hz=y-pred,profile_bias_hz=float(terms['bias'][0]),profile_RMS_hz=float(terms['rms'][0]),noise=noise,
                minimum_elevation_deg=float(elevation.min()))])


class LabelMixture:
    def __init__(self,d,target,candidates,phase_step=.1,phase_limit_s=15.):
        p,_=d['problems']['c0'];self.components=[];self.entries=[];self.priors=[];self.kinds=[];self.phase_step=phase_step
        for candidate in candidates:
            j=int(np.flatnonzero(d['scan'].norads==candidate['norad'])[0])
            shared=any(r['candidate_index']==j and p.keep[sl].any() for r,sl in zip(p.rows,p.slices,strict=True)) or any(e['candidate_index']==j for e in d['entries'])
            for alias in candidate['aliases']:
                t=d['scan'].tracks[target['track_index']]
                entry=dict(track_index=target['track_index'],component=t['key'],candidate_index=j,norad=candidate['norad'],alias=alias,
                    observation_ids=t['observation_ids'],points=len(t['times']))
                component=SharedComponent(entry) if shared else NewFamily(d['scan'],[entry],d['model'],phase_step=phase_step,allow_uncalibrated_label=True,phase_limit_s=phase_limit_s)
                self.components.append(component);self.entries.append(entry);self.kinds.append('shared_posterior' if shared else 'causal_phase_mixture')
                self.priors.append(-np.log(len(candidates))-np.log(len(candidate['aliases'])))
        if len(candidates)<2:raise ValueError('soft identity trial requires at least two distinct families')

    def evaluate(self,p,x,powers,entries,*,details=False,refine_phase=False):
        components=[c.evaluate(p,x,powers,entries,details=details,refine_phase=refine_phase) for c in self.components]
        result=mixture_score([c['negative_twice_log_density'] for c in components] if details else components,self.priors)
        if not details:return result['negative_twice_log_density']
        result['components']=[dict(entry=e,kind=k,weight=float(w),**c) for e,k,w,c in zip(self.entries,self.kinds,result['weights'],components,strict=True)]
        result['compatible_mass']=float(sum(r['weight'] for r in result['components'] if all(g['compatible'] for g in r['gates']) and r['phase_boundary_mass']<.01))
        result['receiver_calibration_change']=max(c['receiver_calibration_change'] for c in components)
        result['hard_identity_assigned']=False
        return result
