"""Conditional catalogue-screen falsification, never a position/GLRT simulator."""
import argparse
import copy
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import multiprocessing
from pathlib import Path
import signal
import sys
import time
import traceback

import numpy as np

KERNEL = Path('/srv/bulk/leo/research/ds24-identity-components-r01/identity')
sys.path.insert(0,str(KERNEL))
import challenge as k

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
CASES = ('DS24-0010','DS24-0011')
ARMS = k.ARMS
SEED = 2026102521
ALIASES = np.arange(-4,5)
CAP = 600.
PROTOCOL = HERE/'protocol.json'
APPROVAL = HERE.parent/'audit/nomination_preflight.json'


def write(path,value): k.m.r.write_new(HERE/path,value)
def read(path): return k.read(path)
def sha(path): return k.sha(path)
def digest(array): return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def alarm(seconds):
    if seconds<=0: raise TimeoutError('global budget exhausted before stage; no new computation')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('fixed conditional-test budget exhausted')))
    signal.setitimer(signal.ITIMER_REAL,max(.001,seconds))


def child_seeds(case,trial):
    seed = np.random.SeedSequence([SEED,int(case[-4:]),trial])
    return [int(child.generate_state(1)[0]) for child in seed.spawn(5)]


def inject(d,values):
    """Change only the target's values, never shared original state or labels."""
    scan = copy.copy(d['scan']); scan.tracks = list(d['scan'].tracks)
    i = d['target']['track_index']; track = dict(scan.tracks[i])
    values = np.asarray(values,float)
    if values.shape != np.asarray(track['values']).shape: raise ValueError('whole-source shape changed')
    track['values'] = values.copy(); scan.tracks[i] = track
    return dict(d,scan=scan,target_track=track)


def ordinary_screen(observation,catalogue):
    """Narrow port: no identity/truth/nominee/reserved competitor parameter."""
    if set(observation) != {'raw_hz','covariance_hz2'}: raise ValueError('undeclared screen observation fields')
    raw,cov = observation['raw_hz'],observation['covariance_hz2']
    result = k.coarse_phase_scores(raw,np.zeros(len(raw)),catalogue['frequency_hz'],
        catalogue['derivative_hz_per_s'],catalogue['phase_sd_s'],cov,np.zeros(len(raw),int))
    scores = np.where(catalogue['minimum_mean_elevation_deg']>=0,result['score'],np.inf)
    ranked = sorted((j for j in range(len(scores)) if np.isfinite(scores[j])),
        key=lambda j:(float(scores[j]),int(catalogue['norads'][j])))
    pool = ranked[:8]
    return dict(candidate_indices=pool,candidate_norads=[int(catalogue['norads'][j]) for j in pool],
        catalogue_norads=catalogue['norads'],coarse_scores=[float(v) if np.isfinite(v) else None for v in scores],
        coarse_aliases=result['aliases'],ranked_visible_indices=ranked,
        ranked_visible_norads=[int(catalogue['norads'][j]) for j in ranked],
        catalogue_count=len(scores),forced_or_reserved_candidate=False,screen_observation_sha256=digest(raw))


def eligible_generators(catalogue,parent_families):
    means,sd = catalogue['phase_means_s'],catalogue['phase_sd_s']
    use = (np.isfinite(means)&np.isfinite(sd)&(sd>0)&(abs(means)<=15)
        &(catalogue['minimum_mean_elevation_deg']>=0)&(catalogue['minimum_domain_endpoint_elevation_deg']>=0))
    return [j for j in range(len(means)) if use[j] and j not in parent_families]


def conditional_draw(radio_mean,covariance,physical_mean,shape,seeds):
    """Independent declared Gaussian conditional noise and physical-mode draws."""
    generators = [np.random.Generator(np.random.PCG64(seed)) for seed in seeds]
    shape_z = generators[1].normal(size=np.asarray(shape).shape[1])
    covariance_z = generators[2].normal(size=len(radio_mean))
    alias = int(generators[3].choice(ALIASES))
    noise = np.linalg.cholesky(covariance)@covariance_z
    latent_mean = radio_mean + physical_mean + shape@shape_z
    values = latent_mean + noise - alias*k.PERIOD
    return values,dict(shape_or_polynomial_coefficients=shape_z,conditional_Gaussian_z=covariance_z,
        conditional_Gaussian_hz=noise,whole_source_alias=alias,latent_mean_hz=latent_mean,
        seed_children=seeds,maximum_forward_identity_error_hz=float(np.max(abs(values+alias*k.PERIOD-latent_mean-noise))))


def adaptive_candidates(records,null_objective):
    usable = [row for row in records if row.get('status')=='complete']
    usable.sort(key=lambda row:(row['reference_objective'],row['norad']))
    if not usable: return []
    best = usable[0]; selected = {row['norad'] for row in usable[:2]}
    best_upper = best['reference_objective'] + best['score_error']
    for row in usable:
        lo = row['reference_objective']-row['score_error']
        hi = row['reference_objective']+row['score_error']
        if lo<=best_upper or lo<=null_objective<=hi:
            selected.add(row['norad'])
    return [row['norad'] for row in usable if row['norad'] in selected]


def freeze():
    previous = k.verify()
    inventory = read(k.OLD/'inventory.json')
    layouts = [row for case in CASES for row in inventory['rows'] if row['case']==case]
    if len(layouts)!=2: raise ValueError('frozen two source layouts missing')
    bindings = dict(previous['source_hashes'])
    ledger_path = Path('/srv/bulk/leo/research/ds24-movement-policy-r01/cohort_ledger.json')
    ledger = read(ledger_path)
    for row in ledger['rows']:
        if row['case'] not in CASES: continue
        for item in row['frozen_scan_files']+[row['baseline']]:
            if sha(item['path']) != item['sha256']: raise ValueError('frozen corpus changed')
            bindings[item['path']] = item['sha256']
        for suffix in ('.json','_forecast.json'):
            path = k.m.r.SOURCE/'causal_phase_history'/(row['case']+suffix)
            bindings[str(path)] = sha(path)
    for path in (Path(__file__),HERE/'test_experiment.py',HERE/'report.py',HERE/'PROTOCOL.md',KERNEL/'challenge.py',
                 KERNEL/'protocol.json',ledger_path,k.m.r.REPO/'tools/ds23_conditioned_relative_nomination.py'):
        bindings[str(path)] = sha(path)
    metadata = []
    for item in layouts:
        target = item['target']; tracks = read(k.m.r.SOURCE/item['case']/'tracks.json')
        track = next(t for t in tracks if t['key']==target['component'])
        metadata.append(dict(case=item['case'],times_s=track['times'],rf_hz=track['rf_hz'],
            native_ids=track['observation_ids'],source_component=track['key'],
            receiver=track['receiver'],channel=track['channel'],historically_response_selected_layout=True))
    write(Path('metadata.json'),dict(layouts=metadata,no_new_CFO_generated=True))
    protocol = dict(cases=CASES,layouts=layouts,metadata_sha256=sha(HERE/'metadata.json'),source_input_hashes=bindings,
        seed=SEED,physical_draws_per_layout=4,null_draws_per_layout=2,maximum_trials=12,arms=ARMS,
        generator_identity_rule='uniform without replacement from sorted original catalogue indices absent from original_protected/active curved/predictive families; finite causal mean within15s,positiveSD,visible at causal mean and domain endpoints',
        identity_rng='PCG64 SeedSequence([2026102521,case_integer,99]); choice4 without replacement; no reroll if blocked',
        trial_rng='five independent PCG64 children of SeedSequence([2026102521,case_integer,trial_index]):phase,shape-or-polynomial,conditionalGaussian,alias,reservedunused',
        physical_law='fresh original causal unit-marginal-variance Student nu3 location/SD conditioned[-15,15]; full original3physical modes standardGaussian; original c0 parent conditional radio/noise covariance including300Hz sourceconstant',
        unresolved_law='original proper degree4 Legendre coefficients PERIOD/sqrt6 times5standardGaussians, same conditional covariance and alias law; declared comparator, not empirical clutter',
        alias_support=ALIASES,alias_prior='uniform finite whole-source integer, same for physical/null generation and scoring',
        position='common original saved c0 endpoint for both arms; fixed conditional context, no GPS truth or position search',
        screen='unchanged original coarse_phase_scores applied to synthetic context; ordinary best8 only, no true label/forced nominee/reserved competitor',
        parent_guard='all possible generating families absent from original likelihood; original common conditioning fixed before CFO; exact shared union-shortlist cavity across every candidate and null',
        conditioning_limit='generator and nomination use full original parent; exact scores may use less parent data after union cavity; not matching-law probability calibration, full parent simulation, GLRT closure, or SBC',
        phase_nodes=1281,reference_nodes=2561,score_tolerance=1e-3,
        adaptive_rule='denser-score top2 plus every finite candidate whose observed1281/2561 discrepancy could alter winner/null ordering; max8; no grid refinement or backfill',
        numerical_outcome='all dense finite candidates ranked; winner failing primary/dense/adaptive/visibility checks means numerically unresolved, never silently replaced by next qualified candidate',
        maximum_candidate_contexts=192,maximum_arm_jobs=24,global_scientific_seconds=CAP,
        per_arm_seconds=60,context_seconds=120,workers=2,BLAS_threads=1,position_fits=0,GPS_used=False,
        operational_identity_acceptance_rule=None,no_retries_rescue_or_seed_reroll=True)
    write(Path('protocol.json'),protocol)
    write(Path('protocol_seal.json'),dict(protocol_sha256=sha(PROTOCOL)))
    print('FROZEN',sha(PROTOCOL),flush=True)


def verify(approval=False):
    p = read(PROTOCOL)
    if sha(PROTOCOL)!=read(HERE/'protocol_seal.json')['protocol_sha256']: raise ValueError('protocol changed')
    for path,expected in p['source_input_hashes'].items():
        if sha(path)!=expected: raise ValueError('bound source/input changed: '+path)
    if sha(HERE/'metadata.json')!=p['metadata_sha256']: raise ValueError('layout metadata changed')
    if approval:
        a = read(APPROVAL)
        if not a.get('all_passed') or a['protocol_sha256']!=sha(PROTOCOL): raise ValueError('independent preflight absent')
    return p


def prepare_context(item,deadline):
    alarm(min(120.,deadline-time.monotonic()))
    d = k.m.t.load_target(item['target'])
    x = np.asarray(d['arms']['c0']['endpoint_east_north_km'])
    d['arms'] = {arm:dict(d['arms'][arm],endpoint_east_north_km=x) for arm in ARMS}
    d = inject(d,np.zeros(len(d['target_track']['times'])))
    entries = k.records(item,d)[:1]
    for entry in entries: entry['alias']=0
    parents = {}
    for arm in ARMS:
        dd,info = k.cavity(d,[],arm)
        if not all(info[key] for key in ('phase_qualified','precision_qualified','support_qualified')):
            raise ValueError('fixed parent conditioning unqualified')
        d['arms'][arm] = dd['arms'][arm]; parents[arm] = info
    comp = k.owners.components(d,'c0',x,entries)
    times = np.asarray(d['target_track']['times']); sky = d['scan'].sky
    freq,elevation = k.phase_frequency_grid(sky,times,*k.latlon(x),phase_seconds=d['all_means'])
    plus = k.phase_frequency_grid(sky,times,*k.latlon(x),phase_seconds=d['all_means']+.01)[0]
    minus = k.phase_frequency_grid(sky,times,*k.latlon(x),phase_seconds=d['all_means']-.01)[0]
    endpoint = [k.phase_frequency_grid(sky,times,*k.latlon(x),phase_seconds=np.full(len(d['all_means']),phi))[1].min(axis=1) for phi in (-15.,15.)]
    catalogue = dict(norads=d['scan'].norads,frequency_hz=freq*comp['q'][None],
        derivative_hz_per_s=(plus-minus)/.02*comp['q'][None],phase_means_s=d['all_means'],phase_sd_s=d['widths'],
        minimum_mean_elevation_deg=elevation.min(axis=1),minimum_domain_endpoint_elevation_deg=np.minimum(*endpoint))
    likelihood_families = {row['candidate_index'] for row,sl in zip(d['base'].rows,d['base'].slices,strict=True) if d['keep'][sl].any()} | {entry['candidate_index'] for entry in d['entries']}
    parent_families = set(d['original_protected']) | likelihood_families
    d['nomination_parent_likelihood_families'] = likelihood_families
    eligible = eligible_generators(catalogue,parent_families)
    if len(eligible)<4: raise ValueError('fewer than4 response-free generating possibilities; no replacement')
    selected = np.random.Generator(np.random.PCG64(np.random.SeedSequence([SEED,int(item['case'][-4:]),99]))).choice(eligible,4,replace=False)
    out = HERE/item['case']; out.mkdir(parents=True,exist_ok=True)
    path = out/'context.npz'
    np.savez_compressed(path,**catalogue,radio_mean_hz=-comp['raw'],conditional_covariance_hz2=comp['covariance'],
        times_s=times,q=comp['q'],native_ids=np.asarray(entries[0]['observation_ids']))
    info = dict(case=item['case'],fixed_position_east_north_km=x,catalogue_count=len(catalogue['norads']),
        catalogue_norads=d['scan'].norads,eligible_generating_indices=eligible,eligible_generating_norads=d['scan'].norads[eligible],
        original_parent_families=sorted(parent_families),original_parent_likelihood_families=sorted(likelihood_families),selected_generating_indices=selected,
        selected_generating_norads=d['scan'].norads[selected],parent_states=parents,
        target_entries=entries,response_free_until_all_identity_draws_frozen=True,context_npz_sha256=sha(path),
        source_layout_historically_response_selected=True,cutoff_utc_ns=d['scan'].receipt['cutoff_utc_ns'])
    write(Path(item['case'])/'context.json',info)
    write(Path(item['case'])/'context_seal.json',dict(protocol_sha256=sha(PROTOCOL),context_npz_sha256=sha(path),
        context_json_sha256=sha(out/'context.json'),no_new_CFO_generated_yet=True))
    signal.setitimer(signal.ITIMER_REAL,0)
    return d,entries,comp,catalogue,selected


def generate(d,comp,identity,kind,trial):
    seeds = child_seeds(d['case'],trial); x=comp['x']; radio=-comp['raw']
    if kind=='physical':
        cd = k.candidate(comp['d'],int(d['scan'].norads[identity])); law=k.m.q.prior(cd)
        uniform=np.random.Generator(np.random.PCG64(seeds[0])).uniform()
        distribution=law['distribution']; lo=distribution.cdf(-15.); hi=distribution.cdf(15.)
        phase=float(distribution.ppf(lo+uniform*(hi-lo)))
        geom=k.m.q.phase_geometry(cd,x,np.asarray([phase])); physical=geom['frequency_hz'][0]*comp['q']
        shape=geom['shape_columns_hz'][0]*comp['q'][:,None]
        if geom['elevation_deg'].min()<0: raise ValueError('drawn phase not visible; no redraw')
        truth=dict(kind=kind,generating_norad=int(d['scan'].norads[identity]),generating_index=int(identity),phase_s=phase,
            phase_uniform_draw=uniform,phase_prior={key:v for key,v in law.items() if key!='distribution'})
    else:
        times=np.asarray(d['target_track']['times']); z=2*(times-times.min())/np.ptp(times)-1
        physical=np.zeros(len(times)); shape=np.polynomial.legendre.legvander(z,4)*k.PERIOD/np.sqrt(6)
        truth=dict(kind=kind,generating_norad=None,generating_index=None,phase_s=None)
    values,draw=conditional_draw(radio,comp['covariance'],physical,shape,seeds)
    truth.update(draw); truth.update(physical_mean_hz=physical,shape_or_polynomial_columns_hz=shape,
        c0_generating_radio_mean_hz=radio,c0_generating_covariance_hz2=comp['covariance'],inference_receives_no_truth=True)
    return values,truth


def exact_arm(d,entries,values,pool,arm,relative,deadline):
    began=time.monotonic(); checkpoint=[]
    try:
        alarm(min(60.,deadline-began))
        synthetic=inject(d,values)
        changed,cavity=k.cavity(synthetic,pool,arm)
        write(relative/(arm+'_cavity.json'),cavity)
        if not all(cavity[key] for key in ('phase_qualified','precision_qualified','support_qualified')):
            raise ValueError('shared union cavity phase/precision/support unqualified')
        comp=k.owners.components(changed,arm,np.asarray(d['arms']['c0']['endpoint_east_north_km']),entries)
        np.savez_compressed(HERE/relative/(arm+'_conditional.npz'),raw_hz=comp['raw'],covariance_hz2=comp['covariance'],
            radio_mean_hz=values-comp['raw'],parent_coefficients=comp['parent_coefficients'],parent_noise=comp['parent_noise'])
        indices=np.arange(len(values)); nullwide=k.null_score(comp,indices,np.arange(-5,6)); null=k.alias_diagnostics(nullwide)
        candidates=[]
        for j in pool:
            norad=int(d['scan'].norads[j]); row=dict(norad=norad,candidate_index=j,status='blocked',numerically_qualified=False)
            try:
                cd=k.candidate(comp['d'],norad)
                first=k.score(cd,comp,indices,1281,np.arange(-5,6)); fixed=k.alias_diagnostics(first)
                reference=k.score(cd,comp,indices,2561)
                error=abs(fixed['objective']-reference['objective'])
                row.update(status='complete',**fixed,reference_objective=reference['objective'],score_error=error,
                    numerically_qualified=bool(error<=1e-3),phase_prior=first['phase_prior'],
                    minimum_elevation_deg=first['minimum_elevation_deg'],quadrature_prior_mass=first['quadrature_prior_mass'])
            except TimeoutError: raise
            except Exception as exc: row.update(reason=repr(exc))
            candidates.append(row); checkpoint.append(row)
            write(relative/(arm+'_'+str(norad)+'_checkpoint.json'),row)
        selected=adaptive_candidates(candidates,null['objective'])
        for row in candidates:
            if row['norad'] not in selected: continue
            try:
                reference=k.adaptive(k.candidate(comp['d'],row['norad']),comp,indices)
                error=abs(row['objective']-reference['objective'])
                row.update(adaptive_reference=reference,adaptive_score_error=error)
                row['numerically_qualified'] &= error<=1e-3
            except TimeoutError: raise
            except Exception as exc: row.update(adaptive_failure=repr(exc),numerically_qualified=False)
        ranked=sorted((row for row in candidates if row['status']=='complete'),key=lambda row:(row['reference_objective'],row['norad']))
        winner=ranked[0] if ranked else None
        ordering_qualified=bool(winner and len(ranked)==len(candidates) and winner['numerically_qualified']
            and all(row['numerically_qualified'] for row in candidates if row['norad'] in selected))
        result=dict(status='complete',arm=arm,candidates=candidates,null=null,denser_ranked_norads=[r['norad'] for r in ranked],
            adaptive_checked_norads=selected,ordering_numerically_qualified=ordering_qualified,
            best_physical_norad=winner['norad'] if winner else None,
            best_physical_minus_null=winner['objective']-null['objective'] if winner else None,
            original_active_shortlist_families=sorted(set(pool)&d['nomination_parent_likelihood_families']),
            fixed_position_east_north_km=comp['x'],cavity=cavity,identity_qualified=False)
    except Exception as exc:
        result=dict(status='failed',arm=arm,error=repr(exc),traceback=traceback.format_exc(),
            preserved_candidate_checkpoints=len(checkpoint),ordering_numerically_qualified=False,identity_qualified=False)
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    result['seconds']=time.monotonic()-began; write(relative/(arm+'_result.json'),result)
    return result


def case_job(item,deadline):
    began=time.monotonic(); case=item['case']; rows=[]
    try:
        d,entries,comp,catalogue,identities=prepare_context(item,deadline)
        for trial in range(6):
            relative=Path(case)/('trial'+str(trial)); (HERE/relative).mkdir(exist_ok=True)
            row=dict(case=case,trial=trial,kind='physical' if trial<4 else 'unresolved',status='failed')
            try:
                alarm(min(60.,deadline-time.monotonic()))
                values,truth=generate(d,comp,identities[trial] if trial<4 else None,row['kind'],trial)
                np.savez_compressed(HERE/relative/'observations.npz',values_hz=values,times_s=d['target_track']['times'],
                    native_ids=np.asarray(entries[0]['observation_ids']),q=comp['q'])
                write(relative/'generation.json',truth)
                # The generator's identity/phase/kind never crosses this port.
                observation=dict(raw_hz=values+comp['raw'],covariance_hz2=comp['covariance'])
                screen=ordinary_screen(observation,catalogue); write(relative/'screen.json',screen)
                signal.setitimer(signal.ITIMER_REAL,0)
                arms={arm:exact_arm(d,entries,values,screen['candidate_indices'],arm,relative,deadline) for arm in ARMS}
                row.update(status='complete',arms={arm:dict(status=arms[arm]['status'],seconds=arms[arm]['seconds']) for arm in ARMS},
                    observations_sha256=sha(HERE/relative/'observations.npz'),screen_sha256=sha(HERE/relative/'screen.json'))
            except Exception as exc:row.update(error=repr(exc),traceback=traceback.format_exc())
            finally:signal.setitimer(signal.ITIMER_REAL,0)
            rows.append(row);write(relative/'trial.json',row)
            print(case,trial,row['kind'],row['status'],row.get('arms'),flush=True)
    except Exception as exc:
        for trial in range(6):rows.append(dict(case=case,trial=trial,kind='physical' if trial<4 else 'unresolved',status='context_failed',error=repr(exc),traceback=traceback.format_exc()))
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    result=dict(case=case,rows=rows,seconds=time.monotonic()-began,position_fits=0,GPS_used=False)
    write(Path(case)/'execution.json',result);return result


def run():
    began=time.monotonic();p=verify(approval=True)
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        if k.m.r.os.environ.get(key)!='1':raise ValueError('one numerical thread required')
    write(Path('scientific_start.json'),dict(protocol_sha256=sha(PROTOCOL),cap_seconds=CAP,started_utc_ns=time.time_ns()))
    deadline=began+CAP;rows=[]
    with ProcessPoolExecutor(max_workers=2,mp_context=multiprocessing.get_context('spawn')) as pool:
        for future in as_completed([pool.submit(case_job,item,deadline) for item in p['layouts']]):rows.append(future.result())
    verify(approval=True)
    write(Path('execution.json'),dict(rows=rows,all_selected_terminal=True,cumulative_scientific_seconds=time.monotonic()-began,
        workers=2,BLAS_threads=1,position_fits=0,GPS_used=False,identity_qualified=False))
    files=sorted(path for path in HERE.rglob('*') if path.is_file() and path.name not in ('RF_seal.json',))
    write(Path('RF_seal.json'),dict(files={str(path):sha(path) for path in files},protocol_sha256=sha(PROTOCOL),
        position_fits=0,GPS_used=False,identity_qualified=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',required=True,choices=('freeze','run'))
    globals()[parser.parse_args().stage]()
