#!/usr/bin/env python3
"""Aggregate the recent-50 ramp-corrected Doppler and TLE-association evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DEFAULT_INPUTS = Path("reports/figures/2026_08_24_recent_50_doppler/inputs.json")
DEFAULT_RESULTS = Path("reports/figures/2026_08_24_recent_50_doppler/results")
DEFAULT_ASSOCIATIONS = Path(
    "reports/figures/2026_08_24_recent_50_doppler/ramp-tle-associations.json"
)
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_24_recent_50_doppler")
DEFAULT_REPORT = Path("reports/2026_08_24_recent_50_ramp_corrected_doppler.md")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--associations", type=Path, default=DEFAULT_ASSOCIATIONS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _result_path(root: Path, row: dict[str, Any]) -> Path:
    suffix = str(row["session_id"]).rsplit("-", 1)[-1]
    return root / f"{row['label']}-{suffix}.json"


def _best_id(model: dict[str, Any] | None) -> int | None:
    if not model or not model.get("best"):
        return None
    return int(model["best"]["catalog_number"])


def _identity_evidence(association: dict[str, Any]) -> dict[str, object]:
    primary_model = association["primary_models"]["bounded_200"]
    best = primary_model["ranked"][0]
    best_id = int(best["candidate"]["catalog_number"])
    sensitivity = association["association_sensitivity"]
    compared: list[int] = []
    for value in sensitivity["best_identity_by_rate_nuisance_model"].values():
        if value is not None:
            compared.append(int(value["catalog_number"]))
    broad_id = _best_id(sensitivity["broad_sky_control"])
    if broad_id is not None:
        compared.append(broad_id)
    for name in (
        "previous_complete_snapshot",
        "following_complete_snapshot_noncausal_sensitivity_only",
    ):
        value = sensitivity[name]
        identity = _best_id(value) if value.get("available") else None
        if identity is not None:
            compared.append(identity)
    for value in sensitivity["observer_site_provenance_stress"]["directions"]:
        identity = _best_id(value)
        if identity is not None:
            compared.append(identity)
    metrics = best["metrics"]
    constant = primary_model["constant_rate_null"]
    margin = primary_model["runner_up_train_standardized_margin"]
    compatible = metrics["holdout_standardized_rms"] <= 2.0
    beats_null = metrics["holdout_standardized_rms"] + 0.10 <= constant["holdout_standardized_rms"]
    separated = margin is not None and margin >= 0.25
    stable = bool(compared) and all(value == best_id for value in compared)
    nuisance_interior = not metrics["nuisance_at_bound"]
    supported = compatible and beats_null and separated and stable and nuisance_interior
    assessment = (
        "supported_candidate"
        if supported
        else "compatible_but_ambiguous"
        if compatible
        else "poor_heldout_fit"
    )
    return {
        "catalog_number": best_id,
        "object_name": best["candidate"]["object_name"],
        "assessment": assessment,
        "rate_compatible": compatible,
        "beats_constant_rate_null": beats_null,
        "runner_up_separated": separated,
        "identity_stable_across_sensitivities": stable,
        "rate_nuisance_interior": nuisance_interior,
        "sensitivity_comparison_count": len(compared),
        "sensitivity_identity_agreement_fraction": (
            sum(value == best_id for value in compared) / len(compared) if compared else None
        ),
    }


def load_rows(
    inputs_path: Path, results_root: Path, associations_path: Path
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    inputs = _load(inputs_path)
    source = tuple(inputs.get("dwells", ()))
    if inputs.get("selected_dwell_count") != 50 or len(source) != 50:
        raise ValueError("recent Doppler report requires the frozen 50-dwell cohort")
    association_document = _load(associations_path)
    by_identity = {
        (item.get("session_id"), item.get("label")): item
        for item in association_document.get("dwells", ())
    }
    if len(by_identity) != 50:
        raise ValueError("association evidence must account for all 50 frozen dwells")
    rows = []
    for item in source:
        result_path = _result_path(results_root, item)
        result = _load(result_path)
        if (
            result.get("session_id") != item["session_id"]
            or result.get("run_id") != item["run_id"]
            or result.get("analysis_manifest_digest") != item["analysis_manifest_digest"]
            or result.get("recording_manifest_digest") != item["recording_manifest_digest"]
        ):
            raise ValueError(f"raw result is not identity closed: {item['label']}")
        association = by_identity[(item["session_id"], item["label"])]
        row: dict[str, Any] = {
            "label": item["label"],
            "session_id": item["session_id"],
            "run_id": item["run_id"],
            "pipeline_release_id": item["pipeline_release_id"],
            "raw_result_path": str(result_path),
            "raw_result_digest": _digest(result_path),
            "raw_status": result.get("status"),
            "association_status": association.get("status"),
            "association_reason": association.get("reason"),
        }
        if result.get("status") == "complete":
            selected = result["selected"]
            diagnostics = selected["result"]["diagnostics"]
            ramp_slopes = np.asarray(
                [item["slope_hz_s"] for item in selected["result"]["ramps"]],
                dtype=float,
            )
            ramp_median = float(np.median(ramp_slopes))
            row.update(
                {
                    "selected_attempt_rank": result["selected_attempt_rank"],
                    "candidate_count": result["candidate_count"],
                    "stream_id": selected["candidate"]["stream_id"],
                    "receiver_id": selected["candidate"]["receiver_id"],
                    "branch_id": selected["candidate"]["branch_id"],
                    "glrt_rate_hz_s": diagnostics["overall_glrt_rate_hz_s"],
                    "glrt_sigma_hz_s": diagnostics["overall_glrt_rate_sigma_hz_s"],
                    "local_rate_hz_s": diagnostics["local_corrected_rate_hz_s"],
                    "local_conditional_sigma_hz_s": diagnostics["local_conditional_sigma_hz_s"],
                    "local_practical_sigma_hz_s": diagnostics["local_practical_sigma_hz_s"],
                    "local_p025_hz_s": diagnostics["local_p025_hz_s"],
                    "local_p975_hz_s": diagnostics["local_p975_hz_s"],
                    "rate_correction_hz_s": diagnostics["rate_correction_hz_s"],
                    "frame_count": diagnostics["frame_count"],
                    "qualified_frame_count": diagnostics["qualified_frame_count"],
                    "coherent_frame_count": diagnostics["coherent_frame_count"],
                    "ramp_count": diagnostics["ramp_count"],
                    "ramp_slope_standard_deviation_hz_s": float(np.std(ramp_slopes, ddof=1)),
                    "ramp_slope_mad_hz_s": 1.4826
                    * float(np.median(np.abs(ramp_slopes - ramp_median))),
                    "gate_spread_hz_s": diagnostics["strict_gate_rate_spread_hz_s"],
                    "odd_validation_reduction_percent": diagnostics[
                        "odd_validation_reduction_percent"
                    ],
                    "glrt_odd_validation_rms_hz": diagnostics["glrt_rate_errors"][
                        "validation_rms_hz"
                    ],
                    "local_odd_validation_rms_hz": diagnostics["local_rate_errors"][
                        "validation_rms_hz"
                    ],
                    "validation_frame_count": diagnostics["local_rate_errors"]["frame_count"],
                    "slope_progression_hz_s2": diagnostics["slope_progression_fit"][
                        "slope_progression_hz_s2"
                    ],
                    "slope_progression_sigma_hz_s2": diagnostics["slope_progression_fit"][
                        "slope_progression_sigma_hz_s2"
                    ],
                    "bic_progression_minus_common": diagnostics["bic_progression_minus_common"],
                }
            )
        if association.get("status") == "complete":
            primary = association["primary_models"]["bounded_200"]
            best = primary["ranked"][0]
            predicted = np.asarray(best["candidate"]["predicted_rate_hz_s"], dtype=float)
            error = association["best_candidate_error_budget"]
            row.update(
                {
                    "radio_id": association["radio_id"],
                    "tle_candidate_count": primary["candidate_count"],
                    "tle_best_catalog_number": best["candidate"]["catalog_number"],
                    "tle_best_object_name": best["candidate"]["object_name"],
                    "tle_best_mean_rate_hz_s": float(np.mean(predicted)),
                    "tle_fitted_rate_nuisance_hz_s": best["metrics"]["fitted_rate_nuisance_hz_s"],
                    "tle_fitted_rate_nuisance_abs_hz_s": abs(
                        best["metrics"]["fitted_rate_nuisance_hz_s"]
                    ),
                    "tle_train_standardized_rms": best["metrics"]["train_standardized_rms"],
                    "tle_holdout_standardized_rms": best["metrics"]["holdout_standardized_rms"],
                    "constant_null_holdout_standardized_rms": primary["constant_rate_null"][
                        "holdout_standardized_rms"
                    ],
                    "runner_up_train_standardized_margin": primary[
                        "runner_up_train_standardized_margin"
                    ],
                    "timing_rate_effect_rms_hz_s": error["timing_rate_effect_rms_hz_s"],
                    "site_50m_rate_effect_rms_hz_s": error["site_max_rate_rms_hz_s"],
                    "rf_scale_rate_effect_hz_s": error["rf_scale_max_rate_effect_hz_s"],
                    "finite_difference_rate_rms_hz_s": error["finite_difference_rate_rms_hz_s"],
                    "previous_tle_rate_rms_hz_s": (
                        error["previous_snapshot"].get("raw_rate_rms_hz_s")
                        if error["previous_snapshot"].get("available")
                        else None
                    ),
                    "previous_tle_shape_rms_hz_s": (
                        error["previous_snapshot"].get("constant_rate_nuisance_removed_rms_hz_s")
                        if error["previous_snapshot"].get("available")
                        else None
                    ),
                    "identity_evidence": _identity_evidence(association),
                }
            )
        rows.append(row)
    return association_document, tuple(rows)


def _pooled_rms(rows: tuple[dict[str, Any], ...], key: str) -> float:
    total = sum(float(row[key]) ** 2 * int(row["validation_frame_count"]) for row in rows)
    count = sum(int(row["validation_frame_count"]) for row in rows)
    return math.sqrt(total / count)


def _distribution(rows: tuple[dict[str, Any], ...], key: str) -> dict[str, float]:
    values = np.asarray([float(row[key]) for row in rows if row.get(key) is not None], dtype=float)
    return {
        "count": int(values.size),
        "median": float(np.median(values)),
        "p10": float(np.percentile(values, 10)),
        "p90": float(np.percentile(values, 90)),
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
    }


def aggregate(rows: tuple[dict[str, Any], ...]) -> dict[str, object]:
    radio = tuple(row for row in rows if row["raw_status"] == "complete")
    associations = tuple(row for row in radio if row["association_status"] == "complete")
    if not radio:
        raise ValueError("no complete raw-Doppler result is available")
    glrt_rms = _pooled_rms(radio, "glrt_odd_validation_rms_hz")
    local_rms = _pooled_rms(radio, "local_odd_validation_rms_hz")
    assessments = Counter(row["identity_evidence"]["assessment"] for row in associations)
    release_rows = {}
    for release in sorted({row["pipeline_release_id"] for row in radio}):
        subset = tuple(row for row in radio if row["pipeline_release_id"] == release)
        release_rows[release] = {
            "dwell_count": len(subset),
            "median_glrt_rate_hz_s": float(np.median([row["glrt_rate_hz_s"] for row in subset])),
            "median_local_rate_hz_s": float(np.median([row["local_rate_hz_s"] for row in subset])),
            "median_rate_correction_hz_s": float(
                np.median([row["rate_correction_hz_s"] for row in subset])
            ),
        }
    association_prefixes = (
        "timing_",
        "site_",
        "rf_",
        "finite_",
        "previous_",
        "tle_",
        "runner_",
        "constant_",
    )
    distributions = {
        key: _distribution(
            associations if key.startswith(association_prefixes) else radio,
            key,
        )
        for key in (
            "local_conditional_sigma_hz_s",
            "local_practical_sigma_hz_s",
            "gate_spread_hz_s",
            "ramp_slope_mad_hz_s",
            "rate_correction_hz_s",
            "local_odd_validation_rms_hz",
            "tle_fitted_rate_nuisance_hz_s",
            "tle_fitted_rate_nuisance_abs_hz_s",
            "tle_holdout_standardized_rms",
            "runner_up_train_standardized_margin",
            "timing_rate_effect_rms_hz_s",
            "site_50m_rate_effect_rms_hz_s",
            "rf_scale_rate_effect_hz_s",
            "finite_difference_rate_rms_hz_s",
            "previous_tle_rate_rms_hz_s",
            "previous_tle_shape_rms_hz_s",
        )
    }
    radio_rows = {}
    for radio_id in sorted({row["radio_id"] for row in associations}):
        subset = tuple(row for row in associations if row["radio_id"] == radio_id)
        radio_rows[radio_id] = {
            "dwell_count": len(subset),
            "median_rate_correction_hz_s": float(
                np.median([row["rate_correction_hz_s"] for row in subset])
            ),
            "median_fitted_rate_nuisance_hz_s": float(
                np.median([row["tle_fitted_rate_nuisance_hz_s"] for row in subset])
            ),
        }
    return {
        "dwell_count": len(rows),
        "raw_status_counts": dict(Counter(row["raw_status"] for row in rows)),
        "association_status_counts": dict(Counter(row["association_status"] for row in rows)),
        "selected_attempt_rank_counts": dict(
            Counter(str(row["selected_attempt_rank"]) for row in radio)
        ),
        "total_frame_count": sum(int(row["frame_count"]) for row in radio),
        "total_qualified_frame_count": sum(int(row["qualified_frame_count"]) for row in radio),
        "total_coherent_frame_count": sum(int(row["coherent_frame_count"]) for row in radio),
        "total_ramp_count": sum(int(row["ramp_count"]) for row in radio),
        "median_glrt_rate_hz_s": float(np.median([row["glrt_rate_hz_s"] for row in radio])),
        "median_local_rate_hz_s": float(np.median([row["local_rate_hz_s"] for row in radio])),
        "median_rate_correction_hz_s": float(
            np.median([row["rate_correction_hz_s"] for row in radio])
        ),
        "pooled_glrt_odd_validation_rms_hz": glrt_rms,
        "pooled_local_odd_validation_rms_hz": local_rms,
        "pooled_odd_validation_reduction_percent": 100.0 * (1.0 - local_rms / glrt_rms),
        "progression_bic_preferred_count": sum(
            float(row["bic_progression_minus_common"]) < 0.0 for row in radio
        ),
        "previous_tle_identical_rate_count": sum(
            row.get("previous_tle_rate_rms_hz_s") == 0.0 for row in associations
        ),
        "association_assessment_counts": dict(assessments),
        "release_strata": release_rows,
        "radio_strata": radio_rows,
        "distributions": distributions,
    }


def render_rate_figure(path: Path, rows: tuple[dict[str, Any], ...]) -> None:
    radio = tuple(row for row in rows if row["raw_status"] == "complete")
    x = np.arange(len(radio))
    glrt = np.asarray([row["glrt_rate_hz_s"] for row in radio]) / 1_000.0
    local = np.asarray([row["local_rate_hz_s"] for row in radio]) / 1_000.0
    low = np.asarray([row["local_p025_hz_s"] for row in radio]) / 1_000.0
    high = np.asarray([row["local_p975_hz_s"] for row in radio]) / 1_000.0
    fig, axes = plt.subplots(3, 1, figsize=(15.5, 10.5), sharex=True, constrained_layout=True)
    axes[0].plot(x, glrt, "o-", color="#6b7280", lw=1.0, ms=3.5, label="20 ms GLRT")
    axes[0].errorbar(
        x,
        local,
        yerr=np.vstack((local - low, high - local)),
        fmt="o-",
        color="#1676a3",
        ecolor="#7db7cf",
        lw=1.2,
        ms=3.5,
        capsize=2,
        label="ramp-corrected local rate (95% ramp bootstrap)",
    )
    axes[0].axhline(0.0, color="#1f2937", lw=0.8)
    axes[0].set_ylabel("CFO rate (kHz/s)")
    axes[0].set_title("A · Raw 20 ms GLRT rate versus reset-debiased Qin ramp rate")
    axes[0].legend(loc="best", ncol=2)

    correction = local - glrt
    axes[1].bar(x, correction, color="#d98c25", width=0.72)
    axes[1].axhline(0.0, color="#1f2937", lw=0.8)
    axes[1].set_ylabel("local − GLRT (kHz/s)")
    axes[1].set_title("B · Rate removed with the sawtooth/reset contribution")

    glrt_error = np.asarray([row["glrt_odd_validation_rms_hz"] for row in radio])
    local_error = np.asarray([row["local_odd_validation_rms_hz"] for row in radio])
    axes[2].plot(x, glrt_error, "o-", color="#6b7280", lw=1.0, ms=3.5, label="GLRT rate")
    axes[2].plot(x, local_error, "o-", color="#2f8a4f", lw=1.2, ms=3.5, label="local rate")
    axes[2].set_ylabel("held-out odd-Qin RMS (Hz)")
    axes[2].set_title("C · Independent odd-symbol validation")
    axes[2].set_xticks(x)
    axes[2].set_xticklabels([row["label"] for row in radio], rotation=90)
    axes[2].set_xlabel("frozen recent-dwell order (newest to oldest)")
    axes[2].legend(loc="best", ncol=2)
    for axis in axes:
        axis.grid(True, alpha=0.22)
    fig.suptitle("Recent 50 dwells · ramp compensation changes the Doppler-rate estimate")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def render_association_figure(path: Path, rows: tuple[dict[str, Any], ...]) -> None:
    selected = tuple(row for row in rows if row["association_status"] == "complete")
    x = np.arange(len(selected))
    fig, axes = plt.subplots(3, 1, figsize=(15.5, 11.5), sharex=True, constrained_layout=True)
    local = np.asarray([row["local_rate_hz_s"] for row in selected]) / 1_000.0
    geometric = np.asarray([row["tle_best_mean_rate_hz_s"] for row in selected]) / 1_000.0
    adjusted = (
        geometric + np.asarray([row["tle_fitted_rate_nuisance_hz_s"] for row in selected]) / 1_000.0
    )
    axes[0].plot(x, local, "o-", color="#1676a3", ms=3.5, lw=1.1, label="radio local rate")
    axes[0].plot(
        x,
        geometric,
        "^-",
        color="#2f8a4f",
        ms=3.5,
        lw=1.0,
        label="best-candidate geometric rate",
    )
    axes[0].plot(
        x,
        adjusted,
        ".-",
        color="#d98c25",
        ms=4,
        lw=1.0,
        label="candidate + fitted ≤200 Hz/s nuisance",
    )
    axes[0].set_ylabel("rate (kHz/s)")
    axes[0].set_title("A · Best candidate is a compatibility fit, not an identity claim")
    axes[0].legend(loc="best", ncol=3)

    best = np.asarray([row["tle_holdout_standardized_rms"] for row in selected])
    null = np.asarray([row["constant_null_holdout_standardized_rms"] for row in selected])
    axes[1].plot(x, null, "o-", color="#6b7280", ms=3.5, lw=1.0, label="constant-rate null")
    axes[1].plot(x, best, "o-", color="#7a4ca5", ms=3.5, lw=1.0, label="best TLE candidate")
    axes[1].axhline(2.0, color="#b74b46", ls="--", lw=1.0, label="2σ compatibility guide")
    axes[1].set_ylabel("held-out standardized RMS")
    axes[1].set_title("B · Chronological held-out comparison")
    axes[1].legend(loc="best", ncol=3)

    margin = np.asarray([row["runner_up_train_standardized_margin"] for row in selected])
    agreement = np.asarray(
        [row["identity_evidence"]["sensitivity_identity_agreement_fraction"] for row in selected]
    )
    axes[2].bar(x, margin, color="#d98c25", width=0.68, label="runner-up margin")
    secondary = axes[2].twinx()
    secondary.plot(x, agreement, "s-", color="#1676a3", ms=3.2, lw=1.0, label="identity agreement")
    axes[2].axhline(0.25, color="#b74b46", ls="--", lw=1.0)
    axes[2].set_ylabel("train standardized-RMS margin")
    secondary.set_ylabel("sensitivity identity agreement")
    secondary.set_ylim(-0.03, 1.03)
    axes[2].set_title("C · Candidate separation and stability across nuisance/TLE/site controls")
    axes[2].set_xticks(x)
    axes[2].set_xticklabels([row["label"] for row in selected], rotation=90)
    axes[2].set_xlabel("frozen recent-dwell order (newest to oldest)")
    handles_a, labels_a = axes[2].get_legend_handles_labels()
    handles_b, labels_b = secondary.get_legend_handles_labels()
    axes[2].legend(handles_a + handles_b, labels_a + labels_b, loc="best", ncol=2)
    for axis in axes:
        axis.grid(True, alpha=0.22)
    fig.suptitle("Recent 50 dwells · rate-space Starlink TLE association diagnostics")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def render_error_budget(path: Path, statistics: dict[str, Any]) -> None:
    keys = (
        ("finite_difference_rate_rms_hz_s", "numerical derivative"),
        ("site_50m_rate_effect_rms_hz_s", "observer ±50 m"),
        ("rf_scale_rate_effect_hz_s", "pilot RF half-width"),
        ("timing_rate_effect_rms_hz_s", "capture-time bracket"),
        ("previous_tle_shape_rms_hz_s", "previous TLE, nuisance removed"),
        ("previous_tle_rate_rms_hz_s", "previous TLE, raw rate"),
        ("local_conditional_sigma_hz_s", "conditional radio fit σ"),
        ("local_practical_sigma_hz_s", "whole-ramp bootstrap σ"),
        ("gate_spread_hz_s", "Qin-gate spread"),
        ("ramp_slope_mad_hz_s", "between-ramp slope MAD"),
        ("tle_fitted_rate_nuisance_abs_hz_s", "fitted drift nuisance magnitude"),
    )
    distributions = statistics["distributions"]
    medians = np.asarray([distributions[key]["median"] for key, _label in keys])
    lower = np.asarray([distributions[key]["p10"] for key, _label in keys])
    upper = np.asarray([distributions[key]["p90"] for key, _label in keys])
    y = np.arange(len(keys))
    fig, axis = plt.subplots(figsize=(12.5, 7.2), constrained_layout=True)
    axis.errorbar(
        medians,
        y,
        xerr=np.vstack((medians - lower, upper - medians)),
        fmt="o",
        color="#1676a3",
        ecolor="#7db7cf",
        capsize=3,
    )
    # Adjacent archive snapshots may contain byte-identical element sets and
    # therefore legitimately contribute exactly zero sensitivity.
    axis.set_xscale("symlog", linthresh=0.01)
    axis.set_yticks(y)
    axis.set_yticklabels([label for _key, label in keys])
    axis.set_xlabel("effect, scatter, or uncertainty (Hz/s)")
    axis.set_title("Estimated error terms · median and 10–90% across usable dwells")
    axis.grid(True, axis="x", which="both", alpha=0.25)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _number(value: object, digits: int = 2) -> str:
    return "—" if value is None else f"{float(value):.{digits}f}"


def write_report(
    path: Path,
    rows: tuple[dict[str, Any], ...],
    statistics: dict[str, Any],
    association_document: dict[str, Any],
    *,
    summary_path: Path,
    rate_figure: Path,
    association_figure: Path,
    error_figure: Path,
) -> None:
    raw_complete = statistics["raw_status_counts"].get("complete", 0)
    association_complete = statistics["association_status_counts"].get("complete", 0)
    assessments = statistics["association_assessment_counts"]
    error_specs = (
        ("finite_difference_rate_rms_hz_s", "Numerical Doppler derivative", "resolution"),
        ("rf_scale_rate_effect_hz_s", "Pilot RF half-width", "bounded scale"),
        ("timing_rate_effect_rms_hz_s", "Capture timing bracket", "bounded timing"),
        ("site_50m_rate_effect_rms_hz_s", "Observer ±50 m", "site sensitivity"),
        ("previous_tle_rate_rms_hz_s", "Previous TLE raw rate", "orbit proxy"),
        (
            "previous_tle_shape_rms_hz_s",
            "Previous TLE after rate nuisance",
            "orbit-shape proxy",
        ),
        ("local_conditional_sigma_hz_s", "Conditional shared-slope σ", "statistical"),
        ("local_practical_sigma_hz_s", "Whole-ramp bootstrap σ", "statistical"),
        ("gate_spread_hz_s", "Qin-gate spread", "selection sensitivity"),
        ("ramp_slope_mad_hz_s", "Between-ramp slope MAD", "heterogeneity"),
        (
            "tle_fitted_rate_nuisance_abs_hz_s",
            "Fitted rate-nuisance magnitude",
            "unresolved composite",
        ),
    )
    error_lines = [
        "| Term | Interpretation | Median Hz/s | 10–90% Hz/s |",
        "|---|---|---:|---:|",
    ]
    for key, label, interpretation in error_specs:
        values = statistics["distributions"][key]
        error_lines.append(
            f"| {label} | {interpretation} | {values['median']:.3f} | "
            f"[{values['p10']:.3f}, {values['p90']:.3f}] |"
        )
    radio_summary = "; ".join(
        f"`{radio_id}`: n={values['dwell_count']}, median fitted nuisance "
        f"{values['median_fitted_rate_nuisance_hz_s']:.1f} Hz/s"
        for radio_id, values in statistics["radio_strata"].items()
    )
    release_summary = "; ".join(
        f"`{release[:8]}`: n={values['dwell_count']}, median correction "
        f"{values['median_rate_correction_hz_s'] / 1_000.0:.3f} kHz/s"
        for release, values in statistics["release_strata"].items()
    )
    attempt_summary = ", ".join(
        f"rank {rank}: {count}"
        for rank, count in statistics["selected_attempt_rank_counts"].items()
    )
    no_track_labels = [row["label"] for row in rows if row["raw_status"] != "complete"]
    short_association_labels = [
        row["label"]
        for row in rows
        if row["raw_status"] == "complete" and row["association_status"] != "complete"
    ]
    lines = [
        "# Fifty recent dwells: ramp-corrected Doppler and Starlink TLE correlation",
        "",
        "## Abstract",
        "",
        (
            "We froze the newest 50 readable, successful Standard V4 dwells without "
            f"selecting on signal strength and re-read their raw IQ. {raw_complete}/50 "
            "produced a complete source-bound Qin ramp solution. The 20 ms GLRT rate "
            "and the reset-debiased local rate are not interchangeable: the median "
            f"correction was **{statistics['median_rate_correction_hz_s'] / 1_000.0:.3f} "
            "kHz/s**, and held-out odd-Qin RMS changed from "
            f"**{statistics['pooled_glrt_odd_validation_rms_hz']:.1f} Hz** to "
            f"**{statistics['pooled_local_odd_validation_rms_hz']:.1f} Hz** "
            f"({statistics['pooled_odd_validation_reduction_percent']:.1f}% reduction). "
            "We then compared per-ramp rates with causal SGP4 Starlink Doppler-rate "
            "curves in rate space, allowing one bounded ±200 Hz/s receiver/transmitter "
            "drift nuisance selected on the first 60% of ramps and evaluated on the "
            f"untouched last 40%. {association_complete}/50 had a geometric candidate "
            "set. The result is strong evidence that ramp correction is necessary, but "
            "satellite identity remains generally ambiguous: "
            f"**{assessments.get('supported_candidate', 0)}** candidates satisfy all "
            "exploratory separation, held-out, nuisance, and sensitivity checks; "
            f"**{assessments.get('compatible_but_ambiguous', 0)}** are rate-compatible "
            f"but ambiguous, and **{assessments.get('poor_heldout_fit', 0)}** have poor "
            "held-out fit for both discrimination and identity."
        ),
        "",
        "## Motivation and hypothesis",
        "",
        (
            "The persisted GLRT fits CFO across reset-bearing 20 ms probe windows. "
            "Qin-specific 1.333 ms frame CFOs reveal short frequency-continuous ramps "
            "separated by emitter/receiver resets. Our hypothesis was that a common "
            "within-ramp slope estimates the physical Doppler rate more faithfully than "
            "the cross-reset GLRT slope, and that the corrected slope progression could "
            "then be matched to TLE geometry despite an unknown absolute CFO and a "
            "smaller unknown rate drift."
        ),
        "",
        "## Data and provenance",
        "",
        (
            f"The cohort runs from `{rows[0]['session_id']}` (R01) through "
            f"`{rows[-1]['session_id']}` (R50), newest to oldest. Selection used "
            "successful Standard-lane V3 scan/V4 bank products, committed two-stream "
            "2.5 Msps recordings, and no RF-strength threshold. Inputs are digest-closed "
            f"in `{summary_path.parent / 'inputs.json'}`. The observer is the reviewed "
            f"Sausalito preset ({association_document['observer']['latitude_deg']}, "
            f"{association_document['observer']['longitude_deg']}, "
            f"{association_document['observer']['altitude_m']} m), but it is not "
            "capture-bound GPS authority; the association audit therefore includes "
            "±10 km cardinal stress tests."
        ),
        "",
        (
            "TLE selection is causal: the primary catalogue is the newest complete "
            "Space-Track snapshot collected at or before each capture. A 4,360-object "
            "snapshot was rejected by a predeclared 90%-of-maximum catalogue-"
            "completeness gate; accepted snapshots contain 10,975 Starlink objects. The "
            "prior complete snapshot and the next snapshot are sensitivity checks only; "
            "the next snapshot never selects the reported primary identity. The tool "
            f"records `{association_document['tle_authority_root']}` as the source "
            f"authority and read `{association_document['tle_root']}` for this run."
        ),
        "",
        "## Approach",
        "",
        (
            "1. Reacquire each persisted branch from its exact raw GLRT source "
            "observations, preserving its timing epoch and acquisition CFO."
        ),
        (
            "2. Fit each complete 1.333 ms Qin frame on even pilot symbols over a ±6 kHz "
            "residual grid; reserve odd pilot symbols for validation."
        ),
        (
            "3. Batch-partition frame locks into frequency-continuous 20–125 ms ramps, "
            "fit one intercept per ramp, and robustly estimate a shared slope. Bootstrap "
            "whole ramps, sweep the Qin gate, and compare with an optional linear slope "
            "progression."
        ),
        (
            "4. At every ramp center, propagate all causally available Starlink TLEs "
            "with SGP4, transform to the reviewed observer, differentiate predicted RF "
            "Doppler at 125 ms spacing, and retain both a ≥60° primary cone and ≥10° "
            "broad-sky control."
        ),
        (
            "5. Select satellite identity and a bounded constant rate nuisance using "
            "only the chronological first 60% of ramps. Report the last 40% unchanged, "
            "plus runner-up, nuisance-bound, broad-sky, adjacent-TLE, timing, RF-scale, "
            "numerical, and observer-location sensitivities."
        ),
        "",
        "## Results: radio Doppler",
        "",
        f"![GLRT and ramp-corrected Doppler]({rate_figure.relative_to(path.parent)})",
        "",
        (
            f"Across {raw_complete} complete dwells, "
            f"{statistics['total_coherent_frame_count']:,} frames formed "
            f"{statistics['total_ramp_count']:,} coherent ramps. The median GLRT rate "
            f"was {statistics['median_glrt_rate_hz_s'] / 1_000.0:.3f} kHz/s; the median "
            "reset-debiased rate was "
            f"{statistics['median_local_rate_hz_s'] / 1_000.0:.3f} kHz/s. A progression "
            f"term improved BIC in {statistics['progression_bic_preferred_count']}/"
            f"{raw_complete} dwells; it is retained as a diagnostic rather than forced "
            "into every estimate."
        ),
        "",
        (
            f"Selected-branch ranks were {attempt_summary}. Release strata were "
            f"{release_summary}. Those release groups occupy different capture times, "
            "so their median difference is reported as a control and is not attributed "
            "causally to software release."
        ),
        "",
        "## Results: TLE correlation",
        "",
        f"![TLE association diagnostics]({association_figure.relative_to(path.parent)})",
        "",
        (
            "The comparison occurs in Doppler-rate space (Hz/s), not absolute CFO. The "
            "fitted nuisance is also a rate: it absorbs a constant LNB/receiver/"
            "transmitter drift but is bounded to ±200 Hz/s in the primary model. "
            "Candidate ranking is often shallow, and the TLE curve frequently does not "
            "beat a radio-only constant-rate null on held-out ramps by a meaningful "
            "margin. Therefore every named object below is a candidate, not a decoded "
            "identity."
        ),
        "",
        (
            "The exploratory `supported_candidate` label requires all five checks: "
            "held-out standardized RMS ≤2.0; at least 0.10 lower than the constant-rate "
            "null; runner-up training separation ≥0.25; the same identity under bounded "
            "25/200 Hz/s and free nuisances, broad-sky, adjacent-TLE, and ±10 km site "
            "controls; and a primary nuisance strictly inside ±200 Hz/s. These criteria "
            "were used to prevent a nearest-rate candidate from becoming an identity "
            "claim."
        ),
        "",
        (
            f"Unmatched controls: {', '.join(no_track_labels)} have no Standard GLRT "
            f"branch; {', '.join(short_association_labels)} have a radio estimate but "
            "fewer than five ramps, so a 60/40 held-out association would be degenerate."
        ),
        "",
        f"Receiver-chain stratification: {radio_summary}.",
        "",
        "## Error budget",
        "",
        f"![Error budget]({error_figure.relative_to(path.parent)})",
        "",
        (
            "The plotted numerical, RF-scale, 50 m site, timing, and adjacent-TLE terms "
            "are estimable sensitivities. Whole-ramp bootstrap and Qin-gate spread "
            "characterize radio statistical/model-selection uncertainty. The ±10 km "
            "location audit is an identity stress test because the site preset is not "
            "capture-bound. Receiver/LNB drift, transmitter frequency-plan drift, and "
            "residual sample-clock drift are not separately identifiable from Doppler "
            "rate in these data; the bounded fitted nuisance is their combined apparent "
            "contribution, not an error bar on orbital Doppler. SGP4/TLE truth error is "
            "not calibrated by this corpus; adjacent-snapshot differences are only an "
            "empirical proxy. The zero median for the previous-TLE rows is literal: "
            f"{statistics['previous_tle_identical_rate_count']}/{association_complete} "
            "comparisons used consecutive archive snapshots containing identical "
            "element sets, so they provide no independent orbit-error sample."
        ),
        "",
        *error_lines,
        "",
        "## Per-dwell results",
        "",
        (
            "| Dwell | Capture ID | GLRT kHz/s | Local kHz/s | 95% local kHz/s | "
            "Ramps | Candidate | Assessment | Held-out σ-RMS | Runner margin |"
        ),
        "|---|---|---:|---:|---:|---:|---|---|---:|---:|",
    ]
    for row in rows:
        if row["raw_status"] != "complete":
            lines.append(
                f"| {row['label']} | `{row['session_id']}` | — | — | — | — | — | "
                f"`{row['raw_status']}` | — | — |"
            )
            continue
        identity = row.get("identity_evidence")
        candidate = (
            "—" if identity is None else f"{identity['object_name']} ({identity['catalog_number']})"
        )
        assessment = row["association_status"] if identity is None else identity["assessment"]
        lines.append(
            f"| {row['label']} | `{row['session_id']}` | "
            f"{row['glrt_rate_hz_s'] / 1_000.0:.3f} | "
            f"{row['local_rate_hz_s'] / 1_000.0:.3f} | "
            f"[{row['local_p025_hz_s'] / 1_000.0:.3f}, "
            f"{row['local_p975_hz_s'] / 1_000.0:.3f}] | {row['ramp_count']} | "
            f"{candidate} | {assessment} | "
            f"{_number(row.get('tle_holdout_standardized_rms'))} | "
            f"{_number(row.get('runner_up_train_standardized_margin'), 3)} |"
        )
    lines.extend(
        [
            "",
            "## Reproducibility products",
            "",
            f"- Frozen inputs: `{summary_path.parent / 'inputs.json'}`",
            f"- Per-dwell raw-IQ results: `{summary_path.parent / 'results'}`",
            f"- TLE association evidence: `{summary_path.parent / 'ramp-tle-associations.json'}`",
            f"- Aggregated machine-readable summary: `{summary_path}`",
            "",
            "## Conclusion",
            "",
            (
                "The robust computational observable is the common slope inside Qin-"
                "coherent ramps, with a free CFO intercept for every ramp. The 20 ms "
                "GLRT remains useful for branch discovery and raw-IQ reacquisition, but "
                "its cross-reset slope should not be called geometric Doppler. TLE "
                "matching should follow ramp correction and operate on the rate curve "
                "with explicit drift nuisance and held-out tests. With the present short "
                "tracks and non-capture-bound site provenance, the radio rate is "
                "substantially better determined than satellite identity."
            ),
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    association_document, rows = load_rows(
        arguments.inputs, arguments.results, arguments.associations
    )
    statistics = aggregate(rows)
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    summary_path = arguments.output_root / "cohort-summary.json"
    rate_figure = arguments.output_root / "recent-50-radio-rates.png"
    association_figure = arguments.output_root / "recent-50-tle-association.png"
    error_figure = arguments.output_root / "recent-50-error-budget.png"
    summary_path.write_text(
        json.dumps(
            {
                "schema": "org.leo.research.recent-50-doppler-summary/v1",
                "inputs_digest": _digest(arguments.inputs),
                "associations_digest": _digest(arguments.associations),
                "statistics": statistics,
                "dwells": rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    render_rate_figure(rate_figure, rows)
    render_association_figure(association_figure, rows)
    render_error_budget(error_figure, statistics)
    write_report(
        arguments.report,
        rows,
        statistics,
        association_document,
        summary_path=summary_path,
        rate_figure=rate_figure,
        association_figure=association_figure,
        error_figure=error_figure,
    )
    print(arguments.report)


if __name__ == "__main__":
    main()
