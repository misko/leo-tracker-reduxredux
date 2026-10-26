"""Independent offline audit of interval interpretation and natural packet mapping."""

import bisect
import collections
import json
from pathlib import Path

from adapter import file_sha

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent


def read(path):
    return json.loads(Path(path).read_text())


def intervals(grid,masses,probabilities=(.025,.5,.975)):
    total=sum(masses)
    weights=[w/total for w in masses]
    cumulative=[];running=0.
    for w in weights:
        running+=w;cumulative.append(running)
    cumulative[-1]=1.
    discrete=[];density=[]
    for q in probabilities:
        index=bisect.bisect_left(cumulative,q)
        before=0. if index==0 else cumulative[index-1]
        left=grid[0] if index==0 else (grid[index-1]+grid[index])/2
        right=grid[-1] if index==len(grid)-1 else (grid[index]+grid[index+1])/2
        discrete.append(grid[index])
        density.append(left+(right-left)*(q-before)/weights[index])
    return dict(discrete_mass=discrete,bin_density=density)


def main():
    frequency=ROOT/'frequency'
    ip=read(frequency/'interval_audit_v2_protocol.json')
    for path,sha in ip['files'].items():
        assert file_sha(path)==sha,path
    published=read(frequency/'interval_audit_v2.json')
    assert published['RF_calls']==published['likelihood_calls']==0
    audit_rows={(r['source'],r['index']):r for r in published['rows']}
    totals={};strata=collections.defaultdict(lambda:collections.Counter())
    for kind in ('synthetic','recorded'):
        source=read(frequency/(kind+'.json'))
        items=source['rows'] if kind=='synthetic' else [c for r in source['rows'] for c in r['cells']]
        counts=collections.Counter();n=0
        for i,item in enumerate(items):
            primary=item['estimate']['primary']
            if primary is None:
                continue
            n+=1;p=primary['proposed']
            result=intervals(p['grid_offsets_hz'],p['conditional_grid_weights'])
            reported=audit_rows[kind,i]
            truth=item['truth_cfo_hz'] if kind=='synthetic' else 213456.75
            offset=truth-primary['predicted_cfo_hz']
            original=p['conditional_95_interval_offsets_hz']
            coverage={'frozen_v1':original[0]<=offset<=original[1]}
            for method,quantiles in result.items():
                assert all(abs(a-b)<1e-8 for a,b in zip(quantiles,reported['quantiles_offsets_hz'][method]))
                coverage[method]=quantiles[0]<=offset<=quantiles[-1]
            assert coverage==reported['coverage']
            counts.update({key:int(value) for key,value in coverage.items()})
            if kind=='synthetic':
                key=f"db{item['db']}/{item['forecast']}/donor_error{item['donor_error_hz']:g}"
                strata[key]['comparisons']+=1
                strata[key].update({k:int(v) for k,v in coverage.items()})
        totals[kind]=dict(n=n,covered=dict(counts))
        assert totals[kind]==published['totals'][kind]
    # Concentrated mass: center-CDF interpolation can exclude its own mode.
    toy=intervals([-25.,0.,25.],[0.,1.,0.])
    assert toy['discrete_mass']==[0.,0.,0.]
    assert toy['bin_density']==[-11.875,0.,11.875]

    natural_protocol=read(frequency/'natural_protocol.json')
    for path,sha in natural_protocol['files'].items():
        assert file_sha(path)==sha,path
    natural=read(frequency/'natural_packets.json')
    qualification=read(frequency/'natural_qualification.json')
    assert natural['natural_protocol_sha256']==file_sha(frequency/'natural_protocol.json')
    assert qualification['packets_sha256']==file_sha(frequency/'natural_packets.json')
    for path,sha in natural['native_index_files'].items():
        assert file_sha(path)==sha,path
    base={f'DS24-{i:04d}':read(HERE/f'DS24-{i:04d}_baseline.json') for i in range(10,14)}
    inventory={case:{(r['support']['native_receiver_id'],r['support']['start_counter']):r
        for r in b['native_inventory']} for case,b in base.items()}
    panel=read(ROOT/'revisit/panel.json')
    slots={s['request_id']:s for s in panel['slots']}
    predictions=read(ROOT/'revisit/predictions.json')
    pred={(r['request_id'],r['receiver_id']):r for r in predictions['rows']}
    authorities={(d['case'],d['receiver_id'],d['counter']):d['authority'] for d in natural['donor_raw_authorities']}
    packets=natural['packets'];assert len(packets)==192
    absent=0;eligible=0;donor_owner_ids=set();half_cfo_advance=[]
    for packet in packets:
        request=packet['prediction_id'].split('/')[0]
        slot=slots[request];prediction=pred[request,packet['receiver_id']]
        target=packet['target_support'];acq=slot['raw_authority']['index']['acquisition']
        offset=target['start_counter']-prediction['target_start_counter']
        assert offset in (0,100000)
        assert target['stop_counter']-target['start_counter']==100000
        owner=inventory[packet['case']][packet['receiver_id'],prediction['target_start_counter']]
        assert owner['support']['start_counter']<=target['start_counter']<target['stop_counter']<=owner['support']['end_counter']
        assert packet['actual_rf_hz']==owner['support']['actual_rf_hz']
        assert packet['edge']==owner['support']['edge']
        assert packet['channel']==owner['support']['channel']
        assert packet['sample_rate_hz']==owner['support']['sample_rate_hz']
        assert packet['actual_if_center_hz']+slot['raw_authority']['target']['lnb_lo_hz']==packet['actual_rf_hz']
        assert target['generation']==acq['generation'] and target['device_session']==acq['device_session']
        assert packet['independent_doppler_observations']==0
        if not packet['hypotheses']:
            absent+=1
            continue
        eligible+=1
        for hypothesis in packet['hypotheses']:
            mode=prediction['forecast']['modes'][hypothesis['source_mode_index']]
            assert mode['status']=='complete'
            assert hypothesis['predicted_cfo_hz']==mode['linear']['CFO_hz']
            assert hypothesis['prediction_sigma_hz']==mode['CFO_fit']['heuristic_half_width_3scale']/3
            assert abs(hypothesis['elapsed_s']-(mode['horizon_s']+offset/packet['sample_rate_hz']))<1e-12
            if offset:
                half_cfo_advance.append(mode['CFO_fit']['rate_per_s']*offset/packet['sample_rate_hz'])
            for donor,counter,rank in zip(hypothesis['donors'],mode['donor_counters'],mode['donor_ranks'],strict=True):
                di=inventory[packet['case']][packet['receiver_id'],counter]
                donor_owner_ids.add(di['observation_id'])
                ds=donor['support'];authority=authorities[packet['case'],packet['receiver_id'],counter]
                da=authority['index']['acquisition']
                assert ds['start_counter']==counter and ds['stop_counter']==di['support']['end_counter']
                assert ds['stop_counter']<=owner['support']['start_counter']
                assert all(di['support'][k]==owner['support'][k] for k in
                    ('channel','edge','actual_rf_hz','native_receiver_id','recording_id','stream_generation','raw_authority_digest'))
                assert ds['generation']==da['generation'] and ds['device_session']==da['device_session']
                assert ds['source_IQ_sha256']==authority['index']['iq_sha256']
    assert absent==182 and eligible==10
    assert qualification['natural_frequency_estimator_calls']==qualification['new_IQ_reads']==0
    result=dict(all_passed=True,interval_rows_independently_recomputed=len(audit_rows),
        intervals=totals,strata=dict(strata),
        inference_weights_MAP_CFO_and_RF_gates_changed=False,
        interval_interpretation_qualifies_RF_uncertainty=False,
        coverage_comparisons_not_independent=288,independent_synthetic_targets=48,
        natural_packets_checked=len(packets),no_donor_half_packets=absent,eligible_half_packets=eligible,
        native_donor_owners=len(donor_owner_ids),natural_RF_calls=0,
        actual_RF_receiver_band_native_sample_mapping_verified=True,
        RF_mapping_authority='preserved capture hypothesis, not independently established RF identity',
        half_packet_CFO_reference='both halves retain original target-start forecast; estimator never called',
        omitted_second_half_CFO_rate_advance_hz=half_cfo_advance,
        future_requirement='if scoring resumes, explicitly declare frequency reference time and propagate donor rate consistently; freeze a new experiment',
        source_hashes={str(frequency/name):file_sha(frequency/name) for name in
            ('interval_audit_v2.py','interval_audit_v2_protocol.json','interval_audit_v2.json',
             'natural_adapter.py','natural_protocol.json','natural_packets.json','natural_qualification.json')})
    with (HERE/'supplemental_audit.json').open('x') as stream:
        json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('strata','source_hashes')},indent=2))


if __name__=='__main__':
    main()
