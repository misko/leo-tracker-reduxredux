import csv
import io
import json
import zipfile

import pytest

from tools.pipeline_eval.qualification import wide_roster as study
from tools.pipeline_eval.qualification import wide_roster_results as results


def test_rebuild_uses_the_same_attempt_description_as_the_published_charts():
    charts = json.loads((study.REPORT / "figures.json").read_bytes())["charts"]
    with zipfile.ZipFile(study.REPORT.parent / "modification-charts.zip") as archive:
        inventory = list(csv.DictReader(io.StringIO(archive.read("chart-inventory.csv").decode())))
    for chart in charts:
        rows = [row for row in inventory if row["panel_id"] == chart["id"]]
        assert {row["arm"] for row in rows} == {"c0", "fitted_c"}
        assert all(row["notes"] == chart["caption"] for row in rows)


def test_roster_precedence_is_fixed_by_study_identity():
    rosters = {
        "scout-full": ["shared", "held", "scout-only"],
        "exact-wide-iq": ["shared", "held"],
        "full-stride": ["shared", "stride-only"],
        "fresh-waveform": ["other-case"],
    }
    assert study.primary_ids(rosters) == {
        "shared": "full-stride",
        "stride-only": "full-stride",
        "held": "exact-wide-iq",
        "scout-only": "scout-full",
    }


def test_earliest_failure_and_different_deadlines_are_retained():
    def record(study_name, launch, status, deadline):
        return {
            "id": "case",
            "study": study_name,
            "service_unit": f"unit-{launch}",
            "started_monotonic_s": launch,
            "result": {"status": status},
            "deadline_s": deadline,
            "full_raw_verified": status != "failed",
        }

    first = record("scout-full", 10, "timed_out", 360)
    primary = record("full-stride", 20, "ok", 360)
    failure = record("whole-winner", 30, "failed", 286)
    assert results.choose_attempts([primary, failure, first], {"case": "full-stride"}) == [
        primary,
        failure,
        first,
    ]
    assert primary["primary"] and not primary["original_first"]
    assert first["original_first"] and not first["primary"]
    assert first["result"]["status"] == "timed_out"
    assert failure["decision"] == "retained failed setup"
    assert failure["deadline_s"] == 286


def test_incomplete_raw_recording_cannot_support_a_position():
    measurement = dict.fromkeys(results.COMMON, "bound")
    measurement.update(
        counts={
            "recording_windows": 3,
            "processed_windows": 2,
            "invalid_capture": 1,
            "probe_rows": 4,
            "iq_bytes": 4_800_000,
        },
        dual_calls=2,
    )
    case = {"recording": {"window_count": 3}}
    results.whole_support(measurement, case, "bound")
    measurement["counts"]["iq_bytes"] -= 1_600_000
    with pytest.raises(ValueError, match="complete received IQ"):
        results.whole_support(measurement, case, "bound")


def test_failed_attempt_counts_against_coverage_and_has_no_pair_delta():
    attempts = []
    scored = []
    for unit, errors in [("finished", [1.0, 0.8]), ("timed-out", [None, None])]:
        attempts.append({"service_unit": unit, "full_raw_verified": True})
        for arm, error in zip(("c0", "fitted_c"), errors, strict=True):
            scored.append(
                {
                    "service_unit": unit,
                    "arm": arm,
                    "published": error is not None,
                    "within_5pct": error == 0.8,
                    "within_10pct": error is not None,
                    "error_km": error,
                    "conditional_rms_hz": 8.0 if error == 1.0 else 8.5 if error else None,
                    "conditional_frequency_score": 20.0 if error else None,
                }
            )
    data = results.summarize(scored, attempts)
    assert data["trials"] == data["complete_raw"] == 2
    assert data["geography"]["fitted_c"]["published"] == 1
    assert data["geography"]["fitted_c"]["within_5pct"] == 1
    assert data["geography"]["fitted_c"]["error_km"]["n"] == 1
    contrast = data["calibration_fitted_minus_zero"]
    assert contrast["error_km"]["p50"] == pytest.approx(-0.2)
    assert contrast["conditional_rms_hz"]["p50"] == pytest.approx(0.5)
    assert contrast["conditional_frequency_score"]["n"] == 1
