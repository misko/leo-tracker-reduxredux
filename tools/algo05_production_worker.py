"""Publish conditional gap recovery only after guarded exact proof verification."""
import argparse
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path
from algo03_shadow_worker import read,write
from algo03_production_worker import checked_file
from algo05_recovery_worker import compact
from run_algo03_shadow import check_read_audit
from leo.contracts.fast_graph_position import KIND
from leo.contracts.fast_graph_position_v4 import MODEL_VERSION,validate_terminal,incumbent_proof
from leo.storage.fast_graph_position_v3_export import FastGraphPositionStoreV3Export
ROOT=Path(__file__).resolve().parents[1]
POLICY='gap_conditional'

def verify_release():
    from stage_algo05_release import MANIFEST,MANIFEST_SHA256
    payload=(ROOT/MANIFEST).read_bytes()
    if hashlib.sha256(payload).hexdigest()!=MANIFEST_SHA256:raise ValueError('ALGO05 manifest changed')
    for name,h in read(ROOT/MANIFEST)['sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=h:raise ValueError('ALGO05 dependency changed: '+name)

def envelope(incumbent,candidate,audit,seconds,failure=None):
    d=dict(schema_version=4,kind=KIND,model_version=MODEL_VERSION,state='complete',
        input_sha256=incumbent['input_sha256'],session_id=incumbent['session_id'],incumbent=incumbent,
        candidate=candidate,decision='ALGO05_additive' if candidate else 'ALGO04_fallback',
        position=dict(zip(('latitude_deg','longitude_deg'),candidate['trial']['arms']['fitted_c']['endpoint_latlon'])) if candidate else incumbent['position'],
        reference_usage='none',future_TLE_used=False,matched_c_inputs=True,selected_arm='fitted_c',
        incumbent_seconds=incumbent['total_seconds'],recovery_seconds=seconds,total_seconds=incumbent['total_seconds']+seconds,
        read_audit=audit,failure=failure,recovery_policy=POLICY)
    return validate_terminal(d,input_sha256=incumbent['input_sha256'])

def verify_candidate(result,recovery):
    selected=result['selected']
    trial=checked_file(Path(selected['path'])/'target_0.json',recovery).parent
    audit=read(checked_file(trial/'exact_owner_replay.json',recovery))
    for name,h in audit['source_hashes'].items():
        if hashlib.sha256(checked_file(name,recovery).read_bytes()).hexdigest()!=h.removeprefix('sha256:'):
            raise ValueError('Exact audit source changed')
    fit=read(trial/'target_0.json')
    identity=read(checked_file(trial.parent/'annotation/result.json',recovery))['annotation']
    parent=read(checked_file(trial.parent.parent/'gap-source/protocol.json',recovery))
    for name,h in parent['input_sha256'].items():
        if hashlib.sha256(checked_file(name,recovery).read_bytes()).hexdigest()!=h:raise ValueError('Gap source changed')
    observation_path=Path(parent['job']['root'])/parent['job']['case']/'observations.json'
    universe={o['observation_id'] for o in read(checked_file(observation_path,recovery))}
    rebuilt=compact(fit,audit,identity,universe,parent['parent_observation_ids'])
    if rebuilt!=result['candidate']:raise ValueError('Selected candidate differs from exact proof files')
    return rebuilt

def guarded_replay(output, *, deadline):
    remaining = min(1170, int(deadline - time.monotonic() - 30))
    if remaining < 1:
        raise TimeoutError("ALGO05 preparation consumed its bounded recovery budget")
    environment = dict(
        os.environ,
        PYTHONDONTWRITEBYTECODE="1",
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        PYTHONPATH=os.pathsep.join(
            map(str, (ROOT / "deploy/fast_graph_guard", ROOT / "src", ROOT / "tools"))
        ),
        LEO_FAST_GRAPH_RUN_ROOT=str(output),
        LEO_FAST_GRAPH_INPUT=str(output / "snapshot/inference/SCAN/tracking.json"),
        LEO_FAST_GRAPH_SOURCE_ROOT=str(ROOT),
        LEO_FAST_GRAPH_TLE_ROOT=str(output / "unused-tle-archive"),
        MPLCONFIGDIR=str(output / "matplotlib-cache"),
    )
    command = [
        sys.executable,
        "-B",
        str(ROOT / "tools/algo05_recovery_worker.py"),
        "--output",
        str(output),
        "--maximum-seconds",
        str(remaining),
    ]
    write(output / "launch.json", dict(policy=POLICY, command=command, maximum_seconds=remaining))
    with (output / "worker.log").open("xb") as log:
        child = subprocess.Popen(
            command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT
        )
        try:
            code = child.wait(timeout=max(1, deadline - time.monotonic() - 20))
        except BaseException:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            raise
    audit = check_read_audit(output, child.pid)
    if code != 0 or not (output / "decision.json").exists():
        raise ValueError("ALGO05 guarded worker failed; retain its log and read receipts")
    result = read(output / "decision.json")
    result["read_audit"] = audit
    write(output / "guarded-result.json", result)
    if not audit["verified"]:
        raise ValueError("ALGO05 process read audit failed")
    return result


def run(args):
    began=time.monotonic();verify_release()
    store=FastGraphPositionStoreV3Export(args.bulk_root);job=store.status(args.job)
    if not job or job['state']!='complete':raise ValueError('Completed ALGO04 required')
    incumbent,before=store.terminal(job);output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    recovery=output/'recovery';recovery.mkdir();candidate=None;audit=None;failure=None
    try:
        if (incumbent_proof(incumbent).get('read_audit') or {}).get('verified') is not True:
            raise ValueError('Historical read audit not verified')
        store.export_recovery(job,recovery/'source-export')
        result=guarded_replay(recovery,deadline=began+args.maximum_seconds);audit=result['read_audit']
        if result.get('selected'):
            candidate=verify_candidate(result,recovery)
            envelope(incumbent,candidate,audit,time.monotonic()-began)
    except Exception as error:
        candidate=None;failure=f'{type(error).__name__}: {error}'
    current,after=store.terminal(job)
    if before!=after or incumbent!=current:raise ValueError('Published ALGO04 changed')
    terminal=envelope(incumbent,candidate,audit,time.monotonic()-began,failure)
    write(output/'terminal.json',terminal)
    return terminal

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bulk-root',type=Path,required=True);p.add_argument('--job',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--maximum-seconds',type=int,choices=range(1,1201),default=1200)
    run(p.parse_args())

