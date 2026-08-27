from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from leo.analysis.research.cross_family_qin_predictive_scoring import (
    load_cross_family_qin_scoring_config,
    score_cross_family_qin_evidence,
)
from leo.contracts.digests import canonical_digest

PROJECT_ROOT = Path(__file__).parents[2]
RESULT = (
    PROJECT_ROOT
    / "reports/figures/2026_08_27_satellite_pnt_cross_family_predictive_scoring_v1.json"
)
REPORT = PROJECT_ROOT / "reports/2026_08_27_satellite_pnt_cross_family_predictive_scoring.md"
CONFIG = PROJECT_ROOT / "config/analysis/satellite-pnt-cross-family-predictive-scoring-v1.json"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_persisted_predictive_result_and_report_close() -> None:
    wrapper = _load(RESULT)
    result = wrapper["result"]
    execution = wrapper["execution"]
    payload = dict(result)
    digest = payload.pop("result_digest")

    assert wrapper["schema"] == ("org.leo.research.satellite-pnt-cross-family-predictive-result/v1")
    assert canonical_digest(payload) == digest
    assert digest == "sha256:e76b85d63b0a3567ebaf1f6a2f9fab98bc4db032d381e25cca6820a4cfdcf12a"
    assert _sha256(RESULT) == (
        "sha256:6ffcad950e0f1f79202b2538a6cca754f3691da0c1671a345b0d7a7a0e3c3b9e"
    )
    assert _sha256(REPORT) == execution["report_sha256"]
    assert execution["repository_head"] == "c2dd22e94ac14d919c907d25263b986600af26a3"
    assert execution["repository_tree"] == "3374272eccf519b8d39eb931490127ee83158d7c"
    assert execution["new_iq_read"] is False
    assert execution["new_rf_collection"] is False


def test_persisted_result_matches_recomputation_and_retains_claim_boundary() -> None:
    wrapper = _load(RESULT)
    persisted = wrapper["result"]
    config = load_cross_family_qin_scoring_config(CONFIG)
    recomputed = score_cross_family_qin_evidence(
        (PROJECT_ROOT / config.evidence_path).read_bytes(),
        (PROJECT_ROOT / config.protocol_path).read_bytes(),
        config,
    )

    assert persisted["result_digest"] == recomputed.result_digest
    assert persisted["correct_truth_arm_count"] == 3
    assert persisted["truth_arm_count"] == 6
    assert persisted["truth_arm_equal_accuracy"] == 0.5
    assert persisted["formal_95_percent_rank_pair_count_sufficient"] is False
    assert persisted["threshold_fitted"] is False
    assert persisted["posterior_odds_produced"] is False
    assert persisted["full_catalogue_multiplicity_modeled"] is False
    assert persisted["identity_claimed"] is False
    assert persisted["positioning_validated"] is False
    assert len(persisted["cases"]) == 6
    assert len(persisted["leave_one_pair_out_diagnostics"]) == 6
