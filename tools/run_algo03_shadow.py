"""Run a bounded shadow canary from the public completed-analysis export port."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from leo.storage.fast_graph_position import FastGraphPositionStore
from algo03_shadow_worker import POLICY, read, write

ROOT = Path(__file__).resolve().parents[1]


def check_read_audit(output, pid, *, supervisor_pid=None):
    supervisor_pid = os.getpid() if supervisor_pid is None else supervisor_pid
    receipts = [read(p) for p in (output / 'read_receipts').glob('*.json')]
    observed = {r['pid'] for r in receipts}
    expected = 1 + sum(len(r['python_spawns']) for r in receipts)
    valid = (pid in observed and len(receipts) == len(observed) == expected
             and not any(r['denied_paths'] for r in receipts)
             and all(r['parent_pid'] in observed | {supervisor_pid} for r in receipts)
             and [r['pid'] for r in receipts if r['parent_pid'] == supervisor_pid] == [pid])
    return dict(verified=valid, receipts=len(receipts), expected=expected,
                root_process_id=pid, supervisor_process_id=supervisor_pid,
                all_launched_processes_accounted=valid,
                denied_paths=sorted({p for r in receipts for p in r['denied_paths']}),
                source_scope='isolated ALGO02 export and current recovery artifacts only')


def run(args):
    if not 1 <= args.maximum_seconds <= 1200:
        raise ValueError('Recovery budget must be 1..1200s')
    began = time.monotonic()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    store = FastGraphPositionStore(args.bulk_root)
    job = store.status(args.job)
    if not job or job['state'] != 'complete':
        raise ValueError('Completed production job required')
    manifest_path = ROOT / 'reports/ALGO03/releases/2026-10-30-r1/manifest.json'
    manifest = read(manifest_path)
    # Preserve the frozen scientific release; adapter changes are separately hashed.
    release_hashes = manifest['sha256']
    for name, expected in release_hashes.items():
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('Frozen ALGO03 release changed: ' + name)
    descriptor = store.export_analysis(job, output / 'snapshot')
    write(output / 'launch.json', dict(policy=POLICY, job_id=args.job,
          maximum_seconds=args.maximum_seconds, frozen_release=manifest.get('release_id'),
          release_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
          adapter_hashes={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
                         ('tools/algo03_shadow_worker.py', 'tools/run_algo03_shadow.py',
                          'src/leo/storage/fast_graph_position.py')},
          shadow_only=True, production_changed=False))
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                       OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
                       PYTHONPATH=os.pathsep.join(map(str, (ROOT / 'deploy/fast_graph_guard',
                                                           ROOT / 'src', ROOT / 'tools'))),
                       LEO_FAST_GRAPH_RUN_ROOT=str(output),
                       LEO_FAST_GRAPH_INPUT=str(output / 'snapshot/inference/SCAN/tracking.json'),
                       LEO_FAST_GRAPH_SOURCE_ROOT=str(ROOT),
                       LEO_FAST_GRAPH_TLE_ROOT=str(output / 'unused-tle-archive'),
                       MPLCONFIGDIR=str(output / 'matplotlib-cache'))
    command = [sys.executable, '-B', str(ROOT / 'tools/algo03_shadow_worker.py'),
               '--output', str(output), '--maximum-seconds', str(args.maximum_seconds)]
    with (output / 'worker.log').open('xb') as log:
        # Every scientific child has its own bounded process-group supervisor.
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                 cwd=ROOT, env=environment)
        try:
            code = child.wait(timeout=args.maximum_seconds + 30)
        except subprocess.TimeoutExpired:
            child.terminate()
            try:
                code = child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                code = child.wait()
    audit = check_read_audit(output, child.pid)
    if code == 0 and (output / 'decision.json').exists():
        result = read(output / 'decision.json')
    else:
        result = dict(decision='ALGO02_fallback', selected=None, failure='Worker failed',
                      baseline=descriptor['terminal'])
    if not audit['verified']:
        result.update(decision='ALGO02_fallback', selected=None, failure='Incomplete or denied read audit')
    if result.get('selected'):
        for path, expected in result['selected']['source_receipts'].items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
                result.update(decision='ALGO02_fallback', selected=None, failure='Scientific receipt changed')
                break
    result.update(read_audit=audit, total_seconds=time.monotonic() - began,
                  production_changed=False, shadow_only=True, job_id=args.job)
    write(output / 'terminal.json', result)
    print(json.dumps(dict(job_id=args.job, decision=result['decision'],
                          seconds=result['total_seconds'], failure=result.get('failure'))), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bulk-root', type=Path, required=True)
    parser.add_argument('--job', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--maximum-seconds', type=int, default=1200)
    run(parser.parse_args())
