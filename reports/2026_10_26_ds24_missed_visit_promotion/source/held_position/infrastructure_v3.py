"""Actual-module-bound infrastructure recovery, one baseline before the panel."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import position as base
from position import HERE,REPO,OLD,SOURCE,read,write,sha
from infrastructure_v2 import job_env

def prepare(study):
    old=read(HERE/'baseline_v2/protocol.json')
    for path,h in dict(old['sources_sha256'],**old['inputs_sha256']).items():assert sha(path)==h,path
    prior=read('/srv/bulk/leo/research/ds24-ch58-continuity-r01/validation/source_receipt.json')['files_sha256']
    for path,h in prior.items():assert sha(path)==h,path
    root=study/'preflight';root.mkdir(parents=True,exist_ok=False)
    code='''import os,sys,json,hashlib
from pathlib import Path
import numpy,scipy,algo02_scan,ds24_engine
from leo.analysis.glrt_frequency_input import frequency_evidence
algo02_scan.bind_run_directory(os.environ['LEO_POSITION_RUN_ROOT'])
assert os.getuid()==1000
modules={}
for name,module in list(sys.modules.items()):
    path=getattr(module,'__file__',None)
    if path and Path(path).is_file():
        path=str(Path(path).resolve())
        modules[name]=dict(path=path,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
print(json.dumps(dict(modules=modules,numpy=numpy.__version__,scipy=scipy.__version__,python=sys.executable)))'''
    proc=subprocess.run([sys.executable,'-B','-c',code],env=job_env(root),cwd=REPO,capture_output=True,text=True)
    assert proc.returncode==0,proc.stderr
    identity=json.loads(proc.stdout);receipts=list((root/'read_receipts').glob('*.json'))
    assert receipts and all(not read(p)['denied_paths'] for p in receipts)
    actual={v['path']:v['sha256'] for v in identity['modules'].values()}
    scientific={p:h for p,h in actual.items() if p.startswith((str(REPO/'src')+'/',str(REPO/'tools')+'/',str(SOURCE)+'/',str(OLD)+'/','/opt/leo-shared-scans/'))}
    extra={p:h for p,h in scientific.items() if p not in prior and p not in old['sources_sha256']}
    assert all(p.endswith('_native_acquisition.cpython-312-x86_64-linux-gnu.so') for p in extra),extra
    assert not any(p.startswith('/opt/leo-shared-scans/') for p in scientific)
    assert all(h==prior.get(p,old['sources_sha256'].get(p,h)) for p,h in scientific.items())
    write(study/'module_identity_audit.json',dict(identity,scientific_module_count=len(scientific),scientific_old_hash_match_count=len(scientific)-len(extra),additional_frozen_unused_native_extensions=extra,all_other_actual_scientific_sources_match=True,no_collection_snapshot_leo_modules_loaded=True))
    write(study/'preflight.json',dict(passed=True,returncode=0,stderr=proc.stderr,expanded_transitive_imports=True,uid=1000,receipt_hashes={str(p):sha(p) for p in receipts},module_identity_audit_sha256=sha(study/'module_identity_audit.json')))
    sources=dict(old['sources_sha256'],**prior);sources.update(actual)
    sources.update({str(p):sha(p) for p in [Path(__file__),study/'module_identity_audit.json',study/'preflight.json']})
    write(study/'protocol.json',dict(old,sources_sha256=sources,baseline_preflight_protocol_sha256=sha(HERE/'baseline_v2/protocol.json'),expanded_actual_module_identity_audit_sha256=sha(study/'module_identity_audit.json'),first_job_only_before_remaining_dispatch=True,first_case='DS24-0015',prior_sealed_scientific_receipt_count=len(prior),no_GPS_evaluation_until_coherent_primary_terminal=True))
    print(dict(protocol_sha256=sha(study/'protocol.json'),scientific_modules=len(scientific),additional_native_extensions=extra),flush=True)

def verify(p):
    for path,h in dict(p['sources_sha256'],**p['inputs_sha256']).items():assert sha(path)==h,path

def run(study,phase):
    assert os.getuid()==1000
    p=read(study/'protocol.json');verify(p);assert read(study/'preflight.json')['passed']
    base.job_env=job_env
    jobs=p['jobs'][:1] if phase=='first' else p['jobs'][1:]
    if phase=='rest':
        first=read(study/'first_terminal_seal.json')
        assert first['all_terminal'] and not first['denied_paths']
    began=time.monotonic();results=[]
    with ThreadPoolExecutor(max_workers=1 if phase=='first' else p['maximum_workers']) as pool:
        for f in as_completed([pool.submit(base.one,j) for j in jobs]):results.append(f.result())
    verify(p);files={};denied=[];audits=[]
    for j in jobs:
        root=Path(j['root']);receipts=[read(f) for f in (root/'read_receipts').glob('*.json')]
        for r in receipts:denied.extend(r['denied_paths'])
        audits.append(dict(case=j['case'],variant=j['variant'],receipt_count=len(receipts),read_paths=sorted({x for r in receipts for x in r['read_paths']}),denied_paths=[x for r in receipts for x in r['denied_paths']]))
        for path in root.rglob('*'):
            if path.is_file():files[str(path)]=sha(path)
    write(study/(phase+'_terminal_seal.json'),dict(protocol_sha256=sha(study/'protocol.json'),all_terminal=True,results=results,output_sha256=files,read_audits=audits,denied_paths=denied,inputs_and_sources_unchanged=True,GPS_evaluation_performed=False,evaluation_permitted=False,wall_seconds=time.monotonic()-began))
    print(phase+'_TERMINAL',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','first','rest']);p.add_argument('--study',type=Path,default=HERE/'baseline_v3');a=p.parse_args()
    if a.action=='prepare':prepare(a.study)
    else:run(a.study,a.action)
