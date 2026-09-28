#!/usr/bin/env python3
"""Supplemental reconstruction of causal-refit scores, contrasts, and MAP penalties."""

import argparse
import hashlib
import json
import math
from pathlib import Path

ARMS = ("D", "E", "S", "T")
NAMES = (*ARMS, "T_swap", "T_reverse", *(f"{arm}_shift" for arm in ARMS))
ROLES = ("reception", "held_frequency")
BETA_SD = (2.0, 1.0, 1.0, 0.5, 0.5, 0.5, 0.35, 0.35)
COMPARISONS = (
    ("E", "D"), ("S", "D"), ("S", "E"), ("T", "D"), ("T", "S"),
    ("T", "T_swap"), ("T", "T_reverse"),
    *((arm, f"{arm}_shift") for arm in ARMS),
)


def close(left, right, tolerance):
    return math.isclose(float(left), float(right), rel_tol=0, abs_tol=tolerance)


def role_scores(evaluation):
    output = {}
    for role in ROLES:
        windows = [window for lane in evaluation["lanes"] for window in lane["windows"]
                   if window["role"] == role]
        relative = math.fsum(float(window["relative_log_score"]) for window in windows)
        reference = math.fsum(float(window["reference_log_score"]) for window in windows)
        output[role] = {
            "windows": len(windows), "relative_log_score": relative,
            "reference_log_score": reference, "full_log_score": relative + reference,
            "relative_log_score_per_window": relative / len(windows),
            "reference_log_score_per_window": reference / len(windows),
            "full_log_score_per_window": (relative + reference) / len(windows),
        }
    return output


def penalty(selected):
    if selected["null_selected"]:
        return 0.0
    beta = selected["beta"]
    occupancy = float(selected["occupancy"])
    logit = math.log(occupancy / (1 - occupancy))
    log_tau = math.log(float(selected["tau_s"]))
    return (
        0.5 * math.fsum((float(value) / BETA_SD[index]) ** 2 for index, value in enumerate(beta))
        + 0.5 * (logit / 2.0) ** 2
        + 0.5 * (log_tau / 1.5) ** 2
    )


def audit(results, frozen):
    frozen_by_id = {fold["held_session"]: fold for fold in frozen["folds"]}
    per_fold = {}
    for fold in results["folds"]:
        sid = fold["held_session"]
        scores = {}
        for name, evaluation in fold["evaluations"].items():
            reconstructed = role_scores(evaluation)
            scores[name] = reconstructed
            for role in ROLES:
                exported = evaluation["roles"][role]
                for key in (
                    "windows",
                    "relative_log_score",
                    "reference_log_score",
                    "full_log_score",
                ):
                    tolerance = 0 if key == "windows" else 1e-8
                    if not close(reconstructed[role][key], exported[key], tolerance):
                        raise ValueError(f"role total mismatch: {sid} {name} {role} {key}")
                for key in ("relative_log_score_per_window", "reference_log_score_per_window",
                            "full_log_score_per_window"):
                    if not close(reconstructed[role][key], exported[key], 1e-10):
                        raise ValueError(f"per-window mismatch: {sid} {name} {role} {key}")
        for arm in ARMS:
            selected = fold["fits"][arm]["selected"]
            expected_penalty = penalty(selected)
            if not close(expected_penalty, selected["map_penalty"], 1e-8):
                raise ValueError(f"MAP penalty mismatch: {sid} {arm}")
            expected_gain = selected["calibration_relative_log_evidence"] - expected_penalty
            if not close(expected_gain, selected["map_gain"], 1e-8):
                raise ValueError(f"MAP gain mismatch: {sid} {arm}")
        frozen_scores = frozen_by_id[sid]["causal"]
        expected_refit = {}
        for name in ("D", "S", "T", "T_swap", "T_reverse", "T_shift"):
            expected_refit[name] = {
                role: scores[name][role]["full_log_score_per_window"]
                - frozen_scores[name]["roles"][role]["full_log_score_per_window"]
                for role in ROLES
            }
            for role in ROLES:
                if not close(expected_refit[name][role],
                             fold["refit_minus_frozen_full_per_window"][name][role], 1e-10):
                    raise ValueError(f"frozen contrast mismatch: {sid} {name} {role}")
        per_fold[sid] = {"scores": scores, "refit": expected_refit}

    expected = {}
    for role in ROLES:
        for name in NAMES:
            expected[f"{role}:{name}-causal_reference"] = {
                sid: row["scores"][name][role]["relative_log_score_per_window"]
                for sid, row in per_fold.items()
            }
        for left, right in COMPARISONS:
            expected[f"{role}:{left}-{right}"] = {
                sid: row["scores"][left][role]["relative_log_score_per_window"]
                - row["scores"][right][role]["relative_log_score_per_window"]
                for sid, row in per_fold.items()
            }
        for name in ("D", "S", "T", "T_swap", "T_reverse", "T_shift"):
            expected[f"{role}:refit-{name}-minus-frozen-{name}-full"] = {
                sid: row["refit"][name][role] for sid, row in per_fold.items()
            }
    if set(expected) != set(results["aggregate_equal_record"]):
        raise ValueError("aggregate comparison grid mismatch")
    for name, records in expected.items():
        exported = results["aggregate_equal_record"][name]
        if set(records) != set(exported["records"]):
            raise ValueError(f"aggregate record population mismatch: {name}")
        if any(not close(value, exported["records"][sid], 1e-10)
               for sid, value in records.items()):
            raise ValueError(f"aggregate record contrast mismatch: {name}")
        mean = math.fsum(records.values()) / len(records)
        if not close(mean, exported["mean"], 1e-10):
            raise ValueError(f"aggregate mean mismatch: {name}")
        if exported["positive_records"] != sum(value > 0 for value in records.values()) or \
                exported["negative_records"] != sum(value < 0 for value in records.values()):
            raise ValueError(f"aggregate sign mismatch: {name}")
    return {"schema": "rx-causal-refit-score-audit/v1", "status": "pass",
            "folds": len(per_fold), "evaluations": len(per_fold) * len(NAMES),
            "aggregate_contrasts": len(expected), "selected_map_penalties": len(per_fold) * 4}


def main():
    parser = argparse.ArgumentParser()
    for name in ("results", "frozen_results", "output"):
        parser.add_argument(f"--{name.replace('_', '-')}", dest=name, type=Path, required=True)
    args = parser.parse_args()
    payloads = {
        "results": args.results.read_bytes(),
        "frozen_results": args.frozen_results.read_bytes(),
    }
    receipt = audit(json.loads(payloads["results"]), json.loads(payloads["frozen_results"]))
    receipt["source_sha256"] = {name: hashlib.sha256(value).hexdigest()
                                for name, value in payloads.items()}
    with args.output.open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()
