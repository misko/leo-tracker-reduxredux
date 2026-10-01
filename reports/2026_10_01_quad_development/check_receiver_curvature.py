"""Bounded conditional receiver-curvature diagnostic; no geographic scoring."""
import fcntl
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
from run_window import prepare_window
from regression_batch import execute, verify_sources
from screen_seed_prefix import sealed, digest
from failure_composition_checks import process_ok
from receiver_curvature import basis, folds, fit, loss

HERE = Path(__file__).resolve().parent
UNITS = ('DS9-B01-S1', 'DS10-B01-S1', 'DS11-B01-S1')


def save(path, value):
    with path.open('x') as stream: json.dump(value, stream, indent=2, allow_nan=False)
    path.with_suffix('.sha256').write_text(digest(path)+'\n')


def worker(unit, directory):
    started = time.monotonic()
    parent_dir = HERE/'one-start-blas-cold-v1'/unit/'blas'
    inputs = {}
    def read(name):
        path = parent_dir/name
        value = sealed(path); inputs[str(path)] = digest(path); return value
    parent = read(unit+'.json')
    frozen = read('sources.json')
    evaluation = read('evaluation.json')
    assert len(evaluation['rows']) == 1 and evaluation['rows'][0]['accepted']
    assert evaluation['rows'][0]['receipt_sha256'] == digest(parent_dir/(unit+'.json'))
    for name in (unit+'.launch.json', 'audit-launch.json'): assert process_ok(read(name))
    sources = dict(frozen['source_sha256'])
    inputs.update(frozen['inputs'])
    for name in ('RECEIVER_CURVATURE_PLAN.md', 'receiver_curvature.py',
                 'test_receiver_curvature.py', 'check_receiver_curvature.py'):
        sources[str(HERE/name)] = digest(HERE/name)
    verify_sources(sources); verify_sources(inputs)
    binding, scans, columns, _, _ = prepare_window(unit)
    assert binding == parent['binding']
    scan, height, ports = scans[0]
    inputs[height.input_bindings['grid_path']] = height.input_bindings['grid_sha256']
    state = np.asarray(parent['best']['mean'])[columns[0]]
    assignments = parent['best']['associations']
    assert len(assignments) == len(ports)
    rows = []; background = 0
    for (track_id, _), port, index in zip(scan.tracks, ports, assignments):
        if index == port.candidate_count:
            background += 1; continue
        prediction = port.predict_selected(state, index)
        assert prediction.eligible
        lookup = {value: i for i, value in enumerate(port.track.observation_ids)}
        selected = np.array([lookup[value] for value in port.observation_ids])
        times = port.track.times_s[selected]; receivers = port.track.receiver_indices[selected]
        B = port.likelihood.contrasts
        np.testing.assert_allclose(B@port.track.frequencies_hz[selected], port.observation, atol=1e-8)
        rows.append(dict(group=int(scan.bank.norad_ids[index]), track_id=str(track_id),
            times=times, receivers=receivers, B=B,
            rf_scale=port.config.reference_frequency_hz/port.track.rf_hz,
            residual=port.observation-prediction.mean, covariance=prediction.covariance,
            jacobian=prediction.jacobian[:, 3:5]))
    all_times = np.concatenate([r['times'] for r in rows])
    center = float((all_times.min()+all_times.max())/2)
    scale = float((all_times.max()-all_times.min())/2)
    records = []; maximum = 0.
    for row in rows:
        X = basis(row['times'], row['receivers'], row['B'], row['rf_scale'], center, scale)
        error = float(np.max(np.abs(X[:, :2]*scale-row['jacobian'])))
        assert error < 1e-8; maximum = max(maximum, error)
        L = np.linalg.cholesky(row['covariance'])
        records.append(dict(group=row['group'], y=np.linalg.solve(L, row['residual']), X=np.linalg.solve(L, X)))
    sources.update({str(Path(m.__file__).resolve()): digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py'
        and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])})
    verify_sources(sources); verify_sources(inputs)
    save(directory/'sources.json', dict(source_sha256=sources, inputs=inputs))
    results = []
    for group, train, held in folds(records):
        assert time.monotonic()-started < 85
        linear = fit(train, [0, 1]); quadratic = fit(train, [0, 1, 2, 3])
        valid = linear['converged'] and quadratic['converged']
        scores = dict(zero=-loss(held, np.zeros(2), [0, 1]))
        for name, fitted, cols in (('linear', linear, [0, 1]), ('quadratic', quadratic, [0, 1, 2, 3])):
            scores[name] = -loss(held, np.asarray(fitted['beta']), cols) if fitted['converged'] else None
        results.append(dict(group=group, tracks=len(held), contrasts=sum(len(r['y']) for r in held),
            valid=valid, linear=linear, quadratic=quadratic, scores=scores))
    valid = all(r['valid'] for r in results)
    gains = [(r['scores']['quadratic']-r['scores']['linear'])/r['contrasts'] for r in results] if valid else []
    pooled = sum(r['scores']['quadratic']-r['scores']['linear'] for r in results)/sum(r['contrasts'] for r in results) if valid else None
    full = {name: fit(records, cols) for name, cols in (('linear', [0, 1]), ('quadratic', [0, 1, 2, 3]))}
    verify_sources(sources); verify_sources(inputs)
    result = dict(unit=unit, binding=binding, signal_tracks=len(records), background_tracks=background,
        receiver_track_counts={str(rx): sum(bool(np.any(r['receivers'] == rx)) for r in rows) for rx in (0, 1)},
        center_seconds=center, scale_seconds=scale, maximum_linear_jacobian_error=maximum,
        folds=results, full_data_fits=full, all_folds_valid=valid,
        pooled_quadratic_minus_linear_per_contrast=pooled,
        median_group_gain_per_contrast=float(np.median(gains)) if valid else None,
        positive_groups=sum(g > 0 for g in gains),
        gate_passed=bool(valid and pooled > 0 and np.median(gains) > 0),
        elapsed_seconds=time.monotonic()-started,
        qualification='Conditional plug-in residual diagnostic. Baseline state and identities used all observations; not independent localization validation. No geographic scoring.')
    save(directory/'result.json', result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('folds', 'full_data_fits', 'binding')}))


def main():
    if len(sys.argv) == 3:
        worker(sys.argv[1], Path(sys.argv[2])); return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root = HERE/'receiver-curvature-v1'; root.mkdir(exist_ok=False)
        env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONPATH=str(HERE.parents[1]/'src'))
        for unit in UNITS:
            directory = root/unit; directory.mkdir()
            launch = execute([sys.executable, str(Path(__file__).resolve()), unit, str(directory)], directory, unit, timeout_s=90, env=env)
            save(directory/'launch.json', launch)
            print(unit, json.dumps(launch), flush=True)
            assert process_ok(launch)


if __name__ == '__main__': main()
