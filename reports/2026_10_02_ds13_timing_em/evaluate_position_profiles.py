"""Evaluate fixed-position profile grids without refitting bootstrap samples."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from prepare_scans import ROOT


SESSIONS = (
    "scan-fw-911c4e5db9243281",
    "scan-fw-ffa1cc19d8d7c09f",
)
BLOCK_LENGTHS_S = (5.0, 15.0, 30.0)
DEFAULT_DRAWS = 500
OUTPUT_DIR = ROOT / "position-profile-evaluation"
DEFAULT_INPUT_DIR = ROOT / "position-profile-grid"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot_files(paths):
    snapshot = {}
    for raw_path in paths:
        path = Path(raw_path).resolve()
        key = str(path)
        if key in snapshot:
            raise ValueError(f"duplicate provenance path {key}")
        snapshot[key] = digest(path)
    return snapshot


def assert_snapshot_unchanged(snapshot):
    changed = [path for path, expected in snapshot.items()
               if not Path(path).is_file() or digest(path) != expected]
    if changed:
        raise RuntimeError(f"source provenance mismatch: {', '.join(changed)}")


def _finite_scalar(value, name):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _best(position):
    best = position.get("best")
    if not isinstance(best, dict):
        raise ValueError(f"position {position.get('label')!r} has no retained best attempt")
    return best


def _group_arrays(record, position):
    best = _best(position)
    group_values = best.get("group_values", record.get("group_values"))
    group_times = best.get("group_time_s", record.get("group_time_s"))
    log_likelihood = best.get("group_log_likelihood")
    if group_values is None or group_times is None or log_likelihood is None:
        raise ValueError(
            f"position {position.get('label')!r} lacks aligned group values, times, or likelihoods"
        )
    group_values = np.asarray(group_values)
    group_times = np.asarray(group_times, dtype=float)
    log_likelihood = np.asarray(log_likelihood, dtype=float)
    if group_values.ndim != 1 or group_times.ndim != 1 or log_likelihood.ndim != 1:
        raise ValueError("group evidence arrays must be one-dimensional")
    if not (len(group_values) == len(group_times) == len(log_likelihood)):
        raise ValueError("group values, times, and likelihoods must align")
    if len(group_values) == 0 or not np.all(np.isfinite(group_times)):
        raise ValueError("group times must be finite and nonempty")
    if not np.all(np.isfinite(log_likelihood)):
        raise ValueError("group log likelihoods must be finite")
    return group_values, group_times, log_likelihood


def _timing_prior(best):
    if "timing_prior_objective" in best:
        return _finite_scalar(best["timing_prior_objective"], "timing prior")
    if "nuisance_prior_nll" in best:
        return _finite_scalar(best["nuisance_prior_nll"], "timing prior")
    return _finite_scalar(best["prior_objective"], "timing prior")


def _total_nll(best):
    if "total_nll" in best:
        return _finite_scalar(best["total_nll"], "total NLL")
    return _finite_scalar(best["objective"], "total NLL")


def validate_profile_record(record, protocol, expected_session=None):
    schema = record.get("schema")
    if not isinstance(schema, str) or not schema.startswith("ds13-"):
        raise ValueError("position-profile input must have a DS13 schema identifier")
    session = record.get("session")
    if expected_session is not None and session != expected_session:
        raise ValueError(f"profile session {session!r} does not match {expected_session!r}")
    if session not in protocol["sessions"]:
        raise ValueError(f"profile session {session!r} is outside the frozen protocol")
    if float(record["sigma_hz"]) != float(protocol["control"]["sigma_hz"]):
        raise ValueError("profile sigma differs from the frozen protocol")
    positions = record.get("positions")
    if not isinstance(positions, list) or not positions:
        raise ValueError("profile has no retained positions")
    labels = [position.get("label") for position in positions]
    if any(not isinstance(label, str) or not label for label in labels):
        raise ValueError("every retained position needs a label")
    if len(set(labels)) != len(labels):
        raise ValueError("position labels must be unique")
    truth = [position for position in positions
             if position.get("kind") in {"truth", "reference"}
             or position.get("label") in {"truth", "reference"}]
    if len(truth) != 1:
        raise ValueError("profile must retain exactly one truth/reference position")
    reference_values, reference_times, _ = _group_arrays(record, truth[0])
    for position in positions:
        best = _best(position)
        values, times, log_likelihood = _group_arrays(record, position)
        if not np.array_equal(values, reference_values):
            raise ValueError("all positions must use the same ordered group values")
        if not np.array_equal(times, reference_times):
            raise ValueError("all positions must use the same group receive times")
        data_nll = _finite_scalar(best["data_nll"], "data NLL")
        prior = _timing_prior(best)
        objective = _total_nll(best)
        if not np.isclose(data_nll, -np.sum(log_likelihood), rtol=1e-10, atol=1e-6):
            raise ValueError(f"position {position['label']!r} data NLL decomposition disagrees")
        if not np.isclose(objective, data_nll + prior, rtol=1e-10, atol=1e-6):
            raise ValueError(f"position {position['label']!r} objective decomposition disagrees")
        if not isinstance(best.get("success"), bool):
            raise ValueError("retained best attempts must record boolean convergence")
        fixed = np.asarray(position["fixed_position_km"], dtype=float)
        if fixed.shape != (2,) or not np.all(np.isfinite(fixed)):
            raise ValueError("fixed positions must be finite east/north pairs")
    expected = int(record.get("position_count", len(positions)))
    completed = int(record.get("completed_position_count", len(positions)))
    if completed != len(positions) or completed > expected:
        raise ValueError("profile completion counts disagree with retained positions")
    complete = bool(record.get("complete", completed == expected))
    if complete != (completed == expected):
        raise ValueError("complete flag disagrees with profile completion counts")
    source_hashes = record.get("source_hashes")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("profile must bind source hashes")
    assert_snapshot_unchanged(source_hashes)
    return record


def _deterministic_seed(*parts):
    payload = "\x1f".join(str(part) for part in parts).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "little")


def paired_time_block_bootstrap(
    truth_group_log_likelihood,
    alternative_group_log_likelihood,
    group_time_s,
    timing_prior_delta_nll,
    block_length_s,
    draws=DEFAULT_DRAWS,
    seed=0,
):
    truth = np.asarray(truth_group_log_likelihood, dtype=float)
    alternative = np.asarray(alternative_group_log_likelihood, dtype=float)
    times = np.asarray(group_time_s, dtype=float)
    if truth.ndim != 1 or alternative.shape != truth.shape or times.shape != truth.shape:
        raise ValueError("paired bootstrap inputs must be aligned one-dimensional arrays")
    if len(truth) == 0 or not np.all(np.isfinite(truth + alternative + times)):
        raise ValueError("paired bootstrap inputs must be finite and nonempty")
    block_length_s = _finite_scalar(block_length_s, "block length")
    if block_length_s <= 0 or int(draws) <= 0:
        raise ValueError("block length and draw count must be positive")
    timing_prior_delta_nll = _finite_scalar(timing_prior_delta_nll, "timing-prior delta")
    block_index = np.floor((times - np.min(times)) / block_length_s).astype(np.int64)
    unique_blocks, inverse = np.unique(block_index, return_inverse=True)
    group_delta_data_nll = truth - alternative
    block_delta_data_nll = np.bincount(
        inverse, weights=group_delta_data_nll, minlength=len(unique_blocks)
    )
    generator = np.random.default_rng(seed)
    samples = generator.integers(
        0, len(unique_blocks), size=(int(draws), len(unique_blocks)), endpoint=False
    )
    sampled_data_delta = np.sum(block_delta_data_nll[samples], axis=1)
    sampled_total_delta = sampled_data_delta + timing_prior_delta_nll
    quantiles = (0.025, 0.5, 0.975)
    return {
        "block_length_s": block_length_s,
        "draw_count": int(draws),
        "block_count": int(len(unique_blocks)),
        "random_seed": int(seed),
        "probability_alternative_beats_truth_data_only": float(
            np.mean(sampled_data_delta < 0.0)
        ),
        "probability_alternative_beats_truth_total": float(
            np.mean(sampled_total_delta < 0.0)
        ),
        "data_delta_nll_quantiles": [float(value) for value in np.quantile(
            sampled_data_delta, quantiles
        )],
        "total_delta_nll_quantiles": [float(value) for value in np.quantile(
            sampled_total_delta, quantiles
        )],
        "quantile_probabilities": list(quantiles),
        "conditional_on_fixed_fitted_solutions": True,
        "refit_each_draw": False,
        "holdout": False,
    }


def _truth_position(record):
    return next(position for position in record["positions"]
                if position.get("kind") in {"truth", "reference"}
                or position.get("label") in {"truth", "reference"})


def summarize_profile_record(record, protocol, draws=DEFAULT_DRAWS):
    validate_profile_record(record, protocol, record["session"])
    truth_position = _truth_position(record)
    truth = _best(truth_position)
    truth_ranking_resolved = bool(truth_position.get("ranking_resolved", truth["success"]))
    group_values, group_times, truth_log_likelihood = _group_arrays(record, truth_position)
    rows = []
    for position in record["positions"]:
        best = _best(position)
        _, _, alternative_log_likelihood = _group_arrays(record, position)
        data_delta = float(best["data_nll"] - truth["data_nll"])
        prior_delta = float(_timing_prior(best) - _timing_prior(truth))
        total_delta = float(_total_nll(best) - _total_nll(truth))
        ranking_resolved = bool(position.get("ranking_resolved", best["success"]))
        both_converged = bool(
            truth["success"] and best["success"] and truth_ranking_resolved and ranking_resolved
        )
        bootstrap = None
        exclusion_reason = None
        if position is not truth_position:
            if both_converged:
                bootstrap = [paired_time_block_bootstrap(
                    truth_log_likelihood,
                    alternative_log_likelihood,
                    group_times,
                    prior_delta,
                    block_length,
                    draws=draws,
                    seed=_deterministic_seed(record["session"], position["label"], block_length),
                ) for block_length in protocol["evaluation"]["block_lengths_s"]]
            else:
                exclusion_reason = (
                    "conditional bootstrap comparison withheld because the truth or alternative "
                    "nuisance fit did not satisfy its convergence criterion or its retained "
                    "ranking remained unresolved"
                )
        fixed = np.asarray(position["fixed_position_km"], dtype=float)
        true_fixed = np.asarray(truth_position["fixed_position_km"], dtype=float)
        rows.append({
            "label": position["label"],
            "kind": position.get("kind"),
            "bearing_deg": position.get("bearing_deg"),
            "radius_m": position.get("radius_m"),
            "fixed_position_km": fixed.tolist(),
            "optimizer_coordinate_distance_from_truth_km": float(np.linalg.norm(fixed - true_fixed)),
            "objective": _total_nll(best),
            "data_nll": float(best["data_nll"]),
            "timing_prior_objective": _timing_prior(best),
            "delta_nll_from_truth": total_delta,
            "data_delta_nll_from_truth": data_delta,
            "timing_prior_delta_nll_from_truth": prior_delta,
            "success": bool(best["success"]),
            "ranking_resolved": ranking_resolved,
            "status": best.get("status"),
            "projected_nuisance_gradient_inf_norm": best.get(
                "projected_nuisance_gradient_inf_norm",
                best.get("projected_gradient_inf_norm"),
            ),
            "attempt_count": len(position.get("attempts", [])),
            "attempt_status_counts": {
                status: sum((attempt.get("status") or "missing") == status
                            for attempt in position.get("attempts", []))
                for status in sorted({attempt.get("status") or "missing"
                                      for attempt in position.get("attempts", [])})
            },
            "bootstrap_eligible": both_converged and position is not truth_position,
            "bootstrap_exclusion_reason": exclusion_reason,
            "conditional_time_block_bootstrap": bootstrap,
        })
    radius_summaries = []
    radii = sorted({float(row["radius_m"]) for row in rows
                    if row["radius_m"] is not None and float(row["radius_m"]) > 0})
    for radius in radii:
        radius_rows = [row for row in rows if row["radius_m"] is not None
                       and float(row["radius_m"]) == radius]
        converged = [row for row in radius_rows if row["success"]]
        radius_summaries.append({
            "radius_m": radius,
            "position_count": len(radius_rows),
            "converged_count": len(converged),
            "optimizer_coordinate_error_km_min": min(
                row["optimizer_coordinate_distance_from_truth_km"] for row in radius_rows
            ),
            "optimizer_coordinate_error_km_max": max(
                row["optimizer_coordinate_distance_from_truth_km"] for row in radius_rows
            ),
            "delta_nll_min_all_retained": min(row["delta_nll_from_truth"] for row in radius_rows),
            "delta_nll_max_all_retained": max(row["delta_nll_from_truth"] for row in radius_rows),
            "delta_nll_min_converged": (
                min(row["delta_nll_from_truth"] for row in converged) if converged else None
            ),
            "delta_nll_max_converged": (
                max(row["delta_nll_from_truth"] for row in converged) if converged else None
            ),
            "unresolved_labels": [row["label"] for row in radius_rows if not row["success"]],
        })
    displaced = [row for row in rows
                 if row["kind"] in {"displaced_optimum", "previous_displaced_optimum"}]
    return {
        "session": record["session"],
        "input_schema": record["schema"],
        "model_variant": record.get("model_variant") or "current-common-rf-fixed-original-set",
        "set_complexity_constant": record.get("set_complexity_constant"),
        "complete": bool(record["complete"]),
        "reference_used_for_fitting": bool(record.get("reference_used_for_fitting", True)),
        "expected_position_count": int(record["position_count"]),
        "completed_position_count": int(record["completed_position_count"]),
        "failed_position_labels": list(record.get("failed_position_labels", [])),
        "group_count": int(len(group_values)),
        "converged_position_count": sum(row["success"] for row in rows),
        "resolved_ranking_count": sum(row["ranking_resolved"] for row in rows),
        "attempt_status_counts": {
            status: sum(row["attempt_status_counts"].get(status, 0) for row in rows)
            for status in sorted({status for row in rows for status in row["attempt_status_counts"]})
        },
        "unresolved_position_labels": [row["label"] for row in rows if not row["success"]],
        "positions": rows,
        "radius_summaries": radius_summaries,
        "existing_bad_optimum": displaced[0] if len(displaced) == 1 else None,
    }


def existing_bias_context(wrong_solution, glrt_information):
    scans = []
    for scan in wrong_solution["scans"]:
        common = next(row for row in scan["variants"] if row["variant"] == "common")
        means = [float(row["mean_hz"]) for row in common["confident_residual_by_channel"]]
        medians = [float(row["median_hz"]) for row in common["confident_residual_by_channel"]]
        scans.append({
            "session": scan["session"],
            "existing_common_rf_position_error_km": float(common["position_error_km"]),
            "existing_common_rf_displacement_east_north_km": list(
                common["displacement_east_north_km"]
            ),
            "existing_common_rf_converged": bool(common["success"]),
            "confident_peak_residual_channel_mean_range_hz": [min(means), max(means)],
            "confident_peak_residual_channel_median_range_hz": [min(medians), max(medians)],
        })
    return {
        "scans": scans,
        "wrong_solution_audit_scope": wrong_solution["scope"],
        "glrt_information_audit_scope": glrt_information["scope"],
        "interpretation": (
            "The prior audits document displaced fitted positions and channel-dependent residual "
            "structure on the same development scans. They are bias diagnostics, not an "
            "independent accuracy estimate or a selection rule for this profile grid."
        ),
    }


def build_summary(records, protocol, amendment, wrong_solution, glrt_information,
                  draws=DEFAULT_DRAWS):
    profiles = [summarize_profile_record(record, protocol, draws=draws) for record in records]
    complete = all(profile["complete"] for profile in profiles)
    variants = list(dict.fromkeys(profile["model_variant"] for profile in profiles))
    return {
        "schema": "ds13-position-profile-evaluation/v1",
        "batch_status": "complete" if complete else "partial",
        "complete": complete,
        "sessions_expected": list(protocol["sessions"]),
        "sessions_evaluated": [profile["session"] for profile in profiles],
        "model_variants": variants,
        "profiles": profiles,
        "existing_bias_context": existing_bias_context(wrong_solution, glrt_information),
        "resource_amendment": {
            "schema": amendment["schema"],
            "maximum_numerical_workers": amendment["maximum_numerical_workers"],
            "scientific_protocol_change": amendment["scientific_protocol_change"],
        },
        "measurement_contract": {
            "fixed_original_set_control": (
                "Fixed original satellite set with the current finite-set likelihood over stored "
                "alias-family representative GLRT peak frequencies."
            ),
            "evaluated_variant": variants,
            "not_evaluated_as_full_surface": (
                "The profile is not a likelihood over complete GLRT response surfaces or raw IQ."
            ),
            "compact_extension": (
                "Any all-visible compact candidate-set result is a separately labelled extension "
                "with its own set-complexity rule and must not be called the unchanged current loss."
            ),
        },
        "uncertainty_contract": {
            "method": "paired time-block resampling of per-group fitted data-NLL differences",
            "block_lengths_s": list(protocol["evaluation"]["block_lengths_s"]),
            "draws": int(draws),
            "timing_prior": "reported separately and added once, not resampled",
            "fitted_solutions_fixed": True,
            "refit_bootstrap": False,
            "holdout": False,
            "coverage_claim": False,
            "failed_fit_policy": (
                "No bootstrap probability is reported unless both the truth and alternative "
                "nuisance fits satisfy their convergence criterion."
            ),
        },
        "scope": (
            "Known-position diagnostic on two development scans, with no holdout and no blind "
            "validation claim. Position-profile comparisons are local nuisance-basin searches, "
            "not proofs of a global position minimum. Bootstrap probabilities are conditional on "
            "the retained fitted solutions and do not establish calibrated geographic confidence."
        ),
    }


def plot_summary(summary, destination):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.tri as tri

    profiles = summary["profiles"]
    values = [row["delta_nll_from_truth"] for profile in profiles
              for row in profile["positions"] if row["kind"] not in {"truth", "reference"}]
    limit = max(abs(min(values, default=-1.0)), abs(max(values, default=1.0)), 1.0)
    figure, axes = plt.subplots(1, len(profiles), figsize=(7 * len(profiles), 6.4), squeeze=False)
    image = None
    for axis, profile in zip(axes[0], profiles):
        truth = next(row for row in profile["positions"]
                     if row["kind"] in {"truth", "reference"}
                     or row["label"] in {"truth", "reference"})
        origin = np.asarray(truth["fixed_position_km"])
        ring_rows = [row for row in profile["positions"]
                     if row["radius_m"] is not None and float(row["radius_m"]) > 0]
        points = np.asarray([np.asarray(row["fixed_position_km"]) - origin for row in ring_rows])
        colors = np.asarray([row["delta_nll_from_truth"] for row in ring_rows])
        if len(points) >= 3:
            triangulation = tri.Triangulation(points[:, 0], points[:, 1])
            axis.tricontourf(triangulation, colors, levels=21, cmap="coolwarm",
                             vmin=-limit, vmax=limit, alpha=.55)
        image = axis.scatter(points[:, 0], points[:, 1], c=colors, cmap="coolwarm",
                             vmin=-limit, vmax=limit, edgecolors="black", s=55, zorder=3)
        unresolved = np.asarray([not row["success"] for row in ring_rows])
        if np.any(unresolved):
            axis.scatter(points[unresolved, 0], points[unresolved, 1], facecolors="none",
                         edgecolors="black", s=115, linewidths=1.5, zorder=4,
                         label="Unresolved nuisance fit")
        axis.scatter(0, 0, marker="*", color="black", s=180, zorder=5, label="Truth")
        displaced = [row for row in profile["positions"]
                     if row["kind"] in {"displaced_optimum", "previous_displaced_optimum"}]
        for row in displaced:
            point = np.asarray(row["fixed_position_km"]) - origin
            axis.scatter(*point, marker="X", color="gold", edgecolors="black", s=120,
                         zorder=5, label="Existing bad optimum")
        for radius_m in sorted({float(row["radius_m"]) for row in ring_rows}):
            circle = plt.Circle((0, 0), radius_m / 1000.0, fill=False, color="black",
                                alpha=.35, linestyle=":" if radius_m < 500 else "--")
            axis.add_patch(circle)
        radius_text = "\n".join(
            f"{row['radius_m']:.0f} m: ΔNLL {row['delta_nll_min_all_retained']:.2f}"
            f"…{row['delta_nll_max_all_retained']:.2f}"
            for row in profile["radius_summaries"]
        )
        axis.text(.02, .02, radius_text, transform=axis.transAxes, fontsize=8,
                  va="bottom", bbox={"facecolor": "white", "alpha": .75, "edgecolor": "none"})
        axis.set_title(f"…{profile['session'][-8:]} ({profile['completed_position_count']}/"
                       f"{profile['expected_position_count']} positions)")
        axis.set_xlabel("East displacement from truth (km)")
        axis.set_ylabel("North displacement from truth (km)")
        axis.set_aspect("equal", adjustable="box")
        axis.grid(alpha=.18)
        axis.legend(fontsize=8, loc="upper right")
    if image is not None:
        figure.colorbar(image, ax=list(axes[0]), label="Profiled total ΔNLL from truth")
    figure.suptitle("DS13 fixed-position profile: sparse compass interpolation is descriptive only")
    figure.text(.5, .015,
                "Open circles mark unresolved fits; no bootstrap confidence claim is made for them. "
                "Stored GLRT peaks, not full GLRT surfaces.", ha="center", fontsize=9)
    figure.subplots_adjust(left=.07, right=.9, bottom=.1, top=.9, wspace=.22)
    destination = Path(destination)
    figure.savefig(destination / "position-profile-compass.png", dpi=170)
    figure.savefig(destination / "position-profile-compass.svg")
    plt.close(figure)


def evaluate(input_dir=DEFAULT_INPUT_DIR, output_dir=OUTPUT_DIR, draws=DEFAULT_DRAWS):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(output_dir)
    protocol_path = ROOT / "position-profile-protocol.json"
    amendment_path = ROOT / "position-profile-resource-amendment.json"
    wrong_path = ROOT / "wrong-solution-summary.json"
    information_path = ROOT / "glrt-information-summary.json"
    profile_paths = [input_dir / f"{session}.json" for session in SESSIONS]
    required = [protocol_path, amendment_path, wrong_path, information_path, *profile_paths]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"required sealed inputs are missing: {', '.join(missing)}")
    hashes = snapshot_files([__file__, *required])
    protocol = json.loads(protocol_path.read_text())
    amendment = json.loads(amendment_path.read_text())
    wrong_solution = json.loads(wrong_path.read_text())
    glrt_information = json.loads(information_path.read_text())
    if protocol.get("schema") != "ds13-nearby-position-protocol/v1":
        raise ValueError("unexpected position-profile protocol")
    if amendment.get("amends") != protocol_path.name:
        raise ValueError("resource amendment does not bind the profile protocol")
    records = [json.loads(path.read_text()) for path in profile_paths]
    for record, session in zip(records, SESSIONS):
        validate_profile_record(record, protocol, session)
    summary = build_summary(
        records, protocol, amendment, wrong_solution, glrt_information, draws=draws
    )
    summary["source_hashes"] = hashes
    assert_snapshot_unchanged(hashes)
    output_dir.mkdir(parents=False)
    with (output_dir / "summary.json").open("x") as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
    plot_summary(summary, output_dir)
    assert_snapshot_unchanged(hashes)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--draws", type=int, default=DEFAULT_DRAWS)
    args = parser.parse_args(argv)
    summary = evaluate(args.input_dir, args.output_dir, args.draws)
    print(json.dumps({
        "schema": summary["schema"],
        "batch_status": summary["batch_status"],
        "sessions": [{
            "session": profile["session"],
            "complete": profile["complete"],
            "converged": profile["converged_position_count"],
            "completed": profile["completed_position_count"],
        } for profile in summary["profiles"]],
    }, allow_nan=False))


if __name__ == "__main__":
    main()
