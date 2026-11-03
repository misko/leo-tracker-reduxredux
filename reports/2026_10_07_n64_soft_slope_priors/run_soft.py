"""Frozen full-grid N01--N64 experiment. No reference positions are read."""
import concurrent.futures as futures
import json
import multiprocessing
from pathlib import Path
import shutil
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / '2026_10_07_n64_before_after'
PREVIOUS = HERE.parent / '2026_10_07_n64_sigma_slope_variants'
sys.path.insert(0, str(OLD))
import experiment as engine
import data
from slope_penalty import PenalizedObjective, annotate_region

LABELS = [f'N{i:02d}' for i in range(1, 65)]
COMMON = dict(sigma=2., levels=[40., 20., 10., 5.], edge='nearest')
PHASES = {
    'hard30': dict(COMMON, width=30., slope_prior=dict(kind='none')),
    'gaussian60': dict(COMMON, width=60., slope_prior=dict(kind='gaussian', scale=20.)),
    'smooth60': dict(COMMON, width=60., slope_prior=dict(kind='smooth', onset=30., scale=10.)),
    'gaussian30': dict(COMMON, width=30., slope_prior=dict(kind='gaussian', scale=10.)),
    'smooth30': dict(COMMON, width=30., slope_prior=dict(kind='smooth', onset=15., scale=5.)),
}
BASE_CONTEXT = engine.context
BASE_REFINE = engine.refine_region
BASE_NATIVE = engine.NativeObjective
BASE_ORACLE = engine.PositionObjective
ACTIVE_PHASE = None


def context(label, phase):
    global ACTIVE_PHASE
    ACTIVE_PHASE = phase
    return BASE_CONTEXT(label, phase)


def native_objective(*args, **kwargs):
    assert ACTIVE_PHASE in PHASES
    return PenalizedObjective(BASE_NATIVE(*args, **kwargs), PHASES[ACTIVE_PHASE]['slope_prior'])


def original_objective(*args, **kwargs):
    assert ACTIVE_PHASE in PHASES
    return PenalizedObjective(BASE_ORACLE(*args, **kwargs), PHASES[ACTIVE_PHASE]['slope_prior'])


def refine_region(task):
    label, phase, xy, radius = task
    result = annotate_region(BASE_REFINE(task), PHASES[phase]['slope_prior'])
    path = HERE / 'results' / label / phase / 'regions' / f'{xy[0]:g}_{xy[1]:g}_{radius:g}.json'
    engine.write(path, result)
    return result


engine.HERE = HERE
engine.PHASES = PHASES
engine.context = context
engine.NativeObjective = native_objective
engine.PositionObjective = original_objective
engine.refine_region = refine_region


def pinned_protocol():
    old = json.loads((PREVIOUS / 'protocol.json').read_text())
    for path, expected in old['sources'].items():
        assert data.digest(path) == expected, path
    manifest = json.loads((PREVIOUS / 'artifact_manifest.json').read_text())
    for name, expected in manifest['files'].items():
        assert data.digest(PREVIOUS / name) == expected, name
    sources = dict(old['sources'])
    paths = [Path(__file__), HERE / 'slope_penalty.py', PREVIOUS / 'protocol.json',
             PREVIOUS / 'artifact_manifest.json', PREVIOUS / 'summary.json', PREVIOUS / 'validation.json']
    sources.update({str(p): data.digest(p) for p in paths})
    return dict(old, phases=PHASES, sources=sources, previous_results=str(PREVIOUS),
        slope_prior_scope='Separate fitted affine terms at coarse/calibration/final stages; not total physical receiver drift.',
        slope_prior_score='Final penalized objective + original piecewise calibration penalty + one frozen postfit affine prior. No prefit double count.',
        comparison=['before', 'after', 'sigma2_60', 'sigma1_30', *PHASES],
        controlled_reference='sigma2_60; hard30 provides the matched sigma=2, +/-30 control',
        bootstrap_reuse='Copied verified geometry-only seeds from the preceding report; all scores and fitted states recomputed.')


def prepare_seeds():
    path = HERE / 'bootstrap_reuse.json'
    if path.exists():
        receipt = json.loads(path.read_text())
        for relative, expected in receipt['files'].items():
            assert data.digest(PREVIOUS / relative) == expected, relative
            assert data.digest(HERE / relative) == expected, relative
        return
    files = {}
    for label in LABELS:
        target = HERE / 'results' / label / 'bootstrap'
        target.mkdir(parents=True, exist_ok=True)
        for source in sorted((PREVIOUS / 'results' / label / 'bootstrap').glob('*.json')):
            relative = source.relative_to(PREVIOUS)
            expected = data.digest(source)
            destination = HERE / relative
            if destination.exists():
                assert data.digest(destination) == expected
            else:
                shutil.copyfile(source, destination)
            files[str(relative)] = expected
    engine.write(path, dict(files=files, count=len(files)))


def main():
    protocol = pinned_protocol()
    path = HERE / 'protocol.json'
    if path.exists():
        assert json.loads(path.read_text()) == protocol, 'Protocol changed; do not mix caches'
    else:
        engine.write(path, protocol)
    start = time.monotonic()
    prepare_seeds()
    for label in LABELS:
        assert data.digest(OLD / 'inputs' / label / 'inputs.json') == protocol['input_metadata'][label]
        engine.CONTEXT[label] = data.load(label)
        for phase in PHASES:
            for sub in ('points', 'regions'):
                (HERE / 'results' / label / phase / sub).mkdir(parents=True, exist_ok=True)
    print('INPUTS LOADED', len(engine.CONTEXT), 'seconds', time.monotonic() - start, flush=True)
    with futures.ProcessPoolExecutor(max_workers=20, mp_context=multiprocessing.get_context('fork')) as pool:
        [f.result() for f in [pool.submit(engine.warm) for _ in range(20)]]
        with futures.ThreadPoolExecutor(max_workers=12) as threads:
            pending = {threads.submit(engine.run_case, label, phase, pool): (label, phase)
                       for label in LABELS for phase in PHASES}
            results = []
            for future in futures.as_completed(pending):
                try:
                    results.append(future.result())
                except Exception as error:
                    label, phase = pending[future]
                    results.append(dict(label=label, phase=phase, status='failed', error=str(error), traceback=traceback.format_exc()))
                engine.write(HERE / 'run_progress.json', dict(completed=len(results), requested=320,
                    elapsed_s=time.monotonic() - start,
                    cases=[dict(label=r['label'], phase=r['phase'], status=r.get('status', 'complete')) for r in results]))
    engine.write(HERE / 'results.json', dict(results=results, elapsed_s=time.monotonic() - start))
    print('COMPLETE', len(results), 'seconds', time.monotonic() - start, flush=True)


if __name__ == '__main__':
    main()
