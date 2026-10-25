"""Ordinary causal nomination of all six frozen portions and whole-W control."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import sys
import time
import traceback
import numpy as np
from scipy.linalg import solve_triangular

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
OLD=Path('/srv/bulk/leo/research/ds24-rx2-witness-r01/scientific')
COHERENCE=Path('/srv/bulk/leo/research/ds24-source-coherence-r01/scientific')
PREDICTION=Path('/srv/bulk/leo/research/ds24-ch5-prediction-r01/prediction')
sys.path.insert(0,str(OLD))
import witness02 as w
sr,k,r=w.sr,w.k,w.r
ARMS=('c0','fitted_c')
CUTS=(14,21,29)


def write(name,value):r.write_new(HERE/name,value)
def npz(name,**arrays):
    path=HERE/name;path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:np.savez_compressed(stream,**arrays)
def arrays(path):
    with np.load(path) as source:return {key:source[key].copy() for key in source.files}


def selections():
    return [('whole_control',np.arange(43))]+[(f'cut{cut}_{side}',np.arange(cut) if side=='prefix' else np.arange(cut,43))
        for cut in CUTS for side in ('prefix','suffix')]


def eligibility(times,values):
    x=times-times.mean();y=values-values.mean()
    residual=y-x*(y@x)/max(x@x,1e-12)
    curvature=float(np.sqrt(np.mean(residual**2)));duration=float(np.ptp(times))
    return dict(duration_s=duration,linear_detrended_RMS_Hz=curvature,duration_at_least20s=duration>=20,
        curvature_at_least250Hz=curvature>=250,original_duration_and_curvature_eligible=duration>=20 and curvature>=250,
        original_whole_source_quality='structure_flagged',independent_new_owner_support_validated=False,
        fresh_original_residual_gates_tested=False,portion_adopted=False)


def select_catalogue(catalogue,use):
    return dict(norads=catalogue['norads'],frequency_hz=catalogue['frequency_hz'][:,use],
        derivative_hz_per_s=catalogue['derivative_hz_per_s'][:,use],phase_means_s=catalogue['phase_means_s'],
        phase_sd_s=catalogue['phase_sd_s'],minimum_mean_elevation_deg=catalogue['mean_elevation_deg'][:,use].min(axis=1))


def screen(raw,covariance,catalogue):
    """No privileged label parameter. Original screen and proposal arithmetic."""
    ordinary=sr.previous.ordinary_screen(dict(raw_hz=raw,covariance_hz2=covariance),catalogue)
    detail=k.coarse_phase_scores(raw,np.zeros(len(raw)),catalogue['frequency_hz'],catalogue['derivative_hz_per_s'],
        catalogue['phase_sd_s'],covariance,np.zeros(len(raw),int))
    phase=catalogue['phase_means_s']+catalogue['phase_sd_s']*detail['phase_z']
    root=np.linalg.cholesky(covariance)
    phase_feature=solve_triangular(root,(catalogue['derivative_hz_per_s']*catalogue['phase_sd_s'][:,None]).T,lower=True)
    sd=catalogue['phase_sd_s']/np.sqrt(1+np.sum(phase_feature**2,axis=0))
    ordinary.update(phase_z=detail['phase_z'],linear_phase_mean_s=phase,linear_phase_SD_s=sd,
        phase_mean_in_operational_domain=abs(phase)<=15,nearest_alias_in_finite_exact_support=np.all(abs(detail['aliases'])<=4,axis=1),
        affine_phase_not_exact_propagation=True,exact_identity_evidence=False,accepted=False)
    return ordinary


def prepare():
    began=time.monotonic();sr.alarm(170.)
    # This actual input smoke performs RF-blind geometry only; no CFO screen.
    cat=arrays(OLD/'owner2/catalogue.npz');obs=arrays(OLD/'owner2/observations.npz')
    d=r.context('DS24-0013');track=next(t for t in d['scan'].tracks if t['key']==r.read(OLD/'owner2/metadata.json')['component'])
    np.testing.assert_array_equal(obs['native_ids'],track['observation_ids'])
    np.testing.assert_array_equal(obs['values_hz'],track['values']);np.testing.assert_array_equal(obs['times_s'],track['times'])
    full={arm:arrays(COHERENCE/'run02'/arm/'inputs.npz') for arm in ARMS}
    x=full['c0']['common_position_east_north_km']
    np.testing.assert_array_equal(x,full['fitted_c']['common_position_east_north_km'])
    f,elevation=k.phase_frequency_grid(d['scan'].sky,obs['times_s'],*k.latlon(x),phase_seconds=d['all_means'])
    np.testing.assert_array_equal(cat['norads'],d['scan'].norads)
    np.testing.assert_array_equal(cat['phase_means_s'],d['all_means']);np.testing.assert_array_equal(cat['phase_sd_s'],d['widths'])
    np.testing.assert_array_equal(f*obs['q'][None],cat['frequency_hz'])
    np.testing.assert_array_equal(elevation.min(axis=1),cat['minimum_mean_elevation_deg'])
    if elevation.shape!=(1487,43) or not np.isfinite(elevation).all():raise ValueError('catalogue mean elevation shape/finite')
    cat['mean_elevation_deg']=elevation
    npz('inputs/catalogue.npz',**cat)
    native={row['observation_id']:row for row in d['observations']}
    native_values=np.array([native[oid]['measured_cfo_hz'] for oid in obs['native_ids']])
    np.testing.assert_allclose(native_values-obs['values_hz'],2*k.PERIOD,atol=1e-7,rtol=0)
    checks=[]
    for arm in ARMS:
        saved=full[arm];ix=np.arange(57,100)
        np.testing.assert_array_equal(saved['native_ids'][ix],obs['native_ids'])
        np.testing.assert_array_equal(saved['times_s'][ix],obs['times_s']);np.testing.assert_array_equal(saved['native_q'][ix],obs['q'])
        raw=saved['raw_hz'][ix];covariance=saved['covariance_hz2'][np.ix_(ix,ix)]
        with np.load(PREDICTION/'run02'/arm/'joint_background.npz') as original:
            old=np.arange(81,124)
            np.testing.assert_array_equal(raw,original['raw_hz'][old])
            np.testing.assert_array_equal(covariance,original['covariance_hz2'][np.ix_(old,old)])
        if raw.shape!=(43,) or covariance.shape!=(43,43) or np.linalg.eigvalsh(covariance).min()<=0:raise ValueError('proper background')
        npz(Path('inputs')/(arm+'.npz'),raw_hz=raw,covariance_hz2=covariance,radio_mean_hz=obs['values_hz']-raw,
            native_ids=obs['native_ids'],times_s=obs['times_s'],graph_values_hz=obs['values_hz'],native_values_hz=native_values,
            q=obs['q'],common_position_east_north_km=x)
        cavity=r.read(OLD/'owner1'/(arm+'_cavity.json'))
        meta=r.read(OLD/'owner1/metadata.json')['original_conditioning_trace']
        original_active=set(meta['original_active_curved_families'])|set(meta['original_active_predictive_families'])
        pool=set(r.read(OLD/'owner1/c0_screen.json')['candidate_indices'])
        write(Path('inputs')/(arm+'_context.json'),dict(original_CH5_cavity_path=str(OLD/'owner1'/(arm+'_cavity.json')),
            retained_parent_supported_families=cavity['retained_supported_families'],retained_parent_active_families=sorted(original_active-pool),
            parent_calibration_IDs=cavity['calibration_ids'],parent_predictive_IDs=cavity['predictive_ids'],
            original_parent_hard_guards_passed=w.hard_parent(cavity),shared_family_orbit_alternatives_not_symmetrized=True))
        checks.append(dict(arm=arm,passed=True,exact_native_IDs_values_q_background=True,mean_catalogue_entries=1487))
    ledger=[dict(name=name,indices=use,native_IDs=obs['native_ids'][use],
        original_eligibility=eligibility(obs['times_s'][use],obs['values_hz'][use])) for name,use in selections()]
    write('inputs/ledger.json',dict(original_CH4_IDs=obs['native_ids'],original_D_IDs=full['c0']['native_ids'][:57],
        all100_original_IDs_retained=True,all43_CH4_IDs_scored_in_every_cut_partition=True,contexts=ledger,
        historical_exposure='CH4 already graph-selected/structure-flagged/rejected; cuts exposed in previous coherence study; prior catalogue alternatives known, none forced'))
    write('load_smoke.json',dict(all_passed=True,checks=checks,scientific_seconds=time.monotonic()-began,
        ordinary_screens=0,position_fits=0,GPS_used=False,per_ID_mean_elevation_reconstructed=True,
        original_nominal_frequency_cache_exact=True,source_sha256=r.sha(__file__)))
    signal.setitimer(signal.ITIMER_REAL,0)
    print('LOAD_SMOKE',r.read(HERE/'load_smoke.json')['scientific_seconds'],flush=True)


def freeze():
    bindings={}
    for seal in [COHERENCE/'run02/RF_seal.json',OLD/'RF_seal.json']:
        for path,h in r.read(seal)['files'].items():
            if r.sha(path)!=h:raise ValueError('archived immutable file changed:'+path)
            bindings[path]=h
        bindings[str(seal)]=r.sha(seal)
    for path in [Path(__file__),HERE/'test_nominate.py',HERE/'PROTOCOL.md',HERE/'test_receipt.json',HERE/'load_smoke.json',ROOT/'COORDINATOR_PLAN.md']:
        bindings[str(path)]=r.sha(path)
    for path in sorted((HERE/'inputs').iterdir()):bindings[str(path)]=r.sha(path)
    for module in list(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file and file.endswith('.py') and (file.startswith(str(r.REPO)) or file.startswith('/srv/bulk/leo/research/')):bindings[file]=r.sha(file)
    prep=r.read(HERE/'load_smoke.json')['scientific_seconds']+r.read(HERE/'test_receipt.json')['numeric_seconds']
    write('protocol.json',dict(source_input_hashes=bindings,cuts=CUTS,portions=6,whole_controls=1,arms=ARMS,screen_contexts=14,
        catalogue_entries=1487,shortlist=8,forced_candidates=False,matched_common_position=True,original_CH5_discovery_cavity=True,
        screen='unchanged ordinary_screen/coarse_phase_scores, momentGaussian affinephase, nearest unrestricted whole-portion integeralias, portion-specific meanLOS',
        no_new_response_selected_cavity=True,existing_parent_candidates='ordinary hypotheses retained; no family-specific conditional covariance correction; proposal ranks only',
        phase_alias_flags='report absphase<=15 and aliasin[-4,4] without clipping or changing rank',
        overlays='nativeCFO=graphCFO+2PERIOD; affine f(mu)+fprime*SD*phase_z + fixed parent radio mean - nearestalias*PERIOD; zero new physical/ownerconstant posterior means',
        eligibility='original duration>=20s AND linear-detrendedRMS>=250Hz; no owner/gate waiver or acceptance',
        numeric_cap_seconds=180,preparation_numeric_seconds=prep,remaining_numeric_seconds=180-prep,worker_deadline_seconds=(180-prep)/2,
        workers=2,BLAS_threads=1,scientific_retries=0,position_fits=0,GPS_used=False,new_RF=0))
    print('FROZEN',r.sha(HERE/'protocol.json'),flush=True)


def verify(approval=False):
    protocol=r.read(HERE/'protocol.json');digest=r.sha(HERE/'protocol.json')
    for path,h in protocol['source_input_hashes'].items():
        if r.sha(path)!=h:raise ValueError('bound input/source changed:'+path)
    if approval:
        receipt=r.read(ROOT/'audit/preflight.json')
        if receipt.get('all_passed') is not True or receipt.get('protocol_sha256')!=digest:raise ValueError('independent matching preflight required')
    return protocol


def job(arm,seconds):
    began=time.monotonic();completed=[];deadline=began+seconds
    try:
        cat=arrays(HERE/'inputs/catalogue.npz');obs=arrays(HERE/'inputs'/(arm+'.npz'));context=r.read(HERE/'inputs'/(arm+'_context.json'))
        for name,use in selections():
            sr.alarm(deadline-time.monotonic())
            catalogue=select_catalogue(cat,use);raw=obs['raw_hz'][use];covariance=obs['covariance_hz2'][np.ix_(use,use)]
            result=screen(raw,covariance,catalogue)
            result.update(arm=arm,source=name,native_IDs=obs['native_ids'][use],
                original_eligibility=eligibility(obs['times_s'][use],obs['graph_values_hz'][use]),
                existing_parent_active_candidate_indices=context['retained_parent_active_families'],
                existing_parent_supported_candidate_indices=context['retained_parent_supported_families'],
                accepted=False,exact_evidence=False,background_response_selected_after_screen=False)
            write(Path(arm)/(name+'_screen.json'),result)
            top=np.asarray(result['candidate_indices'],int)
            shifts=catalogue['phase_sd_s'][top]*np.asarray(result['phase_z'])[top]
            linear=catalogue['frequency_hz'][top]+catalogue['derivative_hz_per_s'][top]*shifts[:,None]
            alias=np.asarray(result['coarse_aliases'])[top,0]
            native_prediction=linear+obs['radio_mean_hz'][use][None]-alias[:,None]*k.PERIOD+2*k.PERIOD
            npz(Path(arm)/(name+'_overlay.npz'),native_ids=obs['native_ids'][use],times_s=obs['times_s'][use],
                observed_native_CFO_Hz=obs['native_values_hz'][use],predicted_affine_native_CFO_Hz=native_prediction,
                residual_Hz=obs['native_values_hz'][use][None]-native_prediction,norads=cat['norads'][top],aliases=alias,
                phase_means_s=np.asarray(result['linear_phase_mean_s'])[top],phase_SD_s=np.asarray(result['linear_phase_SD_s'])[top])
            completed.append(dict(source=name,status='complete',top8=result['candidate_norads'],catalogue_count=result['catalogue_count']))
            print(arm,name,result['candidate_norads'][:3],flush=True)
    except Exception as exc:
        error=dict(error=repr(exc),traceback=traceback.format_exc());write(Path(arm)/'failure.json',error)
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    byname={row['source']:row for row in completed}
    return dict(arm=arm,scientific_numeric_seconds=time.monotonic()-began,
        contexts=[byname.get(name,dict(source=name,status='failed_or_missing')) for name,use in selections()])


def run():
    protocol=verify(True)
    if any(r.os.environ.get(key)!='1' for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']):raise ValueError('one BLAS thread required')
    write('execution_started.json',dict(protocol_sha256=r.sha(HERE/'protocol.json')))
    results=[]
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(job,arm,protocol['worker_deadline_seconds']):arm for arm in ARMS}
        for future in as_completed(futures):
            try:results.append(future.result())
            except Exception as exc:results.append(dict(arm=futures[future],scientific_numeric_seconds=protocol['worker_deadline_seconds'],error=repr(exc),contexts=[dict(source=name,status='failed_or_missing') for name,use in selections()]))
    verify(True)
    write('execution.json',dict(arms=results,cumulative_numeric_seconds=protocol['preparation_numeric_seconds']+sum(row['scientific_numeric_seconds'] for row in results),
        cap_seconds=180,all14_terminal=True,position_fits=0,GPS_used=False,accepted=False))
    files={str(path):r.sha(path) for path in sorted(HERE.rglob('*')) if path.is_file() and not set(path.parts)&{'__pycache__','.pytest_cache'}}
    write('RF_seal.json',dict(files=files,protocol_sha256=r.sha(HERE/'protocol.json'),all14_terminal=True))
    print('TERMINAL',r.read(HERE/'execution.json')['cumulative_numeric_seconds'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','freeze','run'));args=parser.parse_args()
    {'prepare':prepare,'freeze':freeze,'run':run}[args.action]()
