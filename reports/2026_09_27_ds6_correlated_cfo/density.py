"""Exact multivariate-t density with offset and slope covariance components."""
import numpy as np
from scipy.special import gammaln


class TrackDensity:
    def __init__(self,t,mask,slope_scale,noise_scale=100.,offset_scale=1e6,df=4.):
        self.mask=np.asarray(mask,dtype=bool);self.df=df;self.noise_scale=noise_scale
        t=np.asarray(t,dtype=float);t=t-t[self.mask].mean()
        self.parts=[]
        for select in [self.mask,np.ones(len(t),dtype=bool)]:
            n=int(select.sum());u=np.column_stack([np.ones(n)*offset_scale,t[select]*slope_scale])
            q,s,_=np.linalg.svd(u,full_matrices=False)
            variance=noise_scale**2+s*s
            logdet=(n-len(s))*np.log(noise_scale**2)+np.log(variance).sum()
            constant=gammaln((df+n)/2)-gammaln(df/2)-.5*(n*np.log(df*np.pi)+logdet)
            self.parts.append((select,q,variance,float(constant),n))

    def scores(self,residual):
        residual=np.asarray(residual,dtype=float);scores=[]
        for select,q,variance,constant,n in self.parts:
            r=residual[...,select];parallel=r@q;orthogonal=r-parallel@q.T
            quadratic=np.sum(orthogonal**2,axis=-1)/self.noise_scale**2+np.sum(parallel**2/variance,axis=-1)
            scores.append(constant-(self.df+n)/2*np.log1p(quadratic/self.df))
        return scores[0],scores[1]
