"""Earlier-only packet mapping; failed natural RF prerequisite stops scoring."""
import argparse
import copy
import time
from pathlib import Path
import study

HERE=Path(__file__).resolve().parent
REVISIT=HERE.parent/'revisit'


def map_packet(slot,prediction,authorities,offset=0):
    """No target_original or target response is accessed by this mapping."""
    a=slot['raw_authority']; acquisition=a['index']['acquisition']
    start=prediction['target_start_counter']+offset; rate=prediction['sample_rate_hz']
    hypotheses=[]
    for i,m in enumerate(prediction['forecast']['modes']):
        if m['status']!='complete':continue
        donors=[]
        for counter,rank,cfo in zip(m['donor_counters'],m['donor_ranks'],m['donor_CFO_hz']):
            authority=authorities[(slot['case'],counter,prediction['receiver_id'])]
            da=authority['index']['acquisition']
            donors.append(dict(observation_id=f"{slot['case']}/visit{authority['global_visit']}/rx{prediction['receiver_id']}/rank{rank}",
                support=dict(start_counter=da['sample_start'],stop_counter=da['sample_end'],
                    generation=da['generation'],device_session=da['device_session'],
                    source_input=authority['source_input'],source_IQ_sha256=authority['index']['iq_sha256']),
                cfo_hz=cfo,index_path=authority['index_path'],index_sha256=authority['index_sha256'],
                IQ_newly_verified=False,authority='public native index and persisted earlier measurement'))
        hypotheses.append(dict(hypothesis_id=f"mode{i}-rank{m['seed_rank']}",
            source_mode_index=i,epoch_samples=(m['linear']['epoch_samples']-offset)%(rate/750.),
            predicted_cfo_hz=m['linear']['CFO_hz'],
            prediction_sigma_hz=m['CFO_fit']['heuristic_half_width_3scale']/3,
            prediction_sigma_status='earlier-only heuristic width, not calibrated sigma',
            elapsed_s=m['horizon_s']+offset/rate,carry_cfo_hz=m['constant']['CFO_hz'],
            donors=donors))
    return dict(prediction_id=f"{slot['request_id']}/rx{prediction['receiver_id']}/half{offset//100000}",
        case=slot['case'],channel=slot['channel'],receiver_id=prediction['receiver_id'],
        edge=prediction['edge'],sample_rate_hz=rate,actual_rf_hz=a['target']['rf_center_hz'],
        actual_if_center_hz=acquisition['actual_if_center_hz'],
        target_support=dict(start_counter=start,stop_counter=start+100000,
            generation=acquisition['generation'],device_session=acquisition['device_session'],
            source_input=a['source_input'],source_IQ_sha256=a['index']['iq_sha256'],
            original_visit_index=prediction['target_visit_index'],index_path=a['index_path'],
            index_sha256=a['index_sha256']),hypotheses=hypotheses,
        absent_or_ambiguous_state=prediction['forecast']['status'],
        forecast_uses_only_earlier=True,independent_doppler_observations=0)


def prepare():
    # Bind the fixed interface before opening the natural result artifact.
    paths=[HERE/'natural_adapter.py',HERE/'test_natural_adapter.py',HERE/'protocol.json']
    paths += [REVISIT/name for name in ['protocol.json','panel.json','predictions.json','study.py']]
    study.write(HERE/'natural_protocol.json',dict(schema='frequency-natural-adapter/v1',
        frozen_utc_ns=time.time_ns(),files={str(p):study.sha(p) for p in paths},
        forecast_variant='linear',primary='first complete original seed rank',
        sigma_mapping='CFO_fit.heuristic_half_width_3scale / 3; remains heuristic',
        no_target_response_used_in_mapping=True,
        stop_on_no_later_both_half_support=True,no_new_IQ_if_prerequisite_fails=True))


def run():
    began=time.monotonic();study.bounded()
    protocol=study.read(HERE/'natural_protocol.json')
    for path,digest in protocol['files'].items():
        if study.sha(path)!=digest:raise ValueError('natural mapping source changed')
    panel=study.read(REVISIT/'panel.json');predictions=study.read(REVISIT/'predictions.json')
    by_key={(r['request_id'],r['receiver_id']):r for r in predictions['rows']}
    metadata=study.module('natural_public_metadata',study.old.old.PRIOR/'influence/raw_metadata.py')
    authorities={};packets=[];source_files={}
    for slot in panel['slots']:
        for cell in slot['cells']:
            header=cell['header'];prediction=by_key[(slot['request_id'],header['receiver_id'])]
            needed={counter for mode in prediction['forecast']['modes'] if mode['status']=='complete'
                    for counter in mode['donor_counters']}
            for probe in cell['earlier']:
                counter=probe['valid_start_counter'];key=(slot['case'],counter,header['receiver_id'])
                if counter not in needed or key in authorities:continue
                request=dict(source_input=slot['source_input'],probe=dict(probe,
                    window_start_counter=counter,duration_samples=200000))
                authority=metadata.one(request);authorities[key]=authority
                source_files[authority['index_path']]=study.sha(authority['index_path'])
            for offset in [0,100000]:packets.append(map_packet(slot,prediction,authorities,offset))
    study.write(HERE/'natural_packets.json',dict(schema='frequency-natural-packets/v1',packets=packets,
        natural_protocol_sha256=study.sha(HERE/'natural_protocol.json'),
        native_index_files=source_files,IQ_reads=0,source_metadata_only=True,
        donor_raw_authorities=[dict(case=k[0],counter=k[1],receiver_id=k[2],authority=v)
                               for k,v in authorities.items()]))
    # Results are evaluated only after packet construction; none enters mapping.
    results=study.read(REVISIT/'results.json');outcomes=[]
    for slot in results['rows']:
        for cell in slot['cells']:
            modes=[dict(mode_index=o['mode_index'],seed_rank=o['seed_rank'],
                linear_both_half_support=o['variants']['linear']['both_pass'],
                constant_both_half_support=o['variants']['constant']['both_pass'],
                linear_gate_margins=[h['margin'] for h in o['variants']['linear']['halves']])
                for o in cell['outcomes']]
            outcomes.append(dict(request_id=slot['request_id'],receiver_id=cell['receiver_id'],
                forecast_status=cell['forecast_status'],modes=modes,
                status='no_donor' if not modes else 'failed_later_pilot_support',
                frequency_profile_evaluated=False))
    supported=sum(m['linear_both_half_support'] for x in outcomes for m in x['modes'])
    if supported:
        raise RuntimeError('unexpected supported natural mode; requires separate reviewed RF run, no automatic rescue')
    study.write(HERE/'natural_qualification.json',dict(schema='frequency-natural-prerequisite/v1',
        outcomes=outcomes,receiver_cells=len(outcomes),eligible_cells=sum(bool(x['modes']) for x in outcomes),
        eligible_modes=sum(len(x['modes']) for x in outcomes),supported_modes=supported,
        status='RF_NOT_QUALIFIED',reason='Every frozen eligible history fails later pilot support; stop before frequency/position propagation',
        new_IQ_reads=0,natural_frequency_estimator_calls=0,raw_later_profiles_available=False,
        predictions_sha256=study.sha(REVISIT/'predictions.json'),results_sha256=study.sha(REVISIT/'results.json'),
        packets_sha256=study.sha(HERE/'natural_packets.json'),seconds=time.monotonic()-began))
    print('natural prerequisite failed; zero new IQ reads and frequency calls',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run'])
    prepare() if parser.parse_args().action=='prepare' else run()
