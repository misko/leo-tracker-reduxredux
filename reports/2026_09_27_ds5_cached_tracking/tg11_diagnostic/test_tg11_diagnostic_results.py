"""Receipt checks for the frozen TG11 point-scoring diagnostic."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def result():
    return json.loads((HERE / "results.json").read_text())


def test_result_is_complete_stable_bounded_and_diagnostic_only():
    value = result()
    assert value["status"] == "complete"
    assert value["source_lock_stable"]
    assert len(value["rows"]) == 2
    assert sum(len(row["coordinates"]) for row in value["rows"]) == 4
    assert not value["holdout_opened"]
    assert value["elapsed_seconds"] < 60
    assert all(row["input_immutable"] for row in value["rows"])


def test_extra_passes_both_point_scorers_but_application_search_misses_identity():
    interpretation = result()["interpretation"]
    extra = interpretation["extra"]
    assert extra["native_blind_pair_positive"]
    assert extra["native_integer_pair_positive"]
    assert extra["python_pair_positive"]
    assert not extra["application_search_has_matching_identity"]
    assert interpretation["conclusion"] == (
        "python_conditioned_score_passes_at_tg_coordinates_but_search_did_not_retain_them"
    )


def test_anchor_passes_and_was_retained_by_application_search():
    anchor = result()["interpretation"]["anchor"]
    assert anchor["native_blind_pair_positive"]
    assert anchor["native_integer_pair_positive"]
    assert anchor["python_pair_positive"]
    assert anchor["application_search_has_matching_identity"]


def test_support_reproduction_and_repetition_contracts():
    for row in result()["rows"]:
        for coordinate in row["coordinates"]:
            assert coordinate["blind_receipt_margin_delta"] == 0
            assert coordinate["blind_rerun"]["support_frames"] == 15
            assert coordinate["native_exact_fractional"]["support_frames"] == 15
            assert all(cell["support_frames"] == 15
                       for cell in coordinate["native_integer_cells"])
            assert all(cell["support_frames"] == 15
                       for cell in coordinate["python_integer_cells"])
            assert len(coordinate["timing_repetitions"]["native_exact_guided"]) == 3
            assert len(coordinate["timing_repetitions"]["python_nearest_integer"]) == 3


def test_source_lock_and_authoritative_receipt_are_unchanged():
    value = result()
    for name, expected in value["source_lock"]["files"].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected
    config = value["source_lock"]["config"]
    assert hashlib.sha256(
        (HERE.parent / "tg11/phase1_cost_results.json").read_bytes()
    ).hexdigest() == config["phase1_result_sha256"]
