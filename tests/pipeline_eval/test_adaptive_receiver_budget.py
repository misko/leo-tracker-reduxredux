import pytest

from adaptive_receiver_budget import receiver_budget


def test_publication_includes_the_tail_and_charges_unsplit_runs():
    # A 10 s fix has 4 s downstream. At 2x downstream, 60 MB may use
    # 3 s for the median gate. Two such fixes and a 2 s unsplit failure
    # leave 5 s for 120 MB on the summed gate.
    fix = dict(stages=[6, 1, 3], compressed_MB=60)
    failure = dict(stages=[0, 0, 2], compressed_MB=0)
    assert receiver_budget([fix, fix, failure], 2) == pytest.approx(
        dict(median_MB_s=20, summed_MB_s=24, both_MB_s=24))


def test_infeasible_post_detector_clock_has_no_finite_acquisition_rate():
    fix = dict(stages=[4, 4, 2], compressed_MB=40)
    assert receiver_budget([fix], 1) == dict(median_MB_s=None, summed_MB_s=None, both_MB_s=None)
