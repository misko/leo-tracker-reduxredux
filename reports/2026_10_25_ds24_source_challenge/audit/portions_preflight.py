"""Lean independent nomination preflight: real input closure and dense fixture."""
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

HERE = Path(__file__).resolve().parent
PORT = HERE.parent / 'portions'
sys.path.insert(0, str(PORT))
import nominate as n

read = lambda path: json.loads(Path(path).read_bytes())
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    began = time.monotonic(); checks = []
    def check(name, passed, **details):
        checks.append(dict(name=name, passed=bool(passed), **details))
    protocol = read(PORT / 'protocol.json'); digest = sha(PORT / 'protocol.json')
    check('all frozen scientific and input bindings exact',
          all(sha(path) == h for path, h in protocol['source_input_hashes'].items()),
          bindings=len(protocol['source_input_hashes']))
    smoke = read(PORT / 'load_smoke.json')
    check('actual both-arm input smoke passes before any ordinary screen',
          smoke['all_passed'] and smoke['ordinary_screens'] == 0 and
          smoke['source_sha256'] == sha(PORT / 'nominate.py') and
          smoke['per_ID_mean_elevation_reconstructed'] and smoke['original_nominal_frequency_cache_exact'] and
          {row['arm'] for row in smoke['checks']} == {'c0', 'fitted_c'} and
          not (PORT / 'execution_started.json').exists())
    check('all6 fixed portions plus whole control, original catalogue and finite budget',
          protocol['cuts'] == [14, 21, 29] and protocol['screen_contexts'] == 14 and
          protocol['catalogue_entries'] == 1487 and protocol['shortlist'] == 8 and
          protocol['numeric_cap_seconds'] == 180 and protocol['workers'] <= 2 and
          protocol['BLAS_threads'] == 1 and protocol['scientific_retries'] == protocol['position_fits'] == 0 and
          not protocol['GPS_used'] and not protocol['forced_candidates'] and protocol['no_new_response_selected_cavity'] and
          protocol['remaining_numeric_seconds'] == 180 - protocol['preparation_numeric_seconds'])
    catalogue = n.arrays(PORT / 'inputs/catalogue.npz')
    positions = []
    for arm in ('c0', 'fitted_c'):
        actual = n.arrays(PORT / 'inputs' / (arm + '.npz'))
        original = n.arrays(n.COHERENCE / 'run02' / arm / 'inputs.npz')
        use = np.arange(57, 100)
        checks_exact = all(np.array_equal(actual[name], original[source][use]) for name, source in
            [('raw_hz', 'raw_hz'), ('native_ids', 'native_ids'), ('times_s', 'times_s'), ('q', 'native_q')])
        checks_exact &= np.array_equal(actual['covariance_hz2'], original['covariance_hz2'][np.ix_(use, use)])
        checks_exact &= np.allclose(actual['native_values_hz'] - actual['graph_values_hz'], 2 * n.k.PERIOD, atol=1e-7, rtol=0)
        check(arm + ': archived IDs/raw/C/q/time and native gauge exact', checks_exact)
        positions.append(actual['common_position_east_north_km'])
    check('common saved c0 RF position and complete per-ID visibility catalogue',
          np.array_equal(*positions) and catalogue['frequency_hz'].shape == catalogue['mean_elevation_deg'].shape == (1487, 43))
    status = pytest.main(['-q', '-p', 'no:cacheprovider', str(PORT / 'test_nominate.py')])
    signal.setitimer(signal.ITIMER_REAL, 0)
    check('nine component-owned controls independently rerun', status == 0)
    rng = np.random.default_rng(202610260301)
    rows, points = 13, 9
    latent = rng.normal(size=(points, 3)); covariance = np.diag(np.linspace(5., 20., points)) + latent @ latent.T
    frequency = rng.normal(size=(rows, points)) * 70
    derivative = rng.normal(size=(rows, points)) * 8
    sd = np.linspace(.3, 3., rows)
    cat = dict(norads=np.arange(90001, 90001 + rows), frequency_hz=frequency, derivative_hz_per_s=derivative,
        phase_means_s=np.linspace(-3, 3, rows), phase_sd_s=sd, minimum_mean_elevation_deg=np.ones(rows))
    raw = rng.normal(size=points) * 15
    actual = n.screen(raw, covariance, cat)
    differences = []
    for j in range(rows):
        phase = sd[j] * derivative[j]
        full = covariance + np.outer(phase, phase)
        root = np.linalg.cholesky(full)
        residual = raw + actual['coarse_aliases'][j][0] * n.k.PERIOD - frequency[j]
        white = solve_triangular(root, residual, lower=True)
        score = white @ white + 2 * np.log(np.diag(root)).sum() + points * np.log(2 * np.pi)
        differences.append(abs(score - actual['coarse_scores'][j]))
    check('independent dense normalized rank-one Gaussian matches ordinary score', max(differences) < 1e-8,
          maximum_objective_error=max(differences))
    check('screen has no truth/reserve port and source/input bytes remain exact',
          list(inspect.signature(n.screen).parameters) == ['raw', 'covariance', 'catalogue'] and
          not actual['forced_or_reserved_candidate'] and not actual['accepted'] and
          all(sha(path) == h for path, h in protocol['source_input_hashes'].items()))
    seconds = time.monotonic() - began
    result = dict(all_passed=all(row['passed'] for row in checks) and seconds <= 180,
        protocol_sha256=digest, checks=checks, seconds=seconds, source_sha256=sha(__file__),
        audit_numeric_cap_seconds=180, corpus_propagation_calls=0, corpus_CFO_screens=0, position_fits=0,
        geographic_truth_read=False,
        scope='14 ordinary coarse nomination contexts only; no exact identity evidence, partial acceptance, second-source fit or position claim.')
    with (HERE / 'preflight.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps(dict(all_passed=result['all_passed'], protocol_sha256=digest, seconds=seconds,
        failed=[row for row in checks if not row['passed']])))


if __name__ == '__main__':
    main()
