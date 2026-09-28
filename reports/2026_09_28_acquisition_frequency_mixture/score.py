"""Independent component-evidence audit and paired window scoring."""

import ast
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
mapping = {
    r["original_path"]: r for r in json.loads((HERE / "executed-source-map.json").read_text())
}
for row in mapping.values():
    assert ast.dump(ast.parse((ROOT / row["original_path"]).read_text())) == ast.dump(
        ast.parse((ROOT / row["archived_path"]).read_text())
    )


def lse(values):
    # Independent reduction instead of the production maximum/sum implementation.
    return float(np.logaddexp.reduce(values))


summaries, windows, checks = [], [], []
for dataset in ("DS7", "DS8", "DS9"):
    target = HERE / dataset
    launch = json.loads((target / "launch.json").read_text())
    for name, sha in launch["sha256"].items():
        path = mapping[name]["archived_path"] if name in mapping else name
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha, name
    if (target / "exit-code.txt").read_text().strip() != "0":
        summaries.append({"dataset": dataset, "state": "failed"})
        continue
    result = json.loads((target / "result.json").read_text())
    rows = result["rows"]
    assert len(rows) == 56 and result["replayed_predictions"] == 560
    for row in rows:
        for method, prior in (
            ("acquisition_broad", [0.5, 0.5]),
            ("acquisition_broad_null", [0.25, 0.25, 0.5]),
        ):
            evidence = np.asarray(row["training_log_evidence"][: len(prior)])
            joint = evidence + np.log(prior)
            weights = np.exp(joint - lse(joint))
            assert np.allclose(
                weights, row["arms"][method]["component_weights"], rtol=1e-10, atol=1e-12
            )
            for label in ("real", "scrambled"):
                predictions = [
                    row["old_arms"][n][label]["log_ratio_to_noise"]
                    for n in ("fixed_zero", "frequency_mixture")
                ] + [0.0]
                expected = lse(joint + predictions[: len(prior)]) - lse(joint)
                error = abs(expected - row["arms"][method][label + "_log_ratio_to_noise"])
                assert error <= 1e-10
                checks.append(error)
    for method in rows[0]["arms"]:
        for wi in range(4):
            group = [r for r in rows if r["window_index"] == wi]
            arm = [r["arms"][method] for r in group]
            windows.append(
                {
                    "dataset": dataset,
                    "method": method,
                    "window": wi,
                    "visit": group[0]["visit_index"],
                    "receiver": group[0]["receiver_id"],
                    "gain_vs_acquisition": float(
                        np.mean(
                            [
                                a["real_log_ratio_to_noise"]
                                - r["old_arms"]["fixed_zero"]["real"]["log_ratio_to_noise"]
                                for a, r in zip(arm, group, strict=True)
                            ]
                        )
                    ),
                    "gain_vs_broad_null": float(
                        np.mean(
                            [
                                a["real_log_ratio_to_noise"]
                                - r["old_arms"]["frequency_mixture_null"]["real"][
                                    "log_ratio_to_noise"
                                ]
                                for a, r in zip(arm, group, strict=True)
                            ]
                        )
                    ),
                    "gain_vs_noise": float(np.mean([a["real_log_ratio_to_noise"] for a in arm])),
                    "scrambled_vs_noise": float(
                        np.mean([a["scrambled_log_ratio_to_noise"] for a in arm])
                    ),
                    "mean_component_weights": np.mean(
                        [a["component_weights"] for a in arm], axis=0
                    ).tolist(),
                }
            )
        selected = [w for w in windows if w["dataset"] == dataset and w["method"] == method]
        injections = [i for r in rows for i in r["arms"][method]["injections"]]
        reliable = [i for i in injections if i["reliable_pair"]]
        summary = {
            "dataset": dataset,
            "method": method,
            "frames": len(rows),
            "windows": len(selected),
        }
        summary.update(
            {
                k: float(np.mean([w[k] for w in selected]))
                for k in (
                    "gain_vs_acquisition",
                    "gain_vs_broad_null",
                    "gain_vs_noise",
                    "scrambled_vs_noise",
                )
            }
        )
        summary.update(
            {
                "positive_windows_vs_acquisition": sum(
                    w["gain_vs_acquisition"] > 0 for w in selected
                ),
                "reliable_pairs": len(reliable),
                "all_pairs": len(injections),
                "reliable_failures_over_5hz": sum(
                    abs(i["fixed_mean_shift_error_hz"]) > 5 for i in reliable
                ),
                "max_reliable_shift_error_hz": max(
                    abs(i["fixed_mean_shift_error_hz"]) for i in reliable
                ),
                "max_all_shift_error_hz": max(
                    abs(i["fixed_mean_shift_error_hz"]) for i in injections
                ),
                "translated_max_error": max(i["translated_max_error"] for i in injections),
            }
        )
        summary["prerequisite_passed"] = (
            summary["gain_vs_acquisition"] > 0
            and summary["gain_vs_noise"] > 0
            and summary["max_reliable_shift_error_hz"] <= 5
        )
        summaries.append(summary)
output = {
    "summaries": summaries,
    "windows": windows,
    "audit": {
        "predictions_checked": len(checks),
        "max_absolute_error": max(checks),
        "ast_identical_final_sources": 2,
    },
}
with (HERE / "scores.json").open("x") as stream:
    json.dump(output, stream, indent=2, allow_nan=False)
print(json.dumps({"summaries": summaries, "audit": output["audit"]}, indent=2))
