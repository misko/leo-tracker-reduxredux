"""Research selected-margin conditioning; margins are not calibrated odds."""
import numpy as np
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import ALIAS_HZ, WindowLikelihood, circular
from leo.analysis.shared_scan_model import elevation_geometry,horizon_weight


def covariate(margins, training):
    values,mask=np.asarray(margins,float),np.asarray(training)
    if (values.ndim!=1 or mask.dtype!=bool or mask.shape!=values.shape or not mask.any()
            or not np.isfinite(values).all() or np.any(values<=0)):
        raise ValueError('Positive finite margins and nonempty boolean training mask required')
    logs=np.log(values);center=float(logs[mask].mean());scale=float(logs[mask].std())
    if not np.isfinite(scale) or scale<=0:raise ValueError('Training log-margin variance must be positive')
    return (logs-center)/scale,dict(center=center,scale=scale,training_count=int(mask.sum()),
        transformation='(log(selected margin)-training mean)/training population standard deviation')


def conditioned_density(measured,prediction,weight,sigma,q,config,log_clutter_multiplier):
    measured,prediction,weight,sigma,q,log_multiplier=map(np.asarray,
        (measured,prediction,weight,sigma,q,log_clutter_multiplier))
    if (prediction.ndim!=2 or measured.shape!=(len(prediction),)
            or weight.shape!=prediction.shape or sigma.shape!=measured.shape
            or q.shape!=(prediction.shape[1],) or log_multiplier.shape!=measured.shape
            or not all(np.isfinite(a).all() for a in (measured,prediction,weight,sigma,q,log_multiplier))
            or np.any((weight<0)|(weight>1)) or np.any((q<=0)|(q>=1))
            or np.any((sigma<=0)|(sigma>1000)) or abs(q.sum()-config.detection_budget)>1e-10):
        raise ValueError('Aligned finite density arrays and preserved detection budget required')
    rate=config.clutter_rate*np.exp(log_multiplier)
    if not np.isfinite(rate).all() or np.any(rate<=0):raise ValueError('Finite positive clutter rates required')
    p=weight*q[None,:];odds=p/(1-p);residual=circular(measured[:,None]-prediction)
    gaussian=np.exp(-.5*(residual/sigma[:,None])**2)/(sigma[:,None]*np.sqrt(2*np.pi))
    signal=odds*gaussian;total=rate/ALIAS_HZ+signal.sum(axis=1)
    normalizer=rate+odds.sum(axis=1);rows=np.log(normalizer)-np.log(total)
    responsibility=signal/total[:,None];clutter=rate/ALIAS_HZ/total
    p_gradient=(1/normalizer[:,None]-gaussian/total[:,None])/(1-p)**2
    terms=WindowLikelihood(float(rows.sum()),responsibility,clutter,
        -responsibility*residual/sigma[:,None]**2,residual)
    return terms,dict(row_nll=rows,detection_probability_gradient=(p_gradient*weight).sum(axis=0),
        visibility_weight_gradient=p_gradient*q[None,:],
        clutter_log_multiplier_gradient=rate/normalizer-clutter,clutter_rate=rate)


class AcquisitionClutterModel:
    def __init__(self,base,full_covariate):
        x=np.asarray(full_covariate,float)
        if x.shape!=base.observations.times_s.shape or not np.isfinite(x).all():
            raise ValueError('One finite fixed acquisition covariate per original row required')
        self.base=base;self.x=x[base.mask].copy();self.x.setflags(write=False)
        self.base_count=len(base.initial_nuisance)
        self.initial_nuisance=np.r_[base.initial_nuisance,0.]
        self.group_count=base.group_count+1
        self.group_limits=np.r_[base.group_limits,2.];self.group_scales=np.r_[base.group_scales,.5]
        self.precision=np.zeros((self.base_count+1,self.base_count+1))
        self.precision[:self.base_count,:self.base_count]=base.precision
        self.precision[-1,-1]=1.
        self.group_precision=self.precision[base.clock_count:,base.clock_count:]

    def __getattr__(self,name):
        if name=='base':raise AttributeError(name)
        return getattr(self.base,name)

    def split(self,nuisance):
        n=np.asarray(nuisance,float)
        if n.shape!=self.initial_nuisance.shape or not np.isfinite(n).all():
            raise ValueError('Exact base nuisance and one finite clutter slope required')
        return n[:self.clock_count],n[self.clock_count:]

    def evaluate_details(self,vector,nuisance):
        self.split(nuisance);v,n=np.asarray(vector),np.asarray(nuisance)
        old_n,beta=n[:-1],float(n[-1]);old,details=self.base.evaluate_details(v,old_n)
        obs=self.base.scored_observations;shifts=v[7]+self.basis@v[8:]
        prediction,_,spatial,timing=predict_orbits(self.bank,obs,self.prior,v[:2],shifts)
        correction=self.original.correction(v,old_n[:self.base.base_nuisance_count])
        prediction+=correction[self.base.mask,None]
        sigma,_,q,q_jac,_=self.base.hyperparameters(old_n[self.base.base_nuisance_count:])
        terms,current=conditioned_density(obs.measured_hz,prediction,details['visibility_weight'],
            sigma,q,self.score,beta*self.x)
        dw=terms.prediction_gradient-old[3].prediction_gradient
        _,es,et,_=elevation_geometry(self.bank,obs,self.prior,v[:2],shifts)
        _,slope=horizon_weight(details['sine_elevation'],self.visibility_width)
        de=(current['visibility_weight_gradient']-details['visibility_weight_gradient'])*slope
        gradient=old[1].copy()
        gradient[:2]+=np.einsum('nk,nki->i',dw,spatial)+np.einsum('nk,nki->i',de,es)
        gradient[2:7]+=self.original.design[self.base.mask].T@dw.sum(axis=1)
        dt=np.sum(dw*timing+de*et,axis=0);gradient[7]+=dt.sum();gradient[8:]+=self.basis.T@dt
        extra=old[2].copy();counts=self.base.base_nuisance_count
        extra[:self.clock_count]+=self.original.clock_design[self.base.mask].T@dw.sum(axis=1)
        extra[self.clock_count:counts]+=self.original.group_design[self.base.mask].T@dw.sum(axis=1)
        extra[counts:]+=q_jac.T@(current['detection_probability_gradient']-details['detection_probability_gradient'])
        beta_gradient=float(self.x@current['clutter_log_multiplier_gradient'])+beta
        value=old[0]+terms.nll-old[3].nll+.5*beta**2
        return (float(value),gradient,np.r_[extra,beta_gradient],terms),dict(details,**current,
            acquisition_clutter_slope=beta,prior_penalty=details['prior_penalty']+.5*beta**2)

    def evaluate_joint(self,vector,nuisance):return self.evaluate_details(vector,nuisance)[0]
