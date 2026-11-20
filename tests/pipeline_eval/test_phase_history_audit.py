from tools.pipeline_eval.qualification import stable_phase_history_audit as study


def test_first_eligible_epoch_is_inclusive_and_requires_both_thresholds():
    fields = (
        (0.0, 0.0),
        (0.010001, 0.0),
        (0.01, 0.001),
        (0.0, 0.0),
        (1.0, 1.0),
    )
    rows = [dict(raw_phase_change_s=p, movement_km=m) for p, m in fields]
    assert study.stop_index(rows) == 2
    rows[2]["movement_km"] = 0.001001
    assert study.stop_index(rows) == 3
    rows[3]["movement_km"] = 0.1
    assert study.stop_index(rows) == 4


def test_branch_selection_uses_the_paired_c0_checkpoint_and_cold_rank_ties():
    branches = [
        dict(
            c0=dict(rounds=[{"objective": first}, {"objective": last}], stop_index=0),
            fitted_c=dict(rounds=[{"objective": -first}], stop_index=0),
        )
        for first, last in ((1, 5), (1, 4), (2, 3))
    ]
    assert study.winner(branches, stopped=False) == 2
    assert study.winner(branches, stopped=True) == 0


def mapped(**values):
    return ["map", list(values.items())]


def saved_series(start, end, fit):
    return dict(
        phase_reference=["list", [start]],
        posterior_phase_s=["list", [end]],
        max_reference_change_s=abs(end - start),
        fit=fit,
    )


def test_archive_trajectory_uses_raw_phase_and_the_actual_previous_endpoint():
    positions = [0.0, 0.1, 0.1003, 0.1008, 0.101]
    frames = [(0, 16), (15, 15.1), (15, 15.008), (15, 15), (15, 15)]
    fits = [mapped(parameters=["list", [x, 0]], score=19, residual_rms_hz=3) for x in positions]
    series = [
        mapped(epoch=i, **saved_series(*phases, fit))
        for i, (phases, fit) in enumerate(zip(frames, fits, strict=True))
    ]
    actual = study.trajectory(mapped(phase_rounds=["list", series], fit=fits[-1]), None)
    assert actual["stop_index"] == 2
    assert actual["rounds"][1]["raw_phase_change_s"] > 0.01
    assert actual["rounds"][2]["start_east_north_km"] == [0.1, 0.0]
