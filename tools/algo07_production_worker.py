"""Bounded guarded reassociation with exact ALGO06 fallback on every failure."""
import argparse
import hashlib
import os
import signal
from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
import time
from algo03_shadow_worker import read, write
from algo06_prepare import export_catalogue
from algo07_prepare import prepare
from algo07_history import export_history
from algo07_science.runner import published_baseline, SETTINGS
from algo07_science.policy import POLICY
from run_algo03_shadow import check_read_audit
from leo.contracts.fast_graph_position import KIND, ARMS
from leo.contracts.fast_graph_position_v6 import MODEL_VERSION, incumbent_owners, validate_terminal
from leo.storage.fast_graph_position_v5_export import FastGraphPositionStoreV5Export
from leo.operations.tle_archive import TleArchiveReader

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def preparation_budget(deadline):
    """Bound archive/export work too, reserving time for fallback publication."""
    def expired(*_):
        raise TimeoutError('ALGO07 preparation/inference deadline reached')
    remaining = deadline-time.monotonic()-10
    if remaining <= 0:
        raise TimeoutError('No ALGO07 preparation budget remains')
    handler = signal.signal(signal.SIGALRM, expired)
    previous = signal.setitimer(signal.ITIMER_REAL, remaining)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous)
        signal.signal(signal.SIGALRM, handler)


def verify_release():
    from stage_algo07_release import MANIFEST, MANIFEST_SHA256
    payload = (ROOT/MANIFEST).read_bytes()
    if hashlib.sha256(payload).hexdigest() != MANIFEST_SHA256:
        raise ValueError('ALGO07 manifest changed')
    for name, expected in read(ROOT/MANIFEST)['sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
            raise ValueError('ALGO07 dependency changed: '+name)


def envelope(old, candidate, audit, seconds, failure=None):
    value = dict(schema_version=6,kind=KIND,model_version=MODEL_VERSION,state='complete',
        input_sha256=old['input_sha256'],session_id=old['session_id'],incumbent=old,candidate=candidate,
        decision='ALGO07_reassociation' if candidate else 'ALGO06_fallback',
        position=dict(zip(('latitude_deg','longitude_deg'),candidate['arms']['fitted_c']['endpoint_latlon'])) if candidate else old['position'],
        reference_usage='none',future_TLE_used=False,matched_c_inputs=True,selected_arm='fitted_c',
        incumbent_seconds=old['total_seconds'],recovery_seconds=seconds,total_seconds=old['total_seconds']+seconds,
        read_audit=audit,failure=failure,recovery_policy=POLICY)
    return validate_terminal(value,input_sha256=old['input_sha256'])


def compact(root, result, old):
    if result['execution_status'] != 'complete' or result['selected'] is None:
        return None
    record = next(r for r in result['records'] if r['name'] == result['selected'])
    guard = result['guards'][record['name']]
    prior = incumbent_owners(old)
    published = {a:{oid:record['pair'][a]['proposed_owners'][oid] for oid in prior[a]} for a in ARMS}
    changed = {a:sorted(oid for oid in prior[a] if prior[a][oid] != published[a][oid]) for a in ARMS}
    if changed['c0'] != changed['fitted_c']:
        raise ValueError('Reassociation differs between matched c arms')
    arms = {a:dict(record['pair'][a],
                   negative_twice_elbo=record['pair'][a]['objective'],
                   endpoint_east_north_km=record['pair'][a]['x'],
                   associated_points=len(published[a])) for a in ARMS}
    z = read(root/'inputs/SCAN.json')
    catalogue = read(root/'catalogues/SCAN.json')
    new = int(record['hypothesis']['norad'])
    return dict(policy=POLICY,old_norad=int(record['target']),new_norad=new,target_ids=changed['c0'],
        observation_ids=[o['observation_id'] for o in read(Path(z['native_path'])/'observations.json')],
        published_owners=published,arms=arms,record=record,guard=guard,shortlist_count=len(guard['candidates']),
        cutoff_utc_ns=z['scan_receipt']['cutoff_utc_ns'],element=catalogue['elements'][str(new)],
        baseline_objectives={a:result['baseline'][a]['objective'] for a in ARMS})


def guarded_replay(root, old, *, deadline):
    remaining = int(deadline-time.monotonic()-15)
    if remaining < 1:
        raise TimeoutError('Preparation consumed reassociation budget')
    z = read(root/'inputs/SCAN.json')
    output = root/'candidate'
    write(output/'protocol.json',dict(settings=SETTINGS,baselines={'SCAN':published_baseline(root,'SCAN')}))
    env = dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
        PYTHONPATH=os.pathsep.join(map(str,(ROOT/'deploy/fast_graph_guard',ROOT/'src',ROOT/'tools'))),
        LEO_FAST_GRAPH_RUN_ROOT=str(root),LEO_FAST_GRAPH_INPUT=str(Path(z['native_path'])/'tracking.json'),
        LEO_FAST_GRAPH_SOURCE_ROOT=str(ROOT),LEO_FAST_GRAPH_TLE_ROOT=str(root/'unused-archive'),
        MPLCONFIGDIR=str(root/'matplotlib-cache'))
    command = [sys.executable,'-B',str(ROOT/'tools/algo07_recovery_worker.py'),
               '--input',str(root),'--output',str(output)]
    write(root/'launch.json',dict(command=command,maximum_seconds=remaining,policy=POLICY))
    with (root/'worker.log').open('xb') as stream:
        child = subprocess.Popen(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
        try:
            code = child.wait(timeout=remaining)
        except BaseException:
            child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait()
            raise
    audit = check_read_audit(root,child.pid)
    write(root/'read-audit.json',audit)
    if code or not audit['verified']:
        raise ValueError('Guarded ALGO07 replay or read audit failed')
    result = read(output/'SCAN/worker_result.json')
    write(root/'decision.json',dict(status=result['execution_status'],selected=result['selected'],policy=POLICY))
    if result['execution_status'] != 'complete':
        raise ValueError('ALGO07 fail-closed outcome: '+result['execution_status'])
    return compact(root,result,old),audit


def run(args):
    began = time.monotonic();verify_release()
    store = FastGraphPositionStoreV5Export(args.bulk_root)
    job = store.status(args.job)
    if not job or job['state'] != 'complete':
        raise ValueError('Completed ALGO06 required')
    old,before = store.terminal(job)
    output = args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    recovery = output/'recovery'
    candidate=audit=None;failure=None
    try:
        with preparation_budget(began+args.maximum_seconds):
            store.export_recovery(job,recovery)
            z=prepare(recovery)
            reader=TleArchiveReader(Path('/var/lib/leo/tle'))
            export_catalogue(recovery,z['scan_receipt']['cutoff_utc_ns'],reader=reader)
            export_history(recovery/'history-bank.json',z['scan_receipt']['cutoff_utc_ns'],reader=reader)
            candidate,audit=guarded_replay(recovery,old,deadline=began+args.maximum_seconds)
            envelope(old,candidate,audit,time.monotonic()-began)
    except Exception as exc:
        candidate=None;failure=f'{type(exc).__name__}: {exc}'
    current,after=store.terminal(job)
    if old!=current or before!=after:
        raise ValueError('Published ALGO06 changed')
    verify_release()
    terminal=envelope(old,candidate,audit,time.monotonic()-began,failure)
    write(output/'terminal.json',terminal)
    return terminal


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bulk-root',type=Path,required=True)
    parser.add_argument('--job',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--maximum-seconds',type=int,choices=range(1,1201),default=1200)
    run(parser.parse_args())
