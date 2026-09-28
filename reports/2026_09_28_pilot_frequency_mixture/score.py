"""All-window paired predictive scores and declared prerequisite checks."""

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
summaries, windows = [], []
for dataset in ("DS7", "DS8", "DS9"):
    target = HERE / dataset
    launch = json.loads((target / "launch.json").read_text())
    for path, sha in launch["sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha, path
    if (target / "exit-code.txt").read_text().strip() != "0":
        summaries.append({"dataset": dataset, "state": "failed"})
        continue
    result = json.loads((target / "result.json").read_text())
    assert (
        hashlib.sha256((target / "posterior.npz").read_bytes()).hexdigest()
        == result["posterior_sha256"]
    )
    rows = result["rows"]
    assert len(rows) == 56
    posterior = np.load(target / "posterior.npz", allow_pickle=False)
    for row in rows:
        weights = posterior[row["matrix_key"] + "_weights"]
        assert abs(weights.sum() - 1) <= 1e-12
        assert np.all(weights >= 0)
        assert 0 <= row["signal_probability"] <= 1
    groups = sorted({r["window_index"] for r in rows})
    for index in groups:
        selected = [r for r in rows if r["window_index"] == index]
        for name in selected[0]["arms"]:
            windows.append(
                {
                    "dataset": dataset,
                    "window_index": index,
                    "receiver": selected[0]["receiver_id"],
                    "visit": selected[0]["visit_index"],
                    "method": name,
                    "frames": len(selected),
                    "held_gain_vs_fixed_zero_nats_per_frame": float(
                        np.mean(
                            [
                                r["arms"][name]["real"]["log_density"]
                                - r["arms"]["fixed_zero"]["real"]["log_density"]
                                for r in selected
                            ]
                        )
                    ),
                    "held_gain_vs_noise_nats_per_frame": float(
                        np.mean([r["arms"][name]["real"]["log_ratio_to_noise"] for r in selected])
                    ),
                    "scrambled_gain_vs_noise_nats_per_frame": float(
                        np.mean(
                            [r["arms"][name]["scrambled"]["log_ratio_to_noise"] for r in selected]
                        )
                    ),
                    "mean_signal_probability": float(
                        np.mean([r["signal_probability"] for r in selected])
                    ),
                    "strong_signal_frames": sum(r["signal_probability"] > 0.99 for r in selected),
                    "weak_signal_frames": sum(r["signal_probability"] < 0.01 for r in selected),
                }
            )
    injections = [i for r in rows for i in r["injections"]]
    reliable = [i for i in injections if i["reliable_pair"]]
    reliable_max = max((abs(i["fixed_domain_mean_error_hz"]) for i in reliable), default=None)
    arms = {}
    for method in rows[0]["arms"]:
        selected = [w for w in windows if w["dataset"] == dataset and w["method"] == method]
        arms[method] = {
            k: float(np.mean([w[k] for w in selected]))
            for k in (
                "held_gain_vs_fixed_zero_nats_per_frame",
                "held_gain_vs_noise_nats_per_frame",
                "scrambled_gain_vs_noise_nats_per_frame",
            )
        }
        arms[method]["positive_windows_vs_fixed_zero"] = sum(
            w["held_gain_vs_fixed_zero_nats_per_frame"] > 0 for w in selected
        )
    new = arms["frequency_mixture_null"]
    summaries.append(
        {
            "dataset": dataset,
            "state": "returned",
            "frames": len(rows),
            "windows": len(groups),
            "strong_signal_frames": sum(r["signal_probability"] > 0.99 for r in rows),
            "weak_signal_frames": sum(r["signal_probability"] < 0.01 for r in rows),
            "arms": arms,
            "translated_domain_checks": len(injections),
            "max_translated_error": max(
                max(
                    i[k]
                    for k in (
                        "translated_weight_error",
                        "translated_evidence_error",
                        "translated_density_error",
                    )
                )
                for i in injections
            ),
            "reliable_pairs": len(reliable),
            "max_reliable_shift_error_hz": reliable_max,
            "max_all_shift_error_hz": max(abs(i["fixed_domain_mean_error_hz"]) for i in injections),
            "prerequisite_passed": new["held_gain_vs_fixed_zero_nats_per_frame"] > 0
            and new["held_gain_vs_noise_nats_per_frame"] > 0
            and reliable_max is not None
            and reliable_max <= 5,
        }
    )
output = {"summaries": summaries, "windows": windows}
with (HERE / "scores.json").open("x") as stream:
    json.dump(output, stream, indent=2, allow_nan=False)
print(json.dumps(summaries, indent=2))
