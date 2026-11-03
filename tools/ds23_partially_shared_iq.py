"""Allow a pilot component to be unrelated across the two receiver streams.

Each source component has one circular Gaussian frame gain. A matched target
uses that same gain; an unmatched target has its own independent gain. One
receiver phase is shared only where the waveform supplies cross-RX evidence.
The model has no satellite, orbit, location or truth input.
"""

import numpy as np
from scipy.optimize import minimize

from ds23_phase_marginal_iq import PhaseMarginalIQ, phase_integral
from ds23_shared_receiver_phase import phase_NLL


class PartiallySharedIQ(PhaseMarginalIQ):
    def __init__(self,*args,shared_components,**kwargs):
        super().__init__(*args,**kwargs)
        self.shared = np.asarray(shared_components,bool)
        if self.shared.shape != (self.count,):
            raise ValueError('one correspondence flag per physical component required')
        if not self.shared.all() and self.clock_count != self.count:
            raise ValueError('unrelated components need independent target carrier contrasts')
        self.map0 = np.arange(self.count)
        self.map1 = self.map0.copy()
        self.map1[~self.shared] = self.count+np.arange((~self.shared).sum())
        self.latent_count = self.count+(~self.shared).sum()
        self.latent_gain = np.r_[self.gain,self.gain[~self.shared]]

    def expanded(self,physical,receiver):
        value=np.asarray(physical)
        result=np.zeros((value.shape[0],self.latent_count)+value.shape[2:],complex)
        result[:,self.map1 if receiver else self.map0]=value
        return result

    def statistics(self,parameters,*,fixed_sigma=None,gradient=True):
        parameters=np.asarray(parameters,float);p=parameters[:self.width]
        sigma=float(np.exp(parameters[-1])) if fixed_sigma is None else float(fixed_sigma)
        if parameters.shape != (self.width+(fixed_sigma is None),):
            raise ValueError('RF coordinates and optional log phase SD required')
        if not np.isfinite(sigma) or sigma < 0 or sigma > np.pi:
            raise ValueError('receiver phase SD must be between zero and pi')
        if gradient:signals,local=self.signals(p,True)
        else:signals=self.signals(p)
        ratio=self.ratios(p);total=0.;derivative=np.zeros(len(parameters));moments=[]
        for ix in self.frames:
            a=self.expanded(signals[0][ix],0);b=self.expanded(signals[1][ix]*ratio,1)
            a=(a-a.mean(axis=0))/np.sqrt(self.noise[0]);b=(b-b.mean(axis=0))/np.sqrt(self.noise[1])
            y=(self.y[0,ix]-self.y[0,ix].mean())/np.sqrt(self.noise[0])
            z=(self.y[1,ix]-self.y[1,ix].mean())/np.sqrt(self.noise[1])
            h=np.diag(1/self.latent_gain)+a.conj().T@a+b.conj().T@b
            inverse=np.linalg.inv(h);c,d=a.conj().T@y,b.conj().T@z
            u,v=inverse@c,inverse@d;cross=np.vdot(c,v)
            integral,moment,phase_derivative=phase_integral(cross,sigma,self.grid_size)
            normalizer=np.linalg.slogdet(h)[1]+np.log(self.latent_gain).sum()+(len(ix)-1)*np.log(np.pi*self.noise).sum()
            total+=float(np.vdot(y,y).real+np.vdot(z,z).real-np.vdot(c,u).real-np.vdot(d,v).real+normalizer-integral)
            moments.append(moment)
            if not gradient:continue
            da=np.zeros((len(ix),self.count,self.width),complex);db=np.zeros_like(da)
            for k in range(self.count):
                da[:,k,k]=local[0][k][ix,0];db[:,k,k]=local[1][k][ix,0]*ratio[k]
                db[:,k,self.count+(k if self.clock_count>1 else 0)]+=local[1][k][ix,0]*ratio[k]
                for r,design in [(0,da),(1,db)]:
                    begin=self.code_start+2*self.count*r+2*k
                    design[:,k,begin:begin+2]=local[r][k][ix,1:]*(ratio[k] if r else 1.)
                db[:,k,self.ratio_start+2*k]=signals[1][ix,k]
                db[:,k,self.ratio_start+2*k+1]=1j*signals[1][ix,k]
            da=self.expanded(da,0);db=self.expanded(db,1)
            da=(da-da.mean(axis=0))/np.sqrt(self.noise[0]);db=(db-db.mean(axis=0))/np.sqrt(self.noise[1])
            for j in range(self.width):
                aa,bb=da[:,:,j],db[:,:,j]
                dh=aa.conj().T@a+a.conj().T@aa+bb.conj().T@b+b.conj().T@bb
                dc,dd=aa.conj().T@y,bb.conj().T@z
                base=(-2*np.vdot(dc,u).real-2*np.vdot(dd,v).real+np.vdot(u,dh@u).real
                    +np.vdot(v,dh@v).real+np.trace(inverse@dh).real)
                change=np.vdot(dc,v)+np.vdot(u,dd)-np.vdot(u,dh@v)
                derivative[j]+=base-2*(moment*change).real
            if fixed_sigma is None:derivative[-1]-=phase_derivative
        return dict(NLL=float(total),gradient_scaled=derivative,posterior_phase_first_moments=np.asarray(moments))

    def fit(self,start,*,sigma_start=.3,fit_sigma=True,maxiter=60):
        start=np.asarray(start,float).copy()
        if start.shape != (self.width,):raise ValueError('matching RF initialization required')
        if not self.shared.any():fit_sigma=False
        active=np.ones(self.width,bool)
        for k in np.flatnonzero(~self.shared):
            # A circular independent target gain makes its channel phase a gauge.
            j=self.ratio_start+2*k
            start[j]=abs(start[j]+1j*start[j+1]);start[j+1]=0.;active[j+1]=False
        lower=np.r_[start[:self.count]-800.,start[self.count:self.code_start]-375.,
            np.tile([-.75,-40.],2*self.count),np.full(2*self.count,-5.)]
        upper=np.r_[start[:self.count]+800.,start[self.count:self.code_start]+375.,
            np.tile([.75,40.],2*self.count),np.full(2*self.count,5.)]
        lower[self.ratio_start+2*np.flatnonzero(~self.shared)]=.02
        center=np.clip(start,lower,upper);scale=self.scale.copy()
        if fit_sigma:
            center=np.r_[center,np.log(sigma_start)];scale=np.r_[scale,1.]
            lower=np.r_[lower,-6.];upper=np.r_[upper,np.log(np.pi)];active=np.r_[active,True]
        def unpack(x):
            p=center.copy();p[active]+=scale[active]*x;return p
        def objective(x):
            result=self.statistics(unpack(x),fixed_sigma=None if fit_sigma else 0.)
            return result['NLL'],result['gradient_scaled'][active]
        result=minimize(objective,np.zeros(active.sum()),jac=True,method='L-BFGS-B',
            bounds=list(zip(((lower-center)/scale)[active],((upper-center)/scale)[active],strict=True)),
            options=dict(maxiter=maxiter,ftol=1e-10,gtol=1e-5,maxls=30))
        p=unpack(result.x);clock=p[self.count:self.code_start]
        physical=clock if self.clock_count==1 else clock[self.shared]
        return dict(parameters=p[:self.width],full_parameters=p,training_NLL=float(result.fun),
            sigma_rad=float(np.exp(p[-1])) if fit_sigma else 0.,fit_phase_variance=fit_sigma,
            converged=bool(result.success),message=str(result.message),calls=int(result.nfev),iterations=int(result.nit),
            active_parameters=int(active.sum()),maximum_scaled_gradient=float(max(abs(result.jac))),
            boundary=bool(np.any(abs(p[:self.width][active[:self.width]]-lower[:self.width][active[:self.width]])<1e-4)
                or np.any(abs(p[:self.width][active[:self.width]]-upper[:self.width][active[:self.width]])<1e-4)),
            phase_variance_boundary=bool(fit_sigma and (abs(p[-1]-lower[-1])<1e-3 or abs(p[-1]-upper[-1])<1e-3)),
            source_carrier_hz=p[:self.count],receiver_frequency_contrasts_hz=clock,
            physical_receiver_clock_hz=physical,shared_components=self.shared,
            absolute_CFO_covariance_not_calibrated=True)

    def predict(self,fit,segments,*,source_receiver=0):
        held=[np.asarray(ix,int) for ix in segments]
        if source_receiver not in (0,1):raise ValueError('receiver zero or one required')
        if np.intersect1d(self.used,np.concatenate(held)).size:
            raise ValueError('held IQ overlaps phase/clock training support')
        p=np.asarray(fit['parameters']);physical=self.signals(p);physical[1]*=self.ratios(p)
        signals=[self.expanded(physical[r],r) for r in [0,1]]
        source=source_receiver;target=1-source;total=0.;frames=[]
        for ix in held:
            bs=signals[source][ix]-signals[source][ix].mean(axis=0)
            bt=signals[target][ix]-signals[target][ix].mean(axis=0)
            ys=self.y[source,ix]-self.y[source,ix].mean();yt=self.y[target,ix]-self.y[target,ix].mean()
            hs=np.diag(1/self.latent_gain)+bs.conj().T@bs/self.noise[source]
            covariance=np.linalg.inv(hs);coefficient=covariance@(bs.conj().T@ys)/self.noise[source]
            mean=bt@coefficient;normal=hs+bt.conj().T@bt/self.noise[target]
            def inverse(value):
                return value/self.noise[target]-bt@np.linalg.solve(normal,bt.conj().T@value)/self.noise[target]**2
            cross=np.vdot(mean,inverse(yt))
            logdet=(len(ix)-1)*np.log(self.noise[target])+np.linalg.slogdet(normal)[1]-np.linalg.slogdet(hs)[1]
            stats=dict(constant=float(logdet+(len(ix)-1)*np.log(np.pi)),y_quadratic=float(np.vdot(yt,inverse(yt)).real),
                mean_quadratic=float(np.vdot(mean,inverse(mean)).real),cross_real=float(cross.real),cross_imag=float(cross.imag))
            value=phase_NLL(stats,fit['sigma_rad'],grid_size=self.grid_size)
            total+=value;frames.append(value)
        return dict(NLL=float(total),per_frame_NLL=frames,source_receiver=source_receiver,
            held_target_signal_and_phase_never_fit=True)
