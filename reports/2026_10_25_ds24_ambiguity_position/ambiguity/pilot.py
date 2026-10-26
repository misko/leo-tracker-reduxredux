"""Whole-owner identity mixtures at three fixed RF positions; no position fit."""
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

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
OLD=Path('/srv/bulk/leo/research/ds24-identity-components-r01/identity')
WITNESS=Path('/srv/bulk/leo/research/ds24-rx2-witness-r01/scientific')
INFORMATION=Path('/srv/bulk/leo/research/ds24-nomination-information-r01/information/results.json')
sys.path.insert(0,str(WITNESS))
import witness02 as w
sr,k,r=w.sr,w.k,w.r
CASES=('DS24-0011','DS24-0012');ARMS=('c0','fitted_c');PROBES=('center','minus','plus')
PHYSICAL_WEIGHTS=(.25,.5,.75);H=.1


def write(name,value):r.write_new(HERE/name,value)
def npz(name,**data):
    path=HERE/name;path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:np.savez_compressed(stream,**data)
def arrays(path):
    with np.load(path) as data:return {key:data[key].copy() for key in data.files}


def context(case):
    d=r.context(case);saved=r.read(OLD/(case+'_screen.json'));entry=saved['entries'][0]
    track=d['scan'].tracks[entry['track_index']]
    if track['key']!=entry['component'] or track['observation_ids']!=entry['observation_ids']:raise ValueError('complete owner changed')
    active={row['candidate_index'] for row,sl in zip(d['base'].rows,d['base'].slices,strict=True) if d['keep'][sl].any()}
    active|={row['candidate_index'] for row in d['entries']}
    if active&set(saved['candidate_indices']):raise ValueError('incumbent hypothesis requires shared-family hierarchy; block whole case, no fresh copy')
    coverage=r.read(Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/transfer/ownership')/case/'parent.json')['coverage']
    if any(set(entry['observation_ids'])&set(coverage[a]['accepted_observation_ids']) for a in ARMS):raise ValueError('target overlaps accepted IDs')
    d=w.owner_context(d,entry);d['original_protected']=set(d['original_protected'])-set(saved['candidate_indices'])
    parent=next(row for row in r.read(INFORMATION)['parents'] if row['case']==case and row['arm']=='c0')
    weak=np.asarray(parent['weak']);matrix=np.asarray(parent['information']);x=np.asarray(d['arms']['c0']['endpoint_east_north_km'])
    if abs(weak@weak-1)>1e-10 or np.linalg.eigvalsh(matrix).min()<=0:raise ValueError('archived information not positive/unit')
    return d,entry,saved,dict(common_x=x,weak=weak,information=matrix,weak_information=float(weak@matrix@weak),
        probes=dict(center=x,minus=x-H*weak,plus=x+H*weak),hard_norad=saved['nominee'])


def parent_component(d,entry,saved,arm,x):
    changed,info=k.cavity(w.at_common_position(d,x),saved['candidate_indices'],arm)
    if info['removed_curved_ids'] or info['removed_predictive_ids']:raise ValueError('common cavity unexpectedly removes data')
    if not w.hard_parent(info):raise ValueError('parent phase/Gamma/support prerequisite failed')
    comp=w.background(changed,arm,x,[entry])
    p=r.build(changed,arm,changed['arms'][arm]['phase_reference'])
    info['parent_negative_twice_ELBO']=float(p.calculate(x)['negative_twice_elbo'])
    info['coefficient_prior_hierarchy']='original parent VI/Gamma and joint old-predictive Gaussian conditional; no target update'
    return comp,info


def complete_component(d,base,x,entry):
    comp=dict(base,d=d,x=np.asarray(x));root=np.linalg.cholesky(comp['covariance'])
    aliases,shifts=k.alias_vectors(np.zeros(len(comp['raw']),int),np.arange(-4,5))
    meta=d['scan'].fixed_window_noise
    sigma=np.array([meta['per_observation_noise_sigma_hz'][oid] if meta['extra_parameter_BIC_gain']>0 else d['scan'].radio_sigma_hz for oid in entry['observation_ids']])
    comp.update(root=root,base_logdet=float(2*np.log(np.diag(root)).sum()),aliases=aliases,shifts=shifts,
        whitened_aliases=solve_triangular(root,shifts.T,lower=True).T,noise_minimum_sd=float(sigma.min()*np.sqrt(2)),
        observer=sr.geodetic_to_ecef_km(*k.latlon(x),0.))
    if np.linalg.eigvalsh(comp['covariance']).min()<comp['noise_minimum_sd']**2*(1-1e-8):raise ValueError('independent noise floor violated')
    return comp


def unknown(comp):
    # Fixed graph-frequency coordinates. No x/candidate-dependent recentering.
    times=np.asarray(comp['d']['target_track']['times'])
    primary=k.null_score(comp,np.arange(len(times)))
    reference=w.null_qr(comp['raw'],comp['covariance'],times,k.PERIOD)
    error=abs(primary['objective']-reference)
    return dict(kind='unknown',objective=primary['objective'],independent_QR_objective=reference,reference_error=error,
        reference_passed=error<=1e-7,lower_logZ=-.5*(primary['objective']+1e-6) if error<=1e-7 else None,
        upper_logZ=-.5*(primary['objective']-1e-6) if error<=1e-7 else None,
        curve_prior='zero graph-frequency mean; fixed degree4 Legendre(times), PERIOD/sqrt6 coefficients; x dependence only original radio mean/covariance')


def physical_bound(row):
    if row.get('empty_support_certified') and row.get('certified_visibility'):return (-np.inf,-np.inf)
    a,b=row.get('full_support_lower_log_integral'),row.get('full_support_upper_log_integral')
    if not row.get('certified_visibility') or a is None or b is None or not np.isfinite([a,b]).all() or a>b:return None
    return float(a),float(b)


def mixture(physical,null,weight):
    if len(physical)!=8 or any(row.get('objective') is None and not (row.get('empty_support_certified') and row.get('certified_visibility')) for row in physical):return dict(available=False)
    values=np.array([-.5*row['objective'] if row.get('objective') is not None else -np.inf for row in physical]+[-.5*null['objective']])
    prior=np.r_[np.full(8,weight/8),1-weight];point=float(logsumexp(values+np.log(prior)))
    bounds=[physical_bound(row) for row in physical]+[(null['lower_logZ'],null['upper_logZ']) if null['reference_passed'] else None]
    valid=all(pair is not None for pair in bounds)
    result=dict(available=True,physical_class_weight=weight,objective=-2*point,
        conditional_model_weights=np.exp(values+np.log(prior)-point),bounds_available=valid,
        weights_are_calibrated_identity_probabilities=False)
    if valid:
        lo=float(logsumexp([pair[0] for pair in bounds]+np.log(prior)));hi=float(logsumexp([pair[1] for pair in bounds]+np.log(prior)))
        result.update(lower_objective=-2*hi,upper_objective=-2*lo)
    return result


def secant_difference(minus,plus,hard_minus,hard_plus,information):
    point=(plus['objective']-hard_plus['objective']-minus['objective']+hard_minus['objective'])/(2*H)
    result=dict(delta_finite_difference_per_km=point,archived_c0_curvature_scaled_secant_proxy_km=-.5*point/information,
        true_derivative_claimed=False,achieved_displacement_claimed=False,bounds_available=False)
    if all(row.get('bounds_available') for row in [minus,plus,hard_minus,hard_plus]):
        low=((plus['lower_objective']-hard_plus['upper_objective'])-(minus['upper_objective']-hard_minus['lower_objective']))/(2*H)
        high=((plus['upper_objective']-hard_plus['lower_objective'])-(minus['lower_objective']-hard_minus['upper_objective']))/(2*H)
        proxy=[-.5*high/information,-.5*low/information]
        result.update(bounds_available=True,delta_finite_difference_interval=[low,high],proxy_interval_km=proxy,
            interval_supports_material_25m=bool(proxy[0]>=.025 or proxy[1]<=-.025))
    return result


def singleton(row):
    result=dict(objective=row['objective'],bounds_available=physical_bound(row) is not None)
    if result['bounds_available']:
        lo,hi=physical_bound(row);result.update(lower_objective=-2*hi,upper_objective=-2*lo)
    return result


def prepare():
    began=time.monotonic();sr.alarm(300.);cases=[]
    for case in CASES:
        d,entry,saved,meta=context(case);models=[]
        for norad in saved['candidate_norads']:
            cd=k.candidate(d,norad)
            if not np.array_equal(cd['target_sky']['time_s'],cd['target_mode_bank']['time_s']):raise ValueError('bank grids differ')
            models.append(dict(norad=norad,phase=cd['target']))
        for arm in ARMS:
            comp,info=parent_component(d,entry,saved,arm,meta['common_x'])
            complete_component(d,comp,meta['common_x'],entry)
            npz(Path('prepared')/case/(arm+'.npz'),raw=comp['raw'],covariance=comp['covariance'],q=comp['q'],
                parent_coefficients=comp['parent_coefficients'],parent_noise=comp['parent_noise'])
            write(Path('prepared')/case/(arm+'_parent.json'),info)
        write(Path('prepared')/case/'metadata.json',dict(meta,entry=entry,pool=saved['candidate_norads'],pool_indices=saved['candidate_indices'],models=models,
            target_times_s=d['scan'].tracks[entry['track_index']]['times'],all8_families_absent_from_parent_likelihood=True))
        cases.append(dict(case=case,passed=True,complete_native_IDs=len(entry['observation_ids']),candidate_count=8,common_probe_positions=meta['probes']))
    signal.setitimer(signal.ITIMER_REAL,0)
    write('load_smoke.json',dict(all_passed=True,cases=cases,scientific_seconds=time.monotonic()-began,target_density_evaluations=0,source_sha256=r.sha(__file__)))
    print('SMOKE',r.read(HERE/'load_smoke.json')['scientific_seconds'],flush=True)


def freeze():
    bindings={}
    for path,h in r.read(OLD/'protocol.json')['source_hashes'].items():
        if r.sha(path)!=h:raise ValueError('original source/input changed:'+path)
        bindings[path]=h
    for path in [Path(__file__),HERE/'preparation01/pilot.py',HERE/'test_pilot.py',HERE/'PROTOCOL.md',HERE/'test_receipt.json',HERE/'load_smoke.json',INFORMATION,ROOT/'COORDINATOR_PLAN.md']:
        bindings[str(path)]=r.sha(path)
    for path in sorted((HERE/'prepared').rglob('*')):
        if path.is_file():bindings[str(path)]=r.sha(path)
    for case in CASES:
        path=OLD/(case+'_screen.json');bindings[str(path)]=r.sha(path)
    for module in list(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and path.endswith('.py') and (path.startswith(str(r.REPO)) or path.startswith('/srv/bulk/leo/research/')):bindings[path]=r.sha(path)
    spent=r.read(HERE/'load_smoke.json')['scientific_seconds']+r.read(HERE/'test_receipt.json')['numeric_seconds']
    write('protocol.json',dict(source_input_hashes=bindings,cases=CASES,arms=ARMS,probes=PROBES,h_km=H,physical_models=8,
        physical_class_weights=PHYSICAL_WEIGHTS,conditional_physical_prior='uniform1/8',hard_physical='fixed archivednominees58175/57743',
        unknown='originalzero-meanproperdegree4Legendre in graph-observationcoordinates,PERIOD/sqrt6; no x/candidaterecenter',
        conditional_law='samefullparentVI/Gamma+jointoldpredictiveGaussianconditional perx/arm for all8+unknown; zeroparent removals; target-onlyphase/B independent becauseall8 absent',
        parent_refresh='exactly5 atcommonprobe fromsavedarmreference,phase<=15.000001/finalchange<=.01/Gamma<=1e-5; no targetnoiselearning',
        integral='originalcertifiedLOS support/no visiblemassrenorm; stablepositiveWoodbury+tanh-sinhlog; original8192analyticpanelcap; independentGL32/64all96',
        dominated_component_stop='stopanalyticrefinement when upperlogZ<bestvalidcomponentlower−log(8e6); retain finite fullbounds, no scoreprecisionwaiver',
        null_reference='originalCholesky+existingaugmentedQR error<=1e-7,objectiveallowance1e-6',
        physics='originalcausalStudentnu3conditioned[-15,+15]s,full3physicalmodes,9uniformaliases−4..4,source300Hzconstantonce',
        proxy='samearchivedc0parentI+weakaxisbotharms; −.5 Δsecant/(uIu); neitherderivative nor displacementbound',
        triage='atleastoneclassweight sensitivity proxyintervalsupportsabs>=.025kminBOTHarms; pointestimatesalone leads notqualification',
        scientific_cap_seconds=600,preparation_seconds=spent,remaining_seconds=600-spent,case_worker_seconds=(600-spent)/2,
        physical_contexts=96,unknown_contexts=12,workers=2,BLAS_threads=1,retries=0,position_fits=0,GPS_used=False,operational_adoption=False))
    print('FROZEN',r.sha(HERE/'protocol.json'),flush=True)


def verify(approval=False):
    protocol=r.read(HERE/'protocol.json')
    for path,h in protocol['source_input_hashes'].items():
        if r.sha(path)!=h:raise ValueError('bound source/input changed:'+path)
    if approval:
        receipt=r.read(ROOT/'audit/preflight.json')
        if receipt.get('all_passed') is not True or receipt.get('protocol_sha256')!=r.sha(HERE/'protocol.json'):raise ValueError('matching B preflight required')
    return protocol


def job(case,seconds):
    began=time.monotonic();deadline=began+seconds;outputs=[]
    try:
        sr.alarm(deadline-time.monotonic());d,entry,saved,meta=context(case)
        models={n:k.candidate(d,n) for n in saved['candidate_norads']}
        for probe in PROBES:
            x=np.asarray(meta['probes'][probe]);comps={};rows={a:[] for a in ARMS};nulls={}
            for arm in ARMS:
                sr.alarm(deadline-time.monotonic())
                if probe=='center':base=arrays(HERE/'prepared'/case/(arm+'.npz'));info=r.read(HERE/'prepared'/case/(arm+'_parent.json'))
                else:base,info=parent_component(d,entry,saved,arm,x)
                comps[arm]=complete_component(d,base,x,entry)
                write(Path(case)/probe/(arm+'_parent.json'),info)
                npz(Path(case)/probe/(arm+'_background.npz'),raw=comps[arm]['raw'],covariance=comps[arm]['covariance'],q=comps[arm]['q'],common_x=x)
                nulls[arm]=unknown(comps[arm]);write(Path(case)/probe/(arm+'_unknown.json'),nulls[arm])
            observer=comps['c0']['observer'];up=sr.ecef_to_enu_matrix(*k.latlon(x))[2]
            best_lower={arm:nulls[arm]['lower_logZ'] if nulls[arm]['reference_passed'] else None for arm in ARMS}
            for norad in saved['candidate_norads']:
                cd=models[norad];sr.alarm(deadline-time.monotonic())
                support=sr.sg.support(cd['target_sky'],cd['target_track']['times'],up,observer)
                write(Path(case)/probe/(str(norad)+'_support.json'),support)
                for arm in ARMS:
                    sr.alarm(deadline-time.monotonic());comp=dict(comps[arm],d=cd)
                    threshold=best_lower[arm]-np.log(8e6) if best_lower[arm] is not None else None
                    row,fun,inner,brackets=sr.score_candidate(cd,comp,support,threshold)
                    row.update(norad=norad,arm=arm,probe=probe,case=case)
                    bound=physical_bound(row)
                    if bound is not None and np.isfinite(bound[0]):best_lower[arm]=max(best_lower[arm],bound[0]) if best_lower[arm] is not None else bound[0]
                    write(Path(case)/probe/(arm+'_'+str(norad)+'_primary.json'),row)
                    reference=sr.sm.reference(fun,inner)
                    row['independent_GL32_64']=reference;row['primary_reference_objective_difference']=abs(row['objective']-reference['objective']) if row.get('objective') is not None and reference.get('objective') is not None else None
                    row['point_quadrature_stable']=bool(row.get('empty_support_certified') and row.get('certified_visibility') or reference['success'] and row['primary']['success'] and row['primary_reference_objective_difference'] is not None and row['primary_reference_objective_difference']<=1e-3)
                    write(Path(case)/probe/(arm+'_'+str(norad)+'.json'),row);rows[arm].append(row)
            for arm in ARMS:
                hard=next(row for row in rows[arm] if row['norad']==meta['hard_norad'])
                point=dict(case=case,probe=probe,arm=arm,hard=singleton(hard),unknown=nulls[arm],models=rows[arm],
                    mixture={str(p):mixture(rows[arm],nulls[arm],p) for p in PHYSICAL_WEIGHTS},
                    best_physical_point_norad=min(rows[arm],key=lambda row:row['objective'] if row.get('objective') is not None else np.inf)['norad'],
                    best_physical_point_objective=min((row['objective'] for row in rows[arm] if row.get('objective') is not None),default=None),
                    all_point_quadratures_stable=all(row['point_quadrature_stable'] for row in rows[arm]))
                write(Path(case)/probe/(arm+'_summary.json'),point);outputs.append(point)
            print(case,probe,'complete',flush=True)
        contrasts=[]
        for arm in ARMS:
            minus=next(row for row in outputs if row['arm']==arm and row['probe']=='minus');plus=next(row for row in outputs if row['arm']==arm and row['probe']=='plus')
            for p in PHYSICAL_WEIGHTS:
                contrast=secant_difference(minus['mixture'][str(p)],plus['mixture'][str(p)],minus['hard'],plus['hard'],meta['weak_information'])
                contrast.update(arm=arm,weight=p,all_point_quadratures_stable=minus['all_point_quadratures_stable'] and plus['all_point_quadratures_stable']);contrasts.append(contrast)
        result=dict(case=case,status='complete',contrasts=contrasts,scientific_seconds=time.monotonic()-began,
            target_currently_unaccepted=True,potential_added_factor_only=True,position_fits=0,GPS_used=False)
    except Exception as exc:
        result=dict(case=case,status='failed_or_budget_limited',error=repr(exc),traceback=traceback.format_exc(),scientific_seconds=time.monotonic()-began,
            complete_probe_arm_summaries=[dict(probe=row['probe'],arm=row['arm']) for row in outputs],position_fits=0,GPS_used=False)
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    write(Path(case)/'execution.json',result);return result


def run():
    protocol=verify(True)
    if any(r.os.environ.get(key)!='1' for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']):raise ValueError('BLAS1 required')
    write('execution_started.json',dict(protocol_sha256=r.sha(HERE/'protocol.json')));results=[]
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(job,case,protocol['case_worker_seconds']):case for case in CASES}
        for future in as_completed(futures):
            try:results.append(future.result())
            except Exception as exc:results.append(dict(case=futures[future],status='worker_failed',error=repr(exc),scientific_seconds=protocol['case_worker_seconds']))
    verify(True)
    slots=[]
    for case in CASES:
        pool=r.read(HERE/'prepared'/case/'metadata.json')['pool']
        for probe in PROBES:
            for arm in ARMS:
                for identity in pool+['unknown']:
                    path=HERE/case/probe/(arm+'_'+str(identity)+'.json')
                    slots.append(dict(case=case,probe=probe,arm=arm,identity=identity,status='complete' if path.exists() else 'failed_or_missing'))
    write('execution.json',dict(cases=results,all108_slots=slots,cumulative_scientific_seconds=protocol['preparation_seconds']+sum(row['scientific_seconds'] for row in results),
        cap_seconds=600,all_cases_terminal=True,position_fits=0,GPS_used=False,operational_adoption=False))
    files={str(path):r.sha(path) for path in sorted(HERE.rglob('*')) if path.is_file() and not set(path.parts)&{'__pycache__','.pytest_cache'}}
    write('RF_seal.json',dict(files=files,protocol_sha256=r.sha(HERE/'protocol.json'),all_cases_terminal=True))
    print('TERMINAL',r.read(HERE/'execution.json')['cumulative_scientific_seconds'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','freeze','run'));args=parser.parse_args();{'prepare':prepare,'freeze':freeze,'run':run}[args.action]()
