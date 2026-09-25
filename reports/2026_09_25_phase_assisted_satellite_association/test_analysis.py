import importlib.util
import json
from pathlib import Path

import numpy as np

MODULE_PATH = Path(__file__).with_name("analyze.py")
SPEC = importlib.util.spec_from_file_location("phase_assisted_association", MODULE_PATH)
assert SPEC and SPEC.loader
ANALYSIS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYSIS)


def test_zero_centered_phase_model_rewards_continuity() -> None:
    kappa = ANALYSIS.kappa_from_resultant(0.9109282200498481)

    assert 5.0 < kappa < 7.0
    assert ANALYSIS.von_mises_log_bayes_factor(np.radians([0.0]), kappa) > 0
    assert ANALYSIS.von_mises_log_bayes_factor(np.radians([180.0]), kappa) < 0


def test_persisted_phase_evidence_validates_pairing_but_not_tle_rank() -> None:
    result = json.loads(MODULE_PATH.with_name("results.json").read_text())

    assert result["method"]["phase_model"] == "zero-centered von Mises; no phase intercept"
    assert result["summary"]["track_count"] == 5
    assert result["summary"]["phase_validated_pair_count"] == 5
    assert result["summary"]["leader_change_count"] == 0
    assert result["summary"]["maximum_candidate_phase_log_likelihood_spread"] < 0.002
    assert all(row["phase_pairing_bayes_factor"] > 1.0 for row in result["tracks"])


def test_one_global_receiver_order_sign_is_used() -> None:
    result = json.loads(MODULE_PATH.with_name("results.json").read_text())

    assert result["method"]["receiver_order_sign_policy"] == "one global sign across all tracks"
    assert result["method"]["selected_receiver_order_sign"] in (-1, 1)
    assert result["summary"]["receiver_order_sign_score_difference"] < 0.001
