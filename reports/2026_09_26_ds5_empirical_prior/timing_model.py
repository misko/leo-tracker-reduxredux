"""Pure shared-timing integration accepting explicit normalized prior weights."""
import numpy as np
from scipy.special import logsumexp


def grid_summary(grid,lp):
    p=np.exp(lp-logsumexp(lp));c=np.cumsum(p)
    return {'mean_s':float(p@grid),'map_s':float(grid[np.argmax(p)]),
            'central_90_s':[float(grid[min(np.searchsorted(c,q),len(grid)-1)]) for q in (.05,.95)],
            'edge_mass':float(p[0]+p[-1]) if len(grid)>1 else 0.}


def evaluate(rows,total,delta,clock,clock_sigma,priors):
    """Conditional timing evidence; CFO profiled and observation independence assumed."""
    ix=np.rint((clock[:,None]+delta[None,:]-total[0])/(total[1]-total[0])).astype(int)
    if ix.min()<0 or ix.max()>=len(total):raise ValueError('prediction grid too small')
    groups={}
    for row in rows:groups.setdefault(row['satellite_id'],[]).append(row)
    cp=np.zeros(len(clock)) if clock_sigma is None else -.5*(clock/clock_sigma)**2
    cp-=logsumexp(cp);train_clock=cp.copy();joint_clock=cp.copy();factors={}
    for cid,rr in groups.items():
        lp=priors[cid]
        if len(lp)!=len(delta) or abs(logsumexp(lp))>1e-8:raise ValueError('normalized prior required')
        tr=lp+sum(r['train'][ix] for r in rr);z=logsumexp(tr,axis=1)
        train_clock+=z;joint_clock+=logsumexp(tr+sum(r['test'][ix] for r in rr),axis=1)
        factors[cid]=tr-z[:,None]
    clock_lp=train_clock-logsumexp(train_clock);tracks=[];mse=0.;weight=0.;boundary=[]
    for cid,rr in groups.items():
        joint_p=np.exp(clock_lp[:,None]+factors[cid]);boundary.append(float(joint_p[:,0].sum()+joint_p[:,-1].sum()))
        tp=np.bincount(ix.ravel(),weights=joint_p.ravel(),minlength=len(total))
        timing=grid_summary(total,np.log(np.maximum(tp,1e-300)))
        for r in rr:
            em=float(tp@r['test_mse']);mse+=r['weight_s']*em;weight+=r['weight_s']
            tracks.append({'track_id':r['track_id'],'satellite_id':cid,'timing':timing,
                'posterior_expected_test_rms_hz':float(np.sqrt(em))})
    n=sum(r['n_test'] for r in rows);score=float(logsumexp(joint_clock)-logsumexp(train_clock))
    return {'conditional_predictive_log_score':score,'negative_log_score_per_test_observation':-score/n,
            'training_log_integrated_profile_likelihood':float(logsumexp(train_clock)),
            'test_observations':n,'uncapped_posterior_expected_weighted_rms_hz':float(np.sqrt(mse/weight)),
            'max_satellite_boundary_mass':max(boundary),'clock':grid_summary(clock,clock_lp),'tracks':tracks}
