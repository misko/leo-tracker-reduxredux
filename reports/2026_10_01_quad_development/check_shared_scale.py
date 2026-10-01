"""Real fixed-state model prerequisites, without fitting or geography."""
import fcntl
import os
from pathlib import Path
import sys
import time
import numpy as np
from run_window import prepare_window
from check_receiver_curvature import save
from shared_scale_port import SharedScalePort
from fixed_association_port import FixedAssociationPort
from screen_seed_prefix import sealed, digest
from regression_batch import execute, verify_sources
from failure_composition_checks import process_ok

HERE = Path(__file__).resolve().parent
UNITS = ('DS9-B01-S1', 'DS10-B01-S1', 'DS11-B01-S1')


def worker(unit, directory):
    started = time.monotonic(); inputs = {}
    parent_dir = HERE/'one-start-blas-cold-v1'/unit/'blas'
    def read(name):
        path = parent_dir/name; value = sealed(path); inputs[str(path)] = digest(path); return value
    parent = read(unit+'.json'); freeze = read('sources.json'); evaluation = read('evaluation.json')
    assert len(evaluation['rows']) == 1 and evaluation['rows'][0]['accepted']
    assert evaluation['rows'][0]['receipt_sha256'] == digest(parent_dir/(unit+'.json'))
    for name in (unit+'.launch.json', 'audit-launch.json'): assert process_ok(read(name))
    sources = dict(freeze['source_sha256']); inputs.update(freeze['inputs'])
    verify_sources(sources); verify_sources(inputs)
    binding, scans, columns, precision, original = prepare_window(unit)
    assert binding == parent['binding']
    assert parent['observations'] == [list(p.observation_ids) for p in original]
    np.testing.assert_array_equal(parent['precision'], precision)
    x = np.asarray(parent['best']['mean']); labels = parent['best']['associations']
    groups = {}; background = []; singleton_error = 0.
    for p, i in zip(original, labels):
        if i == p.candidate_count: background.append(FixedAssociationPort(p, i)); continue
        groups.setdefault(i, []).append((p, i))
        singleton = SharedScalePort([(p, i)])
        singleton_error = max(singleton_error, abs(singleton.score_selected(x, 0)-p.score_selected(x, i)))
        pred = singleton.predict_selected(x, 0); old = p.predict_selected(x, i)
        np.testing.assert_array_equal(pred.mean, old.mean)
        np.testing.assert_array_equal(pred.jacobian, old.jacobian)
        np.testing.assert_array_equal(pred.covariance, old.covariance)
    ports = [SharedScalePort(m) for m in groups.values()]+background
    ids = [v for p in ports for v in p.observation_ids]
    assert len(ids) == len(set(ids)) and set(ids) == {v for p in original for v in p.observation_ids}
    assigned = [int(np.argmax(p.score_all(x))) for p in ports]
    active = {0, 1, *np.flatnonzero(x).tolist()}; predictions = []
    for p, i in zip(ports, assigned):
        if i == p.candidate_count: continue
        pred = p.predict_selected(x, i); assert pred.eligible
        active.update(np.flatnonzero(np.any(pred.jacobian != 0, axis=0)).tolist()); predictions.append((p, pred))
    active = np.asarray(sorted(active)); gradient = (precision*x)[active]
    for p, pred in predictions:
        r = p.observation-pred.mean; v = np.linalg.solve(pred.covariance, r)
        gradient -= (4+len(r))/(4+float(r@v))*pred.jacobian[:, active].T@v
    def objective(z): return float(.5*(precision*z)@z-sum(p.score_selected(z, i) for p, i in zip(ports, assigned)))
    sources.update({str(Path(m.__file__).resolve()): digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])})
    for name in ('SHARED_SCALE_PLAN.md', 'test_shared_scale_port.py'): sources[str(HERE/name)] = digest(HERE/name)
    verify_sources(sources); verify_sources(inputs); save(directory/'sources.json', dict(source_sha256=sources, inputs=inputs))
    errors = {}
    for h in (.0005, .0001):
        numeric = []
        for j in active:
            assert time.monotonic()-started < 85
            shift = np.zeros(len(x)); shift[j] = h
            numeric.append((objective(x+shift)-objective(x-shift))/(2*h))
        errors[str(h)] = float(np.max(abs(gradient-numeric)))
        assert errors[str(h)] < .005
    sizes = [len(m) for m in groups.values()]
    result = dict(unit=unit, signal_groups=len(groups), singleton_groups=sizes.count(1), multi_track_groups=sum(n > 1 for n in sizes),
        group_sizes=sizes, background_tracks=len(background), preserved_observation_ids=len(ids),
        singleton_score_error=singleton_error, active_dimension=len(active), gradient_errors=errors,
        original_objective=parent['best']['objectives'][-1], shared_scale_objective=objective(x),
        elapsed_seconds=time.monotonic()-started,
        qualification='Fixed-state model prerequisite only. Objectives are from different normalized likelihoods; no localization fits or geographic scoring.')
    verify_sources(sources); verify_sources(inputs); save(directory/'result.json', result); print(result, flush=True)


def main():
    if len(sys.argv) == 3: worker(sys.argv[1], Path(sys.argv[2])); return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root = HERE/'shared-scale-check-v1'; root.mkdir(exist_ok=False)
        env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONPATH=str(HERE.parents[1]/'src'))
        for unit in UNITS:
            directory = root/unit; directory.mkdir()
            launch = execute([sys.executable, str(Path(__file__).resolve()), unit, str(directory)], directory, unit, timeout_s=90, env=env)
            save(directory/'launch.json', launch); print(unit, launch, flush=True)
            assert process_ok(launch)


if __name__ == '__main__': main()
