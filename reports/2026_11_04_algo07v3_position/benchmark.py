"""Same-CPU ABBA measurement of a bounded position-component oracle workload.

This is not the full initial hypothesis search or the complete ALGO07 pipeline.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    if args.cpu not in os.sched_getaffinity(0):
        raise ValueError('Selected CPU is not available')
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for number, side in enumerate(('reference', 'candidate', 'candidate', 'reference'), 1):
        output = args.output/f'trial{number}.json'
        command = [str(args.reference_python) if side == 'reference' else sys.executable,
                   '-B', str(args.repo/'tools/check_algo07v3_position.py'), '--side', side,
                   '--source', str(args.reference_input if side == 'reference'
                                    else args.candidate_input), '--output', str(output),
                   '--search-center', '37.906', '-122.545', '--rounds', '1', '--iterations', '4']
        if side == 'reference':
            command += ['--reference-runtime', str(args.reference_runtime)]
        else:
            command = ['unshare', '--mount', '--propagation', 'private', 'sh', '-c',
                       'mount -t tmpfs -o ro,size=1m tmpfs /opt && exec "$@"',
                       'isolated-v3', *command]
        command = ['taskset', '-c', str(args.cpu), *command]
        env = dict(os.environ, PYTHONPATH=str(args.repo/'src'), OPENBLAS_NUM_THREADS='1',
                   OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
        start = time.monotonic()
        with (args.output/f'trial{number}.log').open('x') as log:
            subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                           timeout=180, check=True)
        wall = time.monotonic()-start
        row = dict(trial=number, side=side, wall_seconds=wall, output_sha256=digest(output),
                   receipt_sha256=digest(output.with_suffix('.receipt.json')))
        rows.append(row)
        print(json.dumps(row), flush=True)
    result = dict(scope='One zero-calibration hypothesis, both arms, 1 phase round × 4 iterations',
                  cpu=args.cpu, rows=rows, exact=len({r['output_sha256'] for r in rows}) == 1,
                  complete_pipeline_speedup_established=False)
    (args.output/'benchmark.json').write_text(json.dumps(result, indent=2)+'\n')
    if not result['exact']:
        raise ValueError('Bounded workload differs')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'reference-runtime', 'reference-python', 'reference-input',
                 'candidate-input', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--cpu', type=int, required=True)
    run(parser.parse_args())
