"""Sealed six-arm conditional mixture localization pilot."""
import fcntl
import os
from pathlib import Path
import sys
import time
import numpy as np
from run_window import prepare_window
from check_shared_scale import UNITS
from check_receiver_curvature import save
from mixture_localization import MixtureObjective
from mixture_optimizer import fit, audit
from screen_seed_prefix import sealed, digest
from regression_batch import execute, verify_sources
from failure_composition_checks import process_ok

HERE = Path(__file__).resolve().parent


def worker(unit, arm, directory):
    inputs = {}
    def read(path):
        value = sealed(path); inputs[str(path)] = digest(path); return value
    check_dir = HERE/'mixture-localization-check-v1'/unit
    assert process_ok(read(check_dir/'launch.json'))
    check = read(check_dir/'result.json'); assert max(check['mixture_gradient_errors'].values()) < .005
    frozen = read(check_dir/'sources.json'); sources = dict(frozen['source_sha256']); inputs.update(frozen['inputs'])
    parent = read(HERE/'one-start-blas-cold-v1'/unit/'blas'/(unit+'.json'))
    verify_sources(sources); verify_sources(inputs)
    binding, scans, columns, precision, ports = prepare_window(unit)
    assert binding == parent['binding'] and parent['observations'] == [list(p.observation_ids) for p in ports]
    np.testing.assert_array_equal(parent['precision'], precision)
    initial = np.asarray(parent['best']['mean']); labels = parent['best']['associations']
    model = MixtureObjective(ports, labels, labels, precision, initial, arm)
    sources.update({str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])})
    sources[str(HERE/'test_mixture_optimizer.py')] = digest(HERE/'test_mixture_optimizer.py')
    verify_sources(sources); verify_sources(inputs); save(directory/'sources.json', dict(source_sha256=sources, inputs=inputs))
    started = time.monotonic(); result = fit(model, initial, started+60); seconds = time.monotonic()-started
    accepted = audit(model, result); x = np.asarray(result['mean'])
    control_delta = float(np.linalg.norm(x[:2]-initial[:2])*1000)
    control_objective_difference = abs(model.evaluate(x, False)[0]-parent['best']['objectives'][-1]) if arm == 'independent' else None
    control_equivalent = bool(control_delta <= 1 and control_objective_difference <= 1e-5) if arm == 'independent' else None
    verify_sources(sources); verify_sources(inputs)
    value = dict(unit=unit, arm=arm, binding=binding, fit=result, audit=accepted, fit_seconds=seconds,
        control_equivalent=control_equivalent, baseline_position_delta_m=control_delta,
        control_objective_difference=control_objective_difference,
        final_responsibilities=model.evaluate(x, False)[3] if accepted['accepted'] else None)
    save(directory/'result.json', value); print(unit, arm, accepted, control_equivalent, flush=True)


def main():
    if len(sys.argv) == 4: worker(sys.argv[1], sys.argv[2], Path(sys.argv[3])); return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for unit in UNITS: assert process_ok(sealed(HERE/'mixture-localization-check-v1'/unit/'launch.json'))
        root = HERE/'mixture-localization-pilot-v1'; root.mkdir(exist_ok=False)
        env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONPATH=str(HERE.parents[1]/'src'))
        for unit in UNITS:
            for arm in ('independent', 'mixture'):
                directory = root/unit/arm; directory.mkdir(parents=True)
                launch = execute([sys.executable, str(Path(__file__).resolve()), unit, arm, str(directory)], directory, unit, timeout_s=90, env=env)
                save(directory/'launch.json', launch); print(unit, arm, launch['returncode'], flush=True)


if __name__ == '__main__': main()
