"""Ordered process-isolated dispatch with one global 45-minute wall cap."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import time

from common import (binding, digest, job_key, load_sealed, read, result_path, write_new)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def approved(path, protocol_sha256):
    receipt = read(path)
    if receipt.get('approved') is not True or receipt.get('movement_protocol_sha256') != protocol_sha256:
        raise ValueError('launch approval missing or refers to another scientific protocol')
    return binding(path)


def select_workers(max_rss_kib, preflight):
    return 6 if preflight['allocated_cpu_capacity'] >= 8 and 6 * max_rss_kib * 1024 < preflight['memory_available_bytes'] / 2 else 2


def main(root, coordinator_go, audit_go):
    root = Path(root).resolve()
    protocol = load_sealed(root)
    protocol_sha = digest(root/'protocol.json')
    approvals = [approved(path, protocol_sha) for path in (coordinator_go, audit_go)]
    if any((root/name).exists() for name in ('batch_start.json', 'execution.json', 'results', 'claims')):
        raise ValueError('refuse to relaunch or resume an executed scientific version')
    preflight = read(root.parent/'preflight.json')
    env = os.environ.copy()
    env.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
    jobs = protocol['jobs']
    started = time.monotonic()
    deadline = started + protocol['batch_seconds_cap']
    write_new(root/'batch_start.json', dict(utc=utc_now(), monotonic=started, deadline_monotonic=deadline,
        batch_seconds_cap=protocol['batch_seconds_cap'], protocol_sha256=protocol_sha, approvals=approvals,
        resources=binding(root.parent/'preflight.json'), initial_workers=2))
    active, receipts = {}, []
    cursor, capacity, smoke_done, smoke_rss = 0, 2, False, []
    cap_reached = False

    def launch(job):
        key = job_key(**job)
        path = root/'logs'/(key+'.log')
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = path.open('x')
        cmd = [sys.executable, '-B', str(root/'movement.py'), '--root', str(root),
            '--case', job['case'], '--seed', str(job['seed']), '--fold', str(job['fold'])]
        process = subprocess.Popen(cmd, stdout=stream, stderr=subprocess.STDOUT, env=env)
        active[key] = dict(process=process, stream=stream, job=job, started=time.monotonic(), utc=utc_now())
        print('launch', key, 'pid', process.pid, 'capacity', capacity, flush=True)

    while cursor < len(jobs) or active:
        now = time.monotonic()
        if now >= deadline:
            cap_reached = True
            break
        # The first two jobs form a complete resource smoke barrier before expansion.
        dispatch_limit = len(jobs) if smoke_done else 2
        while cursor < dispatch_limit and len(active) < capacity:
            launch(jobs[cursor])
            cursor += 1
        for key, running in list(active.items()):
            process = running['process']
            returncode = process.poll()
            if returncode is None:
                continue
            running['stream'].close()
            job = running['job']
            path = result_path(root, **job)
            if not path.exists():
                write_new(path, dict(**job, status='process_failed', error=f'worker exited {returncode} before a result',
                    protocol_sha256=protocol_sha, GPS_used=False, arms={}, seconds=time.monotonic()-running['started']))
            result = read(path)
            receipt = dict(**job, pid=process.pid, returncode=returncode, launch_utc=running['utc'],
                process_seconds=time.monotonic()-running['started'], status=result['status'],
                peak_rss_kib=result.get('peak_rss_kib'), result=binding(path))
            write_new(root/'receipts'/(key+'.json'), receipt)
            receipts.append(receipt)
            if not smoke_done and result.get('peak_rss_kib') is not None:
                smoke_rss.append(result['peak_rss_kib'])
            del active[key]
            print('finished', key, result['status'], 'count', len(receipts), flush=True)
        if not smoke_done and cursor == 2 and not active:
            # Unknown RSS cannot justify expansion; scientific signs never enter this decision.
            capacity = select_workers(max(smoke_rss), preflight) if len(smoke_rss) == 2 else 2
            write_new(root/'resource_decision.json', dict(smoke_jobs=protocol['smoke_jobs'],
                peak_rss_kib=smoke_rss, workers=capacity, rule=protocol['resource_rule'],
                preflight=binding(root.parent/'preflight.json'), scientific_outcomes_used=False))
            smoke_done = True
            print('resource decision: movement workers', capacity, flush=True)
        time.sleep(.1)
    if cap_reached:
        for running in active.values():
            running['process'].terminate()
        for key, running in active.items():
            process = running['process']
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            running['stream'].close()
            path = result_path(root, **running['job'])
            if not path.exists():
                write_new(path, dict(**running['job'], status='batch_interrupted', GPS_used=False,
                    protocol_sha256=protocol_sha, arms={}, error='frozen 2700-second batch cap',
                    seconds=time.monotonic()-running['started']))
            receipt = dict(**running['job'], pid=process.pid, returncode=process.returncode,
                launch_utc=running['utc'], process_seconds=time.monotonic()-running['started'],
                status=read(path)['status'], result=binding(path))
            write_new(root/'receipts'/(key+'.json'), receipt)
            receipts.append(receipt)
        for job in jobs[cursor:]:
            path = result_path(root, **job)
            write_new(path, dict(**job, status='batch_not_started', GPS_used=False, protocol_sha256=protocol_sha,
                arms={}, error='frozen 2700-second batch cap', seconds=0.))
            receipt = dict(**job, status='batch_not_started', result=binding(path))
            write_new(root/'receipts'/(job_key(**job)+'.json'), receipt)
            receipts.append(receipt)
    load_sealed(root)
    execution = dict(status='all_terminal', jobs=len(jobs), terminal_records=len(receipts),
        complete_jobs=sum(r['status'] == 'complete' for r in receipts), batch_cap_reached=cap_reached,
        seconds=time.monotonic()-started, completed_utc=utc_now(), workers=capacity,
        protocol_sha256=protocol_sha, job_receipts=receipts, GPS_used=False)
    write_new(root/'execution.json', execution)
    print('batch terminal', execution['complete_jobs'], '/', execution['jobs'], 'seconds', round(execution['seconds'], 2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--coordinator-go', type=Path, required=True)
    parser.add_argument('--audit-go', type=Path, required=True)
    args = parser.parse_args()
    main(args.root, args.coordinator_go, args.audit_go)
