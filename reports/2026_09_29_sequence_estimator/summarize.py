"""Audit source bindings and display matched held-observation comparisons."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BASE = Path(__file__).resolve().parent


def main():
    primary_path = BASE / "results.json"
    p = json.loads(primary_path.read_text())
    f = json.loads((BASE / "followup-results.json").read_text())
    assert f["primary_sha256"] == hashlib.sha256(primary_path.read_bytes()).hexdigest()
    for bindings in [p["input_sha256"], f["source_sha256"]]:
        for path, expected in bindings.items():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
    assert len(p["rows"]) == len(f["rows"]) == 72
    keys = ["dataset", "receiver", "frame", "qualified"]
    for a, b in zip(p["rows"], f["rows"], strict=True):
        assert all(a[k] == b[k] for k in keys)
        assert all(arm["success"] for arm in a["arms"].values())
    comparisons = [
        ("Short support, free drift", "pilot", "sequence", p["rows"]),
        ("Short support, fixed drift", "pilot_fixed", "sequence_fixed", f["rows"]),
        ("Long pilot support, fixed drift", "pilot_long", "hybrid_long", f["rows"]),
    ]
    summary = []
    for title, baseline, candidate, rows in comparisons:
        for dataset in ["DS7", "DS8", "DS9"]:
            for qualified in [False, True]:
                subset = [
                    r for r in rows if r["dataset"] == dataset and (not qualified or r["qualified"])
                ]
                for metric in ["held_pilot_nmse", "held_sequence_nmse"]:
                    a = np.array([r["arms"][baseline][metric] for r in subset])
                    b = np.array([r["arms"][candidate][metric] for r in subset])
                    summary.append(
                        dict(
                            comparison=title,
                            dataset=dataset,
                            qualified_only=qualified,
                            metric=metric,
                            count=len(a),
                            baseline_median=float(np.median(a)),
                            candidate_median=float(np.median(b)),
                            median_paired_gain=float(np.median(a - b)),
                            candidate_wins=int(np.sum(b < a)),
                        )
                    )
    (BASE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
    for ax, (title, baseline, candidate, rows) in zip(axes, comparisons, strict=True):
        for dataset, color in zip(
            ["DS7", "DS8", "DS9"], ["#1674b8", "#dd8020", "#20876b"], strict=True
        ):
            subset = [r for r in rows if r["dataset"] == dataset]
            a = [r["arms"][baseline]["held_pilot_nmse"] for r in subset]
            b = [r["arms"][candidate]["held_pilot_nmse"] for r in subset]
            ax.scatter(a, b, label=dataset, color=color, s=24, alpha=0.75)
        ax.plot([0.4, 1.2], [0.4, 1.2], "--", color="gray", linewidth=1)
        ax.set(
            xlabel="Pilot-only held pilot NMSE",
            ylabel="Sequence-assisted held pilot NMSE",
            title=title,
            xlim=(0.4, 1.2),
            ylim=(0.4, 1.2),
        )
        ax.grid(alpha=0.15)
    axes[0].legend()
    fig.suptitle("72 receiver-frames, three previously examined visits • below diagonal is better")
    fig.savefig(BASE / "comparison.png", dpi=160)
    plt.close(fig)
    print("Input bindings, joins and optimizer statuses verified; summary and figure written.")


if __name__ == "__main__":
    main()
