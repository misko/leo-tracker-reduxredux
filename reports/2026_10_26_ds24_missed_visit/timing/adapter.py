"""Prediction mapping; does not read archived target responses."""
import copy


def adapt(row,raw_authority=None,donor_authorities=None):
    header=row['header'];rate=header['sample_rate_hz'];start=header['start_counter'];stop=header['stop_counter']
    midpoint=(stop-start)/(2*rate);modes=[];donor_authorities=donor_authorities or {}
    for mode in row.get('forecast',{}).get('modes',[]):
        full=mode['full'];donors=[]
        for donor in mode['donors']:
            d=copy.deepcopy(donor);authority=donor_authorities.get((header['case'],donor['visit_index']))
            support=dict(start_counter=donor['start_counter'],stop_counter=donor['stop_counter'],
                source_id=donor['source_id'],stream_generation=donor['generation'],
                native_generation=None,native_generation_verified=False)
            if 'support' in donor:
                support=copy.deepcopy(donor['support'])
                support.update(native_generation=support['generation'],native_generation_verified=True,
                    stream_generation=donor.get('stream_generation'),source_id=donor['source_id'])
            if authority is not None:
                acq=authority['index']['acquisition']
                if (acq['sample_start'],acq['sample_end'])!=(support['start_counter'],support['stop_counter']):
                    raise ValueError('donor public authority counters disagree')
                support.update(native_generation=acq['generation'],device_session=acq['device_session'],
                    native_generation_verified=True,source_IQ_sha256=authority['index']['iq_sha256'],
                    index_path=authority['index_path'],index_sha256=authority['index_sha256'])
            d['support']=support;donors.append(d)
        epoch=(full['epoch_samples']+full['timing_rate_samples_per_s']*midpoint)%(rate/750.)
        reference_offset=(full['reference_counter']-start)/rate
        modes.append(dict(mode_id=mode['hypothesis_id'],status=mode['status'],
            epoch_samples=epoch,timing_reference_offset_s=midpoint,
            timing_rate_samples_s=full['timing_rate_samples_per_s'],
            constant_epoch_approximation=True,
            maximum_within_window_timing_approximation_samples=abs(full['timing_rate_samples_per_s'])*midpoint,
            source_start_epoch_samples=full['epoch_samples'],
            cfo_hz=full['CFO_hz'],cfo_rate_hz_s=full['CFO_rate_hz_per_s'],
            reference_offset_s=reference_offset,cfo_reference_counter=full['reference_counter'],
            cfo_half_width_hz=full['CFO_half_width_hz'],timing_half_width_samples=full['timing_half_width_samples'],
            widths_calibrated=False,missed_visits_after_latest=mode['missed_visits_after_latest'],
            missed_visits_between_donors=mode['missed_visits_between_donors'],donors=donors))
    support=dict(start_counter=start,stop_counter=stop,source_id=header['source_id'],
        stream_generation=header['generation'],native_generation=None,
        tracking_sha256=header.get('tracking_sha256'),raw_recording_authority_digest=header.get('raw_recording_authority_digest'))
    if 'target_support' in row:
        support.update(copy.deepcopy(row['target_support']))
        support['native_generation']=row['target_support']['generation']
        support['stream_generation']=header.get('stream_generation')
    if raw_authority is not None:
        acq=raw_authority['index']['acquisition']
        if (acq['sample_start'],acq['sample_end'])!=(start,stop):raise ValueError('target authority counters disagree')
        support.update(native_generation=acq['generation'],device_session=acq['device_session'],
            source_IQ_sha256=raw_authority['index']['iq_sha256'],index_path=raw_authority['index_path'],
            index_sha256=raw_authority['index_sha256'])
    return dict(owner_id=f"{header['source_id']}/rx{header['receiver_id']}/{start}:{stop}",
        prediction_id=header['prediction_id'],header=copy.deepcopy(header),target_support=support,modes=modes,
        forecast_status=row.get('forecast',{}).get('status',row.get('status','missing')),
        target_responses_used=False,alternative_modes_share_native_owner=True)
