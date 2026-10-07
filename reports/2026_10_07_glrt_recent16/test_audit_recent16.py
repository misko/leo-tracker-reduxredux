"""Audit fixtures use the frozen producer; numerical oracles remain independent."""

import copy
import json

import audit_recent16 as audit
import numpy as np
import pytest
from evaluator import evaluate_bank


def fixture():
    rng = np.random.default_rng(808)

    def pair(frames):
        return tuple(
            rng.normal(size=(frames, 64)) + 1j * rng.normal(size=(frames, 64)) for _ in range(2)
        )

    first, later = [pair(3), pair(2)], [pair(2), pair(4)]
    bank = [
        dict(candidate_id=0, candidate_rank=0, epoch_sample=137, seed_cfo_hz=57000.0),
        dict(candidate_id=4, candidate_rank=4, epoch_sample=417, seed_cfo_hz=-18000.0),
    ]
    energy = dict(
        exact_template_energy=np.linspace(0.3, 2.1, 64),
        control_template_energy=np.linspace(0.6, 1.3, 64),
    )
    evaluation = evaluate_bank(bank, first, later, **energy)
    case = dict(label="R01", case_id="fixture", candidate_bank=bank, evaluation=evaluation)
    arrays = dict(energy)
    for wi, pairs in enumerate((first, later)):
        for index, values in enumerate(pairs):
            for name, value in zip(("exact", "control"), values, strict=True):
                arrays[f"w{wi}_c{index}_{name}"] = value
    return case, arrays


def test_independent_oracles_accept_noncontiguous_ids_and_variable_support():
    case, arrays = fixture()
    result = audit.audit_bank(case, arrays)
    assert result["passed"]
    assert result["candidates"] == 2
    assert result["methods"] == 17
    assert result["comparison_counts"]["first_current_score"] == 2
    assert result["comparison_counts"]["later_gaussian_winner_margin"] == 17
    assert result["comparison_counts"]["later_phase_kernel32_baseline_margin"] == 17
    assert max(result["max_absolute_errors"].values()) < 1e-9


@pytest.mark.parametrize(
    "metric,field",
    [
        ("gaussian", "margin"),
        ("phase_kernel32", "exact_score"),
        ("phase_kernel32", "control_score"),
    ],
)
def test_corrupted_later_confirmation_is_detected(metric, field):
    case, arrays = fixture()
    case = copy.deepcopy(case)
    item = case["evaluation"]["methods"]["segment8"]["common_confirmation"][metric]
    item["winner"][field] += 0.05
    result = audit.audit_bank(case, arrays)
    assert not result["passed"]
    assert result["max_absolute_errors"][f"later_{metric}_winner_{field}"] == pytest.approx(0.05)


@pytest.mark.parametrize("change", ["first_frames", "later_frames", "epoch", "id", "baseline"])
def test_identity_and_support_corruptions_fail(change):
    case, arrays = fixture()
    case = copy.deepcopy(case)
    item = case["evaluation"]["methods"]["segment8"]
    if change == "first_frames":
        item["first_frame_count"] += 1
    elif change == "later_frames":
        item["later_frame_count"] += 1
    elif change == "epoch":
        item["winner"]["epoch_sample"] += 1
    elif change == "id":
        item["winner"]["candidate_id"] = 1000
    elif change == "baseline":
        case["evaluation"]["baseline_winner"]["candidate_id"] = 1000
    with pytest.raises(ValueError):
        audit.audit_bank(case, arrays)


def test_embedded_frozen_hash_mismatch_detected():
    case, arrays = fixture()
    case["evaluation"]["frozen_scorer_sha256"] = "0" * 64
    result = audit.audit_bank(case, arrays)
    assert not result["passed"]
    assert not result["frozen_scorer_hash_matches"]


def test_directory_requires_complete_scan_receipts_and_preserves_failures(tmp_path):
    case, arrays = fixture()
    folder = tmp_path / "R01"
    folder.mkdir()
    path = folder / "audit-v000000-rx0.npz"
    np.savez_compressed(path, **arrays)
    path.with_suffix(".json").write_text(json.dumps(case))
    provisional = audit.audit_directory(tmp_path, expected_scans=1)
    assert provisional["passed"] and provisional["provisional"]
    assert not audit.audit_directory(tmp_path, expected_scans=1, require_complete=True)["passed"]
    (folder / "receipt.json").write_text(json.dumps(dict(status="complete")))
    complete = audit.audit_directory(tmp_path, expected_scans=1, require_complete=True)
    assert complete["passed"] and not complete["provisional"]
    assert complete["audited_banks"] == 1
    path.with_suffix(".json").unlink()
    failed = audit.audit_directory(tmp_path, expected_scans=1)
    assert not failed["passed"]
    assert len(failed["failures"]) == 1


def test_zero_direct_oracles_are_finite():
    zeros = np.zeros((2, 64), complex)
    assert audit.direct_gaussian(zeros, np.ones(64), 57000.0) == 0
    assert audit.direct_kernel(zeros, np.ones(64), 57000.0) == 0
