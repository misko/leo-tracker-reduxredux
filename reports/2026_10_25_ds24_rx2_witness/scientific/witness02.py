"""Three whole RX2 owners: truth-free nomination and symmetric cavity evidence.

Research adapter only. No assignments, position fitting, or evaluation coordinates.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy
from pathlib import Path
import signal
import sys
import time
import traceback

import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPAIR = Path('/srv/bulk/leo/research/ds24-identity-support-r01/scientific')
sys.path.insert(0, str(REPAIR))
import support_replay as sr
k, r = sr.k, sr.r
ARMS = ('c0', 'fitted_c')
CASE = 'DS24-0013'
CAP = 600.
PROTOCOL = HERE/'protocol02.json'
PROTOCOL_SEAL = HERE/'protocol_seal02.json'
INVENTORY = REPAIR.parent/'witness/whole_scan_inventory.json'
OWNERSHIP = Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/transfer/ownership')/CASE/'parent.json'


def write(name, value):
    r.write_new(HERE/name, value)


def npz(name, **arrays):
    path = HERE/name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        np.savez_compressed(stream, **arrays)


def clean_entries(d, entries):
    """Only radio columns are used. Archived identity and alias are discarded."""
    dummy = int(d['base'].labels[0])
    return [dict(e, candidate_index=dummy, alias=0) for e in entries]


def background(d, arm, x, entries):
    return k.owners.components(d, arm, x, clean_entries(d, entries))


def native_entries(d, selected, coverage):
    entries = []
    accepted = set().union(*(set(coverage[a]['accepted_observation_ids']) for a in ARMS))
    for row in selected:
        i = next(i for i, track in enumerate(d['scan'].tracks) if track['key'] == row['component'])
        track = d['scan'].tracks[i]
        if list(track['observation_ids']) != row['observation_ids']:
            raise ValueError('complete native source ID order changed')
        if accepted & set(track['observation_ids']):
            raise ValueError('whole owner overlaps original accepted IDs')
        entries.append(dict(component=track['key'], track_index=i,
            observation_ids=list(track['observation_ids']), points=len(track['observation_ids'])))
    ids = [oid for e in entries for oid in e['observation_ids']]
    if len(entries) != 3 or len(ids) != 124 or len(ids) != len(set(ids)):
        raise ValueError('three complete mutually disjoint owners /124 IDs required')
    return clean_entries(d, entries)


def at_common_position(d, x):
    # cavity() has a fixed-state phase-refresh interface reading these fields.
    # Both arms get the same existing RF coordinate, never a new position fit.
    return dict(d, arms={a:dict(d['arms'][a], endpoint_east_north_km=np.asarray(x).copy()) for a in ARMS})


def owner_context(d, entry):
    track = d['scan'].tracks[entry['track_index']]
    dummy = int(d['base'].labels[0])
    return dict(d, target=dict(component=entry['component'], track_index=entry['track_index'],
        candidate_index=dummy, norad=int(d['scan'].norads[dummy]), observation_ids=entry['observation_ids'],
        phase_nu=d['model']['nu'], phase_mean_s=float(d['all_means'][dummy]), phase_sd_s=float(d['widths'][dummy])),
        target_entry=clean_entries(d, [entry])[0],
        target_track=dict(times=np.asarray(track['times']), rf_hz=11.5e9))


def catalogue(d, x, entry, q):
    times = np.asarray(d['scan'].tracks[entry['track_index']]['times'])
    sky = d['scan'].sky
    f, elevation = k.phase_frequency_grid(sky, times, *k.latlon(x), phase_seconds=d['all_means'])
    plus = k.phase_frequency_grid(sky, times, *k.latlon(x), phase_seconds=d['all_means']+.01)[0]
    minus = k.phase_frequency_grid(sky, times, *k.latlon(x), phase_seconds=d['all_means']-.01)[0]
    return dict(norads=d['scan'].norads, frequency_hz=f*q[None],
        derivative_hz_per_s=(plus-minus)/.02*q[None], phase_means_s=d['all_means'],
        phase_sd_s=d['widths'], minimum_mean_elevation_deg=elevation.min(axis=1))


def marginal(comp, sl):
    indices = np.arange(len(comp['raw']))[sl]
    return dict(raw=comp['raw'][indices].copy(), covariance=comp['covariance'][np.ix_(indices, indices)].copy(),
        q=comp['q'][indices].copy(), parent_coefficients=comp['parent_coefficients'].copy(),
        parent_noise=comp['parent_noise'].copy())


def hard_parent(info):
    return bool(info['phase_qualified'] and info['precision_qualified'] and info['support_qualified'])


def conditioning_trace(d, pool):
    curved = {row['candidate_index'] for row, sl in zip(d['base'].rows, d['base'].slices, strict=True) if d['keep'][sl].any()}
    predictive = {e['candidate_index'] for e in d['entries']}
    return dict(original_active_curved_families=sorted(curved), original_active_predictive_families=sorted(predictive),
        shortlist_parent_family_intersection=sorted(set(pool) & (curved | predictive)),
        cavity_scope='this owner ordinary c0 top8 only; shared across all8+null and both c arms')


def component_contract(d, x, entry, arm, source):
    comp = background(d, arm, x, [entry])
    cov = comp['covariance']
    meta = d['scan'].fixed_window_noise
    sigma = np.array([meta['per_observation_noise_sigma_hz'][oid] if meta['extra_parameter_BIC_gain'] > 0
        else d['scan'].radio_sigma_hz for oid in entry['observation_ids']])
    minimum = float(sigma.min()*np.sqrt(2))
    if np.linalg.eigvalsh(cov).min() < minimum**2*(1-1e-8):
        raise ValueError('conditional covariance violates native-noise lower bound')
    if not np.isfinite(cov).all() or np.any(comp['q'] <= 0):
        raise ValueError('invalid background/q')
    root = np.linalg.cholesky(cov)
    aliases, shifts = k.alias_vectors(np.zeros(len(comp['raw']), int), np.arange(-4, 5))
    coordinates = k.latlon(x)
    observer = sr.geodetic_to_ecef_km(*coordinates, 0.)
    comp.update(d=owner_context(d, entry), root=root, observer=observer,
        base_logdet=float(2*np.log(np.diag(root)).sum()), noise_minimum_sd=minimum,
        aliases=aliases, shifts=shifts, whitened_aliases=solve_triangular(root, shifts.T, lower=True).T)
    npz(Path(source)/(arm+'_conditional.npz'), raw_hz=comp['raw'], covariance_hz2=cov, q=comp['q'],
        parent_coefficients=comp['parent_coefficients'], parent_noise=comp['parent_noise'],
        native_ids=np.asarray(entry['observation_ids']), times_s=np.asarray(d['scan'].tracks[entry['track_index']]['times']),
        values_hz=np.asarray(d['scan'].tracks[entry['track_index']]['values']), aliases=aliases,
        common_position_east_north_km=x)
    return comp


def null_qr(raw,covariance,times,period):
    """Independent augmented-QR density, avoiding full broad-prior covariance."""
    z=2*(times-times.min())/np.ptp(times)-1
    modes=np.polynomial.legendre.legvander(z,4)*period/np.sqrt(6)
    root=np.linalg.cholesky(covariance)
    u=solve_triangular(root,modes,lower=True)
    _,rr=np.linalg.qr(np.vstack((u,np.eye(5))),mode='reduced')
    shifted=raw[None]+np.arange(-4,5)[:,None]*period
    w=solve_triangular(root,shifted.T,lower=True).T
    coefficient=np.linalg.solve(rr,np.linalg.solve(rr.T,(w@u).T)).T
    residual=w-coefficient@u.T
    energy=np.sum(residual**2,axis=1)+np.sum(coefficient**2,axis=1)
    volume=2*np.log(np.diag(root)).sum()+2*np.log(abs(np.diag(rr))).sum()
    return float(-2*(logsumexp(-.5*(energy+volume+len(raw)*np.log(2*np.pi)))-np.log(9)))


def verify(approval=False):
    protocol = r.read(PROTOCOL)
    if r.sha(PROTOCOL) != r.read(PROTOCOL_SEAL)['protocol_sha256']:
        raise ValueError('protocol changed')
    for path, expected in protocol['source_input_hashes'].items():
        if r.sha(path) != expected:
            raise ValueError('bound source/input changed: '+path)
    if approval:
        receipt = r.read(ROOT/'audit/preflight.json')
        if receipt.get('all_passed') is not True or receipt.get('protocol_sha256') != r.sha(PROTOCOL):
            raise ValueError('independent matching preflight required')
        if protocol['coordinator_authorization'] != r.sha(ROOT/'COORDINATOR_PLAN.md'):
            raise ValueError('standing bounded coordinator authorization changed')
    return protocol


def freeze():
    if PROTOCOL.exists():
        raise FileExistsError('freeze only once')
    context = r.read(ROOT/'context/checks.json')
    if context['all_passed'] is not True:
        raise ValueError('independent corpus/native-ID context required')
    bindings = dict(context['bindings'])
    for path, expected in bindings.items():
        if r.sha(path) != expected:
            raise ValueError('previous metadata binding changed: '+path)
    # Freeze all transitive numerical source files actually imported by these ports.
    prefixes = (str(r.REPO), '/srv/bulk/leo/research/')
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and path.endswith('.py') and path.startswith(prefixes):
            bindings[path] = r.sha(path)
    for path in (Path(__file__), HERE/'test_witness02.py', HERE/'PROTOCOL02.md', ROOT/'context/checks.json',
        ROOT/'COORDINATOR_PLAN.md', HERE/'test_receipt02.json', REPAIR/'protocol.json', REPAIR/'RF_seal.json',
        REPAIR.parent/'audit/preflight.py', INVENTORY, OWNERSHIP):
        bindings[str(path)] = r.sha(path)
    inventory = r.read(INVENTORY)
    selected = inventory['selected']
    if [len(e['observation_ids']) for e in selected] != [24, 57, 43]:
        raise ValueError('original chronological three-owner order changed')
    # Whitelist metadata. Historical response-selected candidate/alias are not copied.
    sources = [{key:row[key] for key in ('component', 'observation_ids')} for row in selected]
    protocol = dict(case=CASE, sources=sources, arms=ARMS, sources_selected_before_new_CFO=True,
        sources_have_historical_graph_and_information_exposure=True, source_input_hashes=bindings,
        coordinator_authorization=r.sha(ROOT/'COORDINATOR_PLAN.md'),
        common_position='original saved c0 RF endpoint, both arms', ordinary_catalogue='complete causal bank',
        ordinary_screen='unchanged moment-Gaussian phase/nearest per-owner alias; mean LOS eligibility; no nominee/reserve',
        primary_shortlist='c0 ordinary top8 per owner, reused unchanged in fitted_c; fitted_c screen diagnostic only',
        original_parent_background='5 fixed-position phase refreshes; joint3 radio-only target background, independent marginals',
        exact_parent_background='PER-OWNER union-top8 curved+predictive cavity;5 fixed-position phase refreshes; shared among8+null',
        target_law='original causal Student nu3 marginal SD conditioned[-15,+15]s, full3 original Gaussian physical modes B(phi), unitprior',
        support_law='whole-source LOS indicator times original conditioned phase prior; invisible likelihood0, no visible-mass renormalization',
        aliases=list(range(-4, 5)), alias_prior='uniform per whole owner; same measure for every physical/null',
        null='proper degree4 Legendre Gaussian coefficients PERIOD/sqrt6, same background and source300Hzconstant',
        absolute_precision='unchanged1e-3 -2logevidence, full analytic physical/support enclosure and selected independent GL32/64 refs',
        reference_selection='new raw top2 plus every bound-overlap winner/null; no old-score/true-label input',
        order_certificate='strict lowerlogZwinner>all8+null upperlogZ; null independent augmentedQR guard1e-7, floating allowance1e-6',
        hard_parent_checks='absolute phase<=15.000001, final refresh<=.01s,Gamma<=1e-5,nonempty supported calibration',
        original_parent_residual_gates='saved diagnostic only; no qualification or operational admission',
        original_accepted_IDs='operational ledgers unchanged; cavity removals are diagnostic conditioning only',
        source_residuals='descriptive causal-mean orbit plus ordinary coarse alias, radio conditioned on stated background; no posterior phase/mode/constant adjustment',
        budget=dict(cumulative_scientific_seconds=600, workers=2, numeric_threads=1,
            preparation_max_seconds=120, worker_dispatch='one arm/worker; all3owners chronological',
            worker_wall_seconds='(600-actual preparation scientific seconds)/2; no retries/rescues'),
        preparation_scientific_seconds=0., owned_test_receipt_sha256=r.sha(HERE/'test_receipt02.json'),
        prior_unexecuted_protocol_sha256=r.sha(HERE/'protocol.json'),
        technical_revision='pass only serializable x/metadata to workers; context reconstruction charged inside worker budget; exact previously audited augmentedQR null reference replaces eigen arithmetic with same1e-7guard/1e-6allowance',
        maximum_owner_arm_results=6, maximum_candidate_contexts=48, maximum_catalogue_screens=6,
        fitted_position_count=0, GPS_used=False, operational_identity_assignment=False,
        discovery_conditioned_evidence_executed=False, software=dict(numpy=np.__version__, scipy=sr.sm.scipy.__version__ if hasattr(sr.sm,'scipy') else __import__('scipy').__version__))
    write('protocol02.json', protocol)
    write('protocol_seal02.json', dict(protocol_sha256=r.sha(PROTOCOL)))
    print(r.sha(PROTOCOL), flush=True)


def prepare(deadline):
    sr.alarm(deadline-time.monotonic())
    protocol = verify(True)
    d = r.context(CASE)
    x = np.asarray(d['arms']['c0']['endpoint_east_north_km'])
    d = at_common_position(d, x)
    coverage = r.read(OWNERSHIP)['coverage']
    entries = native_entries(d, protocol['sources'], coverage)
    originals = {}
    for arm in ARMS:
        sr.alarm(deadline-time.monotonic())
        changed, info = k.cavity(d, [], arm)
        originals[arm] = (changed, background(changed, arm, x, entries), info)
        write('original_parent_'+arm+'.json', dict(info, common_position_east_north_km=x,
            original_accepted_IDs=coverage[arm]['accepted_observation_ids'], operational_membership_changed=False))
        if not hard_parent(info):
            raise ValueError('original parent hard fixed-state guard failed: '+arm)
    screens = []
    for index, entry in enumerate(entries):
        sr.alarm(deadline-time.monotonic())
        name = 'owner'+str(index)
        nominal = marginal(originals['c0'][1], originals['c0'][1]['slices'][index])
        cat = catalogue(d, x, entry, nominal['q'])
        npz(Path(name)/'catalogue.npz', **cat)
        track = d['scan'].tracks[entry['track_index']]
        npz(Path(name)/'observations.npz', native_ids=np.asarray(entry['observation_ids']),
            times_s=track['times'], values_hz=track['values'], q=nominal['q'])
        owner_screens = {}
        for arm in ARMS:
            comp = marginal(originals[arm][1], originals[arm][1]['slices'][index])
            screen = sr.previous.ordinary_screen(dict(raw_hz=comp['raw'], covariance_hz2=comp['covariance']), cat)
            if len(screen['candidate_indices']) != 8 or screen['forced_or_reserved_candidate']:
                raise ValueError('ordinary full catalogue did not return8 unforced candidates')
            npz(Path(name)/(arm+'_nomination_background.npz'), raw_hz=comp['raw'], covariance_hz2=comp['covariance'],
                parent_coefficients=comp['parent_coefficients'], parent_noise=comp['parent_noise'])
            write(Path(name)/(arm+'_screen.json'), screen)
            owner_screens[arm] = screen
        pool = owner_screens['c0']['candidate_indices']
        metadata = dict(entry, owner=name, common_position_east_north_km=x,
            exact_candidate_indices=pool, exact_candidate_norads=owner_screens['c0']['candidate_norads'],
            original_conditioning_trace=conditioning_trace(d, pool), shortlist_shared_both_arms=True,
            historical_exposure='response-selected graph source and earlier fixed-label information ranking; labels not imported')
        write(Path(name)/'metadata.json', metadata)
        screens.append(metadata)
    return d, x, screens


def score_owner(d, x, owner, arm, deadline):
    sr.alarm(deadline-time.monotonic())
    name = owner['owner']
    pool, norads = owner['exact_candidate_indices'], owner['exact_candidate_norads']
    changed, info = k.cavity(d, pool, arm)
    write(Path(name)/(arm+'_cavity.json'), info)
    if not hard_parent(info):
        raise ValueError('exact cavity hard fixed-state guard failed')
    changed = owner_context(changed, owner)
    comp = component_contract(changed, x, owner, arm, name)
    up = sr.ecef_to_enu_matrix(*k.latlon(x))[2]
    times = np.asarray(changed['target_track']['times'])
    null = k.null_score(comp, np.arange(len(comp['raw'])))
    null['independent_dense_objective'] = null_qr(comp['raw'], comp['covariance'], times, k.PERIOD)
    null['independent_reference_method'] = 'exact previously audited augmentedQR, same normalized null law'
    null['independent_dense_error'] = abs(null['objective']-null['independent_dense_objective'])
    null['independent_dense_passed'] = bool(null['independent_dense_error'] <= 1e-7)
    null['floating_objective_allowance'] = 1e-6
    write(Path(name)/(arm+'_null.json'), null)
    threshold = -.5*(null['objective']+1e-6) if null['independent_dense_passed'] else None
    rows, callbacks = [], {}
    for j, norad in zip(pool, norads, strict=True):
        sr.alarm(deadline-time.monotonic())
        began = time.monotonic()
        try:
            cd = k.candidate(changed, norad)
            if not np.array_equal(cd['target_sky']['time_s'], cd['target_mode_bank']['time_s']):
                raise ValueError('nominal/mode grid mismatch')
            support = sr.sg.support(cd['target_sky'], times, up, comp['observer'])
            write(Path(name)/(arm+'_'+str(norad)+'_support.json'), support)
            row, fun, ip, bp = sr.score_candidate(cd, comp, support, threshold)
            row.update(norad=norad, candidate_index=j)
            if row.get('full_support_lower_log_integral') is not None:
                threshold = max(threshold, row['full_support_lower_log_integral']) if threshold is not None else row['full_support_lower_log_integral']
            callbacks[norad] = (fun, ip, bp)
        except TimeoutError:
            raise
        except Exception as exc:
            row = dict(norad=norad, candidate_index=j, status='failed', numerically_qualified=False,
                error=repr(exc), traceback=traceback.format_exc())
        row['seconds'] = time.monotonic()-began
        rows.append(row)
        write(Path(name)/(arm+'_'+str(norad)+'_checkpoint.json'), row)
    selected = sr.required_references(rows, null['objective'], [])
    for row in rows:
        if row['norad'] not in selected or row['norad'] not in callbacks:
            continue
        sr.alarm(deadline-time.monotonic())
        fun, ip, bp = callbacks[row['norad']]
        reference, bracket = sr.sm.reference(fun, ip), sr.sm.reference(fun, bp)
        error = abs(reference['objective']-row['objective']) if row.get('objective') is not None and reference['objective'] is not None else 0.
        row.update(independent_reference=reference, independent_bracket_reference=bracket, primary_reference_error=float(error))
        row['numerically_qualified'] &= bool(reference['success'] and bracket['success'] and error <= sr.sm.TOL)
    finite = sorted([row for row in rows if row.get('objective') is not None], key=lambda q:(q['objective'], q['norad']))
    winner = finite[0] if finite else None
    full_precision = bool(null['independent_dense_passed'] and winner and winner['numerically_qualified']
        and all(row['numerically_qualified'] for row in rows if row['norad'] in selected)
        and all(row['status'] in ('complete', 'zero_physical_evidence') for row in rows))
    result = dict(owner=name, component=owner['component'], arm=arm, status='complete', candidates=rows, null=null,
        required_reference_norads=selected, ranked_physical_norads=[row['norad'] for row in finite],
        raw_physical_winner_norad=winner['norad'] if winner else None,
        physical_minus_null=winner['objective']-null['objective'] if winner else None,
        ordering_absolute_precision_qualified=full_precision, evidence_order_certificate=sr.certified_order(rows, null),
        cavity_hard_parent_checks_passed=hard_parent(info), cavity_original_residual_gates_passed=info['original_remaining_gates_pass'],
        common_position_east_north_km=x, original_accepted_IDs_changed=False,
        operational_identity_assignment=False, discovery_conditioned_evidence=False, position_fits=0, GPS_used=False)
    write(Path(name)/(arm+'_result.json'), result)
    return result


def arm_worker(x, owners, arm, deadline):
    began = time.monotonic()
    results = []
    try:
        sr.alarm(deadline-time.monotonic())
        d = at_common_position(r.context(CASE), x)
    except Exception as exc:
        results = [dict(owner=o['owner'], arm=arm, status='worker_context_failed', error=repr(exc)) for o in owners]
        signal.setitimer(signal.ITIMER_REAL, 0)
        output = dict(arm=arm, owners=results, scientific_worker_seconds=time.monotonic()-began)
        write(arm+'_execution.json', output)
        return output
    for owner in owners:
        try:
            result = score_owner(d, x, owner, arm, deadline)
            results.append(dict(owner=owner['owner'], status='complete',
                raw_winner=result['raw_physical_winner_norad'], order=result['evidence_order_certificate']))
            print(arm, owner['owner'], results[-1], flush=True)
        except Exception as exc:
            failure = dict(owner=owner['owner'], arm=arm, status='budget_or_context_failed', error=repr(exc),
                traceback=traceback.format_exc(), all8candidate_slots_retained_in_denominator=True)
            write(Path(owner['owner'])/(arm+'_failure.json'), failure)
            results.append(failure)
    signal.setitimer(signal.ITIMER_REAL, 0)
    output = dict(arm=arm, owners=results, scientific_worker_seconds=time.monotonic()-began)
    write(arm+'_execution.json', output)
    return output


def run():
    protocol = verify(True)
    for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        if r.os.environ.get(key) != '1':
            raise ValueError('one numeric thread required')
    if (HERE/'execution_started.json').exists():
        raise FileExistsError('no reruns/retries')
    write('execution_started.json', dict(protocol_sha256=r.sha(PROTOCOL), cap_seconds=CAP))
    began = time.monotonic()
    results = []
    try:
        d, x, owners = prepare(began+120.)
        prep = time.monotonic()-began
        signal.setitimer(signal.ITIMER_REAL, 0)
        write('preparation.json', dict(scientific_seconds=prep, owners=[e['owner'] for e in owners],
            common_position_east_north_km=x, all3screened=True, position_fits=0, GPS_used=False))
        deadline = time.monotonic()+(CAP-prep)/2
        with ProcessPoolExecutor(max_workers=2) as pool:
            futures = {pool.submit(arm_worker, x, owners, arm, deadline):arm for arm in ARMS}
            for future in as_completed(futures):
                arm = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    results.append(dict(arm=arm, worker_failed=repr(exc), scientific_worker_seconds=(CAP-prep)/2,
                        owners=[dict(owner='owner'+str(i), status='worker_failed', error=repr(exc)) for i in range(3)]))
    except Exception as exc:
        prep = time.monotonic()-began
        write('preparation_failure.json', dict(error=repr(exc), traceback=traceback.format_exc(), scientific_seconds=prep))
        results = [dict(arm=a, scientific_worker_seconds=0., owners=[dict(owner='owner'+str(i), status='preparation_failed') for i in range(3)]) for a in ARMS]
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    verify(True)
    write('execution.json', dict(arms=results, total_scientific_seconds=prep+sum(q['scientific_worker_seconds'] for q in results),
        cap_seconds=600, all_selected_terminal=True, selected_sources=3, selected_owner_arm_contexts=6,
        selected_candidate_contexts=48, wall_seconds=time.monotonic()-began, position_fits=0, GPS_used=False,
        operational_identity_assignment=False, discovery_conditioned_evidence_executed=False))
    files = {str(p):r.sha(p) for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
    write('RF_seal.json', dict(protocol_sha256=r.sha(PROTOCOL), files=files,
        all_selected_terminal=True, position_fits=0, GPS_used=False, operational_identity_assignment=False))
    print('TERMINAL', r.read(HERE/'execution.json')['total_scientific_seconds'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('freeze', 'run'))
    args = parser.parse_args()
    freeze() if args.action == 'freeze' else run()
