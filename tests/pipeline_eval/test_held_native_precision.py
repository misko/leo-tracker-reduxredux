from math import isclose

from held_native_precision import Positive, auc_tally, learn, relative_variance, score, stratified_random


def positive(variance, status, error=None, stream=(0, "lower", 1, 1e10), block=0):
    return Positive(variance, status, None if error is None else error**2, stream, block)


def test_relative_variance_uses_only_candidate_margin_and_aperture():
    low = {"fractional_margin": .05}
    high = {"fractional_margin": .20}
    assert relative_variance(low, 8) / relative_variance(high, 8) == 4
    assert relative_variance(low, 8) / relative_variance(low, 20) == 6.25


def test_fixed_gate_preserves_at_least_95_percent_and_keeps_boundary_ties():
    rows = [positive(1., "same_atom", 10)] * 19 + [positive(5., "same_atom", 20)]
    model = learn(rows)
    assert model["reject_at_variance"] == 5.
    assert score(rows, model)["specificity"] == .95
    # This held panel can have very different margin exposure.
    assert score([positive(5., "same_atom", 10)], model)["specificity"] == 0.


def test_auc_ignores_candidate_only_for_disagreement_and_preserves_ties():
    rows = [positive(3, "sparse_only"), positive(1, "same_atom", 10), positive(1, "disagreement"),
            positive(2, "disagreement")]
    assert auc_tally(rows) == (1.5, 2)


def test_random_eligibility_pays_sparse_only_and_respects_stream_budget():
    radio0 = [positive(5, "same_atom", 10), positive(4, "disagreement"), positive(1, "sparse_only")]
    radio1 = [positive(1, "disagreement", stream=(1,)), positive(2, "same_atom", 10, stream=(1,))]
    result = stratified_random({0: radio0, 1: radio1}, {"reject_at_variance": 4})
    assert all(isclose(result[key]["expectation"], 2/3)
               for key in ("same_atom", "disagreement", "sparse_only"))
    assert isclose(result["discrepancy2"]["expectation"], 200/3)
