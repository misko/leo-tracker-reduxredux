from probe_ds23_gate_retention_cohort import select_offer


def test_offer_selection_never_uses_an_unsupported_family_for_more_coverage():
    unsupported=dict(added_points=100,independent_support_pass=False,proposal_score=0,norad=1)
    supported=dict(added_points=50,independent_support_pass=True,proposal_score=20,norad=2)
    assert select_offer([unsupported,supported]) is supported
    assert select_offer([unsupported]) is None


def test_offer_ties_are_decided_by_radio_score_then_identity_only():
    a=dict(added_points=30,independent_support_pass=True,proposal_score=10,norad=5)
    b=dict(added_points=30,independent_support_pass=True,proposal_score=11,norad=3)
    assert select_offer([b,a]) is a
    assert select_offer([dict(a,norad=7),a]) is a
