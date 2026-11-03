"""Saved-IQ research fit with separate frame cadence and intra-frame rate.

The published coupled fitter is unchanged. Equal rates reproduce its sampled
replica exactly. Frame phases and DC remain independent nuisance parameters;
this model does not assume carrier continuity across frames.
"""

import numpy as np
from functools import lru_cache

from fast_local_pilot_refinement import FastPilotWorkspace
from leo.analysis.starlink.templates import qin_edge_pilot_frame, CONTROL_SYMBOL_ROLL
from probe_native_code_carrier import periodic_upsample, interpolate_periodic


@lru_cache(maxsize=8)
def isolated_pilot_wave(fs,edge,control=False):
    frame=qin_edge_pilot_frame(fs,edge,symbol_roll=CONTROL_SYMBOL_ROLL if control else 0)
    values=np.zeros(round(fs/250),complex);values[:len(frame)]=frame
    return periodic_upsample(values,32)


class DecoupledPilotWorkspace(FastPilotWorkspace):
    parameter_scale=np.array([100.,1.,20.,20.])

    def frame_starts(self,u):
        return np.rint(np.floor(u/self.period)*self.period)

    def wave_position(self,u,start,a,b):
        return (start+(u-start)*b/a)*32

    def signal(self,parameters,derivatives=False):
        f,offset,frame_ppm,intra_ppm=np.asarray(parameters,float)
        a,b=1+frame_ppm*1e-6,1+intra_ppm*1e-6
        u=(self.n-self.epoch-offset)*a
        start=self.frame_starts(u)
        position=self.wave_position(u,start,a,b)
        index=np.floor(position).astype(np.int64);fraction=position-index
        left,right=self.wave[index%len(self.wave)],self.wave[(index+1)%len(self.wave)]
        rotation=np.exp(2j*np.pi*f*(self.t-self.mid))
        signal=(left+(right-left)*fraction)*rotation
        if not derivatives:
            return signal
        slope=(right-left)*rotation*32
        jacobian=np.column_stack((2j*np.pi*(self.t-self.mid)*signal*100,
            -b*slope,
            start*b/(a*a)*1e-6*slope*20,
            (u-start)/a*1e-6*slope*20))
        return signal,jacobian

    def statistics(self,parameters,subset='all',derivatives=True):
        if not np.isfinite(parameters).all() or subset not in ('all','odd','even'):
            raise ValueError('finite four-parameter clock model and named frame subset required')
        if derivatives:
            signal,jacobian=self.signal(parameters,True)
        else:
            signal=self.signal(parameters)
        normal=np.zeros((4,4));rhs=np.zeros(4);explained=raw=0.
        for k,ix in enumerate(self.frames):
            if subset=='odd' and k%2==0 or subset=='even' and k%2==1:
                continue
            s=signal[ix];s=s-s.mean();y=self.y[ix]-self.raw_sum[k]/len(ix)
            energy=float(np.vdot(s,s).real)
            if energy<=1e-20:
                continue
            cross=np.vdot(s,y);amplitude=cross/energy;residual=y-amplitude*s
            explained+=abs(cross)**2/energy;raw+=self.raw_energy[k]
            if derivatives:
                d=jacobian[ix];summed=d.sum(axis=0);cross_d=s.conj()@d
                gram=d.conj().T@d-np.outer(summed.conj(),summed)/len(ix)
                gram-=np.outer(cross_d.conj(),cross_d)/energy
                normal+=abs(amplitude)**2*gram.real
                rhs+=(amplitude.conjugate()*(d.conj().T@residual)).real
        return dict(score=float(explained/max(raw,1e-20)),normal=normal,rhs=rhs,
            gradient_score=2*rhs/max(raw,1e-20),raw_energy=raw,
            projected_residual_energy=float(raw-explained))

    def clock_fit(self,start,*,iterations=24,subset='all'):
        parameters=np.asarray(start,float).copy();center=parameters[0]
        lower=np.array([center-800.,-.75,-40.,-100.])
        upper=np.array([center+800.,.75,40.,100.])
        parameters=np.clip(parameters,lower,upper)
        current=self.statistics(parameters,subset);calls=1;damping=1e-3
        history=[dict(parameters=parameters.copy(),score=current['score'])]
        for _ in range(iterations):
            diagonal=np.maximum(np.diag(current['normal']),current['raw_energy']*1e-14)
            improved=False
            for _ in range(7):
                try:
                    step=np.linalg.solve(current['normal']+damping*np.diag(diagonal),current['rhs'])
                except np.linalg.LinAlgError:
                    damping*=10;continue
                step/=max(1.,float(np.max(abs(step)/np.array([.6,.25,.5,1.]))))
                proposed=np.clip(parameters+self.parameter_scale*step,lower,upper)
                if np.max(abs((proposed-parameters)/self.parameter_scale))<1e-4:
                    break
                candidate=self.statistics(proposed,subset);calls+=1
                if candidate['score']>current['score']+1e-12:
                    parameters,current=proposed,candidate;damping=max(1e-8,damping/3)
                    improved=True;history.append(dict(parameters=parameters.copy(),score=current['score']));break
                damping*=10
            if not improved:
                break
        points=sum(len(ix) for k,ix in enumerate(self.frames)
            if subset=='all' or (subset=='even' and k%2==0) or (subset=='odd' and k%2==1))
        noise=current['projected_residual_energy']/max(points,1)
        covariance=np.linalg.pinv(current['normal'],rcond=1e-12)*noise/2
        covariance*=self.parameter_scale[:,None]*self.parameter_scale[None,:]
        return dict(CFO_hz=float(parameters[0]),offset_samples=float(parameters[1]),
            frame_ppm=float(parameters[2]),intra_ppm=float(parameters[3]),score=current['score'],
            raw_energy=current['raw_energy'],residual_energy=current['projected_residual_energy'],
            sample_count=points,conditional_covariance=covariance,
            conditional_parameter_sigma=np.sqrt(np.maximum(0,np.diag(covariance))),
            boundary=bool(np.any(abs(parameters-lower)<1e-4) or np.any(abs(parameters-upper)<1e-4)),
            subset=subset,calls=calls,history=history,
            covariance_is_local_Gaussian_proxy_not_calibrated=True)


class ContinuousFrameWorkspace(DecoupledPilotWorkspace):
    """Place each frame at its true fractional sample epoch, not rounded starts."""

    def __init__(self,samples,fs,edge,epoch):
        super().__init__(samples,fs,edge,epoch)
        self.wave=isolated_pilot_wave(fs,edge)
        self.control=isolated_pilot_wave(fs,edge,True)

    def frame_starts(self,u):
        return np.floor(u/self.period)*self.period

    def wave_position(self,u,start,a,b):
        return (u-start)*b/a*32


class ContinuousCoupledWorkspace(ContinuousFrameWorkspace):
    """Three-parameter comparison isolating fractional frame placement alone."""

    parameter_scale=np.array([100.,1.,20.])

    def replica(self,offset=0.,ppm=0.,control=False):
        u=(self.n-self.epoch-offset)*(1+ppm*1e-6)
        local=u-self.frame_starts(u)
        return interpolate_periodic(self.control if control else self.wave,local*32)

    def statistics(self,parameters,subset='all',derivatives=True):
        f,offset,ppm=np.asarray(parameters,float)
        result=super().statistics([f,offset,ppm,ppm],subset,derivatives)
        transform=np.array([[1.,0,0],[0,1.,0],[0,0,1.],[0,0,1.]])
        result['normal']=transform.T@result['normal']@transform
        result['rhs']=transform.T@result['rhs']
        result['gradient_score']=transform.T@result['gradient_score']
        return result
