"""Conditional held-track prediction from other tracks' residual energy."""
import fcntl
import os
from pathlib import Path
import sys
import numpy as np
from run_window import prepare_window
from check_shared_scale import UNITS
from check_receiver_curvature import save
from scale_prediction import conditional, log_density
from leo.analysis.robust_likelihood import student_t_logpdf
from screen_seed_prefix import sealed, digest
from regression_batch import execute, verify_sources
from failure_composition_checks import process_ok

HERE = Path(__file__).resolve().parent


def worker(unit, directory):
    inputs = {}
    def read(path):
        value = sealed(path); inputs[str(path)] = digest(path); return value
    prerequisite = HERE/'shared-scale-check-v1'/unit
    freeze = read(prerequisite/'sources.json'); sources = dict(freeze['source_sha256']); inputs.update(freeze['inputs'])
    assert process_ok(read(prerequisite/'launch.json')); read(prerequisite/'result.json')
    parent = read(HERE/'one-start-blas-cold-v1'/unit/'blas'/(unit+'.json'))
    verify_sources(sources); verify_sources(inputs)
    binding, scans, columns, precision, ports = prepare_window(unit)
    assert binding == parent['binding'] and parent['observations'] == [list(p.observation_ids) for p in ports]
    state = np.asarray(parent['best']['mean']); records = []; background = 0
    for track_index, (p, label) in enumerate(zip(ports, parent['best']['associations'])):
        if label == p.candidate_count: background += 1; continue
        pred = p.predict_selected(state, label); assert pred.eligible
        residual = p.observation-pred.mean; L = np.linalg.cholesky(pred.covariance); y = np.linalg.solve(L, residual)
        d = len(y); q = float(y@y); logdet = float(2*np.log(np.diag(L)).sum())
        old = student_t_logpdf(residual, pred.covariance, 4.)
        np.testing.assert_allclose(log_density(d, q, logdet), old, atol=1e-10, rtol=0)
        records.append(dict(track_index=track_index, norad=int(scans[0][0].bank.norad_ids[label]), d=d, q=q, logdet=logdet, independent=old))
    sources.update({str(Path(m.__file__).resolve()): digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])})
    for name in ('SCALE_PREDICTION_PLAN.md', 'test_scale_prediction.py'): sources[str(HERE/name)] = digest(HERE/name)
    verify_sources(sources); verify_sources(inputs); save(directory/'sources.json', dict(source_sha256=sources, inputs=inputs))
    maximum = 0.
    for row in records:
        train = [r for r in records if r['norad'] == row['norad'] and r['track_index'] != row['track_index']]
        td = sum(r['d'] for r in train); tq = sum(r['q'] for r in train); tl = sum(r['logdet'] for r in train)
        value = conditional(row['d'], row['q'], row['logdet'], td, tq)
        difference = log_density(row['d']+td, row['q']+tq, row['logdet']+tl)-log_density(td, tq, tl)
        error = abs(value-difference); assert error < 1e-9; maximum = max(maximum, error)
        row.update(training_tracks=len(train), training_dimension=td, training_energy=tq, shared_predictive=value,
                   gain=value-row['independent'], gain_per_contrast=(value-row['independent'])/row['d'])
        if not train: assert abs(row['gain']) < 1e-10
    multi = [r for r in records if r['training_tracks']]
    group_rows = [dict(norad=g, tracks=len(local), gain_per_contrast=sum(r['gain'] for r in local)/sum(r['d'] for r in local))
                  for g in sorted({r['norad'] for r in multi}) for local in [[r for r in multi if r['norad'] == g]]]
    pooled = sum(r['gain'] for r in multi)/sum(r['d'] for r in multi)
    median = float(np.median([r['gain_per_contrast'] for r in multi]))
    value = dict(unit=unit, tracks=records, groups=group_rows, background_tracks=background,
        multi_track_count=len(multi), singleton_track_count=len(records)-len(multi),
        pooled_gain_per_contrast=pooled, median_track_gain_per_contrast=median,
        improving_tracks=sum(r['gain'] > 0 for r in multi), improving_groups=sum(r['gain_per_contrast'] > 0 for r in group_rows),
        maximum_formula_difference=maximum, conditional_signal=bool(pooled > 0 and median > 0),
        qualification='Fixed baseline state and identities used all data. Conditional residual-scale diagnostic, not independent validation or geography.')
    verify_sources(sources); verify_sources(inputs); save(directory/'result.json', value)
    print({k:v for k,v in value.items() if k not in ('tracks', 'groups')}, flush=True)


def main():
    if len(sys.argv) == 3: worker(sys.argv[1], Path(sys.argv[2])); return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root = HERE/'scale-prediction-v1'; root.mkdir(exist_ok=False)
        env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONPATH=str(HERE.parents[1]/'src'))
        for unit in UNITS:
            directory = root/unit; directory.mkdir()
            launch = execute([sys.executable, str(Path(__file__).resolve()), unit, str(directory)], directory, unit, timeout_s=90, env=env)
            save(directory/'launch.json', launch); assert process_ok(launch)
            print(unit, launch['elapsed_seconds'], flush=True)


if __name__ == '__main__': main()
