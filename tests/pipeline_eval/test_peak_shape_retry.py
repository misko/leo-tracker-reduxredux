import pytest

from reports.ALGO08.v3.peak_shape_retry import compare, confidence, predictions


def metric(curvature, rival):
    peak = dict(score=2, distinct_peak=rival, curvature=curvature)
    return dict(exact=[peak, dict(peak, curvature=-2)])


def test_weaker_half_and_separated_tie_limit_confidence():
    assert confidence(metric(-1, 1)) == 0.5
    assert confidence(metric(-3, None)) == 2
    assert confidence(metric(-1, 2)) == 0
    assert confidence(None) == 0
    assert confidence(metric(None, 0)) == 0
    with pytest.raises(ValueError):
        confidence(metric(-1, 3))


def test_cutoff_does_not_use_held_distribution_or_empty_lanes():
    def row(i, curvature, factor=True):
        return dict(key=str(i), lane=0, digest=str(i), metric=metric(curvature, 0), factor=factor)

    groups = dict(dense=[row(i, -(i+1)/10) for i in range(4)] + [row(4, 0, None)],
                  weak=[row(5, -0.09), row(6, -0.1), row(7, -0.11)])
    result = predictions(groups)
    assert result["cutoff"] == 0.1
    assert [r["retry"] for r in result["rows"]["weak"]] == [True, True, False]


def test_uniform_charges_unmatched_paid_positives_and_checks_alignment():
    preds = [dict(key=str(i), lane=1, retry=i != 1) for i in range(3)]
    labels = [dict(key=str(i), lane=1, state=s, error_hz=e) for i, (s,e) in enumerate(
        (("matched", 3), ("matched", -4), ("different", None)))]
    out = compare(preds, labels)
    assert out["paid_states"] == dict(matched=1, different=1)
    assert out["captured_squared_fraction"] == 9/25
    assert out["uniform_expected_squared_fraction"] == 2/3
    assert out["best_possible_rms_hz"] == pytest.approx((16/2)**0.5)
    with pytest.raises(ValueError):
        compare(preds[:2], labels)
