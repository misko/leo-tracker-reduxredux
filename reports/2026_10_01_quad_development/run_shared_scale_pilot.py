"""Paired conditional warm pilot after sealed shared-scale prerequisites."""
import fcntl
import os
from pathlib import Path
import sys
import time
import numpy as np
from run_window import prepare_window
from leo.analysis.localization_fast import fit_localization_fast
from check_shared_scale import UNITS
from check_group_deletion import audit_fit
from check_receiver_curvature import save
from shared_scale_port import SharedScalePort
from fixed_association_port import FixedAssociationPort
from screen_seed_prefix import sealed, digest
from regression_batch import execute, verify_sources
from failure_composition_checks import process_ok

HERE = Path(__file__).resolve().parent


def worker(unit, arm, directory):
    inputs = {}; started = time.monotonic()
    def read(path):
        value = sealed(path); inputs[str(path)] = digest(path); return value
    check_dir = HERE/'shared-scale-check-v1'/unit
    check = read(check_dir/'result.json'); assert check['singleton_score_error'] == 0 and max(check['gradient_errors'].values()) < .005
    assert process_ok(read(check_dir/'launch.json'))
    freeze = read(check_dir/'sources.json'); sources = dict(freeze['source_sha256']); inputs.update(freeze['inputs'])
    parent = read(HERE/'one-start-blas-cold-v1'/unit/'blas'/(unit+'.json'))
    verify_sources(sources); verify_sources(inputs)
    binding, scans, columns, precision, original = prepare_window(unit)
    assert binding == parent['binding'] and parent['observations'] == [list(p.observation_ids) for p in original]
    np.testing.assert_array_equal(parent['precision'], precision)
    labels = parent['best']['associations']; initial = np.asarray(parent['best']['mean'])
    groups = {}; background = []
    for p, i in zip(original, labels):
        if i == p.candidate_count: background.append(FixedAssociationPort(p, i))
        else: groups.setdefault(i, []).append((p, i))
    ports = ([SharedScalePort(m) for m in groups.values()]+background if arm == 'shared'
             else [FixedAssociationPort(p, i) for p, i in zip(original, labels)])
    ids = [v for p in ports for v in p.observation_ids]
    assert len(ids) == len(set(ids)) and set(ids) == {v for p in original for v in p.observation_ids}
    sources.update({str(Path(m.__file__).resolve()): digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])})
    verify_sources(sources); verify_sources(inputs); save(directory/'sources.json', dict(source_sha256=sources, inputs=inputs))
    t = time.monotonic()
    fit = fit_localization_fast(initial, ports, precision, lambda x: np.linalg.norm(x[:2]) <= 250,
        max_iterations=64, deadline=t+60, degrees_of_freedom=4.)
    fit_seconds = time.monotonic()-t; audit = audit_fit(fit, ports, precision)
    result = dict(unit=unit, arm=arm, binding=binding, audit=audit,
        fit=dict(mean=fit.mean.tolist(), associations=list(fit.associations), objectives=list(fit.objectives),
            converged=fit.converged, reason=fit.reason, iterations=fit.iterations),
        fit_seconds=fit_seconds, elapsed_seconds=time.monotonic()-started,
        physical_ids_preserved=len(ids), groups={str(scans[0][0].bank.norad_ids[i]):len(m) for i,m in groups.items()},
        baseline_position_delta_m=float(np.linalg.norm(fit.mean[:2]-initial[:2])*1000) if audit['accepted'] else None,
        qualification='Conditional warm fit, fixed identities and memberships; no geographic scoring or cold/runtime claim.')
    verify_sources(sources); verify_sources(inputs); save(directory/'result.json', result)
    print(unit, arm, audit, result['baseline_position_delta_m'], flush=True)


def main():
    if len(sys.argv) == 4: worker(sys.argv[1], sys.argv[2], Path(sys.argv[3])); return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for unit in UNITS:
            check_dir = HERE/'shared-scale-check-v1'/unit
            assert process_ok(sealed(check_dir/'launch.json'))
            assert max(sealed(check_dir/'result.json')['gradient_errors'].values()) < .005
        root = HERE/'shared-scale-pilot-v1'; root.mkdir(exist_ok=False)
        env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONPATH=str(HERE.parents[1]/'src'))
        for unit in UNITS:
            for arm in ('control', 'shared'):
                directory = root/unit/arm; directory.mkdir(parents=True)
                launch = execute([sys.executable, str(Path(__file__).resolve()), unit, arm, str(directory)], directory, unit, timeout_s=90, env=env)
                save(directory/'launch.json', launch); print(unit, arm, launch['returncode'], launch['elapsed_seconds'], flush=True)


if __name__ == '__main__': main()
