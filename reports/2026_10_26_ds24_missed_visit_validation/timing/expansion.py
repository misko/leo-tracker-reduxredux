"""Bounded application of unchanged R01 search; separate from R02 method."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import numpy as np

HERE=Path(__file__).resolve().parent;OUT=HERE/'expansion'
R01=Path('/srv/bulk/leo/research/ds24-missed-visit-r01')
def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as f:return json.load(f)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with (gzip.open(path,'xt') if str(path).endswith('.gz') else Path(path).open('x')) as f:
        json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def frozen_modules():
    p=read(R01/'timing/protocol.json')
    paths=[R01/'timing/timing_search.py',R01/'timing/adapter.py']
    for path in paths:
        if sha(path)!=p['files'][str(path)]:raise ValueError('sealed R01 method changed')
    return module('sealed_R01_application_search',paths[0]),module('sealed_R01_application_adapter',paths[1])


def open_native(slot):
    """Fresh per-window hash/exhaustion; global detector parity is reused."""
    from leo.storage.fast_scan import FastSegmentSource
    began=time.monotonic();a=slot['raw_authority']
    if 'sha256:'+sha(a['index_path'])!=a['index_sha256']:raise ValueError('frozen public index changed')
    port=FastSegmentSource(a['segment'],start_sequence=a['local_sequence'],stop_sequence=a['local_sequence']+1)
    windows=tuple(port.windows())
    if len(windows)!=1:raise ValueError('bounded source not exhausted to exactly one window')
    w=windows[0]
    if w.iq_sha256!=a['index']['iq_sha256'] or w.acquisition!=a['index']['acquisition'] or w.target!=a['target']:
        raise ValueError('native window authority mismatch')
    if w.sample_rate_hz!=a['sample_rate_hz'] or w.sample_rate_hz!=10_000_000:raise ValueError('native sample rate mismatch')
    values=(w.samples[:,:,0]+1j*w.samples[:,:,1]).astype(np.complex64)
    return w,port.receiver_ids,values,dict(full_reader_exhausted=True,native_IQ_sha256=w.iq_sha256,
        native_read_verify_seconds=time.monotonic()-began,repeated_blind_acquisition_calls=0,
        fresh_per_window_paired_candidate_parity=False,
        detector_parity_reuse='R01 global unchanged-implementation evidence, not fresh per-window parity')


def prepare(panel_path,forecast_path,upstream_protocol):
    old=read(R01/'timing/protocol.json');panel=read(panel_path);forecast=read(forecast_path)
    slots=panel['slots'];cases=sorted({s['case'] for s in slots})
    if not set(cases)<=set(['DS24-0011','DS24-0097']) or len(slots)>320:raise ValueError('expansion selection/cap differs')
    if any(sum(s['case']==c for s in slots)>160 for c in cases):raise ValueError('per-case paired-window cap exceeded')
    if any('forecast' not in r for r in forecast['rows']):raise ValueError('requires R01 sparse causal forecast shape')
    frozen_modules();files=dict(old['files'])
    paths=[Path(__file__),HERE/'test_expansion.py',Path(panel_path),Path(forecast_path),Path(upstream_protocol),
        R01/'COHERENT_EXPANSION_PLAN.md',R01/'timing/protocol.json']
    for case in cases:
        prior=R01/'timing/outcomes'/(case+'.json.gz');paths.append(prior)
        if not all(r['status']=='complete' and all(x['all_passed'] for x in r['public_source_parity']['parity'].values()) for r in read(prior)['rows']):
            raise ValueError('global unchanged-detector parity evidence failed')
    files.update({str(p):sha(p) for p in paths})
    test=subprocess.run([sys.executable,'-m','unittest','-v','test_expansion'],cwd=HERE,capture_output=True,text=True,timeout=60)
    write(OUT/'test_results.json',dict(exit_code=test.returncode,stdout=test.stdout,stderr=test.stderr))
    if test.returncode:raise ValueError('expansion reader/source tests failed')
    files[str(OUT/'test_results.json')]=sha(OUT/'test_results.json')
    write(OUT/'protocol.json',dict(schema='sealed-R01-coherent-application/v1',frozen_utc_ns=time.time_ns(),
        files=files,panel_path=str(panel_path),forecast_path=str(forecast_path),cases=cases,
        paired_windows=len(slots),receiver_cells=sum(len(s['cells']) for s in slots),
        upstream_protocol=str(upstream_protocol),method_source='R01 frozen search/point/confirmation, no R02 quadratic',
        no_new_recovered_donors=True,process_bound_seconds=580,maximum_workers=2,BLAS_threads=1,
        runtime_identity=old['runtime_identity'],requires_root_authorization=True,outcomes_before_freeze=0))
    print('expansion frozen',sha(OUT/'protocol.json'),flush=True)


def run(case):
    for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:
        if os.environ.get(key)!='1':raise ValueError('BLAS1 required')
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('580second expansion bound')));signal.alarm(580)
    began=time.monotonic();p=read(OUT/'protocol.json');approval=read(OUT/'run_authorization.json')
    if approval['protocol_sha256']!=sha(OUT/'protocol.json') or not approval['raw_scoring_authorized']:
        raise ValueError('expansion stage not root-authorized')
    for path,h in p['files'].items():
        if sha(path)!=h:raise ValueError('frozen expansion source/input changed: '+path)
    from leo.processing.fast_scan import implementation_identity
    code,environment=implementation_identity()
    if (code,environment)!=(p['runtime_identity']['code_digest'],p['runtime_identity']['environment_digest']):raise ValueError('historical runtime differs')
    if case not in p['cases']:raise ValueError('unlisted case')
    math,adapter=frozen_modules();panel=read(p['panel_path']);forecast=read(p['forecast_path'])
    by_id={r['header']['prediction_id']:r for r in forecast['rows']};rows=[];tracking_cache={}
    for slot in [s for s in panel['slots'] if s['case']==case]:
        row=dict(request_id=slot['request_id'],case=case,channel=slot['channel'],status='started',cells=[])
        try:
            if time.monotonic()-began>540:raise TimeoutError('reserve final checkpoint budget')
            if slot['status']!='nominated':raise ValueError(slot.get('reason','not nominated'))
            w,ids,values,receipt=open_native(slot);row['native_receipt']=receipt
            for index,rx in enumerate(ids):
                cell=next(c for c in slot['cells'] if c['header']['receiver_id']==rx)
                pid=cell['header']['prediction_id'];prediction=by_id[pid];packet=adapter.adapt(prediction,slot['raw_authority'])
                def selected_receipt(value):write(OUT/'selections'/(pid.replace('/','_')+'.json'),value)
                score_began=time.monotonic();result=math.score_target(values[:,index],w.sample_rate_hz,w.target['edge'],packet,selected_receipt)
                scoring_seconds=time.monotonic()-score_began
                path=slot['tracking']['path']
                if path not in tracking_cache:tracking_cache[path]=read(path)
                h=cell['header']
                original=next((v for v in tracking_cache[path]['source']['probes'] if v['visit_index']==h['visit_index'] and v['probe_index']==h['probe_index'] and v['receiver_id']==rx),None)
                row['cells'].append(dict(prediction_id=pid,receiver_id=rx,packet=packet,result=result,
                    original_fullwindow=original,original_used_for_evaluation_only=True,scoring_seconds=scoring_seconds))
            row['status']='complete'
        except Exception as exc:row.update(status='failed',error=repr(exc))
        rows.append(row);write(OUT/'checkpoints'/(slot['request_id']+'.json.gz'),row)
        print(slot['request_id'],row['status'],flush=True)
    write(OUT/'outcomes'/(case+'.json.gz'),dict(rows=rows,seconds=time.monotonic()-began,
        protocol_sha256=sha(OUT/'protocol.json'),fresh_blind_candidate_parity=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run'])
    parser.add_argument('--panel');parser.add_argument('--forecast');parser.add_argument('--upstream-protocol');parser.add_argument('--case');args=parser.parse_args()
    if args.action=='prepare':prepare(args.panel,args.forecast,args.upstream_protocol)
    else:run(args.case)
