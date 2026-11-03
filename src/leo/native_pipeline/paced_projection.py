"""Pure adapter from recorded detector candidate checkpoints to observations.

The checkpoint profile is fixed to two receivers, 120-ms dwells and one 20-ms
integer-epoch probe. Analysis identity is explicit and never borrowed from an
unrelated archived run merely to make candidate IDs compare equal.
"""
from .projection import WindowAuthority, project_integer_candidates
from leo.contracts.digests import canonical_digest


def analysis_identity(binary_sha256):
    """Stable detector configuration identity; runtime timing is provenance only."""
    if len(binary_sha256)!=64 or any(c not in '0123456789abcdef' for c in binary_sha256):
        raise ValueError('invalid detector binary digest')
    return canonical_digest({'algorithm':'recorded-integer-glrt-config-v1',
        'binary_sha256':binary_sha256,'rate_hz':2500000,'dwell_ms':120,
        'stride_ms':120,'probe_ms':20,'minimum_margin':.025})


def project_paced(capture, rows, capture_digest, analysis_digest):
    events=capture['receipt']['events'];geometry=capture['receipt']['plan']['geometry']
    if geometry['sample_rate_hz']!=2500000 or geometry['receiver_ids']!=[0,1]:
        raise ValueError('unsupported paced checkpoint geometry')
    if not rows or rows[-1].get('kind')!='summary':raise ValueError('missing terminal summary')
    arrivals=rows[:-1];summary=rows[-1]
    if (len(arrivals)!=len(events) or summary['arrivals']!=len(events)
        or summary['completed']!=len(events) or summary['failed'] or summary['rejected']):
        raise ValueError('incomplete paced detector checkpoint')
    timing=capture['timing'];projected=[]
    for visit,(event,row) in enumerate(zip(events,arrivals)):
        if row['sequence']!=visit or event['visit_index']!=visit or not row['accepted'] or row['status']!=0:
            raise ValueError('invalid paced visit')
        if event['valid_end_counter_exclusive']-event['valid_start_counter']!=300000:
            raise ValueError('unsupported dwell length')
        groups={0:[],1:[]}
        for candidate in row['candidates']:
            if len(candidate)!=10:raise ValueError('invalid candidate fields')
            rx,probe,rank,epoch,acquired,tracking,exact,control,margin,complete=candidate
            if type(rx) is not int or rx not in groups or probe!=0 or type(rank) is not int:
                raise ValueError('invalid candidate source')
            if rank!=len(groups[rx]) or rank>=8:raise ValueError('missing or duplicated candidate rank')
            groups[rx].append(dict(epoch=epoch,tracking_cfo_hz=tracking,exact_score=exact,
                                   control_score=control,margin=margin,glrt_complete=complete))
        for rx,candidates in groups.items():
            target=event['target']
            authority=WindowAuthority(capture_digest,analysis_digest,visit,rx,0,target['channel'],
                target['edge'],float(target['rf_center_hz']-event['actual_if_offset_hz']),
                2500000,50000,event['valid_start_counter'],timing['session_start_device_sample_counter'],
                timing['first_sample_estimate_utc_ns'])
            projected.extend(project_integer_candidates(authority,candidates))
    return projected
