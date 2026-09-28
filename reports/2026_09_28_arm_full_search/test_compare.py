import importlib.util
from pathlib import Path

import numpy as np

SPEC = importlib.util.spec_from_file_location("compare", Path(__file__).with_name("compare.py"))
compare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compare)


def candidate(epoch=10, cfo=100.0, margin=0.5):
    return {
        "coarse_epoch_sample": epoch,
        "coarse_residual_cfo_hz": 0.0,
        "refined_epoch_sample": epoch,
        "residual_cfo_hz": 0.0,
        "absolute_cfo_hz": cfo,
        "coarse_score": 0.1,
        "acquire_score": 0.2,
        "verify_score": 0.3,
        "conditioned_exact_score": 0.4,
        "conditioned_control_score": 0.01,
        "verify_minus_control_margin": 0.29,
        "frame_support": 2,
        "tracking_cfo_hz": cfo,
        "margin": margin,
    }


def native_from(reference):
    return {
        "coarse_epoch": reference["coarse_epoch_sample"],
        "coarse_bin": 5,
        "refined_epoch": reference["refined_epoch_sample"],
        "frame_support": reference["frame_support"],
        "glrt_complete": True,
        "coarse_cfo_hz": reference["coarse_residual_cfo_hz"],
        "fine_cfo_hz": 0.0,
        "conditioned_cfo_hz": reference["residual_cfo_hz"],
        "epoch": reference["refined_epoch_sample"],
        "acquired_cfo_hz": reference["absolute_cfo_hz"],
        "tracking_cfo_hz": reference["tracking_cfo_hz"],
        "exact_score": 0.6,
        "control_score": 0.1,
        "margin": 0.5,
        "acquire_score": reference["acquire_score"],
        "verify_score": reference["verify_score"],
        "verify_control_score": reference["conditioned_control_score"],
        "conditioned_score": reference["conditioned_exact_score"],
        "coarse_score": reference["coarse_score"],
    }


def final():
    return {"tracking_cfo_hz": 100.0, "exact_score": 0.6, "control_score": 0.1, "margin": 0.5}


def test_grid_reports_byte_exact_and_toleranced_parity(tmp_path):
    reference = tmp_path / "reference.f64"
    native = tmp_path / "native.f64"
    np.asarray([[1.0, 2.0]], dtype="<f8").tofile(reference)
    np.asarray([[1.0, 2.0 + 1e-12]], dtype="<f8").tofile(native)
    result = compare.compare_grid(reference, native, [1, 2])
    assert not result["byte_exact"]
    assert result["within_tolerance"]


def test_candidate_comparison_and_one_to_one_hits_are_separate():
    reference = candidate()
    result = compare.compare_candidate(native_from(reference), reference, final())
    assert result["exact"]
    assert result["within_tolerance"]
    metrics = compare.hit_metrics([reference], [native_from(reference)])
    assert metrics["matched_count"] == 1
    assert metrics["recall"] == 1.0
    assert metrics["precision"] == 1.0


def test_one_native_positive_cannot_recover_two_reference_hits():
    reference = candidate()
    metrics = compare.hit_metrics([reference, dict(reference)], [native_from(reference)])
    assert metrics["reference_positive_count"] == 2
    assert metrics["matched_count"] == 1
    assert metrics["missed_count"] == 1
    assert metrics["recall"] == 0.5


def test_negative_margin_is_not_credited_as_a_recovered_hit():
    reference = candidate()
    native = {**native_from(reference), "margin": 0.024999}
    metrics = compare.hit_metrics([reference], [native])
    assert metrics["native_positive_count"] == 0
    assert metrics["matched_count"] == 0
