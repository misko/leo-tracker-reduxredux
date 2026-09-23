"""Verify frozen unseen-scan runs and build the compact comparison receipt."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNS = {name: ROOT / "inputs/runs" / name for name in ("fitted", "original", "causal_mean")}


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def main():
    results = {name: load(path / "result.json") for name, path in RUNS.items()}
    fit_path = ROOT / "inputs/authorities/frozen-fit.json"
    exact_path = ROOT / "inputs/authorities/exact-fit-replay.json"
    inventory_path = ROOT / "inputs/authorities/holdout-inventory.json"
    fit, exact, inventory = map(load, (fit_path, exact_path, inventory_path))
    bindings = {
        "fit_digest": digest(fit_path),
        "exact_digest": digest(exact_path),
        "inventory_digest": digest(inventory_path),
    }
    expected_totals = {
        "fitted": -18189.345927416787,
        "original": -18312.790960433384,
        "causal_mean": -18189.351962909517,
    }
    common_sessions = None
    common_config = None
    common_training_sessions = None
    episode_identity = None
    observations = 0
    episodes = 0
    scan_documents = {}
    for mode, result in results.items():
        if not result.get("complete") or result.get("parameters_refitted") is not False:
            raise ValueError(f"{mode} run is incomplete or refitted")
        if any(result[key] != value for key, value in bindings.items()):
            raise ValueError(f"{mode} authority binding differs")
        if result["log_predictive"] != expected_totals[mode]:
            raise ValueError(f"{mode} aggregate differs from completed run")
        config = result["score_config"]
        training_sessions = result["training_sessions"]
        common_config = config if common_config is None else common_config
        common_training_sessions = (
            training_sessions if common_training_sessions is None else common_training_sessions
        )
        if config != common_config or training_sessions != common_training_sessions:
            raise ValueError("score configuration or training cohort differs")
        sessions = {row["session_id"] for row in result["scans"]}
        common_sessions = sessions if common_sessions is None else common_sessions
        if sessions != common_sessions or len(sessions) != len(result["scans"]):
            raise ValueError("run scan sets differ or contain duplicates")
        documents = {}
        identity = []
        mode_observations = 0
        for row in result["scans"]:
            path = RUNS[mode] / f"{row['session_id']}.json"
            if digest(path) != row["digest"]:
                raise ValueError("per-scan digest mismatch")
            document = load(path)
            documents[row["session_id"]] = document
            for episode in document["episodes"]:
                identity.append((row["session_id"], episode["episode_id"], episode["observations"]))
                mode_observations += episode["observations"]
        identity.sort()
        episode_identity = identity if episode_identity is None else episode_identity
        if identity != episode_identity:
            raise ValueError("run episode identities or observation counts differ")
        if mode == "fitted":
            observations, episodes = mode_observations, len(identity)
        scan_documents[mode] = documents
    source_paths = {
        "fitted": ROOT / "inputs/sources/scorer-fitted.py",
        "original": ROOT / "inputs/sources/scorer-ablation.py",
        "causal_mean": ROOT / "inputs/sources/scorer-ablation.py",
    }
    if any(digest(source_paths[mode]) != results[mode]["source_digest"] for mode in RUNS):
        raise ValueError("copied scorer source does not match run binding")
    if (len(common_sessions), episodes, observations) != (14, 350, 10184):
        raise ValueError("unexpected scan, episode, or observation total")

    chronology = {
        row["session_id"]: (row["reference_utc_ns"], row)
        for row in inventory["scans"]
        if row["included"]
    }
    if set(chronology) != common_sessions:
        raise ValueError("holdout inventory differs from scored scan set")
    rows = []
    for session in sorted(common_sessions, key=lambda value: chronology[value][0]):
        scores = {
            mode: scan_documents[mode][session]["log_predictive"] for mode in RUNS
        }
        inventory_row = chronology[session][1]
        rows.append(
            {
                "session_id": session,
                "reference_utc_ns": chronology[session][0],
                "observation_count": sum(
                    episode["observations"] for episode in scan_documents["fitted"][session]["episodes"]
                ),
                "episode_count": len(scan_documents["fitted"][session]["episodes"]),
                "inventory_observation_count": inventory_row["observation_count"],
                "scores": scores,
                "deltas": {
                    "fitted_minus_original": scores["fitted"] - scores["original"],
                    "causal_mean_minus_original": scores["causal_mean"] - scores["original"],
                    "fitted_minus_causal_mean": scores["fitted"] - scores["causal_mean"],
                },
            }
        )

    rates = {int(row["norad"]): abs(float(row["rate_s_h"])) for row in fit["rates"]}
    dominant = []
    for document in scan_documents["fitted"].values():
        for episode in document["episodes"]:
            leader = episode["top_candidates"][0]
            if leader["weight"] > 0.5:
                norad = int(leader["norad"])
                dominant.append((norad, float(leader["weight"]), rates.get(norad)))
    if len(dominant) != 319 or any(rate is None for _, _, rate in dominant):
        raise ValueError("dominant fitted-rate coverage differs")
    maximum_dominant_rate = max(rate for _, _, rate in dominant)
    if maximum_dominant_rate >= 1e-6:
        raise ValueError("dominant identities unexpectedly exercise nonzero fitted rates")

    totals = {mode: result["log_predictive"] for mode, result in results.items()}
    summary = {
        "schema": "unseen-scan-orbit-validation-summary/v1",
        "scope": "preparatory five-scan Reno model on whole-scan holdouts",
        "truth_accessed": False,
        "parameters_refitted": False,
        "bindings": bindings,
        "training_sessions": common_training_sessions,
        "counts": {
            "scan_count": len(rows),
            "episode_count": episodes,
            "observation_count": observations,
        },
        "totals": totals,
        "aggregate_deltas": {
            "fitted_minus_original": totals["fitted"] - totals["original"],
            "causal_mean_minus_original": totals["causal_mean"] - totals["original"],
            "fitted_minus_causal_mean": totals["fitted"] - totals["causal_mean"],
        },
        "positive_scan_counts": {
            key: sum(row["deltas"][key] > 0 for row in rows)
            for key in rows[0]["deltas"]
        },
        "dominant_fitted_rate_coverage": {
            "leader_weight_threshold": 0.5,
            "episode_count": len(dominant),
            "leaders_present_in_saved_fit": len(dominant),
            "leaders_with_abs_rate_below_1e-6": sum(rate < 1e-6 for _, _, rate in dominant),
            "maximum_abs_saved_rate_s_h": maximum_dominant_rate,
        },
        "method": {
            "position": "fixed five-scan Reno position",
            "identity_support": "same-parameter full causal catalogue per holdout scan",
            "offset": "constant frequency offset removed by within-segment contrasts",
            "unseen_norad_rate": "zero residual rate at causal mean",
            "orbit_uncertainty_integrated": False,
        },
        "claims_excluded": [
            "learned orbital-rate correction generalization",
            "correct satellite identities",
            "final eight-hour training result",
            "geometry gain",
            "receiver position accuracy",
        ],
        "scans": rows,
    }
    (ROOT / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )


if __name__ == "__main__":
    main()
