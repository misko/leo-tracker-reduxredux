"""Two-signal RF fit with explicit within-probe carrier frequency rates.

The two new coordinates are Hz/s at the IQ midpoint. Channels remain free per
original guarded frame, and no orbital or receiver-calibration prior is added.
"""

import copy
import numpy as np
from scipy.optimize import minimize
from ds23_smooth_component_workspace import SmoothComponentWorkspace


class ChirpedComponentWorkspace(SmoothComponentWorkspace):
    scale=np.r_[SmoothComponentWorkspace.scale,1000.,1000.]

    @classmethod
    def from_workspace(cls,workspace):
        result=cls.__new__(cls);result.__dict__=copy.copy(workspace.__dict__)
        result.start=np.r_[workspace.start[:6],0.,0.]
        return result

    def component_columns(self,parameters,component):
        parameters=np.asarray(parameters,float)
        a,d=super().columns_and_derivatives(parameters[3*component:3*component+3],component)
        rotation=np.exp(1j*np.pi*parameters[6+component]*self.centered**2)[:,None]
        a=a*rotation;d=d*rotation[:,:,None]
        rate=1j*np.pi*self.centered[:,None]**2*a*1000
        return a,np.concatenate((d,rate[:,:,None]),axis=2)

    def statistics(self,parameters,parity=None,derivatives=True,prediction=False):
        parameters=np.asarray(parameters,float)
        if parameters.shape!=(8,) or not np.isfinite(parameters).all():raise ValueError('eight finite carrier/code/rate coordinates required')
        (a,da),(b,db)=[self.component_columns(parameters,k) for k in [0,1]]
        design=np.column_stack((a,b,np.ones(len(self.y))))
        normal=np.zeros((8,8));rhs=np.zeros(8);error=raw=0.;count=0;held_error=held_raw=0.;held_count=0
        for segment in self.segments:
            ix=segment if parity is None else segment[self.symbol[segment]%2==parity]
            if len(ix)<25:continue
            x,y=design[ix],self.y[ix];c,_,rank,_=np.linalg.lstsq(x,y,rcond=1e-8)
            if rank!=17:raise ValueError('chirped channel model lost rank')
            residual=y-x@c;error+=float(np.vdot(residual,residual).real);raw+=float(np.vdot(y,y).real);count+=len(ix)
            if derivatives:
                d1=np.einsum('nij,i->nj',da[ix],c[:8]);d2=np.einsum('nij,i->nj',db[ix],c[8:16])
                d=np.column_stack((d1[:,:3],d2[:,:3],d1[:,3],d2[:,3]))
                q,_=np.linalg.qr(x,mode='reduced');projected=d-q@(q.conj().T@d)
                normal+=(projected.conj().T@projected).real;rhs+=(d.conj().T@residual).real
            if prediction:
                if parity is None:raise ValueError('disjoint parity required for prediction')
                test=segment[self.symbol[segment]%2!=parity];r=self.y[test]-design[test]@c
                held_error+=float(np.vdot(r,r).real);held_raw+=float(np.vdot(self.y[test],self.y[test]).real);held_count+=len(test)
        if count<=17*len(self.segments):raise ValueError('insufficient chirped support')
        return dict(score=1-error/raw,squared_error=error,raw_energy=raw,samples=count,normal=normal,rhs=rhs,
            gradient_score=2*rhs/raw,heldout_squared_error=held_error,heldout_raw_energy=held_raw,heldout_samples=held_count)

    def fit(self,start,parity=None,*,iterations=160):
        x=np.asarray(start,float);native=self.start.copy();lower=native.copy();upper=native.copy()
        lower[[0,3]]-=120;upper[[0,3]]+=120;lower[[1,4]]=-.75;upper[[1,4]]=.75
        lower[[2,5]]=-40;upper[[2,5]]=40;lower[6:]=-15000;upper[6:]=15000
        initial=self.statistics(x,parity);variance=initial['squared_error']/max(1,initial['samples']-17*len(self.segments)-8)
        def objective(u):
            s=self.statistics(u*self.scale,parity)
            return s['squared_error']/variance,-2*s['rhs']/variance
        result=minimize(objective,x/self.scale,jac=True,method='L-BFGS-B',
            bounds=list(zip(lower/self.scale,upper/self.scale,strict=True)),
            options=dict(maxiter=iterations,maxls=30,ftol=2e-15,gtol=1e-7,maxcor=12))
        physical=result.x*self.scale;s=self.statistics(physical,parity)
        noise=s['squared_error']/max(1,s['samples']-17*len(self.segments)-8)
        covariance=np.diag(self.scale)@np.linalg.solve(s['normal'],np.eye(8))@np.diag(self.scale)*noise/2
        contrast=np.zeros((2,8));contrast[0,[0,3]]=[1,-1];contrast[1,[6,7]]=[1,-1]
        return dict(parameters=physical,score=s['score'],squared_error=s['squared_error'],
            noise_variance=noise,covariance=covariance,contrast=contrast@physical,
            contrast_covariance=contrast@covariance@contrast.T,
            maximum_standardized_score=float(np.max(abs(s['rhs'])/np.sqrt(np.maximum(np.diag(s['normal'])*noise/2,1e-20)))),
            boundary=bool(np.any(physical<=lower+1e-5) or np.any(physical>=upper-1e-5)),
            optimizer_success=bool(result.success),optimizer_message=str(result.message),calls=int(result.nfev),iterations=int(result.nit))
