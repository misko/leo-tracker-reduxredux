"""Pure fixed-background draw, pair design and normalized Gaussian control."""
import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp

PERIOD=1/4.4e-6
ALIASES=np.arange(-4,5)


def pair_choice(frequency,derivative,sd,covariance,eligible,norads):
    root=np.linalg.cholesky(covariance)
    f=solve_triangular(root,np.asarray(frequency).T,lower=True).T
    d=solve_triangular(root,np.asarray(derivative).T,lower=True).T*np.asarray(sd)[:,None]
    choices=[]
    eligible=sorted(eligible,key=lambda j:int(norads[j]))
    for ii,a in enumerate(eligible):
        for b in eligible[ii+1:]:
            delta=f[a]-f[b];u=np.column_stack((d[a],d[b]))/np.sqrt(2)
            rhs=u.T@delta
            alpha=np.linalg.solve(np.eye(2)+u.T@u,rhs)
            residual=delta-u@alpha
            metric=float(residual@residual+alpha@alpha)
            choices.append((metric,int(norads[a]),int(norads[b]),a,b))
    if not choices:raise ValueError('no full-visible confusable pair; no replacement')
    return min(choices),choices


def near_null(times,frequencies,derivatives,phase_variances,modes,native_sigma):
    times=np.asarray(times);n=len(times)
    z=2*(times-times.min())/np.ptp(times)
    q=np.linalg.qr(np.polynomial.legendre.legvander(z-1,4),mode='reduced')[0]
    delta=np.asarray(frequencies[0])-frequencies[1]
    columns=[delta[:,None]/2]
    for d,v,b in zip(derivatives,phase_variances,modes,strict=True):
        columns += [np.asarray(d)[:,None]*np.sqrt(v/2),np.asarray(b)/np.sqrt(2)]
    design=np.column_stack(columns);projected=q.T@design
    floor=n/5*float(np.median(native_sigma))**2
    coefficient_cov=projected@projected.T+floor*np.eye(5)
    factor=q@np.linalg.cholesky(coefficient_cov)
    return (np.asarray(frequencies[0])+frequencies[1])/2,factor,q,coefficient_cov,floor


def gaussian_score(raw,covariance,mean,factor):
    covariance=np.asarray(covariance)+np.asarray(factor)@np.asarray(factor).T
    root=np.linalg.cholesky(covariance);shift=np.asarray(raw)[None]-mean+ALIASES[:,None]*PERIOD
    white=solve_triangular(root,shift.T,lower=True).T
    costs=np.sum(white**2,axis=1)+2*np.log(np.diag(root)).sum()+len(raw)*np.log(2*np.pi)
    return float(-2*(logsumexp(-costs/2)-np.log(len(ALIASES)))),costs


def gaussian_qr_score(raw,covariance,mean,factor):
    root=np.linalg.cholesky(covariance)
    b=solve_triangular(root,np.asarray(factor),lower=True)
    design=np.vstack((b,np.eye(b.shape[1])))
    q,r=np.linalg.qr(design,mode='reduced')
    shifts=np.asarray(raw)[None]-mean+ALIASES[:,None]*PERIOD
    w=solve_triangular(root,shifts.T,lower=True).T
    targets=np.column_stack((w,np.zeros((len(w),b.shape[1]))))
    residual=targets-(targets@q)@q.T
    costs=np.sum(residual**2,axis=1)+2*np.log(np.diag(root)).sum()+2*np.log(abs(np.diag(r))).sum()+len(raw)*np.log(2*np.pi)
    return float(-2*(logsumexp(-costs/2)-np.log(len(ALIASES))))


def draw(mean,covariance,physical_mean,factor,seed,trial,case=0):
    children=np.random.SeedSequence([seed,case,trial]).spawn(4)
    rng=[np.random.Generator(np.random.PCG64(s)) for s in children]
    z=rng[1].normal(size=np.asarray(factor).shape[1]);noise_z=rng[2].normal(size=len(mean));alias=int(rng[3].choice(ALIASES))
    noise=np.linalg.cholesky(covariance)@noise_z
    values=np.asarray(mean)+physical_mean+factor@z+noise-alias*PERIOD
    return values,dict(latent_z=z,noise_z=noise_z,noise_Hz=noise,alias=alias,
        phase_uniform=float(rng[0].uniform()),children=[s.generate_state(4).tolist() for s in children])
