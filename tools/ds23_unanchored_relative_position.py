"""Receiver-independent relative-CFO likelihood on complete native curves.

Inputs are numerical orbit banks and explicit RF groups. No recording, database,
geographic truth or catalogue selection is accessed here. Shared radio offsets,
drifts and the RF calibration coefficient cancel before constructing features.
"""

import numpy as np
from dsx01_hierarchical_bound import hierarchical_bound
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.retained_track_likelihood import PERIOD


class RelativeCurveProblem:
    def __init__(self,sky,labels,groups,mean,sigma,reference,coordinate,*,mode_bank=None,supported=(),nu=None,bias_sigma=np.sqrt(2)*300):
        self.labels=list(map(int,labels));self.groups=list(groups);self.coordinate=coordinate
        self.phase_mean=np.asarray(mean,float);self.phase_sigma=np.asarray(sigma,float);self.reference=np.asarray(reference,float)
        nlabel=len(self.labels)
        if (not nlabel or len(set(self.labels))!=nlabel or not groups or
                any(v.shape!=(nlabel,) for v in [self.phase_mean,self.phase_sigma,self.reference]) or
                not np.isfinite(np.r_[self.phase_mean,self.phase_sigma,self.reference,bias_sigma]).all() or
                np.any(self.phase_sigma<=0) or bias_sigma<=0):
            raise ValueError('distinct labels, RF curves and matching finite physical phase priors required')
        self.sky=dict(time_s=sky['time_s'],position_km=np.asarray(sky['position_km'])[self.labels],
            velocity_km_s=np.asarray(sky['velocity_km_s'])[self.labels])
        self.mode_bank=mode_bank;self.supported=[self.labels.index(int(j)) for j in supported]
        if self.supported and mode_bank is None:raise ValueError('physical orbit bank required for supported modes')
        self.nu=nu;self.bias_sigma=float(bias_sigma)
        times=[];values=[];noise=[];first=[];second=[];q=[];group_ids=[];self.slices=[];offset=0
        seen=set()
        for k,g in enumerate(groups):
            points=g['points'];t=np.array([r['time_s'] for r in points]);nomination=g['nomination']
            if len(t)<4 or np.any(np.diff(t)<=0) or g['noise_sigma_hz']<=0:raise ValueError('ordered supported relative curves and positive RF noise required')
            pair=[self.labels.index(nomination[role+'_index']) for role in ['first','second']]
            if pair[0]==pair[1]:raise ValueError('distinct satellite hypotheses required')
            y=np.array([r['second_value_hz']-r['first_value_hz'] for r in points])+nomination['difference_alias']*PERIOD
            for row in points:
                identity=tuple(g['lane'])+(row['probe'],)
                if identity in seen:raise ValueError('one native relative observation per physical receiver probe required')
                seen.add(identity)
            times.extend(t);values.extend(y);noise.extend([g['noise_sigma_hz']]*len(t))
            first.extend([pair[0]]*len(t));second.extend([pair[1]]*len(t));q.extend([g['lane'][2]/11.5e9]*len(t));group_ids.extend([k]*len(t))
            self.slices.append(slice(offset,offset+len(t)));offset+=len(t)
        self.times=np.asarray(times);self.values=np.asarray(values);self.noise=np.asarray(noise)
        self.first=np.asarray(first);self.second=np.asarray(second);self.q=np.asarray(q);self.noise_groups=np.asarray(group_ids)
        if not np.isfinite(np.r_[self.times,self.values,self.noise,self.q]).all():raise ValueError('finite relative observations required')
        self.flat_times=np.r_[self.times,self.times];self.flat_labels=np.r_[self.first,self.second]
        self.keep=np.ones(len(self.values),bool);self.lower=np.full(2,-12.5);self.upper=np.full(2,12.5)

    def geometry(self,position,phases=None):
        reference=self.reference if phases is None else np.asarray(phases,float)
        xy=self.coordinate(np.asarray(position));count=len(self.values)
        f,e=paired_phase_frequency(self.sky,self.flat_times,self.flat_labels,reference,*xy)
        plus,_=paired_phase_frequency(self.sky,self.flat_times,self.flat_labels,reference+.01,*xy)
        minus,_=paired_phase_frequency(self.sky,self.flat_times,self.flat_labels,reference-.01,*xy)
        derivative=(plus-minus)/.02
        intercept=f-derivative*reference[self.flat_labels]
        values=self.q*(intercept[count:]-intercept[:count])
        features=np.zeros((count,len(self.labels)+3*len(self.supported)+len(self.groups)))
        for indices,sign,part in [(self.first,-1.,slice(0,count)),(self.second,1.,slice(count,None))]:
            features[np.arange(count),indices]+=sign*self.q*derivative[part]*self.phase_sigma[indices]
        if self.supported:
            modes=paired_frequency_modes(self.sky,self.mode_bank,self.flat_times,self.flat_labels,reference,*xy)
            for k,j in enumerate(self.supported):
                begin=len(self.labels)+3*k
                for indices,sign,part in [(self.first,-1.,slice(0,count)),(self.second,1.,slice(count,None))]:
                    use=indices==j;features[use,begin:begin+3]+=sign*self.q[use,None]*modes[part][use]
        features[np.arange(count),len(self.labels)+3*len(self.supported)+self.noise_groups]=self.bias_sigma
        return dict(intercept=values,features=features,elevation=np.minimum(e[:count],e[count:]))

    def calculate(self,position):
        g=self.geometry(position);width=g['features'].shape[1];mean=np.zeros(width)
        mean[:len(self.labels)]=self.phase_mean/self.phase_sigma
        prior=np.full(width,-1,int)
        if self.nu is not None:prior[:len(self.labels)]=np.arange(len(self.labels))
        result=hierarchical_bound(self.values-g['intercept']-g['features']@mean,g['features'],self.noise,self.noise_groups,
            prior_groups=None if self.nu is None else prior,prior_nu=4 if self.nu is None else self.nu)
        result['latent_coefficient']=result['coefficient'].copy();result['coefficient']+=mean
        result['conditional_residual_hz']=self.values-g['intercept']-g['features']@result['coefficient']
        result.update(g);return result

    def residual(self,position):
        r=self.calculate(position)
        return np.r_[r['residual'],np.maximum(0,-r['elevation'])/2]

    def phases(self,position):return self.calculate(position)['coefficient'][:len(self.labels)]*self.phase_sigma

    def exact_residual(self,position):
        result=self.calculate(position);phase=result['coefficient'][:len(self.labels)]*self.phase_sigma
        g=self.geometry(position,phase)
        # At these phases the phase tangent reconstructs the exact nominal orbit.
        prediction=g['intercept']+g['features']@result['coefficient']
        return self.values-prediction,g['elevation'],phase
