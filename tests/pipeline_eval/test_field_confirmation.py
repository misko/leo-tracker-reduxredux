import gzip
import hashlib
import json

import pytest

from tools.pipeline_eval.qualification import field_confirmation as confirmation


def test_scoring_requires_the_joint_prediction_seal(monkeypatch, tmp_path):
    monkeypatch.setattr(confirmation, "_verify_sources", lambda _: None)
    with pytest.raises(FileNotFoundError, match="prediction-lock.json"):
        confirmation.score(tmp_path, tmp_path / "results")

    (tmp_path / "predictions.jsonl.gz").write_bytes(gzip.compress(b""))
    (tmp_path / "sources.json").write_text("{}")
    (tmp_path / "holdout-receipt.json").write_text("{}")
    (tmp_path / "prediction-lock.json").write_text(
        json.dumps(dict(predictions_sha256=hashlib.sha256(b"different results").hexdigest()))
    )
    with pytest.raises(ValueError, match="differ from the seal"):
        confirmation.score(tmp_path, tmp_path / "results")


def test_region_acceptance_and_fix_are_scored_separately():
    label = dict(
        id="probe",
        pair="acquisition",
        site_group="region",
        difficulty="dispersed_open",
        condition="present",
        true_region="correct",
        latlon=[14.0, 2.0],
    )
    predictions = dict(
        latlon=None,
        forced_latlon=[14.0, 2.0],
        selected_region="correct",
        region_accepted=True,
        reason="position_at_tile_boundary",
    )
    simulation = {"tracks": [{"corrupt": False}, {"corrupt": True}]}
    present = confirmation._score_row(predictions, label, simulation)
    label.update(condition="missing", true_region=None)
    missing = confirmation._score_row(predictions, label, simulation)
    assert present["correct_nomination"]
    assert present["forced_error_km"] == 0
    assert not present["published"]
    assert missing["correct_nomination"] is None
    assert missing["region_accepted"]
    assert missing["false_region_acceptance"]
    assert not missing["false_publication"]
    groups = {
        g["condition"]: g
        for g in confirmation._summaries({"method": [present, missing]})
        if g["scene"] == "all"
    }
    assert groups["present"]["correct_nominations"] == 1
    assert groups["present"]["fixes"] == 0
    assert groups["present"]["trials"] == 1
    assert groups["missing"]["false_publications"] == 0
    assert groups["missing"]["false_region_acceptances"] == 1
