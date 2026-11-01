"""Conditional physical-feature transfer across held receivers and families.

The position is estimated with the entire target family omitted. Phase
linearization uses causal prior means, never held-family fitted phases.
This is a local Gaussian model diagnostic, not a fresh position estimator.
"""
import argparse
import numpy as np
from reconsider import OUT,INPUT,ARMS,read,write,reconstruct,build,extend_history,apply_hypothesis
from ds23_height_problem import geometry_features

def gaussian_predict(y,X,train,test,sigma=150.,powers=None):
    weights=np.ones(len(y)) if powers is None else np.asarray(powers)
    u=X[train]*np.sqrt(weights[train,None])/sigma;v=y[train]*np.sqrt(weights[train])/sigma
    gram=np.eye(X.shape[1])+u.T@u
    root=np.linalg.cholesky(gram);coef=np.linalg.solve(root.T,np.linalg.solve(root,u.T@v))
    cov=np.linalg.solve(root.T,np.linalg.solve(root,np.eye(len(gram))))
    residual=y[test]-X[test]@coef;V=X[test]/sigma
    update=np.eye(len(gram))+np.linalg.solve(root,V.T)@np.linalg.solve(root,V.T).T
    rhs=V.T@(residual/sigma)
    correction=np.linalg.solve(gram+V.T@V,rhs)
    quadratic=float(residual@residual/sigma**2-rhs@correction)
    score=quadratic+np.linalg.slogdet(update)[1]+sum(test)*np.log(2*np.pi*sigma**2)
    return dict(score=float(score),rms_hz=float(np.sqrt(np.mean(residual**2))),residual_hz=residual,
        posterior_coefficient=coef,predictive_sigma_hz=np.sqrt(sigma**2+np.einsum('ij,jk,ik->i',X[test],cov,X[test])))

def run(case,selected=False,refresh=False):
    z=read(INPUT/(case+'.json'));d=reconstruct(z);out=OUT/case;trigger=read(out/'trigger.json');rows=[]
    targets=[(n,n) for n in trigger['selected']]
    if selected:
        result=read(out/'result.json')
        if result['selected'] is None:return
        rec=next(r for r in result['records'] if r['hypothesis']['name']==result['selected']);h=rec['hypothesis']
        d,_=extend_history(d,z,case,set(h['mapping'].values()),out/'transfer_history')
        d,_=apply_hypothesis(d,z,case,h,out);targets=[(rec['target'],h['norad'])]
    for source,n in targets:
        screen=read(out/str(source)/'screen.json')
        for a in ARMS:
            point=np.array(screen['cavity'][a]['x']);reference=np.clip(d['means'],-30,30)
            p,_=build(d,z,a,reference);c=p.calculate(point);begin=p.hardware.shape[1]+p.smooth.shape[1]
            mean=np.zeros(c['features'].shape[1]);mean[begin:begin+len(p.labels)]=d['means']/p.phase_sigma
            raw=p.values-p.q*c['intercept']-c['features']@mean
            target=np.zeros(len(raw),bool);rx=np.zeros(len(raw),int);ch=np.zeros(len(raw),int);labels=np.zeros(len(raw),int);keys=np.empty(len(raw),object)
            for r,i,sl in zip(p.rows,p.members,p.slices):
                tr=p.scan.tracks[i];target[sl]=r['candidate_norad']==n;rx[sl]=tr['receiver'];ch[sl]=tr['channel'];labels[sl]=r['candidate_norad'];keys[sl]=r['component']
            splits={'whole_family':p.keep&target}
            for receiver in sorted(set(rx[p.keep&target])):
                test=p.keep&target&(rx==receiver)
                if (p.keep&target&~test).sum()>=10:splits[f'held_RX{receiver}']=test
            for key in sorted(set(keys[p.keep&target])):
                test=p.keep&(keys==key)
                if (p.keep&target&~test).sum()>=10:splits['held_'+key]=test
            for model in ('full','receiver50','receiver0','orbit0','receiver0_orbit0'):
                scale=np.ones(c['features'].shape[1]);scale[-len(p.members):]=.3
                if model=='receiver50':scale[p.hardware.shape[1]:begin]=.25
                if model in ('receiver0','receiver0_orbit0'):scale[p.hardware.shape[1]:begin]=0
                if model in ('orbit0','receiver0_orbit0'):scale[begin+len(p.labels):begin+len(p.labels)+3*len(p.supported)]=0
                X=c['features']*scale
                for name,test in splits.items():
                    train=p.keep&~test
                    if sum(train)<20 or sum(test)<5:continue
                    if refresh:
                        p.reference=reference.copy();history=[]
                        try:
                            for step in range(20):
                                geom=geometry_features(p,point,0.);design=geom['features']*scale
                                values=p.values-p.q*geom['intercept']-geom['features']@mean
                                r=gaussian_predict(values,design,train,test,powers=d['powers'][p.noise_groups])
                                phase=(r['posterior_coefficient']*scale+mean)[begin:begin+len(p.labels)]*p.phase_sigma
                                change=float(max(abs(phase-p.reference)));history.append(change)
                                if change<=.01 or step==19:break
                                p.reference=.5*p.reference+.5*np.clip(phase,-30,30)
                            r.update(phase_change_s=change,phase_closed=change<=.01,phase_outside_window=bool(np.any(abs(phase)>30)),phase_iterations=len(history),phase=phase)
                        except ValueError as exc:
                            rows.append(dict(target=n,arm=a,model=model,split=name,status='failed',reason=str(exc)));continue
                    else:r=gaussian_predict(raw,X,train,test,powers=d['powers'][p.noise_groups])
                    r.pop('posterior_coefficient')
                    rows.append(dict(target=n,arm=a,model=model,split=name,train_points=int(sum(train)),held_points=int(sum(test)),
                        training_families=sorted(set(map(int,labels[train]))),held_times=p.flat_times[test],held_receiver=rx[test],held_channel=ch[test],held_component=keys[test],
                        position=point,phase_reference=reference,**r))
            print(case,n,a,'transfer complete',flush=True)
    filename='transfer'+('_selected' if selected else '')+('_refreshed' if refresh else '')+'.json'
    write(out/filename,dict(case=case,rows=rows,noise_hz=150,training_only_phase_refresh=refresh,
        scope='conditional local-Gaussian physical-feature check; fixed whole-family-omitted position and causal-mean phase linearization; graph/alias assignments inherited; no GPS',
        limits='not independent catalogue discovery or nonlinear phase validation; covariance is conditional on specified noise and frozen position; existing graph masks/aliases selected on full data'))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('case');parser.add_argument('--selected',action='store_true');parser.add_argument('--refresh',action='store_true');args=parser.parse_args();run(args.case,args.selected,args.refresh)
