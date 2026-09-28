"""Audit reception-vs-frequency identity evidence; no estimator changes."""
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent


def track_override(track, variant="mixture"):
    ids = track["candidate_ids"]
    fit = track["variants"][variant]
    a = ids.index(fit["frequency_map_candidate_id"])
    b = ids.index(fit["joint_map_candidate_id"])
    delta = {"training": track["log_weights"][b] - track["log_weights"][a]}
    for name in ("frequency", "detection", "ratio"):
        ll = fit[f"candidate_{name}_log_likelihood"]
        delta[name] = ll[b] - ll[a]
    expected = fit["joint_posterior_log_weights"][b] - fit["joint_posterior_log_weights"][a]
    if not math.isclose(sum(delta.values()), expected, abs_tol=1e-8):
        raise ValueError("candidate evidence does not reconstruct posterior odds")
    return {
        "track_id": track["track_id"], "occupied_seconds": track["weight_seconds"],
        "reserve_observations": track["reserve_observations"],
        "matched_reception_observations": fit["matched_reception_observations"],
        "frequency_map": ids[a], "joint_map": ids[b], "changed": a != b,
        "log_evidence_joint_choice_minus_frequency_choice": delta,
        "frequency_probability_of_joint_choice": math.exp(fit["frequency_posterior_log_weights"][b]),
        "joint_probability_of_joint_choice": math.exp(fit["joint_posterior_log_weights"][b]),
    }


def summarize(data):
    if not data["finished"]:
        raise ValueError("unfinished diagnostic")
    positions = [(f"{prior}:{'+'.join(row['labels'])}", row["diagnostic"])
                 for prior, branch in data["branches"].items() for row in branch["positions"]]
    positions.append(("reference", data["roof_reference"]["diagnostic"]))
    result = {}
    for label, point in positions:
        variants = {}
        for variant in ("old", "mean", "mixture"):
            rows = [track_override(track, variant) for track in point["tracks"]]
            overrides = [row for row in rows if row["changed"]]
            variants[variant] = {
                "tracks": len(rows), "overrides": len(overrides),
                "overrides_with_joint_probability_above_099": sum(
                    row["joint_probability_of_joint_choice"] > .99 for row in overrides),
                "override_details": overrides,
            }
        result[label] = variants
    return result


if __name__ == "__main__":
    output = {"interpretation": "Model probabilities conditional on the frozen shortlist and independence assumptions, not calibrated physical identity confidence.",
              "sessions": {}, "source_sha256": {}}
    for sid in ("scan-fw-53ce822d78d476ba", "scan-fw-e76c229e9dc498b3"):
        source = HERE / f"mixture-track-diagnostic-{sid}.json"
        payload = source.read_bytes()
        output["source_sha256"][sid] = "sha256:" + hashlib.sha256(payload).hexdigest()
        output["sessions"][sid] = summarize(json.loads(payload))
    with (HERE / "reception-identity-overrides.json").open("x") as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
        stream.write("\n")
