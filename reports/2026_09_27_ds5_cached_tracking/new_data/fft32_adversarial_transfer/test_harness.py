from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def runner():
    spec = importlib.util.spec_from_file_location("fft32_adversarial_runner", HERE / "run_transfer.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_sources_and_complete_geometry() -> None:
    module = runner()
    lock = module.verify_source_lock()
    assert lock["stage"] == "frozen_before_outcomes"
    payload = module.load_json(module.CONTROL / "cases.json")
    design = module.load_json(module.CONTROL / "design.json")
    selected = module.select_cases(payload, design)
    assert len(selected) == 20
    assert {(case["rate_hz"], case["edge"]) for case, _ in selected} == {
        (2_500_000, "lower"),
        (2_500_000, "upper"),
        (5_000_000, "lower"),
        (5_000_000, "upper"),
    }
    for case, _ in selected:
        values = module.load_iq(case)
        assert values.shape == (case["rate_hz"] * 120 // 1000, 2, 2)


def test_reference_association_and_extra_are_independent_of_truth() -> None:
    module = runner()
    base = {
        "selected_window": 1,
        "rank_order": [1, 0, 2, 3, 4, 5],
        "projected_epoch_samples": [100] * 6,
        "rank_scores": [1.0, 0.9, 0.8, 0.7, 0.6, 0.5],
        "proposals": [
            {
                "window": 1,
                "epoch_samples": 100.0,
                "cfo_hz": 399000.0,
                "scoring_cfo_hz": 399000.0,
                "exact_score": 0.2,
                "control_score": 0.1,
                "margin": 0.1,
                "supported": True,
                "positive": True,
            }
        ],
        "positive": True,
    }
    same = json.loads(json.dumps(base))
    result = module.compare(base, same, 2_500_000)
    assert result["matched_positive_reference"] is True
    assert result["additional_candidate_positive"] is False
    same["proposals"][0]["cfo_hz"] += 9000
    result = module.compare(base, same, 2_500_000)
    assert result["matched_positive_reference"] is False
    assert result["lost_positive_reference"] is True
    assert result["additional_candidate_positive"] is True


def test_design_does_not_make_injected_presence_a_detector_label() -> None:
    design = json.loads((HERE / "design.json").read_text())
    assert design["constructed_truth"]["positive_semantics"] == (
        "injected pilot presence does not require a detector-positive result"
    )
    assert design["methods"]["calls_per_receiver_method"] == 1
    assert design["methods"]["automatic_fallback"] is False
