"""Joint-source phase extraction with disjoint fit, qualification and evaluation."""
import numpy as np
from scipy.optimize import minimize_scalar
from leo.analysis.starlink.adaptive_dual_rx_phase import fit_linear_phasor

def masks(n=70000,block=200,seed=20261003):
    labels=np.arange((n+block-1)//block);rng=np.random.default_rng(seed);order=rng.permutation(labels)
    assignment=np.empty(len(labels),int);assignment[order[:len(labels)//2]]=0;assignment[order[len(labels)//2:3*len(labels)//4]]=1;assignment[order[3*len(labels)//4:]]=2
    group=np.arange(n)//block
    return [assignment[group]==k for k in range(3)],group

def fit_score(X,y,fit,quality,groups):
    coefficient=np.linalg.lstsq(X[fit],y[fit],rcond=None)[0]
    error=abs(y[quality]-X[quality]@coefficient)**2
    return coefficient,np.array([error[groups[quality]==g].sum() for g in np.unique(groups[quality])])

def contrast(first,second,energy):
    difference=first-second;n=len(difference)
    fraction=float(difference.sum()/max(energy,1e-30))
    se=np.sqrt(n*np.var(difference,ddof=1))
    z=float(difference.sum()/max(se,1e-30)) if abs(fraction)>1e-12 else 0.
    return dict(fraction=fraction,z=z)

def common_frequency(values,times,midpoint):
    """Profile separate phase intercepts but one simultaneous receiver rate."""
    grid=np.arange(-375.,376.)
    score=sum(abs(np.exp(-2j*np.pi*grid[:,None]*(t-midpoint))@z) for z,t in zip(values,times))
    best=int(np.argmax(score));lo=grid[max(0,best-2)];hi=grid[min(len(grid)-1,best+2)]
    objective=lambda f:-sum(abs(np.sum(z*np.exp(-2j*np.pi*f*(t-midpoint)))) for z,t in zip(values,times))
    return float(minimize_scalar(objective,bounds=(lo,hi),method='bounded',options={'xatol':1e-8}).x)

def extract(designs,controls,iq,rate=1e7,shared_frequency=False):
    (fit,quality,evaluation),groups=masks(len(iq));coefficients=[];metrics=[];centers=[];offset=np.cumsum([0]+[d.shape[1] for d in designs[0]])
    for rx in (0,1):
        X=np.column_stack(designs[rx]);c,q=fit_score(X,iq[:,rx],fit,quality,groups)
        held=np.linalg.lstsq(X[evaluation],iq[evaluation,rx],rcond=None)[0];coefficients.append((c,held))
        energy=float(np.sum(abs(iq[quality,rx])**2))
        for mode in (0,1):
            donor=designs[rx][1-mode];_,single=fit_score(donor,iq[:,rx],fit,quality,groups)
            _,control=fit_score(np.column_stack([donor,controls[rx][mode]]),iq[:,rx],fit,quality,groups)
            a=contrast(single,q,energy);b=contrast(control,q,energy)
            metrics.append(dict(receiver=rx,mode=mode,donor_improvement=a,control_improvement=b,qualified=bool(a['fraction']>1e-8 and a['z']>3 and b['z']>3)))
        if rx==0:
            power=abs(X)**2;times=np.arange(len(iq))/rate
            for mask in (fit,evaluation):
                centers.append((power[mask]*times[mask,None]).sum(axis=0)/np.maximum(power[mask].sum(axis=0),1e-30))
    modes=[];midpoint=len(iq)/(2*rate)
    common=None
    if shared_frequency:
        values=[coefficients[1][0][offset[m]:offset[m+1]]*np.conj(coefficients[0][0][offset[m]:offset[m+1]]) for m in (0,1)]
        times=[centers[0][offset[m]:offset[m+1]] for m in (0,1)]
        common=common_frequency(values,times,midpoint)
    for mode in (0,1):
        take=slice(offset[mode],offset[mode+1]);tr=coefficients[1][0][take]*np.conj(coefficients[0][0][take]);he=coefficients[1][1][take]*np.conj(coefficients[0][1][take])
        frequency,_,_=fit_linear_phasor(tr,centers[0][take],np.maximum(abs(tr),1e-30),midpoint)
        independent=frequency
        if common is not None:frequency=common
        def stat(z,t):
            value=z*np.exp(-2j*np.pi*frequency*(t-midpoint));mean=np.mean(value)
            return dict(phase_rad=float(np.angle(mean)),R=float(abs(mean)/max(np.mean(abs(value)),1e-30)))
        modes.append(dict(mode=mode,qualified=all(r['qualified'] for r in metrics if r['mode']==mode),frequency_hz=frequency,train=stat(tr,centers[0][take]),evaluation=stat(he,centers[1][take])))
        if shared_frequency:modes[-1]['independent_frequency_hz']=independent
    return dict(modes=modes,metrics=metrics,both_qualified=all(r['qualified'] for r in modes),sample_counts=[int(m.sum()) for m in (fit,quality,evaluation)])
