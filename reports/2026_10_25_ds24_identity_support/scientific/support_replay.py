"""Exact old12 observation/cavity replay; no draws, parent refits or geography."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import sys
import time
import traceback
import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp
from scipy.stats import t

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
OLD=Path('/srv/bulk/leo/research/ds24-nomination-information-r01/nomination')
sys.path.insert(0,str(OLD))
import experiment as previous
k=previous.k;r=k.m.r
from leo.sky.frames import geodetic_to_ecef_km,ecef_to_enu_matrix
import support_geometry as sg
import support_math as sm
import support_bounds as sb

CASES=('DS24-0010','DS24-0011')
ARMS=('c0','fitted_c')
PROTOCOL=HERE/'protocol.json'


def write(path,value):r.write_new(HERE/path,value)


def alarm(seconds):
    if seconds<=0:raise TimeoutError('frozen total scientific budget exhausted')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('frozen scientific deadline')))
    signal.setitimer(signal.ITIMER_REAL,seconds)


def verify(approval=False):
    protocol=r.read(PROTOCOL)
    if r.sha(PROTOCOL)!=r.read(HERE/'protocol_seal.json')['protocol_sha256']:raise ValueError('protocol changed')
    for path,h in protocol['source_input_hashes'].items():
        if r.sha(path)!=h:raise ValueError('bound source/input changed: '+path)
    if approval:
        receipt=r.read(ROOT/'audit/preflight.json')
        if receipt.get('all_passed') is not True or receipt.get('protocol_sha256')!=r.sha(PROTOCOL):raise ValueError('independent frozen preflight required')
        go=r.read(ROOT/'coordinator_go.json')
        if go.get('approved') is not True or go.get('protocol_sha256')!=r.sha(PROTOCOL):raise ValueError('matching coordinator replay go required')
    return protocol


def law(d):
    target=d['target'];nu=float(target['phase_nu']);sd=float(target['phase_sd_s']);location=float(target['phase_mean_s'])
    if nu!=3 or sd<=0 or not np.isfinite([sd,location]).all():raise ValueError('original causal Student nu3 required')
    distribution=t(nu,loc=location,scale=sd/np.sqrt(3))
    return dict(distribution=distribution,sd=sd,location=location,nu=nu,
        mass=float(distribution.cdf(15)-distribution.cdf(-15)))


def saved_context(case,item):
    d=k.m.t.load_target(item['target']);context=r.read(OLD/case/'context.json')
    x=np.asarray(context['fixed_position_east_north_km']);times=np.asarray(d['target_track']['times'])
    # owner02 made the candidate bank reference-frequency11.5GHz; q is applied
    # once below. Do not reuse the original track's RF a second time.
    d=dict(d,target_track=dict(times=times,rf_hz=11.5e9))
    coordinates=k.latlon(x);observer=geodetic_to_ecef_km(*coordinates,0.)
    up=ecef_to_enu_matrix(*coordinates)[2]
    return d,x,times,observer,up


def components(d,x,observer,case,trial,arm):
    directory=OLD/case/f'trial{trial}'
    with np.load(directory/(arm+'_conditional.npz')) as saved:
        raw=saved['raw_hz'].copy();cov=saved['covariance_hz2'].copy()
        parent_coefficient=saved['parent_coefficients'].copy();parent_noise=saved['parent_noise'].copy()
    with np.load(directory/'observations.npz') as observations:
        q=observations['q'].copy();ids=observations['native_ids'].copy();values=observations['values_hz'].copy()
    if len(raw)!=len(ids) or np.any(q<=0) or not np.isfinite(q).all():raise ValueError('original complete observation/q contract invalid')
    if list(ids)!=d['target']['observation_ids']:raise ValueError('native observation IDs/order changed')
    meta=d['scan'].fixed_window_noise
    sigma=np.array([meta['per_observation_noise_sigma_hz'][oid] if meta['extra_parameter_BIC_gain']>0
        else d['scan'].radio_sigma_hz for oid in ids])
    minimum=float(np.min(sigma)*np.sqrt(2))
    if np.linalg.eigvalsh(cov).min()<minimum**2*(1-1e-8):raise ValueError('saved covariance lacks declared native-noise lower bound')
    root=np.linalg.cholesky(cov)
    aliases,shifts=k.alias_vectors(np.zeros(len(raw),int),np.arange(-4,5))
    return dict(d=d,x=x,observer=observer,q=q,groups=np.zeros(len(raw),int),raw=raw,covariance=cov,root=root,
        base_logdet=float(2*np.log(np.diag(root)).sum()),noise_minimum_sd=minimum,
        whitened_aliases=solve_triangular(root,shifts.T,lower=True).T,shifts=shifts,aliases=aliases,
        original_values_sha256=previous.digest(values),original_raw_sha256=previous.digest(raw),
        original_covariance_sha256=previous.digest(cov),original_parent_coefficient_sha256=previous.digest(parent_coefficient),
        original_parent_noise_sha256=previous.digest(parent_noise),native_ids_sha256=previous.digest(ids))


def geometry_fun(d,x):
    return lambda phases:k.m.q.phase_geometry(d,x,np.asarray(phases))


def density_fun(d,comp,prior):
    geometry=geometry_fun(d,comp['x'])
    def logdensity(phases):
        geo=geometry(phases)
        raw=comp['raw'][None]-geo['frequency_hz']*comp['q'][None]
        shape=geo['shape_columns_hz']*comp['q'][None,:,None]
        costs=sm.positive_costs(raw,comp['covariance'],shape,comp['shifts'])
        return logsumexp(-costs/2,axis=1)-np.log(len(comp['aliases']))+prior['distribution'].logpdf(phases)-np.log(prior['mass'])
    return logdensity


def score_candidate(d,comp,support,stop_below=None):
    prior=law(d);fun=density_fun(d,comp,prior)
    cuts=support['interpolation_breakpoints']
    inner_pieces=sg.panels(support['inner_visible_intervals'],cuts)
    bracket_pieces=sg.panels(support['root_brackets'],cuts)
    if len(inner_pieces)>sb.MAX_PANELS:raise ValueError('too many original interpolation panels for frozen cap')
    main=sm.log_integrate(fun,inner_pieces);brackets=sm.log_integrate(fun,bracket_pieces)
    threshold=stop_below-np.log(2) if stop_below is not None else None
    inner=sb.enclosure(d,comp,geometry_fun(d,comp['x']),prior,inner_pieces,threshold)
    roots=sb.enclosure(d,comp,geometry_fun(d,comp['x']),prior,bracket_pieces,threshold)
    lower=inner.get('lower_log_integral');upper=inner.get('upper_log_integral')
    if roots.get('upper_log_integral') is not None:upper=float(np.logaddexp(upper,roots['upper_log_integral'])) if upper is not None else roots['upper_log_integral']
    objective=main['objective']
    empty=not len(inner_pieces) and not len(bracket_pieces) and support['certified']
    error=max(abs(objective+2*lower),abs(objective+2*upper)) if objective is not None and lower is not None and upper is not None else None
    bound_qualified=bool(empty or support['certified'] and error is not None and error<=sm.TOL)
    distribution=prior['distribution']
    mass=lambda intervals:float(sum(distribution.cdf(b)-distribution.cdf(a) for a,b in intervals)/prior['mass'])
    root_mass=mass(support['root_brackets'])
    universal_root_log_bound=(np.log(root_mass)-.5*(comp['base_logdet']+len(comp['raw'])*np.log(2*np.pi))) if root_mass>0 else None
    result=dict(status='zero_physical_evidence' if empty else 'complete',objective=objective,
        empty_support_certified=empty,
        primary=main,bracket_quadrature=brackets,physical_enclosure=inner,root_enclosure=roots,
        full_support_lower_log_integral=lower,full_support_upper_log_integral=upper,
        objective_distance_to_full_enclosure=error,mode_and_support_qualified=bound_qualified,
        numerically_qualified=bool(empty or bound_qualified and main['success'] and brackets['success']),
        certified_visibility=support['certified'],inner_visible_prior_mass=mass(support['inner_visible_intervals']),
        root_bracket_prior_mass=root_mass,universal_root_log_density_bound=universal_root_log_bound,
        original_domain_prior_probability=prior['mass'],original_phase_location_s=prior['location'],original_phase_sd_s=prior['sd'],
        support_law_changed=bool(support['inner_visible_intervals']!=[[-15.,15.]] or support['root_brackets']),
        visible_mass_renormalized=False)
    return result,fun,inner_pieces,bracket_pieces


def certified_order(rows,null):
    # Null's closed-form Gaussian computation has its own tiny explicit
    # floating allowance, independently replayed before a proof is admitted.
    if not null['independent_dense_passed']:return dict(proved=False,reason='null reference failed')
    models=[dict(kind='unresolved',norad=None,lower=-.5*(null['objective']+1e-6),upper=-.5*(null['objective']-1e-6))]
    for row in rows:
        if row.get('status')=='zero_physical_evidence' and row.get('empty_support_certified') and row.get('certified_visibility'):
            models.append(dict(kind='physical',norad=row['norad'],lower=-np.inf,upper=-np.inf));continue
        lower=row.get('full_support_lower_log_integral');upper=row.get('full_support_upper_log_integral')
        if (not row.get('certified_visibility') or lower is None or upper is None
            or not np.isfinite([lower,upper]).all() or lower>upper):
            return dict(proved=False,reason='at least one physical support/evidence bound unresolved')
        models.append(dict(kind='physical',norad=row['norad'],lower=lower,upper=upper))
    for index,winner in enumerate(models):
        upper=max(q['upper'] for i,q in enumerate(models) if i!=index)
        if winner['lower']>upper:
            margin=winner['lower']-upper
            return dict(proved=True,winner_kind=winner['kind'],winner_norad=winner['norad'],
                minimum_log_evidence_margin=float(margin) if np.isfinite(margin) else None,
                infinite_margin=bool(np.isposinf(margin)),models_compared=len(models),
                absolute_score_precision_implied=False,operational_identity_assignment=False)
    return dict(proved=False,reason='evidence intervals overlap',models_compared=len(models))


def null_reference(comp):
    # Independently assemble the proper degree4/null covariance and evaluate
    # each finite alias with a symmetric eigensolve, unlike the old Cholesky.
    times=np.asarray(comp['d']['target_track']['times']);z=2*(times-times.min())/np.ptp(times)-1
    columns=np.polynomial.legendre.legvander(z,4)*k.PERIOD/np.sqrt(6)
    covariance=comp['covariance']+columns@columns.T
    values,vectors=np.linalg.eigh(covariance)
    if min(values)<=0:raise ValueError('null covariance nonpositive')
    raw=comp['raw'][None]+comp['shifts'];white=(raw@vectors)/np.sqrt(values)[None]
    loglike=-.5*(np.sum(white**2,axis=1)+np.log(values).sum()+len(times)*np.log(2*np.pi))
    return float(-2*(logsumexp(loglike)-np.log(len(loglike))))


def required_references(rows,null_objective,old_rows):
    finite=sorted([row for row in rows if row.get('objective') is not None],key=lambda q:(q['objective'],q['norad']))
    selected={row['norad'] for row in finite[:2]}
    selected|={row['norad'] for row in sorted([q for q in old_rows if q.get('status')=='complete'],key=lambda q:(q['reference_objective'],q['norad']))[:2]}
    best_upper=min((-2*q['full_support_lower_log_integral'] for q in rows if q.get('full_support_lower_log_integral') is not None),default=np.inf)
    for row in rows:
        if row['status']=='zero_physical_evidence':continue
        low=row.get('full_support_upper_log_integral');high=row.get('full_support_lower_log_integral')
        if low is None or high is None:selected.add(row['norad']);continue
        lower,upper=-2*low,-2*high
        if lower<=best_upper or lower<=null_objective<=upper:selected.add(row['norad'])
    return sorted(selected)


def case_job(case,item,deadline):
    began=time.monotonic();trial_rows=[];support_cache={};candidates={}
    try:
        alarm(deadline-time.monotonic());d,x,times,observer,up=saved_context(case,item)
        for trial in range(6):
            directory=OLD/case/f'trial{trial}';screen=r.read(directory/'screen.json')
            pool=screen['candidate_indices'];norads=screen['candidate_norads'];old_results={a:r.read(directory/(a+'_result.json')) for a in ARMS}
            if len(pool)!=8 or screen['forced_or_reserved_candidate']:raise ValueError('ordinary frozen shortlist changed')
            if [int(d['scan'].norads[j]) for j in pool]!=norads:raise ValueError('catalogue identities changed')
            dd=dict(d,original_protected=set(d['original_protected'])-set(pool))
            arm_rows={}
            for arm in ARMS:
                comp=components(dd,x,observer,case,trial,arm);rows=[];callbacks={}
                null=k.null_score(comp,np.arange(len(comp['raw'])))
                null['independent_dense_objective']=null_reference(comp)
                null['independent_dense_error']=abs(null['objective']-null['independent_dense_objective'])
                null['independent_dense_passed']=null['independent_dense_error']<=1e-7
                null['floating_objective_allowance']=1e-6
                exclusion_threshold=-.5*(null['objective']+1e-6) if null['independent_dense_passed'] else None
                for j,norad in zip(pool,norads,strict=True):
                    alarm(deadline-time.monotonic());started=time.monotonic()
                    try:
                        if norad not in candidates:
                            cd=k.candidate(dd,norad)
                            if not np.array_equal(cd['target_sky']['time_s'],cd['target_mode_bank']['time_s']):raise ValueError('nominal/mode grid mismatch')
                            candidates[norad]=cd
                            support_cache[norad]=sg.support(cd['target_sky'],times,up,observer)
                            write(Path(case)/f'support_{norad}.json',support_cache[norad])
                        cd=candidates[norad];row,fun,ip,bp=score_candidate(cd,comp,support_cache[norad],exclusion_threshold)
                        if row.get('full_support_lower_log_integral') is not None:
                            exclusion_threshold=max(exclusion_threshold,row['full_support_lower_log_integral']) if exclusion_threshold is not None else row['full_support_lower_log_integral']
                        row.update(norad=norad,candidate_index=j)
                        old=next(q for q in old_results[arm]['candidates'] if q['norad']==norad)
                        row['old_status']=old['status'];row['old_objective']=old.get('objective')
                        row['old_numerically_qualified']=old['numerically_qualified']
                        row['new_minus_old_objective']=row['objective']-old['objective'] if row['objective'] is not None and old.get('objective') is not None else None
                        row['change_category']='visibility-event-law plus numerics' if row['support_law_changed'] else 'numerics only; same physical support'
                        callbacks[norad]=(fun,ip,bp)
                    except TimeoutError:raise
                    except Exception as exc:row=dict(norad=norad,candidate_index=j,status='failed',numerically_qualified=False,error=repr(exc),traceback=traceback.format_exc())
                    row['seconds']=time.monotonic()-started;rows.append(row)
                    write(Path(case)/f'trial{trial}'/(arm+'_'+str(norad)+'_checkpoint.json'),row)
                selected=required_references(rows,null['objective'],old_results[arm]['candidates'])
                for row in rows:
                    if row['norad'] not in selected or row['norad'] not in callbacks:continue
                    alarm(deadline-time.monotonic());fun,ip,bp=callbacks[row['norad']]
                    reference=sm.reference(fun,ip);bracket_reference=sm.reference(fun,bp)
                    error=abs(reference['objective']-row['objective']) if row['objective'] is not None and reference['objective'] is not None else 0.
                    row.update(independent_reference=reference,independent_bracket_reference=bracket_reference,primary_reference_error=float(error))
                    row['numerically_qualified']&=bool(reference['success'] and bracket_reference['success'] and error<=sm.TOL)
                finite=sorted([q for q in rows if q.get('objective') is not None],key=lambda q:(q['objective'],q['norad']))
                winner=finite[0] if finite else None
                qualified=bool(null['independent_dense_passed'] and winner and winner['numerically_qualified'] and all(q['numerically_qualified'] for q in rows if q['norad'] in selected)
                    and all(q['status'] in ('complete','zero_physical_evidence') for q in rows))
                order=certified_order(rows,null)
                arm_result=dict(case=case,trial=trial,arm=arm,status='complete',candidates=rows,null=null,
                    required_reference_norads=selected,ranked_physical_norads=[q['norad'] for q in finite],
                    winner_norad=winner['norad'] if winner else None,physical_minus_null=winner['objective']-null['objective'] if winner else None,
                    ordering_numerically_qualified=qualified,old_ordering_numerically_qualified=old_results[arm]['ordering_numerically_qualified'],
                    evidence_order_certificate=order,
                    saved_input_hashes={key:value for key,value in comp.items() if key.endswith('_sha256')},
                    null_old_objective_difference=float(null['objective']-old_results[arm]['null']['objective']),
                    conditional_background_relearned=False,ordinary_shortlist_replaced=False,identity_qualified=False)
                write(Path(case)/f'trial{trial}'/(arm+'_result.json'),arm_result)
                arm_rows[arm]=dict(status='complete',ordering_numerically_qualified=qualified)
            trial_rows.append(dict(case=case,trial=trial,status='complete',arms=arm_rows))
            print(case,'trial',trial,arm_rows,flush=True)
    except Exception as exc:
        completed={q['trial'] for q in trial_rows}
        for trial in range(6):
            if trial not in completed:trial_rows.append(dict(case=case,trial=trial,status='budget_or_context_failed',error=repr(exc),traceback=traceback.format_exc()))
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    result=dict(case=case,trials=sorted(trial_rows,key=lambda q:q['trial']),scientific_worker_seconds=time.monotonic()-began,
        position_fits=0,new_observations=0,GPS_used=False)
    write(Path(case)/'execution.json',result);return result


def run():
    protocol=verify(approval=True)
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        if r.os.environ.get(key)!='1':raise ValueError('one numeric thread required')
    began=time.monotonic();deadline=began+(600-protocol['preparation_scientific_seconds'])/2
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(case_job,case,protocol['layouts'][case],deadline):case for case in CASES}
        results=[]
        for future in as_completed(futures):
            try:results.append(future.result())
            except Exception as exc:results.append(dict(case=futures[future],worker_failed=repr(exc),scientific_worker_seconds=deadline-began,
                trials=[dict(case=futures[future],trial=i,status='worker_failed',error=repr(exc)) for i in range(6)]))
    verify(approval=True)
    seconds=sum(q['scientific_worker_seconds'] for q in results)+protocol['preparation_scientific_seconds']
    write(Path('execution.json'),dict(cases=results,wall_seconds=time.monotonic()-began,
        total_scientific_seconds=seconds,cap_seconds=600,protocol_sha256=r.sha(PROTOCOL),
        all_selected_terminal=True,selected_trials=12,selected_arm_rows=24,maximum_candidate_contexts=192,
        observations_regenerated=False,parent_relearned=False,position_fits=0,GPS_used=False,identity_qualified=False))
    files={str(p):r.sha(p) for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
    write(Path('RF_seal.json'),dict(protocol_sha256=r.sha(PROTOCOL),files=files,position_fits=0,GPS_used=False,identity_qualified=False))
    print('TERMINAL',seconds,flush=True)


if __name__=='__main__':run()
