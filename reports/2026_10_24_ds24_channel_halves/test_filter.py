from filtered_prepare import restrict


def test_halves_partition_original_evidence_without_changing_time_or_identity():
    rows=[dict(channel=c,observation_id=f'p{c}',time_s=101.3+c,measured_cfo_hz=c*100,
               receiver=2,actual_rf_hz=10e9+c*1e8) for c in range(1,9)]
    metadata=dict(anchor_utc_ns=123,causal_cutoff_utc_ns=100)
    a,ma=restrict(rows,metadata,[1,2,3,4]);b,mb=restrict(rows,metadata,[5,6,7,8])
    assert a+b==rows and len(a)==len(b)==4
    assert set(r['observation_id'] for r in a).isdisjoint(r['observation_id'] for r in b)
    assert ma['anchor_utc_ns']==mb['anchor_utc_ns']==123
    assert ma['causal_cutoff_utc_ns']==100
    assert metadata==dict(anchor_utc_ns=123,causal_cutoff_utc_ns=100)


def test_empty_half_is_explicit_not_replaced_by_other_channels():
    rows=[dict(channel=1,observation_id='x')]
    kept,meta=restrict(rows,{},[5,6,7,8])
    assert kept==[] and meta['selected_winning_points']==0
