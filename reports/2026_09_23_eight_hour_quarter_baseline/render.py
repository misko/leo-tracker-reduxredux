#!/usr/bin/env python3
"""Verify the frozen quarter-baseline evidence and render compact report plots."""

import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


HERE = Path(__file__).resolve().parent
REGIONS = ("sacramento", "reno", "denver")


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


def main():
    reference = read(HERE / "inputs/evaluation-reference.json")
    rows = []
    fits = {}
    for region in REGIONS:
        fit_path = HERE / f"inputs/fits/{region}.json"
        exact_path = HERE / f"inputs/exact/{region}.json"
        evaluation_path = HERE / f"inputs/evaluations/{region}.json"
        fit, exact, evaluation = map(read, (fit_path, exact_path, evaluation_path))
        fits[region] = fit
        fit_digest, exact_digest = digest(fit_path), digest(exact_path)
        calculated_error = haversine_km(
            fit["latitude_deg"], fit["longitude_deg"],
            reference["latitude_deg"], reference["longitude_deg"],
        )
        assert fit["converged"] is True and fit["truth_accessed"] is False
        assert fit["training_only"] is True and fit["observation_count"] == 5890
        assert fit["track_count"] == 198 and len(fit["sessions"]) == 8
        assert exact["fit_digest"] == fit_digest and exact["score_agreement"] is True
        assert exact["maximum_doppler_error_hz"] == 0.0
        assert evaluation["fit_digest"] == fit_digest
        assert evaluation["exact_digest"] == exact_digest
        assert evaluation["reference_digest"] == digest(HERE / "inputs/evaluation-reference.json")
        assert math.isclose(calculated_error, evaluation["horizontal_error_km"], abs_tol=1e-9)
        rows.append({
            "region": region,
            "start_latitude_deg": fit["region"]["latitude_deg"],
            "start_longitude_deg": fit["region"]["longitude_deg"],
            "latitude_deg": fit["latitude_deg"],
            "longitude_deg": fit["longitude_deg"],
            "horizontal_error_km": calculated_error,
            "negative_log_posterior": fit["negative_log_posterior"],
            "projected_gradient_max": fit["projected_gradient_max"],
            "fit_digest": fit_digest,
            "exact_digest": exact_digest,
            "exact_cases": exact["evaluated_cases"],
            "exact_objective_difference": exact["objective_difference"],
        })

    source_dir = HERE / "source"
    numerical_names = {
        "compressed_orbit_states.py", "joint_orbit_position.py", "orbit_rate_states.py",
        "robust_track_location.py", "shared_gaussian_orbit.py",
    }
    for fit in fits.values():
        assert set(fit["numerical_source_digests"]) == numerical_names
        for name, expected in fit["numerical_source_digests"].items():
            assert digest(source_dir / name) == expected
        assert digest(source_dir / "fit_cached_joint_orbit_position.py") == fit["source_digest"]
        assert digest(source_dir / "load_compressed_joint_cache.py") == fit["compressed_loader_digest"]
    for region in REGIONS:
        exact = read(HERE / f"inputs/exact/{region}.json")
        assert digest(source_dir / "replay_joint_orbit_cohort.py") == exact["source_digest"]

    associations = {
        region: {item["episode_id"]: item for item in fit["associations"]}
        for region, fit in fits.items()
    }
    episode_ids = set(associations["reno"])
    assert len(episode_ids) == 198
    assert all(set(associations[region]) == episode_ids for region in REGIONS)

    stability = read(HERE / "inputs/quarter8-association-stability.json")
    assert {row["episode_id"] for row in stability["rows"]} == episode_ids
    for row in stability["rows"]:
        episode_id = row["episode_id"]
        direct_winners = {}
        for region in REGIONS:
            association = associations[region][episode_id]
            leader = association["top_candidates"][0]
            direct_winners[region] = None if association["null_weight"] > leader["weight"] else leader["norad"]
        reno = associations["reno"][episode_id]
        assert row["leader_norad"] == reno["top_candidates"][0]["norad"]
        assert math.isclose(row["leader_weight"], reno["top_candidates"][0]["weight"], abs_tol=1e-15)
        assert math.isclose(row["null_weight"], reno["null_weight"], abs_tol=1e-15)
        assert row["winners"] == direct_winners
        assert row["same_winner_all_initializations"] == (len(set(direct_winners.values())) == 1)
    derived = {
        "track_count": len(stability["rows"]),
        "same_winner_all_initializations": sum(
            row["same_winner_all_initializations"] for row in stability["rows"]
        ),
        "leader_above_0_9": sum(row["leader_weight"] > 0.9 for row in stability["rows"]),
        "leader_above_0_5": sum(row["leader_weight"] > 0.5 for row in stability["rows"]),
        "null_majority": sum(row["null_weight"] > 0.5 for row in stability["rows"]),
    }
    for key, value in derived.items():
        assert stability[key] == value
    assert stability["fit_digests"] == {row["region"]: row["fit_digest"] for row in rows}

    paired = read(HERE / "inputs/diagnostics/quarter8-paired-association-consistency.json")
    paired_derived = {
        "pair_count": len(paired["rows"]),
        "available": sum(row["available"] for row in paired["rows"]),
        "same_leader": sum(row["same_leader"] for row in paired["rows"]),
        "high_weight_disagreements": sum(
            (not row["same_leader"]) and row["both_leader_above_0_9"] for row in paired["rows"]
        ),
    }
    for key, value in paired_derived.items():
        assert paired[key] == value
    assert paired["fit_digest"] == next(row["fit_digest"] for row in rows if row["region"] == "reno")
    for row in paired["rows"]:
        direct_leaders = []
        for episode_id in row["episode_ids"]:
            leader = associations["reno"][episode_id]["top_candidates"][0]
            direct_leaders.append({"norad": leader["norad"], "weight": leader["weight"]})
        assert row["leaders"] == direct_leaders
        assert row["same_leader"] == (direct_leaders[0]["norad"] == direct_leaders[1]["norad"])
        assert row["both_leader_above_0_9"] == all(item["weight"] > 0.9 for item in direct_leaders)

    holdout = read(HERE / "inputs/holdout/quarter8-reno.json")
    prior = read(HERE / "inputs/holdout/five-scan-reno.json")
    assert holdout["complete"] is True and len(holdout["scans"]) == 14
    assert holdout["fit_digest"] == next(row["fit_digest"] for row in rows if row["region"] == "reno")
    assert holdout["exact_digest"] == next(row["exact_digest"] for row in rows if row["region"] == "reno")
    assert len(prior["scans"]) == 14
    assert holdout["truth_accessed"] is False and prior["truth_accessed"] is False
    assert holdout["parameters_refitted"] is False and prior["parameters_refitted"] is False
    assert holdout["orbit_mode"] == "fitted"
    assert holdout["score_config"] == prior["score_config"]
    assert holdout["unseen_norad_policy"] == prior["unseen_norad_policy"]
    assert digest(source_dir / "score_unseen_joint_scans.py") == holdout["source_digest"]
    assert digest(source_dir / "score_unseen_joint_scans-five-scan.py") == prior["source_digest"]
    holdout_by_session = {row["session_id"]: row for row in holdout["scans"]}
    prior_by_session = {row["session_id"]: row for row in prior["scans"]}
    assert set(holdout_by_session) == set(prior_by_session) and len(holdout_by_session) == 14
    for session in holdout_by_session:
        quarter_path = HERE / f"inputs/holdout/quarter8-scans/{session}.json"
        prior_path = HERE / f"inputs/holdout/five-scan-scans/{session}.json"
        quarter_scan, prior_scan = read(quarter_path), read(prior_path)
        assert digest(quarter_path) == holdout_by_session[session]["digest"]
        assert digest(prior_path) == prior_by_session[session]["digest"]
        assert quarter_scan["session_id"] == prior_scan["session_id"] == session
        assert len(quarter_scan["episodes"]) == len(prior_scan["episodes"])
        assert sum(item["observations"] for item in quarter_scan["episodes"]) == sum(
            item["observations"] for item in prior_scan["episodes"]
        )
        assert math.isclose(quarter_scan["log_predictive"], holdout_by_session[session]["log_predictive"], abs_tol=1e-9)
        assert math.isclose(prior_scan["log_predictive"], prior_by_session[session]["log_predictive"], abs_tol=1e-9)
    assert math.isclose(sum(row["log_predictive"] for row in holdout["scans"]), holdout["log_predictive"], abs_tol=1e-9)
    assert math.isclose(sum(row["log_predictive"] for row in prior["scans"]), prior["log_predictive"], abs_tol=1e-9)

    summary = {
        "schema": "eight-hour-quarter-baseline-report/v1",
        "scope": {"available_scans": 44, "training_scans": 8, "holdout_scans": 14,
                  "training_tracks": 198, "training_observations": 5890},
        "method": "fixed-zero-residual-rate causal-orbit baseline",
        "rows": rows,
        "association_stability": derived,
        "paired_association_diagnostic": paired_derived,
        "holdout": {
            "quarter8_log_predictive": holdout["log_predictive"],
            "five_scan_log_predictive": prior["log_predictive"],
            "difference": holdout["log_predictive"] - prior["log_predictive"],
            "comparison_is_pure_scan_count_experiment": False,
        },
        "limitations": [
            "This is a subset result: 8 training scans, 198 tracks, and 5890 observations.",
            "This is not a completed joint fit or a fit over all 30 training scans.",
            "Association weights are not calibrated identity probabilities or identity truth.",
            "The nominal 80 mm paired-receiver geometry does not yet justify a calibrated positioning claim.",
            "The five-scan comparison differs in more than scan count.",
        ],
    }
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    errors = [row["horizontal_error_km"] for row in rows]
    axes[0].scatter([r.title() for r in REGIONS], errors, s=70, color=["#4c78a8", "#f58518", "#54a24b"])
    axes[0].set_ylabel("Evaluation error (km)")
    axes[0].set_title("Same fitted location from three starts")
    axes[0].set_ylim(2.76184, 2.76190)
    axes[0].ticklabel_format(axis="y", style="plain", useOffset=False)
    axes[0].grid(axis="y", alpha=0.25)
    labels = ["> 0.9", "> 0.5", "null majority"]
    values = [derived["leader_above_0_9"], derived["leader_above_0_5"], derived["null_majority"]]
    axes[1].bar(labels, values, color=["#72b7b2", "#4c78a8", "#e45756"])
    axes[1].axhline(198, color="black", linewidth=1, linestyle="--", label="198 tracks")
    axes[1].set_ylabel("Track count")
    axes[1].set_title("Leading-satellite weight diagnostic")
    axes[1].legend(frameon=False)
    axes[1].grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(HERE / "quarter-baseline-summary.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    values = [prior["log_predictive"], holdout["log_predictive"]]
    ax.scatter(["Earlier 5-scan fit", "Quarter 8-scan baseline"], values,
               s=90, color=["#9d755d", "#4c78a8"])
    ax.set_ylabel("14-scan log predictive")
    ax.set_title("Same holdout set; methods are not scan-count matched")
    ax.set_ylim(-18192, -18170)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(HERE / "holdout-comparison.png", dpi=180)
    plt.close(fig)

    files = {}
    for path in sorted(HERE.rglob("*")):
        if path.is_file() and path.name != "artifact-manifest.json" and "__pycache__" not in path.parts:
            files[str(path.relative_to(HERE))] = {"sha256": digest(path), "bytes": path.stat().st_size}
    manifest = {"schema": "report-artifact-manifest/v1", "files": files}
    (HERE / "artifact-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"verified_regions": list(REGIONS), "derived": derived,
                      "holdout_difference": summary["holdout"]["difference"],
                      "manifest_files": len(files)}, indent=2))


if __name__ == "__main__":
    main()
