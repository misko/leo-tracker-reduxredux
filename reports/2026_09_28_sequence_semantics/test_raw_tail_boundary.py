from raw_tail_boundary import eligible_transition


def test_eligibility_requires_real_axis_tail_and_distinct_preceding_region():
    assert eligible_transition(0.5, 0.02)
    assert not eligible_transition(0.5, 0.5)
    assert not eligible_transition(0.02, 0.02)
