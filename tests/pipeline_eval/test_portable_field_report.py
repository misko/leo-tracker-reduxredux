from tools.pipeline_eval.qualification import portable_field_report as report


def test_stage_csv_rows_carry_each_cdf_point_and_preserve_absent_results(tmp_path, monkeypatch):
    header = "visit,status,cpu_ms,wall_ms\n"
    archive = tmp_path / "secondary-raw-visits.csv"
    archive.write_text(header + "0,processed,250,270\n")
    live = tmp_path / "raw-visits.csv"
    live.write_text(header + "0,processed,20,22\n1,invalid_capture,1,1\n2,processed,15,17\n")
    monkeypatch.setattr(report, "HISTORICAL", tmp_path)
    evidence = dict(
        raw=dict(wall_s=25, completed=3),
        accelerated_raw=dict(wall_s=30),
        command_wall_s=34,
        command_clock=dict(process_elapsed_s=35),
        accelerated_command=dict(process_elapsed_s=40),
        accelerated_compact={},
        archived_compact={},
        recorded_delivery_span_s=32,
    )
    scores = [
        dict(method=report.PORTABLE, arm="c0", rf_rms_hz=71, frequency_score=2000),
        dict(method="omitted-tracks", arm="c0", rf_rms_hz=None, frequency_score=None),
    ]
    rows = report.stage_rows(tmp_path, evidence, scores)
    cpu = [row for row in rows if row["series"] == "Portable CPU"]
    assert [(r["visit"], r["value"], r["fraction"]) for r in cpu] == [(2, 15, 0.5), (0, 20, 1.0)]
    assert next(r for r in rows if r["series"] == "Portable command")["value"] == 35
    assert {r["series"] for r in rows if r["panel"] == "rf"} == {"Portable live"}
    assert next(r for r in rows if r["panel"] == "objective")["value"] == 2000
