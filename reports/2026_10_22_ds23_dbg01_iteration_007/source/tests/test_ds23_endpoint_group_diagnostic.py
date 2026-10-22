import numpy as np

from probe_ds23_endpoint_group_diagnostic import endpoint_variants


def test_remote_endpoint_can_propose_a_lower_order_core_without_deleting_a_measurement():
    rng=np.random.default_rng(22);times=np.r_[-10.,np.linspace(0.,12.,19)]
    values=1000+20*times+2*times**2+rng.normal(0,3,len(times));values[0]-=1000
    track=dict(times=times,values=values,pieces=[dict(degree=4)])
    original=values.copy();variants=endpoint_variants(track)
    assert len(variants)==1 and variants[0]['removed_index']==0 and len(variants[0]['indices'])==19
    np.testing.assert_array_equal(track['values'],original)


def test_evenly_supported_high_order_curve_has_no_isolated_endpoint_offer():
    times=np.linspace(0.,20.,20);track=dict(times=times,values=times**4,pieces=[dict(degree=4)])
    assert endpoint_variants(track)==[]


def test_predictive_subset_selection_requires_both_arms_and_matching_aliases():
    from probe_ds23_endpoint_predictive_view import choose
    a=dict(candidate_index=3,norad=123,eligible=True,alias=0,penalized_gain=20.)
    b=dict(a,alias=1)
    data=dict(rows=[dict(offer=dict(indices=[1,2]),arms=dict(c0=[a],fitted_c=[b]))])
    assert choose(data)==[]
    b['alias']=0
    selected=choose(data)
    assert len(selected)==1 and selected[0]['candidate_index']==3


def test_debug_targets_include_long_unused_linear_tracks():
    from diagnose_ds23_iteration007_tracks import choose_targets
    rows=[dict(points=19,original_points=19,curved=False),dict(points=10,original_points=20,curved=True)]
    assert choose_targets(rows)==rows[:1]


def test_following_archive_lookup_encodes_alpha5_identifiers():
    from prepare_ds23_dbg01_following import target_codes
    assert target_codes({100032,66871})==['66871','A0032']
