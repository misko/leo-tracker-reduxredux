"""Fit-only clustered phase uncertainty and weighted circular dwell model."""
import numpy as np
from scipy.optimize import least_squares

def phase_covariance(designs,iq,mask,groups):
    """Delta-method covariance; correlated RX residuals share physical blocks."""
    labels=np.unique(groups[mask]);influences=[];conditions=[]
    for X,y in zip(designs,iq.T):
        x=X[mask];y=y[mask];beta=np.linalg.lstsq(x,y,rcond=None)[0]
        residual=y-x@beta;gram=x.conj().T@x;conditions.append(float(np.linalg.cond(gram)))
        scores=np.array([x[groups[mask]==g].conj().T@residual[groups[mask]==g] for g in labels])
        change=np.linalg.solve(gram,scores.T).T
        influences.append(np.imag(change/np.where(abs(beta)>1e-15,beta,1e-15)))
    influence=influences[1]-influences[0]
    correction=len(labels)/max(len(labels)-1,1)*mask.sum()/max(mask.sum()-designs[0].shape[1],1)
    covariance=influence.T@influence*correction
    return covariance,conditions

def weights(covariance):
    # Fixed precision floor and cap; no evaluation data enter these choices.
    precision=1/np.maximum(np.diag(covariance),np.radians(.5)**2)
    return np.minimum(precision/np.median(precision),100.)

def residual(pred,z,weight):
    d=(np.exp(1j*pred)-z)*np.sqrt(weight)
    return np.r_[d.real,d.imag]

def fit(windows,indices,bound,weighted):
    ref=np.mean([w['midpoint'] for w in windows]);best=None
    for slope in np.linspace(-bound,bound,5):
        dd=np.angle(np.mean([np.exp(1j*(windows[i]['result']['modes'][1]['train']['phase_rad']-windows[i]['result']['modes'][0]['train']['phase_rad']-2*np.pi*slope*(windows[i]['midpoint']-ref))) for i in indices]))
        initial=[]
        for i in indices:
            w=windows[i];initial.extend([w['result']['modes'][0]['train']['phase_rad']+(dd+2*np.pi*slope*(w['midpoint']-ref))/2,np.mean([m['frequency_hz'] for m in w['result']['modes']])])
        initial.extend([dd,slope*.999])
        def fun(p):
            errors=[]
            for j,i in enumerate(indices):
                w=windows[i];d=w['data']['fit'];a,f=p[2*j:2*j+2]
                pred=a+2*np.pi*f*d['t']+d['s']/2*(p[-2]+2*np.pi*p[-1]*(w['midpoint']+d['t']-ref))
                errors.extend(residual(pred,d['z'],w['weight'] if weighted else 1.))
            return errors
        lo=np.full(len(initial),-np.inf);hi=-lo;lo[-1]=-bound;hi[-1]=bound
        solution=least_squares(fun,initial,bounds=(lo,hi),max_nfev=200)
        if best is None or solution.cost<best.cost:best=solution
    return dict(dd=float(best.x[-2]),rate=float(best.x[-1]),ref=float(ref))

def evaluate(windows,train,held,bound,weighted):
    model=fit(windows,train,bound,weighted);errors=[]
    for i in held:
        w=windows[i];d=w['data']['fit'];m=w['result']['modes']
        def predict(p,d):return p[0]+2*np.pi*p[1]*d['t']+d['s']/2*(model['dd']+2*np.pi*model['rate']*(w['midpoint']+d['t']-model['ref']))
        initial=[m[0]['train']['phase_rad']+(model['dd']+2*np.pi*model['rate']*(w['midpoint']-model['ref']))/2,np.mean([x['frequency_hz'] for x in m])]
        solution=least_squares(lambda p:residual(predict(p,d),d['z'],w['weight'] if weighted else 1.),initial,max_nfev=200)
        d=w['data']['evaluation'];errors.extend(np.angle(d['z']*np.exp(-1j*predict(solution.x,d))))
    return dict(model=model,held_frame_count=len(errors),held_rms_deg=float(np.degrees(np.sqrt(np.mean(np.square(errors))))))
