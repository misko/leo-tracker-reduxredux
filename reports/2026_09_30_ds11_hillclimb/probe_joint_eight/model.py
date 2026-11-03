"""Noncoherent eight-frame variable projection with shared frequency offsets."""
import importlib.util
from pathlib import Path

import numpy as np
from scipy.optimize import minimize, minimize_scalar

path=Path(__file__).resolve().parent.parent/'probe_joint_frequency/model.py'
spec=importlib.util.spec_from_file_location('single_frame_frequency_model',path)
single=importlib.util.module_from_spec(spec)
spec.loader.exec_module(single)


def profile(blocks,delta):
    total=sum(float(np.vdot(b['samples'],b['samples']).real) for b in blocks)
    loss=0.;gradient=np.zeros(2);condition=0.
    for b in blocks:
        weight=float(np.vdot(b['samples'],b['samples']).real)/total
        value,g,_,c=single.profile(b['parts'],b['times'],b['samples'],delta)
        loss+=weight*value;gradient+=weight*g;condition=max(condition,c)
    return loss,gradient,condition


def separate_fit(blocks,candidate):
    prepared=[(np.linalg.qr(b['parts'][candidate],mode='reduced')[0],b['times'],b['samples']) for b in blocks]
    energy=sum(float(np.vdot(y,y).real) for _,_,y in prepared)
    def loss(delta):
        explained=0.
        for q,t,y in prepared:
            z=q.conj().T@(y*np.exp(-2j*np.pi*1000*delta*t))
            explained+=float(np.vdot(z,z).real)
        return 1.-explained/energy
    grid=np.linspace(-1.5,1.5,121);scores=[loss(x) for x in grid];i=int(np.argmin(scores))
    choices=[(scores[i],float(grid[i]))];success=True
    if 0<i<len(grid)-1:
        fit=minimize_scalar(loss,bounds=(grid[i-1],grid[i+1]),method='bounded',options=dict(xatol=1e-10,maxiter=80))
        success=bool(fit.success)
        if success:choices.append((float(fit.fun),float(fit.x)))
    value,x=min(choices)
    return dict(delta_khz=x,training_nmse=value,refinement_success=success,boundary=abs(x)>=1.499999)


def fit_joint(blocks,separate):
    records=[]
    for seed in ([0.,0.],list(separate)):
        def objective(x):
            value,gradient,_=profile(blocks,x)
            return value,gradient
        fit=minimize(objective,seed,jac=True,method='L-BFGS-B',bounds=[(-1.5,1.5)]*2,
                     options=dict(maxiter=80,maxfun=120,ftol=1e-13,gtol=1e-8,maxls=25))
        loss,g,condition=profile(blocks,fit.x);audit=0.
        for axis in range(2):
            d=np.eye(2)[axis]*1e-5
            finite=(profile(blocks,fit.x+d)[0]-profile(blocks,fit.x-d)[0])/2e-5
            audit=max(audit,abs(finite-g[axis]))
        boundary=bool(np.max(abs(fit.x))>=1.499999);maximum=float(np.max(abs(g)))
        records.append(dict(seed=seed,delta_khz=fit.x.tolist(),training_nmse=loss,success=bool(fit.success),
                            message=str(fit.message),boundary=boundary,gradient_max=maximum,
                            finite_difference_discrepancy=float(audit),condition=condition,nfev=int(fit.nfev),
                            qualified=bool(fit.success and not boundary and maximum<1e-5 and audit<1e-6)))
    valid=[r for r in records if r['qualified']]
    return records,min(valid,key=lambda r:r['training_nmse']) if valid else None


def held_score(blocks,delta):
    numerator=0.;denominator=0.;frame_scores=[]
    for b in blocks:
        score=single.held_score(b['parts'],b['times'],b['samples'],b['training'],b['held'],delta)
        energy=float(np.sum(abs(b['samples'][b['held']])**2))
        numerator+=score*energy;denominator+=energy;frame_scores.append(score)
    return dict(nmse=numerator/denominator,frame_nmse=frame_scores)
