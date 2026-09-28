"""Describe history horizons and conditional nominee motion separation."""

import hashlib
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def summarize(panel):
    path = HERE / f"{panel}.json"
    data_path = ROOT / "reports" / (
        "2026_09_28_rx_geometry_association" if panel == "pilot"
        else "2026_09_28_rx_ds8_confirmation"
    ) / "dataset.json"
    payload = path.read_bytes()
    result = json.loads(payload)
    data = json.loads(data_path.read_text())
    priors = {}
    for lane in data["lanes"]:
        if lane["recording_split"] != "evaluation":
            continue
        key = json.dumps(lane["lane"], sort_keys=True)
        logs = [c["log_prior"] for c in lane["components"][:-1]]
        maximum = max(x for x in logs if x is not None)
        weights = [0.0 if x is None else math.exp(x - maximum) for x in logs]
        total = math.fsum(weights)
        priors[key] = (lane["alias_period_hz"], [x / total for x in weights])
    output = {}
    for role in ("reception", "held_frequency"):
        horizons, spreads = [], []
        total_rows = 0
        for sid in result["evaluation_sessions"]:
            for lane in result["orbit_increment_diagnostics"][f"{sid}:D"]:
                period, weights = priors[json.dumps(lane["lane"], sort_keys=True)]
                for receiver in lane["receivers"]:
                    for window in receiver["windows"]:
                        if window["role"] != role:
                            continue
                        total_rows += 1
                        nominees = window["nominees"]
                        if nominees[0]["mode"] != "orbit_increment":
                            continue
                        horizons.append(nominees[0]["forecast_horizon_s"])
                        delta = [n["motion_delta_hz"] for n in nominees]
                        sine = math.fsum(w * math.sin(2 * math.pi * d / period)
                                         for w, d in zip(weights, delta, strict=True))
                        cosine = math.fsum(w * math.cos(2 * math.pi * d / period)
                                           for w, d in zip(weights, delta, strict=True))
                        center = math.atan2(sine, cosine) * period / (2 * math.pi)
                        variance = math.fsum(
                            w * ((d - center + period / 2) % period - period / 2) ** 2
                            for w, d in zip(weights, delta, strict=True)
                        )
                        spreads.append(math.sqrt(variance) / nominees[0]["sigma_hz"])
        output[role] = {
            "receiver_windows": total_rows,
            "recent_history_receiver_windows": len(horizons),
            "median_horizon_s": statistics.median(horizons),
            "median_prior_weighted_motion_spread_over_sigma": statistics.median(spreads),
        }
    return {"source_sha256": hashlib.sha256(payload).hexdigest(), "roles": output}


def main():
    with (HERE / "history-summary.json").open("x") as stream:
        json.dump({p: summarize(p) for p in ("pilot", "ds8")}, stream,
                  indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
