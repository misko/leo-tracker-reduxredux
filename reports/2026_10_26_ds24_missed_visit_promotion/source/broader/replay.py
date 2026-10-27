"""Sealed, bounded orchestration; scientific acquisition ports remain unchanged."""
import argparse
import concurrent.futures
import os
from pathlib import Path
import subprocess
import sys
import time
import application as app

HERE=app.HERE;RAW=app.RAW

def engine():
    base=app.module('frozen_coherent_replay',app.R02/'timing/expansion.py')
    base.OUT=RAW
    return base

def verify_equal(old_slots,new_slots,old_packets,new_packets):
    assert old_slots==new_slots, 'target, donor, original-input or block identity differs'
    assert old_packets==new_packets, 'serialized R01 forecast/native identity differs'

def prepare():
    upstream=app.read(HERE/'forecast_protocol.json');audit=app.read(HERE/'metadata_audit.json')
    assert audit['all_passed']
    for path,h in upstream['files'].items():assert app.sha(path)==h,path
    base=engine();base.frozen_modules(); old=app.read(app.R01/'timing/protocol.json')
    files=dict(old['files']);files.update(upstream['files'])
    panel=app.read(HERE/'panel.json');forecasts=app.read(HERE/'prediction_packets_v2.json')
    original_panel=app.read(app.PRED/'panel.json')['slots']
    original_forecast=app.read(app.PRED/'prediction_packets_v2.json')['rows']
    original_raw=app.R02/'timing/expansion_v2'
    original_protocol=app.read(original_raw/'protocol.json')
    # Exact scientific sources, historical implementation, and frozen v2 provenance.
    for path,h in original_protocol['files'].items():assert app.sha(path)==h,path
    assert original_protocol['runtime_identity']==old['runtime_identity']
    reused=[]
    for case in ['DS24-0011','DS24-0097']:
        old_slots=[s for s in original_panel if s['case']==case]
        new_slots=[s for s in panel['slots'] if s['case']==case]
        old_packets=[p for p in original_forecast if p['header']['case']==case]
        new_packets=[p for p in forecasts['rows'] if p['header']['case']==case]
        verify_equal(old_slots,new_slots,old_packets,new_packets)
        path=original_raw/'outcomes'/(case+'.json.gz');doc=app.read(path)
        assert doc['protocol_sha256']==app.sha(original_raw/'protocol.json')
        assert all(r['status']=='complete' for r in doc['rows'])
        for slot,row in zip(old_slots,doc['rows'],strict=True):
            assert row['request_id']==slot['request_id'] and row['native_receipt']['full_reader_exhausted']
            assert row['native_receipt']['native_IQ_sha256']==slot['raw_authority']['index']['iq_sha256']
            for cell in row['cells']:
                if cell['result']['status']!='complete':
                    assert cell['result']['status']=='no_donor'
                    continue
                selection=original_raw/'selections'/(cell['prediction_id'].replace('/','_')+'.json')
                assert app.read(selection)==cell['result']['selection_receipt']
                files[str(selection)]=app.sha(selection)
        files[str(path)]=app.sha(path)
        reused.append(dict(case=case,outcome_path=str(path),selection_root=str(original_raw),
            upstream_protocol_path=str(original_raw/'protocol.json'),upstream_protocol_sha256=app.sha(original_raw/'protocol.json'),
            outcome_sha256=app.sha(path),exact_panel_and_serialized_forecast_equality=True,
            native_IQ_hashes_and_full_reader_exhaustion_verified=True,new_IQ_reads=0))
    reuse_receipt=dict(all_passed=True,cases=reused,source_input_native_protocol_equality=True)
    if (HERE/'reuse_audit.json').exists():assert app.read(HERE/'reuse_audit.json')==reuse_receipt
    else:app.write(HERE/'reuse_audit.json',reuse_receipt)
    files.update({str(p):app.sha(p) for p in [Path(__file__),HERE/'forecast_protocol.json',HERE/'reuse_audit.json',
        HERE/'test_application.py',HERE/'test_replay.py',app.R02/'timing/expansion.py',app.R02/'timing/test_expansion.py',
        app.R01/'validation/coherent_application/integrate.py',app.R01/'validation/prepare_overlay.py',
        app.R01/'validation/integration.py',app.R01/'validation/coherent_application/graph.py',
        app.SOURCE/'engine/ds24_engine.py']})
    from leo.processing.fast_scan import implementation_identity
    code,env=implementation_identity()
    assert (code,env)==(old['runtime_identity']['code_digest'],old['runtime_identity']['environment_digest'])
    tests=[]
    for cwd,names in [(HERE,['test_application','test_replay']),(app.R02/'timing',['test_expansion'])]:
        test=subprocess.run([sys.executable,'-B','-m','unittest','-v']+names,cwd=cwd,capture_output=True,text=True,timeout=60)
        tests.append(dict(cwd=str(cwd),modules=names,exit_code=test.returncode,stdout=test.stdout,stderr=test.stderr))
        assert test.returncode==0,test.stderr
    app.write(HERE/'raw_test_results.json',dict(all_passed=True,runs=tests))
    files[str(HERE/'raw_test_results.json')]=app.sha(HERE/'raw_test_results.json')
    app.write(RAW/'protocol.json',dict(schema='frozen-all24-R01-coherent-application/v1',files=files,
        panel_path=str(HERE/'panel.json'),forecast_path=str(HERE/'prediction_packets_v2.json'),
        cases=panel['cases'],runtime_identity=old['runtime_identity'],metadata_handoff_version=2,
        no_new_recovered_donors=True,process_bound_seconds=580,maximum_workers=2,BLAS_threads=1,
        fresh_cases=[r['case'] for r in app.read(HERE/'nominations.json')['cases'] if r['paired_windows'] and r['case'] not in ['DS24-0011','DS24-0097']],
        reused_cases=['DS24-0011','DS24-0097'],raw_IQ_reads_before_freeze=0,
        no_eligible_cases=[r['case'] for r in app.read(HERE/'nominations.json')['cases'] if not r['paired_windows']]))
    app.write(RAW/'run_authorization.json',dict(protocol_sha256=app.sha(RAW/'protocol.json'),raw_scoring_authorized=True,
        authority='root frozen PLAN plus explicit delegated execution after source/input/native audit',no_new_RF=True))
    print(dict(protocol=app.sha(RAW/'protocol.json'),fresh_cases=app.read(RAW/'protocol.json')['fresh_cases']),flush=True)

def dispatch(case):
    began=time.monotonic();cmd=[sys.executable,'-B',str(Path(__file__)),'run','--case',case]
    with (RAW/'logs'/(case+'.log')).open('x') as log:
        try:
            result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=600)
            receipt=dict(case=case,exit_code=result.returncode,seconds=time.monotonic()-began)
        except subprocess.TimeoutExpired:
            receipt=dict(case=case,status='outer_600second_guard',seconds=time.monotonic()-began)
    app.write(RAW/'terminal'/(case+'.json'),receipt)
    print(receipt,flush=True)
    return receipt

def launch():
    p=app.read(RAW/'protocol.json');(RAW/'logs').mkdir(parents=True,exist_ok=True)
    assert all(os.environ.get(k)=='1' for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'])
    # Frozen cases list is reserved-first; no outcome-dependent retries.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for receipt in pool.map(dispatch,p['fresh_cases']):pass

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run','launch']);p.add_argument('--case');a=p.parse_args()
    if a.action=='run':engine().run(a.case)
    else:globals()[a.action]()
