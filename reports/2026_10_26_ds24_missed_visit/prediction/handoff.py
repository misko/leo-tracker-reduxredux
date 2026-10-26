"""Metadata-only enrichment; preserve every frozen numerical forecast."""
import copy
import hashlib
import json
from pathlib import Path
import study

HERE=Path(__file__).resolve().parent


def native_support(authority):
    a=authority['index']['acquisition']
    return dict(start_counter=a['sample_start'],stop_counter=a['sample_end'],generation=a['generation'],
        IQ_sha256=authority['index']['iq_sha256'],source_input_sha256=authority['source_input']['sha256'],
        index_sha256=authority['index_sha256'],global_visit=authority['global_visit'])


def enrich(row,slot,donor_lookup):
    result=copy.deepcopy(row)
    support=native_support(slot['raw_authority'])
    h=result['header'];h['stream_generation']=h['generation'];h['generation']=support['generation']
    result['target_support']=support
    result['donor_metadata_status']='verified'
    for mode in result.get('forecast',{}).get('modes',[]):
        enriched=[]
        for donor in mode['donors']:
            authority=donor_lookup.get((h['case'],donor['visit_index']))
            if authority is None:
                result['donor_metadata_status']='unavailable'
                donor['support']=None;donor['metadata_status']='unavailable';enriched.append(donor);continue
            ds=native_support(authority)
            if ds['generation']!=support['generation'] or ds['start_counter']!=donor['start_counter'] or ds['stop_counter']!=donor['stop_counter']:
                result['donor_metadata_status']='ownership_mismatch'
            donor['stream_generation']=donor['generation'];donor['generation']=ds['generation']
            donor['support']=ds;donor['authority_key']=f"{h['case']}/visit{donor['visit_index']}"
            enriched.append(donor)
        mode['donors']=enriched;mode['model']['donors']=copy.deepcopy(enriched)
        for forecast in [mode['full']]+mode['halves']:
            forecast['generation']=support['generation'];forecast['source_IQ_sha256']=support['IQ_sha256']
    return result


def main():
    study.bound()
    names=['handoff.py','test_handoff.py','protocol.json','panel.json','predictions.json','donor_authority.json']
    study.write(HERE/'handoff_protocol.json',dict(schema='sparse-prediction-native-ownership/v1',
        files={str(HERE/name):study.sha(HERE/name)for name in names},
        scope='metadata ownership naming only; no forecast/CFO/epoch/rate/width/selection changes',
        target_outcome_inputs=False,raw_IQ_reads=0))
    panel=study.read(HERE/'panel.json');slots={s['request_id']:s for s in panel['slots']}
    donors=study.read(HERE/'donor_authority.json')
    lookup={(r['case'],r['visit_index']):r['raw_authority']for r in donors['rows']if r['status']=='metadata_verified'}
    rows=[enrich(row,slots[row['header']['request_id']],lookup)for row in study.read(HERE/'predictions.json')['rows']]
    study.write(HERE/'prediction_packets.json',dict(schema='sparse-native-prediction-packets/v1',
        handoff_protocol_sha256=study.sha(HERE/'handoff_protocol.json'),
        frozen_predictions_sha256=study.sha(HERE/'predictions.json'),rows=rows,
        outcome_inputs=False,raw_IQ_reads=0,numerical_forecasts_unchanged=True))
    print('native packets',len(rows),study.sha(HERE/'prediction_packets.json'))


if __name__=='__main__':main()
