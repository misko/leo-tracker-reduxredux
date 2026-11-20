from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import complete_detector_roster as study


def position(ident, method, point=(0, 0)):
    result = dict(
        status="ok" if point is not None else "timed_out",
        boundary="IQ through position",
        metrics={},
        arms={arm: dict(latlon=point) for arm in study.ARMS},
    )
    if point is None:
        result["reason"] = "recorded terminal deadline"
    return dict(
        id=ident,
        method=method,
        tile={"id": "original"},
        native_sha256="detected",
        paired_capture_sha256="original",
        original_request_sha256="request",
        catalog_sha256="orbit",
        result=result,
    )


def examples():
    twelve = [
        position(i, name, None if i == "overlap" and name.endswith("_first") else (0, 0))
        for i in ("old", "overlap")
        for name in ("wide_iq_roster_primary", "wide_iq_roster_original_first")
    ]
    eight = [
        position(i, name)
        for i in ("pair", "overlap")
        for name in ("fresh_replay_stock", "fresh_replay_fifth")
    ]
    ten = [position("old", "fifth_completion_candidate")]
    fresh = [position("new", name) for name in ("new_waveforms_stock", "new_waveforms_fifth")]
    groups = dict(
        original_stock=["old", "overlap"],
        original_pair=["overlap", "pair"],
        fifth_completion=["old"],
        fresh=["new"],
        all=["new", "old", "overlap", "pair"],
    )
    return twelve, eight, ten, fresh, groups


def test_deduplicate_overlapping_inputs_and_preserve_earliest_timeout():
    *sources, groups = examples()
    rows = study.join_roster(*sources, groups)
    assert len(rows) == len(groups["all"]) * 3
    failed = [row for row in rows if row["result"]["status"] != "ok"]
    assert [(row["id"], row["method"]) for row in failed] == [("overlap", study.EARLY)]
    references = {
        i: dict(
            truth=[0, 0],
            reference={
                role: {arm: {"error_km": 0.0} for arm in study.ARMS} for role in study.ROLES
            },
        )
        for i in groups["all"]
    }
    scores = study.scored(rows, references)
    summary, paired = study.statistics(scores, groups)
    early = next(
        row
        for row in summary
        if (row["cohort"], row["arm"], row["method"]) == ("all", "c0", study.EARLY)
    )
    assert (early["scheduled"], early["published"], early["within_10pct"]) == (4, 3, 3)
    assert all(row["five_minus_four_m"] == 0 for row in paired)


def test_overlap_requires_both_scientific_arms_and_authenticated_measurements():
    twelve, eight, ten, fresh, groups = examples()
    row = next(r for r in eight if r["id"] == "overlap" and r["method"] == "fresh_replay_stock")
    row["result"]["metrics"]["stage_s"] = {"load": 29}
    study.join_roster(twelve, eight, ten, fresh, groups)
    row["result"]["arms"]["fitted_c"]["rf_rms_hz"] = 17
    with pytest.raises(ValueError, match="outcomes disagree"):
        study.join_roster(twelve, eight, ten, fresh, groups)
    shifted = deepcopy(ten)
    shifted[0]["catalog_sha256"] = "different-clock"
    with pytest.raises(ValueError, match="different original"):
        study.same_capture(shifted[0], ten[0])


def test_missing_and_duplicate_attempts_must_have_explicit_records():
    row = position("held", "capture", None)
    with pytest.raises(ValueError, match="every assigned"):
        study.select([row], "capture", ["held", "absent"])
    with pytest.raises(ValueError, match="repeated"):
        study.select([row, row], "capture", ["held"])


def test_actual_clock_and_exclusion_receipts_must_match_even_when_request_matches():
    stock = dict.fromkeys(("input_manifest_sha256", *study.COMMON), "same capture")
    candidate = position("held", "fifth")
    evidence = dict(stock, complete_raw=True, native_sha256=candidate["native_sha256"])
    study.verify_raw_pair(stock, evidence, candidate)
    with pytest.raises(ValueError, match="excluded visits"):
        study.verify_raw_pair(stock, dict(evidence, excluded_sha256="other"), candidate)
    with pytest.raises(ValueError, match="incomplete raw"):
        study.verify_raw_pair(stock, {"complete_raw": False}, candidate)
    failure = dict(position("held", "fifth", None), native_sha256=None)
    study.verify_raw_pair(stock, {"complete_raw": False}, failure)


def test_benchmark_cli_exposes_the_paired_summary_and_chart_location(tmp_path, monkeypatch, capsys):
    from tools.pipeline_eval.__main__ import main

    clock = dict(median_worker_s=1.5, detector_wall_within_20=2, detector_calls=3)
    study.save_json(
        tmp_path / "runtime-summary.json",
        {"groups": {"all": {study.FOUR: clock, study.FIVE: clock}}},
    )

    def measured(out):
        assert out == tmp_path.resolve()
        return [
            dict(
                cohort="all",
                arm="c0",
                method=study.FIVE,
                scheduled=2,
                published=1,
                within_10pct=0,
                median_km=1.5,
                p95_km=1.5,
            )
        ]

    monkeypatch.setattr(study, "run", measured)
    assert main(["benchmark", "--out", str(tmp_path)]) == 0
    display = capsys.readouterr().out
    assert all(value in display for value in ("Five regions", "1/2", "0/2", str(tmp_path)))
    assert "2/3 complete detector calls within 20 ms" in display


def test_timing_must_bind_the_actual_solver_and_both_calibration_outcomes():
    row = position("held", study.FIVE)
    measurement = dict(
        id=row["id"],
        method=row["method"],
        request_sha256="request",
        capture_sha256="original",
        catalog_sha256="orbit",
        scientific_outcome_sha256=study.sha256(
            study.encoded(study.scientific_outcome(row))
        ).hexdigest(),
    )
    study.verify_timed_positions([row], [measurement])
    with pytest.raises(ValueError, match="scientific outcome"):
        study.verify_timed_positions([row], [dict(measurement, request_sha256="other")])
    with pytest.raises(ValueError, match="missing measured timing"):
        study.verify_timed_positions([row], [])
