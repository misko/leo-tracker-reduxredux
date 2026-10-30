"""Exact two-family phase integration with shared Gaussian calibration uncertainty."""
import numpy as np
from scipy.linalg import cho_solve
from scipy.special import logsumexp


def two_family_phase_evidence(observed, means, base_covariance, modes, log_priors, visible, *, max_pairs=32768):
    """Integrate independent orbit modes and phases, retaining cross-family covariance.

    The base covariance contains measurement/track noise and a single shared
    calibration covariance. No fitted calibration mean is changed. Work arrays
    are chunked; the log phase table is retained for exact marginalization.
    """
    if any(len(v)!=2 for v in (observed,means,modes,log_priors,visible)) or max_pairs<1:
        raise ValueError('exactly two families and a positive chunk budget required')
    y=[np.asarray(v,float) for v in observed];m=[np.asarray(v,float) for v in means]
    u=[np.asarray(v,float) for v in modes];lp=[np.asarray(v,float) for v in log_priors]
    valid=[np.asarray(v,bool) for v in visible];b=np.asarray(base_covariance,float)
    for k in range(2):
        if y[k].ndim!=1 or not len(y[k]) or m[k].ndim!=2 or m[k].shape[1:]!=y[k].shape or not len(m[k]):
            raise ValueError('matching nonempty observation and phase geometry required')
        if u[k].ndim!=3 or u[k].shape[:2]!=m[k].shape or not u[k].shape[2] or lp[k].shape!=(len(m[k]),) or valid[k].shape!=lp[k].shape:
            raise ValueError('matching orbit modes and phase priors required')
        if not all(np.isfinite(v).all() for v in (y[k],m[k],u[k])) or not np.isfinite(lp[k]).any() or np.isnan(lp[k]).any() or np.isposinf(lp[k]).any():
            raise ValueError('finite geometry and a finite phase prior required')
    n1,n2=map(len,y);n=n1+n2
    if b.shape!=(n,n) or not np.isfinite(b).all() or not np.allclose(b,b.T,rtol=1e-10,atol=1e-8):
        raise ValueError('matching symmetric base covariance required')
    root=np.linalg.cholesky((b+b.T)/2);precision=cho_solve((root,True),np.eye(n))
    p11,p12,p22=precision[:n1,:n1],precision[:n1,n1:],precision[n1:,n1:]
    r1,r2=y[0]-m[0],y[1]-m[1];u1,u2=u;d1,d2=u1.shape[2],u2.shape[2]
    a1=np.einsum('kna,nm->kam',u1,p11);a2=np.einsum('kna,nm->kam',u2,p22)
    cross=np.einsum('kna,nm->kam',u1,p12)
    g1=np.eye(d1)+np.einsum('kan,knb->kab',a1,u1);g2=np.eye(d2)+np.einsum('kan,knb->kab',a2,u2)
    h1=np.einsum('kan,kn->ka',a1,r1);h2=np.einsum('kan,kn->ka',a2,r2)
    q1=np.einsum('kn,nm,km->k',r1,p11,r1);q2=np.einsum('kn,nm,km->k',r2,p22,r2)
    projected=r1@p12;counts=[len(v) for v in m];prior=[v-logsumexp(v) for v in lp]
    log_joint=np.full(counts,-np.inf);best=-np.inf;best_coeff=np.zeros(d1+d2)
    constant=2*np.log(np.diag(root)).sum()+n*np.log(2*np.pi)
    rows_per_chunk=max(1,max_pairs//counts[1])
    for start in range(0,counts[0],rows_per_chunk):
        end=min(start+rows_per_chunk,counts[0]);shape=(end-start,counts[1]);gram=np.empty((*shape,d1+d2,d1+d2))
        gram[:,:,:d1,:d1]=g1[start:end,None];gram[:,:,d1:,d1:]=g2[None]
        off=np.einsum('ian,jnb->ijab',cross[start:end],u2)
        gram[:,:,:d1,d1:]=off;gram[:,:,d1:,:d1]=off.swapaxes(-1,-2)
        rhs=np.concatenate((h1[start:end,None]+np.einsum('ian,jn->ija',cross[start:end],r2),
            h2[None]+np.einsum('jna,in->ija',u2,projected[start:end])),axis=-1)
        coefficient=np.linalg.solve(gram,rhs[...,None])[...,0]
        raw=q1[start:end,None]+q2[None]+2*projected[start:end]@r2.T
        sign,logdet=np.linalg.slogdet(gram)
        if not np.all(sign>0):raise ValueError('orbital precision is not positive definite')
        log_density=-.5*(raw-np.sum(rhs*coefficient,axis=-1)+logdet+constant)
        joint=log_density+prior[0][start:end,None]+prior[1][None]
        joint=np.where(valid[0][start:end,None]&valid[1][None],joint,-np.inf);log_joint[start:end]=joint
        flat=int(np.argmax(joint));score=joint.flat[flat]
        if score>best:best=score;best_coeff=coefficient.reshape(-1,d1+d2)[flat].copy()
    evidence=float(logsumexp(log_joint));weights=np.exp(log_joint-evidence) if np.isfinite(evidence) else np.zeros(counts)
    k=np.unravel_index(int(np.argmax(log_joint)),tuple(counts))
    return dict(negative_twice_log_density=-2*evidence,phase_marginals=[weights.sum(axis=1),weights.sum(axis=0)],
        joint_map_indices=list(map(int,k)),orbital_map_mean=[best_coeff[:d1],best_coeff[d1:]],
        visible_prior_mass=float(np.exp(prior[0][valid[0]]).sum()*np.exp(prior[1][valid[1]]).sum()),
        phase_pair_count=int(np.prod(counts)),receiver_covariance_integrated_once=True)
