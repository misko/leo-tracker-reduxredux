"""Independent matching-law, near-null and real-context closure audit."""
import hashlib
import inspect
import json
from pathlib import Path
import signal
import sys
import time

import numpy as np
import pytest
from scipy.linalg import solve_triangular
from scipy.special import logsumexp
from scipy.stats import t

HERE = Path(__file__).resolve().parent
LAW = HERE.parent / 'matched_law'
sys.path.insert(0, str(LAW))
import control as c

read = lambda path: json.loads(Path(path).read_bytes())
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()


def truncated_student_moments(location, sd):
    scale = sd / np.sqrt(3.)
    a, b = (-15 - location) / scale, (15 - location) / scale
    mass = t.cdf(b, 3) - t.cdf(a, 3)
    first = ((3 + a * a) * t.pdf(a, 3) - (3 + b * b) * t.pdf(b, 3)) / (2 * mass)
    second = (6 * (t.cdf(b / np.sqrt(3.), 1) - t.cdf(a / np.sqrt(3.), 1)) - 3 * mass) / mass
    return location + scale * first, scale * scale * (second - first * first)


def main():
    start = time.monotonic(); checks = []; detail = []
    def check(name, passed, **more):
        checks.append(dict(name=name, passed=bool(passed), **more))
    protocol = read(LAW / 'protocol.json'); digest = sha(LAW / 'protocol.json')
    check('exact final protocol and every source/input binding',
          digest == '8afa3e694ae5e2b6a5d12069a57ca41bf9be576eced8c282c5e93e01cfb821f6' and
          all(sha(path) == h for path, h in protocol['files'].items()), bindings=len(protocol['files']))
    preparation = read(LAW / 'preparation.json')
    check('both actual context smokes before synthetic observations and no budget reset',
          preparation['actual_context_smoke_passed'] and preparation['no_generated_vectors'] and
          len(preparation['rows']) == 2 and not (LAW / 'execution_started.json').exists() and
          protocol['maximum_scientific_worker_seconds'] == 600 and protocol['workers'] == 2 and
          protocol['BLAS_threads'] == 1 and protocol['preparation_seconds'] + protocol['test_seconds'] < 600)
    check('same-data c ablation has exact-law claim only for c0',
          protocol['c0_only_matching_law'] and protocol['fitted_c_same_vector_off_law_sensitivity'] and
          protocol['total_vectors'] == 6 and protocol['physical_vectors'] == 4 and protocol['null_vectors'] == 2 and
          protocol['position_fits'] == 0 and not protocol['GPS_used'] and protocol['operational_association_rule'] is None)
    for case in ('DS24-0010', 'DS24-0011'):
        meta = read(LAW / case / 'context.json')
        frozen = next(row for row in protocol['prepared'] if row['case'] == case)
        check(case + ': frozen metadata, arrays and response-free design before draws',
              sha(LAW / case / 'context.npz') == frozen['context_sha256'] == meta['context_sha256'] and
              sha(LAW / case / 'context.json') == frozen['metadata_sha256'] and
              meta['no_synthetic_CFO_generated'] and meta['background_fixed_before_every_hypothetical_label'] and
              meta['historically_response_selected_layout'])
        with np.load(LAW / case / 'context.npz') as saved:
            data = {key: saved[key].copy() for key in saved.files}
        oldmeta = read(c.PREVIOUS / case / 'context.json')
        with np.load(c.PREVIOUS / case / 'context.npz') as old:
            check(case + ': original layout IDs/times/RF and c0 exogenous background exact',
                  np.array_equal(data['native_ids'], old['native_ids']) and np.array_equal(data['times_s'], old['times_s']) and
                  np.array_equal(data['q'], old['q']) and np.array_equal(data['position_east_north_km'], oldmeta['fixed_position_east_north_km']) and
                  np.array_equal(data['c0_radio_mean_Hz'], old['radio_mean_hz']) and
                  np.array_equal(data['c0_covariance_Hz2'], old['conditional_covariance_hz2']))
        full = meta['full_visible_generators']; selected = meta['pair_indices']
        absent = set(oldmeta['original_parent_families'])
        full_support = all(meta['all_generator_support'][str(int(data['norads'][j]))]['certified'] and
            meta['all_generator_support'][str(int(data['norads'][j]))]['inner_visible_intervals'] == [[-15., 15.]] and
            not meta['all_generator_support'][str(int(data['norads'][j]))]['root_brackets'] for j in full)
        check(case + ': generator pool excludes parent families and has full-domain nominal support',
              full_support and not set(full) & absent and len(selected) == 2 and set(selected) <= set(full) and
              data['norads'][selected].tolist() == meta['pair_norads'])
        j, k = selected
        delta = data['frequency_hz'][j] - data['frequency_hz'][k]
        phase = data['derivative_hz_per_s'] * data['phase_sd_s'][:, None]
        pair_covariance = data['c0_covariance_Hz2'] + .5 * (np.outer(phase[j], phase[j]) + np.outer(phase[k], phase[k]))
        root = np.linalg.cholesky(pair_covariance)
        white = solve_triangular(root, delta, lower=True)
        pair_metric = float(white @ white)
        check(case + ': independent dense pair-distance metric', abs(pair_metric - meta['pair_metric']) < 1e-6,
              dense_metric=pair_metric, recorded_metric=meta['pair_metric'])
        q = data['null_Q']; n = len(data['times_s'])
        fa, fb = data['pair_frequencies_Hz']
        S = .25 * np.outer(fa - fb, fa - fb)
        moments = []
        for i, law in enumerate(meta['selected_phase_laws']):
            mean, variance = truncated_student_moments(law['location'], law['original_marginal_SD'])
            moments.append(dict(norad=law['norad'], mean=mean, variance=variance))
            check(case + ': analytic truncated Student moments ' + str(law['norad']),
                  abs(mean - law['conditioned_mean']) < 1e-8 and abs(variance - law['conditioned_variance']) < 1e-8 and
                  abs(variance - data['pair_phase_variances'][i]) < 1e-8)
            derivative = data['pair_derivatives_Hz_s'][i]
            modes = data['pair_modes_Hz'][i]
            S += .5 * (variance * np.outer(derivative, derivative) + modes @ modes.T)
        floor = n / 5 * float(np.median(data['native_sigma_Hz'])) ** 2
        coefficient_covariance = q.T @ S @ q + floor * np.eye(5)
        reconstructed = q @ coefficient_covariance @ q.T
        actual = data['null_factor_Hz'] @ data['null_factor_Hz'].T
        scale = max(1., float(np.max(abs(reconstructed))))
        check(case + ': proper local-affine null projection, native-noise roughness and midpoint',
              np.allclose(q.T @ q, np.eye(5), atol=1e-12, rtol=0) and
              np.linalg.eigvalsh(coefficient_covariance).min() > 0 and
              np.max(abs(data['null_coefficient_covariance'] - coefficient_covariance)) <= 1e-8 * scale and
              np.max(abs(actual - reconstructed)) <= 1e-8 * scale and
              np.array_equal(data['null_mean_Hz'], (fa + fb) / 2), maximum_relative_covariance_error=float(np.max(abs(actual - reconstructed)) / scale))
        for arm in ('c0', 'fitted_c'):
            covariance = data[arm + '_covariance_Hz2']
            check(case + ': ' + arm + ' finite positive fixed background',
                  np.isfinite(covariance).all() and np.linalg.eigvalsh(covariance).min() > 0 and np.all(data['q'] > 0))
        detail.append(dict(case=case, pair=meta['pair_norads'], pair_metric=pair_metric, phase_moments=moments,
            layout_points=n, null_is_local_affine_design_not_nonlinear_moment_match=True))
    status = pytest.main(['-q', '-p', 'no:cacheprovider', str(LAW / 'test_control.py')])
    signal.setitimer(signal.ITIMER_REAL, 0)
    check('six owned tests including actual generation and screen wrapper ports rerun', status == 0)
    rng = np.random.default_rng(202610260515)
    n = 12; background = np.diag(np.linspace(3., 14., n)); factor = rng.normal(size=(n, 5)) * 2
    mean = rng.normal(size=n); raw = rng.normal(size=n) * 3
    covariance = background + factor @ factor.T
    root = np.linalg.cholesky(covariance)
    logs = []
    for alias in range(-4, 5):
        white = solve_triangular(root, raw - mean + alias * c.lm.PERIOD, lower=True)
        logs.append(-.5 * (white @ white + 2 * np.log(np.diag(root)).sum() + n * np.log(2 * np.pi)))
    oracle = -2 * (logsumexp(logs) - np.log(9))
    actual = c.lm.gaussian_score(raw, background, mean, factor)[0]
    reference = c.lm.gaussian_qr_score(raw, background, mean, factor)
    check('independent normalized9-alias Gaussian-null density oracle',
          abs(actual - oracle) < 1e-8 and abs(reference - oracle) < 1e-8, maximum_objective_error=max(abs(actual - oracle), abs(reference - oracle)))
    source = (LAW / 'control.py').read_text()
    check('no response-selected conditioning or truth supplied to ordinary screen',
          'k.cavity(' not in source and list(inspect.signature(c.ordinary_screen).parameters) == ['observation', 'catalogue'] and
          'ordinary_shortlist_unchanged=True' in source and 'label_available_only.json' in source and
          'nominal/mode bank grids differ' in source and all(sha(path) == h for path, h in protocol['files'].items()))
    seconds = time.monotonic() - start
    prior_seconds = read(HERE / 'portions_terminal.json')['cumulative_audit_seconds']
    result = dict(all_passed=all(row['passed'] for row in checks) and seconds + prior_seconds <= 180,
        protocol_sha256=digest, checks=checks, context_checks=detail, seconds=seconds,
        cumulative_audit_seconds=seconds + prior_seconds, source_sha256=sha(__file__),
        corpus_propagation_calls=0, new_synthetic_scientific_vectors=0, position_fits=0, geographic_truth_read=False,
        scope='Exact c0 exogenous conditional generator/scorer control; original screen approximate. Fitted-c same-vector off-law sensitivity. No full shared-family, GLRT-selection or identity-rate calibration.')
    with (HERE / 'matched_law_preflight.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps(dict(all_passed=result['all_passed'], protocol_sha256=digest, seconds=seconds,
        failed=[row for row in checks if not row['passed']], context_checks=detail)))


if __name__ == '__main__':
    main()
