"""Exact phase-grid likelihood for one previously absent satellite family.

The curved calibration and incumbent predictive objective remain unchanged.
Shared coefficient uncertainty is conditioned on incumbent predictive data
before adding the new family, so receiver uncertainty is never counted twice.
"""
import numpy as np
from scipy.linalg import cho_solve
from scipy.stats import norm,t as student
from scipy.optimize import minimize_scalar
from annotate_predictive_only import receiver_design
from build_dsx01_orbit_modes import build_modes
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.predictive_track import condition_coefficients,phase_mixture_evidence,phase_resolution_agreement
from leo.analysis.research.retained_track_likelihood import PERIOD,profile
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from prototype_dsx01_continuous_position import latlon


class NewFamily:
    def __init__(self,scan,entries,model,*,phase_step=.1,allow_uncalibrated_label=False,
                 integrate_orbit_uncertainty=True,integrate_receiver_uncertainty=True):
        families={e['candidate_index'] for e in entries}
        if len(families)!=1:raise ValueError('one shared new family per exact integration required')
        self.j=next(iter(families));self.entries=entries;self.scan=scan
        self.allow_uncalibrated_label=allow_uncalibrated_label
        # Research-only binary ablations; defaults preserve the full likelihood.
        if type(integrate_orbit_uncertainty) is not bool or type(integrate_receiver_uncertainty) is not bool:
            raise ValueError('uncertainty integration switches must be boolean')
        self.integrate_orbit_uncertainty=integrate_orbit_uncertainty
        self.integrate_receiver_uncertainty=integrate_receiver_uncertainty
        self.tracks=[scan.tracks[e['track_index']] for e in entries];counts=[len(t['times']) for t in self.tracks]
        boundaries=np.r_[0,np.cumsum(counts)];self.slices=[slice(a,b) for a,b in zip(boundaries[:-1],boundaries[1:],strict=True)]
        self.times=np.concatenate([t['times'] for t in self.tracks]);self.q=np.concatenate([np.full(n,t['rf_hz']/11.5e9) for n,t in zip(counts,self.tracks,strict=True)])
        self.values=np.concatenate([t['values']+e['alias']*PERIOD for t,e in zip(self.tracks,entries,strict=True)])
        ids=[o for t in self.tracks for o in t['observation_ids']]
        if len(ids)!=len(set(ids)):raise ValueError('new family duplicates observation IDs')
        meta=scan.fixed_window_noise
        sigma=np.array([meta['per_observation_noise_sigma_hz'][o] if meta['extra_parameter_BIC_gain']>0 else scan.radio_sigma_hz for o in ids])
        groups=np.repeat(np.arange(len(entries)),counts);self.noise=np.diag(2*sigma*sigma)+300.**2*(groups[:,None]==groups[None,:])
        self.phases=np.linspace(-15,15,int(round(30/phase_step))+1);count=len(self.phases);n=len(self.times)
        self.grid_times=np.tile(self.times,count);self.grid_labels=np.repeat(np.arange(count),n)
        modes,metadata=build_modes(scan,[self.j],[self.j],'physical')
        self.bank={'time_s':scan.sky['time_s']};self.modes={'time_s':modes['time_s']}
        for key in ['position_km','velocity_km_s']:
            self.bank[key]=np.broadcast_to(scan.sky[key][[self.j]],(count,*scan.sky[key].shape[1:]))
            self.modes[key]=np.tile(modes[key],(count,1,1))
        widths,history=phase_widths(scan,[self.j]);mean=float(forecast_phase_mean(history,model['shrinkage'])[0]);sigma_phase=float(widths[0]*model['multiplier'])
        distribution=norm(loc=mean,scale=sigma_phase) if model['nu'] is None else student(model['nu'],loc=mean,scale=sigma_phase)
        self.distribution=distribution
        self.logprior=distribution.logpdf(self.phases);self.logprior[[0,-1]]-=np.log(2)
        self.receipt=dict(candidate_index=self.j,norad=int(scan.norads[self.j]),phase_step_s=phase_step,
            phase_prior_mean_s=mean,phase_prior_sigma_s=sigma_phase,phase_prior_nu=model['nu'],
            prior_mass_in_phase_box=float(distribution.cdf(15)-distribution.cdf(-15)),orbital_prior=metadata,
            history=history,target_updates_receiver_calibration=False,conditions_on_incumbent_predictive_uncertainty=True,
            integrate_orbit_uncertainty=integrate_orbit_uncertainty,integrate_receiver_uncertainty=integrate_receiver_uncertainty)

    def evaluate(self,p,x,powers,old_entries,*,details=False,refine_phase=False):
        if self.j in p.labels:
            if not self.allow_uncalibrated_label or any(r['candidate_index']==self.j and p.keep[sl].any() for r,sl in zip(p.rows,p.slices,strict=True)):
                raise ValueError('family has active calibration evidence or uncalibrated-label use is disabled')
        if any(e['candidate_index']==self.j for e in old_entries):raise ValueError('family also present in conditioning observations')
        c=p.curved_calculate(x) if old_entries else p.calculate(x)
        coef=c['coefficient'];before=coef.copy();u=c['features'][p.keep];groups=p.noise_groups[p.keep]
        w=np.asarray(powers)[groups]*c['noise_precision'][groups]/p.point_noise[p.keep]**2
        gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*w[:,None])
        covariance=cho_solve((np.linalg.cholesky(gram),True),np.eye(len(gram)))
        mean=coef;posterior=covariance
        if old_entries:
            view,y,sigma,g,_=linear_geometry(p,old_entries);geo=geometry_features(view,x,0.);h=geo['features']
            raw=y-view.q*geo['intercept']-h@coef
            noise=np.diag(2*sigma*sigma)+300.**2*(g[:,None]==g[None,:])
            mean,posterior=condition_coefficients(coef,covariance,h,raw,noise)
        receiver=np.concatenate([receiver_design(t['times'],t['rf_hz'],t['receiver'],t['channel'],self.scan.rx_basis[e['track_index']],fitted_c=p.fitted_c)
                                 for t,e in zip(self.tracks,self.entries,strict=True)])
        h=np.zeros((len(self.times),len(coef)));h[:,:receiver.shape[1]]=receiver
        f,e=paired_phase_frequency(self.bank,self.grid_times,self.grid_labels,self.phases,*latlon(x))
        modes=paired_frequency_modes(self.bank,self.modes,self.grid_times,self.grid_labels,self.phases,*latlon(x))
        f=f.reshape(len(self.phases),-1)*self.q;e=e.reshape(len(self.phases),-1)
        modes=modes.reshape(len(self.phases),len(self.times),3)*self.q[None,:,None]
        if not self.integrate_orbit_uncertainty:modes=np.zeros_like(modes)
        conditional_mean=h@mean+f
        cov=self.noise+(h@posterior@h.T if self.integrate_receiver_uncertainty else 0.)
        result=phase_mixture_evidence(self.values,conditional_mean,cov,modes,self.logprior,e.min(axis=1)>=0)
        if not details:return result['negative_twice_log_density']
        weights=result['phase_weights'];k=int(np.argmax(weights));phase_mean=float(weights@self.phases)
        orbital=result['orbital_posterior_mean'][k];phase_map=float(self.phases[k]);frequency=f[k];mode=modes[k];elevation=e[k]
        if refine_phase:
            bank={key:value[:1] if key!='time_s' else value for key,value in self.bank.items()}
            mode_bank={key:value[:3] if key!='time_s' else value for key,value in self.modes.items()}
            def at_phase(phase):
                ff,ee=paired_phase_frequency(bank,self.times,np.zeros(len(self.times),int),np.array([phase]),*latlon(x))
                uu=paired_frequency_modes(bank,mode_bank,self.times,np.zeros(len(self.times),int),np.array([phase]),*latlon(x))*self.q[:,None]
                if not self.integrate_orbit_uncertainty:uu=np.zeros_like(uu)
                ff=ff*self.q
                value=phase_mixture_evidence(self.values,(h@mean+ff)[None],cov,uu[None],np.zeros(1),np.array([ee.min()>=0]))
                return value,ff,uu,ee
            step=float(self.phases[1]-self.phases[0]);opt=minimize_scalar(
                lambda phi:at_phase(phi)[0]['negative_twice_log_density']-2*self.distribution.logpdf(phi),
                bounds=(max(-15,phase_map-step),min(15,phase_map+step)),method='bounded',options=dict(xatol=1e-7,maxiter=40))
            phase_map=float(opt.x);value,frequency,mode,elevation=at_phase(phase_map);orbital=value['orbital_posterior_mean'][0]
        # Gate the physical prediction with the original receiver mean. The
        # likelihood integrates receiver uncertainty, but does not expose a
        # target-driven receiver posterior as a new calibration solution.
        prediction=h@coef+frequency+mode@orbital;raw=self.values-prediction;gates=[];diagnostics=[]
        for entry,track,sl in zip(self.entries,self.tracks,self.slices,strict=True):
            terms=profile(raw[sl],np.zeros(sl.stop-sl.start),*self.scan.white[entry['track_index']],bias_sigma=300.)
            noise=batch_noise_screen(terms['innovations'],track['times']);screen={key:bool(v[0]) if v.dtype==bool else float(v[0]) for key,v in noise.items()}
            valid=bool(terms['rms'][0]<=450 and abs(terms['bias'][0])<=3000 and int(terms['alias'][0])==0 and noise['noise_screen_pass'][0] and elevation[sl].min()>=0)
            gates.append(dict(component=entry['component'],norad=entry['norad'],candidate_index=self.j,points=entry['points'],compatible=valid,observation_ids=entry['observation_ids']))
            diagnostics.append(dict(component=entry['component'],times_s=track['times'],CFO_hz=track['values'],
                prediction_CFO_hz=prediction[sl]-entry['alias']*PERIOD,raw_residual_hz=raw[sl],profile_bias_hz=float(terms['bias'][0]),
                profile_RMS_hz=float(terms['rms'][0]),noise=screen,minimum_elevation_deg=float(elevation[sl].min())))
        after=p.curved_calculate(x) if old_entries else p.calculate(x)
        return dict(negative_twice_log_density=result['negative_twice_log_density'],phase_map_s=phase_map,grid_phase_map_s=float(self.phases[k]),
            continuous_phase_gate=refine_phase,
            phase_mean_s=phase_mean,phase_sigma_s=float(np.sqrt(weights@((self.phases-phase_mean)**2))),
            phase_weights=weights,phase_grid_s=self.phases,phase_boundary_mass=float(weights[abs(self.phases)>=14.9].sum()),
            orbital_posterior_mean=orbital,visible_prior_mass=result['visible_prior_mass'],gates=gates,diagnostics=diagnostics,
            receiver_calibration_change=float(np.max(abs(before-after['coefficient']))))


def resolution_audit(family,p,x,powers,entries,model):
    """Post-fit local quadrature check, without changing data or fitted position."""
    x=np.asarray(x);step=family.receipt['phase_step_s'];steps=[step,step/2,step/4]
    if np.max(abs(x))+.025>12.5:
        return dict(local_agreement=False,reason='centered local audit unavailable at regional boundary',steps_s=steps)
    predictors=[family]+[NewFamily(family.scan,family.entries,model,phase_step=h,
        allow_uncalibrated_label=family.allow_uncalibrated_label,
        integrate_orbit_uncertainty=family.integrate_orbit_uncertainty,
        integrate_receiver_uncertainty=family.integrate_receiver_uncertainty) for h in steps[1:]]
    offsets=np.array([[0,0],[.025,0],[-.025,0],[0,.025],[0,-.025]])
    scores=np.array([[f.evaluate(p,x+offset,powers,entries) for f in predictors] for offset in offsets])
    return dict(steps_s=steps,offsets_km=offsets,scores=scores,incumbent_phase_reference_fixed_locally=True,
        position_refitted=False,**phase_resolution_agreement(scores))
