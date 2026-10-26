"""Bounded metadata application of the two immutable missed-visit predictors."""
import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
R01=ROOT/'prediction'
R02=Path('/srv/bulk/leo/research/ds24-missed-visit-r02/prediction')
MAPPER=Path('/srv/bulk/leo/research/ds24-detector-response-r01/influence/raw_metadata.py')
TRACK=Path('/srv/bulk/leo/research/ds25-20261024')
INPUT=Path('/srv/bulk/leo/fast-scan-inputs')
CHANNELS=[1,4,5,6,7,8]
FRACTIONS=[.2,.4,.6,.8]
BINDINGS={
    R01/'protocol.json':'f31f786c6231be33497faf4071c32ffb6d9f6574fabae3cb4fbba262e8fc771d',
    R01/'predictor.py':'7910f860cd99e24e84c13c4a6f424acd3d98191413e4d4858a5a6b418e918823',
    R01/'study.py':'75a9fe75e21af1de69416d3912c4760e15b2a3dfb70e0351612595ef7dfc9913',
    R01/'handoff.py':'a6c86100d876f8e0213f8a2186e806bce921122930c955913a770135d151d2e7',
    R02/'protocol.json':'77ba1b8f357ddbb900da0d965822aefbc484b1b936e31c00b24ea9329c326758',
    R02/'predictor.py':'b1b49492a84c9d2e61c59c5416061540964f318c788d0f67871d9fe09c982c3d',
    ROOT/'split.json':'acb7a47cfca7a109db0a722a2801808cbd467a7e66f0b7fdfb5cdc30388756c5',
    MAPPER:'94dee28c90493763247024de7ce3e0b951c78295eb0c591606f30ce21e9eeb26',
}


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x')as stream:json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')
def materialize(value):return json.loads(json.dumps(value,allow_nan=False))


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def ports():
    for path,digest in BINDINGS.items():
        if sha(path)!=digest:raise ValueError('sealed method changed: '+str(path))
    first=module('held_frozen_R01_predictor',R01/'predictor.py')
    sys.modules['predictor']=first
    oldstudy=module('held_frozen_R01_study',R01/'study.py')
    sys.modules['study']=oldstudy
    return dict(r01=first,r02=module('held_frozen_R02_predictor',R02/'predictor.py'),
        study=oldstudy,handoff=module('held_frozen_R01_handoff',R01/'handoff.py'),
        mapper=module('held_public_metadata_mapper',MAPPER),
        adapter=module('held_frozen_R01_adapter',ROOT/'timing/adapter.py'))


def bound(check=True):
    for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:
        if os.environ.get(key)!='1':raise ValueError('BLAS1 required')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('580-second bound')))
    signal.alarm(580)
    if check:
        for path,digest in read(HERE/'protocol.json')['files'].items():
            if sha(path)!=digest:raise ValueError('frozen application input changed: '+path)


def empty_slots(case,reason):
    slots=[]
    for channel in CHANNELS:
        for fraction in FRACTIONS:
            request=f'{case}-CH{channel}-F{int(100*fraction)}'
            cells=[dict(header=dict(prediction_id=f'{request}/RX{rx}',request_id=request,
                case=case,channel=channel,receiver_id=rx,fraction=fraction,
                sample_rate_hz=10000000,window_samples=200000),history=[])for rx in [0,1]]
            slots.append(dict(request_id=request,case=case,channel=channel,fraction=fraction,
                status='missing',reason=reason,cells=cells))
    return slots


def make_slots(case,source,tracking_path,tracking_digest,input_path,input_digest):
    """Exact R01 metadata selection and history rule; no target candidate access."""
    if source['sample_rate_hz']!=10000000 or source['probe_ms']!=20:
        raise ValueError('unhandled native geometry')
    probes=source['probes']
    low=min(p['valid_start_counter']for p in probes);high=max(p['valid_start_counter']for p in probes)
    slots=[]
    for channel in CHANNELS:
        visits=[p for p in probes if p['channel']==channel and p['receiver_id']==0]
        for fraction in FRACTIONS:
            request=f'{case}-CH{channel}-F{int(100*fraction)}'
            slot=dict(request_id=request,case=case,channel=channel,fraction=fraction,status='missing',cells=[],
                tracking=dict(path=str(tracking_path),sha256=tracking_digest),
                source_input=dict(path=str(input_path),sha256='sha256:'+input_digest))
            chosen=min(visits,key=lambda p:(abs(p['valid_start_counter']-(low+fraction*(high-low))),
                p['valid_start_counter']),default=None)
            if chosen is None:
                slot.update(reason='no processed channel visit',cells=empty_slots(case,'no channel visit')[CHANNELS.index(channel)*4+FRACTIONS.index(fraction)]['cells'])
                slots.append(slot);continue
            slot.update(status='nominated',probe_metadata={k:v for k,v in chosen.items()if k!='candidates'})
            for rx in [0,1]:
                same=[p for p in probes if p['channel']==channel and p['edge']==chosen['edge']and p['receiver_id']==rx]
                header=dict(prediction_id=f'{request}/RX{rx}',request_id=request,case=case,channel=channel,
                    receiver_id=rx,edge=chosen['edge'],fraction=fraction,sample_rate_hz=source['sample_rate_hz'],
                    window_samples=200000,start_counter=chosen['valid_start_counter'],
                    stop_counter=chosen['valid_start_counter']+200000,visit_index=chosen['visit_index'],
                    probe_index=chosen['probe_index'],generation=source['stream_generation'],
                    source_id=source['session_id'],actual_rf_hz=chosen['actual_rf_hz'],
                    tracking_sha256=tracking_digest,raw_recording_authority_digest=source['raw_recording_authority_digest'])
                history=sorted([p for p in same if p['valid_start_counter']+200000<=header['start_counter']and
                    0<(header['start_counter']-p['valid_start_counter'])/source['sample_rate_hz']<=4.5],
                    key=lambda p:p['valid_start_counter'])[-12:]
                slot['cells'].append(dict(header=header,history=history))
            slots.append(slot)
    return slots


def prepare():
    began=time.monotonic();bound(False);port=ports()
    owned=['PROTOCOL.md','INTERFACE.md','application.py','test_application.py']
    inputs=list(BINDINGS)+[ROOT/'HELD_VALIDATION_PLAN.md',R02/'INTERFACE.md',ROOT/'timing/adapter.py']
    run=subprocess.run([sys.executable,'-B','-m','unittest','-v','test_application.py'],cwd=HERE,
        capture_output=True,text=True,timeout=30)
    if run.returncode:raise RuntimeError(run.stderr)
    write(HERE/'test_results.json',dict(expected_tests=3,exit_code=0,stdout=run.stdout,stderr=run.stderr))
    files={str(p):sha(p)for p in inputs+[HERE/n for n in owned]+[HERE/'test_results.json']}
    slots=[]
    for case in read(ROOT/'split.json')['validation']:
        path=TRACK/case/'tracking.json'
        try:
            data=read(path);files[str(path)]=sha(path)
            # Existing R01 public inventory reference rule, not an IQ storage path.
            input_path=INPUT/(data['source']['session_id']+'.json');files[str(input_path)]=sha(input_path)
            chosen=make_slots(case,data['source'],path,files[str(path)],input_path,files[str(input_path)])
            for slot in chosen:
                if slot['status']!='nominated':continue
                try:slot['raw_authority']=port['mapper'].one(port['study'].request(slot,slot['probe_metadata']))
                except Exception as exc:slot.update(status='missing',reason=repr(exc))
        except Exception as exc:chosen=empty_slots(case,repr(exc))
        slots.extend(chosen);print(case,'metadata slots',len(chosen),flush=True)
    write(HERE/'panel.json',dict(schema='sparse-held-recording-panel/v1',
        selection='exact R01 metadata-only native-counter fractions',validation=read(ROOT/'split.json')['validation'],
        fractions=FRACTIONS,channels=CHANNELS,requested_windows=288,requested_receiver_cells=576,
        slots=slots,target_candidate_fields_excluded=True,target_outcomes_analyzed=False))
    files[str(HERE/'panel.json')]=sha(HERE/'panel.json')
    write(HERE/'protocol.json',dict(schema='frozen-R01-R02-held-application/v1',files=files,
        frozen_utc_ns=time.time_ns(),paired_slots=288,receiver_cells=576,
        tracking_exports_parsed_for_metadata_and_earlier_donors=True,
        target_responses_selected_or_analyzed=False,target_evaluation_archive_created=False,
        raw_IQ_reads=0,scoring_calls=0,geography_used=False,process_bound_seconds=580,BLAS_threads=1,
        earlier_panel_targets_may_be_original_donors=True,seconds=time.monotonic()-began))
    print('protocol',sha(HERE/'protocol.json'),flush=True)


def generate():
    began=time.monotonic();bound();port=ports();panel=read(HERE/'panel.json')
    slots={s['request_id']:s for s in panel['slots']};rows=[]
    for slot in panel['slots']:
        for cell in slot['cells']:
            row=dict(header=cell['header'],status='failed')
            try:
                if 'start_counter'not in cell['header']:
                    row.update(status='missing',forecast=dict(status='no_donor',modes=[]))
                else:row.update(status='complete',forecast=port['r01'].predict(cell['header'],cell['history']))
            except Exception as exc:row['error']=repr(exc)
            rows.append(row)
    write(HERE/'r01_predictions.json',dict(schema=port['r01'].VERSION,protocol_sha256=sha(HERE/'protocol.json'),
        panel_sha256=sha(HERE/'panel.json'),rows=rows,target_outcomes_read=False,raw_IQ_reads=0))
    # Mandatory serialization/reload: shared live donor objects must not cross enrich.
    serialized=read(HERE/'r01_predictions.json');unique={}
    for row in serialized['rows']:
        for mode in row.get('forecast',{}).get('modes',[]):
            for donor in mode['donors']:
                unique.setdefault((row['header']['case'],donor['visit_index']),(row['header'],donor))
    authority=[]
    for (case,visit),(header,donor)in sorted(unique.items()):
        slot=slots[header['request_id']]
        probe=next(p for c in slot['cells']for p in c['history']if p['visit_index']==visit)
        item=dict(case=case,visit_index=visit,status='failed')
        try:item.update(status='metadata_verified',raw_authority=port['mapper'].one(port['study'].request(slot,probe)))
        except Exception as exc:item['error']=repr(exc)
        authority.append(item)
    write(HERE/'donor_authority.json',dict(rows=authority,requested_donor_windows=len(unique),raw_IQ_reads=0))
    write(HERE/'handoff_protocol.json',dict(schema='sparse-prediction-native-ownership/v1',
        files={str(p):sha(p)for p in [R01/'handoff.py',HERE/'protocol.json',HERE/'panel.json',
            HERE/'r01_predictions.json',HERE/'donor_authority.json']},
        restored_original_JSON_reload_boundary=True,numerical_changes=False,raw_IQ_reads=0))
    lookup={(r['case'],r['visit_index']):r['raw_authority']for r in authority if r['status']=='metadata_verified'}
    packets=[]
    for row in serialized['rows']:
        slot=slots[row['header']['request_id']]
        if 'raw_authority'in slot:packet=port['handoff'].enrich(materialize(row),slot,lookup)
        else:
            packet=materialize(row);packet.update(target_support=None,donor_metadata_status='unavailable')
        packets.append(packet)
    write(HERE/'r01_prediction_packets.json',dict(schema='sparse-native-prediction-packets/v1',
        handoff_protocol_sha256=sha(HERE/'handoff_protocol.json'),frozen_predictions_sha256=sha(HERE/'r01_predictions.json'),
        rows=packets,outcome_inputs=False,raw_IQ_reads=0,numerical_forecasts_unchanged=True))
    # Each method remains separate and sees no target measurement.
    second=[]
    for row in read(HERE/'r01_prediction_packets.json')['rows']:
        try:result=port['r02'].predict(row)
        except Exception as exc:result=dict(header=row['header'],prediction_id=row['header']['prediction_id'],status='failed',error=repr(exc),methods={})
        second.append(result)
    write(HERE/'r02_predictions.json',dict(schema=port['r02'].VERSION,protocol_sha256=sha(HERE/'protocol.json'),
        original_R02_protocol_sha256=BINDINGS[R02/'protocol.json'],source_packets_sha256=sha(HERE/'r01_prediction_packets.json'),
        rows=second,target_outcomes_read=False,raw_IQ_reads=0))
    common=dict(application_protocol_sha256=sha(HERE/'protocol.json'),panel_sha256=sha(HERE/'panel.json'),
        receiver_cells=len(rows),paired_slots=len(panel['slots']),raw_IQ_reads=0,scoring_calls=0,
        target_outcomes_analyzed_before_seal=False,frozen_utc_ns=time.time_ns())
    write(HERE/'r01_forecast_seal.json',dict(common,original_protocol_sha256=BINDINGS[R01/'protocol.json'],
        predictions_sha256=sha(HERE/'r01_predictions.json'),packets_sha256=sha(HERE/'r01_prediction_packets.json'),
        handoff_protocol_sha256=sha(HERE/'handoff_protocol.json'),statuses=dict(Counter(r.get('forecast',{}).get('status',r['status'])for r in rows))))
    write(HERE/'r02_forecast_seal.json',dict(common,original_protocol_sha256=BINDINGS[R02/'protocol.json'],
        predictions_sha256=sha(HERE/'r02_predictions.json'),source_packets_sha256=sha(HERE/'r01_prediction_packets.json'),
        statuses=dict(Counter(r['status']for r in second))))
    print('R01',sha(HERE/'r01_prediction_packets.json'),'R02',sha(HERE/'r02_predictions.json'),
          'seconds',round(time.monotonic()-began,3),flush=True)


def verify():
    began=time.monotonic();bound();port=ports()
    panel=read(HERE/'panel.json');raw=read(HERE/'r01_predictions.json')['rows']
    packets=read(HERE/'r01_prediction_packets.json')['rows'];second=read(HERE/'r02_predictions.json')['rows']
    assert len(panel['slots'])==288 and len(raw)==len(packets)==len(second)==576
    raw_by_id={r['header']['prediction_id']:r for r in raw}
    packet_by_id={r['header']['prediction_id']:r for r in packets}
    second_by_id={r['prediction_id']:r for r in second}
    assert sha(HERE/'r01_prediction_packets.json')==read(HERE/'r01_forecast_seal.json')['packets_sha256']
    assert sha(HERE/'r02_predictions.json')==read(HERE/'r02_forecast_seal.json')['predictions_sha256']
    authority=read(HERE/'donor_authority.json')['rows']
    lookup={(r['case'],r['visit_index']):r['raw_authority']for r in authority if r['status']=='metadata_verified'}
    fresh=redacted=native=primary=0;channels=set();missing=0
    for slot in panel['slots']:
        assert 'candidates'not in slot.get('probe_metadata',{})
        for cell in slot['cells']:
            h=cell['header'];row=raw_by_id[h['prediction_id']];packet=packet_by_id[h['prediction_id']]
            result=second_by_id[h['prediction_id']]
            if 'start_counter'not in h:missing+=1;continue
            assert port['r01'].predict(h,cell['history'])==row['forecast'];fresh+=1
            assert port['r01'].predict(dict(h,target_candidates=[dict(epoch_samples=1e99)]),cell['history'])==row['forecast'];redacted+=1
            assert all(p['valid_start_counter']+200000<=h['start_counter']for p in cell['history'])
            if 'raw_authority'in slot:
                assert port['handoff'].enrich(materialize(row),slot,lookup)==packet
                support=port['handoff'].native_support(slot['raw_authority'])
                assert packet['target_support']==support and isinstance(packet['header']['generation'],int)
                assert packet['header']['stream_generation']==h['generation'];native+=1
                channels.add((h['channel'],h['receiver_id']))
                for mode in packet.get('forecast',{}).get('modes',[]):
                    for donor in mode['donors']:
                        assert donor['stream_generation']==h['generation']
                        assert isinstance(donor['generation'],int)
                        assert donor['support']['generation']==support['generation']
                        assert donor['support']['stop_counter']<=h['start_counter']
            assert port['r02'].predict(packet)==result
            poison=dict(packet,header=dict(packet['header'],target_candidates=[dict(CFO_hz=1e99)]),
                target_original=dict(candidates=[dict(epoch_samples=-1e99)]))
            assert port['r02'].predict(poison)==result
            if not result['methods']:continue
            mode=packet['forecast']['modes'][0];full=mode['full']
            assert result['donors']==mode['donors']and result['primary_hypothesis_id']==mode['hypothesis_id']
            assert result['methods']['linear']['epoch_samples']==full['epoch_samples']
            assert result['methods']['legacy_adapter_linear']['epoch_samples']==port['adapter'].adapt(packet)['modes'][0]['epoch_samples']
            for point in result['methods'].values():
                assert point['cfo_hz']==full['CFO_hz']and point['cfo_rate_hz_s']==full['CFO_rate_hz_per_s']
                assert point['cfo_reference_counter']==full['reference_counter']
                assert point['cfo_half_width_hz']==full['CFO_half_width_hz']
            primary+=1
    write(HERE/'verification.json',dict(all_passed=True,owned_tests=3,receiver_cells=576,
        fresh_exact_R01=fresh,R01_target_response_redactions=redacted,
        exact_R02_and_target_redactions=576-missing,native_receiver_cells=native,
        all_channel_receiver_pairs=sorted(channels),selected_donor_windows=len(authority),
        donor_metadata_statuses=dict(Counter(r['status']for r in authority)),
        original_primary_CFO_and_exact_legacy_preserved=primary,missing_header_cells=missing,
        mandatory_JSON_reload_verified=True,target_outcomes_analyzed=False,
        new_per_window_paired_detector_parity=False,raw_IQ_reads=0,scoring_calls=0,
        seconds=time.monotonic()-began))
    example=next(r for r in packets if r.get('forecast',{}).get('modes'))
    write(HERE/'r01_example_packet.json',example)
    write(HERE/'r02_example_packet.json',second_by_id[example['header']['prediction_id']])
    summary=dict(paired_slots=288,receiver_cells=576,panel_statuses=dict(Counter(s['status']for s in panel['slots'])),
        R01_statuses=dict(Counter(r.get('forecast',{}).get('status',r['status'])for r in raw)),
        R02_statuses=dict(Counter(r['status']for r in second)),by_case=[])
    for case in read(ROOT/'split.json')['validation']:
        ids=[r['header']['prediction_id']for r in raw if r['header']['case']==case]
        summary['by_case'].append(dict(case=case,receiver_cells=len(ids),
            R01=dict(Counter(raw_by_id[i].get('forecast',{}).get('status',raw_by_id[i]['status'])for i in ids)),
            R02=dict(Counter(second_by_id[i]['status']for i in ids))))
    write(HERE/'summary.json',summary)
    print(json.dumps(read(HERE/'verification.json')),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','generate','verify'])
    globals()[parser.parse_args().action]()
