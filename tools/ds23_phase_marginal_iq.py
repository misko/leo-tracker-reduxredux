"""Normalized joint-IQ clock fit with receiver phase noise marginalized per frame.

Transmitter gains are independent circular Gaussian variables in each frame.
Their training-only power estimates are fixed during a fit. One wrapped-normal
relative receiver phase acts on all components together. This is a research
likelihood; no geographic or satellite input is accepted.
"""

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

from ds23_training_channel_rf import TrainingChannelWorkspace
from ds23_shared_receiver_phase import phase_grid, phase_NLL


def phase_integral(cross, sigma, grid_size):
    """Log phase integral, posterior first moment, and log-SD derivative."""
    if sigma == 0:
        return 2*cross.real, 1.+0j, 0.
    phi, cosine, sine = phase_grid(grid_size)
    image = phi[:, None]+2*np.pi*np.arange(-3, 4)[None]
    exponent = -.5*(image/sigma)**2
    image_logsum = logsumexp(exponent, axis=1)
    logprior = image_logsum-logsumexp(image_logsum)
    image_moment = np.sum(np.exp(exponent-image_logsum[:, None])*(image/sigma)**2, axis=1)
    prior_moment = float(np.exp(logprior)@image_moment)
    logweight = logprior+2*(cross.real*cosine+cross.imag*sine)
    integral = float(logsumexp(logweight))
    posterior = np.exp(logweight-integral)
    moment = posterior@(cosine-1j*sine)
    derivative = float(posterior@image_moment-prior_moment)
    return integral, moment, derivative


class PhaseMarginalIQ:
    def __init__(self, samples, fs, edge, epochs, segments, noise_variance, gain_variance,
                 *, separate_clocks=False, grid_size=2048):
        self.y, self.epochs = np.asarray(samples, complex), np.asarray(epochs, float)
        self.noise, self.gain = np.asarray(noise_variance, float), np.asarray(gain_variance, float)
        if self.y.ndim != 2 or self.y.shape[0] != 2 or self.epochs.ndim != 2 or self.epochs.shape[0] != 2:
            raise ValueError('two receiver IQ streams and RX-by-component epochs required')
        self.count = self.epochs.shape[1]
        if self.count not in (1,2) or self.noise.shape != (2,) or self.gain.shape != (self.count,):
            raise ValueError('one or two components and matching variances required')
        if np.any(self.noise <= 0) or np.any(self.gain <= 0) or not np.isfinite(np.r_[self.noise,self.gain]).all():
            raise ValueError('positive finite training-only IQ and gain variances required')
        self.frames = [np.asarray(ix,int) for ix in segments]
        self.parts = [[TrainingChannelWorkspace(self.y[r],fs,edge,self.epochs[r,k],self.frames)
            for k in range(self.count)] for r in [0,1]]
        self.clock_count = self.count if separate_clocks else 1
        self.code_start = self.count+self.clock_count
        self.ratio_start = self.code_start+4*self.count
        self.width = self.ratio_start+2*self.count
        self.scale = np.r_[np.full(self.code_start,100.),np.tile([1.,20.],2*self.count),np.ones(2*self.count)]
        self.grid_size, self.fs = grid_size, fs
        self.used = np.concatenate(self.frames)

    def ratios(self,p):
        return p[self.ratio_start::2]+1j*p[self.ratio_start+1::2]

    def signals(self,p,derivatives=False):
        p=np.asarray(p,float)
        if p.shape != (self.width,) or not np.isfinite(p).all():
            raise ValueError('matching finite carrier, clock, code, and ratio coordinates required')
        values=[];derivative=[]
        for r in [0,1]:
            signals=[];local=[]
            for k in range(self.count):
                f=p[k]+(p[self.count+(k if self.clock_count>1 else 0)] if r else 0.)
                begin=self.code_start+2*self.count*r+2*k
                column=self.parts[r][k].columns([f,p[begin],p[begin+1]],derivatives=derivatives)
                if derivatives:
                    column,jac=column
                    local.append(np.column_stack([d.sum(axis=1) for d in jac]))
                signals.append(column.sum(axis=1))
            values.append(np.column_stack(signals))
            derivative.append(local)
        return (values,derivative) if derivatives else values

    def statistics(self,parameters,*,fixed_sigma=None,gradient=True):
        parameters=np.asarray(parameters,float)
        p=parameters[:self.width]
        sigma=float(np.exp(parameters[-1])) if fixed_sigma is None else float(fixed_sigma)
        if fixed_sigma is None and parameters.shape != (self.width+1,):
            raise ValueError('one log receiver-phase SD required')
        if gradient:signals,local=self.signals(p,True)
        else:signals=self.signals(p)
        ratio=self.ratios(p)
        total=0.;derivative=np.zeros(len(parameters));phase_means=[]
        for ix in self.frames:
            a=signals[0][ix];b=signals[1][ix]*ratio
            a=(a-a.mean(axis=0))/np.sqrt(self.noise[0])
            b=(b-b.mean(axis=0))/np.sqrt(self.noise[1])
            y=(self.y[0,ix]-self.y[0,ix].mean())/np.sqrt(self.noise[0])
            z=(self.y[1,ix]-self.y[1,ix].mean())/np.sqrt(self.noise[1])
            h=np.diag(1/self.gain)+a.conj().T@a+b.conj().T@b
            inverse=np.linalg.inv(h)
            c,d=a.conj().T@y,b.conj().T@z
            u,v=inverse@c,inverse@d
            cross=np.vdot(c,v)
            integral,moment,phase_derivative=phase_integral(cross,sigma,self.grid_size)
            normalizer=float(np.linalg.slogdet(h)[1]+np.log(self.gain).sum()
                +(len(ix)-1)*np.log(np.pi*self.noise).sum())
            total+=float(np.vdot(y,y).real+np.vdot(z,z).real-np.vdot(c,u).real-np.vdot(d,v).real)+normalizer-integral
            phase_means.append(moment)
            if not gradient:continue
            da=np.zeros((len(ix),self.count,self.width),complex);db=np.zeros_like(da)
            for k in range(self.count):
                da[:,k,k]=local[0][k][ix,0]
                db[:,k,k]=local[1][k][ix,0]*ratio[k]
                db[:,k,self.count+(k if self.clock_count>1 else 0)]+=local[1][k][ix,0]*ratio[k]
                for r,design in [(0,da),(1,db)]:
                    begin=self.code_start+2*self.count*r+2*k
                    design[:,k,begin:begin+2]=local[r][k][ix,1:]*(ratio[k] if r else 1.)
                db[:,k,self.ratio_start+2*k]=signals[1][ix,k]
                db[:,k,self.ratio_start+2*k+1]=1j*signals[1][ix,k]
            da=(da-da.mean(axis=0))/np.sqrt(self.noise[0]);db=(db-db.mean(axis=0))/np.sqrt(self.noise[1])
            for j in range(self.width):
                aa,bb=da[:,:,j],db[:,:,j]
                dh=aa.conj().T@a+a.conj().T@aa+bb.conj().T@b+b.conj().T@bb
                dc,dd=aa.conj().T@y,bb.conj().T@z
                base=(-2*np.vdot(dc,u).real-2*np.vdot(dd,v).real
                    +np.vdot(u,dh@u).real+np.vdot(v,dh@v).real+np.trace(inverse@dh).real)
                change=np.vdot(dc,v)+np.vdot(u,dd)-np.vdot(u,dh@v)
                derivative[j]+=base-2*(moment*change).real
            if fixed_sigma is None:derivative[-1]-=phase_derivative
        return dict(NLL=float(total),gradient_scaled=derivative,posterior_phase_first_moments=np.asarray(phase_means))

    def fit(self,start,*,sigma_start=.3,fit_sigma=True,maxiter=60):
        start=np.asarray(start,float)
        if start.shape != (self.width,):raise ValueError('matching RF initialization required')
        lower=np.r_[start[:self.count]-800.,start[self.count:self.code_start]-375.,
            np.tile([-.75,-40.],2*self.count),np.full(2*self.count,-5.)]
        upper=np.r_[start[:self.count]+800.,start[self.count:self.code_start]+375.,
            np.tile([.75,40.],2*self.count),np.full(2*self.count,5.)]
        center=np.clip(start,lower,upper);scale=self.scale.copy()
        if fit_sigma:
            center=np.r_[center,np.log(sigma_start)];scale=np.r_[scale,1.]
            lower=np.r_[lower,-6.];upper=np.r_[upper,np.log(np.pi)]
        def objective(x):
            result=self.statistics(center+scale*x,fixed_sigma=None if fit_sigma else 0.)
            return result['NLL'],result['gradient_scaled']
        result=minimize(objective,np.zeros(len(center)),jac=True,method='L-BFGS-B',
            bounds=list(zip((lower-center)/scale,(upper-center)/scale,strict=True)),
            options=dict(maxiter=maxiter,ftol=1e-10,gtol=1e-5,maxls=30))
        p=center+scale*result.x
        return dict(parameters=p[:self.width],sigma_rad=float(np.exp(p[-1])) if fit_sigma else 0.,
            full_parameters=p,training_NLL=float(result.fun),converged=bool(result.success),message=str(result.message),
            source_carrier_hz=p[:self.count],receiver_clock_hz=p[self.count:self.code_start],
            calls=int(result.nfev),iterations=int(result.nit),maximum_scaled_gradient=float(max(abs(result.jac))),
            boundary=bool(np.any(abs(p[:self.width]-lower[:self.width])<1e-4) or np.any(abs(p[:self.width]-upper[:self.width])<1e-4)),
            phase_variance_boundary=bool(fit_sigma and (abs(p[-1]-lower[-1])<1e-3 or abs(p[-1]-upper[-1])<1e-3)),
            fit_phase_variance=fit_sigma,absolute_CFO_covariance_not_calibrated=True)

    def predict(self,fit,segments,*,source_receiver=0):
        held=[np.asarray(ix,int) for ix in segments]
        if np.intersect1d(self.used,np.concatenate(held)).size:
            raise ValueError('held IQ overlaps phase/clock training support')
        p=np.asarray(fit['parameters']);signals=self.signals(p);signals[1]*=self.ratios(p)
        source=source_receiver;target=1-source;total=0.;frames=[]
        for ix in held:
            bs=signals[source][ix];bt=signals[target][ix]
            bs=bs-bs.mean(axis=0);bt=bt-bt.mean(axis=0)
            ys=self.y[source,ix]-self.y[source,ix].mean();yt=self.y[target,ix]-self.y[target,ix].mean()
            hs=np.diag(1/self.gain)+bs.conj().T@bs/self.noise[source]
            covariance=np.linalg.inv(hs);coefficient=covariance@(bs.conj().T@ys)/self.noise[source]
            mean=bt@coefficient
            normal=hs+bt.conj().T@bt/self.noise[target]
            def inverse(value):
                rhs=bt.conj().T@value/self.noise[target]
                return value/self.noise[target]-bt@np.linalg.solve(normal,rhs)/self.noise[target]
            cross=np.vdot(mean,inverse(yt))
            logdet=(len(ix)-1)*np.log(self.noise[target])+np.linalg.slogdet(normal)[1]+np.linalg.slogdet(covariance)[1]
            stats=dict(constant=float(logdet+(len(ix)-1)*np.log(np.pi)),y_quadratic=float(np.vdot(yt,inverse(yt)).real),
                mean_quadratic=float(np.vdot(mean,inverse(mean)).real),cross_real=float(cross.real),cross_imag=float(cross.imag))
            value=phase_NLL(stats,fit['sigma_rad'],grid_size=self.grid_size)
            total+=value;frames.append(value)
        return dict(NLL=float(total),per_frame_NLL=frames,source_receiver=source_receiver,
            held_target_signal_and_phase_never_fit=True)
