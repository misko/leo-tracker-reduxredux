"""Independent v1/v2 label-only diff and exact earlier forecast/native audit."""
import importlib.util
import json
import hashlib
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
R01=HERE.parents[1]
PRED=R01/'expansion/prediction'


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_label_diff(old,new,path=''):
    if isinstance(old,dict) and isinstance(new,dict):
        assert set(old)==set(new),path
        return sum(check_label_diff(old[k],new[k],path+'/'+k) for k in old)
    if isinstance(old,list) and isinstance(new,list):
        assert len(old)==len(new),path
        return sum(check_label_diff(a,b,path+f'/{i}') for i,(a,b) in enumerate(zip(old,new)))
    if old==new and type(old)==type(new):return 0
    assert path.endswith('/stream_generation') and type(old) is int and isinstance(new,str),(path,old,new)
    return 1


def clean_forecast(value):
    value=json.loads(json.dumps(value));value.pop('prediction_id',None)
    for mode in value.get('modes',[]):mode.pop('hypothesis_id',None)
    return value


def main():
    began=time.monotonic();old=read(PRED/'prediction_packets.json');new=read(PRED/'prediction_packets_v2.json')
    assert sha(PRED/'prediction_packets_v2.json')=='3eb5bbf491eae2f1c2300961ef6f88d5406720f02db57f2c6b97a59fdd0a881e'
    protocol=read(PRED/'metadata_handoff_v2_protocol.json')
    for path,digest in protocol['files'].items():assert sha(path)==digest,path
    changed=check_label_diff(old['rows'],new['rows']);assert changed==4670
    panel=read(PRED/'panel.json');raw=read(PRED/'predictions.json')
    by_id={r['header']['prediction_id']:r for r in new['rows']};raw_by_id={r['header']['prediction_id']:r for r in raw['rows']}
    spec=importlib.util.spec_from_file_location('sealed_sparse_predictor_application',R01/'prediction/predictor.py')
    predictor=importlib.util.module_from_spec(spec);spec.loader.exec_module(predictor)
    previous=read(R01/'prediction/prediction_packets.json')['rows']
    previous={(r['header']['case'],r['header']['visit_index'],r['header']['receiver_id']):r for r in previous}
    authorities=read(PRED/'donor_authority.json')['rows']
    authority={(r['case'],r['visit_index']):r['raw_authority'] for r in authorities if r['status']=='metadata_verified'}
    assert len(authority)==72
    targets=set();donors=set();overlap=0;mode_count=0
    for slot in panel['slots']:
        a=slot['raw_authority'];acq=a['index']['acquisition']
        assert slot['case'] in ('DS24-0011','DS24-0097')
        for cell in slot['cells']:
            h=cell['header'];r=by_id[h['prediction_id']]
            assert raw_by_id[h['prediction_id']]['forecast']==predictor.predict(h,cell['history'])
            assert predictor.predict(dict(h,target_candidates=[{'secret':1e99}]),cell['history'])==raw_by_id[h['prediction_id']]['forecast']
            assert r['header']['stream_generation']==h['generation']
            assert r['header']['generation']==acq['generation']
            assert r['target_support']['start_counter']==acq['sample_start']==h['start_counter']
            assert r['target_support']['stop_counter']==acq['sample_end']==h['stop_counter']
            assert r['header']['actual_rf_hz']==a['target']['rf_center_hz']
            target=(h['case'],h['receiver_id'],h['start_counter']);assert target not in targets;targets.add(target)
            assert r['donor_metadata_status']=='verified'
            for mode in r['forecast']['modes']:
                mode_count+=1
                for donor in mode['donors']:
                    da=authority[h['case'],donor['visit_index']];d=da['index']['acquisition']
                    assert donor['stream_generation']==h['generation']
                    assert donor['support']['generation']==d['generation']
                    assert donor['support']['start_counter']==d['sample_start']
                    assert donor['support']['stop_counter']==d['sample_end']<=h['start_counter']
                    assert donor['support']['IQ_sha256']==da['index']['iq_sha256']
                    donors.add((h['case'],h['receiver_id'],d['sample_start']))
            key=(h['case'],h['visit_index'],h['receiver_id'])
            if key in previous:
                assert clean_forecast(r['forecast'])==clean_forecast(previous[key]['forecast'])
                assert r['target_support']==previous[key]['target_support'];overlap+=1
    assert len(targets)==526 and len(panel['slots'])==263 and overlap==8
    out=dict(all_passed=True,only_stream_generation_labels_changed=True,changed_fields=changed,
        numerical_forecasts_and_native_support_unchanged=True,exact_forecast_replays=526,response_redaction_checks=526,
        paired_windows=263,receiver_cells=526,unique_target_owners=526,unique_donor_owners=len(donors),
        target_owners_also_in_donor_histories=len(targets&donors),original_sparse_overlap_cells=8,modes=mode_count,
        corrected_packets_sha256=sha(PRED/'prediction_packets_v2.json'),
        per_window_fresh_detector_parity_claimed=False,raw_IQ_reads=0,position_or_GPS_used=False,
        scope='Only verified corrected packets may enter the separately approved raw stage; v1 remains revoked.',seconds=time.monotonic()-began)
    with (HERE/'metadata_audit_v2.json').open('x') as stream:json.dump(out,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()
