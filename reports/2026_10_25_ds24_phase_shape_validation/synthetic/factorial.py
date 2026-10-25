"""Missing generating phase/shape cells; inference and eight draws stay frozen."""
import argparse
import copy
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from pathlib import Path
import signal
import sys
import time
import traceback

import numpy as np

COMBINED = Path('/srv/bulk/leo/research/ds24-identity-components-r01/synthetic')
sys.path.insert(0, str(COMBINED))
import components as previous

control, r = previous.control, previous.r
fingerprint = previous.fingerprint
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PROTOCOL = HERE / 'protocol.json'
APPROVAL = HERE.parent / 'audit/synthetic_preflight.json'
OLD = control.HERE
CASES, VARIANTS = previous.CASES, previous.VARIANTS
INTERVENTIONS = ('phase_at_causal_mean', 'shape_zero')
EXPECTED_COMBINED_SEAL = '840051200579dc65cc87d6e37ad4a9e07a99000221ec9b882e6662495dea9310'


def changed_truth(common, intervention):
    if intervention not in INTERVENTIONS: raise ValueError(intervention)
    truth = copy.deepcopy(common)
    coefficient = np.asarray(common['selected_coefficients']).copy()
    phases = np.asarray(common['true_phases_s']).copy()
    bounds = np.r_[0, np.cumsum(common['coordinate_widths'])]
    if intervention == 'phase_at_causal_mean':
        phases = np.asarray(common['original_phase_locations_s']).copy()
    else:
        coefficient[bounds[3]:bounds[4]] = 0.
    truth.update(selected_coefficients=coefficient, true_phases_s=phases,
        original_drawn_phases_s=np.asarray(common['true_phases_s']),
        original_drawn_coefficients=np.asarray(common['selected_coefficients']),
        common_control_observations_sha256=common['observations_sha256'], intervention=intervention,
        factorial_phase_on=intervention == 'shape_zero', factorial_shape_on=intervention == 'phase_at_causal_mean',
        phase_deviation_removed=intervention == 'phase_at_causal_mean', inference_priors_not_truth_conditioned=True,
        alias_gauge='same known control integers, even outside centered alias interval; no association/alias search')
    preserved = ('actual_noise_by_ID', 'noise_sigma_by_ID', 'noise_precision_by_track', 'seed_children',
        'predictive_fragment_bias_hz', 'inference_model', 'inference_powers')
    truth['preserved_draw_sha256'] = {key:fingerprint(common[key]) for key in preserved if key in common}
    return truth


def construct(d, site, variant, intervention):
    _, _, _, common = control.synthesize(d, site, variant)
    truth = changed_truth(common, intervention)
    phases, coefficient = np.asarray(truth['true_phases_s']), np.asarray(truth['selected_coefficients'])
    x = np.asarray(control.SITES[site])
    scan, node, entries, _ = control.generate(d['scan'], d['node'], d['base'], phases, d['entries'], x)
    node['aliases'] = list(common['curved_aliases'])
    for entry, alias in zip(entries, common['predictive_aliases'], strict=True): entry['alias'] = alias
    p = control.make_event_problem(scan, node, d['keep'], 'c0', phases,
        d['powers'], d['means'], d['model'], [])
    # Both Doppler and B are constructed at the actual generating phase.
    geometry = control.geometry_features(p, x, 0.)
    delta = geometry['features'] @ coefficient
    for k, (i, sl) in enumerate(zip(p.members, p.slices, strict=True)):
        scan.tracks[i]['values'] = p.q[sl] * geometry['frequency'][sl] + delta[sl] - node['aliases'][k] * control.PERIOD
    if entries:
        view, _, _, groups, slices = control.linear_geometry(p, entries)
        g = control.geometry_features(view, x, 0.)
        prediction = view.q * g['frequency'] + g['features'] @ coefficient
        for entry, sl in zip(entries, slices, strict=True):
            scan.tracks[entry['track_index']]['values'] = (prediction[sl]
                + np.asarray(common['predictive_fragment_bias_hz'])[groups[sl]] - entry['alias'] * control.PERIOD)
    members = set(p.members) | {entry['track_index'] for entry in entries}
    control.add_noise(scan, members, common['actual_noise_by_ID'])
    truth.update(observations_sha256=control.observations_digest(scan, members), phase_geometry_reference_s=phases)
    return scan, node, entries, truth


def location(case, site, variant, intervention):
    return HERE / 'instances' / case / f'site{site}' / variant / intervention


def seal_verify(path):
    for name, digest in r.read(path)['files'].items(): assert r.sha(name) == digest, name


def result_path(case, site, variant, arm, cell):
    if cell == '11': return OLD / 'fits' / case / f'site{site}' / variant / arm / 'result.json'
    if cell == '00': return COMBINED / 'fits' / case / f'site{site}' / variant / 'no_orbital_deviations' / arm / 'result.json'
    name = {'01':'phase_at_causal_mean', '10':'shape_zero'}[cell]
    return HERE / 'fits' / case / f'site{site}' / variant / name / arm / 'result.json'


def prepare():
    started = time.time_ns()
    r.write_new(HERE / 'scientific_start.json', dict(started_utc_ns=started, deadline_utc_ns=started + int(600e9),
        cap_seconds=600, includes='all control/NPZ reconstruction, numerical preparation, review wait, fits and fixed gate replay'))
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('600s scientific cap')))
    signal.alarm(600)
    original_protocol = control.verify()
    assert r.sha(COMBINED / 'scientific_seal.json') == EXPECTED_COMBINED_SEAL
    previous.verify(require_approval=True)
    seal_verify(OLD / 'scientific_seal.json'); seal_verify(COMBINED / 'scientific_seal.json')
    bindings = {str(root / name):r.sha(root / name) for root, names in
        ((OLD, ('protocol.json', 'scientific_seal.json', 'experiment.py')),
         (COMBINED, ('protocol.json', 'scientific_seal.json', 'components.py', 'summary.json', 'gate_replay.json')))
        for name in names}
    reconstructed, instances, observation_factorials = [], [], []
    for case in CASES:
        d = control.context(case)
        for site in range(2):
            for variant in VARIANTS:
                s11, n11, e11, common = previous.construct(d, site, variant, 'unchanged')
                cell_arrays = {'11':previous.observation_arrays(d, s11, n11, e11)}
                full_paths = [OLD / 'fits' / case / f'site{site}' / variant / arm / 'generation.json' for arm in control.ARMS]
                for path in full_paths:
                    saved = r.read(path); bindings[str(path)] = r.sha(path)
                    for key in ('observations_sha256', 'selected_coefficients', 'true_phases_s', 'actual_noise_by_ID',
                            'noise_precision_by_track', 'noise_sigma_by_ID', 'seed_children', 'predictive_fragment_bias_hz'):
                        if key in saved: assert fingerprint(common[key]) == fingerprint(saved[key]), (case, site, variant, key)
                s0, n0, e0, t0 = previous.construct(d, site, variant, 'no_orbital_deviations')
                cell_arrays['00'] = previous.observation_arrays(d, s0, n0, e0)
                old_directory = previous.location(case, site, variant, 'no_orbital_deviations')
                saved0 = r.read(old_directory / 'truth.json')
                assert t0['observations_sha256'] == saved0['observations_sha256']
                with np.load(old_directory / 'observations.npz', allow_pickle=False) as archive:
                    for key, value in previous.observation_arrays(d, s0, n0, e0).items(): np.testing.assert_array_equal(value, archive[key])
                for path in (old_directory / 'truth.json', old_directory / 'observations.npz'):
                    bindings[str(path)] = r.sha(path)
                for arm in control.ARMS:
                    for cell in ('11', '00'):
                        path = result_path(case, site, variant, arm, cell)
                        saved = r.read(path); assert saved['status'] == 'complete'
                        assert saved['qualification']['passed']
                        bindings[str(path)] = r.sha(path)
                members = set(d['base'].members) | {entry['track_index'] for entry in d['entries']}
                sigma, gaussian = control.measurement_noise(d['scan'], members, 1., common['seed_children'][1])
                rng = np.random.default_rng(common['seed_children'][3])
                precision = {i:float(rng.gamma(2., .5)) for i in sorted(members)}
                assert fingerprint(precision) == fingerprint(common['noise_precision_by_track'])
                for i in members:
                    for oid in d['scan'].tracks[i]['observation_ids']:
                        assert common['actual_noise_by_ID'][oid] == gaussian[oid] / np.sqrt(precision[i])
                assert len(common['seed_children']) == len(set(common['seed_children'])) == 4
                reconstructed.append(dict(case=case, site=site, variant=variant,
                    full_observations_sha256=common['observations_sha256'], both_removed_observations_sha256=t0['observations_sha256'],
                    full_truth_sha256=fingerprint(common), both_removed_truth_sha256=fingerprint(t0),
                    Gaussian_noise_before_Gamma_sha256=fingerprint(gaussian), Gamma_precision_sha256=fingerprint(precision),
                    original_phase_draw_sha256=fingerprint(common['true_phases_s']),
                    original_coefficient_draw_sha256=fingerprint(common['selected_coefficients']), seed_children=common['seed_children'],
                    inference_fingerprint=previous.inference_fingerprint(d)))
                for intervention in INTERVENTIONS:
                    scan, node, entries, truth = construct(d, site, variant, intervention)
                    out = location(case, site, variant, intervention); out.mkdir(parents=True, exist_ok=True)
                    path = out / 'observations.npz'
                    if path.exists(): raise FileExistsError(path)
                    arrays = previous.observation_arrays(d, scan, node, entries)
                    cell_arrays['01' if intervention == 'phase_at_causal_mean' else '10'] = arrays
                    np.savez_compressed(path, **arrays)
                    closures, arms = {}, {}
                    for arm in control.ARMS:
                        p = control.build(d, scan, node, entries, arm, truth['true_phases_s'])
                        closures[arm] = control.known_forward_closure(p, np.asarray(control.SITES[site]), truth)
                        arms[arm] = fingerprint(dict(values=p.values, mask=p.keep, labels=p.labels, aliases=p.alias))
                    assert arms['c0'] == arms['fitted_c']
                    truth.update(forward_closures=closures, c_arm_input_fingerprints=arms,
                        inference_fingerprint=previous.inference_fingerprint(d), compact_observations_sha256=r.sha(path))
                    r.write_new(out / 'truth.json', truth)
                    instances.append(dict(case=case, site=site, variant=variant, intervention=intervention,
                        observations_sha256=truth['observations_sha256'], observations_npz_path=str(path), observations_npz_sha256=r.sha(path),
                        truth_path=str(out / 'truth.json'), truth_sha256=r.sha(out / 'truth.json')))
                for cell in ('00', '01', '10'):
                    for key in cell_arrays['11']:
                        if key != 'values_hz': np.testing.assert_array_equal(cell_arrays[cell][key], cell_arrays['11'][key])
                vectors = {cell:arrays['values_hz'] for cell, arrays in cell_arrays.items()}
                interaction = vectors['11'] - vectors['10'] - vectors['01'] + vectors['00']
                path = HERE / 'observation_factorials' / case / f'site{site}' / (variant + '.npz')
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.exists(): raise FileExistsError(path)
                np.savez_compressed(path, observation_ids=cell_arrays['11']['observation_ids'],
                    **{'values_' + cell + '_hz':values for cell, values in vectors.items()},
                    phase_effect_shape_on_hz=vectors['11'] - vectors['01'],
                    phase_effect_shape_off_hz=vectors['10'] - vectors['00'],
                    shape_effect_phase_on_hz=vectors['11'] - vectors['10'],
                    shape_effect_phase_off_hz=vectors['01'] - vectors['00'], interaction_hz=interaction)
                observation_factorials.append(dict(case=case, site=site, variant=variant, path=str(path), sha256=r.sha(path),
                    observation_count=len(interaction), interaction_RMS_hz=float(np.sqrt(np.mean(interaction ** 2))),
                    interaction_maximum_abs_hz=float(np.max(abs(interaction))),
                    meaning='[B(original nonlinear phase)-B(causal phase location)] times original shape coefficients; all common noise/receiver/constants cancel'))
    signal.alarm(0)
    r.write_new(HERE / 'preparation.json', dict(all_passed=True, original_file_bindings=bindings,
        control_reconstructions=reconstructed, instances=instances, observation_factorials=observation_factorials,
        exact_full_control_count=8, exact_both_removed_control_count=8,
        generated_intervention_count=16, position_fits=0, real_GPS_used=False, seconds=(time.time_ns() - started) / 1e9))
    sources = {str(HERE / name):r.sha(HERE / name) for name in ('factorial.py', 'test_factorial.py', 'summarize.py')}
    protocol = dict(version='missing generating phase-shape factorial r01', cases=CASES, sites=control.SITES, seeds=control.SEEDS,
        noisy_variants=VARIANTS, interventions=INTERVENTIONS, arms=control.ARMS, source_sha256=sources,
        reused_original_bindings=bindings, original_input_source_bindings_sha256=fingerprint(dict(input=original_protocol['input_sha256'], source=original_protocol['source_sha256'])),
        preparation_sha256=r.sha(HERE / 'preparation.json'), scientific_start_sha256=r.sha(HERE / 'scientific_start.json'),
        instance_bindings=instances, observation_factorial_bindings=observation_factorials,
        required_independent_approval=str(APPROVAL), maximum_position_fits=32,
        reused_full_fits=16, reused_both_removed_fits=16, workers=2, BLAS_threads=1, per_fit_seconds=180,
        global_seconds_including_preparation=600, cold_start=[0., 0.], phase_rounds=5, iterations_per_round=48,
        regional_center_latlon=[37.906, -122.545], box_width_km=25., c_truth=0.,
        generator='phase_at_causal_mean changes only true phase to original causal location, retaining shape coefficients; shape_zero zeros only3physical shape coefficients per originally supported family, retaining original nonlinear phase draw',
        physical_modes='B and nonlinear Doppler recomputed at actual generating phase; original linear physical engineering modes, not perturbed-orbit propagation',
        phase_law='original unit-marginal-variance Student nu3 location/SD conditioned[-15,15] draw unchanged in phase-on cells; phase-off deterministic original causal location inside domain',
        preserved='receiver coefficients, curved/predictive source constants, per-ID Gaussian draws, per-track Gamma precision, all IDs/times/labels/masks/powers/known aliases; no new random draw',
        inference='unchanged original priors/powers/VI/local-phase/Gaussian predictive approximations; no nuisance truth supplied; zero initial phase reference',
        cell_map={'11':'original_all_deviations', '00':'prior_no_orbital_deviations', '01':'phase_at_causal_mean', '10':'shape_zero'},
        contrasts=dict(metrics=['east_north_error_vector_km', 'error_km', 'squared_error_km2'],
            phase_removal_shape_on='g01-g11', phase_removal_shape_off='g00-g10',
            shape_removal_phase_on='g10-g11', shape_removal_phase_off='g00-g01',
            marginal_phase_removal='0.5*((g01-g11)+(g00-g10))',
            marginal_shape_removal='0.5*((g10-g11)+(g00-g01))', interaction='g11-g10-g01+g00',
            missing_or_failed_cell='retain all attempts; contrasts undefined, no imputation; report gates separately',
            interpretation='endpoint interaction includes generating B(phase)-shape coupling and estimator response; paired conditional simulator diagnostics, eight draws not independent geometry replicates; no significance threshold or real prior update'),
        endpoint_checks='truth/endpoint objectives and FD gradients at same final phase reference; truth also at actual generating phase; forward closure and exact original gate replay',
        all_completed_errors_included_regardless_of_qualification=True, association_selection_tested=False, full_generative_SBC=False,
        real_GPS_used=False, no_retries_rescue_reroll_or_gate_waiver=True)
    r.write_new(PROTOCOL, protocol); r.write_new(HERE / 'protocol_seal.json', dict(protocol_sha256=r.sha(PROTOCOL)))
    print('PREPARED/FROZEN', r.sha(PROTOCOL), 'seconds', (time.time_ns() - started) / 1e9, flush=True)


def verify(require_approval=False):
    p = r.read(PROTOCOL)
    assert r.sha(PROTOCOL) == r.read(HERE / 'protocol_seal.json')['protocol_sha256']
    control.verify()
    for group in ('source_sha256', 'reused_original_bindings'):
        for path, digest in p[group].items(): assert r.sha(path) == digest, path
    for name in ('preparation', 'scientific_start'): assert r.sha(HERE / (name + '.json')) == p[name + '_sha256']
    for row in p['instance_bindings']:
        assert r.sha(row['observations_npz_path']) == row['observations_npz_sha256']
        assert r.sha(row['truth_path']) == row['truth_sha256']
    for row in p['observation_factorial_bindings']: assert r.sha(row['path']) == row['sha256']
    if require_approval:
        receipt = r.read(APPROVAL)
        assert receipt.get('all_passed') is True and receipt['protocol_sha256'] == r.sha(PROTOCOL)
    return p


def one_fit(case, site, variant, intervention, arm, deadline):
    began = time.monotonic(); history = []
    out = HERE / 'fits' / case / f'site{site}' / variant / intervention / arm
    try:
        remaining = min(180., (deadline - time.time_ns()) / 1e9)
        if remaining <= 0: raise TimeoutError('600s total scientific cap exhausted')
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('180s fit or600s global cap')))
        signal.setitimer(signal.ITIMER_REAL, remaining)
        d = control.context(case); scan, node, entries, truth = construct(d, site, variant, intervention)
        saved = r.read(location(case, site, variant, intervention) / 'truth.json')
        assert truth['observations_sha256'] == saved['observations_sha256']
        with np.load(location(case, site, variant, intervention) / 'observations.npz', allow_pickle=False) as archive:
            for key, value in previous.observation_arrays(d, scan, node, entries).items(): np.testing.assert_array_equal(value, archive[key])
        assert previous.inference_fingerprint(d) == saved['inference_fingerprint']
        x, reference = np.zeros(2), np.zeros(len(d['means']))
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
        truth_problem = control.build(d, scan, node, entries, arm, truth['true_phases_s'])
        diagnostics = dict(endpoint_at_final_reference=control.objective_terms(p, x),
            truth_at_final_reference=control.objective_terms(p, target),
            truth_at_true_phase_reference=control.objective_terms(truth_problem, target),
            known_forward_closure=control.known_forward_closure(truth_problem, target, truth))
        controls = {cell:dict(path=str(result_path(case, site, variant, arm, cell)),
            sha256=r.sha(result_path(case, site, variant, arm, cell))) for cell in ('11', '00')}
        result.update(status='complete', case=case, site_index=site, variant=variant, intervention=intervention, arm=arm,
            artificial_position_east_north_km=target, synthetic_position_error_km=float(np.linalg.norm(x - target)),
            error_vector_east_north_km=x - target, fixed_objective_diagnostics=diagnostics,
            qualification=control.final_checks(p, x, result), observations_sha256=truth['observations_sha256'], reused_controls=controls,
            instance_truth_sha256=r.sha(location(case, site, variant, intervention) / 'truth.json'),
            seconds=time.monotonic() - began, real_GPS_used=False, inference_not_truth_conditioned=True, association_selection_tested=False)
    except Exception as exc:
        result = dict(status='failed', case=case, site_index=site, variant=variant, intervention=intervention, arm=arm,
            error=repr(exc), traceback=traceback.format_exc(), completed_rounds=len(history),
            raw_endpoint_preserved=(out / 'raw_endpoint.json').exists(), seconds=time.monotonic() - began, real_GPS_used=False)
    finally: signal.setitimer(signal.ITIMER_REAL, 0)
    r.write_new(out / 'result.json', result)
    print(case, site, variant, intervention, arm, result['status'], round(result['seconds'], 3),
        result.get('synthetic_position_error_km', result.get('error')), flush=True)
    return result


def run():
    protocol = verify(require_approval=True)
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'): assert r.os.environ.get(name) == '1'
    start = r.read(HERE / 'scientific_start.json'); began = time.monotonic()
    tasks = [(case, site, variant, intervention, arm) for case in CASES for site in range(2)
        for variant in VARIANTS for intervention in INTERVENTIONS for arm in control.ARMS]
    assert len(tasks) == protocol['maximum_position_fits'] == 32
    r.write_new(HERE / 'execution_start.json', dict(started_utc_ns=time.time_ns(), jobs=tasks,
        protocol_sha256=r.sha(PROTOCOL), independent_approval_sha256=r.sha(APPROVAL)))
    rows = []
    with ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context('spawn')) as pool:
        for future in as_completed([pool.submit(one_fit, *task, start['deadline_utc_ns']) for task in tasks]): rows.append(future.result())
    verify(require_approval=True)
    r.write_new(HERE / 'execution.json', dict(status='terminal', rows=rows, attempted_fits=len(rows),
        completed=sum(row['status'] == 'complete' for row in rows), failures=sum(row['status'] != 'complete' for row in rows),
        fit_batch_wall_seconds=time.monotonic() - began,
        wall_seconds_since_first_preparation=(time.time_ns() - start['started_utc_ns']) / 1e9,
        protocol_sha256=r.sha(PROTOCOL), real_GPS_used=False, association_selection_tested=False))
    files = sorted((HERE / 'fits').rglob('*.json')) + [HERE / name for name in
        ('scientific_start.json', 'preparation.json', 'protocol.json', 'protocol_seal.json', 'execution_start.json', 'execution.json')]
    files += [Path(row[key]) for row in protocol['instance_bindings'] for key in ('truth_path', 'observations_npz_path')]
    files += [Path(row['path']) for row in protocol['observation_factorial_bindings']]
    r.write_new(HERE / 'scientific_seal.json', dict(files={str(path):r.sha(path) for path in files},
        protocol_sha256=r.sha(PROTOCOL), maximum_position_fits=32, all_attempts_terminal=True,
        real_GPS_used=False, association_selection_tested=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, choices=('prepare', 'run'))
    {'prepare':prepare, 'run':run}[parser.parse_args().stage]()
