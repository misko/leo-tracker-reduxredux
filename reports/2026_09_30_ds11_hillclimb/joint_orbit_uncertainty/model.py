"""Finite source-shared revision mixture with joint physical-candidate identity."""
from pathlib import Path
import sys
import numpy as np
from scipy.special import gammaln,logsumexp
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tools'))
import ds7_fast_baseline_adapter as fast

MAGNITUDES=np.array([0.,.01,.03,.1,.3,1.])
BETA=np.r_[0.,np.column_stack((-MAGNITUDES[1:],MAGNITUDES[1:])).ravel()]
LOG_C=float(gammaln(2.5)-gammaln(2)-.5*np.log(4*np.pi)-np.log(100.))


def direction(delta,jac,times,mask,linear=False):
    d=delta-delta[:,mask].mean(axis=1)[:,None]
    j=jac-jac[:,mask].mean(axis=1)[:,None,:]
    if not linear:return d,j
    t=np.asarray(times)-np.mean(np.asarray(times)[mask]);trms=np.sqrt(np.mean(t[mask]**2))
    rms=np.sqrt(np.mean(d[:,mask]**2,axis=1));valid=rms>1e-6
    out=np.zeros_like(d);derivative=np.zeros_like(j)
    if np.any(valid):
        assert trms>0
        sign=np.where(d[:,mask]@t[mask]<0,-1.,1.)
        out[valid]=sign[valid,None]*rms[valid,None]*t[None,:]/trms
        drms=np.mean(d[valid][:,mask,None]*j[valid][:,mask,:],axis=1)/rms[valid,None]
        derivative[valid]=sign[valid,None,None]*t[None,:,None]*drms[:,None,:]/trms
    return out,derivative


class JointOrbit:
    def __init__(self,document,older,config,mapping,groups,singletons,variant,weights,geometry_factory=None):
        assert variant in ('zero','orbit','linear');self.variant=variant
        factory=geometry_factory or fast.Stationary
        self.model=factory(document,config);self.old_model=factory(older,config)
        new={t['track_id']:t for t in document['tracks']};old={t['track_id']:t for t in older['tracks']}
        assert set(new)==set(old)==set(mapping)
        self.beta=np.array([0.]) if variant=='zero' else BETA
        self.weights=np.array([1.]) if variant=='zero' else np.r_[weights[0],np.repeat(np.asarray(weights[1:])/2,2)]
        assert np.all(self.weights>0) and abs(self.weights.sum()-1)<1e-12
        units=[dict(track_ids=g['track_ids'],candidate_norad=g['candidate_norad']) for g in groups]
        units += [dict(track_ids=[s['track_id']],candidate_norad=s['candidate_norad']) for s in singletons]
        accounted=[t for u in units for t in u['track_ids']]
        assert len(accounted)==len(set(accounted)) and set(accounted)==set(new)
        self.units=[]
        for unit in units:
            numbers=unit['candidate_norad'];support=set.intersection(*(set(mapping[t]) for t in unit['track_ids']))
            assert set(numbers)==support
            members=[]
            for tid in unit['track_ids']:
                slots=[mapping[tid].index(n) for n in numbers]
                def subset(track):
                    result=dict(track)
                    for key in ('candidate_position_km','candidate_velocity_km_s','base','jac'):
                        if key in result:result[key]=np.asarray(result[key])[slots]
                    return result
                members.append((subset(new[tid]),subset(old[tid])))
            sizes={a['catalogue_size'] for a,b in members};assert len(sizes)==1
            self.units.append((members,len(numbers),sizes.pop()))

    def evaluate(self,x,gradient=True):
        x=np.asarray(x,dtype=float);total=0.;derivative=np.zeros(3)
        for members,count,catalogue_size in self.units:
            combined=np.zeros((count,len(self.beta)));combined_gradient=np.zeros((count,len(self.beta),3))
            for track,older in members:
                mask=track['mask'];base,visible=self.model.prediction(track,x)
                old=self.old_model.prediction(older,x)[0] if self.variant!='zero' else base
                jb=np.zeros((*base.shape,3));jo=np.zeros_like(jb)
                if gradient:
                    for axis,step in enumerate((1e-4,1e-4,1e-5)):
                        dx=np.eye(3)[axis]*step
                        jb[:,:,axis]=(self.model.prediction(track,x+dx)[0]-self.model.prediction(track,x-dx)[0])/(2*step)
                        if self.variant!='zero':jo[:,:,axis]=(self.old_model.prediction(older,x+dx)[0]-self.old_model.prediction(older,x-dx)[0])/(2*step)
                        else:jo[:,:,axis]=jb[:,:,axis]
                d,jd=direction(old-base,jo-jb,track['times_s'],mask,self.variant=='linear')
                prediction=base[:,None,:]+self.beta[None,:,None]*d[:,None,:]
                residual=track['y'][None,None,mask]-prediction[:,:,mask]
                flat=residual.reshape(-1,int(mask.sum()))
                offsets,audits=fast.fit_stationary_offsets(flat);assert all(a['converged'] for a in audits)
                centered=(flat-offsets[:,None]).reshape(residual.shape)
                score=(LOG_C-2.5*np.log1p((centered/100.)**2/4)).sum(axis=2)-.5*(offsets.reshape(count,-1)/1e6)**2
                combined+=np.where(visible[:,None],score,-np.inf)
                if gradient:
                    jp=jb[:,None,mask,:]+self.beta[None,:,None,None]*jd[:,None,mask,:]
                    combined_gradient+=np.sum((5*centered/(40000+centered**2))[:,:,:,None]*jp,axis=2)
            logits=combined+np.log(self.weights)[None,:];normal=logsumexp(logits);assert np.isfinite(normal)
            total+=float(normal-np.log(catalogue_size))
            if gradient:derivative+=np.sum(np.exp(logits-normal)[:,:,None]*combined_gradient,axis=(0,1))
        return dict(score=total,gradient=derivative)
