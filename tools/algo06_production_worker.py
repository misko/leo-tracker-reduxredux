"""Bounded causal family recovery; every failure retains the exact ALGO05 result."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time
from algo03_shadow_worker import read, write
from algo06_prepare import prepare, export_catalogue, compact
from algo06_policy import POLICY
from run_algo03_shadow import check_read_audit
from leo.contracts.fast_graph_position import KIND
from leo.contracts.fast_graph_position_v5 import MODEL_VERSION, POLICIES, validate_terminal
from leo.storage.fast_graph_position_v4_export import FastGraphPositionStoreV4Export
from leo.operations.tle_archive import TleArchiveReader

ROOT=Path(__file__).resolve().parents[1]

def verify_release():
    from stage_algo06_release import MANIFEST, MANIFEST_SHA256
    payload=(ROOT/MANIFEST).read_bytes()
    if hashlib.sha256(payload).hexdigest()!=MANIFEST_SHA256:
        raise ValueError('ALGO06 manifest changed')
    for name, expected in read(ROOT/MANIFEST)['sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('ALGO06 dependency changed: '+name)
    if POLICY not in POLICIES:
        raise ValueError('No sealed ALGO06 recovery policy')

def envelope(old, candidate, audit, seconds, failure=None, *, policy=POLICY):
    value=dict(schema_version=5,kind=KIND,model_version=MODEL_VERSION,state='complete',
        input_sha256=old['input_sha256'],session_id=old['session_id'],incumbent=old,candidate=candidate,
        decision='ALGO06_additive' if candidate else 'ALGO05_fallback',
        position=dict(zip(('latitude_deg','longitude_deg'),candidate['trial']['arms']['fitted_c']['endpoint_latlon'])) if candidate else old['position'],
        reference_usage='none',future_TLE_used=False,matched_c_inputs=True,selected_arm='fitted_c',
        incumbent_seconds=old['total_seconds'],recovery_seconds=seconds,total_seconds=old['total_seconds']+seconds,
        read_audit=audit,failure=failure,recovery_policy=policy)
    return validate_terminal(value,input_sha256=old['input_sha256'])

def guarded_replay(root, *, deadline, policy=POLICY):
    remaining=int(deadline-time.monotonic()-15)
    if remaining<1:
        raise TimeoutError('Preparation consumed recovery budget')
    z=read(root/'inputs/SCAN.json')
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
        PYTHONPATH=os.pathsep.join(map(str,(ROOT/'deploy/fast_graph_guard',ROOT/'src',ROOT/'tools'))),
        LEO_FAST_GRAPH_RUN_ROOT=str(root),LEO_FAST_GRAPH_INPUT=str(Path(z['native_path'])/'tracking.json'),
        LEO_FAST_GRAPH_SOURCE_ROOT=str(ROOT),LEO_FAST_GRAPH_TLE_ROOT=str(root/'unused-archive'),
        MPLCONFIGDIR=str(root/'matplotlib-cache'))
    command=[sys.executable,'-B',str(ROOT/'tools/algo06_recovery_worker.py'),'--output',str(root),'--policy',policy]
    write(root/'launch.json',dict(command=command,maximum_seconds=remaining,policy=policy))
    with (root/'worker.log').open('xb') as stream:
        child=subprocess.Popen(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
        try:
            code=child.wait(timeout=remaining)
        except BaseException:
            child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait()
            raise
    audit=check_read_audit(root,child.pid)
    write(root/'read-audit.json',audit)
    if code or not audit['verified']:
        raise ValueError('Guarded ALGO06 replay or read audit failed')
    return compact(root,policy),audit

def run(args):
    began=time.monotonic(); verify_release()
    store=FastGraphPositionStoreV4Export(args.bulk_root)
    job=store.status(args.job)
    if not job or job['state']!='complete':
        raise ValueError('Completed ALGO05 required')
    old,before=store.terminal(job)
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    recovery=output/'recovery';recovery.mkdir()
    candidate=audit=None;failure=None
    try:
        store.export_recovery(job,recovery/'source-export')
        z=prepare(recovery)
        if z['targets']:
            export_catalogue(recovery,z['scan_receipt']['cutoff_utc_ns'],reader=TleArchiveReader(Path('/var/lib/leo/tle')))
            candidate,audit=guarded_replay(recovery,deadline=began+args.maximum_seconds)
            envelope(old,candidate,audit,time.monotonic()-began)
        else:
            write(recovery/'decision.json',dict(status='no_eligible_native_residual',policy=POLICY))
    except Exception as exc:
        candidate=None;failure=f'{type(exc).__name__}: {exc}'
    current,after=store.terminal(job)
    if old!=current or before!=after:
        raise ValueError('Published ALGO05 changed')
    terminal=envelope(old,candidate,audit,time.monotonic()-began,failure)
    write(output/'terminal.json',terminal)
    return terminal

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bulk-root',type=Path,required=True);p.add_argument('--job',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--maximum-seconds',type=int,choices=range(1,1201),default=1200)
    run(p.parse_args())
