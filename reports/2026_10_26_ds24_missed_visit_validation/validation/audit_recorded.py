"""Independent development-only full-window replay audit and new-owner manifest."""
import collections
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
R01=Path('/srv/bulk/leo/research/ds24-missed-visit-r01')
TIMING=ROOT/'timing'
sys.path.insert(0,str(R01/'validation'))
from baseline_scope import metadata_inventory

METHODS=('linear','quadratic_or_fallback','legacy_adapter_linear')
BIN=10000000/(44*512)


def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as stream:return json.load(stream)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    began=time.monotonic();control=read(HERE/'control_audit.json')
    assert control['primary_practical_RF_screen_passed']
    protocol=read(TIMING/'protocol.json')
    for path,digest in protocol['files'].items():assert sha(path)==digest,path
    split=read(R01/'split.json');panel=read(R01/'prediction/panel.json')
    slots={s['request_id']:s for s in panel['slots']}
    forecasts={r['prediction_id']:r for r in read(ROOT/'prediction/predictions.json')['rows']}
    totals=collections.Counter();by_channel=collections.defaultdict(collections.Counter);by_status=collections.defaultdict(collections.Counter)
    cases=[];candidates=[];seen=set();sources={};identity_checks=0;score_seconds=0.;reader_seconds=0.
    for case in split['development']:
        raw_path=TIMING/'outcomes'/(case+'.json.gz');document=read(raw_path);sources[str(raw_path)]=sha(raw_path)
        assert document['protocol_sha256']==sha(TIMING/'protocol.json')
        prior={r['request_id']:r for r in read(R01/'timing/outcomes'/(case+'.json.gz'))['rows']}
        _,inventory,original=metadata_inventory(case)
        native={(r['native_receiver_id'],r['start_counter']):r for r in inventory};original_ids={o['observation_id'] for o in original}
        local=collections.Counter()
        for window in document['rows']:
            totals['windows_'+window['status']]+=1;local['windows_'+window['status']]+=1
            if window['status']!='complete':continue
            slot=slots[window['request_id']];receipt=window['native_read_receipt'];raw=slot['raw_authority']
            assert receipt['full_reader_exhausted'] and receipt['repeated_blind_acquisition_calls']==0
            assert receipt['round1_paired_candidate_parity_reused']
            assert receipt['source_IQ_sha256']==raw['index']['iq_sha256']==prior[window['request_id']]['public_source_parity']['IQ_sha256']
            assert all(p['all_passed'] for p in prior[window['request_id']]['public_source_parity']['parity'].values())
            reader_seconds+=receipt['native_read_verify_seconds'];identity_checks+=1
            for cell in window['cells']:
                prediction=cell['prediction'];assert prediction==forecasts[cell['prediction_id']]
                h=prediction['header'];result=cell['result'];n=native[h['receiver_id'],h['start_counter']]
                assert n['observation_id'] not in seen;seen.add(n['observation_id'])
                assert h['case']==case and h['case'] in split['development']
                assert n['actual_rf_hz']==h['actual_rf_hz']==raw['target']['rf_center_hz']
                assert n['edge']==h['edge'] and n['sample_rate_hz']==h['sample_rate_hz']
                assert result['owner_id']==f"{n['recording_id']}/rx{n['native_receiver_id']}/{n['start_counter']}:{n['stop_counter']}"
                assert result['target_support']==prediction['target_support']
                assert result['primary_operational_method']=='quadratic_or_fallback' and not result['target_timing_or_mode_search']
                totals['cells']+=1;local['cells']+=1;score_seconds+=cell['scoring_seconds']
                ch=str(n['channel']);by_channel[ch]['cells']+=1;by_status[prediction['status']]['cells']+=1
                if prediction['status']=='no_donor':assert result['methods']=={};continue
                for method in METHODS:
                    item=result['methods'][method];point=item['point'];score=item['score']
                    assert point==prediction['methods'][method]
                    if score['status']!='complete':continue
                    innovation=score['tracking_cfo_hz']-point['cfo_hz']
                    assert abs(innovation/BIN-round(innovation/BIN))<1e-8
                    pilot=score['margin']>=.025;compatible=abs(innovation)<=point['cfo_half_width_hz']
                    assert item['admitted']==(pilot and compatible)
                    for key,val in [('pilot',pilot),('admitted',pilot and compatible),('new_native',pilot and compatible and n['observation_id'] not in original_ids),
                        ('zero_bin_admitted',pilot and compatible and abs(innovation)<1e-9)]:
                        totals[f'{method}_{key}']+=val;local[f'{method}_{key}']+=val;by_channel[ch][f'{method}_{key}']+=val
                        by_status[prediction['status']][f'{method}_{key}']+=val
                    if method=='quadratic_or_fallback' and pilot and compatible and n['observation_id'] not in original_ids:
                        candidates.append(dict(case=case,prediction_id=cell['prediction_id'],target_observation_id=n['observation_id'],
                            native=n,measured_cfo_hz=score['tracking_cfo_hz'],earlier_prediction_CFO_hz=point['cfo_hz'],
                            frequency_innovation_hz=innovation,frequency_bin_spacing_hz=BIN,confirmation_margin=score['margin'],
                            primary_hypothesis_id=prediction['primary_hypothesis_id'],donors=prediction['donors'],
                            source_IQ_sha256=receipt['source_IQ_sha256'],paired_detector_parity_reused=True,
                            repeated_blind_acquisition_calls=0,independent_precision_qualified=False,
                            status='exploratory_new_native_pending_graph_and_causal_association'))
                assert result['operational_admitted']==result['methods']['quadratic_or_fallback']['admitted']
                if prediction['status']=='linear_fallback':
                    assert result['methods']['linear']['score']==result['methods']['quadratic_or_fallback']['score']
        cases.append(dict(case=case,counts=dict(local),seconds=document['seconds']))
    assert len(seen)==576 and identity_checks==288
    out=dict(all_passed=True,counts=dict(totals),by_case=cases,by_channel={k:dict(v) for k,v in by_channel.items()},
        by_prediction_status={k:dict(v) for k,v in by_status.items()},native_window_identity_checks=identity_checks,
        unique_native_owner_checks=len(seen),reader_seconds=reader_seconds,scoring_seconds=score_seconds,
        original_rows_or_margins_changed=False,held_validation_targets_opened=False,geography_used=False,
        new_graph_or_position_runs=0,source_hashes=sources,protocol_sha256=sha(TIMING/'protocol.json'),
        seconds=time.monotonic()-began)
    with (HERE/'recorded_audit.json').open('x') as stream:json.dump(out,stream,indent=2,allow_nan=False);stream.write('\n')
    with (HERE/'candidate_manifest.json').open('x') as stream:json.dump(dict(candidates=candidates,
        new_native_owners=len(candidates),corrections=0,operational_method='quadratic_or_fallback',
        no_target_selected_union=True,graph_review_pending=True,position_authorized=False),stream,indent=2);stream.write('\n')
    print(json.dumps(dict(counts=dict(totals),by_status=out['by_prediction_status'],reader_seconds=reader_seconds,
        scoring_seconds=score_seconds,new_native=len(candidates)),indent=2))


if __name__=='__main__':main()
