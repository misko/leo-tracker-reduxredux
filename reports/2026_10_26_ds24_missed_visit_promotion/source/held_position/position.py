"""Finite frozen held-panel regional comparison; inference never reads geography."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
OLD = Path('/srv/bulk/leo/research/ds24-missed-visit-r01/validation')
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024')
GRAPH = Path('/srv/bulk/leo/research/ds24-missed-visit-r02/validation/held_graph')
CASES = tuple('DS24-'+s for s in ('0015','0016','0019','0075','0077','0081','0083','0085','0089','0091','0093','0095'))
VARIANTS = ('baseline','additions_bin_floor','additions_proxy')
BIN = 10000000/(44*512)
sys.path[:0] = [str(OLD), '/tmp/algo03-feasible-deps', str(REPO/'src'), str(REPO/'tools')]
from position_run import floored_noise
from integration import bank_reuse_audit
from ds23_radio_noise import estimate
import numpy as np

def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def encode(value):
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,np.ndarray):return value.tolist()
    raise TypeError(type(value).__name__)
def write(path, value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f: json.dump(value,f,indent=2,allow_nan=False,default=encode); f.write('\n')

def input_audit(original, rows, tracks, bank, elements, receipt, old_tracks):
    assert rows[:len(original)] == original
    ids=[r['observation_id'] for r in rows]; assert len(ids)==len(set(ids))
    members=[oid for t in tracks for oid in t['observation_ids']]
    assert len(members)==len(set(members)) and set(members)<=set(ids)
    audit=bank_reuse_audit(bank['time_s'].tolist(),bank['norad'].tolist(),elements,receipt,old_tracks,tracks)
    assert audit['reuse_allowed'],audit
    return audit

def prepare():
    assert os.getuid()==1000
    prior=read(OLD/'baseline_source_receipt.json')['files_sha256']
    for p,h in prior.items(): assert sha(p)==h,p
    graph_protocol=read(GRAPH/'protocol.json')
    for p,h in dict(graph_protocol['source_hashes'],**graph_protocol['input_hashes']).items(): assert sha(p)==h,p
    input_hashes={}; jobs=[]; audits=[]
    for case in CASES:
        folder=SOURCE/case; overlay=GRAPH/'graphs/r01_search'/case
        original=read(folder/'observations.json'); rows=read(overlay/'observations.json'); tracks=read(overlay/'tracks.json')
        ga=read(overlay/'audit.json'); assert ga['status']=='complete' and ga['method']=='r01_search'
        bank=dict(np.load(folder/'bank.npz'))
        ba=input_audit(original,rows,tracks,bank,read(folder/'nominal_elements.json'),read(SOURCE/'causal_prior'/case/'receipt.json'),read(folder/'tracks.json'))
        new=set(r['observation_id'] for r in rows)-set(r['observation_id'] for r in original)
        assert len(new)==ga['new_native']
        proxy=estimate(tracks,rows)
        for variant in VARIANTS:
            root=HERE/'runs'/case/variant; dest=root/case; dest.mkdir(parents=True,exist_ok=False)
            for name in ('tracking.json','input_receipt.json','bank.npz','nominal_elements.json','receipt.json','selected.tle','previous.tle','previous_receipt.json'):
                shutil.copyfile(folder/name,dest/name)
            prior_dest=root/'causal_prior'/case; prior_dest.mkdir(parents=True)
            for p in (SOURCE/'causal_prior'/case).iterdir():
                if p.is_file(): shutil.copyfile(p,prior_dest/p.name)
            history=root/'causal_phase_history'; history.mkdir()
            for name in (case+'.json',case+'_forecast.json'): shutil.copyfile(SOURCE/'causal_phase_history'/name,history/name)
            if variant=='baseline':
                for name in ('observations.json','tracks.json','radio_noise.json'): shutil.copyfile(folder/name,dest/name)
            else:
                for name in ('observations.json','tracks.json'): shutil.copyfile(overlay/name,dest/name)
                noise=floored_noise(proxy,[o['observation_id'] for o in rows],new) if variant=='additions_bin_floor' else copy.deepcopy(proxy)
                noise['source_sha256']={name:sha(dest/name) for name in ('observations.json','tracks.json')}
                noise['code_sha256']=sha(REPO/'tools/ds23_radio_noise.py');write(dest/'radio_noise.json',noise)
            prepared=read(folder/'prepared.json')
            if variant!='baseline': prepared.update(GLRT_points=len(rows),graph_points=sum(len(t['observation_ids']) for t in tracks),graph_tracks=len(tracks),curved_tracks=ga['curved_tracks'],measurement_transfer='Frozen R01 reserved-panel additions plus exact original measurements')
            write(dest/'prepared.json',prepared)
            write(dest/'research_input_receipt.json',dict(case=case,variant=variant,added_native_observation_ids=[] if variant=='baseline' else sorted(new),bank_support_audit=ba,original_rows_exact=True,original_tracking_export_sha256=sha(folder/'tracking.json'),no_geographic_inputs=True,fresh_initialization=True))
            for p in root.rglob('*'):
                if p.is_file(): input_hashes[str(p)]=sha(p)
            jobs.append(dict(case=case,variant=variant,root=str(root)))
        for p in overlay.iterdir():
            if p.is_file(): input_hashes[str(p)]=sha(p)
        audits.append(dict(case=case,new_native=len(new),new_curved=ga['new_curved'],bank_support_audit=ba))
    sources=dict(prior)
    for p in [Path(__file__),HERE/'test_position.py',OLD/'position_run.py',OLD/'integration.py',OLD/'position_harness/sitecustomize.py',OLD/'position_harness/position_read_audit.py']:
        sources[str(p)]=sha(p)
    write(HERE/'protocol.json',dict(schema='held-R01-promotion-regional/v1',jobs=jobs,cases=CASES,variants=VARIANTS,primary='additions_bin_floor',secondary='additions_proxy',sources_sha256=sources,inputs_sha256=input_hashes,input_audits=audits,source_imports_equality_passed=True,seconds_per_job=240,maximum_workers=4,BLAS_threads=1,uid=1000,python=sys.executable,original_pythonpath='/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src:/tmp/algo03-feasible-deps',radio_seed_budget=4,fully_fitted_RF_branches=3,phase_rounds=5,steps_per_round=48,regional_center=[37.906,-122.545],box_width_km=25.,start=[0.,0.],matched_c_arms=['c0','fitted_c'],full_causal_catalogue=True,causal_signed_prior=True,equal_prior_family_cavity=True,no_archived_endpoint_input=True,no_GPS_inference=True,no_retry=True,failure_policy='retain all capped/failed jobs; no extra budget or scientific changes',baseline_reuse='none: historical held controls lack strict per-process read receipts',authorization='Root explicitly authorizes finite frozen panel execution once source/input/test/read preflight audit passes',prepared_ns=time.time_ns()))
    print(json.dumps(dict(status='protocol_sealed',sha256=sha(HERE/'protocol.json'),jobs=len(jobs),inputs=len(input_hashes))),flush=True)

def job_env(root):
    return dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=':'.join(map(str,[OLD/'position_harness',Path('/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src'),Path('/tmp/algo03-feasible-deps'),REPO/'src',REPO/'tools',SOURCE/'engine'])),LEO_POSITION_RUN_ROOT=str(root),LEO_POSITION_AUDIT_DIR=str(root/'read_receipts'))

def preflight():
    p=read(HERE/'protocol.json')
    for path,h in dict(p['sources_sha256'],**p['inputs_sha256']).items(): assert sha(path)==h,path
    root=HERE/'preflight';root.mkdir(exist_ok=False)
    command=[sys.executable,'-B','-c','import os, numpy, scipy, algo02_scan, ds24_engine; from position_read_audit import forbidden; assert os.getuid()==1000; assert forbidden("/srv/bulk/leo/research/old/result.json",os.environ["LEO_POSITION_RUN_ROOT"]); print(numpy.__version__, scipy.__version__)']
    proc=subprocess.run(command,env=job_env(root),cwd=REPO,capture_output=True,text=True)
    receipts=list((root/'read_receipts').glob('*.json'))
    write(HERE/'preflight.json',dict(returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr,protocol_sha256=sha(HERE/'protocol.json'),read_receipts_sha256={str(f):sha(f) for f in receipts},passed=proc.returncode==0 and bool(receipts) and all(not read(f)['denied_paths'] for f in receipts)))
    assert read(HERE/'preflight.json')['passed'],proc.stderr
    print('preflight_passed',flush=True)

def one(job):
    root=Path(job['root']); case=job['case'];began=time.monotonic();deadline=began+240
    result=dict(job,status='running',stages=[],uid=os.getuid(),GPS_in_inference=False)
    commands=[('fresh_algo02',[sys.executable,'-B',str(REPO/'tools/algo02_scan.py'),'--run-dir',str(root),'--case',case,'--stage','all']),('signed_prior_equal_cavity',[sys.executable,'-B',str(SOURCE/'engine/ds24_engine.py'),'--root',str(root),'--case',case])]
    try:
        for stage,command in commands:
            remaining=deadline-time.monotonic()
            if remaining<=0: raise subprocess.TimeoutExpired(command,240)
            started=time.monotonic()
            with (root/(stage+'.log')).open('x') as log:
                process=subprocess.Popen(command,cwd=REPO,env=job_env(root),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                try: code=process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGTERM)
                    try:process.wait(timeout=2)
                    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                    raise
            result['stages'].append(dict(stage=stage,returncode=code,seconds=time.monotonic()-started))
            if code: raise RuntimeError(stage+' failed; retained log/read receipts')
        final=read(root/'family_cavity/position'/(case+'.json'))
        result['status']='complete' if final['status']=='complete' else 'inference_unavailable'
    except subprocess.TimeoutExpired: result.update(status='capped',reason='shared240scompletejobcap')
    except Exception as exc:result.update(status='failed',error=repr(exc))
    result['seconds']=time.monotonic()-began;write(root/'execution.json',result)
    print(json.dumps(dict(case=case,variant=job['variant'],status=result['status'],seconds=result['seconds'])),flush=True)
    return result

def run():
    assert os.getuid()==1000
    p=read(HERE/'protocol.json');assert read(HERE/'preflight.json')['passed']
    assert read(HERE/'preflight.json')['protocol_sha256']==sha(HERE/'protocol.json')
    for path,h in dict(p['sources_sha256'],**p['inputs_sha256']).items(): assert sha(path)==h,path
    began=time.monotonic();results=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(one,j) for j in p['jobs']]):results.append(f.result())
    files={};denied=[];read_audits=[]
    for j in p['jobs']:
        root=Path(j['root']);receipts=[read(f) for f in (root/'read_receipts').glob('*.json')]
        for r in receipts:denied.extend(r['denied_paths'])
        read_audits.append(dict(case=j['case'],variant=j['variant'],receipt_count=len(receipts),read_paths=sorted({x for r in receipts for x in r['read_paths']}),denied_paths=[x for r in receipts for x in r['denied_paths']]))
        for path in root.rglob('*'):
            if path.is_file():files[str(path)]=sha(path)
    for path,h in dict(p['sources_sha256'],**p['inputs_sha256']).items(): assert sha(path)==h,path
    write(HERE/'terminal_seal.json',dict(protocol_sha256=sha(HERE/'protocol.json'),preflight_sha256=sha(HERE/'preflight.json'),all_terminal=True,results=sorted(results,key=lambda r:(r['case'],r['variant'])),output_sha256=files,read_audits=read_audits,denied_paths=denied,inputs_and_sources_unchanged=True,GPS_evaluation_performed=False,evaluation_permitted=not denied,wall_seconds=time.monotonic()-began))
    print('ALL_TERMINAL',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','preflight','run']);a=p.parse_args();globals()[a.action]()
