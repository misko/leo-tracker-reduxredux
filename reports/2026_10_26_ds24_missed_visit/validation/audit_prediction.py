"""Independent development forecast/provenance audit, no IQ or held outcomes."""

import collections
import importlib.util
import json
import math
from pathlib import Path
import time

from baseline_scope import metadata_inventory,sha

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
PRED=ROOT/'prediction'


def read(path):return json.loads(Path(path).read_text())


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


def main():
    began=time.monotonic();split=read(ROOT/'split.json');protocol=read(PRED/'protocol.json')
    for path,digest in protocol['files'].items():assert sha(path)==digest,path
    panel=read(PRED/'panel.json');forecasts=read(PRED/'predictions.json')
    assert forecasts['panel_sha256']==sha(PRED/'panel.json')
    assert forecasts['protocol_sha256']==sha(PRED/'protocol.json')
    assert set(panel['development'])==set(split['development'])
    assert not forecasts['validation_target_outcomes_opened']
    predictor=module('independent_sparse_predictor',PRED/'predictor.py')
    predictions={r['header']['prediction_id']:r for r in forecasts['rows']}
    authorities=read(PRED/'donor_authority.json')
    assert authorities['predictions_sha256']==sha(PRED/'predictions.json')
    donor_raw={(r['case'],r['visit_index']):r['raw_authority'] for r in authorities['rows'] if r['status']=='metadata_verified'}
    assert len(donor_raw)==authorities['requested_donor_windows']
    inventory={};native={};original={}
    for case in split['development']:
        _,rows,obs=metadata_inventory(case)
        inventory[case]={(r['native_receiver_id'],r['start_counter']):r for r in rows}
        native[case]={r['observation_id']:r for r in rows}
        original[case]={r['observation_id']:r for r in obs}
    counters=collections.Counter();by_channel=collections.defaultdict(collections.Counter)
    native_bindings={};target_owners=set();donor_owners=collections.Counter();index_files={}
    for slot in panel['slots']:
        assert slot['case'] in split['development'] and slot['status']=='nominated'
        raw=slot['raw_authority'];a=raw['index']['acquisition']
        index_files[raw['index_path']]=raw['index_sha256'].removeprefix('sha256:')
        assert slot['probe_metadata']['actual_rf_hz']==raw['target']['rf_center_hz']
        assert a['actual_if_center_hz']+raw['target']['lnb_lo_hz']==raw['target']['rf_center_hz']
        for cell in slot['cells']:
            h=cell['header'];saved=predictions[h['prediction_id']]
            assert saved['status']=='complete'
            calculated=predictor.predict(h,cell['history'])
            assert calculated==saved['forecast']
            assert predictor.predict(dict(h,target_winner={'CFO_hz':1e99}),cell['history'])==calculated
            forecast=saved['forecast'];n=inventory[h['case']][h['receiver_id'],h['start_counter']]
            assert n['stop_counter']==h['stop_counter']==a['sample_end']
            assert h['start_counter']==a['sample_start']
            assert all(n[k]==h[v] for k,v in [('actual_rf_hz','actual_rf_hz'),('stream_generation','generation'),
                ('channel','channel'),('edge','edge'),('sample_rate_hz','sample_rate_hz')])
            oid=n['observation_id'];assert oid not in target_owners;target_owners.add(oid)
            native_bindings[oid]=dict(native=n,native_generation=a['generation'],device_session=a['device_session'],
                raw_index_IQ_sha256=raw['index']['iq_sha256'],raw_index_sha256=raw['index_sha256'],role='target')
            lane=f"CH{h['channel']}-RX{h['receiver_id']}"
            counts=dict(cells=1,forecast_available=bool(forecast['modes']),
                existing_winner=oid in original[h['case']],modes=len(forecast['modes']),
                any_missed_visit=any(m['missed_visits_after_latest'] or m['missed_visits_between_donors'] for m in forecast['modes']),
                any_multi_donor=any(m['donor_count']>1 for m in forecast['modes']))
            counters.update(counts);by_channel[lane].update(counts)
            for mode in forecast['modes']:
                assert len(mode['donors'])==mode['donor_count']
                assert mode['full']['reference_counter']==(h['start_counter']+h['stop_counter'])/2
                for half in mode['halves']:
                    assert half==predictor.propagate(mode['model'],h['sample_rate_hz'],half['start_counter'],half['stop_counter'])
                for donor in mode['donors']:
                    dn=inventory[h['case']][h['receiver_id'],donor['start_counter']]
                    assert dn['stop_counter']==donor['stop_counter']<=h['start_counter']
                    assert all(dn[k]==n[k] for k in ('recording_id','stream_generation','raw_authority_digest',
                        'native_receiver_id','receiver','channel','edge','actual_rf_hz','sample_rate_hz'))
                    da=donor_raw[h['case'],donor['visit_index']];acq=da['index']['acquisition']
                    assert acq['sample_start']==dn['start_counter'] and acq['sample_end']==dn['stop_counter']
                    assert h['receiver_id'] in da['receiver_ids']
                    assert type(acq['generation']) is int
                    assert donor['generation']==h['generation']==dn['stream_generation']
                    # Preserve the stream label and add each donor's actual native generation.
                    did=dn['observation_id'];donor_owners[did]+=1
                    native_bindings.setdefault(did,dict(native=dn,native_generation=acq['generation'],
                        device_session=acq['device_session'],raw_index_IQ_sha256=da['index']['iq_sha256'],
                        raw_index_sha256=da['index_sha256'],role='donor'))
                    index_files[da['index_path']]=da['index_sha256'].removeprefix('sha256:')
    for path,digest in index_files.items():assert sha(path)==digest,path
    assert len(panel['slots'])==288 and len(target_owners)==576
    survey=read(PRED/'summary.json');assert survey['predictions_sha256']==sha(PRED/'predictions.json')
    assert counters['forecast_available']==survey['overall']['forecast_available']
    result=dict(schema='missed-visit-independent-prediction-audit-v1',all_passed=True,
        independent_forecast_replays=576,target_response_redaction_checks=576,
        all_target_native_IDs_unique=True,counts=dict(counters),by_channel_receiver={k:dict(v) for k,v in by_channel.items()},
        donor_windows=len(donor_raw),native_index_files_verified=len(index_files),
        unique_donor_owners=len(donor_owners),donor_owner_uses=sum(donor_owners.values()),
        target_owners_also_used_as_donors=len(target_owners&set(donor_owners)),
        donor_generation_interpretation='Frozen donor generation is the stream label. Each actual integer native generation is supplied separately from that donor native index.',
        IQ_hashes_newly_verified=False,metadata_and_archive_only=True,
        new_RF_outcomes_read=False,held_validation_target_outcomes_read=False,geographic_errors_read=False,
        native_bindings=list(native_bindings.values()),
        observed_archived_target_compatibility_is_not_ground_truth=True,
        source_hashes={str(PRED/name):sha(PRED/name) for name in ('PROTOCOL.md','protocol.json','predictor.py','study.py',
            'panel.json','predictions.json','donor_authority.json','summary.json')},seconds=time.monotonic()-began)
    with (HERE/'prediction_audit.json').open('x') as stream:
        json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('native_bindings','by_channel_receiver','source_hashes')},indent=2))


if __name__=='__main__':main()
