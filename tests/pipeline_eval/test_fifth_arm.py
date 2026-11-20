from tools.pipeline_eval.qualification import fifth_arm


def payload(offset=0.0, hz=42_000.0, margin=0.2, selected=(730, 912)):
    candidate = dict(
        epoch=730,
        coarse_bin=5,
        fractional_epoch=dict(
            status="complete",
            offset_samples=offset,
            tracking_cfo_hz=hz,
            exact_score=margin + 0.1,
            control_score=0.1,
            margin=margin,
        ),
    )
    return dict(
        rows=[
            dict(candidates=[candidate], timings_ms={"fractional_epoch": 0.5}),
            dict(candidates=[]),
        ],
        top16=[list(selected), []],
        trace=[{"added_epochs": 3}, {"added_epochs": 0}],
    )


def test_numerical_drift_does_not_mask_ordered_scout_and_fractional_match():
    host, arm = payload(), payload(offset=1e-9, hz=42_005.0)
    out = fifth_arm.compare(host, arm)
    assert not out["exact_payload"]
    assert out["full16_matches"] == [True, True]
    assert out["support_trace_exact"]
    assert out["lanes"][0]["ordered_integer_keys_match"]
    assert out["lanes"][0]["positive_matches"][0]["raw_cfo_delta_hz"] == 5.0


def test_full_order_and_gate_change_remain_visible():
    host, arm = payload(), payload(margin=0.024, selected=(730, 913))
    out = fifth_arm.compare(host, arm)
    assert out["rank_one_matches"] == [True, True]
    assert out["full16_matches"] == [False, True]
    assert out["lanes"][0]["production_only"] == 1
    assert out["lanes"][0]["native_positive"] == 0


def test_science_projection_ignores_native_stage_clocks_only():
    raw = payload()["rows"]
    assert fifth_arm.science(raw)[0] == {"candidates": raw[0]["candidates"]}
    assert fifth_arm.science(raw)[1] == {"candidates": []}
