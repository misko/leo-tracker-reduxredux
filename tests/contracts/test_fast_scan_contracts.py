import pytest

from leo.contracts.fast_scan import FastScanPolicyV1, FastScanScoreV1


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 1.1])
def test_gate_cutoff_is_finite_and_normalized(value):
    with pytest.raises(ValueError):
        FastScanPolicyV1(threshold=value)


def test_unsupported_sample_geometry_and_nonfinite_score_are_rejected():
    with pytest.raises(ValueError):
        FastScanPolicyV1(sample_rate_hz=5000000)
    with pytest.raises(ValueError):
        FastScanScoreV1(receiver_id=0, margin=float("nan"), exact=0, control=0, epoch_sample=0)
