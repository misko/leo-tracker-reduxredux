"""Independent all-cell replay and native-ownership audit, no IQ/scoring."""
import copy
from collections import Counter
from pathlib import Path
import selection
import study

HERE=Path(__file__).resolve().parent


def without_request_ids(value):
    result=copy.deepcopy(value);result.pop('prediction_id',None)
    for mode in result.get('modes',[]):mode.pop('hypothesis_id',None)
    return result


def main():
    study.bound();port=study.ports();panel=study.read(HERE/'panel.json');blocks=study.read(HERE/'blocks.json')['blocks']
    original=study.read(HERE/'predictions.json');packets=study.read(HERE/'prediction_packets.json')
    by_id={r['header']['prediction_id']:r for r in original['rows']};native={r['header']['prediction_id']:r for r in packets['rows']}
    donors=study.read(HERE/'donor_authority.json')['rows']
    old=study.read(study.R01/'prediction_packets.json')
    prior={(r['header']['case'],r['header']['visit_index'],r['header']['receiver_id']):r for r in old['rows']}
    assert len(blocks)==4 and len(panel['slots'])==263 and len(by_id)==len(native)==526
    assert all(not b['capped']for b in blocks)
    assert len(selection.deduplicate(blocks))==263
    assert all(s['status']=='nominated'for s in panel['slots'])
    assert all(d['status']=='metadata_verified'for d in donors)
    overlap=0
    for slot in panel['slots']:
        authority=slot['raw_authority'];a=authority['index']['acquisition']
        assert authority['payload_read']is False and authority['IQ_hash_newly_verified']is False
        assert a['sample_start']==slot['probe']['window_start_counter']
        assert a['sample_end']-a['sample_start']==200000
        assert set(authority['receiver_ids'])=={0,1}
        assert len(slot['cells'])==2
        for cell in slot['cells']:
            h=cell['header'];row=by_id[h['prediction_id']];packet=native[h['prediction_id']]
            assert row['status']=='complete'
            assert row['forecast']==port['predictor'].predict(h,cell['history'])
            assert row['forecast']==port['predictor'].predict(dict(h,target_candidates=[dict(CFO_hz=1e99)]),cell['history'])
            assert packet['donor_metadata_status']=='verified'
            assert packet['target_support']['generation']==a['generation']==packet['header']['generation']
            assert packet['header']['stream_generation']==h['generation']
            for mode in packet['forecast']['modes']:
                for donor in mode['donors']:
                    assert donor['support']['generation']==a['generation']
                    assert donor['support']['stop_counter']<=h['start_counter']
                    assert donor['source_id']==h['source_id']
            key=(h['case'],h['visit_index'],h['receiver_id'])
            if key in prior:
                assert without_request_ids(packet['forecast'])==without_request_ids(prior[key]['forecast'])
                assert packet['target_support']==prior[key]['target_support']
                overlap+=1
    assert overlap==8
    study.write(HERE/'verification.json',dict(all_passed=True,selector_tests=3,blocks=4,paired_windows=263,
        receiver_cells=526,fresh_exact_R01_forecasts=526,fresh_target_response_redactions=526,
        native_target_authority_windows=263,selected_native_donor_windows=len(donors),
        original_sparse_overlap_cells_exact_numeric_and_ownership_parity=overlap,
        raw_IQ_reads=0,scoring_calls=0,new_per_window_paired_detector_parity=False,
        protocol_sha256=study.sha(HERE/'protocol.json'),packets_sha256=study.sha(HERE/'prediction_packets.json')))
    print('verification passed',len(donors),'donor windows',overlap,'overlap cells')


if __name__=='__main__':main()
