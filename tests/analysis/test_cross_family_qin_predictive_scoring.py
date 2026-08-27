from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from leo.analysis.research.cross_family_qin_predictive_scoring import (
    CrossFamilyQinPredictiveScoringResult,
    CrossFamilyQinScoringInputError,
    load_cross_family_qin_scoring_config,
    score_cross_family_qin_evidence,
)
from leo.contracts.digests import canonical_digest

PROJECT_ROOT = Path(__file__).parents[2]
CONFIG_PATH = PROJECT_ROOT / "config/analysis/satellite-pnt-cross-family-predictive-scoring-v1.json"


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


@pytest.fixture(scope="module")
def scored() -> CrossFamilyQinPredictiveScoringResult:
    config = load_cross_family_qin_scoring_config(CONFIG_PATH)
    return score_cross_family_qin_evidence(
        (PROJECT_ROOT / config.evidence_path).read_bytes(),
        (PROJECT_ROOT / config.protocol_path).read_bytes(),
        config,
    )


def test_frozen_paired_evidence_scores_all_truth_arms_without_a_gate(
    scored: CrossFamilyQinPredictiveScoringResult,
) -> None:
    assert scored.independent_background_pair_count == 3
    assert scored.truth_arm_count == 6
    assert len(scored.cases) == 6
    assert len(scored.leave_one_pair_out_diagnostics) == 6
    assert scored.correct_truth_arm_count == 3
    assert scored.tied_truth_arm_count == 0
    assert scored.truth_arm_equal_accuracy == 0.5
    assert scored.formal_95_percent_rank_pair_count_sufficient is False
    assert scored.catalogue_calibration.scenario_count == 3
    assert scored.radio_calibration.scenario_count == 3
    assert scored.threshold_fitted is False
    assert scored.posterior_odds_produced is False
    assert scored.full_catalogue_multiplicity_modeled is False
    assert scored.identity_claimed is False
    assert scored.positioning_validated is False


def test_result_digest_and_predictive_decompositions_close(
    scored: CrossFamilyQinPredictiveScoringResult,
) -> None:
    payload = asdict(scored)
    digest = payload.pop("result_digest")
    assert canonical_digest(payload) == digest
    assert digest == "sha256:e76b85d63b0a3567ebaf1f6a2f9fab98bc4db032d381e25cca6820a4cfdcf12a"

    for case in scored.cases:
        assert case.catalogue_fit.future_response_used_for_fit is False
        assert all(item.future_response_used_for_fit is False for item in case.radio_fits)
        assert tuple(item.degree for item in case.radio_fits) == (1, 2, 3)
        assert case.catalogue_fit.future_observation_count == len(
            case.audit.evaluation_observation_ids
        )
        for comparison in case.audit.comparisons:
            expected = (
                comparison.catalogue.residual_fit_negative_log_likelihood_component
                + comparison.catalogue.uncertainty_volume_negative_log_likelihood_component
                + comparison.catalogue.gaussian_normalization_negative_log_likelihood_component
            )
            assert comparison.catalogue.total_predictive_negative_log_likelihood == pytest.approx(
                expected, abs=1e-9
            )


def test_leave_one_pair_out_scales_exclude_the_scored_pair(
    scored: CrossFamilyQinPredictiveScoringResult,
) -> None:
    catalogue_scales = {
        item.scenario_id: item.leave_one_scenario_out_variance_scale
        for item in scored.catalogue_calibration.scenario_diagnostics
    }
    radio_scales = {
        item.scenario_id: item.leave_one_scenario_out_variance_scale
        for item in scored.radio_calibration.scenario_diagnostics
    }
    for item in scored.leave_one_pair_out_diagnostics:
        assert item.catalogue_variance_scale_from_other_pairs == catalogue_scales[item.scenario_id]
        assert item.radio_variance_scale_from_other_pairs == radio_scales[item.scenario_id]


def test_future_response_mutation_cannot_change_training_fits() -> None:
    config = load_cross_family_qin_scoring_config(CONFIG_PATH)
    original_bytes = (PROJECT_ROOT / config.evidence_path).read_bytes()
    protocol_bytes = (PROJECT_ROOT / config.protocol_path).read_bytes()
    original = score_cross_family_qin_evidence(original_bytes, protocol_bytes, config)
    mutated = json.loads(original_bytes)
    row = next(
        item
        for item in mutated["paired_evidence"][0]["orbit"]["observation_rows"]
        if item["split"] == "future-odd-qin" and item["usable"]
    )
    row["measured_cfo_hz"] += 100.0
    row["residual_hz"] += 100.0
    mutated_bytes = (json.dumps(mutated, sort_keys=True) + "\n").encode()
    mutated_config = replace(config, evidence_sha256=_sha256(mutated_bytes))

    changed = score_cross_family_qin_evidence(mutated_bytes, protocol_bytes, mutated_config)

    assert changed.cases[0].catalogue_fit.coefficients_hz == (
        original.cases[0].catalogue_fit.coefficients_hz
    )
    assert tuple(item.coefficients_hz for item in changed.cases[0].radio_fits) == tuple(
        item.coefficients_hz for item in original.cases[0].radio_fits
    )
    assert changed.cases[0].catalogue_fit.summary != original.cases[0].catalogue_fit.summary


def test_hash_partition_and_frame_inventory_poisons_fail_closed() -> None:
    config = load_cross_family_qin_scoring_config(CONFIG_PATH)
    evidence_bytes = (PROJECT_ROOT / config.evidence_path).read_bytes()
    protocol_bytes = (PROJECT_ROOT / config.protocol_path).read_bytes()
    with pytest.raises(CrossFamilyQinScoringInputError, match="evidence hash"):
        score_cross_family_qin_evidence(evidence_bytes + b" ", protocol_bytes, config)

    poisoned = json.loads(evidence_bytes)
    poisoned["paired_evidence"][0]["orbit"]["observation_rows"].pop()
    poisoned_bytes = (json.dumps(poisoned, sort_keys=True) + "\n").encode()
    poisoned_config = replace(config, evidence_sha256=_sha256(poisoned_bytes))
    with pytest.raises(CrossFamilyQinScoringInputError, match="frame count"):
        score_cross_family_qin_evidence(poisoned_bytes, protocol_bytes, poisoned_config)


def test_config_claim_or_model_mutation_is_rejected(tmp_path: Path) -> None:
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    raw["claims"]["threshold_fitted"] = True
    poisoned = tmp_path / "config.json"
    poisoned.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CrossFamilyQinScoringInputError, match="semantics"):
        load_cross_family_qin_scoring_config(poisoned)
