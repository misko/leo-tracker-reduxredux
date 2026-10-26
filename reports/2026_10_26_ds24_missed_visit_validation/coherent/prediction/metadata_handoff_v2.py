"""Restore exact R01 JSON reload boundary before enrichment; metadata only."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import study

HERE=Path(__file__).resolve().parent


def materialize(row):
    """JSON boundary removes shared donor-object aliases, exactly as original R01."""
    return json.loads(json.dumps(row,allow_nan=False))


def differences(a,b,path=''):
    if type(a)!=type(b):return [dict(path=path,old=a,new=b)]
    if isinstance(a,dict):
        result=[]
        for key in sorted(set(a)|set(b)):
            if key not in a or key not in b:result.append(dict(path=path+'/'+key,old=a.get(key),new=b.get(key)))
            else:result.extend(differences(a[key],b[key],path+'/'+key))
        return result
    if isinstance(a,list):
        if len(a)!=len(b):return[dict(path=path,old_length=len(a),new_length=len(b))]
        result=[]
        for i,(x,y)in enumerate(zip(a,b)):result.extend(differences(x,y,path+f'/{i}'))
        return result
    return []if a==b else[dict(path=path,old=a,new=b)]


def clean_ids(forecast):
    result=copy.deepcopy(forecast);result.pop('prediction_id',None)
    for mode in result.get('modes',[]):mode.pop('hypothesis_id',None)
    return result


def main():
    study.bound();port=study.ports()
    run=subprocess.run([sys.executable,'-B','-m','unittest','-v','test_metadata_handoff_v2.py'],cwd=HERE,
        text=True,capture_output=True,timeout=30)
    if run.returncode:raise RuntimeError(run.stderr)
    study.write(HERE/'metadata_handoff_v2_test_results.json',dict(exit_code=0,expected_tests=1,stderr=run.stderr,stdout=run.stdout))
    names=['metadata_handoff_v2.py','test_metadata_handoff_v2.py','metadata_handoff_v2_test_results.json',
           'protocol.json','panel.json','predictions.json','prediction_packets.json','donor_authority.json']
    study.write(HERE/'metadata_handoff_v2_protocol.json',dict(schema='R01-expansion-metadata-handoff-correction/v2',
        files={str(HERE/name):study.sha(HERE/name)for name in names},
        scope='restore original R01 JSON reload boundary; stream_generation label correction only',
        predictor_or_numeric_change=False,new_target_outcomes=False,raw_IQ_reads=0,scoring_calls=0))
    panel=study.read(HERE/'panel.json');slots={s['request_id']:s for s in panel['slots']}
    predictions=study.read(HERE/'predictions.json');original=study.read(HERE/'prediction_packets.json')
    authority=study.read(HERE/'donor_authority.json')['rows']
    lookup={(r['case'],r['visit_index']):r['raw_authority']for r in authority if r['status']=='metadata_verified'}
    rows=[]
    for row in predictions['rows']:
        slot=slots[row['header']['request_id']]
        packet=port['handoff'].enrich(materialize(row),slot,lookup)
        packet['block_ids']=slot['block_ids'];packet['overlaps_original_sparse_panel']=slot['overlaps_original_sparse_panel']
        rows.append(packet)
    corrected=copy.deepcopy(original);corrected['rows']=rows
    corrected['metadata_handoff_v2_protocol_sha256']=study.sha(HERE/'metadata_handoff_v2_protocol.json')
    corrected['source_v1_packet_sha256']=study.sha(HERE/'prediction_packets.json')
    changed=differences(original['rows'],rows)
    assert changed and all(d['path'].endswith('/stream_generation')and isinstance(d['old'],int)and isinstance(d['new'],str)for d in changed)
    study.write(HERE/'prediction_packets_v2.json',corrected)
    old=study.read(study.R01/'prediction_packets.json')
    old_by_key={(r['header']['case'],r['header']['visit_index'],r['header']['receiver_id']):r for r in old['rows']}
    raw={r['header']['prediction_id']:r for r in predictions['rows']};by_id={r['header']['prediction_id']:r for r in rows}
    overlap=0
    for slot in panel['slots']:
        acq=slot['raw_authority']['index']['acquisition']
        for cell in slot['cells']:
            h=cell['header'];row=raw[h['prediction_id']];packet=by_id[h['prediction_id']]
            assert port['predictor'].predict(h,cell['history'])==row['forecast']
            assert port['predictor'].predict(dict(h,target_candidates=[dict(CFO_hz=1e99)]),cell['history'])==row['forecast']
            assert packet['donor_metadata_status']=='verified'
            assert packet['header']['generation']==acq['generation']
            assert packet['header']['stream_generation']==h['generation']
            for mode in packet['forecast']['modes']:
                for donor in mode['donors']:
                    assert donor['stream_generation']==h['generation']
                    assert donor['support']['generation']==acq['generation']
                    assert donor['support']['stop_counter']<=h['start_counter']
            key=(h['case'],h['visit_index'],h['receiver_id'])
            if key in old_by_key:
                assert clean_ids(packet['forecast'])==clean_ids(old_by_key[key]['forecast'])
                assert packet['target_support']==old_by_key[key]['target_support'];overlap+=1
    assert len(rows)==526 and len(panel['slots'])==263 and overlap==8
    study.write(HERE/'verification_attempt01.json',dict(status='failed_metadata_aliasing',
        v1_packets_sha256=study.sha(HERE/'prediction_packets.json'),failed_audit_source_sha256=study.sha(HERE/'verify.py'),
        reason='live shared donor objects crossed an enrichment boundary that original R01 executes after JSON reload',
        superseded_by='prediction_packets_v2.json',raw_IQ_reads=0))
    study.write(HERE/'metadata_diff_v2.json',dict(source_v1_sha256=study.sha(HERE/'prediction_packets.json'),
        corrected_v2_sha256=study.sha(HERE/'prediction_packets_v2.json'),changed_row_fields=len(changed),differences=changed,
        all_row_differences_are_stream_generation_labels=True,numerical_forecasts_and_native_ownership_identical=True,
        additional_top_level_provenance_fields=['metadata_handoff_v2_protocol_sha256','source_v1_packet_sha256']))
    study.write(HERE/'verification_v2.json',dict(all_passed=True,selector_tests=3,shared_donor_boundary_regression_tests=1,
        receiver_cells=526,fresh_exact_R01_forecasts=526,fresh_target_response_redactions=526,
        target_native_authority_windows=263,selected_native_donor_authority_windows=len(authority),
        original_sparse_overlap_cells_exact_forecast_and_ownership_parity=overlap,
        v1_row_fields_changed=len(changed),only_stream_generation_labels_changed=True,
        numerical_forecasts_and_native_ownership_identical=True,predictions_sha256=study.sha(HERE/'predictions.json'),
        corrected_packets_sha256=study.sha(HERE/'prediction_packets_v2.json'),
        raw_IQ_reads=0,scoring_calls=0,new_per_window_paired_detector_parity=False))
    study.write(HERE/'forecast_seal_v2.json',dict(protocol_sha256=study.sha(HERE/'protocol.json'),
        metadata_handoff_protocol_sha256=study.sha(HERE/'metadata_handoff_v2_protocol.json'),
        predictions_sha256=study.sha(HERE/'predictions.json'),packets_sha256=study.sha(HERE/'prediction_packets_v2.json'),
        metadata_diff_sha256=study.sha(HERE/'metadata_diff_v2.json'),verification_sha256=study.sha(HERE/'verification_v2.json'),
        paired_windows=263,receiver_cells=526,raw_IQ_reads=0,scoring_calls=0,
        source_v1_preserved=True,corrected_rows_only_stream_generation_labels=True))
    print(json.dumps(study.read(HERE/'forecast_seal_v2.json')),flush=True)


if __name__=='__main__':main()
