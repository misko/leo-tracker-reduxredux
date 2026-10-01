"""Bounded nonlinear group-deletion validation; no geography."""
import fcntl
import os
from pathlib import Path
import sys
import time
import numpy as np
from run_window import prepare_window
from leo.analysis.localization_fast import fit_localization_fast
from check_group_influence import UNITS
from check_receiver_curvature import save
from fixed_association_port import FixedAssociationPort
from regression_batch import execute, verify_sources
from screen_seed_prefix import sealed, digest
from failure_composition_checks import process_ok

HERE = Path(__file__).resolve().parent


def audit_fit(fit, ports, precision):
    errors = []; details = {}
    try:
        assert fit.converged, fit.reason
        x = fit.mean; assigned = fit.associations
        assert np.isfinite(x).all() and np.linalg.norm(x[:2]) <= 250
        assert list(assigned) == [int(np.argmax(p.score_all(x))) for p in ports]
        assert np.all(np.diff(fit.objectives) <= 1e-6)
        def objective(z): return float(.5*(precision*z)@z-sum(p.score_selected(z, i) for p, i in zip(ports, assigned)))
        assert abs(objective(x)-fit.objectives[-1]) < 1e-6
        active = {0, 1, *np.flatnonzero(x).tolist()}; predictions = []
        for p, i in zip(ports, assigned):
            if i == p.candidate_count: continue
            pred = p.predict_selected(x, i); assert pred.eligible
            active.update(np.flatnonzero(np.any(pred.jacobian != 0, axis=0)).tolist())
            predictions.append((p, pred))
        active = np.asarray(sorted(active)); H = np.diag(precision[active]); g = (precision*x)[active]
        for p, pred in predictions:
            r = p.observation-pred.mean; v = np.linalg.solve(pred.covariance, r)
            w = (4+len(r))/(4+float(r@v)); J = pred.jacobian[:, active]
            g -= w*J.T@v; H += w*J.T@np.linalg.solve(pred.covariance, J)
        numeric = []
        for i in active:
            step = np.zeros(len(x)); step[i] = .0005
            numeric.append((objective(x+step)-objective(x-step))/.001)
        numeric = np.asarray(numeric)
        details = dict(gradient_error=float(np.max(abs(numeric-g))), decrement_squared=float(numeric@np.linalg.solve(H, numeric)))
        assert details['gradient_error'] < .005 and details['decrement_squared'] < 1e-5, str(details)
    except (AssertionError, ValueError, np.linalg.LinAlgError) as error: errors.append(type(error).__name__+': '+str(error))
    return dict(accepted=not errors, failures=errors, **details)


def worker(unit, arm, directory):
    started = time.monotonic(); inputs = {}
    def read(path):
        value = sealed(path); inputs[str(path)] = digest(path); return value
    diagnostic_dir = HERE/'group-influence-v1'/unit
    diagnostic = read(diagnostic_dir/'result.json'); assert diagnostic['all_valid']
    frozen = read(diagnostic_dir/'sources.json')
    assert process_ok(read(diagnostic_dir/'launch.json'))
    sources = dict(frozen['source_sha256']); inputs.update(frozen['inputs'])
    campaign = 'one-start-blas-cold-v1' if unit.endswith('S1') else 'one-start-blas-window-cold-v1'
    parent = read(HERE/campaign/unit/'blas'/(unit+'.json'))
    verify_sources(sources); verify_sources(inputs)
    binding, scans, columns, precision, all_ports = prepare_window(unit)
    assert binding == parent['binding'] == diagnostic['binding']
    assert parent['observations'] == [list(p.observation_ids) for p in all_ports]
    np.testing.assert_array_equal(parent['precision'], precision)
    initial = np.asarray(parent['best']['mean']); labels = parent['best']['associations']
    selected = diagnostic['maximum_group']; removed = []; kept = []; offset = 0
    for scan_id, (scan, _, ports) in zip(binding['scans'], scans):
        for j in range(len(ports)):
            index = offset+j; label = labels[index]
            remove = scan_id == selected['scan'] and label < len(scan.bank.norad_ids) and int(scan.bank.norad_ids[label]) == selected['norad']
            (removed if remove else kept).append(index)
        offset += len(ports)
    assert len(removed) == selected['tracks'] and removed and kept
    original_ports = [all_ports[i] for i in kept]; baseline_labels = [labels[i] for i in kept]
    ports = [FixedAssociationPort(p, i) for p, i in zip(original_ports, baseline_labels)] if arm == 'fixed' else original_ports
    ids = [v for p in ports for v in p.observation_ids]; assert len(ids) == len(set(ids))
    sources.update({str(Path(m.__file__).resolve()): digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])})
    for name in ('GROUP_DELETION_PLAN.md', 'test_fixed_association_port.py'): sources[str(HERE/name)] = digest(HERE/name)
    verify_sources(sources); verify_sources(inputs)
    save(directory/'sources.json', dict(source_sha256=sources, inputs=inputs))
    fit_start = time.monotonic()
    fit = fit_localization_fast(initial, ports, precision, lambda x: np.linalg.norm(x[:2]) <= 250,
        max_iterations=64, deadline=fit_start+60, degrees_of_freedom=4.)
    fit_seconds = time.monotonic()-fit_start
    audit = audit_fit(fit, ports, precision)
    result = dict(unit=unit, arm=arm, selected_group=selected, removed_indices=removed, kept_indices=kept,
        retained_observations=[list(p.observation_ids) for p in ports], audit=audit,
        fit=dict(mean=fit.mean.tolist(), associations=list(fit.associations), objectives=list(fit.objectives),
            converged=fit.converged, reason=fit.reason, iterations=fit.iterations), fit_seconds=fit_seconds)
    if audit['accepted']:
        actual = fit.mean[:2]-initial[:2]; predicted = np.asarray(selected['horizontal_delta_km'])
        actual_norm = np.linalg.norm(actual); predicted_norm = np.linalg.norm(predicted)
        result['comparison'] = dict(actual_delta_km=actual.tolist(), predicted_delta_km=predicted.tolist(),
            actual_step_m=float(actual_norm*1000), predicted_step_m=float(predicted_norm*1000),
            vector_difference_m=float(np.linalg.norm(actual-predicted)*1000), norm_ratio=float(actual_norm/predicted_norm),
            direction_cosine=float(actual@predicted/(actual_norm*predicted_norm)) if actual_norm > 0 else None,
            changed_assignments=sum(a != b for a, b in zip(fit.associations, baseline_labels)),
            unconstrained_disagreements=sum(int(np.argmax(p.score_all(fit.mean))) != i for p, i in zip(original_ports, fit.associations)))
    verify_sources(sources); verify_sources(inputs)
    result['elapsed_seconds'] = time.monotonic()-started
    save(directory/'result.json', result)
    print(unit, arm, audit, result.get('comparison'), flush=True)


def main():
    if len(sys.argv) == 4: worker(sys.argv[1], sys.argv[2], Path(sys.argv[3])); return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root = HERE/'group-deletion-v1'; root.mkdir(exist_ok=False)
        env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONPATH=str(HERE.parents[1]/'src'))
        for unit in UNITS:
            for arm in ('fixed', 'reassigned'):
                directory = root/unit/arm; directory.mkdir(parents=True)
                launch = execute([sys.executable, str(Path(__file__).resolve()), unit, arm, str(directory)], directory, unit, timeout_s=90, env=env)
                save(directory/'launch.json', launch); print(unit, arm, launch['returncode'], launch['elapsed_seconds'], flush=True)


if __name__ == '__main__': main()
