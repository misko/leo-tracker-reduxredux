import pytest

from tools.pipeline_eval import __main__ as cli
from tools.pipeline_eval.qualification import staggered_benchmark as study


def endpoint(method, *, status="ok", **extra):
    return dict(
        method=method,
        id="case",
        paired_capture_sha256="recording",
        native_sha256=method if status == "ok" else None,
        original_request_sha256="request",
        catalog_sha256="orbit",
        tile={"center": [0, 0]},
        result=dict(
            status=status,
            reason=None if status == "ok" else "service timed out",
            boundary="position",
            metrics={},
            arms={arm: {"latlon": [0.01, 0] if status == "ok" else None} for arm in study.ARMS},
        ),
        **extra,
    )


def test_stored_lane_mixture_binds_both_detector_inputs_and_both_calibrations():
    controls = [endpoint("stock"), endpoint("fifth")]
    mixed = endpoint("mixed", stock_native_sha256="stock", fifth_native_sha256="fifth")
    args = (controls, ("stock", "fifth"))
    rows = study.joined_panel(*args, [mixed], "mixed", ["case"], "reconstructed")
    assert [r["method"] for r in rows] == list(study.METHODS)
    assert [r["acquisition_evidence"] for r in rows] == [
        "full saved I/Q",
        "full saved I/Q",
        "reconstructed antenna records",
    ]
    with pytest.raises(ValueError, match="source detector"):
        study.joined_panel(
            *args, [dict(mixed, fifth_native_sha256="other")], "mixed", ["case"], "reconstructed"
        )
    with pytest.raises(ValueError, match="requests, tiles or catalogues"):
        study.joined_panel(
            *args, [dict(mixed, tile={"center": [1, 1]})], "mixed", ["case"], "fresh"
        )
    with pytest.raises(ValueError, match="every assigned"):
        study.joined_panel(*args, [], "mixed", ["case"], "fresh")
    failure = endpoint("mixed", status="timed_out")
    rows = study.joined_panel(*args, [failure], "mixed", ["case"], "fresh")
    assert rows[-1]["result"]["status"] == "timed_out"
    assert rows[-1]["acquisition_evidence"] == "full saved I/Q"


def test_selector_bound_and_mixed_recoveries_count_every_scheduled_recording():
    rows = []
    cases = {
        "gained": ([3, 3, 1], 1),
        "lost": ([0.3, 0.5, None], 1),
        "zero": ([0, 0.1, 0], 0),
        "no_original": ([0.2, 0.1, 0.4], None),
    }
    for ident, (errors, original) in cases.items():
        for m, error in zip(study.METHODS, errors, strict=True):
            for arm in study.ARMS:
                rows.append(
                    dict(
                        id=ident,
                        arm=arm,
                        method=m,
                        status="ok" if error is not None else "timed_out",
                        error_km=error,
                        within_5pct=error is not None
                        and original is not None
                        and error <= original * 1.05,
                        within_10pct=error is not None
                        and original is not None
                        and error <= original * 1.1,
                        **{f"{role}_km": original for role in study.ROLES},
                    )
                )
    summary, counts, pairs = study.comparison(rows, {"all": list(cases)})
    c = next(x for x in counts if x["arm"] == "fitted_c" and x["tolerance_pct"] == 10)
    assert (c["both"], c["four_only"], c["five_only"], c["neither"], c["no_reference"]) == (
        1,
        1,
        0,
        1,
        1,
    )
    assert (c["scheduled"], c["best_possible_fixed"], c["staggered"]) == (4, 2, 2)
    assert (c["beyond_fixed"], c["lost_from_fixed"]) == (1, 1)
    row = next(r for r in summary if r["method"] == study.MIXED)
    assert (row["published"], row["scheduled"], row["within_10pct"]) == (3, 4, 2)
    assert all(p["staggered_km"] is None for p in pairs if p["id"] == "lost")
    with pytest.raises(ValueError, match="once per arm"):
        study.comparison([*rows, rows[0]], {"all": list(cases)})


def test_frozen_schedule_uses_two_new_lower_edge_cases_outside_the_twenty():
    groups = study.frozen_groups()
    assert groups["fresh"] == ["DS26-0144", "DS29-0491"]
    assert len(groups["all"]) == 22 and len(groups["difficult"]) == 6
    assert set(groups["difficult"]) <= set(groups["reconstructed"])
    assert not set(groups["fresh"]) & set(groups["reconstructed"])


def test_public_benchmark_uses_distinct_default_output_for_staggered(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "DEFAULT_OUT", tmp_path)
    monkeypatch.setattr(study, "run", lambda p: seen.append(p) or [])
    monkeypatch.setattr(study, "show", lambda rows, p: seen.append(p))
    assert cli.main(["benchmark", "--receiver", "staggered"]) == 0
    assert seen == [tmp_path / "staggered-benchmark"] * 2


def test_reconstruction_exposes_only_its_measured_position_clock():
    r = dict(endpoint("mixed"), acquisition_evidence="reconstructed antenna records")
    t = study.timing_row(r, fit=8.0)
    assert t["position_worker_s"] == 8 and t["full_service_s"] is None
    assert t["complete_detector_calls"] is None and t["deadline_fraction"] is None
    with pytest.raises(ValueError, match="cannot measure"):
        study.timing_row(r, elapsed=8.0)
    r["acquisition_evidence"] = "full saved I/Q"
    assert study.timing_row(r, elapsed=9, calls=4, within=0)["deadline_fraction"] == 0
    with pytest.raises(ValueError, match="exceeds"):
        study.timing_row(r, calls=4, within=5)


@pytest.mark.parametrize(
    ("first", "second", "truth", "expected_km", "fraction"),
    [
        ([0, 179], [0, -179], [0, 180], 0, 0.5),
        ([0, 0], [0, 2], [1, 1], 111.195, 0.5),
        ([0, 0], [0, 2], [0, 3], 111.195, 1),
        ([0, 0], [0, 2], [0, -179.5], 19848.322, 1),
        ([40, -120], [40, -120], [40, -120], 0, 0),
    ],
)
def test_retrospective_segment_bound_handles_rotation_wrap_and_endpoint_limits(
    first, second, truth, expected_km, fraction
):
    km, along = study.segment_bound(first, second, truth)
    assert km == pytest.approx(expected_km, abs=0.02)
    assert along == pytest.approx(fraction, abs=1e-8)


def test_segment_is_undefined_for_missing_or_antipodal_endpoints():
    assert study.segment_bound([0, 0], None, [0, 1]) == (None, None)
    assert study.segment_bound([0, 0], [0, 180], [45, 80]) == (None, None)


def test_calibration_does_not_use_an_rf_improvement_as_a_coordinate():
    rows = []
    for method in study.METHODS:
        rows.extend(
            [
                dict(id="a", method=method, arm="c0", error_km=1, rf_rms_hz=3, frequency_score=4),
                dict(
                    id="a",
                    method=method,
                    arm="fitted_c",
                    error_km=2,
                    rf_rms_hz=1,
                    frequency_score=1,
                ),
                dict(
                    id="b", method=method, arm="c0", error_km=None, rf_rms_hz=4, frequency_score=3
                ),
                dict(
                    id="b",
                    method=method,
                    arm="fitted_c",
                    error_km=None,
                    rf_rms_hz=2,
                    frequency_score=2,
                ),
            ]
        )
    effects = study.calibration_effects(rows, {"all": ["a", "b"]})
    assert len(effects) == 3
    for r in effects:
        assert (r["paired_error_km"], r["paired_rf_rms_hz"], r["paired_frequency_score"]) == (
            1,
            2,
            2,
        )
        assert r["median_fitted_minus_zero_error_km"] == 1
        assert r["median_fitted_minus_zero_rf_rms_hz"] == -2
