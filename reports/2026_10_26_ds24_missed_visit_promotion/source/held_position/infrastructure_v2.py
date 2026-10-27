"""Retain failed sparse attempt; restore frozen repository import precedence."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import position as base
from position import HERE,REPO,OLD,SOURCE,CASES,read,write,sha

def job_env(root):
    # Keep the original worker/dependency pair, after the frozen scientific repo.
    # Worker-first shadows leo.analysis with an older collection-only package.
    return dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=':'.join(map(str,[OLD/'position_harness',REPO/'src',REPO/'tools',SOURCE/'engine',Path('/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src'),Path('/tmp/algo03-feasible-deps')])),LEO_POSITION_RUN_ROOT=str(root),LEO_POSITION_AUDIT_DIR=str(root/'read_receipts'))

def prepare_baseline(study):
    original=read(HERE/'protocol.json');terminal=read(HERE/'terminal_seal.json')
    assert terminal['all_terminal'] and not terminal['denied_paths']
    assert all(r['status']=='failed' and len(r['stages'])==1 and r['stages'][0]['returncode']==1 for r in terminal['results'])
    for r in terminal['results']:
        assert "ModuleNotFoundError: No module named 'leo.analysis.glrt_frequency_input'" in (Path(r['root'])/'fresh_algo02.log').read_text()
        assert not (Path(r['root'])/r['case']/'result.json').exists()
    for path,h in dict(original['sources_sha256'],**original['inputs_sha256']).items():assert sha(path)==h,path
    jobs=[];inputs={}
    for case in CASES:
        root=study/'runs'/case/'baseline';old=HERE/'runs'/case/'baseline'
        for part in (case,'causal_prior','causal_phase_history'):shutil.copytree(old/part,root/part)
        for path in root.rglob('*'):
            if path.is_file():inputs[str(path)]=sha(path)
        jobs.append(dict(case=case,variant='baseline',root=str(root)))
    sources=dict(original['sources_sha256']);sources.update({str(Path(__file__)):sha(__file__),str(HERE/'test_infrastructure_v2.py'):sha(HERE/'test_infrastructure_v2.py')})
    write(study/'protocol.json',dict(original,jobs=jobs,variants=['baseline'],primary_candidate_held_for_coherent_handoff=True,sources_sha256=sources,inputs_sha256=inputs,original_sparse_protocol_sha256=sha(HERE/'protocol.json'),previous_import_failures_retained=True,infrastructure_amendment='Repository src precedes original collection worker path. Transitive bind_run_directory import preflight now required. No numerical work executed in prior attempt; new job uses original240s budget.',maximum_workers=4))
    print(dict(protocol_sha256=sha(study/'protocol.json'),jobs=len(jobs)),flush=True)

def preflight(study):
    p=read(study/'protocol.json')
    for path,h in dict(p['sources_sha256'],**p['inputs_sha256']).items():assert sha(path)==h,path
    root=study/'preflight';root.mkdir(exist_ok=False)
    command=[sys.executable,'-B','-c','import os, numpy, scipy, algo02_scan, ds24_engine; from leo.analysis.glrt_frequency_input import frequency_evidence; algo02_scan.bind_run_directory(os.environ["LEO_POSITION_RUN_ROOT"]); assert os.getuid()==1000; print(numpy.__version__, scipy.__version__)']
    proc=subprocess.run(command,env=job_env(root),cwd=REPO,capture_output=True,text=True)
    receipts=list((root/'read_receipts').glob('*.json'))
    passed=proc.returncode==0 and bool(receipts) and all(not read(f)['denied_paths'] for f in receipts)
    write(study/'preflight.json',dict(returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr,protocol_sha256=sha(study/'protocol.json'),read_receipts_sha256={str(f):sha(f) for f in receipts},passed=passed))
    assert passed,proc.stderr
    print('transitive_preflight_passed',flush=True)

def run(study):
    assert os.getuid()==1000
    p=read(study/'protocol.json');assert read(study/'preflight.json')['passed']
    assert read(study/'preflight.json')['protocol_sha256']==sha(study/'protocol.json')
    for path,h in dict(p['sources_sha256'],**p['inputs_sha256']).items():assert sha(path)==h,path
    base.job_env=job_env
    began=time.monotonic();results=[]
    with ThreadPoolExecutor(max_workers=p['maximum_workers']) as pool:
        for f in as_completed([pool.submit(base.one,j) for j in p['jobs']]):results.append(f.result())
    files={};denied=[];audits=[]
    for j in p['jobs']:
        root=Path(j['root']);receipts=[read(f) for f in (root/'read_receipts').glob('*.json')]
        for r in receipts:denied.extend(r['denied_paths'])
        audits.append(dict(case=j['case'],variant=j['variant'],receipt_count=len(receipts),read_paths=sorted({x for r in receipts for x in r['read_paths']}),denied_paths=[x for r in receipts for x in r['denied_paths']]))
        for path in root.rglob('*'):
            if path.is_file():files[str(path)]=sha(path)
    for path,h in dict(p['sources_sha256'],**p['inputs_sha256']).items():assert sha(path)==h,path
    write(study/'terminal_seal.json',dict(protocol_sha256=sha(study/'protocol.json'),preflight_sha256=sha(study/'preflight.json'),all_terminal=True,results=sorted(results,key=lambda r:(r['case'],r['variant'])),output_sha256=files,read_audits=audits,denied_paths=denied,inputs_and_sources_unchanged=True,GPS_evaluation_performed=False,evaluation_permitted=not denied,wall_seconds=time.monotonic()-began))
    print('ALL_TERMINAL',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare_baseline','preflight','run']);p.add_argument('--study',type=Path,default=HERE/'baseline_v2');a=p.parse_args();globals()[a.action](a.study)
