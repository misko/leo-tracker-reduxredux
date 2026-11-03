"""DS11 coverage and fixed-point check for donor RX-difference scale features."""
from __future__ import annotations

import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.special import gammaln, logsumexp


HERE = Path(__file__).resolve().parent
HILL = HERE.parent
ROOT = HERE.parents[2]
BASE = HILL.parent / "2026_09_30_ds11_single10"
CALIBRATION = HILL.parent / "2026_09_30_rx_scale_common_transfer" / "summary.json"
SIDECAR = HILL / "source_balance" / "catalogue_identities.json"
STRONG_THRESHOLD = 0.5
PAIR_TOLERANCE_S = 1e-6
MIN_TRAINING_PAIRS = 8
MIN_TRAINING_SPAN_S = 5.0


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def profile_scale(residual, mask, sigma, slow):
    offsets = np.asarray([
        slow.fit_stationary_offset(row[mask], sigma=sigma)[0] for row in residual
    ])
    z = (residual - offsets[:, None]) / sigma
    density = (
        gammaln(2.5) - gammaln(2.0) - 0.5 * math.log(4 * math.pi)
        - math.log(sigma) - 2.5 * np.log1p(z * z / 4)
    )
    prior = 0.5 * offsets**2 / 1e12
    return density[:, mask].sum(axis=1) - prior, density.sum(axis=1) - prior


def paired_feature(left, right):
    ta, tb = np.asarray(left["times_s"]), np.asarray(right["times_s"])
    distance = abs(ta[:, None] - tb[None, :])
    ab = distance.argmin(axis=1)
    ba = distance.argmin(axis=0)
    ia = np.asarray([
        i for i, j in enumerate(ab) if ba[j] == i and distance[i, j] <= PAIR_TOLERANCE_S
    ], dtype=int)
    ib = ab[ia]
    ma, mb = left["mask"][ia], right["mask"][ib]
    train = ma & mb
    held = ~ma & ~mb
    mixed = ma != mb
    if train.sum() < MIN_TRAINING_PAIRS or np.ptp(ta[ia][train]) < MIN_TRAINING_SPAN_S:
        return None
    difference = left["residual"][ia] - right["residual"][ib]
    center = float(np.median(difference[train]))
    feature = max(1.0, 1.4826 * float(np.median(abs(difference[train] - center))))
    return {
        "feature_hz": feature,
        "training_pairs": int(train.sum()),
        "held_pairs": int(held.sum()),
        "mixed_pairs": int(mixed.sum()),
        "training_span_s": float(np.ptp(ta[ia][train])),
    }


def arm_score(document, engine, local, scales, slow):
    training = held = 0.0
    for track in document["tracks"]:
        prediction, visible = engine.prediction(track, local)
        train, joint = profile_scale(
            track["y"][None, :] - prediction, track["mask"], scales[track["track_id"]], slow
        )
        train_normal = logsumexp(np.where(visible, train, -np.inf))
        joint_normal = logsumexp(np.where(visible, joint, -np.inf))
        if not np.isfinite(train_normal) or not np.isfinite(joint_normal):
            raise ValueError("no visible candidate in scaled fixed-point score")
        training += float(train_normal - math.log(track["catalogue_size"]))
        held += float(joint_normal - train_normal)
    return {"training": training, "held": held}


def main():
    sys.path.insert(0, str(ROOT / "tools"))
    import ds7_baseline_adapter as slow
    import ds7_fast_baseline_adapter as fast

    fast.baseline.profile = fast.profile
    plan_path = BASE / "plan.json"
    plan = json.loads(plan_path.read_text())
    sidecar = json.loads(SIDECAR.read_text())
    calibration = json.loads(CALIBRATION.read_text())
    coefficients = {}
    for receiver in (0, 1):
        summary = calibration[f"rx{receiver}"]["fits"]
        assert summary["constant"]["qualified"] and summary["paired_scale"]["qualified"]
        constant = float(summary["constant"]["params"][0])
        intercept, exponent = map(float, summary["paired_scale"]["params"])
        coefficients[receiver] = {
            "constant_log_scale": constant,
            "variable_intercept": intercept,
            "feature_exponent": exponent,
        }

    scans = []
    for index, entry in enumerate(plan["inputs"]):
        documents = fast.load_documents({"config": plan["config"], "inputs": [entry]})
        document = documents[0]
        engine = fast.baseline.Stationary(document, plan["config"])
        incumbent_path = BASE / "runs" / f"{index:02d}_iid.json"
        incumbent = json.loads(incumbent_path.read_text())["selected"]
        if incumbent is None:
            raise ValueError(f"unqualified original IID endpoint at index {index}")
        local = np.asarray(incumbent["x"], dtype=float)
        physical = {
            track_id: row["candidate_norad"]
            for track_id, row in sidecar["scans"][str(index)]["tracks"].items()
        }
        eligible = []
        for track in document["tracks"]:
            prediction, visible = engine.prediction(track, local)
            train, _, audits, _ = fast.profile(
                track["y"][None, :] - prediction, track["mask"]
            )
            if not all(row["converged"] for row in audits):
                raise RuntimeError("offset stationarity failed in feature assignment")
            train = np.where(visible, train, -np.inf)
            normal = logsumexp(train)
            probability = np.exp(train - normal)
            slot = int(np.argmax(probability))
            if probability[slot] < STRONG_THRESHOLD:
                continue
            norads = physical[track["track_id"]]
            if len(norads) != len(prediction) or len(norads) != len(set(norads)):
                raise ValueError("physical candidate mapping mismatch")
            eligible.append({
                "track_id": track["track_id"],
                "receiver_id": int(track["receiver_id"]),
                "rf_hz": float(track["rf_hz"]),
                "norad": int(norads[slot]),
                "times_s": np.asarray(track["times_s"], dtype=float),
                "mask": track["mask"],
                "residual": track["y"] - prediction[slot],
                "confidence": float(probability[slot]),
            })

        grouped = defaultdict(list)
        for track in eligible:
            grouped[(track["rf_hz"], track["norad"])].append(track)
        pairs = []
        attempted = 0
        features_by_track = defaultdict(list)
        for group in grouped.values():
            left = [row for row in group if row["receiver_id"] == 0]
            right = [row for row in group if row["receiver_id"] == 1]
            for a in left:
                for b in right:
                    attempted += 1
                    feature = paired_feature(a, b)
                    if feature is None:
                        continue
                    pairs.append({
                        **feature,
                        "track0": a["track_id"],
                        "track1": b["track_id"],
                        "rf_hz": a["rf_hz"],
                        "norad": a["norad"],
                    })
                    features_by_track[(0, a["track_id"])].append(feature["feature_hz"])
                    features_by_track[(1, b["track_id"])].append(feature["feature_hz"])

        log_ratios = {}
        by_receiver = defaultdict(list)
        for (receiver, track_id), features in features_by_track.items():
            feature = float(np.exp(np.median(np.log(features))))
            coefficient = coefficients[receiver]
            log_ratio = (
                coefficient["variable_intercept"]
                + coefficient["feature_exponent"] * math.log(feature)
                - coefficient["constant_log_scale"]
            )
            log_ratios[track_id] = log_ratio
            by_receiver[receiver].append(log_ratio)
        controls = {
            receiver: float(np.median(by_receiver[receiver])) if by_receiver[receiver] else 0.0
            for receiver in (0, 1)
        }
        baseline_scales = {track["track_id"]: 100.0 for track in document["tracks"]}
        variable_scales = {
            track["track_id"]: 100.0 * math.exp(log_ratios.get(track["track_id"], 0.0))
            for track in document["tracks"]
        }
        control_scales = {
            track["track_id"]: (
                100.0 * math.exp(controls[int(track["receiver_id"])])
                if track["track_id"] in log_ratios else 100.0
            )
            for track in document["tracks"]
        }
        scores = {
            "fixed100": arm_score(document, engine, local, baseline_scales, slow),
            "receiver_constant": arm_score(document, engine, local, control_scales, slow),
            "track_variable": arm_score(document, engine, local, variable_scales, slow),
        }
        if abs(scores["fixed100"]["training"] - float(incumbent["score"])) > 1e-6:
            raise ValueError("fixed100 training score does not replay original IID")
        scans.append({
            "index": index,
            "session_id": entry["session_id"],
            "tracks": len(document["tracks"]),
            "strong_tracks": len(eligible),
            "attempted_cross_rx_pairs": attempted,
            "training_feature_pairs": len(pairs),
            "calibration_rule_pairs_with_3_held": sum(row["held_pairs"] >= 3 for row in pairs),
            "supported_tracks": len(log_ratios),
            "supported_rx0": len(by_receiver[0]),
            "supported_rx1": len(by_receiver[1]),
            "receiver_constant_log_ratios": controls,
            "variable_scale_min_hz": min(variable_scales.values()),
            "variable_scale_max_hz": max(variable_scales.values()),
            "scores": scores,
            "held_gain_variable_vs_fixed100": (
                scores["track_variable"]["held"] - scores["fixed100"]["held"]
            ),
            "held_gain_constant_vs_fixed100": (
                scores["receiver_constant"]["held"] - scores["fixed100"]["held"]
            ),
            "held_gain_variable_vs_constant": (
                scores["track_variable"]["held"] - scores["receiver_constant"]["held"]
            ),
            "pairs": pairs,
            "incumbent_sha256": digest(incumbent_path),
        })

    variable_control = [row["held_gain_variable_vs_constant"] for row in scans]
    result = {
        "schema": "ds11-rx-relative-scale-diagnostic/v1",
        "scope": "training-only features; fixed original IID endpoints; held used only for transfer score",
        "pairing": {
            "strong_iid_candidate_probability": STRONG_THRESHOLD,
            "identity": "same physical NORAD and exact RF within scan",
            "time": "mutual nearest within 1 microsecond",
            "feature_support": "at least 8 both-training pairs spanning at least 5 seconds",
            "feature": "max(1 Hz, 1.4826 * centered training RX-difference MAD)",
            "multiple_pairs": "median log feature per track",
            "unsupported": "relative scale 1",
            "control": "within-scan median log ratio per receiver on same supported tracks",
        },
        "coefficients": coefficients,
        "totals": {
            "scans": len(scans),
            "tracks": sum(row["tracks"] for row in scans),
            "strong_tracks": sum(row["strong_tracks"] for row in scans),
            "attempted_cross_rx_pairs": sum(row["attempted_cross_rx_pairs"] for row in scans),
            "training_feature_pairs": sum(row["training_feature_pairs"] for row in scans),
            "calibration_rule_pairs_with_3_held": sum(
                row["calibration_rule_pairs_with_3_held"] for row in scans
            ),
            "supported_tracks": sum(row["supported_tracks"] for row in scans),
            "scans_variable_beats_constant": sum(value > 0 for value in variable_control),
            "sum_held_gain_variable_vs_constant": sum(variable_control),
            "median_scan_held_gain_variable_vs_constant": statistics.median(variable_control),
            "sum_held_gain_variable_vs_fixed100": sum(
                row["held_gain_variable_vs_fixed100"] for row in scans
            ),
            "sum_held_gain_constant_vs_fixed100": sum(
                row["held_gain_constant_vs_fixed100"] for row in scans
            ),
        },
        "scans": scans,
        "source_sha256": {
            str(path): digest(path) for path in (
                Path(__file__), plan_path, CALIBRATION, SIDECAR,
                ROOT / "tools/ds7_baseline_adapter.py",
                ROOT / "tools/ds7_fast_baseline_adapter.py",
            )
        },
    }
    with (HERE / "diagnostic.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({
        "totals": result["totals"],
        "per_scan": [{key: row[key] for key in (
            "index", "tracks", "strong_tracks", "training_feature_pairs",
            "supported_tracks", "held_gain_variable_vs_constant",
        )} for row in scans],
    }, indent=2))


if __name__ == "__main__":
    main()
