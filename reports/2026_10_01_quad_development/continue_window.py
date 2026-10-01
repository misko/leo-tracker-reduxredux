"""Sealed warm continuation diagnostic; never replace a cold baseline outcome."""
import argparse
import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys
import time

import numpy as np
from run_window import prepare_window, fit_localization_fast
from regression_batch import digest, execute, verify_sources
from evaluate_pilot import audit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GOAL = HERE.parent / '2026_10_01_localization_goal'


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
    path.with_suffix('.sha256').write_text(digest(path)+'\n')


def worker(unit, directory, seconds):
    started = time.monotonic()
    frozen = json.loads((directory/'sources.json').read_text())
    verify_sources(frozen['source_sha256']); verify_sources(frozen['inputs'])
    source = HERE/'independent-v2'/unit.rsplit('-', 1)[0]/(unit+'.json')
    baseline = json.loads(source.read_text())
    assert baseline['status'] == 'unresolved'
    assert baseline['best']['reason'] == 'iteration_limit'
    assert baseline['best'] == min(baseline['fits'], key=lambda f: f['objectives'][-1])
    binding, scans, columns, precision, ports = prepare_window(unit)
    assert binding == baseline['binding']
    assert baseline['precision'] == precision.tolist()
    assert baseline['columns'] == [c.tolist() for c in columns]
    assert baseline['inputs'] == {k:v for scan,_,_ in scans for k,v in scan.inputs.items()}
    state = np.asarray(baseline['best']['mean'])
    fit = fit_localization_fast(state, ports, precision,
        lambda x: np.linalg.norm(x[:2]) <= 250, max_iterations=32,
        deadline=started+seconds-5, degrees_of_freedom=4.)
    assert abs(fit.objectives[0]-baseline['best']['objectives'][-1]) < 1e-6
    continued = dict(seed_index=baseline['best']['seed_index'], mean=fit.mean.tolist(),
        objectives=list(fit.objectives), converged=fit.converged, reason=fit.reason,
        iterations=fit.iterations, associations=list(fit.associations),
        seconds=time.monotonic()-started)
    result = copy.deepcopy(baseline)
    result.update(best=continued, fits=[continued],
        status='converged_local_mode' if fit.converged else 'unresolved',
        qualification='Warm continuation diagnostic. Baseline retained. Total runtime includes original cold launch and this separately prepared continuation.',
        continuation=dict(source_receipt_sha256=digest(source), max_iterations=32,
            extra_limit_s=seconds, initial_objective=baseline['best']['objectives'][-1]),
        source_sha256=frozen['source_sha256'])
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result.update(wall_seconds=baseline['wall_seconds']+time.monotonic()-started,
        cpu_seconds=baseline['cpu_seconds']+usage.ru_utime+usage.ru_stime)
    verify_sources(frozen['source_sha256']); verify_sources(frozen['inputs'])
    save(directory/(unit+'.json'), result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit'); parser.add_argument('--worker', action='store_true')
    parser.add_argument('--seconds', type=float)
    args = parser.parse_args()
    directory = HERE/'continuation-v1'/args.unit
    if args.worker:
        worker(args.unit, directory, args.seconds)
        return
    with (GOAL/'.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        baseline_dir = HERE/'independent-v2'/args.unit.rsplit('-', 1)[0]
        source = baseline_dir/(args.unit+'.json')
        baseline = json.loads(source.read_text())
        launch = json.loads(source.with_suffix('.launch.json').read_text())
        original_freeze = baseline_dir/'sources.json'
        assert digest(original_freeze) == original_freeze.with_suffix('.sha256').read_text().strip() == launch['freeze_sha256']
        frozen = json.loads(original_freeze.read_text())
        verify_sources(frozen['source_sha256']); verify_sources(frozen['inputs'])
        assert digest(source) == source.with_suffix('.sha256').read_text().strip() == launch['receipt_sha256']
        assert launch['returncode'] == 0 and not launch['timed_out']
        assert baseline['status'] == 'unresolved' and baseline['best']['reason'] == 'iteration_limit'
        limit = 90*baseline['binding']['size']
        seconds = min(60., limit-launch['elapsed_seconds'])
        if seconds < 10:
            raise ValueError('insufficient remaining budget for this diagnostic')
        sources = dict(frozen['source_sha256'])
        sources.update({str(Path(m.__file__).resolve()):digest(m.__file__)
            for m in tuple(sys.modules.values()) if getattr(m,'__file__',None)
            and Path(m.__file__).suffix == '.py' and Path(m.__file__).resolve().is_relative_to(ROOT)})
        inputs = dict(frozen['inputs'])
        inputs.update({str(p):digest(p) for p in [source, source.with_suffix('.launch.json'), original_freeze]})
        directory.mkdir(parents=True, exist_ok=False)
        freeze = directory/'sources.json'
        save(freeze, dict(source_sha256=sources, inputs=inputs, units=[baseline['binding']],
            policy='Resume lowest-objective iteration-limited start once, at most32iterations and60s extra; total original+extra within90s per scan; no GPS selector.'))
        env = dict(os.environ, PYTHONPATH=str(ROOT/'src'), OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
        extra = execute([sys.executable, str(Path(__file__).resolve()), args.unit,
            '--worker', '--seconds', str(seconds)], directory, args.unit, timeout_s=seconds, env=env)
        output = directory/(args.unit+'.json')
        total = dict(extra)
        total.update(elapsed_seconds=launch['elapsed_seconds']+extra['elapsed_seconds'],
            within_budget=extra['within_budget'] and launch['elapsed_seconds']+extra['elapsed_seconds'] <= limit,
            freeze_sha256=digest(freeze), receipt_sha256=digest(output) if output.exists() else None,
            original_launch=launch, continuation_launch=extra)
        save(output.with_suffix('.launch.json'), total)
        rows, states, freeze_hash = audit(directory)
        # Reference access follows all numerical decisions, as in the baseline.
        ref_path = HERE/'reference-admission-v1.json'
        assert digest(ref_path) == ref_path.with_suffix('.sha256').read_text().strip()
        references = json.loads(ref_path.read_text()); verify_sources(references['source_sha256'])
        reference = {r['unit']:r['reference_latlon'] for r in references['rows']}
        helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
        assert digest(helper) == 'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
        spec = importlib.util.spec_from_file_location('offline_geo', helper)
        geo = importlib.util.module_from_spec(spec); spec.loader.exec_module(geo)
        for row in rows:
            locations = [reference[u] for u in row['scans']]
            assert all(p == locations[0] for p in locations)
            row['error_m'] = geo.distance_m(geo.latlon_from_enu(*states[row['unit']]), locations[0]) if row['accepted'] else None
        save(directory/'evaluation.json', dict(rows=rows, freeze_sha256=freeze_hash,
            reference_sha256=digest(ref_path), qualification='Development diagnostic selected by numerical failure; not an independent cold rerun or full-panel continuation benchmark.'))
        print(json.dumps(rows, indent=2), flush=True)


if __name__ == '__main__':
    main()
