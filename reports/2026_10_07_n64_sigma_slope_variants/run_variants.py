"""Two additional controlled V16 passes over the frozen N01--N64 cohort.

The original experiment is reused without changing its numerical implementation.
Only position/geometry bootstrap seeds are reused; point scores and fitted states
are recomputed. Reference coordinates are never read by this driver.
"""
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
sys.path.insert(0, str(OLD))
import experiment as engine
import data

PHASES = {
    'sigma2_60': dict(sigma=2., width=60., levels=[40., 20., 10., 5.], edge='nearest'),
    'sigma1_30': dict(sigma=1., width=30., levels=[40., 20., 10., 5.], edge='nearest'),
}
LABELS = [f'N{i:02d}' for i in range(1, 65)]
engine.HERE = HERE
engine.PHASES = PHASES


def pinned_protocol():
    old = json.loads((OLD / 'protocol.json').read_text())
    for path, expected in old['sources'].items():
        assert data.digest(path) == expected, path
    manifest = json.loads((OLD / 'artifact_manifest.json').read_text())
    for name, expected in manifest['files'].items():
        assert data.digest(OLD / name) == expected, name
    sources = dict(old['sources'])
    for path in [Path(__file__), OLD / 'protocol.json', OLD / 'artifact_manifest.json',
                 OLD / 'summary.json', OLD / 'results.json', OLD / 'validation.json']:
        sources[str(path)] = data.digest(path)
    return {**old, 'phases': PHASES, 'sources': sources,
            'input_metadata': manifest['input_metadata'],
            'previous_results': str(OLD),
            'bootstrap_reuse': 'Copied, hash-pinned geometry-only seeds; no old fitted states or scores.',
            'comparison': ['before', 'after', 'sigma2_60', 'sigma1_30']}


def prepare_seeds():
    """Copy immutable geometry seeds into this run's writable cache once."""
    path = HERE / 'bootstrap_reuse.json'
    if path.exists():
        receipt = json.loads(path.read_text())
        for relative, expected in receipt['files'].items():
            assert data.digest(OLD / relative) == expected, relative
            assert data.digest(HERE / relative) == expected, relative
        return
    files = {}
    for label in LABELS:
        target = HERE / 'results' / label / 'bootstrap'
        target.mkdir(parents=True, exist_ok=True)
        for source in sorted((OLD / 'results' / label / 'bootstrap').glob('*.json')):
            relative = source.relative_to(OLD)
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
        assert json.loads(path.read_text()) == protocol, 'Protocol changed; do not mix caches.'
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
                    results.append(dict(label=label, phase=phase, status='failed',
                                        error=str(error), traceback=traceback.format_exc()))
                engine.write(HERE / 'run_progress.json', dict(
                    completed=len(results), requested=128, elapsed_s=time.monotonic() - start,
                    cases=[dict(label=r['label'], phase=r['phase'], status=r.get('status', 'complete'))
                           for r in results]))
    engine.write(HERE / 'results.json', dict(results=results, elapsed_s=time.monotonic() - start))
    print('COMPLETE', len(results), 'seconds', time.monotonic() - start, flush=True)


if __name__ == '__main__':
    main()
