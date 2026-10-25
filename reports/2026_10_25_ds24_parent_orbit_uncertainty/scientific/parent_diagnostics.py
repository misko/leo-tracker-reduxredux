"""Fixed-state RF controls, with old-state covariance triage separated from VI."""
import copy
import numpy as np

import adapter as a
from ds23_position_information import marginal_position_information
from ds23_predictive_linear import linear_geometry
from ds23_frozen_precision import conditional_gaussian


def derivative(fun,x,h):
    return np.column_stack([(fun(x+d)-fun(x-d))/(2*h) for d in np.eye(2)*h])


def objective_probe(p,x):
    rows=[]
    for h in (.01,.02):
        pairs=[]
        for axis in range(2):
            delta=np.eye(2)[axis]*h
            pairs.append([float(p.calculate(x+sign*delta)['negative_twice_elbo']) for sign in (-1,1)])
        gradient=np.array([(right-left)/(2*h) for left,right in pairs])
        rows.append(dict(step_km=h,axis_minus_plus_objectives=pairs,gradient=gradient))
    discrepancy=float(np.linalg.norm(rows[0]['gradient']-rows[1]['gradient']))
    tolerance=max(1e-3,1e-3*float(np.linalg.norm(rows[0]['gradient'])))
    return dict(center=components(p,x),steps=rows,gradient=rows[0]['gradient'],
        gradient_step_discrepancy=discrepancy,gradient_tolerance=tolerance,
        gradient_qualified=discrepancy<=tolerance)


def components(p,x):
    full=p.calculate(x)
    c=p.curved_calculate(x) if p.linear_entries else full
    pieces={key:float(c[key]) for key in ('quadratic','logvolume','noise_gamma_cost',
        'prior_gamma_cost','normalization_constant','negative_twice_elbo')}
    reconstruction=sum(pieces[k] for k in ('quadratic','logvolume','noise_gamma_cost','prior_gamma_cost','normalization_constant'))
    predictive=float(full.get('linear_predictive_objective',0.))
    gate=a.conservative_result(p,x)
    return dict(curved=pieces,predictive_objective=predictive,total_objective=float(full['negative_twice_elbo']),
        decomposition_error=float(full['negative_twice_elbo']-reconstruction-predictive),
        optimization_residual_squared=float(p.residual(x)@p.residual(x)),
        minimum_elevation_deg=float(np.min(full['elevation'])),
        full_likelihood_conditional_RMS_hz=float(np.sqrt(np.mean(full['conditional_residual_hz'][p.keep]**2))),
        conservative_gate_conditional_RMS_hz=float(np.sqrt(np.mean(gate['conditional_residual_hz'][p.keep]**2))),
        final_log_precision_change=float(full['final_log_precision_change']),
        predictive_calibration_max_difference=float(np.max(abs(full['coefficient']-c['coefficient']))))


def design(d,p,x,coefficient=None):
    c=p.calculate(x)
    coef=c['coefficient'] if coefficient is None else coefficient
    def mean(z):
        geo=a.geometry(p,z)
        return (p.q*geo['intercept']+geo['features']@coef)[p.keep]
    j=derivative(mean,x,.01);check=derivative(mean,x,.02)
    u=c['features'][p.keep].copy();prior=c['coefficient_prior_precision'].copy()
    g=p.noise_groups[p.keep]
    weights=d['powers'][g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
    ncurved=len(u)
    if d['entries']:
        view,_,sigma,groups,_=linear_geometry(p,d['entries'])
        def emean(z):
            geo=a.geometry(view,z)
            return view.q*geo['intercept']+geo['features']@coef
        je=derivative(emean,x,.01);ce=derivative(emean,x,.02)
        he=a.geometry(view,x)['features']
        constants=300*np.eye(len(d['entries']))[groups]
        u=np.vstack((np.column_stack((u,np.zeros((len(u),len(d['entries']))))),np.column_stack((he,constants))))
        prior=np.r_[prior,np.ones(len(d['entries']))]
        j=np.vstack((j,je));check=np.vstack((check,ce));weights=np.r_[weights,1/(2*sigma**2)]
    relative=float(np.linalg.norm(j-check)/max(1e-30,np.linalg.norm(j)))
    info=marginal_position_information(j,u,weights,prior)
    return dict(j=j,u=u,weights=weights,prior=prior,information=info,ncurved=ncurved,
        mean_derivative_relative_error=relative,mean_derivative_qualified=relative<=1e-5)


def primary_information(d,old,new,x):
    base=design(d,old,x)
    b=a.extra_columns(new,x)[new.keep]
    if d['entries']:
        view,*_=linear_geometry(new,d['entries'])
        b=np.vstack((b,a.extra_columns(view,x)))
    u=np.column_stack((base['u'],b));prior=np.r_[base['prior'],np.ones(b.shape[1])]
    info=marginal_position_information(base['j'],u,base['weights'],prior)
    if not all(np.isfinite(m).all() and np.linalg.eigvalsh(m).min()>0 for m in (base['information'],info)):
        raise ValueError('finite positive-definite baseline and augmented information required')
    eigen,axes=np.linalg.eigh(base['information']);weak=axes[:,0]
    oldvar=float(weak@np.linalg.solve(base['information'],weak))
    newvar=float(weak@np.linalg.solve(info,weak))
    difference=(base['information']-info+base['information'].T-info.T)/2
    tolerance=1e-8*max(1.,float(np.linalg.norm(base['information'])))
    monotonic=bool(np.linalg.eigvalsh(difference).min()>=-tolerance and newvar>=oldvar*(1-1e-8))
    return dict(base=base,new_u=u,new_prior=prior,extra=b,information=info,weak=weak,
        old_weak_variance_km2=oldvar,new_weak_variance_km2=newvar,
        weak_variance_fractional_change=newvar/oldvar-1,PSD_information_loss=monotonic,
        information_loss_eigenvalues=np.linalg.eigvalsh(difference))


def dense_oracle(u,weights,prior,b):
    # A deterministic short row panel checks the full shared kernel without
    # allocating a scan-sized dense matrix. All rows still enter the real score.
    family_rows=[]
    for start in range(0,b.shape[1],3):
        nonzero=np.flatnonzero(np.any(b[:,start:start+3]!=0,axis=1))
        if len(nonzero):family_rows.extend([int(nonzero[0]),int(nonzero[-1])])
    take=np.unique(np.r_[np.arange(min(24,len(u))),np.arange(max(0,len(u)-24),len(u)),family_rows]).astype(int)
    u,w,b=u[take],weights[take],b[take]
    old=np.diag(1/w)+(u/prior)@u.T
    aug=np.column_stack((u,b));precision=np.r_[prior,np.ones(b.shape[1])]
    covariance=np.diag(1/w)+(aug/precision)@aug.T
    identity=float(np.max(abs(covariance-old-b@b.T)))
    raw=np.sin(np.arange(len(take)))*20
    root=np.linalg.cholesky(covariance)
    z=np.linalg.solve(root,raw)
    dense=float(z@z+2*np.log(np.diag(root)).sum()+len(raw)*np.log(2*np.pi))
    compressed=conditional_gaussian(raw,aug,np.sqrt(1/w),np.ones(len(w)),np.ones(len(w)),precision,1.)
    return dict(rows=take,kernel_identity_error=identity,dense_normalized_objective=dense,
        nuisance_normalized_objective=float(compressed['objective']),
        objective_error=float(compressed['objective']-dense),
        passed=bool(identity<=1e-5 and abs(compressed['objective']-dense)<=1e-6))


def equivalence(d,arm,x,reference,old,new):
    legacy=a.r.build(d,arm,reference);zero=a.build(d,arm,reference,'retained_uncertainty',0.)
    oc,lc,zc=old.calculate(x),legacy.calculate(x),zero.calculate(x)
    comparisons={}
    for name,other in (('unmodified_legacy',lc),('zero_extra_variance',zc)):
        comparisons[name]=dict(objective_error=float(other['negative_twice_elbo']-oc['negative_twice_elbo']),
            coefficient_max_error=float(np.max(abs(other['coefficient'][:len(oc['coefficient'])]-oc['coefficient']))),
            Gamma_max_error=float(np.max(abs(other['noise_precision']-oc['noise_precision']))),
            residual_max_error=float(np.max(abs(other['conditional_residual_hz']-oc['conditional_residual_hz']))),
            predictive_residual_max_error=float(np.max(abs(other.get('linear_raw_prediction_residual_hz',np.zeros(1))-
                oc.get('linear_raw_prediction_residual_hz',np.zeros(1))))))
    comparisons['zero_extra_feature_maximum']=float(np.max(abs(zc['features'][:,zero.extra_start:]),initial=0))
    # Predictive values may change the predictive score, never calibration.
    dd=dict(d);dd['scan']=copy.copy(d['scan']);dd['scan'].tracks=list(d['scan'].tracks)
    for e in d['entries']:
        i=e['track_index'];t=dict(dd['scan'].tracks[i]);t['values']=t['values']+1e4*np.cos(np.arange(len(t['values'])))
        dd['scan'].tracks[i]=t
    redacted=a.build(dd,arm,reference,'retained_uncertainty');rc=redacted.calculate(x);nc=new.calculate(x)
    redaction=dict(coefficient_error=float(np.max(abs(rc['coefficient']-nc['coefficient']))),
        Gamma_error=float(np.max(abs(rc['noise_precision']-nc['noise_precision']))),
        predictive_objective_change=float(rc.get('linear_predictive_objective',0)-nc.get('linear_predictive_objective',0)))
    snapshots={k:np.array(nc[k],copy=True) for k in ('coefficient','noise_precision','residual','conditional_residual_hz')}
    before=a.fingerprint(nc);curved_before=a.fingerprint(new.curved_calculate(x))
    saved=a.summarize(new,x,d['entries']);a.coverage(new,x,d['entries'],saved)
    after=a.fingerprint(new.calculate(x));curved_after=a.fingerprint(new.curved_calculate(x))
    invariant=before==after and curved_before==curved_after and all(np.array_equal(v,new.calculate(x)[k]) for k,v in snapshots.items())
    olds=a.summarize(old,x,d['entries']);zeros=a.summarize(zero,x,d['entries'])
    oldcov=a.coverage(old,x,d['entries'],olds);zerocov=a.coverage(zero,x,d['entries'],zeros)
    zero_coverage=oldcov['accepted_observation_ids']==zerocov['accepted_observation_ids']
    def decisions(saved):
        return [[(q['component'],q['compatible']) for q in saved['gates']['tracks']],
            [(q['component'],q['compatible']) for q in saved['linear_gates']]]
    old_gates=decisions(olds)==decisions(zeros)
    numeric=all(abs(v['objective_error'])<1e-6 and v['coefficient_max_error']<1e-7 and v['Gamma_max_error']<1e-8
        and v['residual_max_error']<1e-6 and v['predictive_residual_max_error']<1e-6
        for v in (comparisons['unmodified_legacy'],comparisons['zero_extra_variance']))
    old_columns_exact=bool(np.array_equal(oc['features'],nc['features'][:,:new.extra_start]))
    return dict(comparisons=comparisons,predictive_redaction=redaction,calculate_gate_extension_invariant=invariant,
        zero_extra_coverage_exact=zero_coverage,zero_extra_gates_exact=old_gates,
        old_columns_exact=old_columns_exact,
        all_passed=bool(numeric and invariant and zero_coverage and old_gates and old_columns_exact and comparisons['zero_extra_feature_maximum']==0
            and redaction['coefficient_error']==0 and redaction['Gamma_error']==0
            and (not d['entries'] or redaction['predictive_objective_change']!=0)))


def triage(cases):
    triggers=[]
    for row in cases:
        arms=row.get('arms',{})
        complete=row.get('status')=='complete' and set(arms)==set(a.r.ARMS)
        move=complete and all(v['numerically_qualified'] and v['movement_proxy_norm_km']>=.05 for v in arms.values())
        variance=complete and all(v['numerically_qualified'] and v['weak_variance_fractional_change']>=.05 for v in arms.values())
        if move or variance:triggers.append(dict(case=row['case'],both_arms_movement=bool(move),both_arms_variance=bool(variance)))
    return dict(proceed_all_four_cases=bool(triggers),triggers=triggers,
        rule='any case: BOTH arms movement>=.05km OR BOTH arms weak variance fractional increase>=.05')
