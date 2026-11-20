import pytest

from tools.pipeline_eval.qualification import online_full as full
from tools.pipeline_eval.qualification.online_full_results import evaluate, verify_frontiers


def fixture_row(t, left, right):
    support = {str(i): {"latest_s": t - 0.1} for i in range(4)}
    return dict(
        checkpoint=t,
        capture=dict(actual_last_sample_s=t, available_at_elapsed_s=[t, t + 0.1]),
        result=dict(status="ok", arms={"c0": dict(latlon=left), "fitted_c": dict(latlon=right)}),
        orbit_support={"c0": support, "fitted_c": support},
        worker_wall_s=2.0,
        worker={"cpu_s": 1.0},
    )


def test_pair_stop_retains_first_arm_while_second_completes():
    rows = [
        fixture_row(120, [2, 3], [2, 3]),
        fixture_row(180, [2, 3], [1, 2]),
        fixture_row(240, [2, 2], [1, 2]),
    ]
    chosen = {}
    for i in range(1, 4):
        for arm in ("c0", "fitted_c"):
            full.decision(rows[:i], chosen, arm)
    assert chosen == {"c0": (1, "adjacent agreement"), "fitted_c": (2, "adjacent agreement")}
    fixture = dict(
        id="case",
        recording="case",
        condition="matched",
        rows=rows,
        terminal=dict(native_sha256="a", catalog_sha256="b"),
        picked={a: list(v) for a, v in chosen.items()},
    )
    result = evaluate(fixture)["result"]
    assert result["arms"]["c0"]["latlon"] == [2, 3]
    assert result["arms"]["fitted_c"]["latlon"] == [1, 2]
    assert result["metrics"]["workers"] == 3
    assert result["metrics"]["by_arm"]["c0"]["elapsed_host_s"] == [182.0, 182.1]
    with pytest.raises(ValueError, match="after both calibration"):
        evaluate(dict(fixture, rows=[*rows, fixture_row(300, [9, 8], [9, 8])]))


def test_score_rejects_a_sealed_wrong_frontier_even_with_an_ok_fit():
    limit = 120 * 10_000_000
    capture = dict(
        first_counter=50,
        last_sample_counter=limit + 40,
        first_noncausal_end_counter=limit + 60,
        uses_complete_capture=False,
        expected_probes=4,
        actual_last_sample_s=119.999999,
    )
    row = dict(
        checkpoint=120,
        capture=capture,
        result=dict(status="ok"),
        counts=dict(probes=4),
        latest_graph_time_s=110.0,
    )
    fixture = [dict(terminal={}, rows=[row])]
    verify_frontiers(fixture)
    capture["last_sample_counter"] = limit + 60
    with pytest.raises(ValueError, match="declared sample frontier"):
        verify_frontiers(fixture)
