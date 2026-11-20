import pytest

from tools.pipeline_eval.qualification import portable_field_scores as scores


def test_calibration_error_threshold_and_rf_change_are_independent():
    rows = []
    for method in (scores.PORTABLE, scores.ARCHIVE, *scores.ROLES):
        for arm in scores.ARMS:
            withheld = method == "omitted-tracks"
            fitted = arm == "fitted_c"
            error = 1.0 + (0.08 if method == scores.PORTABLE and fitted else 0.0)
            rows.append(
                dict(
                    method=method,
                    arm=arm,
                    error_km=None if withheld else error,
                    rf_rms_hz=None if withheld else (80 if fitted else 90),
                    frequency_score=None,
                )
            )
    decision = scores.accuracy(rows)
    assert decision["primary"] == dict(within_5_percent=False, within_10_percent=True)
    ablation = decision["fitted_c_minus_c0"][scores.PORTABLE]
    assert ablation["error_km"] == pytest.approx(0.08)
    assert ablation["rf_rms_hz"] == -10
    assert decision["comparison_by_control"]["omitted-tracks"]["c0"]["within_10_percent"] is None
    rows[1]["error_km"] = None
    assert scores.accuracy(rows)["primary"]["within_10_percent"] is None


def test_visit_deadline_uses_valid_count_and_separate_clocks():
    visits = [
        dict(status="processed", detector_cpu_s=0.020, detector_wall_s=0.022),
        dict(status="processed", detector_cpu_s=0.017, detector_wall_s=0.019),
        dict(status="invalid_capture", detector_cpu_s=0.001, detector_wall_s=0.001),
    ]
    timings = scores.visit_timings(visits)
    assert timings["cpu_ms"]["n"] == timings["wall_ms"]["n"] == 2
    assert timings["cpu_ms"]["within_20_ms"] == 2
    assert timings["wall_ms"]["within_20_ms"] == 1


def test_modified_terminal_evidence_is_rejected(tmp_path):
    path = tmp_path / "summary.json"
    path.write_text('{"status":"ok"}')
    seal = {path.name: scores._sha(path)}
    scores.checked_files(tmp_path, seal, (path.name,))
    path.write_text('{"status":"failed"}')
    with pytest.raises(ValueError, match="SHA-256"):
        scores.checked_files(tmp_path, seal, (path.name,))
