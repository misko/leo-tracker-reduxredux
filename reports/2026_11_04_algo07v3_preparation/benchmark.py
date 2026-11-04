"""Bounded ABBA preparation timing; no localization or end-to-end speed claim."""
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
    args.output.mkdir(parents=True, exist_ok=False)
    files = [*sorted((args.repo/'src/leo/analysis/localization_v3').glob('*.py')),
             args.repo/'src/leo/application/localization_v3.py',
             args.repo/'src/leo/operations/localization_v3_inputs.py',
             args.repo/'src/leo/operations/causal_tle_catalogue.py',
             args.repo/'tools/prepare_algo07v3_inputs.py']
    pins = {str(p):digest(p) for p in files}
    native_sha = digest(args.native)
    config = args.repo/'deploy/config/fast-graph-tracklets-v1.json'
    config_sha = digest(config)
    rows = []
    env = dict(os.environ, PYTHONPATH=str(args.repo/'src'), OPENBLAS_NUM_THREADS='1',
               OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
    for i, cached in enumerate((False, True, True, False)):
        output = args.output/f'trial{i+1}'
        command = [sys.executable, '-B', str(args.repo/'tools/prepare_algo07v3_inputs.py'),
                   '--native-input', str(args.native), '--input-sha256', 'sha256:'+native_sha,
                   '--track-config', str(config), '--tle-root', str(args.archive),
                   '--screen-latitude', '37.5', '--screen-longitude', '-122.0',
                   '--output', str(output)]
        if not cached:
            command.append('--no-element-cache')
        start = time.monotonic()
        with (args.output/f'trial{i+1}.log').open('x') as log:
            result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=300, check=True)
        wall = time.monotonic()-start
        summary = json.loads((output/'summary.json').read_text())
        rows.append(dict(trial=i+1, cached=cached, wall_seconds=wall,
                         preparation_seconds=summary['elapsed_seconds'],
                         cache=summary['element_cache'], returncode=result.returncode,
                         summary_sha256=digest(output/'summary.json')))
        print(json.dumps(rows[-1]), flush=True)
    unchanged = pins == {str(p):digest(p) for p in files}
    if not unchanged or digest(args.native) != native_sha or digest(config) != config_sha:
        raise ValueError('Benchmark sources or inputs changed')
    value = dict(scope='Native input to standalone persisted preparation; no position fit',
                  rows=rows, sources=pins, native_sha256=native_sha, config_sha256=config_sha,
                  full_pipeline_speedup_established=False, scientific_comparison_pending=True)
    (args.output/'benchmark.json').write_text(json.dumps(value, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'native', 'archive', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    run(parser.parse_args())
