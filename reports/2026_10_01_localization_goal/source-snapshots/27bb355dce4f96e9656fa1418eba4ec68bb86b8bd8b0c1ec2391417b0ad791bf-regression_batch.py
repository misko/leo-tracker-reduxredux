"""Explicit eight-scan batches, two workers, externally enforced 90-second cap."""
import argparse
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FREEZE = HERE/'regression-v1-freeze.json'


def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_sources(bindings):
    for path, expected in bindings.items():
        if digest(path) != expected:
            raise ValueError('frozen source changed: '+path)


def execute(command, directory, unit, *, timeout_s=90., env=None):
    directory = Path(directory)
    launch_path = directory/(unit+'.launch.json')
    if launch_path.exists():
        raise FileExistsError(launch_path)
    begin = time.monotonic()
    launched_utc = datetime.now(UTC).isoformat()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True, env=env, cwd=ROOT)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # The process may exit between timeout and group termination.
        stdout, stderr = process.communicate()
    elapsed = time.monotonic()-begin
    (directory/(unit+'.stdout.txt')).write_bytes(stdout)
    (directory/(unit+'.stderr.txt')).write_bytes(stderr)
    result = dict(unit_id=unit, command=command, pid=process.pid, started_utc=launched_utc,
                  finished_utc=datetime.now(UTC).isoformat(),
                  elapsed_seconds=elapsed, external_limit_seconds=timeout_s,
                  timed_out=timed_out, returncode=process.returncode,
                  within_budget=not timed_out and elapsed <= timeout_s)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', required=True, type=int, choices=range(1, 9))
    args = parser.parse_args()
    freeze = json.loads(FREEZE.read_text())
    if digest(FREEZE) != FREEZE.with_suffix('.sha256').read_text().strip():
        raise ValueError('freeze digest mismatch')
    verify_sources(freeze['source_sha256'])
    directory = HERE/'regression-v1'/f'batch-{args.batch:02d}'
    directory.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, PYTHONPATH=str(ROOT/'src'), OPENBLAS_NUM_THREADS='1',
               OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
    units = freeze['ordered_units'][(args.batch-1)*8:args.batch*8]

    def run(unit):
        verify_sources(freeze['source_sha256'])
        output = directory/(unit+'.json')
        command = [sys.executable, str(HERE/'run_fast_pipeline.py'), unit,
                   '--arm', 'hard', '--output', str(output)]
        launch = execute(command, directory, unit, env=env)
        verify_sources(freeze['source_sha256'])
        launch['freeze_sha256'] = digest(FREEZE)
        launch['receipt_sha256'] = digest(output) if output.exists() else None
        with (directory/(unit+'.launch.json')).open('x') as stream:
            json.dump(launch, stream, indent=2)
        status = json.loads(output.read_text())['status'] if output.exists() else 'no_receipt'
        print(json.dumps(dict(unit=unit, status=status, seconds=launch['elapsed_seconds'],
                              within_budget=launch['within_budget'])), flush=True)
        return launch

    # This advisory lock covers every new regression batch in this experiment.
    # Other diagnostic fits must not be launched alongside a running batch.
    with (HERE/'.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, unit) for unit in units]
            results = [future.result() for future in as_completed(futures)]
        with (directory/'batch.json').open('x') as stream:
            json.dump(dict(batch=args.batch, planned_units=units, launches=results,
                           freeze_sha256=digest(FREEZE)), stream, indent=2)


if __name__ == '__main__':
    main()
