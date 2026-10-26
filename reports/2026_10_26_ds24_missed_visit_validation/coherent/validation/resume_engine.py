"""Authorized infrastructure-only continuation of an unstarted cavity stage."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from integrate import read,write,sha
OLD=HERE.parent
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')


def prepare():
    original=read(HERE/'position_protocol.json');first=read(HERE/'position_terminal_seal.json')
    assert first['all_terminal'] and not first['denied_reads'] and first['inputs_unchanged']
    preflight=list((HERE/'environment_preflight_user/read_receipts').glob('*.json'))
    assert preflight and all(not read(p)['denied_paths'] for p in preflight)
    jobs=[];protected={}
    for job in original['jobs']:
        root=Path(job['root']);execution=read(root/'execution.json');stages=execution['stages']
        assert execution['status']=='failed' and len(stages)==2 and stages[0]['returncode']==0 and stages[1]['returncode']==1
        assert "ModuleNotFoundError: No module named 'scipy'" in (root/'signed_prior_equal_cavity.log').read_text()
        assert not (root/'family_cavity').exists()
        assert all(not read(p)['denied_paths'] for p in (root/'read_receipts').glob('*.json'))
        remaining=240-execution['seconds'];assert remaining>0
        jobs.append(dict(job,remaining_seconds=remaining,first_attempt_seconds=execution['seconds'],
            first_execution_sha256=sha(root/'execution.json'),fresh_ALGO02_reused=True,engine_numerical_work_previously_started=False))
        for path in root.rglob('*'):
            if path.is_file():protected[str(path)]=sha(path)
    for path,h in dict(original['input_hashes'],**original['source_hashes']).items():assert sha(path)==h,path
    write(HERE/'engine_continuation_protocol.json',dict(schema='coherent-cavity-infrastructure-continuation/v1',
        original_protocol_sha256=sha(HERE/'position_protocol.json'),first_terminal_seal_sha256=sha(HERE/'position_terminal_seal.json'),
        jobs=jobs,protected_existing_files=protected,code_sha256=sha(__file__),
        execution_uid=1000,python_executable=sys.executable,scientific_dependency_path='/tmp/algo03-feasible-deps',
        actual_dependency_tree=str(Path('/tmp/algo03-feasible-deps').resolve()),
        source_library_changes=False,model_gate_seed_budget_changes=False,fresh_ALGO02_reruns=0,
        untouched_cavity_stage_only=True,original_total_numerical_budget_seconds=240,maximum_workers=2,BLAS_threads=1,
        import_preflight_passed=True,import_preflight_receipts={str(p):sha(p) for p in preflight},
        authorization='Root authorizes infrastructure fix after exact cause/identity tests; restore original numeric UID and resume only untouched cavity within remaining240second budget',
        require_hash_bound_authorization=True,GPS_reporting_before_final_audit=False))
    print(dict(protocol_sha256=sha(HERE/'engine_continuation_protocol.json'),jobs=[dict(case=j['case'],variant=j['variant'],remaining_seconds=j['remaining_seconds']) for j in jobs]),flush=True)


def one(job):
    root=Path(job['root']);began=time.monotonic();env=dict(os.environ,
        PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
        PYTHONPATH=':'.join(map(str,[OLD/'position_harness',Path('/tmp/algo03-feasible-deps'),REPO/'src',REPO/'tools',SOURCE/'engine'])),
        LEO_POSITION_RUN_ROOT=str(root),LEO_POSITION_AUDIT_DIR=str(root/'read_receipts'))
    command=[sys.executable,'-B',str(SOURCE/'engine/ds24_engine.py'),'--root',str(root),'--case',job['case']]
    record=dict(job,status='running',uid=os.getuid(),fresh_ALGO02_reruns=0)
    try:
        with (root/'signed_prior_equal_cavity_continuation.log').open('x') as log:
            process=subprocess.Popen(command,cwd=REPO,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:code=process.wait(timeout=job['remaining_seconds'])
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                raise
        record['returncode']=code
        if code:raise RuntimeError('retained engine continuation failed')
        final=read(root/'family_cavity/position'/(job['case']+'.json'))
        record['status']='complete' if final['status']=='complete' else 'inference_unavailable'
    except subprocess.TimeoutExpired:record.update(status='capped',reason='remaining original240second numerical budget')
    except Exception as exc:record.update(status='failed',error=repr(exc))
    record['continuation_seconds']=time.monotonic()-began
    record['total_numerical_seconds']=job['first_attempt_seconds']+record['continuation_seconds']
    write(root/'engine_continuation_execution.json',record)
    print(dict(case=job['case'],variant=job['variant'],status=record['status'],continuation_seconds=record['continuation_seconds'],total_numerical_seconds=record['total_numerical_seconds']),flush=True)
    return record


def run():
    assert os.getuid()==1000
    p=read(HERE/'engine_continuation_protocol.json');auth=read(HERE/'engine_continuation_authorization.json')
    assert auth['protocol_sha256']==sha(HERE/'engine_continuation_protocol.json') and auth['untouched_engine_continuation_authorized']
    assert sha(__file__)==p['code_sha256']
    for path,h in p['protected_existing_files'].items():assert sha(path)==h,path
    results=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(one,j) for j in p['jobs']]):results.append(future.result())
    files={};denied=[]
    for job in p['jobs']:
        root=Path(job['root'])
        for path in root.rglob('*.json'):files[str(path)]=sha(path)
        for path in (root/'read_receipts').glob('*.json'):denied.extend(read(path)['denied_paths'])
    for path,h in p['protected_existing_files'].items():assert sha(path)==h,path
    write(HERE/'position_final_terminal_seal.json',dict(all_terminal=True,results=results,
        original_protocol_sha256=sha(HERE/'position_protocol.json'),continuation_protocol_sha256=sha(HERE/'engine_continuation_protocol.json'),
        terminal_output_hashes=files,denied_reads=denied,GPS_error_evaluation_performed=False,
        inputs_and_first_attempt_artifacts_unchanged=True,evaluation_now_permitted=not denied,
        reused_controls=read(HERE/'position_protocol.json')['controls']))
    print(dict(all_terminal=True,statuses=[r['status'] for r in results],denied_reads=len(denied)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run']);a=parser.parse_args()
    {'prepare':prepare,'run':run}[a.action]()
