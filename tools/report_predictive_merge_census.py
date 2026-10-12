"""Publish compact receipts and plots for the complete nested curve census."""

import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from band_calibrated_merge_study import REPORT
from continuous_merge_study import sha, write
from predictive_merge_census import OUTPUT, verify

PUBLIC = REPORT / "predictive-curves"


def main():
    protocol_path = OUTPUT / "protocol.json"
    protocol = json.loads(protocol_path.read_bytes())
    verify(protocol["bindings"])
    cases, summary = [], []
    seal = {}
    for member in protocol["cases"]:
        path = OUTPUT / member["dataset"] / (member["session_id"] + ".json")
        if not path.exists():
            raise ValueError("complete pinned census required: " + member["session_id"])
        verify(member["bindings"])
        data = json.loads(path.read_bytes())
        if data["protocol_sha256"] != sha(protocol_path):
            raise ValueError("numerical result belongs to another predictive protocol")
        seal[str(path)] = sha(path)
        rows = []
        for item in data["rows"]:
            record = {k: item[k] for k in ("component", "status", "reason")}
            if item["status"] == "complete":
                comparison = item["comparison"]
                record["prediction"] = {
                    k: comparison[k]
                    for k in ("rows", "seed", "repeat_rms_hz", "rms_hz", "joined_gain_hz")
                }
                record["outer_folds"] = [
                    {
                        "repeat": fold["repeat"],
                        "fold": fold["fold"],
                        "test_blocks": fold["test_blocks"],
                        "models": {
                            mode: {k: model[k] for k in ("degree", "inner_scores", "held_rms_hz")}
                            for mode, model in fold["models"].items()
                        },
                    }
                    for fold in comparison["folds"]
                ]
            rows.append(record)
        cases.append(
            {
                "dataset": member["dataset"],
                "session_id": member["session_id"],
                "role": member["role"],
                "numerical_result_sha256": sha(path),
                "rows": rows,
            }
        )
    for dataset in ("DS20", "DS16"):
        for role in ("development", "validation"):
            members = [c for c in cases if c["dataset"] == dataset and c["role"] == role]
            rows = [r for c in members for r in c["rows"]]
            completed = [r for r in rows if r["status"] == "complete"]
            gains = np.array([r["prediction"]["joined_gain_hz"] for r in completed])
            summary.append(
                {
                    "dataset": dataset,
                    "role": role,
                    "recordings": len(members),
                    "components": len(rows),
                    "complete_components": len(completed),
                    "failed_components": len(rows) - len(completed),
                    "failure_reasons": dict(
                        Counter(r["reason"] for r in rows if r["status"] != "complete")
                    ),
                    "positive_gain_components": int(sum(gains > 0)),
                    "gain_over_5hz_components": int(sum(gains > 5)),
                    "gain_below_minus_5hz_components": int(sum(gains < -5)),
                    "median_gain_hz": float(np.median(gains)) if len(gains) else None,
                }
            )
    anchors_path = OUTPUT / "anchors.json"
    anchors = json.loads(anchors_path.read_bytes())
    anchor_summary = [
        {
            "label": r["label"],
            "input_sha256": r["input_sha256"],
            "status": r["status"],
            "reason": r["reason"],
            "rms_hz": r.get("comparison", {}).get("rms_hz"),
            "joined_gain_hz": r.get("comparison", {}).get("joined_gain_hz"),
        }
        for r in anchors["rows"]
    ]
    seal[str(anchors_path)] = sha(anchors_path)
    probe_path = OUTPUT / "clock-shape-probe.json"
    probe = json.loads(probe_path.read_bytes())
    verify(probe["bindings"])
    seal[str(probe_path)] = sha(probe_path)
    write(PUBLIC / "clock-shape-probe.json", probe)
    write(PUBLIC / "protocol.json", protocol)
    write(PUBLIC / "numerical-seal.json", seal)
    (PUBLIC / "results.json").write_text(
        json.dumps(
            {
                "cases": cases,
                "summary": summary,
                "anchors": anchor_summary,
                "script_sha256": sha(Path(__file__)),
                "protocol_sha256": sha(protocol_path),
                "scope": protocol["scope"],
                "reference_usage": "none",
            },
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    )
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), constrained_layout=True)
    for column, dataset in enumerate(("DS20", "DS16")):
        for role, color in (("development", "#1679ac"), ("validation", "#d87814")):
            rows = [
                r
                for c in cases
                if c["dataset"] == dataset and c["role"] == role
                for r in c["rows"]
                if r["status"] == "complete"
            ]
            separate = [r["prediction"]["rms_hz"]["separate"] for r in rows]
            joined = [r["prediction"]["rms_hz"]["joined"] for r in rows]
            axes[0, column].scatter(separate, joined, label=role, color=color, alpha=0.55, s=24)
        axis = axes[0, column]
        axis.set_xscale("log")
        axis.set_yscale("log")
        low = min(axis.get_xlim()[0], axis.get_ylim()[0])
        high = max(axis.get_xlim()[1], axis.get_ylim()[1])
        axis.plot([low, high], [low, high], color="black", lw=0.8)
        axis.set(
            xlabel="Separate curves: outer held-out RMS (Hz)",
            ylabel="Joined curve: outer held-out RMS (Hz)",
            title=dataset,
        )
        axis.legend()
        items = [s for s in summary if s["dataset"] == dataset]
        positions = np.arange(len(items))
        axes[1, column].bar(
            positions,
            [s["positive_gain_components"] for s in items],
            label="Joined predicts better",
        )
        not_better = [s["complete_components"] - s["positive_gain_components"] for s in items]
        axes[1, column].bar(
            positions,
            not_better,
            bottom=[s["positive_gain_components"] for s in items],
            label="Separate predicts as well or better",
        )
        axes[1, column].bar(
            positions,
            [s["failed_components"] for s in items],
            bottom=[s["complete_components"] for s in items],
            label="Insufficient nested training support",
            color="#999999",
        )
        axes[1, column].set_xticks(positions, [s["role"] for s in items])
        axes[1, column].set(ylabel="Final guarded components", title="Every component retained")
        axes[1, column].legend(fontsize=8)
    for axis in axes.flat:
        axis.grid(alpha=0.2)
    fig.suptitle(
        "Nested curve prediction on all 18 DS20 and 63 DS16 recordings\n"
        "Conditional on existing component membership; no position or identity validation"
    )
    fig.savefig(PUBLIC / "nested-curve-census.png", dpi=180)
    plt.close(fig)
    fig, axis = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
    labels = ["No drift", "Original seed", "Original coarse", "Joined seed", "Joined coarse"]
    axis.bar(range(len(labels)), [r["changed_original_preferences"] for r in probe["rows"]])
    axis.set_xticks(range(len(labels)), labels)
    axis.set(
        ylabel="Changed original-track candidate preferences (of 24)",
        title="Orbital-shape profiling depends on common receiver drift",
    )
    axis.grid(alpha=0.2)
    fig.suptitle(
        "DS20 sparse case · same point, catalogue and proposal pool\n"
        "Existing in-sample slope states; no position re-fit"
    )
    fig.savefig(PUBLIC / "clock-shape-candidates.png", dpi=180)
    plt.close(fig)
    sparse = next(c for c in cases if c["session_id"] == "fast-43ce59233fe914e1d273ee584efcd405")
    sparse_ch2 = next(r for r in sparse["rows"] if r["component"]["lane"][:3] == [2, "lower", 1])
    write(
        PUBLIC / "sparse-regression.json",
        {
            "session_id": sparse["session_id"],
            "result_sha256": sparse["numerical_result_sha256"],
            "component": sparse_ch2,
            "reference_usage": "none",
            "scope": (
                "Better conditional curve prediction in the previously reported position "
                "regression case is not a geographic improvement."
            ),
        },
    )
    print(
        json.dumps(
            {"summary": summary, "anchors": anchor_summary, "sparse_ch2": sparse_ch2["prediction"]},
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
