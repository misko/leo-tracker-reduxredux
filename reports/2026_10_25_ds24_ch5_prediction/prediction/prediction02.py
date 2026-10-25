"""CH5-discovery-conditioned consistency, fixed radio parent and source IDs."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import signal
import sys
import time
import traceback

import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp, roots_legendre

OWN=Path(__file__).resolve().parent
HERE=OWN/'run02'
ROOT=OWN.parent
OLD=Path('/srv/bulk/leo/research/ds24-rx2-witness-r01/scientific')
sys.path.insert(0,str(OLD))
import witness02 as w
sr,k,r=w.sr,w.k,w.r
ARMS=w.ARMS
NORAD=57450
ORDER=('owner1','owner0','owner2')  # D, W_CH3, W_CH4; not outcome-selected.
CAP=600.
PRIOR_WORKER_SECONDS=7.320185383781791


def write(name,value):r.write_new(HERE/name,value)


def npz(name,**arrays):
    path=HERE/name;path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:np.savez_compressed(stream,**arrays)


def context(arm):
    d=r.context(w.CASE)
    x=np.asarray(r.read(OLD/'owner1/metadata.json')['common_position_east_north_km'])
    d=w.at_common_position(d,x)
    pool=r.read(OLD/'owner1/c0_screen.json')['candidate_indices']
    keep=d['keep'].copy()
    for row,sl in zip(d['base'].rows,d['base'].slices,strict=True):
        if row['candidate_index'] in pool:keep[sl]=False
    entries=[e for e in d['entries'] if e['candidate_index'] not in pool]
    saved=r.read(OLD/'owner1'/(arm+'_cavity.json'))
    if not w.hard_parent(saved):raise ValueError('original CH5 cavity prerequisite failed')
    arms=dict(d['arms']);arms[arm]=dict(arms[arm],phase_reference=np.asarray(saved['phase_reference']))
    d=dict(d,keep=keep,entries=entries,original_protected=set(d['original_protected'])-set(pool),arms=arms)
    owners=[r.read(OLD/name/'metadata.json') for name in ORDER]
    allids=[oid for e in owners for oid in e['observation_ids']]
    if len(allids)!=124 or len(set(allids))!=124:raise ValueError('complete disjoint D57/W24/W43 required')
    comp=w.background(d,arm,x,owners)
    times=np.concatenate([d['scan'].tracks[e['track_index']]['times'] for e in owners])
    model=w.owner_context(d,owners[0]);model['target_track']=dict(times=times,rf_hz=11.5e9)
    cd=k.candidate(model,NORAD)
    if not np.array_equal(cd['target_sky']['time_s'],cd['target_mode_bank']['time_s']):raise ValueError('physical bank grids differ')
    # Fixed parent/calibration is recreated at the exact archived reference.
    # No W value updates phase, parent coefficients, Gamma, or physical priors.
    original=r.read(OLD/'owner1'/(arm+'_cavity.json'))
    actual_curved=[oid for i,sl in zip(d['base'].members,d['base'].slices,strict=True)
        for oid,use in zip(d['scan'].tracks[i]['observation_ids'],keep[sl],strict=True) if use]
    if set(actual_curved)!=set(original['calibration_ids']):raise ValueError('discovery cavity curved IDs changed')
    if [oid for e in entries for oid in e['observation_ids']]!=original['predictive_ids']:raise ValueError('discovery cavity predictive IDs changed')
    return cd,x,owners,comp,saved


def setup(cd,x,base,indices,physical_count,model):
    ix=np.asarray(indices,int)
    times=np.asarray(cd['target_track']['times'])[ix]
    dd=dict(cd,target_track=dict(times=times,rf_hz=11.5e9))
    raw=np.asarray(base['raw'])[ix].copy()
    covariance=np.asarray(base['covariance'])[np.ix_(ix,ix)].copy()
    groups=np.zeros(len(ix),int)
    if physical_count<len(ix):groups[physical_count:]=1
    q=np.asarray(base['q'])[ix].copy();native_q=q.copy()
    polynomial=np.zeros((len(ix),5))
    if model=='mixed':
        wt=times[physical_count:]
        z=2*(wt-wt.min())/np.ptp(wt)-1
        polynomial[physical_count:]=np.polynomial.legendre.legvander(z,4)*k.PERIOD/np.sqrt(6)
        covariance+=polynomial@polynomial.T
        q[physical_count:]=0.  # structural absence of W physical curve, not native RF.
    root=np.linalg.cholesky(covariance)
    aliases,shifts=k.alias_vectors(groups,np.arange(-4,5))
    observer=sr.geodetic_to_ecef_km(*k.latlon(x),0.)
    # Native unseen Gamma(2,2) contributes the original 2sigma^2 diagonal.
    ids=[oid for owner in base['owners'] for oid in owner['observation_ids']]
    meta=cd['scan'].fixed_window_noise
    sigma=np.array([meta['per_observation_noise_sigma_hz'][ids[i]] if meta['extra_parameter_BIC_gain']>0
        else cd['scan'].radio_sigma_hz for i in ix])
    minimum=float(sigma.min()*np.sqrt(2))
    if np.linalg.eigvalsh(covariance).min()<minimum**2*(1-1e-8):raise ValueError('noise lower bound failed')
    return dict(d=dd,x=x,raw=raw,covariance=covariance,q=q,native_q=native_q,groups=groups,
        root=root,base_logdet=float(2*np.log(np.diag(root)).sum()),noise_minimum_sd=minimum,
        aliases=aliases,shifts=shifts,whitened_aliases=solve_triangular(root,shifts.T,lower=True).T,
        observer=observer,polynomial_columns=polynomial,physical_count=physical_count,model=model)


def supports(cd,comp):
    times=np.asarray(comp['d']['target_track']['times'])
    up=sr.ecef_to_enu_matrix(*k.latlon(comp['x']))[2]
    all_support=sr.sg.support(cd['target_sky'],times,up,comp['observer'])
    if comp['model']=='mixed':
        support=sr.sg.support(cd['target_sky'],times[:comp['physical_count']],up,comp['observer'])
        # Include W bank knots too: derivative-bound pieces remain conservative
        # even though W's physical q is structurally zero.
        support['interpolation_breakpoints']=np.asarray(sorted(set(support['interpolation_breakpoints'])|set(all_support['interpolation_breakpoints'])))
        return support
    return all_support


def evidence(cd,comp,name,deadline,stop_below=None):
    name=str(name)
    sr.alarm(deadline-time.monotonic())
    support=supports(cd,comp)
    write(name+'_support.json',support)
    row,fun,inner,brackets=sr.score_candidate(comp['d'],comp,support,stop_below)
    write(name+'_primary_checkpoint.json',row)
    sr.alarm(deadline-time.monotonic())
    reference,root_reference=sr.sm.reference(fun,inner),sr.sm.reference(fun,brackets)
    error=abs(reference['objective']-row['objective']) if reference['objective'] is not None and row['objective'] is not None else 0.
    row.update(reference=reference,root_reference=root_reference,primary_reference_error=float(error))
    row['numerically_qualified'] &= bool(reference['success'] and root_reference['success'] and error<=sr.sm.TOL)
    row.update(model=comp['model'],native_q_sha256=sr.previous.digest(comp['native_q']),
        physical_q_mask=comp['q']!=0,phase_shared=True,source_constant_SD_Hz=300.,alias_hypotheses=comp['aliases'])
    write(name+'_evidence.json',row)
    return row


def evidence_interval(row):
    if row.get('status')=='zero_physical_evidence' and row.get('empty_support_certified') and row.get('certified_visibility'):
        return -np.inf,-np.inf
    lower=row.get('full_support_lower_log_integral');upper=row.get('full_support_upper_log_integral')
    if not row.get('certified_visibility') or lower is None or upper is None or not np.isfinite([lower,upper]).all() or lower>upper:
        return None
    return lower,upper


def compare(same,mixed,discovery):
    a,b,d=map(evidence_interval,(same,mixed,discovery))
    if a is None or b is None:return dict(proved=False,reason='joint bound unresolved')
    low,high=a[0]-b[1],a[1]-b[0]
    if np.isnan([low,high]).any():return dict(proved=False,reason='undefined joint odds')
    winner='same_family' if low>0 else 'unresolved_witness' if high<0 else None
    result=dict(proved=winner is not None,winner=winner,joint_log_evidence_odds_bounds=[float(low),float(high)],
        raw_conditional_same_minus_mixed_objective=same['objective']-mixed['objective'] if same.get('objective') is not None and mixed.get('objective') is not None else None,
        discovery_denominator_cancels=True,absolute_precision_implied=False,identity_acceptance=False)
    if d is not None and np.isfinite(d).all():
        result['same_conditional_log_evidence_bounds']=[float(a[0]-d[1]),float(a[1]-d[0])]
        result['mixed_conditional_log_evidence_bounds']=[float(b[0]-d[1]),float(b[1]-d[0])]
    if discovery.get('objective') is not None:
        result['same_raw_conditional_objective']=same['objective']-discovery['objective'] if same.get('objective') is not None else None
        result['mixed_raw_conditional_objective']=mixed['objective']-discovery['objective'] if mixed.get('objective') is not None else None
    return result


def diagnostic_rule(cd,base,order,deadline):
    """D-only posterior moments and alias-adjusted W moment prediction.

    Fixed GL rule; no W responses enter any posterior weight or prediction.
    Independent source constants remain in the parent-radio covariance.
    """
    sr.alarm(deadline-time.monotonic())
    n=57;raw=base['raw'][:n];cov=base['covariance'];q=base['q']
    dcomp=setup(cd,base['x'],base,np.arange(n),n,'discovery')
    support=supports(cd,dcomp)
    if not support['certified'] or support['root_brackets']:raise ValueError('diagnostic support not exact full certified pieces')
    pieces=sr.sg.panels(support['inner_visible_intervals'],np.asarray(support['interpolation_breakpoints']))
    z,weight=roots_legendre(order);pieces=np.asarray(pieces)
    half=np.diff(pieces,axis=1)[:,0]/2;center=pieces.mean(axis=1)
    nodes=(center[:,None]+half[:,None]*z).ravel();logweights=(np.log(half[:,None])+np.log(weight)[None]).ravel()
    prior=sr.law(cd)
    root=np.linalg.cholesky(cov[:n,:n])
    v=solve_triangular(root,cov[:n,n:],lower=True).T
    base_diag=np.diag(cov[n:,n:])-np.sum(v*v,axis=1)
    if not np.isfinite(base_diag).all() or np.any(base_diag<=0):raise ValueError('D-conditioned base predictive variance nonpositive')
    c=solve_triangular(root,np.ones(n)*300.,lower=True)
    alias=np.arange(-4,5)
    white_raw=solve_triangular(root,(raw[None]+alias[:,None]*k.PERIOD).T,lower=True).T
    fixed_prediction=white_raw@v.T
    total=-np.inf;mean=np.zeros(5);second=np.zeros((5,5));predmean=np.zeros(len(q)-n);predsecond=np.zeros_like(predmean)
    aliassum=np.zeros(9);node_mass=[];node_phase=[]
    for start in range(0,len(nodes),128):
        sr.alarm(deadline-time.monotonic())
        ph=nodes[start:start+128]
        geo=k.m.q.phase_geometry(cd,base['x'],ph)
        f=geo['frequency_hz']*q[None];b=geo['shape_columns_hz']*q[None,:,None]
        bd=b[:,:n];bw=b[:,n:]
        u=solve_triangular(root,bd.transpose(1,0,2).reshape(n,-1),lower=True).reshape(n,len(ph),3).transpose(1,0,2)
        white_f=solve_triangular(root,f[:,:n].T,lower=True).T
        gram=np.eye(3)[None]+np.einsum('nki,nkj->nij',u,u)
        inv=np.linalg.inv(gram)
        wr=white_raw[None]-white_f[:,None]
        rhs=np.einsum('nki,nak->nai',u,wr)
        zm=np.einsum('nij,naj->nai',inv,rhs)
        residual=wr-np.einsum('nki,nai->nak',u,zm)
        costs=np.sum(residual**2,axis=2)+np.sum(zm**2,axis=2)+2*np.log(np.diag(root)).sum()+np.linalg.slogdet(gram)[1][:,None]+n*np.log(2*np.pi)
        logs=-costs/2+prior['distribution'].logpdf(ph)[:,None]-np.log(prior['mass'])-np.log(9)+logweights[start:start+len(ph),None]
        chunk=float(logsumexp(logs));combined=float(np.logaddexp(total,chunk))
        old_factor=float(np.exp(total-combined));factor=float(np.exp(chunk-combined));wt=np.exp(logs-chunk)
        cm=np.einsum('k,nak->na',c,residual)  # source constant pull /300Hz.
        uc=np.einsum('nki,k->ni',u,c)
        constvar=1-c@c+np.einsum('ni,nij,nj->n',uc,inv,uc)
        if not np.isfinite(constvar).all() or np.any(constvar < -1e-8):raise ValueError('Dconstant posterior variance invalid')
        constshape=-np.einsum('nij,nj->ni',inv,uc)
        features=np.concatenate((np.broadcast_to(ph[:,None,None],(len(ph),9,1)),zm,cm[:,:,None]),axis=2)
        conditional_cov=np.zeros((len(ph),5,5));conditional_cov[:,1:4,1:4]=inv
        conditional_cov[:,4,4]=constvar;conditional_cov[:,1:4,4]=constshape;conditional_cov[:,4,1:4]=constshape
        chunkmean=np.einsum('na,nai->i',wt,features)
        chunksecond=np.einsum('na,nai,naj->ij',wt,features,features)+np.einsum('n,nij->ij',wt.sum(axis=1),conditional_cov)
        t=bw-np.einsum('wk,nki->nwi',v,u)
        pm=f[:,None,n:]+fixed_prediction[None]-np.einsum('nk,wk->nw',white_f,v)[:,None]+np.einsum('nwi,nai->naw',t,zm)
        pv=base_diag[None]+np.einsum('nwi,nij,nwj->nw',t,inv,t)
        if not np.isfinite(pv).all() or np.any(pv<=0):raise ValueError('conditional predictive variance invalid')
        predmean=old_factor*predmean+factor*np.einsum('na,naw->w',wt,pm)
        predsecond=old_factor*predsecond+factor*np.einsum('na,naw->w',wt,pm**2+pv[:,None])
        mean=old_factor*mean+factor*chunkmean;second=old_factor*second+factor*chunksecond
        aliassum=old_factor*aliassum+factor*wt.sum(axis=0)
        node_phase.append(ph.copy());node_mass.append(logsumexp(logs,axis=1))
        total=combined
    variance=np.maximum(np.diag(second)-mean**2,0.)
    posterior_cov=second-np.outer(mean,mean)
    phase=np.concatenate(node_phase);mass=np.exp(np.concatenate(node_mass)-total)
    sorting=np.argsort(phase);cdf=np.cumsum(mass[sorting])
    quantiles=np.interp([.025,.5,.975],cdf,phase[sorting])
    return dict(order=order,objective=float(-2*total),phase_mean_s=float(mean[0]),phase_SD_s=float(np.sqrt(variance[0])),
        phase_quantiles_s=quantiles,shape_mean=mean[1:4],shape_covariance=posterior_cov[1:4,1:4],
        Dconstant_mean_Hz=float(300*mean[4]),Dconstant_SD_Hz=float(300*np.sqrt(variance[4])),
        alias_values=alias,alias_probabilities=aliassum,alias_edge_probability=float(aliassum[0]+aliassum[-1]),
        latent_order=['phase_s','shape_z1','shape_z2','shape_z3','Dconstant_over300Hz'],latent_mean=mean,latent_covariance=posterior_cov,
        prediction_mean_Hz=predmean,prediction_SD_Hz=np.sqrt(np.maximum(predsecond-predmean**2,0.)),
        quadrature_nodes=phase,quadrature_posterior_mass=mass,
        posterior_phase_node_effective_mass=float(1/np.sum(mass**2)),
        W_responses_used=False,alias_adjusted_prediction=True,band_is_moment_SD_not_credible_interval=True)


def diagnostics(cd,base,arm,deadline,discovery):
    values={order:diagnostic_rule(cd,base,order,deadline) for order in (32,64)}
    a,b=values[32],values[64]
    checks=dict(objective=abs(a['objective']-b['objective'])<=1e-3,
        phase=abs(a['phase_mean_s']-b['phase_mean_s'])<=1e-4 and abs(a['phase_SD_s']-b['phase_SD_s'])<=1e-4,
        alias=np.max(abs(a['alias_probabilities']-b['alias_probabilities']))<=1e-6,
        shape=np.max(abs(a['shape_mean']-b['shape_mean']))<=1e-4 and np.max(abs(a['shape_covariance']-b['shape_covariance']))<=1e-4,
        constant=abs(a['Dconstant_mean_Hz']-b['Dconstant_mean_Hz'])<=.01 and abs(a['Dconstant_SD_Hz']-b['Dconstant_SD_Hz'])<=.01,
        prediction=np.max(abs(a['prediction_mean_Hz']-b['prediction_mean_Hz']))<=.1 and np.max(abs(a['prediction_SD_Hz']-b['prediction_SD_Hz']))<=.1,
        same_discovery_objective=abs(b['objective']-discovery['objective'])<=1e-3)
    for order,value in values.items():
        arrays={key:value.pop(key) for key in ('quadrature_nodes','quadrature_posterior_mass','prediction_mean_Hz','prediction_SD_Hz')}
        npz(Path(arm)/('Dposterior_GL'+str(order)+'.npz'),**arrays)
    result=dict(GL32=values[32],GL64=values[64],checks=checks,quadrature_stability_passed=all(checks.values()),
        analytic_moment_error_certified=False,calibrated_predictive_band=False,discovery_evidence_absolute_precision=discovery['numerically_qualified'],
        predictive_curve_W_response_free=True,source_constant_W_mean_zero=True,
        prediction_coordinate='radio-conditioned alias-adjusted CFO; raw observation has9uniformlytranslated bands',
        no_W_alias_selected_from_W_values=True)
    write(Path(arm)/'Dposterior.json',result)
    return result


def arm_job(arm,deadline):
    began=time.monotonic();pairs=[];discovery=None
    try:
        sr.alarm(deadline-time.monotonic());cd,x,owners,base,cavity=context(arm)
        base.update(owners=owners,x=x)
        npz(Path(arm)/'joint_background.npz',raw_hz=base['raw'],covariance_hz2=base['covariance'],native_q=base['q'],
            native_ids=np.asarray([oid for e in owners for oid in e['observation_ids']]),
            times_s=cd['target_track']['times'],parent_coefficients=base['parent_coefficients'],parent_noise=base['parent_noise'],common_position_east_north_km=x)
        write(Path(arm)/'parent.json',dict(cavity=cavity,original_accepted_IDs_changed=False,owner_order=ORDER,
            same_CH5_discovery_cavity_every_model=True,common_position_east_north_km=x))
        dcomp=setup(cd,x,base,np.arange(57),57,'discovery')
        with np.load(OLD/'owner1'/(arm+'_conditional.npz')) as original:
            errors=dict(raw=float(np.max(abs(dcomp['raw']-original['raw_hz']))),
                covariance=float(np.max(abs(dcomp['covariance']-original['covariance_hz2']))),
                parent_coefficient=float(np.max(abs(base['parent_coefficients']-original['parent_coefficients']))),
                parent_Gamma=float(np.max(abs(base['parent_noise']-original['parent_noise']))))
            if not np.allclose(dcomp['raw'],original['raw_hz'],atol=1e-7,rtol=0) or not np.allclose(dcomp['covariance'],original['covariance_hz2'],atol=1e-7,rtol=1e-12):
                raise ValueError('original CH5 D marginal changed: '+str(errors))
        discovery=evidence(cd,dcomp,Path(arm)/'D',deadline)
        old=next(q for q in r.read(OLD/'owner1'/(arm+'_result.json'))['candidates'] if q['norad']==NORAD)
        score_error=abs(discovery['objective']-old['objective'])
        write(Path(arm)/'D_replay.json',dict(array_errors=errors,objective_error=score_error,passed=score_error<=1e-3))
        if score_error>1e-3:raise ValueError('original CH5 evidence does not replay')
        diagnostics(cd,base,arm,deadline,discovery)
        for label,ix in [('CH3',np.r_[np.arange(57),np.arange(57,81)]),('CH4',np.r_[np.arange(57),np.arange(81,124)])]:
            sr.alarm(deadline-time.monotonic())
            same=setup(cd,x,base,ix,57,'same');mixed=setup(cd,x,base,ix,57,'mixed')
            if not np.array_equal(same['raw'][:57],mixed['raw'][:57]) or not np.array_equal(same['covariance'][:57],mixed['covariance'][:57]):
                raise ValueError('mixed polynomial changed D marginal or D-W background')
            npz(Path(arm)/(label+'_models.npz'),raw_hz=same['raw'],same_covariance_hz2=same['covariance'],
                mixed_covariance_hz2=mixed['covariance'],native_q=same['native_q'],same_physical_q=same['q'],mixed_physical_q=mixed['q'],
                aliases=same['aliases'],mixed_polynomial_columns_Hz=mixed['polynomial_columns'])
            b=evidence(cd,mixed,Path(arm)/(label+'_mixed'),deadline)
            threshold=b.get('full_support_lower_log_integral')
            a=evidence(cd,same,Path(arm)/(label+'_same'),deadline,threshold)
            result=dict(arm=arm,witness=label,status='complete',comparison=compare(a,b,discovery),
                same_evidence=a,mixed_evidence=b,Dphysical_identical_both_models=True,
                candidate=NORAD,alternative_identities_tested=False,operational_identity_assignment=False,position_fits=0,GPS_used=False)
            write(Path(arm)/(label+'_result.json'),result)
            pairs.append(dict(witness=label,status='complete',comparison=result['comparison']))
            print(arm,label,result['comparison'],flush=True)
    except Exception as exc:
        done={p['witness'] for p in pairs}
        for label in ('CH3','CH4'):
            if label not in done:
                failure=dict(arm=arm,witness=label,status='budget_or_context_failed',error=repr(exc),traceback=traceback.format_exc())
                write(Path(arm)/(label+'_failure.json'),failure);pairs.append(failure)
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    result=dict(arm=arm,pairs=pairs,scientific_worker_seconds=time.monotonic()-began,position_fits=0,GPS_used=False)
    write(Path(arm)/'execution.json',result);return result


def verify(approval=False):
    p=r.read(HERE/'protocol.json');digest=r.sha(HERE/'protocol.json')
    if digest!=r.read(HERE/'protocol_seal.json')['protocol_sha256']:raise ValueError('protocol changed')
    for path,h in p['source_input_hashes'].items():
        if r.sha(path)!=h:raise ValueError('bound source/input changed: '+path)
    if approval:
        receipt=r.read(ROOT/'audit/preflight02.json')
        if receipt.get('all_passed') is not True or receipt.get('protocol_sha256')!=digest:raise ValueError('matching independent preflight required')
    return p


def freeze():
    old=r.read(OLD/'protocol02.json');bindings=dict(old['source_input_hashes'])
    for path,h in r.read(OLD/'RF_seal.json')['files'].items():
        if r.sha(path)!=h:raise ValueError('old scientific artifact changed: '+path)
        bindings[path]=h
    for path in (Path(__file__),OWN/'test_prediction02.py',OWN/'PROTOCOL02.md',OWN/'test_receipt02.json',
        ROOT/'COORDINATOR_PLAN.md',OWN/'RF_seal.json',OWN/'execution.json',ROOT/'HARNESS_REPAIR_AUTHORIZATION.md',
        OLD/'RF_seal.json',OLD/'protocol02.json',OLD/'capsule.json',OLD.parent/'audit/CONDITIONAL_DESIGN.md'):
        bindings[str(path)]=r.sha(path)
    protocol=dict(arms=ARMS,discovery='DS24-0013 RX2 CH5/T001 complete57IDs',witnesses=['CH3/T002 complete24IDs','CH4/T000 complete43IDs'],
        candidate=NORAD,order=ORDER,source_input_hashes=bindings,ordinary_nomination_repeated=False,
        shared_parent='exact archived CH5c0top8 union cavity, saved arm phase refs/commonc0RFcoordinate, unchangedoriginalnoise/powers/priors',
        models=dict(same='D+W share57450 Studentphase/full3physicalmodes',mixed='Dphysical57450 unchanged; Windependentproperdegree4polyprior'),
        aliases='independentuniform−4..4 perwholeowner,81joint,9D; originalgraphgauge−2PERIOD retained',
        covariance='sharedparentradio D-W crosscov plusindependent300Hzownerconstants; unseenGamma noise2sigma² unchanged',
        supports='same:D∩W nominalLOS; mixed:Donly; originalconditionedStudentnormalization retained,no visiblemassrenormalization',
        ordering='disjointjointlogevidencebounds; sharedDmarginalcancels exactly; no product/sum of overlappingfolds',
        numerical='reuse immutable support/log/envelope code,max8192panels,no tolerancechange,1e-3absoluteprecisionseparate',
        model_evaluation_order='Dreplay,DONLYdiagnostics,CH3mixedthen same,CH4mixedthen same; existing lowerboundexclusionstop for same',
        discovery_replay_tolerances=dict(raw_Hz=1e-7,covariance_Hz2_atol=1e-7,covariance_rtol=1e-12,objective=1e-3),
        diagnostics='DONLYGL32/64 posteriorphase/aliases/shape/constantpulls,WmomentmeanSD; no Wresponseconditioning, no Waliasselection',
        diagnostic_stability=dict(objective=1e-3,phase_mean_SD_s=1e-4,alias_probability=1e-6,shape_moments_prior_units=1e-4,
            Dconstant_mean_SD_Hz=.01,prediction_mean_SD_Hz=.1),
        diagnostic_certified_moment_error=False,predictive_band_is_calibrated=False,
        budget=dict(total_worker_seconds=600,prior_harness_worker_seconds=PRIOR_WORKER_SECONDS,
            remaining_worker_seconds=CAP-PRIOR_WORKER_SECONDS,workers=2,BLAS_threads=1,
            each_worker_wall_seconds=(CAP-PRIOR_WORKER_SECONDS)/2,includes_preparation_and_fixed_replays=True),
        preserved_failed_protocol_sha256=r.sha(OWN/'protocol.json'),
        harness_revision='only name=str(name) at evidence output-port entry; distinct outputrun02, prior7.320185worker-s charged',
        retries=0,new_RF=0,position_fits=0,GPS_used=False,operational_identity_assignments=0,
        controls='all2witnesses×2arms retained; not a full alternative-identity challenge, independentvalidation or adoption policy')
    write('protocol.json',protocol);write('protocol_seal.json',dict(protocol_sha256=r.sha(HERE/'protocol.json')))
    print(r.sha(HERE/'protocol.json'),flush=True)


def run():
    verify(True)
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        if r.os.environ.get(name)!='1':raise ValueError('one numeric thread required')
    write('execution_started.json',dict(protocol_sha256=r.sha(HERE/'protocol.json'),cap_seconds=CAP))
    began=time.monotonic();deadline=began+(CAP-PRIOR_WORKER_SECONDS)/2;results=[]
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(arm_job,a,deadline):a for a in ARMS}
        for future in as_completed(futures):
            arm=futures[future]
            try:results.append(future.result())
            except Exception as exc:results.append(dict(arm=arm,scientific_worker_seconds=(CAP-PRIOR_WORKER_SECONDS)/2,
                pairs=[dict(witness=label,status='worker_failed',error=repr(exc)) for label in ('CH3','CH4')]))
    verify(True)
    write('execution.json',dict(arms=results,scientific_seconds=PRIOR_WORKER_SECONDS+sum(a['scientific_worker_seconds'] for a in results),
        prior_harness_worker_seconds=PRIOR_WORKER_SECONDS,this_run_worker_seconds=sum(a['scientific_worker_seconds'] for a in results),
        wall_seconds=time.monotonic()-began,cap_seconds=600,selected_witnesses=2,selected_arm_witness_contexts=4,
        all_selected_terminal=True,position_fits=0,GPS_used=False,operational_identity_assignments=0))
    files={str(p):r.sha(p) for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
    write('RF_seal.json',dict(protocol_sha256=r.sha(HERE/'protocol.json'),files=files,all_selected_terminal=True,position_fits=0,GPS_used=False))
    print('TERMINAL',r.read(HERE/'execution.json')['scientific_seconds'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('freeze','run'));args=parser.parse_args()
    freeze() if args.action=='freeze' else run()
