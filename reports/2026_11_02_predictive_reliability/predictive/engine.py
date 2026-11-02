"""Fixed-identity RF predictive reliability with train-only nuisance fitting."""
import hashlib
import importlib.util
from pathlib import Path
import time
import numpy as np
from scipy.optimize import minimize
from scipy.special import ndtr
from algo07_science import engine as e
from algo07_science.diagnose import objective
from phase_reference_checks import phase_refresh

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
OLD=REPO/'reports/2026_11_02_family_reliability'


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


family=module('reliability_fixed_family',OLD/'family/prototype.py')
box=module('reliability_box',OLD/'predictive/bounded/bounded.py')
adapter=module('reliability_training_preprocessing',ROOT.parent/'preprocessing/adapter.py')


def native(p):
    ids=np.asarray([o for i in p.members for o in p.scan.tracks[i]['observation_ids']])
    def flat(key):return np.concatenate([np.full(sl.stop-sl.start,p.scan.tracks[i][key])for i,sl in zip(p.members,p.slices)])
    families=np.concatenate([np.full(sl.stop-sl.start,r['candidate_norad'])for r,sl in zip(p.rows,p.slices)])
    assert len(ids)==len(set(ids))==len(p.keep)
    return dict(ids=ids,times=np.asarray(p.flat_times),family=families,receiver=flat('receiver'),channel=flat('channel'))


def span(t):return float(np.ptp(t))if len(t)>1 else 0.


def plans(p,target,seed,folds=3):
    """Geometry/identity inventory only; never inspect CFO or fit outcomes."""
    a=native(p);eligible=np.asarray(p.keep,bool);blocks=np.floor(a['times']/5).astype(int)
    available=np.unique(blocks[eligible]);hardware=2*(a['receiver']-1)+(a['channel']>4)
    rng=np.random.default_rng(seed);seen=set();out=[]
    def pack(name,train,test,**kw):
        return dict(name=name,train_ids=a['ids'][train],held_ids=a['ids'][test],training_points=int(train.sum()),held_points=int(test.sum()),**kw)
    for fold in range(folds):
        for retry in range(10000):
            held=np.sort(rng.choice(available,max(1,round(.2*len(available))),replace=False))
            if tuple(held)in seen:continue
            guard=np.unique(np.r_[held-1,held,held+1]);train=eligible&~np.isin(blocks,guard);test=eligible&np.isin(blocks,held)
            target_mask=a['family']==target
            supported=all(np.sum(train&(hardware==g))>=5 for g in np.unique(hardware[eligible]))
            if np.sum(train&target_mask)>=5 and np.sum(test&target_mask)>=2 and supported:break
        else:raise ValueError('No supported randomized synchronized time split')
        seen.add(tuple(held));out.append(pack(f'time_f{fold}',train,test,kind='time_group',fold=fold,seed=seed,
            eligible=True,held_blocks=held,guard_blocks=guard,retries=retry))
    for rx in sorted(np.unique(a['receiver'][eligible])):
        test=eligible&(a['family']==target)&(a['receiver']==rx);train=eligible&~test
        opposite=train&(a['family']==target)&(a['receiver']!=rx)
        other_support={}
        for band in sorted(np.unique((a['channel'][test]>4).astype(int))):
            in_range=(a['times']>=a['times'][test].min())&(a['times']<=a['times'][test].max())
            candidates=train&(a['receiver']==rx)&(a['family']!=target)&((a['channel']>4)==band)&in_range
            others=[]
            for n in np.unique(a['family'][candidates]):
                use=candidates&(a['family']==n)
                if use.sum()>=10 and span(a['times'][use])>=10:others.append(int(n))
            other_support[str(int(band))]=others
        overlap=max(0.,min(a['times'][test].max(),a['times'][opposite].max())-max(a['times'][test].min(),a['times'][opposite].min()))if test.any()and opposite.any()else 0.
        reasons=[]
        if test.sum()<20:reasons.append('fewer_than20_held_target_points')
        if opposite.sum()<20:reasons.append('fewer_than20_opposite_receiver_target_train_points')
        if overlap<10:reasons.append('target_receiver_time_overlap_below10s')
        if not other_support or any(len(v)<2 for v in other_support.values()):reasons.append('fewer_than2_same_band_overlapping_other_calibration_families')
        out.append(pack(f'family_to_rx{rx}',train,test,kind='family_receiver',held_receiver=int(rx),eligible=not reasons,
            ineligible_reasons=reasons,opposite_receiver_target_points=int(opposite.sum()),target_overlap_seconds=overlap,
            other_receiver_calibration_families_by_band=other_support))
    return out


def fit(d,z,arm,max_rounds=15,maxiter=25,maxfun=100):
    initial=adapter.initial_conditions(d);x=initial['start'];reference=initial['reference'];history=[]
    for epoch in range(max_rounds):
        p,dd=e.build(d,z,arm,reference)
        if list(p.supported)!=list(d['problems']['fitted_c'][0].supported):
            raise ValueError('Training mask changed frozen physical-mode support')
        opt=minimize(lambda at:objective(p,dd,at),x,method='L-BFGS-B',bounds=[(-12.5,12.5)]*2,
            options=dict(maxiter=maxiter,maxfun=maxfun,eps=.001,ftol=1e-10,gtol=1e-4,maxls=15))
        x=np.asarray(opt.x);c=p.calculate(x);actual=np.asarray(p.state(x)['phases'])[p.labels]
        clipped,check=phase_refresh(actual,reference,limit_s=30.)
        history.append(dict(epoch=epoch,x_km=x.copy(),reference=reference.copy(),posterior_phase=actual,
            objective=float(objective(p,dd,x)),optimizer_success=bool(opt.success),optimizer_message=str(opt.message),evaluations=int(opt.nfev),
            precision_iterations=int(c['precision_iterations']),precision_change=float(c['final_log_precision_change']),**check))
        if check['phase_change_s']<=.01:break
        if epoch<max_rounds-1:reference=reference+.5*(clipped-reference)
    return p,x,c,dict(history=history,phase_closed=check['phase_change_s']<=.01,phase_change_s=float(check['phase_change_s']),
        optimizer_success=bool(opt.success),boundary=bool(np.any(abs(x)>12.49)),reference=p.reference.copy())


def gaussian(raw,sigma,uncertainty):
    y=np.asarray(raw)/sigma;a=np.asarray(uncertainty)/sigma[:,None];g=np.eye(a.shape[1])+a.T@a
    root=np.linalg.cholesky(g);rhs=np.linalg.solve(root,a.T@y);quad=float(y@y-rhs@rhs)
    logdet=float(2*np.log(sigma).sum()+2*np.log(np.diag(root)).sum())
    return dict(negative_twice_log_density=quad+logdet+len(y)*np.log(2*np.pi),quadratic=quad,logdet_hz2=logdet,points=len(y))


def predictive_noise(noise_precision,groups,train):
    counts=np.bincount(groups[train],minlength=len(noise_precision));alpha=2.+counts/2.
    w=np.asarray(noise_precision,float);present=counts>0
    if np.any(w[present]<=0):raise ValueError('Nonpositive trained Gamma mean precision')
    inverse=np.full(len(w),2.);inverse[present]=alpha[present]/((alpha[present]-1)*w[present])
    return 150.*np.sqrt(inverse[groups]),dict(train_counts=counts,posterior_shape=alpha,mean_precision=w,
        inverse_precision_expectation=inverse,unseen_groups=np.flatnonzero(~present),
        approximation='Gaussian noise moment matches E[1/tau]; Gamma mixture/heavy tails are not integrated')


def residual_diagnostics(residual,times,groups):
    lag_a=[];lag_b=[];blockmeans=[]
    for g in np.unique(groups):
        use=np.flatnonzero(groups==g);use=use[np.argsort(times[use])]
        if len(use)>1:
            adjacent=np.diff(times[use])<=5.
            lag_a.extend(residual[use[:-1]][adjacent]);lag_b.extend(residual[use[1:]][adjacent])
    for b in np.unique(np.floor(times/5).astype(int)):
        use=np.floor(times/5).astype(int)==b;blockmeans.append(dict(block=int(b),points=int(use.sum()),mean_hz=float(residual[use].mean())))
    corr=float(np.corrcoef(lag_a,lag_b)[0,1])if len(lag_a)>2 and np.std(lag_a)>0 and np.std(lag_b)>0 else None
    return dict(rms_hz=float(np.sqrt(np.mean(residual**2))),mean_hz=float(residual.mean()),
        within_fragment_adjacent_lag_correlation=corr,adjacent_pairs=len(lag_a),maximum_adjacent_pair_gap_seconds=5.,five_second_block_means=blockmeans)


def evaluate(d,z,arm,scale,target,split,budget):
    began=time.monotonic();a=native(d['problems']['fitted_c'][0]);train=np.isin(a['ids'],split['train_ids']);test=np.isin(a['ids'],split['held_ids'])
    if np.any(train&test)or not train.any()or not test.any():raise ValueError('Disjoint nonempty native train/test required')
    dd=family.candidate_context(d,z,float(scale),family=int(target));dd,zz,receipt=adapter.prepare_context(dd,z,train)
    p,x,c,fitted=fit(dd,zz,arm,**budget);u=c['features'];g=p.noise_groups[train]
    weights=c['noise_precision'][g]/p.point_noise[train]**2
    prior=c['coefficient_prior_precision'];gram=np.diag(prior)+u[train].T@(u[train]*weights[:,None])
    root=np.linalg.cholesky(gram);inverse_root=np.linalg.solve(root,np.eye(len(prior)));cov=inverse_root.T@inverse_root
    nuisance=np.linalg.solve(root,u.T).T;mean=p.q*c['intercept']+u@c['coefficient']
    step=.02;hessian=np.zeros((2,2));gradient=[]
    # Include the same training-only horizon penalty used by position fitting.
    cost=lambda at:float(objective(p,dd,at))
    f0=cost(x)
    for k in range(2):
        delta=np.eye(2)[k]*step;cp=p.calculate(x+delta);cm=p.calculate(x-delta)
        gradient.append(((p.q*cp['intercept']+cp['features']@cp['coefficient'])-(p.q*cm['intercept']+cm['features']@cm['coefficient']))/(2*step))
        hessian[k,k]=(cost(x+delta)+cost(x-delta)-2*f0)/step**2
    d0=np.array([step,0]);d1=np.array([0,step])
    hessian[0,1]=hessian[1,0]=(cost(x+d0+d1)-cost(x+d0-d1)-cost(x-d0+d1)+cost(x-d0-d1))/(4*step**2)
    eigen,vectors=np.linalg.eigh(hessian/2);floor=1/(25**2/12);floored=np.maximum(eigen,floor)
    s=(vectors/floored)@vectors.T;j=np.column_stack(gradient);position=j@np.linalg.cholesky(s)
    probes=[]
    for axis in range(2):
        for sign in [-1,1]:
            at=x+sign*vectors[:,axis]/np.sqrt(floored[axis]);inside=bool(np.all(abs(at)<=12.5))
            change=cost(at)-f0 if inside else None
            probes.append(dict(axis=axis,sign=sign,position_km=at,inside_box=inside,
                training_negative_twice_objective_change=change,pass_probe=bool(inside and abs(change-1.)<=.5)))
    sigma,noise=predictive_noise(c['noise_precision'],p.noise_groups,train);raw=p.values-mean;scores={}
    for name,use in {'all':test,'target':test&(a['family']==target),'other':test&(a['family']!=target)}.items():
        if not use.any():scores[name]=dict(status='not_applicable',reason='No held observations in this subset');continue
        original=gaussian(raw[use],sigma[use],np.column_stack((nuisance[use],position[use])))
        corrected=box.correct_score(original['negative_twice_log_density'],raw[use],sigma[use],nuisance[use],j[use],x,s)
        scores[name]=dict(status='complete',unbounded=original,bounded=corrected,
            residual=residual_diagnostics(raw[use],a['times'][use],p.noise_groups[use]))
    inactive=np.flatnonzero(~np.any(abs(u[train])>1e-14,axis=0));posterior_fraction=prior*np.diag(cov)
    nb=p.hardware.shape[1];ns=p.smooth.shape[1];local=p.labels.index(next(v for v in p.labels if int(p.scan.norads[v])==target))
    phase=nb+ns+local;family_columns=[phase]
    target_index=p.labels[local]
    if target_index in p.supported:
        start=nb+ns+len(p.labels)+3*p.supported.index(target_index);family_columns+=list(range(start,start+3))
    sv=np.linalg.svd(u[train,:nb]/p.point_noise[train,None],compute_uv=False)
    tail=ndtr((-12.5-x)/np.sqrt(np.diag(s)))+ndtr((x-12.5)/np.sqrt(np.diag(s)))
    reasons=[]
    if not fitted['phase_closed']:reasons.append('phase_not_closed')
    if not fitted['optimizer_success']:reasons.append('position_optimizer_failed')
    if fitted['boundary']:reasons.append('position_at_regional_boundary')
    if np.any(eigen<=0):reasons.append('nonpositive_position_precision')
    if np.any(eigen!=floored):reasons.append('position_curvature_floored')
    if c['final_log_precision_change']>1e-5:reasons.append('inner_VI_precision_not_converged')
    if not all(probe['pass_probe']for probe in probes):reasons.append('local_gaussian_objective_probes_failed')
    if np.min(c['elevation'][train])<0:reasons.append('training_prediction_below_horizon')
    for name,score in scores.items():
        if score['status']!='complete':continue
        b=score['bounded']
        if score['unbounded']['quadratic']< -1e-8:reasons.append('negative_predictive_quadratic_'+name)
        if not np.isfinite(b['negative_twice_log_density']):reasons.append('nonfinite_bounded_density_'+name)
        if any(not np.isfinite(b[key]['relative_quadrature_error'])or b[key]['relative_quadrature_error']>1e-6 for key in ['prior_box','posterior_box']):reasons.append('box_quadrature_failed_'+name)
    return dict(arm=arm,SD_scale=float(scale),target_family=int(target),split=split['name'],kind=split['kind'],
        status='complete',seconds=time.monotonic()-began,x_km=x,position_covariance_km2=s,
        position_precision_eigenvalues=eigen,position_curvature_floored=bool(np.any(eigen!=floored)),
        gaussian_box_tail_probability_bounds=[float(max(tail)),float(min(1.,sum(tail)))],
        numerical_fit_qualified=not reasons,unqualified_reasons=reasons,preprocessing=receipt,noise=noise,
        final_inner_precision_change=float(c['final_log_precision_change']),scores=scores,**fitted,
        supported_candidate_indices=list(map(int,p.supported)),
        local_gaussian_probes=probes,
        identifiability=dict(prior_only_columns=inactive,hardware_training_singular_values=sv,
            hardware_posterior_prior_variance_ratio=posterior_fraction[:nb],
            target_phase_orbit_columns=family_columns,target_phase_orbit_posterior_prior_variance_ratio=posterior_fraction[family_columns],
            prior_only_held_variance_trace_hz2=float(np.sum(u[test][:,inactive]**2/prior[inactive]))if len(inactive)else 0.,
            nuisance_held_variance_trace_hz2=float(np.sum(nuisance[test]**2)),position_held_variance_trace_hz2=float(np.sum(position[test]**2))),
        held_ids_sha256=hashlib.sha256('\n'.join(a['ids'][test]).encode()).hexdigest(),
        train_ids_sha256=hashlib.sha256('\n'.join(a['ids'][train]).encode()).hexdigest(),
        limitations='Fixed graph nomination/mask/aliases/support; challenge-selected scans; local Gaussian/phase approximation; Gamma mixture and short-time residual dependence not integrated; ancillary families excluded')
