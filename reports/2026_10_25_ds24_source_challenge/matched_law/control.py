"""Six matching-law c0 controls, matched-observation fitted-c sensitivities."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import hashlib
import json
from pathlib import Path
import signal
import sys
import time
import traceback

import numpy as np
from scipy.integrate import quad
from scipy.linalg import solve_triangular

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
PREVIOUS=HERE.parent.parent/'ds24-nomination-information-r01/nomination'
SUPPORT=HERE.parent.parent/'ds24-identity-support-r01/scientific'
sys.path.insert(0,str(PREVIOUS));sys.path.insert(0,str(SUPPORT))
import experiment as old
import support_replay as sr
import law_math as lm
k=old.k;r=k.m.r
CASES=('DS24-0010','DS24-0011');ARMS=('c0','fitted_c');SEED=2026102551;CAP=600.


def read(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def write(name,value):r.write_new(HERE/name,value)
def npz(name,**arrays):
    p=HERE/name;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as stream:np.savez_compressed(stream,**arrays)


def alarm(seconds):
    if seconds<=0:raise TimeoutError('600s cumulative worker budget exhausted')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('600s cumulative worker budget exhausted')))
    signal.setitimer(signal.ITIMER_REAL,seconds)


def ordinary_screen(observation,catalogue):
    if set(observation)!={'raw_hz','covariance_hz2'}:raise ValueError('screen must not receive truth/type/background changes')
    raw=observation['raw_hz'];cov=observation['covariance_hz2']
    result=k.coarse_phase_scores(raw,np.zeros(len(raw)),catalogue['frequency_hz'],catalogue['derivative_hz_per_s'],catalogue['phase_sd_s'],cov,np.zeros(len(raw),int))
    scores=np.where(catalogue['minimum_mean_elevation_deg']>=0,result['score'],np.inf)
    ranked=sorted((j for j in range(len(scores)) if np.isfinite(scores[j])),key=lambda j:(float(scores[j]),int(catalogue['norads'][j])))
    phase=np.asarray(catalogue['phase_means_s'])+np.asarray(catalogue['phase_sd_s'])*result['phase_z']
    return dict(candidate_indices=ranked[:8],candidate_norads=[int(catalogue['norads'][j]) for j in ranked[:8]],
        coarse_scores=[float(v) if np.isfinite(v) else None for v in scores],coarse_aliases=result['aliases'],
        coarse_absolute_phase_s=phase,coarse_phase_outside_exact_domain=abs(phase)>15,
        coarse_alias_outside_exact_domain=np.any(abs(np.asarray(result['aliases']).reshape(len(scores),-1))>4,axis=1),
        ranked_visible_indices=ranked,catalogue_count=len(scores),forced_or_reserved_candidate=False,
        screen_observation_sha256=digest(raw),screen_is_approximate_not_exact_law=True)


def item_for(case):
    return next(row for row in read(k.OLD/'inventory.json')['rows'] if row['case']==case)


def load_context(case):
    item=item_for(case);d=k.m.t.load_target(item['target'])
    saved=read(PREVIOUS/case/'context.json');x=np.asarray(saved['fixed_position_east_north_km'])
    d=old.inject(d,np.zeros(len(d['target_track']['times'])))
    d['arms']={a:dict(d['arms'][a],endpoint_east_north_km=x,
        phase_reference=np.asarray(saved['parent_states'][a]['phase_reference'])) for a in ARMS}
    entry=dict(k.records(item,d)[0],alias=0)
    backgrounds={a:k.owners.components(d,a,x,[entry]) for a in ARMS}
    with np.load(PREVIOUS/case/'context.npz') as archive:
        catalogue={key:archive[key].copy() for key in ['norads','frequency_hz','derivative_hz_per_s','phase_means_s','phase_sd_s','minimum_mean_elevation_deg','minimum_domain_endpoint_elevation_deg']}
        oldmean=archive['radio_mean_hz'];oldcov=archive['conditional_covariance_hz2']
        replay=dict(mean=float(np.max(abs(-backgrounds['c0']['raw']-oldmean))),
                    covariance=float(np.max(abs(backgrounds['c0']['covariance']-oldcov))))
    if max(replay.values())>1e-6:raise ValueError('fixed exogenous full-parent replay mismatch')
    if entry['observation_ids']!=item['target']['observation_ids']:raise ValueError('layout native IDs differ')
    times=np.asarray(d['target_track']['times'])
    score_d=dict(d,target_track=dict(times=times,rf_hz=11.5e9),original_protected=set())
    meta=d['scan'].fixed_window_noise
    sigma=np.asarray([meta['per_observation_noise_sigma_hz'][oid] if meta['extra_parameter_BIC_gain']>0 else d['scan'].radio_sigma_hz for oid in entry['observation_ids']])
    observer=sr.geodetic_to_ecef_km(*k.latlon(x),0.);up=sr.ecef_to_enu_matrix(*k.latlon(x))[2]
    return d,score_d,x,times,entry,backgrounds,catalogue,sigma,observer,up,replay


def support_for(d,j,times,observer,up):
    bank=dict(time_s=d['scan'].sky['time_s'],position_km=d['scan'].sky['position_km'][[j]],velocity_km_s=d['scan'].sky['velocity_km_s'][[j]])
    return sr.sg.support(bank,times,up,observer)


def prepare():
    began=time.monotonic();alarm(CAP)
    bindings={};prepared=[]
    for case in CASES:
        d,sd,x,times,entry,bg,cat,sigma,observer,up,replay=load_context(case)
        absent=set(read(PREVIOUS/case/'context.json')['original_parent_families'])
        eligible=old.eligible_generators(cat,absent)
        certificates={};full=[]
        for j in eligible:
            cert=support_for(sd,j,times,observer,up)
            certificates[str(int(cat['norads'][j]))]=cert
            if cert['certified'] and cert['inner_visible_intervals']==[[-15.,15.]] and not cert['root_brackets']:full.append(j)
        pair,metrics=lm.pair_choice(cat['frequency_hz'],cat['derivative_hz_per_s'],cat['phase_sd_s'],bg['c0']['covariance'],full,cat['norads'])
        indices=list(pair[3:]);means=[];derivatives=[];variances=[];modes=[];laws=[]
        for j in indices:
            cd=k.candidate(sd,int(cat['norads'][j]));law=sr.law(cd);mu=law['location']
            geom=k.m.q.phase_geometry(cd,x,np.asarray([mu]))
            means.append(geom['frequency_hz'][0]*bg['c0']['q'])
            modes.append(geom['shape_columns_hz'][0]*bg['c0']['q'][:,None])
            derivatives.append(cat['derivative_hz_per_s'][j])
            moment=quad(lambda p:p*law['distribution'].pdf(p),-15,15,epsabs=1e-9)[0]/law['mass']
            second=quad(lambda p:p*p*law['distribution'].pdf(p),-15,15,epsabs=1e-9)[0]/law['mass']
            variances.append(second-moment**2)
            laws.append(dict(norad=int(cat['norads'][j]),location=mu,original_marginal_SD=law['sd'],nu=law['nu'],domain_mass=law['mass'],conditioned_mean=moment,conditioned_variance=variances[-1]))
        nullmean,nullfactor,q,cc,floor=lm.near_null(times,means,derivatives,variances,modes,sigma)
        path=Path(case);arrays=dict(**cat,times_s=times,native_ids=np.asarray(entry['observation_ids']),native_sigma_Hz=sigma,q=bg['c0']['q'],position_east_north_km=x,
            null_mean_Hz=nullmean,null_factor_Hz=nullfactor,null_Q=q,null_coefficient_covariance=cc,pair_frequencies_Hz=np.asarray(means),pair_derivatives_Hz_s=np.asarray(derivatives),pair_modes_Hz=np.asarray(modes),pair_phase_variances=np.asarray(variances))
        for a in ARMS:
            arrays[a+'_radio_mean_Hz']=-bg[a]['raw'];arrays[a+'_covariance_Hz2']=bg[a]['covariance']
            arrays[a+'_parent_coefficient']=bg[a]['parent_coefficients'];arrays[a+'_parent_noise']=bg[a]['parent_noise']
        npz(path/'context.npz',**arrays)
        metadata=dict(case=case,pair_indices=indices,pair_norads=[int(cat['norads'][j]) for j in indices],pair_metric=pair[0],metric_candidates=len(metrics),full_visible_generators=full,
            all_generator_support=certificates,selected_phase_laws=laws,null_noise_floor_coefficient=floor,background_replay=replay,
            target_component=item_for(case)['target']['component'],complete_native_IDs=entry['observation_ids'],historically_response_selected_layout=True,
            causal_cutoff_utc_ns=d['scan'].receipt['cutoff_utc_ns'],no_synthetic_CFO_generated=True,
            background_fixed_before_every_hypothetical_label=True,context_sha256=sha(HERE/path/'context.npz'))
        write(path/'context.json',metadata);prepared.append(dict(case=case,context_sha256=metadata['context_sha256'],metadata_sha256=sha(HERE/path/'context.json')))
        for name in ['context.npz','context.json']:bindings[str(PREVIOUS/case/name)]=sha(PREVIOUS/case/name)
        for relative,h in read(r.SOURCE/case/'preparation_receipt.json')['files_sha256'].items():bindings[str(r.SOURCE/relative)]=h
        bindings[str(r.SOURCE/case/'preparation_receipt.json')]=sha(r.SOURCE/case/'preparation_receipt.json')
    signal.setitimer(signal.ITIMER_REAL,0)
    write('preparation.json',dict(rows=prepared,seconds=time.monotonic()-began,actual_context_smoke_passed=True,no_generated_vectors=True))
    for module in tuple(sys.modules.values()):
        value=getattr(module,'__file__',None)
        if not value:continue
        p=Path(value).resolve()
        if p.suffix=='.py' and p.is_file() and (p.is_relative_to(r.REPO) or p.is_relative_to(HERE.parent.parent)) and '.venv' not in p.parts:
            bindings[str(p)]=sha(p)
    for p in [Path(__file__),HERE/'law_math.py',HERE/'test_control.py',HERE/'PROTOCOL.md',HERE/'test_receipt.json',HERE/'preparation.json',k.OLD/'inventory.json']:
        bindings[str(p)]=sha(p)
    write('protocol.json',dict(files=bindings,cases=CASES,prepared=prepared,seed=SEED,physical_vectors=4,null_vectors=2,total_vectors=6,arms=ARMS,
        c0_only_matching_law=True,fitted_c_same_vector_off_law_sensitivity=True,approximate_original_screen_unchanged=True,
        exact_pool='c0ordinarytop8 botharms; missingtruth separate diagnostic only,never ordinarybackfill',
        source_type_or_truth_received_by_screen=False,physical_law='original conditioned Studentnu3/fullB(phi)/finiteuniform9aliases/zero invisible phases with fulloperational normalizer',
        null_law='properGaussian polynomialperturbation about fixed physicalpair midpoint,localaffine prior-designcovariance plus native-noise roughness floor',
        maximum_scientific_worker_seconds=CAP,preparation_seconds=read(HERE/'preparation.json')['seconds'],test_seconds=read(HERE/'test_receipt.json')['seconds'],workers=2,BLAS_threads=1,
        all12armtrialslots_retained=True,position_fits=0,GPS_used=False,operational_association_rule=None))
    print('PREPARED',sha(HERE/'protocol.json'),flush=True)


def verify(approval=False):
    protocol=read(HERE/'protocol.json')
    for p,h in protocol['files'].items():
        if sha(p)!=h:raise ValueError('frozen input/source changed: '+p)
    for row in protocol['prepared']:
        if sha(HERE/row['case']/'context.npz')!=row['context_sha256'] or sha(HERE/row['case']/'context.json')!=row['metadata_sha256']:raise ValueError('frozen context changed')
    if approval:
        receipt=read(ROOT/'audit/matched_law_preflight.json')
        if not receipt.get('all_passed') or receipt['protocol_sha256']!=sha(HERE/'protocol.json'):raise ValueError('independent preflight required')
    return protocol


def make_component(data,arm,values,x,observer):
    covariance=data[arm+'_covariance_Hz2'];root=np.linalg.cholesky(covariance)
    aliases,shifts=k.alias_vectors(np.zeros(len(values),int),lm.ALIASES)
    return dict(raw=values-data[arm+'_radio_mean_Hz'],covariance=covariance,q=data['q'],root=root,
        x=x,observer=observer,base_logdet=float(2*np.log(np.diag(root)).sum()),noise_minimum_sd=float(np.min(data['native_sigma_Hz'])*np.sqrt(2)),
        aliases=aliases,shifts=shifts,whitened_aliases=solve_triangular(root,shifts.T,lower=True).T)


def generate(sd,data,meta,trial):
    case=int(meta['case'][-4:]);truth=dict(kind='physical' if trial<2 else 'near_null',trial=trial)
    if trial<2:
        j=meta['pair_indices'][trial];cd=k.candidate(sd,int(data['norads'][j]));law=sr.law(cd)
        rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([SEED,case,trial]).spawn(4)[0]))
        u=float(rng.uniform());dist=law['distribution'];phase=float(dist.ppf(dist.cdf(-15)+u*law['mass']))
        geo=k.m.q.phase_geometry(cd,data['position_east_north_km'],np.asarray([phase]))
        if np.min(geo['elevation_deg'])<0:raise ValueError('certified generator draw invisible; no reroll')
        mean=geo['frequency_hz'][0]*data['q'];factor=geo['shape_columns_hz'][0]*data['q'][:,None]
        truth.update(norad=int(data['norads'][j]),candidate_index=j,phase_s=phase)
    else:
        mean=data['null_mean_Hz'];factor=data['null_factor_Hz'];truth.update(norad=None,candidate_index=None,phase_s=None)
    values,latents=lm.draw(data['c0_radio_mean_Hz'],data['c0_covariance_Hz2'],mean,factor,SEED,trial,case)
    truth.update(latents,physical_or_null_mean_Hz=mean,physical_or_null_factor_Hz=factor,c0_matching_law=True,fitted_c_off_law=True)
    return values,truth


def exact(cd,comp,deadline,stop_below):
    alarm(deadline-time.monotonic())
    if not np.array_equal(cd['target_sky']['time_s'],cd['target_mode_bank']['time_s']):raise ValueError('nominal/mode bank grids differ')
    up=sr.ecef_to_enu_matrix(*k.latlon(comp['x']))[2]
    support=sr.sg.support(cd['target_sky'],np.asarray(cd['target_track']['times']),up,comp['observer'])
    row,_,_,_=sr.score_candidate(cd,comp,support,stop_below)
    row['support']=support
    return row


def trial_score(sd,data,meta,trial,values,truth,screen,arm,deadline):
    began=time.monotonic();relative=Path(meta['case'])/f'trial{trial}'/arm;rows=[];oracle=None
    slots=[dict(norad=int(data['norads'][j]),candidate_index=int(j),status='unscored') for j in screen['candidate_indices']]
    result=dict(case=meta['case'],trial=trial,arm=arm,exact_matching_law=arm=='c0',fitted_sensitivity_off_law=arm!='c0',status='failed',candidates=rows,ordinary_candidate_slots=slots)
    try:
        alarm(deadline-time.monotonic());x=data['position_east_north_km'];observer=sr.geodetic_to_ecef_km(*k.latlon(x),0.)
        comp=make_component(data,arm,values,x,observer)
        objective,_=lm.gaussian_score(comp['raw'],comp['covariance'],data['null_mean_Hz'],data['null_factor_Hz'])
        reference=lm.gaussian_qr_score(comp['raw'],comp['covariance'],data['null_mean_Hz'],data['null_factor_Hz'])
        null=dict(objective=objective,independent_dense_passed=abs(objective-reference)<1e-6,reference_objective=reference)
        if not null['independent_dense_passed']:raise ValueError('normalized null Gaussian closure failed')
        write(relative/'null.json',null)
        result['null']=null;lower=-(objective+1e-6)/2
        for j in screen['candidate_indices']:
            alarm(deadline-time.monotonic());norad=int(data['norads'][j]);cd=k.candidate(sd,norad)
            row=exact(cd,comp,deadline,lower);row.update(norad=norad,candidate_index=int(j),ordinary_shortlist_member=True)
            write(relative/(str(norad)+'.json'),row);rows.append(row)
            next(s for s in slots if s['candidate_index']==j)['status']=row['status']
            if row.get('full_support_lower_log_integral') is not None:lower=max(lower,row['full_support_lower_log_integral'])
        result['ordinary_order']=sr.certified_order(rows,null)
        missing=truth['kind']=='physical' and truth['candidate_index'] not in screen['candidate_indices']
        result['generating_label_in_ordinary_shortlist']=None if truth['kind']!='physical' else not missing
        if missing:
            cd=k.candidate(sd,truth['norad']);oracle=exact(cd,comp,deadline,lower)
            oracle.update(norad=truth['norad'],candidate_index=truth['candidate_index'],ordinary_shortlist_member=False)
            write(relative/'label_available_only.json',oracle)
        result.update(status='complete',label_available_diagnostic=oracle,
            label_available_order=sr.certified_order(rows+([oracle] if oracle else []),null),
            ordinary_shortlist_unchanged=True,observation_sha256=digest(values),background_mean_sha256=digest(data[arm+'_radio_mean_Hz']),covariance_sha256=digest(comp['covariance']))
    except Exception as exc:result.update(error=repr(exc),traceback=traceback.format_exc())
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    result['seconds']=time.monotonic()-began
    write(relative/'result.json',result)
    return result


def case_job(case,seconds):
    began=time.monotonic();deadline=began+seconds;results=[];failure=None
    try:
        alarm(seconds);d,sd,x,times,entry,bg,cat,sigma,observer,up,replay=load_context(case)
        meta=read(HERE/case/'context.json')
        with np.load(HERE/case/'context.npz') as a:data={key:a[key] for key in a.files}
        for arm in ARMS:
            if not np.allclose(-bg[arm]['raw'],data[arm+'_radio_mean_Hz'],rtol=0,atol=1e-7) or not np.allclose(bg[arm]['covariance'],data[arm+'_covariance_Hz2'],rtol=1e-12,atol=1e-7):raise ValueError('fixed background not reproducible')
        trials=[]
        for trial in range(3):
            values,truth=generate(sd,data,meta,trial);relative=Path(case)/f'trial{trial}'
            npz(relative/'observations.npz',values_Hz=values,native_ids=data['native_ids'],times_s=times)
            write(relative/'truth.json',truth)
            screens={}
            for arm in ARMS:
                screens[arm]=ordinary_screen(dict(raw_hz=values-data[arm+'_radio_mean_Hz'],covariance_hz2=data[arm+'_covariance_Hz2']),cat)
                write(relative/(arm+'_ordinary_screen.json'),screens[arm])
            trials.append((values,truth,screens['c0']))
        for arm in ARMS:
            for trial,(values,truth,screen) in enumerate(trials):
                if time.monotonic()>=deadline:
                    result=dict(case=case,trial=trial,arm=arm,status='unavailable',error='fixed worker deadline before slot')
                    write(Path(case)/f'trial{trial}'/arm/'result.json',result);results.append(result);continue
                results.append(trial_score(sd,data,meta,trial,values,truth,screen,arm,deadline))
    except Exception as exc:failure=dict(error=repr(exc),traceback=traceback.format_exc())
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    present={(row['arm'],row['trial']) for row in results}
    for arm in ARMS:
        for trial in range(3):
            if (arm,trial) not in present:
                unavailable=dict(case=case,trial=trial,arm=arm,status='unavailable',error='case setup/generation failed; not scored',case_failure=failure)
                write(Path(case)/f'trial{trial}'/arm/'result.json',unavailable);results.append(unavailable)
    result=dict(case=case,results=results,failure=failure,seconds=time.monotonic()-began,all_selected_arm_trial_slots=6,position_fits=0,GPS_used=False)
    write(Path(case)/'execution.json',result)
    return result


def run():
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        if r.os.environ.get(name)!='1':raise ValueError('one numerical thread required')
    protocol=verify(True);spent=protocol['preparation_seconds']+protocol['test_seconds'];remaining=CAP-spent
    began=time.monotonic();results=[]
    write('execution_started.json',dict(protocol_sha256=sha(HERE/'protocol.json'),prior_processing_seconds=spent,remaining_worker_seconds=remaining))
    with ProcessPoolExecutor(max_workers=2) as pool:
        jobs={pool.submit(case_job,case,remaining/2):case for case in CASES}
        for future in as_completed(jobs):
            try:results.append(future.result())
            except Exception as exc:results.append(dict(case=jobs[future],error=repr(exc),seconds=remaining/2))
    verify(True)
    write('execution.json',dict(cases=results,worker_seconds=spent+sum(row['seconds'] for row in results),wall_seconds=time.monotonic()-began,cap_seconds=CAP,total_vectors=6,arm_trial_slots=12,position_fits=0,GPS_used=False))
    files={str(p):sha(p) for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.log'}
    write('RF_seal.json',dict(files=files,protocol_sha256=sha(HERE/'protocol.json'),position_fits=0))
    print('TERMINAL',read(HERE/'execution.json')['worker_seconds'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','run']);args=parser.parse_args()
    prepare() if args.stage=='prepare' else run()
