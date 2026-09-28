"""Reconcile every decomposition and visualize assignment-stable losses."""

import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CROSS = HERE.parent / "2026_09_28_cross_dataset_position"
ledger = json.loads((CROSS / "scores.json").read_text())
all_selected = json.loads((CROSS / "all24/source-selection.json").read_text())["selected"]
summaries, strata, rows, composition = [], [], [], []
bindings = {}
for dataset in ("DS7", "DS8", "DS9"):
    target = HERE / dataset
    assert (target / "exit-code.txt").read_text().strip() == "0"
    for name, sha in json.loads((target / "seal.json").read_text())["sha256"].items():
        assert name not in bindings or bindings[name] == sha
        bindings[name] = sha
    data = json.loads((target / "result.json").read_text())
    summaries.extend(data["summaries"])
    strata.extend(data["strata"])
    rows.extend(data["rows"])
    for summary in data["summaries"]:
        unit = "all24" if summary["comparison"] == "all24" else "exclude_" + dataset
        source = next(r for r in ledger["rows"] if r["unit_id"] == unit)
        field = "source_held" if unit == "all24" else "target_held"
        expected = next(r for r in source[field]["datasets"] if r["dataset"] == dataset)
        assert abs(summary["held_delta"] - expected["held_delta_vs_original_panel"]) < 1e-7
        assert summary["held_observations"] == expected["held_observations"]
        for grouping in (["receiver"], ["channel"], ["receiver", "channel"], ["session_id"]):
            selected = [
                s
                for s in data["strata"]
                if s["comparison"] == summary["comparison"] and s["grouping"] == grouping
            ]
            assert sum(s["tracks"] for s in selected) == summary["tracks"]
            assert abs(sum(s["held_delta"] for s in selected) - summary["held_delta"]) < 1e-7
        selected = [r for r in data["rows"] if r["comparison"] == summary["comparison"]]
        ranked = sorted(
            selected, key=lambda r: (-max(-r["training_delta"], 0), r["session_id"], r["track_id"])
        )[: summary["top_decile_count"]]
        composition.append(
            {
                "dataset": dataset,
                "comparison": summary["comparison"],
                "training_ranked_held_observation_share": sum(r["held_count"] for r in ranked)
                / sum(r["held_count"] for r in selected),
                "training_ranked_training_observation_share": sum(
                    r["training_count"] for r in ranked
                )
                / sum(r["training_count"] for r in selected),
                "training_ranked_tracks": [
                    {
                        "session_id": r["session_id"],
                        "track_id": r["track_id"],
                        "training_delta": r["training_delta"],
                        "held_delta": r["held_delta"],
                    }
                    for r in ranked
                ],
            }
        )
for name, sha in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, name
gradient = np.sum(
    [s["position_gradient_sum"] for s in summaries if s["comparison"] == "all24"], axis=0
)
expected = np.array(all_selected["gradient"][:2])
assert np.max(np.abs(gradient - expected)) < 1e-5
for row in rows:
    assert math.isclose(
        row["held_delta"], row["new_held_score"] - row["old_held_score"], abs_tol=1e-10
    )
    assert math.isclose(
        row["training_delta"], row["new_training_score"] - row["old_training_score"], abs_tol=1e-10
    )
assert len(rows) == 2924
output = {
    "summaries": summaries,
    "strata": strata,
    "training_ranked_composition": composition,
    "audit": {
        "bindings": len(bindings),
        "paired_track_rows": len(rows),
        "aggregate_comparisons": 6,
        "all24_position_gradient": gradient.tolist(),
        "reported_gradient": expected.tolist(),
        "max_gradient_difference": float(np.max(np.abs(gradient - expected))),
    },
}
with (HERE / "scores.json").open("x") as stream:
    json.dump(output, stream, indent=2, allow_nan=False)
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
transfer = [s for s in summaries if s["comparison"] == "transfer"]
x = np.arange(3)
axes[0].bar(
    x - 0.18,
    [s["same_map_held_delta"] for s in transfer],
    width=0.34,
    label="Same MAP candidate",
    color="#51758c",
)
axes[0].bar(
    x + 0.18,
    [s["changed_map_held_delta"] for s in transfer],
    width=0.34,
    label="Changed MAP candidate",
    color="#d3992e",
)
axes[0].set_xticks(x, ["DS7", "DS8", "DS9"])
axes[0].set_ylabel("Excluded-dataset held score change (nats)")
axes[0].axhline(0, color="black", linewidth=0.8)
axes[0].legend()
matrix = np.zeros((2, 4))
for s in strata:
    if (
        s["dataset"] == "DS8"
        and s["comparison"] == "transfer"
        and s["grouping"] == ["receiver", "channel"]
    ):
        matrix[s["key"][0], s["key"][1] - 1] = s["held_delta"]
limit = np.max(np.abs(matrix))
axes[1].imshow(matrix, cmap="RdBu", vmin=-limit, vmax=limit, aspect="auto")
axes[1].set_xticks(range(4), ["Channel 1", "Channel 2", "Channel 3", "Channel 4"])
axes[1].set_yticks([0, 1], ["RX0", "RX1"])
for rx in range(2):
    for channel in range(4):
        axes[1].text(
            channel,
            rx,
            f"{matrix[rx, channel]:+.1f}",
            ha="center",
            va="center",
            color="white" if abs(matrix[rx, channel]) > limit * 0.6 else "black",
        )
axes[1].set_title("DS8 held changes by receiver/channel (nats)")
fig.suptitle("Transfer losses persist mainly within unchanged candidate assignments")
fig.savefig(HERE / "transfer-loss.png", dpi=160)
fig.savefig(HERE / "transfer-loss.svg")
print(json.dumps(output["audit"], indent=2))
