import csv
import hashlib
import io
import json
from pathlib import Path

import pytest
from historical_table import MODEL_IDS, REPOSITORY, build_document, render_csv

ROOT = Path(__file__).resolve().parent


def rows_by_id(document):
    return {row["model_id"]: row for row in document["rows"]}


def test_complete_frozen_model_set_and_explicitly_different_training_coverage():
    document = build_document()
    rows = rows_by_id(document)

    assert tuple(rows) == MODEL_IDS
    assert document["row_count"] == 13
    assert {rows[name]["no_holdout"] for name in MODEL_IDS[:3]} == {False}
    assert {rows[name]["no_holdout"] for name in MODEL_IDS[3:]} == {True}
    assert all("first two thirds" in rows[name]["training_coverage"] for name in MODEL_IDS[:3])
    assert all("blind validation" in row["qualification"] for row in rows.values())
    assert rows["track_linear"]["objective_id"] != rows["glrt_fixed_16"]["objective_id"]
    assert rows["glrt_fixed_16"]["objective_id"] != rows["anchors"]["objective_id"]


def test_metrics_and_parameter_freedom_come_from_the_named_artifacts():
    rows = rows_by_id(build_document())

    assert rows["track_linear"]["reference_error_km"] == pytest.approx(3.00555989381213)
    assert rows["track_linear"]["fit_unit_count"] == 60
    assert rows["glrt_fixed_16"]["fit_unit_count"] == 3192
    assert rows["glrt_fixed_16"]["assigned_satellite_ids"] is None
    assert len(rows["glrt_fixed_16"]["candidate_satellite_ids"]) == 16
    assert rows["glrt_fixed_16"][
        "all_group_nearest_curve_mean_capped_soft_l1_loss_hz2"
    ] == pytest.approx(258344.9193427327)
    assert rows["glrt_free_16"]["free_parameters"][-1] == "rx1_slope_hz_s"
    assert rows["glrt_timing_3s"]["timing_sigma_s"] == 1
    assert rows["glrt_timing_3s"]["timing_bound_s"] == 3
    assert rows["glrt_timing_3s"]["assigned_satellite_count"] > 0
    assert rows["glrt_timing_10s"]["timing_sigma_s"] == pytest.approx(10 / 3)
    assert rows["coherent_timing"]["assigned_weighted_rms_hz"] == pytest.approx(99.39371687052841)
    assert rows["coherent_timing"]["active_timing_satellite_count"] == 7
    assert rows["anchors"]["nearest_curve_metric_role"].startswith("diagnostic only")


def test_every_provenance_receipt_matches_current_tree():
    for row in build_document()["rows"]:
        assert row["provenance"]
        for receipt in row["provenance"]:
            path = REPOSITORY / receipt["path"]
            assert path.is_file()
            assert hashlib.sha256(path.read_bytes()).hexdigest() == receipt["sha256"]


def test_csv_preserves_objective_specific_columns_and_json_fields():
    document = build_document()
    parsed = list(csv.DictReader(io.StringIO(render_csv(document))))

    assert len(parsed) == 13
    assert parsed[0]["model_id"] == "track_independent"
    assert parsed[0]["track_training_mean_capped_soft_l1_cost_hz2"]
    assert not parsed[0]["all_group_nearest_curve_mean_capped_soft_l1_loss_hz2"]
    assert parsed[4]["all_group_nearest_curve_mean_capped_soft_l1_loss_hz2"]
    assert json.loads(parsed[4]["free_parameters"]) == ["east_km", "north_km"]
    assert json.loads(parsed[4]["provenance"])[0]["role"] == "result"


def test_generated_outputs_match_the_deterministic_builder():
    document = build_document()

    assert json.loads((ROOT / "historical-sample.json").read_text()) == document
    assert (ROOT / "historical-sample.csv").read_text() == render_csv(document)
