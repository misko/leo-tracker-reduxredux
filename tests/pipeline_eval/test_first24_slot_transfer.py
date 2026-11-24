import pytest

from reports.ALGO08.v3.first24_slot_transfer import project, scenario, transfer


def test_transfer_caps_positive_credit_without_erasing_measured_slowdown():
    assert transfer(3, 4, 2, 5) == 5
    assert transfer(-3, 4, 2, 0) == -6
    assert transfer(-3, 0, 2, 1) == 0
    with pytest.raises(ValueError, match="Invalid"):
        transfer(1, 1, 0, 1)


def row(stock, actual, *, rejected=0, fallback=0):
    return {
        "stock_wall_s": stock,
        "actual_wall_s": actual,
        "actual_child_wall_s": actual - 1,
        "work": {"prefetch": {"worker_cpu_ns": 2_000_000_000, "hit_bytes": 20}},
        "acquisition_s": 8,
        "decision_publication_s": 6,
        "native_detector_s": 5,
        "fallback_route": {
            "rejected": {"elapsed_s": rejected},
            "fallback": {"elapsed_s": fallback},
        },
    }


def test_stage_caps_hold_callback_publication_and_external_verification_fixed():
    donor = {
        "hit_bytes": 10,
        "delta_seconds": {"producer_cpu": 3, "acquisition_wall": 5, "prefix_exit_wall": 40},
    }
    result = project(row(30, 20), donor)
    assert result == {
        "producer_cpu": 2,
        "producer_cpu_if_wall": 2,
        "acquisition_wall": 3,
        "prefix_exit_wall": 8,
    }
    donor["delta_seconds"]["prefix_exit_wall"] = -0.25
    assert project(row(30, 20), donor)["prefix_exit_wall"] == -0.5


def test_fallback_is_disjoint_and_a_slot_slowdown_does_not_add_common_budget():
    rows = [row(28, 20, rejected=2, fallback=3), row(42, 25)]
    measured = scenario(rows, [-1, 0], ())
    proposal = scenario(rows, [-1, 0], ("rejected",))
    both_free = scenario(rows, [-1, 0], ("rejected", "fallback"))
    assert measured["slot_saving"] == -1 and measured["remaining"] == 46
    assert proposal["remaining"] == 44 and both_free["remaining"] == 41
    assert both_free["fallback_saving"] == 5
    assert measured["remaining_common_path"]["eligible_s"] == 23
    assert proposal["remaining_common_path"]["joint_s"] == pytest.approx(529 / 55)
    assert both_free["remaining_common_path"]["joint_s"] == pytest.approx(6)
