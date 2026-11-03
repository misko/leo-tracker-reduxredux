"""Alternate isolated implementations per saved window on the same host CPU."""

import argparse
import importlib.util
import json
import multiprocessing
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path


def initialize(source, cpu):
    global PROFILE, DIAGNOSTICS
    DIAGNOSTICS = []
    os.sched_setaffinity(0, {cpu})
    path = Path(__file__).resolve().parents[2]/'tools/profile_algo07_glrt.py'
    spec = importlib.util.spec_from_file_location('native_profile', path)
    PROFILE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(PROFILE)
    PROFILE.use_source(Path(source))
    # Import outside the per-window timer.
    from leo.scanner.fast_scan_analysis import production_glrt  # noqa: F401
    try:
        from leo.analysis.starlink import coarse_screen
    except ImportError:
        pass
    else:
        from leo.analysis.starlink._screen_native import _native_acquisition  # noqa: F401

        original = coarse_screen.acquire

        def observed(*args, **kwargs):
            return original(*args, **kwargs, observer=DIAGNOSTICS.append)

        coarse_screen.acquire = observed


def evaluate(fixture, item):
    import numpy as np

    from leo.scanner.fast_scan_analysis import VerifiedFastWindow, production_glrt

    window = VerifiedFastWindow(item['sequence'], item['iq_sha256'], item['acquisition'],
                                item['target'], np.load(Path(fixture)/item['samples'],
                                                        allow_pickle=False),
                                item['sample_rate_hz'])
    first_diagnostic = len(DIAGNOSTICS)
    wall, cpu = time.perf_counter(), time.process_time()
    receivers = production_glrt(window, tuple(item['receiver_ids']))
    seconds, cpu_seconds = time.perf_counter()-wall, time.process_time()-cpu
    expected = {p['receiver_id']: p['candidates'] for p in item['expected_probes']}
    assert all(PROFILE.published_candidates(r) == expected[r.receiver_id] for r in receivers)
    return dict(seconds=seconds, cpu_seconds=cpu_seconds,
                screening=DIAGNOSTICS[first_diagnostic:],
                receivers=[r.model_dump(mode='json') for r in receivers])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve().is_relative_to('/mnt/qnap01'):
        raise ValueError('New isolated output required')
    os.environ.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
                      PYTHONDONTWRITEBYTECODE='1')
    cpu = min(os.sched_getaffinity(0))
    rows = []
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('spawn'),
                             initializer=initialize, initargs=(str(args.base), cpu)) as baseline, \
         ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('spawn'),
                             initializer=initialize,
                             initargs=(str(args.candidate), cpu)) as candidate:
        for i, item in enumerate(json.loads((args.fixture/'input.json').read_text())['windows']):
            order = [('baseline', baseline), ('candidate', candidate)]
            if i % 2:
                order.reverse()
            result = {name: pool.submit(evaluate, str(args.fixture), item).result(timeout=60)
                      for name, pool in order}
            assert result['baseline']['receivers'] == result['candidate']['receivers']
            rows.append(dict(visit=item['visit'], channel=item['target']['channel'],
                             order=[name for name, _ in order], exact=True,
                             **{name: {k: v for k, v in data.items() if k != 'receivers'}
                                for name, data in result.items()}))
            print(json.dumps(rows[-1]), flush=True)
    summary = dict(cpu_affinity=cpu, cprofile=False, rows=rows, all_receiver_outputs_exact=True,
                   timing='alternating implementations per window; imports and IQ load excluded',
                   totals={name: sum(r[name]['seconds'] for r in rows)
                           for name in ('baseline', 'candidate')})
    with args.output.open('x') as stream:
        json.dump(summary, stream, indent=2)
