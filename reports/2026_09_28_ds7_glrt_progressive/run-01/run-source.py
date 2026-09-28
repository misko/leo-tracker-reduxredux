"""Single-core saved-IQ experiment; fresh baselines, no RF or storage writes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import signal
import sys
import time

import numpy as np
from pydantic import TypeAdapter
from leo.scanner.models import ScannerConfiguration, ScanTarget

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BASE = HERE.parent / '2026_09_28_ds7_glrt_benchmark'
sys.path.insert(0, str(BASE))
from methods import make_method as make_baseline
from run import validate_inputs

METHODS = ['original', 'optimized', 'candidates4', 'candidates6',
           'windows6', 'windows4', 'windows3', 'windows6_candidates2',
           'windows4_candidates2', 'progressive4']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deadline(_sig, _frame):
    raise TimeoutError('bounded replay exceeded 2400 seconds')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from methods_sparse import make_method
    plan_path = BASE / 'plan.json'
    plan = json.loads(plan_path.read_text())
    inputs = json.loads((args.inputs / 'inputs.json').read_text())
    validate_inputs(plan, inputs, plan_path)
    os.sched_setaffinity(0, {0})
    dependencies = [Path(__file__), HERE / 'methods_sparse.py', BASE / 'methods.py',
                    BASE / 'run.py', BASE / 'scoring.py', plan_path,
                    BASE.parent / '2026_09_27_server_scan_speed/pilot_methods_baseline.py',
                    BASE.parent / '2026_09_27_server_scan_speed/acquisition_peak/original/acquisition.py']
    dependencies += sorted((REPO / 'src/leo/analysis/starlink').glob('*.py'))
    dependencies += sorted((REPO / 'src/leo/analysis/starlink').glob('*.so'))
    dependencies += [REPO / 'src/leo/scanner/detector.py', REPO / 'src/leo/scanner/models.py']
    hashes = {str(p): sha(p) for p in dependencies}
    args.output.mkdir(parents=True, exist_ok=False)
    header = {'schema': 'ds7-glrt-run/v1', 'complete': False, 'sources_unchanged': False,
              'methods': METHODS, 'repetitions': 2, 'planned_calls': len(inputs['rows']) * len(METHODS) * 2,
              'plan_sha256': sha(plan_path), 'input_manifest_sha256': sha(args.inputs / 'inputs.json'),
              'dataset_sha256': plan['dataset_sha256'], 'source_hashes': hashes,
              'python': sys.version, 'numpy': np.__version__, 'platform': platform.platform(),
              'affinity': sorted(os.sched_getaffinity(0)),
              'threads': {k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS')},
              'scope': 'resident CI16 conversion plus detector; no IO or output serialization timed; no RF',
              'failed_calls': 0, 'calls': 0}
    receipt = args.output / 'run.json'
    receipt.write_text(json.dumps(header, indent=2) + '\n')
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(2400)
    started = time.monotonic()
    try:
        with (args.output / 'rows.jsonl').open('x') as output:
            for repeat in range(2):
                workers = {n: make_baseline(n) if n in ('original', 'optimized') else make_method(n)
                           for n in METHODS}
                for ordinal, context in enumerate(inputs['rows']):
                    path = args.inputs / context['file']
                    if path.parent.resolve() != args.inputs.resolve() or sha(path) != context['sha256']:
                        raise ValueError('input payload binding')
                    iq = np.load(path, allow_pickle=False)
                    if list(iq.shape) != context['shape'] or str(iq.dtype) != context['dtype']:
                        raise ValueError('input geometry')
                    rate = context['rate_hz']
                    duration = iq.shape[0] * 1000 / rate
                    if duration != int(duration):
                        raise ValueError('nonintegral dwell')
                    config = ScannerConfiguration(sample_rate_hz=rate, bandwidth_hz=rate,
                        dwell_ms=int(duration), targets=(ScanTarget.model_validate(context['target']),))
                    shift = (ordinal + repeat) % len(METHODS)
                    for name in METHODS[shift:] + METHODS[:shift]:
                        cpu = time.process_time()
                        wall = time.perf_counter()
                        try:
                            samples = np.empty(iq.shape[:2], dtype=np.complex64)
                            samples.real = iq[:, :, 0]
                            samples.imag = iq[:, :, 1]
                            got = workers[name].analyze(samples, config, context['target']['edge'], context)
                            timing = {'cpu_s': time.process_time() - cpu, 'wall_s': time.perf_counter() - wall}
                            result = TypeAdapter(type(got.analysis)).dump_python(got.analysis, mode='json')
                            row = {'context': context, 'method': name, 'repeat': repeat, 'status': 'ok',
                                   'result': result, 'diagnostics': got.diagnostics, 'timing': timing}
                        except Exception as exc:
                            row = {'context': context, 'method': name, 'repeat': repeat, 'status': 'failed',
                                   'result': None, 'diagnostics': {'error': repr(exc)},
                                   'timing': {'cpu_s': time.process_time() - cpu,
                                              'wall_s': time.perf_counter() - wall}}
                            header['failed_calls'] += 1
                        output.write(json.dumps(row, allow_nan=False) + '\n')
                        output.flush()
                        header['calls'] += 1
                    print(json.dumps({'repeat': repeat, 'rate': rate, 'visit': context['visit_index'],
                                      'calls': header['calls'], 'failures': header['failed_calls']}), flush=True)
        header['sources_unchanged'] = all(sha(Path(p)) == h for p, h in hashes.items())
        header['complete'] = (header['calls'] == header['planned_calls']
                              and not header['failed_calls'] and header['sources_unchanged'])
        if not header['complete']:
            raise RuntimeError('incomplete, failed, or changed-source run')
    except BaseException as exc:
        header['error'] = repr(exc)
        raise
    finally:
        signal.alarm(0)
        header['wall_s'] = time.monotonic() - started
        header['peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        receipt.write_text(json.dumps(header, indent=2) + '\n')


if __name__ == '__main__':
    main()
