"""Nine bounded fixed-state influence diagnostics, without geographic scoring."""
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
from check_receiver_curvature import save
from group_influence import deletion, profile

HERE = Path(__file__).resolve().parent
UNITS = tuple(f'{ds}-B01-{size}' for ds in ('DS9', 'DS10', 'DS11') for size in ('S1', 'D1', 'Q'))


def worker(unit, directory):
    started = time.monotonic()
    campaign = 'one-start-blas-cold-v1' if unit.endswith('S1') else 'one-start-blas-window-cold-v1'
    parent_dir = HERE/campaign/unit/'blas'
    inputs = {}
    def read(name):
        p = parent_dir/name; value = sealed(p); inputs[str(p)] = digest(p); return value
    parent = read(unit+'.json'); freeze = read('sources.json'); audit = read('evaluation.json')
    assert len(audit['rows']) == 1 and audit['rows'][0]['accepted']
    assert audit['rows'][0]['receipt_sha256'] == digest(parent_dir/(unit+'.json'))
    for name in (unit+'.launch.json', 'audit-launch.json'): assert process_ok(read(name))
    sources = dict(freeze['source_sha256']); inputs.update(freeze['inputs'])
    verify_sources(sources); verify_sources(inputs)
    binding, scans, columns, precision, ports = prepare_window(unit)
    assert binding == parent['binding']
    assert parent['observations'] == [list(p.observation_ids) for p in ports]
    assert parent['columns'] == [c.tolist() for c in columns]
    np.testing.assert_array_equal(parent['precision'], precision)
    for _, height, _ in scans: inputs[height.input_bindings['grid_path']] = height.input_bindings['grid_sha256']
    state = np.asarray(parent['best']['mean']); assignments = parent['best']['associations']
    assert assignments == [int(np.argmax(p.score_all(state))) for p in ports]
    identifiers = [(scan_id, int(scan.bank.norad_ids[i]) if i < len(scan.bank.norad_ids) else None)
                   for scan_id, (scan, _, local), offset in
                   zip(binding['scans'], scans, np.cumsum([0]+[len(s[2]) for s in scans[:-1]]))
                   for i in assignments[offset:offset+len(local)]]
    assert len(identifiers) == len(ports)
    active = {0, 1, *np.flatnonzero(state).tolist()}; records = []; background = 0
    for port, index, identifier in zip(ports, assignments, identifiers):
        if index == port.candidate_count: background += 1; continue
        prediction = port.predict_selected(state, index); assert prediction.eligible
        active.update(np.flatnonzero(np.any(prediction.jacobian != 0, axis=0)).tolist())
        records.append((identifier, port.observation-prediction.mean, prediction))
    active = np.asarray(sorted(active)); H = np.diag(precision[active]); g = (precision*state)[active]
    groups = {}
    for identifier, residual, prediction in records:
        J = prediction.jacobian[:, active]; solved = np.linalg.solve(prediction.covariance, residual)
        weight = (4+len(residual))/(4+float(residual@solved))
        Hi = weight*J.T@np.linalg.solve(prediction.covariance, J); gi = -weight*J.T@solved
        H += Hi; g += gi
        if identifier not in groups: groups[identifier] = [np.zeros_like(H), np.zeros_like(g), 0]
        groups[identifier][0] += Hi; groups[identifier][1] += gi; groups[identifier][2] += 1
    decrement = float(g@np.linalg.solve(H, g)); assert decrement < 1e-5
    S = profile(H); eig = np.linalg.eigvalsh(S); fixed = np.linalg.eigvalsh(H[:2, :2])
    sources.update({str(Path(m.__file__).resolve()): digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py'
        and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])})
    for name in ('GROUP_INFLUENCE_PLAN.md', 'test_group_influence.py'): sources[str(HERE/name)] = digest(HERE/name)
    verify_sources(sources); verify_sources(inputs)
    save(directory/'sources.json', dict(source_sha256=sources, inputs=inputs))
    rows = []
    for (scan_id, norad), (Hg, gg, count) in sorted(groups.items()):
        assert time.monotonic()-started < 85
        result = deletion(H, g, Hg, gg)
        if result['valid']:
            delta = np.asarray(result.pop('delta')); result['horizontal_delta_km'] = delta[:2].tolist()
            result['nuisance_step_prior_norm'] = float(np.sqrt(np.sum(precision[active][2:]*delta[2:]**2)))
        rows.append(dict(scan=scan_id, norad=norad, tracks=count, **result))
    valid = all(r['valid'] for r in rows)
    maximum = max(rows, key=lambda r: r.get('horizontal_step_m', -1)) if valid else None
    value = dict(unit=unit, size=binding['size'], binding=binding, active_dimension=len(active),
        signal_tracks=len(records), background_tracks=background, groups=rows, all_valid=valid,
        baseline_decrement_squared=decrement, profiled_position_eigenvalues=eig.tolist(),
        fixed_nuisance_position_eigenvalues=fixed.tolist(), profiled_to_fixed_eigenvalue_ratios=(eig/fixed).tolist(),
        profiled_condition_number=float(eig[-1]/eig[0]),
        maximum_group=maximum, median_step_m=float(np.median([r['horizontal_step_m'] for r in rows])) if valid else None,
        elapsed_seconds=time.monotonic()-started,
        qualification='One frozen-weight local group deletion step; not refitted position, geographic error, exact posterior Hessian or confidence calibration.')
    verify_sources(sources); verify_sources(inputs); save(directory/'result.json', value)
    print(json.dumps({k:v for k,v in value.items() if k not in ('groups', 'binding')}))


def main():
    if len(sys.argv) == 3: worker(sys.argv[1], Path(sys.argv[2])); return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root = HERE/'group-influence-v1'; root.mkdir(exist_ok=False)
        env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONPATH=str(HERE.parents[1]/'src'))
        for unit in UNITS:
            directory = root/unit; directory.mkdir()
            launch = execute([sys.executable, str(Path(__file__).resolve()), unit, str(directory)], directory, unit, timeout_s=90, env=env)
            save(directory/'launch.json', launch); print(unit, json.dumps(launch), flush=True)
            assert process_ok(launch)


if __name__ == '__main__': main()
