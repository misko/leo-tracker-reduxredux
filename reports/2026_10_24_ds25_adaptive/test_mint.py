from mint import select


def test_adaptive_subset_preserves_parent_mapping_without_readiness_gate():
    def row(label, mode, time):
        return dict(dataset_label=label, recording_format=mode, captured_utc_ns=time,
                    recording_id=label, sample_rate_hz=10000000, tracking_inputs=[])
    p=dict(members=[row('DS24-0022','starlink_adaptive_hop_iq',3),
                    row('DS24-0001','short_window_iq_recording',2),
                    row('DS24-0020','starlink_adaptive_hop_iq',1)])
    result=select(p)
    assert [(r['dataset_label'],r['parent_dataset_label']) for r in result]==[
        ('DS25-0001','DS24-0020'),('DS25-0002','DS24-0022')]
    assert all(not r['tracking_inputs'] for r in result)
    assert p['members'][0]['dataset_label']=='DS24-0022'
