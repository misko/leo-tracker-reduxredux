"""Matched generating-component interventions on eight frozen noisy fast draws.

Inference remains the original baseline, never conditioned on nuisance truth.
"""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import multiprocessing
from pathlib import Path
import signal
import sys
import time
import traceback

import numpy as np

OLD = Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/synthetic')
sys.path.insert(0, str(OLD))
import experiment as control
import recovery as r

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / 'protocol.json'
APPROVAL = HERE.parent / 'audit/synthetic_preflight.json'
INTERVENTIONS = ('no_orbital_deviations', 'no_receiver_deviations')
CASES = ('DS24-0010', 'DS24-0011')
VARIANTS = ('stochastic_seed0', 'stochastic_seed1')
EXPECTED_CONTROL_SOURCE = '6b19e9e38ca68efe748502f863a69e4b991cf3fda3dd7419bf89d6d72fec5feb'
EXPECTED_CONTROL_SEAL = 'da4d71344744a1d244a6321f601619bbacaad84564e782eacde246ab593ad515'


def canonical(value):
    if isinstance(value, dict): return {str(key):canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [canonical(item) for item in value]
    if isinstance(value, np.ndarray): return canonical(value.tolist())
    if isinstance(value, np.generic): return value.item()
    return value


def fingerprint(value):
    return hashlib.sha256(json.dumps(canonical(value), sort_keys=True, allow_nan=False,
        separators=(',', ':')).encode()).hexdigest()


def changed_truth(common, intervention):
    if intervention not in INTERVENTIONS + ('unchanged',): raise ValueError('unknown intervention')
    truth = copy.deepcopy(common)
    widths = common['coordinate_widths']; bounds = np.r_[0, np.cumsum(widths)]
    coefficient = np.asarray(common['selected_coefficients']).copy()
    phases = np.asarray(common['true_phases_s']).copy()
    changed = np.zeros(len(coefficient), bool)
    if intervention == INTERVENTIONS[0]:
        phases = np.asarray(common['original_phase_locations_s']).copy()
        changed[bounds[3]:bounds[4]] = True
    if intervention == INTERVENTIONS[1]: changed[:bounds[2]] = True
    coefficient[changed] = 0.
    np.testing.assert_array_equal(coefficient[~changed], np.asarray(common['selected_coefficients'])[~changed])
    truth.update(selected_coefficients=coefficient, true_phases_s=phases,
        original_drawn_phases_s=np.asarray(common['true_phases_s']),
        original_drawn_coefficients=np.asarray(common['selected_coefficients']),
        common_control_observations_sha256=common['observations_sha256'], intervention=intervention,
        changed_coefficient_indices=np.flatnonzero(changed),
        phase_deviation_removed=intervention == INTERVENTIONS[0],
        inference_priors_not_truth_conditioned=True,
        alias_gauge='same known common-control integers; no alias search, values need not remain in centered alias interval')
    preserved = ('actual_noise_by_ID', 'noise_sigma_by_ID', 'noise_precision_by_track',
        'seed_children', 'predictive_fragment_bias_hz', 'inference_model', 'inference_powers')
    truth['preserved_draw_sha256'] = {key:fingerprint(common[key]) for key in preserved if key in common}
    for key, digest in truth['preserved_draw_sha256'].items(): assert fingerprint(truth[key]) == digest
    return truth


def construct(d, site, variant, intervention):
    original_scan, original_node, original_entries, common = control.synthesize(d, site, variant)
    truth = changed_truth(common, intervention)
    phases = np.asarray(truth['true_phases_s']); coefficients = np.asarray(truth['selected_coefficients'])
    x = np.asarray(control.SITES[site])
    scan, node, entries, _ = control.generate(d['scan'], d['node'], d['base'], phases, d['entries'], x)
    node['aliases'] = list(common['curved_aliases'])
    for entry, alias in zip(entries, common['predictive_aliases'], strict=True): entry['alias'] = alias
    p = control.make_event_problem(scan, node, d['keep'], 'c0', phases,
        d['powers'], d['means'], d['model'], [])
    geometry = control.geometry_features(p, x, 0.) # recomputes phase-dependent physical modes
    delta = geometry['features'] @ coefficients
    for k, (i, sl) in enumerate(zip(p.members, p.slices, strict=True)):
        mean = p.q[sl] * geometry['frequency'][sl] + delta[sl]
        scan.tracks[i]['values'] = mean - node['aliases'][k] * control.PERIOD
    if entries:
        view, _, _, groups, slices = control.linear_geometry(p, entries)
        g = control.geometry_features(view, x, 0.)
        prediction = view.q * g['frequency'] + g['features'] @ coefficients
        bias = np.asarray(common['predictive_fragment_bias_hz'])
        for entry, sl in zip(entries, slices, strict=True):
            mean = prediction[sl] + bias[groups[sl]]
            scan.tracks[entry['track_index']]['values'] = mean - entry['alias'] * control.PERIOD
    members = set(p.members) | {entry['track_index'] for entry in entries}
    control.add_noise(scan, members, common['actual_noise_by_ID'])
    truth['observations_sha256'] = control.observations_digest(scan, members)
    truth['phase_geometry_reference_s'] = phases
    assert node['aliases'] == common['curved_aliases']
    assert [entry['alias'] for entry in entries] == common['predictive_aliases']
    if intervention == 'unchanged':
        assert truth['observations_sha256'] == common['observations_sha256']
        for i in members:
            np.testing.assert_array_equal(scan.tracks[i]['values'], original_scan.tracks[i]['values'])
    return scan, node, entries, truth


def observation_arrays(d, scan, node, entries):
    records = []
    for k, (i, sl, source) in enumerate(zip(d['base'].members, d['base'].slices, d['base'].rows, strict=True)):
        track = scan.tracks[i]
        for oid, t, value, active in zip(track['observation_ids'], track['times'], track['values'], d['keep'][sl], strict=True):
            records.append((oid, t, value, i, node['aliases'][k], source['candidate_index'], bool(active), 'curved'))
    for entry in entries:
        track = scan.tracks[entry['track_index']]
        for oid, t, value in zip(track['observation_ids'], track['times'], track['values'], strict=True):
            records.append((oid, t, value, entry['track_index'], entry['alias'], entry['candidate_index'], True, 'predictive'))
    records.sort(key=lambda row: row[0]); assert len({row[0] for row in records}) == len(records)
    names = ('observation_ids', 'times_s', 'values_hz', 'track_indices', 'aliases', 'candidate_indices', 'used_by_position_likelihood', 'roles')
    return {name:np.asarray([row[k] for row in records]) for k, name in enumerate(names)}


def location(case, site, variant, intervention):
    return HERE / 'instances' / case / f'site{site}' / variant / intervention


def inference_fingerprint(d):
    return fingerprint(dict(mask=d['keep'], powers=d['powers'], means=d['means'], model=d['model'],
        labels=d['base'].labels, supported=d['base'].supported,
        rows=[(row['component'], row['candidate_index']) for row in d['base'].rows], entries=d['entries']))


def prepare():
    began_ns = time.time_ns(); deadline = began_ns + int(600e9)
    r.write_new(HERE / 'scientific_start.json', dict(started_utc_ns=began_ns, deadline_utc_ns=deadline,
        cap_seconds=600, includes='control reconstruction, preparation checks, review wait and all fits/fixed checks'))
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('600s global preparation/fits cap')))
    signal.alarm(600)
    assert r.sha(OLD / 'experiment.py') == EXPECTED_CONTROL_SOURCE
    assert r.sha(OLD / 'scientific_seal.json') == EXPECTED_CONTROL_SEAL
    old_protocol = control.verify()
    for path, digest in r.read(OLD / 'scientific_seal.json')['files'].items(): assert r.sha(path) == digest
    reconstructions, instances = [], []
    bindings = {str(OLD / name):r.sha(OLD / name) for name in ('protocol.json', 'scientific_seal.json', 'experiment.py')}
    for case in CASES:
        d = control.context(case)
        for site in range(2):
            for variant in VARIANTS:
                scan, node, entries, common = construct(d, site, variant, 'unchanged')
                control_files = {arm:OLD / 'fits' / case / f'site{site}' / variant / arm / 'generation.json' for arm in control.ARMS}
                for arm, path in control_files.items():
                    saved = r.read(path); bindings[str(path)] = r.sha(path)
                    assert common['observations_sha256'] == saved['observations_sha256']
                    for key in ('selected_coefficients', 'true_phases_s', 'actual_noise_by_ID', 'noise_precision_by_track',
                                'noise_sigma_by_ID', 'seed_children', 'predictive_fragment_bias_hz'):
                        if key in saved: assert fingerprint(common[key]) == fingerprint(saved[key]), (case, site, variant, key)
                members = set(d['base'].members) | {entry['track_index'] for entry in entries}
                sigma, gaussian = control.measurement_noise(scan, members, 1., common['seed_children'][1])
                gamma_rng = np.random.default_rng(common['seed_children'][3])
                expected_precision = {i:float(gamma_rng.gamma(2., .5)) for i in sorted(members)}
                assert fingerprint(expected_precision) == fingerprint(common['noise_precision_by_track'])
                for i in members:
                    for oid in scan.tracks[i]['observation_ids']:
                        assert common['actual_noise_by_ID'][oid] == gaussian[oid] / np.sqrt(expected_precision[i])
                assert len(common['seed_children']) == len(set(common['seed_children'])) == 4
                reconstructions.append(dict(case=case, site=site, variant=variant,
                    observations_sha256=common['observations_sha256'], c_arm_generation_files_sha256={arm:r.sha(path) for arm, path in control_files.items()},
                    Gaussian_noise_before_Gamma_sha256=fingerprint(gaussian), Gamma_precision_sha256=fingerprint(expected_precision),
                    original_phase_draw_sha256=fingerprint(common['true_phases_s']), original_coefficient_draw_sha256=fingerprint(common['selected_coefficients']),
                    seed_children=common['seed_children'], inference_fingerprint=inference_fingerprint(d)))
                for intervention in INTERVENTIONS:
                    s, n, es, truth = construct(d, site, variant, intervention)
                    directory = location(case, site, variant, intervention); directory.mkdir(parents=True, exist_ok=True)
                    arrays = observation_arrays(d, s, n, es)
                    path = directory / 'observations.npz'
                    if path.exists(): raise FileExistsError('preserve prepared synthetic observations')
                    np.savez_compressed(path, **arrays)
                    closures, arms = {}, {}
                    for arm in control.ARMS:
                        p = control.build(d, s, n, es, arm, truth['true_phases_s'])
                        closures[arm] = control.known_forward_closure(p, np.asarray(control.SITES[site]), truth)
                        arms[arm] = fingerprint(dict(values=p.values, mask=p.keep, labels=p.labels, aliases=p.alias))
                    assert arms['c0'] == arms['fitted_c']
                    truth.update(forward_closures=closures, c_arm_input_fingerprints=arms,
                        inference_fingerprint=inference_fingerprint(d), compact_observations_sha256=r.sha(path))
                    r.write_new(directory / 'truth.json', truth)
                    instances.append(dict(case=case, site=site, variant=variant, intervention=intervention,
                        observations_sha256=truth['observations_sha256'], observations_npz_path=str(path), observations_npz_sha256=r.sha(path),
                        truth_path=str(directory / 'truth.json'), truth_sha256=r.sha(directory / 'truth.json')))
    signal.alarm(0)
    r.write_new(HERE / 'preparation.json', dict(all_passed=True, control_reconstructions=reconstructions,
        instances=instances, exact_control_count=8, generated_intervention_count=16, position_fits=0,
        seconds=(time.time_ns() - began_ns) / 1e9, original_file_bindings=bindings, real_GPS_used=False))
    sources = {str(Path(__file__)):r.sha(__file__), str(HERE / 'test_components.py'):r.sha(HERE / 'test_components.py')}
    protocol = dict(version='fast generating component controls r01', cases=CASES, sites=control.SITES,
        seeds=control.SEEDS, noisy_variants=VARIANTS, interventions=INTERVENTIONS, arms=control.ARMS,
        unchanged_control_protocol_sha256=r.sha(OLD / 'protocol.json'), unchanged_control_source_sha256=EXPECTED_CONTROL_SOURCE,
        unchanged_control_scientific_seal_sha256=EXPECTED_CONTROL_SEAL,
        original_input_source_bindings_sha256=fingerprint(dict(input=old_protocol['input_sha256'], source=old_protocol['source_sha256'])),
        preparation_sha256=r.sha(HERE / 'preparation.json'), scientific_start_sha256=r.sha(HERE / 'scientific_start.json'),
        instance_bindings=instances, source_sha256=sources, required_independent_approval=str(APPROVAL),
        maximum_position_fits=32, workers=2, BLAS_threads=1, per_fit_seconds=180, global_seconds_including_preparation=600,
        cold_start=[0., 0.], phase_rounds=5, iterations_per_round=48,
        regional_center_latlon=[37.906, -122.545], box_width_km=25., c_truth=0.,
        generator_interventions='zero generating deviations only; no_orbital sets phase to original causal location and3shape coefficients0; no_receiver sets hardware+smooth coefficients0',
        preserved='all other selected coefficient draws, source constants, original Gaussian pointnoise and Gamma precision, exact IDs/times/powers/labels and known alias gauge',
        phase_semantics='original Student nu3 draw conditioned[-15,15] retained except deterministic phase=original causal means in no_orbital; original discarded draw preserved as provenance',
        physical_modes='recomputed at intervened true phase; linear original Gaussian engineering modes, not nonlinear perturbed-orbit propagation',
        inference='unchanged original priors/powers/masks/labels/region and VI/Gaussian predictive approximations; NOT known-nuisance inference oracles',
        association_selection_tested=False, full_generative_SBC=False, real_GPS_used=False,
        no_retries_rescue_seed_reroll_or_gate_waiver=True)
    r.write_new(PROTOCOL, protocol)
    r.write_new(HERE / 'protocol_seal.json', dict(protocol_sha256=r.sha(PROTOCOL)))
    print('PREPARED/FROZEN', r.sha(PROTOCOL), 'seconds', (time.time_ns() - began_ns) / 1e9, flush=True)


def verify(require_approval=False):
    protocol = r.read(PROTOCOL)
    assert r.sha(PROTOCOL) == r.read(HERE / 'protocol_seal.json')['protocol_sha256']
    control.verify()
    for path, digest in protocol['source_sha256'].items(): assert r.sha(path) == digest
    assert r.sha(HERE / 'preparation.json') == protocol['preparation_sha256']
    assert r.sha(HERE / 'scientific_start.json') == protocol['scientific_start_sha256']
    for row in protocol['instance_bindings']:
        assert r.sha(row['observations_npz_path']) == row['observations_npz_sha256']
        assert r.sha(row['truth_path']) == row['truth_sha256']
    if require_approval:
        approval = r.read(APPROVAL)
        assert approval.get('all_passed') is True and approval.get('protocol_sha256') == r.sha(PROTOCOL)
    return protocol


def one_fit(case, site, variant, intervention, arm, deadline_ns):
    began = time.monotonic(); history = []
    out = HERE / 'fits' / case / f'site{site}' / variant / intervention / arm
    try:
        remaining = min(180., (deadline_ns - time.time_ns()) / 1e9)
        if remaining <= 0: raise TimeoutError('600s global scientific cap exhausted')
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('180s fit or600s total cap')))
        signal.setitimer(signal.ITIMER_REAL, remaining)
        d = control.context(case); scan, node, entries, truth = construct(d, site, variant, intervention)
        prepared = r.read(location(case, site, variant, intervention) / 'truth.json')
        assert truth['observations_sha256'] == prepared['observations_sha256']
        npz = np.load(location(case, site, variant, intervention) / 'observations.npz', allow_pickle=False)
        for key, values in observation_arrays(d, scan, node, entries).items(): np.testing.assert_array_equal(values, npz[key])
        assert inference_fingerprint(d) == prepared['inference_fingerprint']
        x = np.zeros(2); reference = np.zeros(len(d['means']))
        for epoch in range(5):
            p = control.build(d, scan, node, entries, arm, reference)
            fitted = control.fit(p, x, iterations=48); x = np.asarray(fitted['parameters'])
            phases = p.state(x)['phases'][p.labels]; refreshed = np.clip(phases, -15, 15)
            record = dict(epoch=epoch, fit=fitted, parent_phase_reference=reference,
                posterior_absolute_phase_s=phases, phase_change_s=float(np.max(abs(refreshed - reference))))
            r.write_new(out / f'round{epoch}.json', record); history.append(record); reference = refreshed
        result = control.summary(p, x, entries)
        result.update(final_phase_change_s=history[-1]['phase_change_s'], history=history)
        r.write_new(out / 'raw_endpoint.json', result)
        target = np.asarray(control.SITES[site])
        diagnostics = dict(endpoint_at_final_reference=control.objective_terms(p, x),
            truth_at_final_reference=control.objective_terms(p, target))
        truth_problem = control.build(d, scan, node, entries, arm, truth['true_phases_s'])
        diagnostics['truth_at_true_phase_reference'] = control.objective_terms(truth_problem, target)
        diagnostics['known_forward_closure'] = control.known_forward_closure(truth_problem, target, truth)
        control_result_path = OLD / 'fits' / case / f'site{site}' / variant / arm / 'result.json'
        saved_control = r.read(control_result_path)
        result.update(status='complete', case=case, site_index=site, variant=variant, intervention=intervention, arm=arm,
            artificial_position_east_north_km=target, synthetic_position_error_km=float(np.linalg.norm(x - target)),
            error_vector_east_north_km=x - target, paired_control_error_km=saved_control['synthetic_position_error_km'],
            paired_control_error_vector_km=np.asarray(saved_control['endpoint_east_north_km']) - target,
            control_result_sha256=r.sha(control_result_path), fixed_objective_diagnostics=diagnostics,
            qualification=control.final_checks(p, x, result), observations_sha256=truth['observations_sha256'],
            instance_truth_sha256=r.sha(location(case, site, variant, intervention) / 'truth.json'),
            seconds=time.monotonic() - began, real_GPS_used=False,
            inference_not_truth_conditioned=True, association_selection_tested=False)
    except Exception as exc:
        result = dict(status='failed', case=case, site_index=site, variant=variant, intervention=intervention,
            arm=arm, error=repr(exc), traceback=traceback.format_exc(), completed_rounds=len(history),
            raw_endpoint_preserved=(out / 'raw_endpoint.json').exists(), seconds=time.monotonic() - began,
            real_GPS_used=False)
    finally: signal.setitimer(signal.ITIMER_REAL, 0)
    r.write_new(out / 'result.json', result)
    print(case, site, variant, intervention, arm, result['status'], round(result['seconds'], 3),
        result.get('synthetic_position_error_km', result.get('error')), flush=True)
    return result


def run():
    protocol = verify(require_approval=True)
    for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'): assert r.os.environ.get(key) == '1'
    start = r.read(HERE / 'scientific_start.json'); deadline = start['deadline_utc_ns']
    tasks = [(case, site, variant, intervention, arm) for case in CASES for site in range(2)
        for variant in VARIANTS for intervention in INTERVENTIONS for arm in control.ARMS]
    assert len(tasks) == protocol['maximum_position_fits'] == 32
    r.write_new(HERE / 'execution_start.json', dict(started_utc_ns=time.time_ns(), jobs=tasks,
        protocol_sha256=r.sha(PROTOCOL), independent_approval_sha256=r.sha(APPROVAL)))
    rows = []
    with ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context('spawn')) as pool:
        for future in as_completed([pool.submit(one_fit, *task, deadline) for task in tasks]): rows.append(future.result())
    verify(require_approval=True)
    result = dict(status='terminal', rows=rows, attempted_fits=len(rows), completed=sum(row['status'] == 'complete' for row in rows),
        failures=sum(row['status'] != 'complete' for row in rows),
        wall_seconds_since_first_preparation=(time.time_ns() - start['started_utc_ns']) / 1e9,
        protocol_sha256=r.sha(PROTOCOL), real_GPS_used=False, association_selection_tested=False)
    r.write_new(HERE / 'execution.json', result)
    files = sorted((HERE / 'fits').rglob('*.json')) + [HERE / name for name in
        ('scientific_start.json', 'preparation.json', 'protocol.json', 'protocol_seal.json', 'execution_start.json', 'execution.json')]
    files += [Path(row[key]) for row in protocol['instance_bindings'] for key in ('truth_path', 'observations_npz_path')]
    r.write_new(HERE / 'scientific_seal.json', dict(files={str(path):r.sha(path) for path in files},
        protocol_sha256=r.sha(PROTOCOL), maximum_position_fits=32, all_attempts_terminal=True,
        real_GPS_used=False, association_selection_tested=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('prepare', 'run'), required=True)
    {'prepare':prepare, 'run':run}[parser.parse_args().stage]()
