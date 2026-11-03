import json

import pytest
from evaluate_profile_batch import validate_receipt


def receipt():
    return {"schema": "finite-set-tau-profile/v1", "run_id": "finite-set-tau-profile-v1",
            "unit": {"unit_id": "DS10-S02"}, "reference_read_before_seal": False,
            "evaluation_written": False, "sealed_utc": "2026-10-02T12:00:00+00:00",
            "source_hashes": {"input": "0" * 64}}


def test_accepts_sealed_profile_receipt():
    validate_receipt(receipt(), "DS10-S02", "finite-set-tau-profile-v1")


@pytest.mark.parametrize("name", [
    "legacy-timing10-cohort", "grouped-timing-profile-joint", "grouped-independent-rx",
])
def test_accepts_timing10_comparison_receipt(name):
    record = receipt()
    record.update(schema=f"{name}/v1", run_id=f"{name}-v1")
    validate_receipt(record, "DS10-S02", f"{name}-v1")


@pytest.mark.parametrize(
    "name",
    [
        "capture-reset", "reset-profile", "rf-fit", "rf-gn", "rf-profile",
        "reset-multistart", "reset-cohort", "rf-cohort", "group-mixture", "group-mixture-continue",
        "reset-sparse-continue",
    ],
)
def test_accepts_sealed_extended_model_receipt(name):
    record = receipt()
    record.update(schema=f"finite-set-{name}/v1", run_id=f"finite-set-{name}-v1")
    record["unit"] = {"unit_id": "DS10-D01"}
    validate_receipt(record, "DS10-D01", f"finite-set-{name}-v1")


@pytest.mark.parametrize("field,value", [
    ("reference_read_before_seal", True), ("evaluation_written", True),
    ("sealed_utc", None), ("source_hashes", {}),
    ("schema", "unknown"), ("run_id", "unknown"),
])
def test_rejects_unsealed_or_unidentified_receipts(field, value):
    record = receipt()
    record[field] = value
    with pytest.raises(ValueError, match="sealed, truth-free"):
        validate_receipt(record, "DS10-S02", "finite-set-tau-profile-v1")


def test_rejects_wrong_unit():
    with pytest.raises(ValueError):
        validate_receipt(receipt(), "DS11-S02", "finite-set-tau-profile-v1")


@pytest.mark.parametrize("matching_fit", [True, False])
def test_archived_evaluation_binds_fit_not_current_fitter_code(tmp_path, monkeypatch, matching_fit):
    import evaluate_profile_batch as module

    monkeypatch.setattr(module, "ROOT", tmp_path)
    directory = tmp_path / "runs" / "finite-set-tau-profile-v1" / "DS10-S02"
    directory.mkdir(parents=True)
    fit_path = directory / "fit.json"
    fit_path.write_text(json.dumps(receipt()))
    reference = tmp_path / "reference.json"
    reference.write_text("reference")
    result = {"fit_sha256": module.digest(fit_path) if matching_fit else "wrong",
              "reference_file_sha256": {str(reference): module.digest(reference)}}
    (directory / "evaluation.json").write_text(json.dumps(result))
    if matching_fit:
        assert module.evaluate_unit("DS10-S02", "finite-set-tau-profile-v1") == result
    else:
        with pytest.raises(ValueError, match="different fit"):
            module.evaluate_unit("DS10-S02", "finite-set-tau-profile-v1")
