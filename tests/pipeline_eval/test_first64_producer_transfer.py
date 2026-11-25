import pytest

from reports.ALGO08.v3.first64_producer_transfer import assess, prices


ROW = dict(hit_bytes=200, hits=2, worker_cpu=4., acquisition_s=10., acquisition_cpu_s=9.,
           native_detector_s=5., native_detector_process_cpu_s=4., actual_wall_s=20., actual_cpu_s=18.,
           decision_publication_s=7., validator_s=1., stock_wall_s=35., stock_cpu_s=31., solver=6., grid=2.)
DONOR = dict(hit_bytes=100, hit_count=1, delta_seconds=dict(producer_cpu=3., acquisition_wall=7.,
             acquisition_non_native_wall=4., paid_wall=20., prefix_exit_wall=-1.))


def test_caps_preserve_measured_negative_and_never_credit_zero_hits():
    expected = dict(producer_cpu=4., producer_cpu_if_wall=4., acquisition_wall=10.,
                    acquisition_non_native_wall=5., paid_wall=20., prefix_exit_wall=-2.)
    assert prices(ROW, DONOR, "bytes") == expected
    assert prices(ROW, DONOR, "hits") == expected
    assert prices(ROW | {"hit_bytes": 0}, DONOR, "bytes") == dict.fromkeys(expected, 0.)
    with pytest.raises(ValueError, match="complete authenticated"):
        prices(ROW, DONOR, "issued_windows")


def test_only_disjoint_wall_boundaries_can_stack_with_native_and_grid():
    for mode in ("paid_wall", "acquisition_wall", "prefix_exit_wall", "producer_cpu"):
        with pytest.raises(ValueError, match="explicitly disjoint"):
            assess([ROW], [1.], mode=mode, native_rate=1.5, grid_fraction=.5)
    report = assess([ROW], [1.], mode="acquisition_non_native_wall", native_rate=1.5, grid_fraction=.5)
    assert report["remaining"] == pytest.approx(20.-1.-5./3.-1.)
    assert report["both_gates"]


def test_producer_cpu_uses_cpu_for_both_arms_and_wall_requires_active_assumption():
    cpu = assess([ROW], [1.], mode="producer_cpu")
    wall = assess([ROW], [1.], mode="producer_cpu_if_wall")
    assert cpu["sum_ratio"] == 17./31.
    assert wall["sum_ratio"] == 19./35.
    assert wall["additional_uniform_non_grid_solver_cut"]["both"] == pytest.approx(1.5/4.)
