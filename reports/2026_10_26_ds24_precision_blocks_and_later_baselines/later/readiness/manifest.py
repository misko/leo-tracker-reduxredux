"""Small frozen identity/time checks shared by metadata and preparation."""

def selected_four(document):
    rows=[r for r in document['rows']if r['proposed_fixed4_metadata_member']]
    if len(rows)!=4 or len({r['recording_id']for r in rows})!=4 or len({r['session_id']for r in rows})!=4:
        raise ValueError('exact four unique original identities required')
    if [r['name_time_proxy_utc_ns']for r in rows]!=sorted(r['name_time_proxy_utc_ns']for r in rows):
        raise ValueError('original chronological selection order changed')
    return rows


def clock_authority(document):
    a=document['clock_anchor'];clocks=document['delivery_clocks']
    if a is None or not clocks:raise ValueError('explicit original clock bracket required')
    before=int(a['before']['realtime_ns']);after=int(a['after']['realtime_ns'])
    if after<before or after-before>2_000_000_000:raise ValueError('invalid original UTC bracket')
    offsets=[int(c['realtime_ns'])-int(c['monotonic_ns'])for c in [a['before'],a['after'],*clocks]]
    if max(offsets)-min(offsets)>2_000_000_000:raise ValueError('original clock-step guard fails')
    if any(p['valid_start_counter']<a['sample_counter']for p in document['source']['probes']):
        raise ValueError('probe precedes original clock origin')
    return dict(anchor_utc_ns=(before+after)//2,causal_cutoff_utc_ns=before,
        first_sample_earliest_utc_ns=before,first_sample_latest_utc_ns=after,
        utc_half_width_s=(after-before)/2e9,device_origin_counter=a['sample_counter'],
        authority='existing fast frequency_evidence host bracket; midpoint anchor and before-bound causal cutoff',
        source_capture_start_utc_ns=document['source'].get('capture_start_utc_ns'),
        source_capture_end_utc_ns=document['source'].get('capture_end_utc_ns'))


def assert_identity(item,row):
    member=row['sample_member']
    if member['recording_id']!=item['recording_id']or member['session_id']!=item['session_id']:
        raise ValueError('fixed recording/session identity changed')
    expected=item['contract_metadata'][0]['declared_raw_authority_digest']
    if member['raw_authority_digest']!=expected:raise ValueError('frozen raw authority changed')

