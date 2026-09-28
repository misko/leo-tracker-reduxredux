from diagnose_reference_scores import classify, profile_offsets


def test_lower_loss_reference_means_missed_coverage():
    assert classify(12., 10.) == 'reference_better_search_missed_it'
    assert classify(8., 10.) == 'selected_better_than_reference'
    assert classify(10.+1e-11, 10.) == 'indistinguishable'


def test_fixed_symmetric_profile_without_adaptive_point_selection():
    offsets = profile_offsets()
    assert len(offsets) == len(set(offsets)) == 13
    assert offsets[0] == (0., 0.)
    assert all((-e, -n) in offsets for e, n in offsets)
    assert {abs(e)+abs(n) for e, n in offsets} == {0., 1.5625, 5., 25.}
