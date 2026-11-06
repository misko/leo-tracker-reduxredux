"""Bounded sequential continuation; never overlap native pairs or grid timings."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def process_identity(pid):
    path = Path(f'/proc/{pid}/stat')
    try:
        fields = path.read_text().rsplit(')', 1)[1].split()
    except FileNotFoundError:
        return None
    return None if fields[0] == 'Z' else fields[19]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--short', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--captures', type=Path, required=True)
    parser.add_argument('--grids', type=Path, required=True)
    args = parser.parse_args()
    identity, started = process_identity(args.pid), time.monotonic()
    print(f'Waiting for existing coordinator {args.pid}, identity {identity}', flush=True)
    while identity is not None and process_identity(args.pid) == identity:
        if time.monotonic() - started > 2400:
            raise TimeoutError('Existing native comparison did not finish within bounded wait')
        time.sleep(10)
    comparison = json.loads((args.after / 'comparison.json').read_bytes())
    assert comparison['exact_owned_science_and_artifacts']
    print('Hard native comparison complete and exact; starting inactive-joint pair', flush=True)
    command = [sys.executable, '-B', str(Path(__file__).with_name('run_inactive_pair.py')),
               '--root', str(args.short), '--request', str(args.request)]
    # Each native worker has its own process-group supervisor and 1200 s limit.
    subprocess.run(command, check=True)
    comparison = json.loads((args.short / 'comparison.json').read_bytes())
    assert comparison['exact_owned_science_and_artifacts']
    print('Both native pairs exact; starting alternating actual-grid timings', flush=True)
    command = ['taskset', '-c', '0,1,2', sys.executable, '-B',
               'tools/benchmark_algo07v3_direct_grids.py', '--variant', 'owned-lu',
               '--native', str(args.captures), '--output', str(args.grids)]
    started = time.monotonic()
    with args.grids.with_suffix('.log').open('xb') as stream:
        subprocess.run(command, check=True, timeout=300, stdout=stream, stderr=subprocess.STDOUT)
    args.grids.with_suffix('.supervisor.json').write_text(json.dumps(dict(
        status='exited', returncode=0, process_seconds=time.monotonic() - started,
        timeout_seconds=300, command=command), indent=2))
    print('All qualification and grid timing jobs complete', flush=True)


if __name__ == '__main__':
    main()
