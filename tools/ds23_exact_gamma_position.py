"""Rao-Blackwell marginal evidence for curved noise and Student phase scales.

All Gaussian modes are integrated analytically for each precision draw. Linear
prediction is integrated from the curved posterior, retaining shared covariance
and the original independent300Hz constants. Returned calibration moments use
only curved evidence. Fractional curved powers remain generalized evidence.
"""

import numpy as np
from scipy.special import gammaln, logsumexp


def gaussian_blocks(raw, features, sigma, groups, powers):
    y,u,s,g,power=(np.asarray(v) for v in (raw,features,sigma,groups,powers))
    if (y.ndim!=1 or not len(y) or u.ndim!=2 or u.shape[0]!=len(y) or s.shape!=y.shape or g.shape!=y.shape
        or not np.issubdtype(g.dtype,np.integer) or np.any(g<0) or power.shape!=(int(g.max())+1,)
        or set(g)!=set(range(len(power))) or not all(np.isfinite(v).all() for v in (y,u,s,power))
        or np.any(s<=0) or np.any((power<=0)|(power>1))):
        raise ValueError('finite matched data, compressed noise groups and powers in(0,1] required')
    blocks=[]
    for k in range(len(power)):
        use=g==k;columns=np.flatnonzero(np.any(u[use]!=0,axis=0));a=u[use][:,columns]/s[use,None];b=y[use]/s[use]
        blocks.append(dict(columns=columns,matrix=a.T@a,rhs=a.T@b,squared=float(b@b),count=int(use.sum())))
    return dict(blocks=blocks,width=u.shape[1],powers=power.astype(float),counts=np.bincount(g),
        normalization=float(np.sum(power[g]*(np.log(2*np.pi)+2*np.log(s)))))


def linear_schur(raw, features, sigma, groups):
    """Eliminate independent linear-fragment constants before precision draws."""
    y,u,s,g=(np.asarray(v) for v in (raw,features,sigma,groups))
    if (y.ndim!=1 or u.ndim!=2 or len(u)!=len(y) or s.shape!=y.shape or g.shape!=y.shape
        or not np.issubdtype(g.dtype,np.integer) or np.any(g<0) or np.any(s<=0)
        or not all(np.isfinite(v).all() for v in (y,u,s))):
        raise ValueError('matching finite linear data, Gaussian design and positive scales required')
    w=1/s**2;ng=int(g.max())+1;bias=np.eye(ng)[g]*300
    cross=u.T@(bias*w[:,None]);normal=1+np.bincount(g,weights=300**2*w,minlength=ng)
    rhs_bias=np.bincount(g,weights=300*w*y,minlength=ng)
    return dict(matrix=u.T@(u*w[:,None])-(cross/normal)@cross.T,
        rhs=u.T@(w*y)-cross@(rhs_bias/normal),
        squared=float(y@(w*y)-np.sum(rhs_bias**2/normal)),
        normalization=float(np.sum(np.log(2*np.pi)+2*np.log(s))+np.log(normal).sum()))


def gamma_log_ratio(draw, prior_shape, prior_rate, shape, rate):
    constant=prior_shape*np.log(prior_rate)-gammaln(prior_shape)-shape*np.log(rate)+gammaln(shape)
    return np.sum(constant+(prior_shape-shape)*np.log(draw)-(prior_rate-rate)*draw,axis=1)


def normalized_weights(logweights):
    normal=logsumexp(logweights);weight=np.exp(logweights-normal)
    return dict(weights=weight,negative_twice_log_evidence=float(-2*(normal-np.log(len(weight)))),
        effective_samples=float(1/np.sum(weight**2)),maximum_normalized_weight=float(weight.max()),
        Monte_Carlo_SE=float(2*np.std(np.exp(logweights-np.max(logweights)),ddof=1)/
            np.sqrt(len(weight))/np.mean(np.exp(logweights-np.max(logweights)))))


def integrate(blocks, noise_mean, phase_indices, phase_mean, nu, *, linear=None, samples=1024, seed=2026102108, batch=64):
    noise_mean,phase_indices,phase_mean=(np.asarray(v) for v in (noise_mean,phase_indices,phase_mean))
    width=blocks['width'];power=blocks['powers'];counts=blocks['counts'];nphase=len(phase_indices)
    if (noise_mean.shape!=counts.shape or phase_mean.shape!=(nphase,) or not np.issubdtype(phase_indices.dtype,np.integer)
        or len(set(phase_indices))!=nphase or np.any(phase_indices<0) or np.any(phase_indices>=width)
        or np.any(noise_mean<=0) or np.any(phase_mean<=0) or not np.isfinite(noise_mean).all()
        or not np.isfinite(phase_mean).all() or samples<2 or batch<1 or (nphase and (nu is None or nu<=2))):
        raise ValueError('positive variational scales and distinct supported phase coordinates required')
    rng=np.random.default_rng(seed);shape=2+power*counts/2;rate=shape/noise_mean
    tau=rng.gamma(shape,1.,size=(samples,len(shape)))/rate
    ratio=gamma_log_ratio(tau,2.,2.,shape,rate)
    if nphase:
        pshape=np.full(nphase,(nu+1)/2);prate=pshape/phase_mean
        phase=rng.gamma(pshape,1.,size=(samples,nphase))/prate
        ratio+=gamma_log_ratio(phase,nu/2,(nu-2)/2,pshape,prate)
    else:phase=np.empty((samples,0))
    curved_log=np.empty(samples);joint_log=np.empty(samples);means=np.empty((samples,width))
    diagonal=np.arange(width)
    for start in range(0,samples,batch):
        stop=min(start+batch,samples);number=stop-start
        prior=np.ones((number,width));prior[:,phase_indices]=phase[start:stop]
        gram=np.zeros((number,width,width));gram[:,diagonal,diagonal]=prior
        rhs=np.zeros((number,width));squared=np.zeros(number)
        for k,block in enumerate(blocks['blocks']):
            cols=block['columns'];weight=(power[k]*tau[start:stop,k])
            gram[:,cols[:,None],cols]+=weight[:,None,None]*block['matrix']
            rhs[:,cols]+=weight[:,None]*block['rhs'];squared+=weight*block['squared']
        constant=blocks['normalization']-np.sum((power*counts)[None]*np.log(tau[start:stop]),axis=1)
        root=np.linalg.cholesky(gram);mu=np.linalg.solve(root.transpose(0,2,1),np.linalg.solve(root,rhs[:,:,None]))[:,:,0]
        means[start:stop]=mu
        value=squared-np.sum(rhs*mu,axis=1)+2*np.log(np.diagonal(root,axis1=1,axis2=2)).sum(axis=1)-np.log(prior).sum(axis=1)+constant
        curved_log[start:stop]=-.5*value+ratio[start:stop]
        if linear is None:joint_log[start:stop]=curved_log[start:stop]
        else:
            joint_root=np.linalg.cholesky(gram+linear['matrix'][None]);joint_rhs=rhs+linear['rhs'][None]
            joint_mu=np.linalg.solve(joint_root.transpose(0,2,1),np.linalg.solve(joint_root,joint_rhs[:,:,None]))[:,:,0]
            joint_value=squared+linear['squared']-np.sum(joint_rhs*joint_mu,axis=1)+2*np.log(np.diagonal(joint_root,axis1=1,axis2=2)).sum(axis=1)-np.log(prior).sum(axis=1)+constant+linear['normalization']
            joint_log[start:stop]=-.5*joint_value+ratio[start:stop]
    curved=normalized_weights(curved_log);joint=normalized_weights(joint_log)
    calibration=curved['weights']@means
    return dict(curved={k:v for k,v in curved.items() if k!='weights'},joint={k:v for k,v in joint.items() if k!='weights'},
        curved_coefficient_mean=calibration,curved_log_importance_weights=curved_log,joint_log_importance_weights=joint_log,
        samples=samples,seed=seed,linear_observations_do_not_update_calibration_moments=True)
