"""Bounded conditional fast-scan synthetic controls; no real GPS or RF access.

Known labels, aliases, masks and likelihood powers are inherited. This does not
exercise graph selection and is not full generative simulation-based calibration.
"""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
import hashlib
import json
import multiprocessing
from pathlib import Path
import signal
import sys
import time
import traceback

import numpy as np
import scipy
from scipy.stats import t, norm

import recovery as r
from ds23_frequency_events import make_event_problem, attach_event_predictive
from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry
from ds23_synthetic_phase_law import bounded_phase_draw
from ds23_synthetic_precision import measurement_noise, add_noise
from investigate_dsx01_localization_failures import fit
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD
from probe_ds23_frequency_events import cached, summary
from probe_ds23_synthetic_closure import generate, alias_encode
from prototype_dsx01_continuous_position import latlon

HERE = Path(__file__).resolve().parent
LEDGER = Path('/srv/bulk/leo/research/ds24-movement-policy-r01/cohort_ledger.json')
SITES = ((-4., 3.), (4., -3.))
SEEDS = (2026102511, 2026102512)
ARMS = ('c0', 'fitted_c')
VARIANTS = ('noiseless_null', 'stochastic_seed0', 'stochastic_seed1')
PROTOCOL = HERE / 'protocol.json'
H = .01


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def select_cases():
    rows = [row for row in r.read(LEDGER)['rows']
            if row['eligible'] and row['mode'] == 'fast'
            and row['case'] not in ('DS24-0095', 'DS24-0087')]
    return sorted(rows, key=lambda row: (row['captured_utc_ns'], row['case']))[:2]


@lru_cache(maxsize=2)
def context(case):
    if case not in [row['case'] for row in select_cases()]:
        raise ValueError('case outside metadata-frozen first-two cohort')
    return r.context(case)


def array_digest(rows):
    digest = hashlib.sha256()
    for oid, value in sorted(rows):
        digest.update(str(oid).encode()); digest.update(b'\0')
        digest.update(np.asarray(value, dtype='<f8').tobytes())
    return digest.hexdigest()


def observations_digest(scan, members):
    return array_digest((oid, value) for i in sorted(members)
        for oid, value in zip(scan.tracks[i]['observation_ids'], scan.tracks[i]['values'], strict=True))


def build(d, scan, node, entries, arm, reference):
    p = make_event_problem(scan, node, d['keep'], arm, np.asarray(reference),
        d['powers'], d['means'], d['model'], [])
    attach_event_predictive(p, entries, d['powers'])
    return cached(p)


def truth_components(d, site, variant, site_index):
    p = make_event_problem(d['scan'], d['node'], d['keep'], 'c0',
        d['means'], d['powers'], d['means'], d['model'], [])
    means = np.asarray(d['means'])
    if not np.isfinite(means).all() or np.any(abs(means) > 15):
        raise ValueError('original causal phase location outside operational +/-15s domain')
    widths = (p.hardware.shape[1], p.smooth.shape[1], len(p.labels),
              3 * len(p.supported), len(p.members))
    coefficient = np.zeros(sum(widths))
    phases = means.copy()
    child_seeds = None
    if variant != 'noiseless_null':
        seed = SEEDS[int(variant[-1])]
        children = np.random.SeedSequence([seed, int(d['case'].split('-')[1]), site_index]).spawn(4)
        child_seeds = [int(child.generate_state(1)[0]) for child in children]
        rng = np.random.Generator(np.random.PCG64(child_seeds[0]))
        coefficient = rng.normal(size=sum(widths))
        begin = widths[0] + widths[1]
        coefficient[begin:begin + widths[2]] = 0. # phase is propagated directly
        coefficient[-widths[4]:] *= .3 # design constants are 1000Hz: SD300Hz
        phases = bounded_phase_draw(means, p.phase_sigma, d['model']['nu'], rng.uniform(size=len(means)))
    law = norm() if d['model']['nu'] is None else t(d['model']['nu'],
        scale=np.sqrt((d['model']['nu'] - 2) / d['model']['nu']))
    mass = law.cdf((15 - means) / p.phase_sigma) - law.cdf((-15 - means) / p.phase_sigma)
    return p, dict(coordinate_widths=widths, selected_coefficients=coefficient,
        true_phases_s=phases, original_phase_locations_s=means,
        original_phase_marginal_sd_s=p.phase_sigma, phase_nu=d['model']['nu'],
        phase_domain_s=[-15., 15.], original_phase_mass_removed=1-mass,
        original_phase_locations_within_domain=True, seed_children=child_seeds,
        c_truth=0., artificial_position_east_north_km=site)


def synthesize(d, site_index, variant):
    site = np.asarray(SITES[site_index])
    original_members = set(d['base'].members) | {entry['track_index'] for entry in d['entries']}
    before = observations_digest(d['scan'], original_members)
    nominal, truth = truth_components(d, site, variant, site_index)
    phases = np.asarray(truth['true_phases_s'])
    scan, node, entries, reconstruction = generate(d['scan'], d['node'], d['base'],
        phases, d['entries'], site)
    p = make_event_problem(scan, node, d['keep'], 'c0', phases,
        d['powers'], d['means'], d['model'], [])
    geometry = geometry_features(p, site, 0.)
    coefficient = np.asarray(truth['selected_coefficients'])
    delta = geometry['features'] @ coefficient
    expected = {}
    for index, (i, sl) in enumerate(zip(p.members, p.slices, strict=True)):
        raw = p.q[sl] * geometry['frequency'][sl] + delta[sl]
        scan.tracks[i]['values'], node['aliases'][index] = alias_encode(raw)
        expected[i] = raw
    if entries:
        view, _, _, groups, slices = linear_geometry(p, entries)
        g = geometry_features(view, site, 0.)
        prediction = view.q * g['frequency'] + g['features'] @ coefficient
        fragment_rng = np.random.default_rng(truth['seed_children'][2]) if truth['seed_children'] else None
        bias = fragment_rng.normal(0, 300., len(entries)) if fragment_rng else np.zeros(len(entries))
        truth['predictive_fragment_bias_hz'] = bias
        for entry, sl in zip(entries, slices, strict=True):
            raw = prediction[sl] + bias[groups[sl]]
            scan.tracks[entry['track_index']]['values'], entry['alias'] = alias_encode(raw)
            expected[entry['track_index']] = raw
    sigma, unit_noise = measurement_noise(scan, original_members, 1.,
        truth['seed_children'][1] if truth['seed_children'] else 0)
    if truth['seed_children']:
        rng = np.random.default_rng(truth['seed_children'][3])
        precision = {i: float(rng.gamma(2., .5)) for i in sorted(original_members)}
        noise = {oid: unit_noise[oid] / np.sqrt(precision[i]) for i in sorted(original_members)
                 for oid in scan.tracks[i]['observation_ids']}
    else:
        precision = {i: 1. for i in sorted(original_members)}
        noise = {oid: 0. for oid in sigma}
    add_noise(scan, original_members, noise)
    maximum_error = reconstruction
    for k, (i, sl) in enumerate(zip(p.members, p.slices, strict=True)):
        track = scan.tracks[i]
        actual = track['values'] + node['aliases'][k] * PERIOD
        predicted = expected[i] + np.asarray([noise[oid] for oid in track['observation_ids']])
        maximum_error = max(maximum_error, float(np.max(abs(actual - predicted))))
    for entry in entries:
        track = scan.tracks[entry['track_index']]
        actual = track['values'] + entry['alias'] * PERIOD
        predicted = expected[entry['track_index']] + np.asarray([noise[oid] for oid in track['observation_ids']])
        maximum_error = max(maximum_error, float(np.max(abs(actual - predicted))))
    assert maximum_error < 1e-7
    assert observations_digest(d['scan'], original_members) == before
    truth.update(noise_precision_by_track=precision, noise_sigma_by_ID=sigma,
        actual_noise_by_ID=noise, maximum_forward_identity_error_hz=maximum_error,
        original_observations_unchanged=True,
        observations_sha256=observations_digest(scan, original_members),
        original_observations_sha256=before,
        native_observation_IDs=sorted(sigma), selected_labels=list(p.labels),
        supported_shape_families=list(p.supported),
        curved_aliases=node['aliases'], predictive_aliases=[entry['alias'] for entry in entries],
        inference_powers=d['powers'], inference_model=d['model'])
    return scan, node, entries, truth


def objective_terms(p, x):
    c = p.calculate(np.asarray(x))
    parent = p.curved_calculate(np.asarray(x)) if getattr(p, 'linear_entries', []) else c
    keys = ('negative_twice_elbo', 'normalization_constant', 'weighted_residual_cost',
            'quadratic', 'logvolume', 'gamma_cost', 'noise_gamma_cost', 'prior_gamma_cost',
            'mean_prior_cost', 'logdet_cost', 'prior_penalty')
    values = {key: parent[key] for key in keys if key in parent}
    residual = p.residual(np.asarray(x))
    values.update(total_negative_twice_elbo=c['negative_twice_elbo'],
        parent_negative_twice_elbo=parent['negative_twice_elbo'],
        predictive_objective=c.get('linear_predictive_objective', 0.),
        optimizer_scalar=float(residual @ residual),
        parent_conditional_RMS_hz=float(np.sqrt(np.mean(parent['conditional_residual_hz'][p.keep] ** 2))),
        final_log_precision_change=c['final_log_precision_change'])
    gradient = []
    for axis in range(2):
        step = np.zeros(2); step[axis] = H
        gradient.append(float((p.calculate(np.asarray(x) + step)['negative_twice_elbo']
            - p.calculate(np.asarray(x) - step)['negative_twice_elbo']) / (2 * H)))
    values['objective_gradient_per_km'] = gradient
    values['parent_decomposition_closure'] = float(parent['negative_twice_elbo']
        - parent['quadratic'] - parent['logvolume'] - parent['gamma_cost']
        - parent['normalization_constant'])
    latent = parent['latent_coefficient']
    values['parent_latent_mean_prior_energy'] = float(np.sum(latent ** 2 * parent['coefficient_prior_precision']))
    values['parent_weighted_residual_energy'] = parent['quadratic'] - values['parent_latent_mean_prior_energy']
    return values


def known_forward_closure(p, x, truth):
    geometry = geometry_features(p, x, 0.)
    coefficient = np.asarray(truth['selected_coefficients']).copy()
    if p.fitted_c:
        coefficient = np.insert(coefficient, 8, 0.)
    begin = p.hardware.shape[1] + p.smooth.shape[1]
    coefficient[begin:begin + len(p.labels)] = np.asarray(truth['true_phases_s']) / p.phase_sigma
    exact = p.q * geometry['intercept'] + geometry['features'] @ coefficient
    noise = np.array([truth['actual_noise_by_ID'][oid] for i in p.members
                     for oid in p.scan.tracks[i]['observation_ids']])
    error = float(np.max(abs(p.values - exact - noise)))
    if error > 1e-7:
        raise ValueError('known forward mean identity failed: '+str(error))
    return dict(maximum_known_forward_mean_identity_error_hz=error,
        actual_truth_residual_RMS_hz=float(np.sqrt(np.mean((p.values - exact)[p.keep] ** 2))),
        supplied_noise_RMS_hz=float(np.sqrt(np.mean(noise[p.keep] ** 2))))


def final_checks(p, x, result):
    state = p.state(x)
    maximum = float(np.max(abs(np.asarray(state['phases']))))
    original = bool(r.valid({arm: result for arm in ARMS}))
    return dict(original_single_arm_valid=original,
        absolute_unclipped_posterior_phase_max_s=maximum,
        phase_converged=result['final_phase_change_s'] <= .01,
        Gamma_converged=p.calculate(x)['final_log_precision_change'] <= 1e-5,
        passed=bool(original and maximum <= 15.000001 and result['final_phase_change_s'] <= .01
                    and p.calculate(x)['final_log_precision_change'] <= 1e-5))


def one_fit(case, site_index, variant, arm, deadline_ns):
    began = time.monotonic()
    directory = HERE / 'fits' / case / f'site{site_index}' / variant / arm
    history = []
    try:
        duration = min(180., (deadline_ns - time.time_ns()) / 1e9)
        if duration <= 0: raise TimeoutError('1200s global budget exhausted before fit')
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('180s fit or1200s batch budget')))
        signal.setitimer(signal.ITIMER_REAL, duration)
        d = context(case)
        scan, node, entries, truth = synthesize(d, site_index, variant)
        r.write_new(directory / 'generation.json', truth)
        reference = np.zeros(len(d['means'])); x = np.zeros(2)
        for epoch in range(5):
            p = build(d, scan, node, entries, arm, reference)
            fitted = fit(p, x, iterations=48); x = np.asarray(fitted['parameters'])
            absolute_phase = p.state(x)['phases'][p.labels]
            next_reference = np.clip(absolute_phase, -15, 15)
            record = dict(epoch=epoch, fit=fitted, parent_phase_reference=reference,
                posterior_absolute_phase_s=absolute_phase,
                phase_change_s=float(np.max(abs(next_reference - reference))))
            r.write_new(directory / f'round{epoch}.json', record)
            history.append(record); reference = next_reference
        result = summary(p, x, entries)
        result.update(final_phase_change_s=history[-1]['phase_change_s'], history=history)
        r.write_new(directory / 'raw_endpoint.json', result)
        target = np.asarray(SITES[site_index])
        fixed = dict(endpoint_at_final_reference=objective_terms(p, x),
            truth_at_final_reference=objective_terms(p, target),
            origin_at_final_reference=objective_terms(p, np.zeros(2)))
        true_phase_problem = build(d, scan, node, entries, arm, truth['true_phases_s'])
        fixed['truth_at_true_phase_reference'] = objective_terms(true_phase_problem, target)
        fixed['known_forward_closure'] = known_forward_closure(true_phase_problem, target, truth)
        active_labels = np.unique(p.flat_labels[p.keep])
        phase = p.state(x)['phases'][p.labels]
        result.update(status='complete', case=case, arm=arm, site_index=site_index, variant=variant,
            synthetic_position_error_km=float(np.linalg.norm(x - target)),
            artificial_position_east_north_km=target,
            observations_sha256=truth['observations_sha256'],
            active_phase_RMSE_s=float(np.sqrt(np.mean((phase[active_labels] - np.asarray(truth['true_phases_s'])[active_labels]) ** 2))),
            fixed_objective_diagnostics=fixed, qualification=final_checks(p, x, result),
            declared_truth_higher_loss_than_endpoint_at_final_reference=float(
                fixed['truth_at_final_reference']['total_negative_twice_elbo']
                - fixed['endpoint_at_final_reference']['total_negative_twice_elbo']),
            seconds=time.monotonic() - began, real_GPS_used=False,
            labels_and_aliases_known_by_construction=True, association_selection_tested=False)
    except Exception as exc:
        result = dict(status='failed', case=case, arm=arm, site_index=site_index, variant=variant,
            error=repr(exc), traceback=traceback.format_exc(), completed_rounds=len(history),
            raw_endpoint_preserved=(directory / 'raw_endpoint.json').exists(),
            seconds=time.monotonic() - began, real_GPS_used=False)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    r.write_new(directory / 'result.json', result)
    print(case, site_index, variant, arm, result['status'], round(result['seconds'], 3),
        result.get('synthetic_position_error_km', result.get('error')), flush=True)
    return result


def freeze():
    selection = select_cases()
    assert [row['case'] for row in selection] == ['DS24-0010', 'DS24-0011']
    inputs = {str(LEDGER): sha(LEDGER)}
    for row in selection:
        files = [row['baseline']] + row['frozen_scan_files']
        for record in files:
            assert sha(record['path']) == record['sha256']
            inputs[record['path']] = record['sha256']
        for suffix in ('.json', '_forecast.json'):
            path = r.SOURCE / 'causal_phase_history' / (row['case'] + suffix)
            inputs[str(path)] = sha(path)
        context(row['case']) # validates causal inputs, without any position fit
    sources = {str(Path(module.__file__).resolve()): sha(module.__file__)
        for module in list(sys.modules.values()) if getattr(module, '__file__', None)
        and str(module.__file__).endswith('.py')
        and (str(Path(module.__file__).resolve()).startswith(str(r.REPO))
             or str(Path(module.__file__).resolve()).startswith('/srv/bulk/leo/research/ds24-movement-policy-r01/recovery'))}
    sources[str(Path(__file__))] = sha(__file__)
    sources[str(HERE / 'test_experiment.py')] = sha(HERE / 'test_experiment.py')
    protocol = dict(version='fast conditional synthetic r01', cases=[row['case'] for row in selection],
        selection='first2eligible fast DS24 bycaptured_utc_ns,case;exclude0095/0087;metadata only',
        metadata=[{key: row[key] for key in ('case', 'captured_utc_ns', 'recording_id')} for row in selection],
        artificial_sites_east_north_km=SITES, seeds=SEEDS, seed_rule='SeedSequence([seed,case_number,site_index]).spawn(4); each child generate_state(1)[0] seeds PCG64:latent,noise,fragment,precision',
        variants=VARIANTS, arms=ARMS, maximum_position_fits=24, per_fit_seconds=180,
        global_scientific_seconds=1200, workers=2, BLAS_threads=1,
        phase_rounds=5, iterations_per_round=48, cold_start=[0., 0.],
        regional_center_latlon=[37.906, -122.545], box_width_km=25., c_truth=0.,
        null='exact bank nonlinear phase at causal mean;all other coefficients/noise0;positive original inference noise/priors retained',
        stochastic='phase unit-marginal Normal/Student conditioned[-15,15]; original Gaussian radio/smooth/3shape scales;300Hzsource constants; percurveGamma(2,2)precision and Gaussian conditional noise',
        physical_orbit='linear original3 engineering modes evaluated at true phase and site; not nonlinear perturbed orbit propagation',
        inferred_model_limits='unchanged inherited likelihood powers; parentVI/phase linearization and unseen predictive Gaussian moment approximation; not full generative SBC',
        labels_masks_aliases_and_point_selection='known/inherited byconstruction; no association or selection benchmark',
        association_entrypoints_reviewed=['run_dsx01_clean_region.fresh_discovery', 'evaluate_ds23_phase_refreshed.fit_case', 'probe_ds23_predictive_linear.select_entries'],
        selection_not_run_reason='24fits allocated to null/stochastic c pairs; full raw/clutter source generation and cached discovery groups not reconstructed; no mixed real/synthetic selection claim',
        no_retry_rescue_or_new_RF=True, real_GPS_used=False,
        input_sha256=inputs, source_sha256=sources, environment=dict(numpy=np.__version__, scipy=scipy.__version__),
        fixed_diagnostics='at truth/endpoint/origin under finalphase ref plus truth under truephase ref;objective decomposition and h=.01km gradients;forwardidentity preserved')
    r.write_new(PROTOCOL, protocol)
    r.write_new(HERE / 'protocol_seal.json', dict(protocol_sha256=sha(PROTOCOL)))
    print('FROZEN', sha(PROTOCOL), flush=True)


def verify():
    protocol = r.read(PROTOCOL)
    assert sha(PROTOCOL) == r.read(HERE / 'protocol_seal.json')['protocol_sha256']
    for key in ('input_sha256', 'source_sha256'):
        for path, expected in protocol[key].items():
            assert sha(path) == expected, path
    return protocol


def run():
    protocol = verify()
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        assert r.os.environ.get(name) == '1'
    started = time.time_ns(); deadline = started + int(1200e9)
    tasks = [(case, site, variant, arm) for variant in VARIANTS
             for case in protocol['cases'] for site in range(2) for arm in ARMS]
    assert len(tasks) == 24
    r.write_new(HERE / 'execution_start.json', dict(started_utc_ns=started,
        deadline_utc_ns=deadline, protocol_sha256=sha(PROTOCOL), jobs=tasks))
    rows = []
    with ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context('spawn')) as pool:
        futures = [pool.submit(one_fit, *task, deadline) for task in tasks]
        for future in as_completed(futures):
            rows.append(future.result())
    verify()
    for case in protocol['cases']:
        for site in range(2):
            for variant in VARIANTS:
                pair = [row for row in rows if row['case'] == case and row['site_index'] == site and row['variant'] == variant]
                if all(row['status'] == 'complete' for row in pair):
                    assert len({row['observations_sha256'] for row in pair}) == 1
    result = dict(status='terminal', attempted_fits=len(rows), maximum_fits=24,
        completed=sum(row['status'] == 'complete' for row in rows),
        failed=sum(row['status'] != 'complete' for row in rows), rows=rows,
        seconds=(time.time_ns() - started) / 1e9, protocol_sha256=sha(PROTOCOL),
        real_GPS_used=False, association_selection_tested=False)
    r.write_new(HERE / 'execution.json', result)
    files = sorted((HERE / 'fits').rglob('*.json')) + [PROTOCOL, HERE / 'protocol_seal.json',
        HERE / 'execution_start.json', HERE / 'execution.json']
    r.write_new(HERE / 'scientific_seal.json', dict(protocol_sha256=sha(PROTOCOL),
        files={str(path): sha(path) for path in files}, all_attempts_terminal=True,
        real_GPS_used=False, association_selection_tested=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, choices=('freeze', 'run'))
    {'freeze': freeze, 'run': run}[parser.parse_args().stage]()
