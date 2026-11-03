from audit import overlap_pairs


def product(left_start=0,left_end=60,right_start=10,right_end=55,rf0=11e9,rf1=11e9):
    tracks=[dict(tracklet_id='a',receiver_id=0,actual_rf_hz=rf0,start_utc_ns=int(left_start*1e9),end_utc_ns=int(left_end*1e9)),
            dict(tracklet_id='b',receiver_id=1,actual_rf_hz=rf1,start_utc_ns=int(right_start*1e9),end_utc_ns=int(right_end*1e9))]
    return dict(tracklets=tracks,tle_candidates=[dict(tracklet_ids=['a','b'])])


def test_overlap_is_intersection_not_union():
    result=overlap_pairs(product())
    assert len(result)==1 and result[0]['overlap_s']==45


def test_different_rf_and_short_overlap_do_not_qualify():
    assert overlap_pairs(product(rf1=12e9))==[]
    assert overlap_pairs(product(right_start=40))==[]


def test_thirty_seconds_inclusive():
    assert overlap_pairs(product(right_start=30,right_end=60))[0]['overlap_s']==30
