"""Read sealed fits, benchmark exact kernels, profile one fixed scan state.

No optimizer, receiver truth, new orbit propagation, or RF collection is used.
Run with OPENBLAS_NUM_THREADS=1 PYTHONPATH=src .venv/bin/python PATH/diagnose.py.
"""
from __future__ import annotations

import cProfile
import hashlib
import json
import os
from pathlib import Path
import platform
import pstats
import sys
import time

import numpy as np

from kernels import collapsed_white_logpdf

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "2026_10_01_fixed_height_greedy"


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def sealed(path):
    expected = json.loads(path.with_suffix('.seal.json').read_text())["prediction_sha256"]
    if digest(path) != expected:
        raise ValueError(f"seal mismatch: {path}")
    return json.loads(path.read_text())


def ambiguity():
    rows = []
    for path in sorted((OLD / "runs/t4-primary").glob("batch-*/*-joint.json")):
        receipt = sealed(path)
        fits = sorted((f for f in receipt['fits'] if f['objectives']),
                      key=lambda f: f['objectives'][-1])
        if len(fits) < 2:
            raise ValueError("fewer than two scored fits")
        xy = np.array([f['mean'][:2] for f in fits])
        rows.append(dict(unit_id=receipt['unit_id'], receipt_sha256=digest(path),
            gap=fits[1]['objectives'][-1] - fits[0]['objectives'][-1],
            best_second_distance_km=float(np.linalg.norm(xy[0] - xy[1])),
            max_distance_km=float(np.linalg.norm(xy[:, None] - xy[None], axis=2).max()),
            best_converged=fits[0]['converged'], second_converged=fits[1]['converged']))
    return dict(count=len(rows),
        close_scores_far_any_pair=sum(r['gap'] < 1 and r['max_distance_km'] > 100 for r in rows),
        close_scores_far_best_second=sum(r['gap'] < 1 and r['best_second_distance_km'] > 100 for r in rows),
        close_scores_far_best_second_both_converged=sum(r['gap'] < 1 and r['best_second_distance_km'] > 100
            and r['best_converged'] and r['second_converged'] for r in rows), rows=rows)


def benchmark():
    rng = np.random.default_rng(9911)
    n, m = 300, 24
    u, y = rng.normal(size=(n, m)), rng.normal(size=n)

    def dense():
        covariance = np.eye(n) + u @ u.T
        chol = np.linalg.cholesky(covariance)
        white = np.linalg.solve(chol, y)
        return -.5 * (white @ white + 2 * np.log(np.diag(chol)).sum() + n * np.log(2 * np.pi))

    values, times = {}, {}
    for name, fn in [('dense', dense), ('collapsed', lambda: collapsed_white_logpdf(y, u))]:
        values[name] = float(fn())
        timings = []
        for _ in range(15):
            start = time.perf_counter()
            fn()
            timings.append(time.perf_counter() - start)
        times[name] = float(np.median(timings))
    assert abs(values['dense'] - values['collapsed']) < 1e-9
    return dict(rows=n, nuisance_dimensions=m, seed=9911, repetitions=15,
                logpdf=values, median_seconds=times, ratio=times['dense']/times['collapsed'],
                qualification='synthetic prewhitened kernel only; not a scan runtime improvement')


def profile_scan():
    sys.path.insert(0, str(OLD))
    sys.path.insert(0, str(HERE.parent / '2026_09_30_broad_prior_acquisition'))
    from common import load_scan
    from orbit_input import use_extended_orbits
    from geoid import load_height_model
    from physics_fixed import build_fixed_height_factor
    from acquire import FixedHeightTrackLikelihood
    from leo.analysis.greedy_joint_location import _selected_log
    import physics
    import acquire
    import leo.analysis.greedy_joint_location as greedy

    path = OLD / 'runs/t4-primary/batch-01/DS9-F001-joint.json'
    receipt = sealed(path)
    fit = receipt['best']
    state = np.r_[fit['mean'], fit['satellite_epoch_s']]
    scan = use_extended_orbits(load_scan('DS9-F001'))
    height = load_height_model()
    factors = [build_fixed_height_factor(obs, scan.bank, scan.layout, scan.config, height).factor
               for _, obs in scan.tracks]
    ports = [FixedHeightTrackLikelihood(obs, scan.bank, scan.config, height, degrees_of_freedom=4)
             for _, obs in scan.tracks]
    labels = list(map(str, scan.bank.norad_ids)) + ['background']
    assigned = [labels.index(s) for s in fit['associations']]
    # This saved scan has no background selections; avoid comparing the Gaussian background adapter.
    assert all(i < len(scan.bank.norad_ids) for i in assigned)

    def score_all():
        return [port.branch_loglik_at_state(state) for port in ports]

    def selected_density():
        return [_selected_log(f, i, state, 4) for f, i in zip(factors, assigned, strict=True)]

    prof = cProfile.Profile()
    durations = {}
    for name, fn in [('all_candidate_scores', score_all), ('selected_density_with_jacobians', selected_density)]:
        prof.enable()
        start = time.perf_counter()
        result = fn()
        durations[name] = time.perf_counter() - start
        prof.disable()
        if name == 'all_candidate_scores':
            full = result
        else:
            np.testing.assert_allclose(result, [v[i] for v, i in zip(full, assigned, strict=True)], atol=1e-8)
    prof.dump_stats(str(HERE / 'fixed-state-profile.pstats'))
    with (HERE / 'fixed-state-profile.txt').open('w') as stream:
        pstats.Stats(prof, stream=stream).strip_dirs().sort_stats('cumulative').print_stats(25)

    shifted = state.copy()
    shifted[2] += .375
    shifted[5:] -= .375
    differences = []
    for port, expected in zip(ports, full, strict=True):
        actual = port.branch_loglik_at_state(shifted)
        assert np.array_equal(np.isfinite(actual), np.isfinite(expected))
        mask = np.isfinite(expected)
        differences.append(float(np.max(np.abs(actual[mask] - expected[mask]))))
    assert max(differences) < 1e-7
    source_files = [Path(m.__file__) for m in [physics, acquire, greedy]]
    source_files += [OLD / p for p in ['physics_fixed.py', 'geoid.py', 'orbit_input.py']]
    return dict(unit_id=scan.unit_id, tracks=len(factors), candidates=len(scan.bank.norad_ids),
        receipt_sha256=digest(path), source_sha256={str(p): digest(p) for p in source_files},
        input_sha256=scan.inputs, height_input_bindings=height.input_bindings,
        seconds=durations, max_clock_epoch_gauge_logscore_difference=max(differences),
        qualification='one profiled fixed state; cold factor caches, no fitting or location truth')


if __name__ == '__main__':
    output = HERE / 'diagnostics.json'
    if output.exists():
        raise FileExistsError(output)
    result = dict(schema='localization-model-review-diagnostics/v1',
        python=platform.python_version(), numpy=np.__version__, machine=platform.machine(),
        openblas_num_threads=os.environ.get('OPENBLAS_NUM_THREADS'),
        source_sha256={p.name: digest(p) for p in [Path(__file__), HERE / 'kernels.py']},
        ambiguity=ambiguity(), kernel_benchmark=benchmark(), fixed_state=profile_scan())
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'ambiguity'}, indent=2))
    print(json.dumps({k: v for k, v in result['ambiguity'].items() if k != 'rows'}))
