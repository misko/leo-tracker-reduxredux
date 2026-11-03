"""Can one changed position explain all tracks? Conditional, bounded diagnostic."""
import itertools
import json
import time
import numpy as np
from scipy.optimize import minimize
from search import ROOT,observations
from leo.contracts.regional_position import PositionOrbitBank,RegionalPrior
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import circular,coordinates


def main():
    begun=time.monotonic();a=np.load(ROOT/'baseline.npz');b=np.load(ROOT/'orbit-bank.npz')
    ctx=json.loads((ROOT/'context.json').read_text());shape=json.loads((ROOT/'shape-controls.json').read_text())
    bank=PositionOrbitBank(b['numbers'],b['nodes'],b['positions'],b['velocities']);prior=RegionalPrior(**ctx['prior'])
    groups=[g for g in shape['groups'] if g['part']==0];v=np.array(ctx['vector']);look={int(n):i for i,n in enumerate(bank.numbers)}
    obs=[observations(a,ctx,np.array(g['rows'])) for g in groups]
    y=[a['measured'][g['rows']]-a['correction'][g['rows']] for g in groups]
    folds=[]
    for split in ['all','early_to_late','late_to_early']:
        train=[np.ones(len(o.times_s),bool) if split=='all' else
            (o.times_s<=np.median(o.times_s) if split=='early_to_late' else o.times_s>np.median(o.times_s)) for o in obs]
        choices=[g['arms']['published'][split][:2] for g in groups]
        trials=[]
        for seeds in itertools.product(*choices):
            if time.monotonic()-begun>90:raise TimeoutError('90 second geometry diagnostic bound')
            one=[bank.select([look[s['satellite']]]) for s in seeds]
            initial=np.r_[v[:2]/100.,[s['timing_s'] for s in seeds],[s['offset_hz']/10000. for s in seeds]]
            def objective(x):
                total=.5*np.sum((x[2:5]/2)**2);gradient=np.zeros(8);gradient[2:5]=x[2:5]/4
                for j,(o,yy,mask) in enumerate(zip(obs,y,train)):
                    pred,visible,spatial,timing=predict_orbits(one[j],o,prior,x[:2]*100,np.array([x[2+j]]),derivatives=True)
                    residual=circular(yy-pred[:,0]-x[5+j]*10000.)/125.
                    r=residual[mask];total+=.5*np.dot(r,r)
                    gradient[:2]+=-r@(spatial[mask,0,:]*100/125)
                    gradient[2+j]+=-r@(timing[mask,0]/125)
                    gradient[5+j]+=-r.sum()*10000/125
                return total,gradient
            constraint={'type':'ineq','fun':lambda x:(prior.radius_km/100)**2-np.dot(x[:2],x[:2]),
                'jac':lambda x:np.r_[-2*x[:2],np.zeros(6)]}
            fitted=minimize(objective,initial,jac=True,method='SLSQP',bounds=[(-2.5,2.5)]*2+[(-20,20)]*3+[(-11.36,11.36)]*3,
                constraints=[constraint],options={'maxiter':150,'ftol':1e-8})
            metrics=[];visible_all=True
            for j,(o,yy,mask) in enumerate(zip(obs,y,train)):
                pred,visible,_,_=predict_orbits(one[j],o,prior,fitted.x[:2]*100,np.array([fitted.x[2+j]]),derivatives=False)
                residual=circular(yy-pred[:,0]-fitted.x[5+j]*10000.);visible_all &= bool(visible[mask].all())
                metrics.append(dict(group=groups[j]['group'],satellite=seeds[j]['satellite'],timing_s=float(fitted.x[2+j]),
                    offset_hz=float(fitted.x[5+j]*10000.),training_count=int(mask.sum()),test_count=int((~mask).sum()),
                    training_rms_hz=float(np.sqrt(np.mean(residual[mask]**2))),
                    test_rms_hz=float(np.sqrt(np.mean(residual[~mask]**2))) if (~mask).any() else None))
            accepted=bool(fitted.success and constraint['fun'](fitted.x)>=-1e-6 and visible_all)
            lat,lon=coordinates(prior,fitted.x[:2]*100)
            trials.append(dict(success=bool(fitted.success),accepted=accepted,message=str(fitted.message),
                score=float(fitted.fun),latitude_deg=lat,longitude_deg=lon,
                displacement_from_saved_km=float(np.linalg.norm(fitted.x[:2]*100-v[:2])),groups=metrics))
        accepted=[trial for trial in trials if trial['accepted']]
        selected=min(accepted,key=lambda r:r['score']) if accepted else None
        folds.append(dict(split=split,selected=selected,trials=trials))
        print(json.dumps(dict(split=split,selected=selected)),flush=True)
        (ROOT/'geometry-control.json').write_text(json.dumps(dict(elapsed_s=time.monotonic()-begun,
            qualification='Conditional geometry sensitivity. Top two identities per trajectory and fold '
            'are selected from the corresponding training-only fixed-position shape search. A common '
            'site within the original 250 km disk, three timings and three free constant offsets are '
            'fitted using training observations only. Frozen receiver calibration and orbit-blind '
            'segment membership use the full scan. This is not the complete scan objective or '
            'independent position/identity validation. Eight candidate combinations per fold, one '
            'saved-site start, at most 150 SLSQP iterations per trial and 90 seconds total.',folds=folds),indent=2)+'\n')


if __name__=='__main__':main()
