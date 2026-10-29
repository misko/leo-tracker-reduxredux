from audit_graph_recovery_witnesses import binned_comparison


def test_correlations_require_multiple_families_and_time_bins():
    target=dict(times_s=[1,6,11],residual_hz=[-10,0,10])
    first=dict(norad=1,times_s=[1,2,6,7,11,12],residual_hz=[-10,-10,0,0,10,10])
    repeated=dict(first)
    assert binned_comparison(target,[first,repeated])['correlation'] is None
    second=dict(first,norad=2)
    result=binned_comparison(target,[first,second])
    assert len(result['bins'])==3
    assert abs(result['correlation']-1)<1e-10
