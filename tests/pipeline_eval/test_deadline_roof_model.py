import pytest

from tools.pipeline_eval.qualification import deadline_roof_model as model


def recorded(status, seconds=8, *, cap=None, pos=None, forced=None):
    return dict(
        id="fixture",
        deadline_s=cap,
        worker_wall_s=seconds,
        result=dict(
            status=status,
            reason="fixture",
            boundary="fixture worker",
            metrics={},
            arms={arm: dict(latlon=pos, forced_latlon=forced) for arm in model.ARMS},
        ),
    )


def test_timely_compact_withholding_keeps_its_diagnostic_and_ends_route():
    original = recorded("withheld", forced=[2.0, 3.0])
    out = model.replay(original, recorded("ok", pos=[3.0, 4.0]), 30)
    assert out["result"] == original["result"]
    assert out["endpoint_source"] == "compact"
    assert [call["method"] for call in out["calls"]] == ["compact"]
    assert out["elapsed_s"] == 8


def test_late_compact_success_is_discarded_and_only_smooth_forced_is_kept():
    compact = recorded("ok", seconds=30, pos=[2.0, 3.0], forced=[2.0, 3.0])
    smooth = recorded("withheld", seconds=6, forced=[3.0, 4.0])
    out = model.replay(compact, smooth, 30)
    assert out["elapsed_s"] == 21
    assert [call["budget_s"] for call in out["calls"]] == [15, 15]
    assert out["calls"][0]["status"] == "timed_out"
    assert out["result"] == smooth["result"]


def test_early_failure_gives_smooth_all_remaining_time():
    out = model.replay(recorded("failed", seconds=5), recorded("ok", seconds=22, pos=[1, 2]), 30)
    assert out["calls"][1]["budget_s"] == 25
    assert out["elapsed_s"] == 27
    assert out["endpoint_source"] == "smooth"


def test_archived_early_censor_leaves_outcome_and_time_unresolved():
    compact = recorded("timed_out", seconds=8.02, cap=8)
    out = model.replay(compact, recorded("ok", pos=[1, 2]), 30)
    assert out["result"]["status"] == "missing"
    assert out["elapsed_s"] is None
    assert out["elapsed_lower_bound_s"] == 8
    assert out["endpoint_source"] is None
    assert [r["method"] for r in out["calls"]] == ["compact"]


def test_new_cutoff_before_known_archived_censor_can_trigger_fallback():
    compact = recorded("timed_out", seconds=20.02, cap=20)
    out = model.replay(compact, recorded("ok", pos=[1, 2]), 30)
    assert out["endpoint_source"] == "smooth"
    assert out["elapsed_s"] == 23


def test_unavailable_input_bypasses_both_callbacks():
    unavailable = recorded("unavailable", seconds=None)
    out = model.replay({}, unavailable, 30, absent=True)
    assert out["result"] == unavailable["result"]
    assert out["selected"] == "none"
    assert out["calls"] == []
    assert out["elapsed_s"] is None


@pytest.mark.parametrize(
    "field", ["prior_timing_worker_wall_s", "prior_confirmation_worker_wall_s"]
)
def test_historical_timing_intervals_remain_usable(field):
    assert model.archived_wall({"id": "fixture", field: 5.0}) == 5.0
