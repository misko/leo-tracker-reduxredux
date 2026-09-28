"""Calibrate a finite presence-state grid around frozen geometry emissions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

from tools.rx_geometry_fit import lane_loglik, raw_features, signal_arrays
from tools.rx_geometry_frozen_score import validate_frozen_model
from tools.rx_presence_filter import forward_score

GRID = [(0.0, 1.0)] + [(p, tau) for p in (0.01, 0.1, 0.5) for tau in (0.1, 1.0, 10.0)]


def prepare_lanes(dataset, center, scale):
    if dataset.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported dataset schema")
    lanes = []
    for source in dataset["lanes"]:
        if not source["windows"]:
            continue
        components = source.get("components", [])
        kinds = [component.get("kind") for component in components]
        if not components or kinds[-1] != "other" or kinds.count("other") != 1:
            raise ValueError("components must end in exactly one other component")
        if any(kind != "track_candidate" for kind in kinds[:-1]):
            raise ValueError("all retained nomination components must be track candidates")
        if not kinds[:-1]:
            raise ValueError("lane has no retained nomination components")
        windows = source["windows"]
        window_ids = [window.get("source_window_id") for window in windows]
        if any(not isinstance(value, str) or not value for value in window_ids):
            raise ValueError("every window must have a nonempty source_window_id")
        if len(window_ids) != len(set(window_ids)):
            raise ValueError("source windows must be unique within a lane")
        times_ns = [window.get("prediction_utc_ns") for window in windows]
        if any(not isinstance(value, int) for value in times_ns) or any(
            right <= left for left, right in zip(times_ns, times_ns[1:], strict=False)
        ):
            raise ValueError("prediction times must be strictly increasing integers")
        roles = [window.get("role") for window in windows]
        if any(role not in {"reception", "held_frequency"} for role in roles):
            raise ValueError("windows contain an unsupported role")
        if "reception" not in roles or "held_frequency" not in roles:
            raise ValueError("each lane must contain reception and held-frequency windows")
        if any(
            role == "reception" for role in roles[roles.index("held_frequency") :]
        ):
            raise ValueError("all reception windows must precede held-frequency windows")
        if any(len(window.get("predictions", [])) != len(components) - 1 for window in windows):
            raise ValueError("prediction/component cardinality mismatch")
        x, visible, mu = raw_features(source)
        times = [w["prediction_utc_ns"] for w in windows]
        prior = np.array(
            [
                c["log_prior"] if c["log_prior"] is not None else -np.inf
                for c in source["components"][:-1]
            ]
        )
        if not np.isfinite(logsumexp(prior)):
            raise ValueError("no retained nomination mass")
        lanes.append(
            {
                "source": source,
                "x": (x - center) / scale,
                "mu": mu,
                "visible": visible,
                "roles": np.array([w["role"] for w in source["windows"]]),
                "times": np.array([(t - times[0]) / 1e9 for t in times]),
                "prior": prior - logsumexp(prior),
                "counts": np.array(
                    [[len(w["observed"][r]) for r in ("rx0", "rx1")] for w in source["windows"]]
                ),
            }
        )
    return lanes


def absent_loglik(lane, lambdas):
    return np.sum(
        -lambdas + lane["counts"] * np.log(lambdas / lane["source"]["alias_period_hz"]), axis=1
    )


def emission(lane, beta, lambdas, center, scale, control=None):
    x = None
    if control in ("swap", "reverse"):
        x = (raw_features(lane["source"], control)[0] - center) / scale
    full = lane_loglik(lane, beta, lambdas, x=x)
    return np.column_stack((absent_loglik(lane, lambdas), full[:, :-1]))


def select_state(lanes, beta, lambdas, center, scale):
    prepared = []
    for lane in lanes:
        if lane["source"]["recording_split"] != "calibration":
            continue
        mask = lane["roles"] == "reception"
        prepared.append(
            (lane["prior"], emission(lane, beta, lambdas, center, scale)[mask], lane["times"][mask])
        )
    if not prepared:
        raise ValueError("no calibration reception population")
    calibration_windows = sum(len(times) for _, _, times in prepared)
    grid = []
    for occupancy, tau in GRID:
        total = 0.0
        for prior, ll, times in prepared:
            n = len(times)
            score = forward_score(
                prior, ll, times, np.ones(n, dtype=bool), np.zeros(n, dtype=bool), occupancy, tau
            )
            total += float(np.sum(score.window_log_scores))
        grid.append({"occupancy": occupancy, "tau_s": tau, "calibration_log_score": total})
    null = grid[0]
    analytical_null = sum(float(np.sum(ll[:, 0])) for _, ll, _ in prepared)
    if not np.isclose(null["calibration_log_score"], analytical_null, rtol=0.0, atol=1e-10):
        raise ValueError("pi=0 score does not reproduce analytical absent density")
    best = min(grid, key=lambda r: (-r["calibration_log_score"], r["occupancy"], r["tau_s"]))
    return {
        "selected": best,
        "grid": grid,
        "calibration_reception_windows": calibration_windows,
        "analytical_absent_log_score": analytical_null,
    }


def encode_logs(values):
    return [float(x) if np.isfinite(x) else None for x in values]


def posterior_summary(logweights):
    log_present = float(logsumexp(logweights[1:]))
    conditional = logweights[1:] - log_present if np.isfinite(log_present) else None
    entropy = None
    if conditional is not None:
        finite = np.isfinite(conditional)
        entropy = float(-np.sum(np.exp(conditional[finite]) * conditional[finite]))
    return {
        "presence_probability": float(np.exp(log_present)),
        "conditional_nomination_entropy_nats": entropy,
        "state_log_weights": encode_logs(logweights),
        "nomination_log_weights_given_presence": None
        if not np.isfinite(log_present)
        else encode_logs(logweights[1:] - log_present),
    }


def evaluate(lanes, beta, lambdas, center, scale, state, control=None):
    records, exports = {}, []
    for lane in lanes:
        if lane["source"]["recording_split"] != "evaluation":
            continue
        ll = emission(lane, beta, lambdas, center, scale, control)
        rec, held = lane["roles"] == "reception", lane["roles"] == "held_frequency"
        score = forward_score(
            lane["prior"], ll, lane["times"], rec, held, state["occupancy"], state["tau_s"]
        )
        sid = lane["source"]["lane"]["session_id"]
        row = records.setdefault(
            sid, {"held_windows": 0, "log_score": 0.0, "absent_log_score": 0.0}
        )
        row["held_windows"] += int(held.sum())
        row["log_score"] += float(score.window_log_scores[held].sum())
        row["absent_log_score"] += float(absent_loglik(lane, lambdas)[held].sum())
        exports.append(
            {
                "lane": lane["source"]["lane"],
                "nomination_components": lane["source"]["components"][:-1],
                "reception_posterior": posterior_summary(score.reception_log_posterior),
                "held_posterior": posterior_summary(score.held_log_posterior),
                "window_ids": [w["source_window_id"] for w in lane["source"]["windows"]],
                "window_presence": score.posterior_presence.tolist(),
                "held_log_scores": score.window_log_scores[held].tolist(),
            }
        )
    for row in records.values():
        row["score_per_window"] = row["log_score"] / row["held_windows"]
        row["versus_absent_per_window"] = (row["log_score"] - row["absent_log_score"]) / row[
            "held_windows"
        ]
    return {
        "records": records,
        "lanes": exports,
        "mean_vs_absent": float(np.mean([r["versus_absent_per_window"] for r in records.values()])),
    }


def run(pilot, confirmation, model):
    center, scale, lambdas = validate_frozen_model(model)
    pids = {lane["lane"]["session_id"] for lane in pilot["lanes"]}
    cids = {lane["lane"]["session_id"] for lane in confirmation["lanes"]}
    if pids & cids:
        raise ValueError("confirmation overlaps pilot")
    if any(lane["recording_split"] != "evaluation" for lane in confirmation["lanes"]):
        raise ValueError("confirmation must be evaluation-only")
    train = prepare_lanes(pilot, center, scale)
    other = prepare_lanes(confirmation, center, scale)
    signal_arrays(train, model["sigma_hz"], calibration_only=True)
    selections = {}
    for arm in ("D", "S", "T"):
        selections[arm] = select_state(
            train, np.array(model["fits"][arm]["parameters"]), lambdas, center, scale
        )
        print(json.dumps({"arm": arm, **selections[arm]["selected"]}), flush=True)
    # All selections are frozen before any held or confirmation emissions are used.
    signal_arrays(train, model["sigma_hz"])
    signal_arrays(other, model["sigma_hz"])
    panels = {}
    for panel, lanes in (("pilot", train), ("confirmation", other)):
        evaluations = {}
        for arm in ("D", "S", "T"):
            evaluations[arm] = evaluate(
                lanes,
                np.array(model["fits"][arm]["parameters"]),
                lambdas,
                center,
                scale,
                selections[arm]["selected"],
            )
        for control in ("swap", "reverse"):
            evaluations[control] = evaluate(
                lanes,
                np.array(model["fits"]["T"]["parameters"]),
                lambdas,
                center,
                scale,
                selections["T"]["selected"],
                control,
            )
        # Fixed quarter-circle nomination control; geometry/times/observations unchanged.
        for lane in lanes:
            lane["mu"] += lane["source"]["alias_period_hz"] / 4
        signal_arrays(lanes, model["sigma_hz"])
        for arm in ("D", "S", "T"):
            evaluations[arm + "_shift"] = evaluate(
                lanes,
                np.array(model["fits"][arm]["parameters"]),
                lambdas,
                center,
                scale,
                selections[arm]["selected"],
            )
        denominators = [
            {s: r["held_windows"] for s, r in e["records"].items()} for e in evaluations.values()
        ]
        if any(d != denominators[0] for d in denominators):
            raise ValueError("model/control denominators disagree")
        contrasts = {}
        for left, right in (
            ("S", "D"),
            ("T", "S"),
            ("T", "swap"),
            ("T", "reverse"),
            ("D", "D_shift"),
            ("S", "S_shift"),
            ("T", "T_shift"),
        ):
            values = {
                sid: evaluations[left]["records"][sid]["score_per_window"]
                - evaluations[right]["records"][sid]["score_per_window"]
                for sid in evaluations[left]["records"]
            }
            contrasts[left + "-" + right] = {
                "records": values,
                "mean": float(np.mean(list(values.values()))),
            }
        panels[panel] = {"evaluations": evaluations, "contrasts": contrasts}
    combined = {}
    for arm in ("D", "S", "T"):
        values = [
            row["versus_absent_per_window"]
            for panel in panels.values()
            for row in panel["evaluations"][arm]["records"].values()
        ]
        combined[arm] = {
            "mean_vs_absent": float(np.mean(values)),
            "positive_records": sum(value > 0 for value in values),
            "records": len(values),
        }
    combined["S_minus_D"] = combined["S"]["mean_vs_absent"] - combined["D"]["mean_vs_absent"]
    combined["S_passes_reference_and_D"] = bool(
        selections["S"]["selected"]["occupancy"] > 0
        and combined["S"]["mean_vs_absent"] > 0
        and combined["S_minus_D"] > 0
    )
    return {
        "schema": "rx-presence-geometry/v1",
        "status": "complete",
        "state_selections": selections,
        "panels": panels,
        "combined_equal_record": combined,
        "interpretation": (
            "Reused-panel state ablation with frozen emissions and assumed background; "
            "presence and conditional nomination are model probabilities, not verified identity."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("pilot", "confirmation", "model", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    payloads = {k: getattr(args, k).read_bytes() for k in ("pilot", "confirmation", "model")}
    inputs = {k: json.loads(v) for k, v in payloads.items()}
    if hashlib.sha256(payloads["pilot"]).hexdigest() != inputs["model"]["dataset_sha256"]:
        raise ValueError("model/pilot digest mismatch")
    if args.output.exists():
        raise FileExistsError(args.output)
    result = run(**inputs)
    result["source_sha256"] = {k: hashlib.sha256(v).hexdigest() for k, v in payloads.items()}
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
