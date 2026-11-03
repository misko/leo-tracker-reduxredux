"""Variable-projection frequency fitting on a fixed common sample support."""
import numpy as np
from scipy.optimize import minimize, minimize_scalar


def profile(parts, times, samples, delta_khz):
    matrices=[a*np.exp(2j*np.pi*1000*d*times)[:,None] for a,d in zip(parts,delta_khz,strict=True)]
    matrix=np.column_stack(matrices)
    beta,_,rank,singular=np.linalg.lstsq(matrix,samples,rcond=1e-10)
    assert rank==matrix.shape[1]
    residual=samples-matrix@beta
    energy=float(np.vdot(samples,samples).real)
    assert energy>0
    derivatives=[];offset=0
    for a in matrices:
        component=a@beta[offset:offset+a.shape[1]];offset+=a.shape[1]
        derivatives.append(-2*float(np.vdot(residual,2j*np.pi*1000*times*component).real)/energy)
    return float(np.vdot(residual,residual).real/energy),np.asarray(derivatives),beta,float(singular[0]/singular[-1])


def single_frequency(matrix,times,samples):
    q,_=np.linalg.qr(matrix,mode='reduced')
    energy=float(np.vdot(samples,samples).real)
    def loss(delta):
        projection=q.conj().T@(samples*np.exp(-2j*np.pi*1000*delta*times))
        return 1.-float(np.vdot(projection,projection).real)/energy
    grid=np.linspace(-1.5,1.5,121);scores=[loss(f) for f in grid]
    i=int(np.argmin(scores));choices=[(scores[i],float(grid[i]))]
    success=True
    if 0<i<len(grid)-1:
        fit=minimize_scalar(loss,bounds=(grid[i-1],grid[i+1]),method='bounded',options=dict(xatol=1e-10,maxiter=80))
        success=bool(fit.success)
        if success:choices.append((float(fit.fun),float(fit.x)))
    score,delta=min(choices)
    return dict(delta_khz=delta,training_nmse=score,refinement_success=success,boundary=abs(delta)>=1.499999)


def joint_fits(parts,times,samples,separate):
    records=[]
    for seed in ([0.,0.],list(separate)):
        def objective(x):
            loss,gradient,_,_=profile(parts,times,samples,x)
            return loss,gradient
        fit=minimize(objective,seed,jac=True,method='L-BFGS-B',bounds=[(-1.5,1.5)]*2,
                     options=dict(maxiter=80,maxfun=120,ftol=1e-13,gtol=1e-8,maxls=25))
        loss,gradient,_,condition=profile(parts,times,samples,fit.x)
        discrepancies=[]
        for axis in range(2):
            d=np.eye(2)[axis]*1e-5
            finite=(profile(parts,times,samples,fit.x+d)[0]-profile(parts,times,samples,fit.x-d)[0])/2e-5
            discrepancies.append(abs(finite-gradient[axis]))
        boundary=bool(np.max(abs(fit.x))>=1.499999)
        audit=max(discrepancies);g=float(np.max(abs(gradient)))
        records.append(dict(seed=seed,delta_khz=fit.x.tolist(),training_nmse=loss,
                            success=bool(fit.success),message=str(fit.message),boundary=boundary,
                            gradient_max=g,finite_difference_discrepancy=audit,condition=condition,
                            nfev=int(fit.nfev),qualified=bool(fit.success and not boundary and g<1e-5 and audit<1e-6)))
    valid=[r for r in records if r['qualified']]
    return records,min(valid,key=lambda r:r['training_nmse']) if valid else None


def held_score(parts,times,samples,training,held,delta):
    _,_,coefficients,_=profile([p[training] for p in parts],times[training],samples[training],delta)
    matrix=np.column_stack([p[held]*np.exp(2j*np.pi*1000*d*times[held])[:,None] for p,d in zip(parts,delta,strict=True)])
    return float(np.sum(abs(samples[held]-matrix@coefficients)**2)/np.sum(abs(samples[held])**2))
