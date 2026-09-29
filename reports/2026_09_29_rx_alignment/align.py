"""Omitted-pair receiver alignment from training frequency curves only."""

import math

import numpy as np

MODELS = ("median", "constant", "drift", "slope", "both", "drift_permuted", "slope_permuted")


def feature(pair):
    mask = np.asarray(pair["training"], bool)
    t = np.asarray(pair["times_s"])[mask]
    y = (np.asarray(pair["rx0_hz"])[mask] + np.asarray(pair["rx1_hz"])[mask]) / 2
    if len(t) < 5 or np.ptp(t) < 5:
        return {"qualified": False, "reason": "insufficient_training"}
    center = float(np.median(t))
    z = (t - center) / 10
    design = np.column_stack([np.ones(len(t)), z, z * z])
    cond = float(np.linalg.cond(design))
    if np.linalg.matrix_rank(design) != 3 or cond > 1e4:
        return {"qualified": False, "reason": "polynomial_rank", "condition": cond}
    coefficients = np.linalg.lstsq(design, y - y.mean(), rcond=None)[0]
    return {
        "qualified": True,
        "center_s": center,
        "slope_hz_s": float(coefficients[1] / 10),
        "acceleration_hz_s2": float(2 * coefficients[2] / 100),
        "condition": cond,
    }


def fit(donors, features, model):
    if len(donors) < 4:
        return {"qualified": False, "reason": "fewer_than_four_donors", "donors": len(donors)}
    if not all(f["qualified"] for f in features):
        return {"qualified": False, "reason": "donor_polynomial_unqualified", "donors": len(donors)}
    y = np.array([p["offset_hz"] for p in donors])
    t = np.array([f["center_s"] for f in features])
    s = np.array([f["slope_hz_s"] for f in features])
    reference = float(np.mean(t))
    columns = [np.ones(len(t))]
    use_time = model in ("drift", "both", "drift_permuted")
    use_slope = model in ("slope", "both", "slope_permuted")
    if model == "drift_permuted":
        t = np.roll(t, 1)
    if model == "slope_permuted":
        s = np.roll(s, 1)
    if use_time:
        columns.append((t - reference) / 100)
    if use_slope:
        columns.append(s / 1000)
    design = np.column_stack(columns)
    cond = float(np.linalg.cond(design))
    if np.linalg.matrix_rank(design) != design.shape[1] or cond > 1000:
        return {
            "qualified": False,
            "reason": "alignment_rank",
            "donors": len(donors),
            "condition": cond,
        }
    beta = np.linalg.lstsq(design, y, rcond=None)[0]
    intercept = float(np.median(y)) if model == "median" else float(beta[0])
    drift = float(beta[1] / 100) if use_time else 0.0
    lag = float(beta[-1] / 1000) if use_slope else 0.0
    passed = abs(drift) <= 20 and abs(lag) <= 5
    return {
        "qualified": passed,
        "reason": "qualified" if passed else "coefficient_bound",
        "donors": len(donors),
        "condition": cond,
        "reference_s": reference,
        "intercept_hz": intercept,
        "drift_hz_s": drift,
        "slope_coefficient_s": lag,
    }


def predict(fitted, target_feature, times):
    times = np.asarray(times)
    slope = target_feature["slope_hz_s"] + target_feature["acceleration_hz_s2"] * (
        times - target_feature["center_s"]
    )
    return (
        fitted["intercept_hz"]
        + fitted["drift_hz_s"] * (times - fitted["reference_s"])
        + fitted["slope_coefficient_s"] * slope
    )


def logscore(residual):
    r = np.asarray(residual)
    scale = math.sqrt(20000)
    return float(
        np.sum(
            math.lgamma(2.5)
            - math.lgamma(2)
            - 0.5 * math.log(4 * math.pi)
            - math.log(scale)
            - 2.5 * np.log1p(r * r / 80000)
        )
    )


def analyze(scan):
    pairs = sorted([p for p in scan["pairs"] if p["selected"]], key=lambda p: (p["rx0"], p["rx1"]))
    features = [feature(p) for p in pairs]
    rows = []
    for i, pair in enumerate(pairs):
        indices = [
            j
            for j, p in enumerate(pairs)
            if j != i and p["channel"] == pair["channel"] and p["rf_hz"] == pair["rf_hz"]
        ]
        donors = [pairs[j] for j in indices]
        df = [features[j] for j in indices]
        row = {
            "rx0": pair["rx0"],
            "rx1": pair["rx1"],
            "channel": pair["channel"],
            "rf_hz": pair["rf_hz"],
            "feature": features[i],
            "donor_ids": [(p["rx0"], p["rx1"]) for p in donors],
            "held_available": pair["evaluation"]["held_available"],
            "models": {},
        }
        held = np.asarray(pair["held"], bool)
        times = np.asarray(pair["times_s"])[held]
        delta = np.asarray(pair["difference_hz"])[held]
        for name in MODELS:
            fitted = fit(donors, df, name)
            row["models"][name] = {"fit": fitted}
            if not features[i]["qualified"] or not fitted["qualified"] or not row["held_available"]:
                continue
            prediction = predict(fitted, features[i], times)
            r = delta - prediction
            row["models"][name]["held"] = {
                "prediction_hz": prediction.tolist(),
                "count": len(r),
                "median_abs_hz": float(np.median(abs(r))),
                "p90_abs_hz": float(np.quantile(abs(r), 0.9)),
                "shape_pass": bool(np.median(abs(r)) <= 100 and np.quantile(abs(r), 0.9) <= 300),
                "log_score": logscore(r),
            }
        rows.append(row)
    return {"session_id": scan["session_id"], "dataset": scan["dataset"], "rows": rows}
