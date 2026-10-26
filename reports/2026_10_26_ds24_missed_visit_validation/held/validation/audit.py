"""Independent saved-outcome audit; never opens IQ or calls a score function."""
import argparse
from collections import Counter
import copy
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
PRED=HERE.parent/'prediction'
ROOT=HERE.parents[1]
TWO=Path('/srv/bulk/leo/research/ds24-missed-visit-r02')
RAW=TWO/'timing/held'
PROTOCOL_SHA='7bfccde3b823cf48c297ae23f21400ddd21f19b92ba9ed3867d4c5bd00dbf646'
BIN=10000000/(44*512)
METHODS=['R01_point','R01_search','R02_linear','R02_quadratic_or_fallback','R02_legacy_adapter_linear']


def read(path):
    with (gzip.open(path,'rt')if str(path).endswith('.gz')else Path(path).open())as f:return json.load(f)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def write(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with Path(path).open('x')as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def bound(check=True):
    for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:
        assert os.environ.get(key)=='1','BLAS1 required'
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('580second audit bound')));signal.alarm(580)
    assert sha(RAW/'protocol.json')==PROTOCOL_SHA
    approval=read(RAW/'run_authorization.json')
    assert approval['protocol_sha256']==PROTOCOL_SHA and approval['raw_scoring_authorized']
    if check:
        for p,h in read(HERE/'audit_protocol.json')['files'].items():assert sha(p)==h,p


def decision(score,point):
    complete=score is not None and score['status']=='complete'
    innovation=score['tracking_cfo_hz']-point['cfo_hz']if complete else None
    if complete:assert abs(innovation/BIN-round(innovation/BIN))<1e-7
    pilot=bool(complete and score['margin']>=.025)
    compatible=bool(complete and abs(innovation)<=point['cfo_half_width_hz'])
    return dict(pilot=pilot,compatible=compatible,admitted=pilot and compatible,
        innovation_hz=innovation,zero_bin=bool(complete and abs(innovation)<1e-8))


def summary(rows,method):
    return dict(cells=len(rows),original=sum(r['original']for r in rows),
        pilot=sum(r['methods'][method]['pilot']for r in rows),
        compatible=sum(r['methods'][method]['compatible']for r in rows),
        admitted=sum(r['methods'][method]['admitted']for r in rows),
        alternate_pilot=sum(r['methods'][method]['pilot']and not r['methods'][method]['compatible']for r in rows),
        new=sum(r['methods'][method]['admitted']and not r['original']for r in rows),
        original_reconfirmed=sum(r['methods'][method]['admitted']and r['original']for r in rows),
        lost_if_replacement=sum(not r['methods'][method]['admitted']and r['original']for r in rows),
        original_lost_additions_only=0,
        admitted_zero_bin=sum(r['methods'][method]['admitted']and r['methods'][method]['zero_bin']for r in rows),
        new_zero_bin=sum(r['methods'][method]['admitted']and not r['original']and r['methods'][method]['zero_bin']for r in rows),
        unavailable=sum(r['unavailable']for r in rows))


def rank(item):return(-item['score']['margin'],item['mode_index'],abs(item['score']['offset_samples']),item['score']['offset_samples'])


def prepare():
    bound(False);began=time.monotonic()
    if (HERE/'test_results.json').exists():assert read(HERE/'test_results.json')['exit_code']==0
    else:
        run=subprocess.run([sys.executable,'-B','-m','unittest','-v','test_audit.py'],cwd=HERE,capture_output=True,text=True,timeout=30)
        assert run.returncode==0,run.stderr
        write(HERE/'test_results.json',dict(exit_code=0,expected_tests=3,stderr=run.stderr,stdout=run.stdout))
    files=dict(read(RAW/'protocol.json')['files'])
    files.update({str(p):sha(p)for p in [RAW/'protocol.json',RAW/'run_authorization.json',
        PRED/'r01_predictions.json',ROOT/'prediction/predictor.py',ROOT/'prediction/handoff.py',
        TWO/'prediction/predictor.py']+[HERE/n for n in ['PROTOCOL.md','audit.py','report.py','test_audit.py','test_results.json']]})
    for p,h in files.items():assert sha(p)==h,p
    write(HERE/'audit_protocol.json',dict(files=files,timing_protocol_sha256=PROTOCOL_SHA,
        outcome_files_analyzed_before_audit_freeze=[],frozen_utc_ns=time.time_ns(),
        new_IQ_reads=0,new_scoring_calls=0,new_position_calls=0,seconds=time.monotonic()-began))
    print('audit source frozen',sha(HERE/'audit_protocol.json'),flush=True)


def case_audit(case):
    began=time.monotonic();bound();protocol=read(RAW/'protocol.json');assert case in protocol['cases']
    path=RAW/'outcomes'/(case+'.json.gz');hash_before=sha(path);document=read(path)
    assert sha(path)==hash_before and document['protocol_sha256']==PROTOCOL_SHA
    panel=read(PRED/'panel.json');slots={s['request_id']:s for s in panel['slots']if s['case']==case}
    assert len(document['rows'])==len(slots)==24 and {w['request_id']for w in document['rows']}==set(slots)
    for window in document['rows']:assert read(RAW/'checkpoints'/(window['request_id']+'.json.gz'))==window
    # A stable complete container and all final checkpoints establish the local
    # readback seal. It may contain failed windows, which remain in denominators.
    seal=dict(case=case,outcome_path=str(path),sha256=hash_before,windows=24,protocol_sha256=PROTOCOL_SHA)
    write(HERE/'source_seals'/(case+'.json'),seal)
    first=module('audit_frozen_R01',ROOT/'prediction/predictor.py')
    second=module('audit_frozen_R02',TWO/'prediction/predictor.py')
    adapter=module('audit_frozen_adapter',ROOT/'timing/adapter.py')
    geometry=module('audit_frozen_geometry_only',ROOT/'timing/timing_search.py')
    rawpred={r['header']['prediction_id']:r for r in read(PRED/'r01_predictions.json')['rows']}
    one={r['header']['prediction_id']:r for r in read(PRED/'r01_prediction_packets.json')['rows']}
    two={r['prediction_id']:r for r in read(PRED/'r02_predictions.json')['rows']}
    track=read(next(iter(slots.values()))['tracking']['path'])['source']
    original={(p['visit_index'],p['probe_index'],p['receiver_id']):p for p in track['probes']}
    rows=[];seen=set();indices={};sources={str(path):hash_before};readtime=0.;one_time=two_time=0.;failures=[]
    for window in document['rows']:
        slot=slots[window['request_id']];a=slot['raw_authority'];acq=a['index']['acquisition']
        if a['index_path']not in indices:indices[a['index_path']]='sha256:'+sha(a['index_path'])
        assert indices[a['index_path']]==a['index_sha256']
        status=window['status'];failed=status!='complete'
        if failed:failures.append(dict(request_id=window['request_id'],status=status,error=window.get('error')))
        else:
            receipt=window['native_receipt'];assert receipt['full_reader_exhausted']
            assert receipt['native_IQ_sha256']==a['index']['iq_sha256']
            assert receipt['repeated_blind_acquisition_calls']==0 and receipt['fresh_per_window_paired_candidate_parity']is False
            assert {c['receiver_id']for c in window['cells']}=={0,1}
            readtime+=receipt['native_read_verify_seconds']
        by_rx={c['receiver_id']:c for c in window['cells']}
        for cell in slot['cells']:
            h=cell['header'];pid=h['prediction_id'];r01=one[pid];r02=two[pid]
            orig=original[h['visit_index'],h['probe_index'],h['receiver_id']]
            orig_pass=any(c['passed_fractional_margin_gate']for c in orig['candidates'])
            assert first.predict(h,cell['history'])==rawpred[pid]['forecast']
            assert first.predict(dict(h,target_candidates=[dict(CFO_hz=1e99)]),cell['history'])==rawpred[pid]['forecast']
            assert second.predict(r01)==r02
            owner=f"{h['source_id']}/rx{h['receiver_id']}/{h['start_counter']}:{h['stop_counter']}"
            assert owner not in seen;seen.add(owner)
            assert (h['start_counter'],h['stop_counter'])==(acq['sample_start'],acq['sample_end'])
            assert r01['header']['generation']==acq['generation']and isinstance(acq['generation'],int)
            assert r01['header']['stream_generation']==h['generation']and isinstance(h['generation'],str)
            assert r01['target_support']==r02['target_support']
            assert h['actual_rf_hz']==a['target']['rf_center_hz']and h['edge']==a['target']['edge']
            for mode in r01['forecast']['modes']:
                for donor in mode['donors']:
                    assert donor['stop_counter']<=h['start_counter']
                    assert donor['generation']==acq['generation']and donor['stream_generation']==h['generation']
                    assert donor['support']['stop_counter']==donor['stop_counter']
            row=dict(prediction_id=pid,case=case,channel=h['channel'],native_receiver_id=h['receiver_id'],
                display_receiver=h['receiver_id']+1,owner_id=owner,original=orig_pass,unavailable=failed,
                R01_forecast_status=r01['forecast']['status'],R02_forecast_status=r02['status'],methods={})
            for name in METHODS:row['methods'][name]=decision(None,{})
            if failed:rows.append(row);continue
            recorded=by_rx[h['receiver_id']];result=recorded['result'];packet=result['r01_packet'];one_result=result['r01'];two_result=result['r02']
            assert recorded['original_fullwindow']==orig and recorded['original_used_for_evaluation_only']
            assert recorded['r02_prediction']==r02
            assert packet==adapter.adapt(r01,a)
            assert one_result['owner_id']==two_result['owner_id']==owner
            assert one_result['mode_provenance']==packet['modes']
            assert result['methods_remain_separate']and not result['best_method_selected']and result['shared_verified_raw_samples']
            assert two_result['target_support']==r02['target_support']
            assert two_result['primary_operational_method']=='quadratic_or_fallback'and not two_result['target_timing_or_mode_search']
            one_time+=result['r01_scoring_seconds'];two_time+=result['r02_scoring_seconds']
            if one_result.get('search'):
                ownership=one_result['ownership'];expected=geometry.partition(h['window_samples'],h['sample_rate_hz'],packet['modes'][0]['epoch_samples'],owner)
                assert ownership==expected
                receipt=one_result['selection_receipt'];saved=read(RAW/'selections'/(pid.replace('/','_')+'.json'))
                assert saved==receipt and receipt['confirmation_accessed']is False
                content=copy.deepcopy(receipt);content.pop('selection_sha256')
                assert digest(content)==receipt['selection_sha256']and receipt['earlier_packet_sha256']==digest(packet)
                candidates=[x for x in one_result['exposure']if x['score']['status']=='complete']
                assert min(candidates,key=rank)==receipt['selected']==one_result['search']['selected']
                points=[x for x in candidates if x['stage']=='coarse'and x['score']['offset_samples']==0]
                assert (min(points,key=rank)if points else None)==receipt['point_selected']
                sources[str(RAW/'selections'/(pid.replace('/','_')+'.json'))]=sha(RAW/'selections'/(pid.replace('/','_')+'.json'))
                for key in ['point','search']:
                    item=one_result.get(key)
                    if item is None:continue
                    selected=item['selected'];mode=packet['modes'][selected['mode_index']]
                    assert selected==receipt['point_selected'if key=='point'else'selected']
                    score=item['confirmation'];decision_saved=decision(score,mode)
                    for field,ours in [('pilot_confirmed','pilot'),('continuity_compatible','compatible'),('admitted','admitted')]:
                        assert item['evaluation'][field]==decision_saved[ours]
                    blocks=geometry.geometry(h['window_samples'],h['sample_rate_hz'],score['epoch_samples'],ownership,'confirmation')
                    assert item['native_confirmation_blocks']==blocks
                    for block in blocks:
                        assert any(i['group']=='confirmation'and i['start']<=block['sample_start']<block['sample_stop']<=i['stop']for i in ownership['intervals'])
                    if key=='search':
                        assert item['native_search_blocks']==geometry.geometry(h['window_samples'],h['sample_rate_hz'],score['epoch_samples'],ownership,'search')
                    row['methods']['R01_'+key]=dict(decision_saved,selected_mode=selected['mode_index'])
            for name,item in two_result['methods'].items():
                assert item['point']==r02['methods'][name]
                chosen=decision(item['score'],item['point'])
                for field,ours in [('pilot_confirmed','pilot'),('continuity_compatible','compatible'),('admitted','admitted')]:assert item[field]==chosen[ours]
                assert item['frequency_innovation_hz']==chosen['innovation_hz']
                assert item['full_target_support_used']and item['timing_search_evaluations']==0 and not item['frequency_posterior_used']
                row['methods']['R02_'+name]=chosen
            if r02['methods']:
                assert two_result['operational_admitted']==row['methods']['R02_quadratic_or_fallback']['admitted']
                if r02['status']=='linear_fallback':assert row['methods']['R02_linear']==row['methods']['R02_quadratic_or_fallback']
            else:assert two_result['methods']=={}and not packet['modes']
            rows.append(row)
    assert len(rows)==len(seen)==48 and sha(path)==hash_before
    write(HERE/'case_audits'/(case+'.json'),dict(all_passed=True,case=case,source_seal=seal,
        cells=rows,counts={m:summary(rows,m)for m in METHODS},failures=failures,
        native_index_files_verified=len(indices),original_IQ_rehashed_by_this_audit=False,
        native_reader_exhaustion_verified_from_locked_producer_receipts=True,
        source_hashes=sources,reader_seconds=readtime,R01_scoring_seconds=one_time,R02_scoring_seconds=two_time,
        producer_process_seconds=document['seconds'],audit_seconds=time.monotonic()-began,
        new_IQ_reads=0,new_scoring_calls=0,new_position_calls=0))
    print(case,json.dumps({m:summary(rows,m)for m in METHODS}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','case']);p.add_argument('--case');args=p.parse_args()
    prepare()if args.action=='prepare'else case_audit(args.case)
