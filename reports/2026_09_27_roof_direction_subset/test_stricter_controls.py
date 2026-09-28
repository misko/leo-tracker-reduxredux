from stricter_controls import shuffle_within_lanes


def test_stratified_shuffle_keeps_calibration_and_lane_boundaries():
    rows=[]
    for split in ('cal','holdout'):
        for rx in ('rx0','rx1'):
            for track in range(4):
                rows.append(dict(split=split,session_id=split,receiver_id=rx,
                                 channel=1,edge='lower',sample_rate_hz=2500000,
                                 track_id=f'{rx}-{track}',observation_utc_ns=track,
                                 east=(100 if rx=='rx1' else 0)+track,up=.5))
    transformed,moved=shuffle_within_lanes(rows,42)
    assert moved>0
    assert [r for r in rows if r['split']=='cal']==[r for r in transformed if r['split']=='cal']
    for rx in ('rx0','rx1'):
        assert sorted(r['east'] for r in rows if r['split']=='holdout' and r['receiver_id']==rx)==sorted(r['east'] for r in transformed if r['split']=='holdout' and r['receiver_id']==rx)
