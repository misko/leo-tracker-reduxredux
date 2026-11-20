from copy import deepcopy

import pytest

from tools.pipeline_eval import __main__ as cli
from tools.pipeline_eval.qualification import one_lane_benchmark as study
from tools.pipeline_eval.qualification import receiver_budget


def observations():
    scores = [
        dict(
            id=ident,
            arm=arm,
            method="m",
            status="ok" if err is not None else "withheld",
            error_km=err,
            baseline_km=base,
        )
        for ident, err, base in (
            ("both", 1.10, 1.0),
            ("late", 0.0, 0.0),
            ("without-wall", 0.5, 1.0),
            ("withheld", None, 1.0),
        )
        for arm in study.ARMS
    ]
    clocks = [
        dict(
            id=ident,
            method="m",
            acquisition_evidence=study.PROJECT if sec is None else study.RAW,
            full_service_s=sec,
            complete_detector_calls=None if sec is None else 10,
            wall_within_20ms=None if sec is None else 8,
            call_clock_scope="native" if sec else None,
        )
        for ident, sec in (
            ("both", 300),
            ("late", 300.001),
            ("without-wall", None),
            ("withheld", 250),
        )
    ]
    spans = {c["id"]: 300.0 for c in clocks}
    return scores, clocks, spans


def test_same_recording_must_meet_both_budget_and_accuracy():
    scores, clocks, spans = observations()
    rows = receiver_budget.joined_rows(scores, clocks, spans)
    out = receiver_budget.summarize(rows, {"all": list(spans)}, ["m"])[0]
    assert (out["scheduled"], out["published"], out["within_10pct"]) == (4, 3, 3)
    assert (out["service_clock_measured"], out["service_clock_unmeasured"]) == (3, 1)
    assert out["within_5pct_and_span"] == 0
    assert out["within_10pct_on_timed"] == 2 and out["within_10pct_and_span"] == 1
    assert out["completed_within_span"] == 2
    assert out["fraction_calls_within_20ms"] == 0.8
    unknown = next(r for r in rows if r["id"] == "without-wall")
    assert unknown["within_10pct_and_span"] is None
    only = receiver_budget.summarize(rows, {"held": ["without-wall"]}, ["m"])[0]
    assert only["within_10pct_and_span"] is None and only["measured_calls"] is None


@pytest.mark.parametrize(
    "problem",
    [
        "missing-time",
        "duplicate-arm",
        "wrong-calibration",
        "fake-time",
        "invalid-count",
        "partial-count",
        "nonfinite-time",
        "bad-span",
        "absent-span",
        "withheld-endpoint",
    ],
)
def test_joint_benchmark_rejects_mismatched_inputs(problem):
    scores, clocks, spans = observations()
    if problem == "missing-time":
        clocks.pop()
    elif problem == "duplicate-arm":
        scores.append(deepcopy(scores[0]))
    elif problem == "wrong-calibration":
        scores[0]["arm"] = "unmeasured"
    elif problem == "fake-time":
        clocks[2]["full_service_s"] = 1
    elif problem == "invalid-count":
        clocks[0]["wall_within_20ms"] = 11
    elif problem == "partial-count":
        clocks[0]["complete_detector_calls"] = None
    elif problem == "nonfinite-time":
        clocks[0]["full_service_s"] = float("nan")
    elif problem == "bad-span":
        spans["both"] = 0
    elif problem == "absent-span":
        spans.pop("late")
    else:
        scores[-1]["error_km"] = 0.1
    with pytest.raises(ValueError):
        receiver_budget.joined_rows(scores, clocks, spans)


def test_one_lane_entry_and_spherical_comparison(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "DEFAULT_OUT", tmp_path)
    monkeypatch.setattr(study, "run", lambda p: calls.append(p) or [])
    monkeypatch.setattr(study, "show", lambda rows, p: calls.append(p))
    assert cli.main(["benchmark", "--receiver", "one-lane"]) == 0
    assert calls == [tmp_path / "one-lane-benchmark"] * 2

    def row(coord):
        return dict(
            id="a",
            paired_capture_sha256="raw",
            original_request_sha256="req",
            tile={"center": [0, 180]},
            catalog_sha256="orbits",
            native_sha256="detector",
            result=dict(status="ok", arms={a: dict(latlon=coord) for a in study.ARMS}),
        )

    diff = study.compare_positions(row([0, 179.999]), row([0, -179.999]))
    assert all(r["coordinate_separation_km"] == pytest.approx(0.22239, rel=0.0001) for r in diff)
    assert study.compare_positions(row(None), row([0, 180]))[0]["coordinate_separation_km"] is None
    with pytest.raises(ValueError, match="catalogues"):
        study.compare_positions(row([0, 0]), dict(row([0, 0]), catalog_sha256="later"))
