"""Truth-free, report-only Hard60 experiments over the frozen N01--N64 inputs."""
import argparse
import concurrent.futures as futures
from dataclasses import asdict
import json
import multiprocessing
from pathlib import Path
import shutil
import sys
import time
import traceback
import numpy as np

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / '2026_10_07_n64_before_after'
CONTROL = HERE.parent / '2026_10_07_n64_sigma_slope_variants'
SOFT = HERE.parent / '2026_10_07_n64_soft_slope_priors'
sys.path.insert(0, str(OLD))
import experiment as engine
import data

COMMON = dict(sigma=2., width=60., levels=[40., 20., 10., 5.], edge='nearest')
PHASES = {name: dict(COMMON) for name in ('two_starts', 'calibration_retry', 'rf_offsets')}
LABELS = [f'N{i:02d}' for i in range(1, 65)]
WATCH = ['N05', 'N25', 'N29', 'N39', 'N49', 'N64']
BASE_POINT, BASE_REFINE, BASE_FIT = engine.score_point, engine.refine_region, engine.fit_position
engine.HERE, engine.PHASES = HERE, PHASES


def read(path):
    return json.loads(Path(path).read_text())


def control_folder(label):
    return CONTROL / 'results' / label / 'sigma2_60'


def reset_seed(vector):
    result = np.asarray(vector).copy()
    result[[3, 5]] = 0.
    result[7:] = 0.
    return result


def choose_coarse(fits):
    # Match the control: coarse ranking uses the best feasible objective even
    # when its strict stationarity check has not yet passed.
    return min(fits, key=lambda r: r.objective)


def recover_fit(obj, start, fit_function=BASE_FIT, **kwargs):
    calls = []
    def once(vector, name):
        result = fit_function(obj, vector, **kwargs)
        calls.append(dict(name=name, **asdict(result)))
        return result
    first = once(start, 'original')
    if first.converged:
        return first, calls
    second = once(first.vector, 'continuation')
    pool = [first, second]
    if not second.converged:
        reset = first.vector.copy()
        reset[7:] = 0.
        pool.append(once(reset, 'zero-timing'))
    accepted = [r for r in pool if r.converged]
    return min(accepted or pool, key=lambda r:r.objective), calls


def score_point(task):
    label, phase, xy = task
    path = engine.point_path(label, phase, xy)
    if path.exists():
        return dict(read(path), cache_hit=True)
    assert phase == 'two_starts'
    started = time.monotonic()
    source = control_folder(label) / 'points' / path.name
    if source.exists():
        first = read(source)
        first = dict(first, first_start_reuse=dict(path=str(source), sha256=data.digest(source)))
    else:
        first = BASE_POINT(task)
    out = dict(first, cache_hit=False, two_start_runs=[])
    if first.get('fit'):
        out['two_start_runs'].append(dict(name='geometry-bootstrap', **first['fit']))
    try:
        _, obs, bank, prior, score = engine.context(label, phase)
        seed = engine.bootstrap(first['bootstrap'])
        obj = engine.NativeObjective(obs, bank.select(list(seed.satellite_indices)), prior, score)
        second = BASE_FIT(obj, reset_seed(seed.vector), fixed_position=True,
                          rf_arm='fitted-c', maximum_seconds=5., maximum_iterations=200,
                          slope_half_width_hz_s=60.)
        out['two_start_runs'].append(dict(name='zero-timing-and-slopes', **asdict(second)))
        fits = [engine.PositionFit(**{k:v for k,v in r.items() if k != 'name'}) for r in out['two_start_runs']]
        best = choose_coarse(fits)
        out.update(status='complete', score=best.objective, fit=asdict(best))
    except Exception as error:
        out['second_start_error'] = str(error)
        out['second_start_traceback'] = traceback.format_exc()
    out['actual_elapsed_s'] = time.monotonic() - started
    out['modeled_fit_seconds'] = sum(r['elapsed_s'] for r in out['two_start_runs'])
    out['elapsed_s'] = out['actual_elapsed_s']
    engine.write(path, out)
    return out


def refine_region(task):
    label, phase, xy, radius = task
    path = HERE / 'results' / label / phase / 'regions' / f'{xy[0]:g}_{xy[1]:g}_{radius:g}.json'
    if path.exists() and read(path)['status'] != 'running':
        return read(path)
    if phase == 'rf_offsets':
        from rf_experiment import refine_rf_region
        return refine_rf_region(task)
    if phase == 'two_starts':
        return BASE_REFINE(task)
    source = control_folder(label) / 'regions' / path.name
    original = read(source)
    if original['status'] == 'complete':
        out = dict(original, unchanged_control_region=True,
                   reused_source=dict(path=str(source), sha256=data.digest(source)))
        engine.write(path, out)
        return out
    calls = []
    def retry(obj, start, **kwargs):
        if kwargs.get('fixed_position'):
            result, attempts = recover_fit(obj, start, **kwargs)
            calls.append(dict(attempts=attempts, selected_objective=result.objective,
                              selected_converged=result.converged))
            return result
        return BASE_FIT(obj, start, **kwargs)
    engine.fit_position = retry
    try:
        out = BASE_REFINE(task)
    finally:
        engine.fit_position = BASE_FIT
    out['calibration_recovery_calls'] = calls
    out['control_region_status'] = original['status']
    engine.write(path, out)
    return out


engine.score_point, engine.refine_region = score_point, refine_region


def prepare(labels, phases):
    receipts = {}
    for label in labels:
        engine.CONTEXT[label] = data.load(label)
        target = HERE / 'results' / label / 'bootstrap'
        target.mkdir(parents=True, exist_ok=True)
        for source in (CONTROL / 'results' / label / 'bootstrap').glob('*.json'):
            dest = target / source.name
            if not dest.exists():
                shutil.copyfile(source, dest)
        for phase in phases:
            folder = HERE / 'results' / label / phase
            for sub in ('points', 'regions'):
                (folder / sub).mkdir(parents=True, exist_ok=True)
            if phase == 'two_starts':
                continue
            source = control_folder(label) / 'search.json'
            if not (folder / 'search.json').exists():
                shutil.copyfile(source, folder / 'search.json')
            receipts[str(source)] = data.digest(source)
            for b in read(source)['basins']:
                name = f"{b['east_km']:g}_{b['north_km']:g}.json"
                point = control_folder(label) / 'points' / name
                if not (folder / 'points' / name).exists():
                    shutil.copyfile(point, folder / 'points' / name)
                receipts[str(point)] = data.digest(point)
    return receipts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--labels', nargs='+', default=LABELS)
    parser.add_argument('--phases', nargs='+', choices=list(PHASES), default=['two_starts', 'calibration_retry'])
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--tag', default='basic')
    args = parser.parse_args()
    old_protocol = read(CONTROL / 'protocol.json')
    for path, expected in old_protocol['sources'].items():
        assert data.digest(path) == expected, path
    for root in (CONTROL, SOFT):
        for name, expected in read(root / 'artifact_manifest.json')['files'].items():
            assert data.digest(root / name) == expected, str(root/name)
    sources = dict(old_protocol['sources'])
    paths = [Path(__file__), CONTROL / 'protocol.json', CONTROL / 'artifact_manifest.json']
    if 'rf_offsets' in args.phases:
        paths += [HERE / 'rf_model.py', HERE / 'rf_experiment.py']
    sources.update({str(p):data.digest(p) for p in paths})
    protocol = dict(config=COMMON, phases=args.phases, labels=args.labels,
        c_ablation='Final c only; matched observations, banks, priors, starts and budgets within each variant.',
        two_starts='Geometry bootstrap and independent zero-timing/zero-slope bootstrap, 5 s/200 iterations EACH, 400 distinct grid points.',
        calibration_retry='Only failed calibration calls: one continuation then one zero-timing reset; unchanged strict KKT 0.001.',
        rf_offsets='Final receiver-by-rounded-MHz RF offsets; SD 50 Hz, group bounds +/-150 Hz; orthogonal to receiver constants and shared linear RF c.',
        reference_usage='No reference coordinates loaded by inference.',
        reuse='Exact unchanged control stages reused; all changed downstream stages recomputed.',
        workers=args.workers, sources=sources)
    protocol_path = HERE / f'protocol_{args.tag}.json'
    if protocol_path.exists():
        assert read(protocol_path) == protocol, 'Protocol changed; use a new experiment directory'
    else:
        engine.write(protocol_path, protocol)
    begun = time.monotonic()
    receipts = prepare(args.labels, args.phases)
    engine.write(HERE / f'reuse_{args.tag}.json', receipts)
    print('READY', args.tag, args.labels, args.phases, flush=True)
    with futures.ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context('fork')) as pool:
        with futures.ThreadPoolExecutor(max_workers=min(6, len(args.labels)*len(args.phases))) as threads:
            pending = {threads.submit(engine.run_case, label, phase, pool):(label,phase)
                       for label in args.labels for phase in args.phases}
            results = []
            for future in futures.as_completed(pending):
                try:
                    results.append(future.result())
                except Exception as error:
                    label,phase=pending[future]
                    results.append(dict(label=label,phase=phase,status='failed',error=str(error),traceback=traceback.format_exc()))
                engine.write(HERE / f'progress_{args.tag}.json',dict(completed=len(results),requested=len(pending),
                    elapsed_s=time.monotonic()-begun,cases=[dict(label=r['label'],phase=r['phase'],status=r.get('status','complete')) for r in results]))
    engine.write(HERE / f'results_{args.tag}.json',dict(results=results,elapsed_s=time.monotonic()-begun))
    print('COMPLETE', args.tag, len(results), time.monotonic()-begun, flush=True)


if __name__ == '__main__':
    main()
