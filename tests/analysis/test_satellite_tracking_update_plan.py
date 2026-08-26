from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[2]
PLAN = ROOT / "satellite_tracking_update_plan.md"
FINAL_PROTOCOL = ROOT / "config/analysis/final-doppler-holdout-satellite-protocol-v3.json"
FINAL_SCORE = ROOT / "reports/figures/2026_08_26_final_doppler_holdout_attempt2-score.json"
FINAL_BIN_INVENTORY = (
    ROOT
    / "reports/figures/2026_08_26_final_doppler_holdout_attempt2"
    / "association-bin-inventory.json"
)
RETROSPECTIVE_PROTOCOL = ROOT / "config/analysis/retrospective-satellite-nuisance-protocol-v1.json"
RETROSPECTIVE_EVIDENCE = (
    ROOT
    / "reports/figures/2026_08_26_retrospective_satellite_nuisance"
    / "retrospective-satellite-nuisance-evidence.json"
)
LONG_ARC_REGISTRY = ROOT / "config/analysis/post-fix-long-arc-research-cohort-v1.json"
DATASET_POLICY = ROOT / "config/analysis/doppler-experiment-dataset-policy-v1.json"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _plain(text: str) -> str:
    text = re.sub(r"[`*_]", "", text)
    text = text.replace("≥", ">=").replace("≤", "<=").replace("±", "+/-")
    return " ".join(text.split()).lower()


def _table_row(text: str, label: str) -> list[str]:
    match = re.search(
        rf"^\|\s*{re.escape(label)}\s*\|(?P<cells>.*)\|\s*$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    assert match is not None, f"missing Markdown table row: {label}"
    return [cell.strip() for cell in match.group("cells").split("|")]


def _assert_pass_count(text: str, label: str, expected: str, *, cell: int) -> None:
    cells = _table_row(text, label)
    assert _plain(cells[cell]) == _plain(expected), (label, cells[cell], expected)


def _assert_requirement(text: str, label: str, expected: str) -> None:
    cells = _table_row(text, label)
    assert _plain(cells[0]) == _plain(expected), (label, cells[0], expected)


def _number_forms(value: int) -> set[str]:
    words = {
        0: "zero",
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
        9: "nine",
        10: "ten",
        20: "twenty",
        40: "forty",
    }
    return {str(value), words[value]} if value in words else {str(value)}


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _condition_pass_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    keys = set(rows[0]["gate"]["conditions"])
    assert all(set(row["gate"]["conditions"]) == keys for row in rows)
    return {key: sum(bool(row["gate"]["conditions"][key]) for row in rows) for key in keys}


def test_satellite_tracking_update_plan_links_and_current_decisions() -> None:
    text = PLAN.read_text(encoding="utf-8")
    plain = _plain(text)
    targets = re.findall(r"\]\(([^)#]+)(?:#[^)]+)?\)", text)

    assert targets
    assert all((PLAN.parent / target).resolve().is_file() for target in targets)

    required = (
        "status: living working plan",
        "8/8 response tracks were recovered",
        "tau in [-5,+5] s",
        "-500 s and +500 s",
        "no p-value",
        "forty-field far-time empirical rank",
        "superseded prospectively",
        "does not launch any stage",
    )
    assert all(item in plain for item in required)
    assert "observe only" in plain or "observe-only" in plain


def test_final_v3_gate_inventory_is_derived_from_sealed_artifacts() -> None:
    text = PLAN.read_text(encoding="utf-8")
    plain = _plain(text)
    protocol = _load_json(FINAL_PROTOCOL)
    score = _load_json(FINAL_SCORE)
    inventory = _load_json(FINAL_BIN_INVENTORY)

    associations = score["association"]
    evaluable = [row for row in associations if row["evaluable"]]
    total_count = int(protocol["selector_v2"]["capture_count"])
    assert len(associations) == total_count
    assert len(inventory["inventories"]) == total_count
    _assert_pass_count(
        text,
        "Association-evaluable captures",
        f"{len(evaluable)}/{total_count}",
        cell=1,
    )

    association = protocol["association"]
    minimum_total = int(association["minimum_total_bins"])
    minimum_training = int(association["minimum_training_bins"])
    minimum_evaluation = int(association["minimum_evaluation_bins"])
    _assert_requirement(
        text,
        "Association-evaluable captures",
        (
            f"both predictors and >={minimum_total} total / "
            f">={minimum_training} training / >={minimum_evaluation} evaluation bins"
        ),
    )

    score_by_session = {row["session_id"]: row for row in associations}
    inventory_by_session = {row["session_id"]: row for row in inventory["inventories"]}
    assert set(score_by_session) == set(inventory_by_session)
    for session_id, row in inventory_by_session.items():
        bins = row["bins"]
        training_count = sum(bin_row["split"] == "training" for bin_row in bins)
        evaluation_count = sum(bin_row["split"] == "evaluation" for bin_row in bins)
        predictors_finite = all(
            _is_finite_number(bin_row["primary_cfo_hz"])
            and _is_finite_number(bin_row["baseline_cfo_hz"])
            for bin_row in bins
        )
        expected_evaluable = (
            predictors_finite
            and len(bins) >= minimum_total
            and training_count >= minimum_training
            and evaluation_count >= minimum_evaluation
        )
        assert bool(row["evaluable"]) is expected_evaluable
        assert bool(score_by_session[session_id]["evaluable"]) is expected_evaluable

    nonevaluable = [row for row in inventory["inventories"] if not row["evaluable"]]
    assert len(nonevaluable) == total_count - len(evaluable)
    for row in nonevaluable:
        session_id = str(row["session_id"])
        capture_time = re.search(r"T(?P<time>\d{6})-", session_id)
        assert capture_time is not None
        short_id = capture_time.group("time")
        start = plain.index(short_id)
        summary = plain[start : plain.index(".", start)]
        for reason in row["failure_reasons"]:
            support_kind = reason.removeprefix("insufficient_").removesuffix("_bins")
            assert support_kind.replace("_", " ") in summary

    minimum_recovery_bins = int(association["minimum_evaluation_bins"])
    minimum_recovery_fraction = float(association["minimum_heldout_odd_bin_fraction"])
    minimum_candidates = int(association["minimum_visible_candidates"])
    _assert_requirement(
        text,
        "Recovered track",
        (
            f">={minimum_recovery_bins} finite evaluation bins, "
            f">={minimum_recovery_fraction:.0%}, >={minimum_candidates} candidates, "
            "all candidate scores finite"
        ),
    )
    assert f">={minimum_candidates} visible candidates" in plain

    counts = _condition_pass_counts(evaluable)
    labels = {
        "recovered_track": "Recovered track",
        "minimum_heldout_odd_bins": "Minimum future bins",
        "minimum_heldout_odd_bin_fraction": "Future-bin availability",
        "absolute_rank_one_heldout_odd_rms": "Rank-one future RMS",
        "primary_baseline_rank_one_agreement": "Primary/baseline rank-one agreement",
        "training_runner_margin_ratio": "Training runner ratio",
        "heldout_rank_one_remains_best": "Training winner remains best held out",
        "heldout_runner_margin_ratio": "Future runner ratio",
        "wrong_time_minimum_scored": "Historical wrong-time fields scored",
        "required_permutations_scored": "All 20 permutations scored",
        "permutation_empirical_p": "Permutation empirical rank",
        "at_least_2_rolling_origins_complete_and_stable": ("At least two stable rolling origins"),
        "utc_site_predecessor_controls_complete_and_stable": ("UTC/site/predecessor controls"),
        "wrong_time_empirical_p": "Forty-field far-time empirical rank",
    }
    assert set(counts) == set(labels)
    for key, label in labels.items():
        _assert_pass_count(text, label, f"{counts[key]}/{len(evaluable)}", cell=1)

    thresholds = score["association_thresholds"]
    assert thresholds == {
        "heldout_runner_margin_ratio_minimum": association["heldout_runner_margin_ratio_minimum"],
        "maximum_claim_rank_one_heldout_odd_rms_hz": association[
            "maximum_claim_rank_one_heldout_odd_rms_hz"
        ],
        "minimum_claim_heldout_odd_bins": association["minimum_claim_heldout_odd_bins"],
        "minimum_heldout_odd_bin_fraction": association["minimum_heldout_odd_bin_fraction"],
        "minimum_stable_rolling_origins": association["minimum_stable_rolling_origins"],
        "null_empirical_p_maximum": association["null_empirical_p_maximum"],
        "training_runner_margin_ratio_minimum": association["training_runner_margin_ratio_minimum"],
        "wrong_time_minimum_scored": association["wrong_time_minimum_scored"],
    }
    final_requirements = {
        "Minimum future bins": f"at least {thresholds['minimum_claim_heldout_odd_bins']}",
        "Future-bin availability": (
            f"at least {float(thresholds['minimum_heldout_odd_bin_fraction']):.0%}"
        ),
        "Rank-one future RMS": (
            f"at most {float(thresholds['maximum_claim_rank_one_heldout_odd_rms_hz']):g} Hz"
        ),
        "Primary/baseline rank-one agreement": "same NORAD",
        "Training runner ratio": (
            f"at least {float(thresholds['training_runner_margin_ratio_minimum']):.2f}"
        ),
        "Training winner remains best held out": "required",
        "Future runner ratio": (
            f"at least {float(thresholds['heldout_runner_margin_ratio_minimum']):.2f}"
        ),
        "Historical wrong-time fields scored": (
            f"at least {thresholds['wrong_time_minimum_scored']} of "
            f"{len(association['wrong_time_offsets_s'])}"
        ),
        "All 20 permutations scored": "required",
        "Permutation empirical rank": (
            f"at most {float(thresholds['null_empirical_p_maximum']):g}"
        ),
        "At least two stable rolling origins": "required",
        "UTC/site/predecessor controls": "complete and same ID",
        "Forty-field far-time empirical rank": (
            f"at most {float(thresholds['null_empirical_p_maximum']):g}"
        ),
    }
    for label, requirement in final_requirements.items():
        _assert_requirement(text, label, requirement)

    compatible = sum(bool(row["gate"]["catalog_compatible"]) for row in evaluable)
    _assert_pass_count(
        text,
        "Complete catalogue compatibility",
        f"{compatible}/{len(evaluable)}",
        cell=1,
    )
    assert score["absolute_secure_norad"] is False
    _assert_pass_count(text, "Absolute secure NORAD", "0", cell=1)
    _assert_requirement(text, "Complete catalogue compatibility", "every frozen condition")
    _assert_requirement(text, "Absolute secure NORAD", "permitted and supported")


def test_retrospective_gates_support_provenance_and_recurrence_are_derived() -> None:
    text = PLAN.read_text(encoding="utf-8")
    plain = _plain(text)
    protocol = _load_json(RETROSPECTIVE_PROTOCOL)
    evidence = _load_json(RETROSPECTIVE_EVIDENCE)
    primary = [row for row in evidence["bundle_results"] if row["primary"]]
    denominator = len(primary)
    assert denominator == int(evidence["aggregate"]["unique_primary_capture_count"])
    assert {row["capture_id"] for row in primary} == set(
        protocol["authority"]["required_capture_ids"]
    )

    support_count = sum(bool(row["support_gate_pass"]) for row in primary)
    _assert_pass_count(
        text,
        "Primary support",
        f"{support_count}/{denominator}",
        cell=0,
    )

    baseline_recovered = sum(bool(row["baseline_recovered_track"]) for row in primary)
    primary_recovered = sum(bool(row["primary_recovered_track"]) for row in primary)
    assert baseline_recovered == int(evidence["aggregate"]["baseline_recovered_track_count"])
    assert primary_recovered == int(evidence["aggregate"]["primary_recovered_track_count"])
    assert baseline_recovered == primary_recovered
    _assert_pass_count(
        text,
        "Recovered baseline and hierarchy catalogue banks",
        f"{primary_recovered}/{denominator}",
        cell=0,
    )

    promotion = protocol["promotion_gates"]
    candidate_conditions = promotion["candidate_evidence"]
    assert len(candidate_conditions) == 9
    rms_limit = float(re.search(r"<=\s*([0-9.]+) Hz", candidate_conditions[0]).group(1))
    quadratic_advantage = float(
        re.search(r"at least ([0-9.]+) Hz", candidate_conditions[1]).group(1)
    )
    training_gap = float(re.search(r">=\s*([0-9.]+) Hz", candidate_conditions[2]).group(1))
    future_gap = float(re.search(r">=\s*([0-9.]+) Hz", candidate_conditions[3]).group(1))
    rolling_count = len(protocol["evaluation"]["rolling_origins"])
    time_model = protocol["models"]["bounded_clock_time_sensitivity"]
    assert abs(float(time_model["minimum_shift_s"])) == float(time_model["maximum_shift_s"])
    time_limit = float(time_model["maximum_shift_s"])
    wrong_time_count = len(protocol["evaluation"]["wrong_time_offsets_s"])
    permutation_count = int(protocol["evaluation"]["permutation_count"])
    rolling_word = next(iter(_number_forms(rolling_count) - {str(rolling_count)}))
    permutation_word = next(iter(_number_forms(permutation_count) - {str(permutation_count)}))
    gate_labels = {
        "heldout_rms_le_100_hz": f"Hierarchy future RMS at most {rms_limit:g} Hz",
        "quadratic_advantage_ge_20_hz": (
            f"TLE beats quadratic radio null by at least {quadratic_advantage:g} Hz"
        ),
        "training_runner_margin_ge_100_hz": (f"Training runner gap at least {training_gap:g} Hz"),
        "heldout_runner_margin_ge_50_hz": f"Future runner gap at least {future_gap:g} Hz",
        "baseline_and_hierarchy_winner_agree": "Baseline/hierarchy winner agreement",
        "rolling_winner_stable": f"All {rolling_word} rolling origins preserve the winner",
        "bounded_time_winner_stable_and_interior": (
            f"Old `+/-{time_limit:g} s` sensitivity keeps the winner and is interior"
        ),
        "wrong_time_fwer_le_0_05": f"Historical {wrong_time_count}-field wrong-time rank",
        "permutation_p_le_0_05": (f"{permutation_word.title()}-permutation temporal-order control"),
    }
    assert all(set(row["candidate_evidence_gates"]) == set(gate_labels) for row in primary)
    for key, label in gate_labels.items():
        passed = sum(bool(row["candidate_evidence_gates"][key]) for row in primary)
        _assert_pass_count(text, label, f"{passed}/{denominator}", cell=0)

    candidate_passes = sum(bool(row["candidate_evidence_pass"]) for row in primary)
    provenance_passes = sum(bool(row["secure_provenance_pass"]) for row in primary)
    secure_capture_passes = sum(bool(row["secure_capture_pass"]) for row in primary)
    _assert_pass_count(
        text,
        "Complete candidate-evidence gate",
        f"{candidate_passes}/{denominator}",
        cell=0,
    )
    _assert_pass_count(
        text,
        "Secure provenance",
        f"{provenance_passes}/{denominator}",
        cell=0,
    )
    _assert_pass_count(
        text,
        "Secure capture",
        f"{secure_capture_passes}/{denominator}",
        cell=0,
    )

    secure_norad_count = int(evidence["aggregate"]["secure_norad_count"])
    assert secure_norad_count == sum(bool(row["secure_norad"]) for row in evidence["recurrence"])
    _assert_pass_count(text, "Independent recurrence", str(secure_norad_count), cell=0)
    _assert_pass_count(text, "Secure NORAD", str(secure_norad_count), cell=0)
    recurrence_rule = next(
        rule for rule in promotion["secure_norad"] if "independent capture_session_ids" in rule
    )
    assert "at least two independent capture_session_ids" in recurrence_rule
    assert "at least 2 independent capture" in plain or ">=2 independent capture" in plain

    reduction = protocol["measurement_reduction"]
    support_summary = _plain(" ".join(_table_row(text, "Primary support")))
    required_support_phrases = {
        f">={reduction['multi_radio_minimum_paths']} paths",
        f">={reduction['multi_radio_minimum_physical_radios']} physical radios",
        f">={reduction['multi_radio_minimum_training_bins_per_path']} training",
        f">={reduction['multi_radio_minimum_evaluation_bins_per_path']} evaluation bins",
        f">={reduction['long_track_minimum_total_bins']} total bins",
    }
    assert all(phrase in support_summary for phrase in required_support_phrases)

    provenance_keys = set().union(*(row["secure_provenance_gates"] for row in primary))
    assert provenance_keys == {
        "latest_causal_tle_source_sensitivity_pass",
        "observer_preset_binding_resolves",
        "path_and_radio_identity_valid",
        "rf_frequency_finite_and_positive",
        "tle_digest_verified_and_strictly_pre_measurement",
        "winner_nuisance_rate_strictly_interior",
    }
    provenance_summary = _plain(" ".join(_table_row(text, "Secure provenance")))
    assert all(
        phrase in provenance_summary
        for phrase in ("causal tle", "observer", "rf", "path/radio identity", "nuisance-bound")
    )


def test_long_arc_spans_roles_and_injection_restriction_come_from_authorities() -> None:
    text = PLAN.read_text(encoding="utf-8")
    plain = _plain(text)
    registry = _load_json(LONG_ARC_REGISTRY)
    policy = _load_json(DATASET_POLICY)

    arcs = registry["arcs"]
    authority = registry["authority"]
    assert len(arcs) == int(authority["expected_arc_count"])
    role_name = str(authority["parent_experiment_role"])
    role = policy["roles"][role_name]
    assert role_name in text
    assert authority["status"] == "opened-development-only"
    assert authority["deny_by_default"] is True

    role_captures = set(role["capture_ids"])
    for arc in arcs:
        session_id = str(arc["provenance"]["session_id"])
        span = arc["span"]
        path = arc["path"]
        assert session_id in role_captures
        assert arc["provenance"]["opened_status"] == "opened-development-only"
        assert arc["research_status"]["holdout_authority"] is False
        assert arc["research_status"]["secure_identity_authority"] is False
        assert session_id in text
        assert f"RX{int(path['receiver_id'])} {path['edge']}" in text
        assert f"[{int(span['sample_start']):,},{int(span['sample_stop_exclusive']):,})" in text
        assert f"{float(span['duration_s']):.3f} seconds" in text

    injection = policy["roles"]["polynomial_injection"]
    assert len(injection["capture_ids"]) == int(injection["expected_capture_count"])
    restriction = next(
        item
        for item in injection["selection_constraints"]
        if "separately reviewed policy revision" in item
    )
    assert _plain(restriction) in plain
    injection_count = int(injection["expected_capture_count"])
    assert any(
        f"exact {form} authorized hard-null captures" in plain
        for form in _number_forms(injection_count)
    )
    freeze_rule = next(
        item
        for item in injection["selection_constraints"]
        if "synthetic seeds and injected truth" in item
    )
    assert "response-free model/truth protocol freezes" in plain
    assert all(term in plain for term in ("seeds", "truth", "scoring"))
    assert "held-background scoring" in freeze_rule
    stage_1b = _table_row(text, "1B")
    assert _plain(stage_1b[-1]) == "not started"
    assert "tle-derived synthetic signals" in _plain(" ".join(stage_1b))
    assert "it becomes blocked if it needs an active real background" in plain


def test_satellite_tracking_update_plan_preserves_data_and_claim_boundaries() -> None:
    text = PLAN.read_text(encoding="utf-8")

    required = (
        "Any newer, ongoing, unlisted, PRE-FIX, or CAPTURE_ONLY input",
        "**Forbidden** until a reviewed policy revision explicitly admits it",
        "Do not promote either opened long-arc candidate to a secure identity",
        "Do not collect new RF under authority of this plan",
        "This plan never authorizes data access, data collection, dataset discovery",
    )
    assert all(item in text for item in required)
