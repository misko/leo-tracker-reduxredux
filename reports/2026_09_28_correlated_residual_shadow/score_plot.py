"""Training-only covariance selection, paired held scoring and descriptive plots."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
datasets = ("DS7", "DS8", "DS9")
results, bindings = {}, {}
for dataset in datasets:
    target = HERE / dataset
    assert (target / "exit-code.txt").read_text().strip() == "0"
    data = json.loads((target / "result.json").read_text())
    results[dataset] = data
    for path, sha in json.loads((target / "seal.json").read_text())["sha256"].items():
        assert path not in bindings or bindings[path] == sha
        bindings[path] = sha
    for arm in data["arms"]:
        rows = [r for r in data["rows"] if r["arm"] == arm["id"]]
        for field in ("train", "held"):
            assert abs(sum(r[field] for r in rows) - arm[field]) < 1e-7
        assert len({(r["session_id"], r["track_id"]) for r in rows}) == len(rows)
for path, sha in bindings.items():
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha

arm_scores = {ds: {a["id"]: a for a in data["arms"]} for ds, data in results.items()}
selections = []
for ds in datasets:
    for mode in ("within_dataset", "donor_datasets"):
        donors = [ds] if mode == "within_dataset" else [d for d in datasets if d != ds]
        chosen = {}
        for family in ("iid", "shared_scale", "correlated"):
            candidates = [
                a
                for a in results[ds]["arms"]
                if (family == "iid" and a["family"] == "iid")
                or (family == "shared_scale" and a["family"] == "mvt" and a["decay_s"] == 0)
                or (family == "correlated" and a["family"] == "mvt" and a["decay_s"] > 0)
            ]
            chosen[family] = max(
                candidates, key=lambda a: sum(arm_scores[d][a["id"]]["train"] for d in donors)
            )
        original = arm_scores[ds]["iid_s100_t0"]
        correlated = chosen["correlated"]
        same_scale = arm_scores[ds][f"mvt_s{correlated['scale']}_t0"]
        paired = []
        for session in sorted({r["session_id"] for r in results[ds]["rows"]}):

            def held(arm_id, ds=ds, session=session):
                return sum(
                    r["held"]
                    for r in results[ds]["rows"]
                    if r["session_id"] == session and r["arm"] == arm_id
                )

            paired.append(
                {
                    "session_id": session,
                    "vs_original": held(correlated["id"]) - held(original["id"]),
                    "vs_shared_scale": held(correlated["id"]) - held(chosen["shared_scale"]["id"]),
                    "vs_same_scale": held(correlated["id"]) - held(same_scale["id"]),
                }
            )
        selections.append(
            {
                "dataset": ds,
                "selection": mode,
                "training_datasets": donors,
                "selected": chosen,
                "correlated_vs_original": correlated["held"] - original["held"],
                "correlated_vs_selected_shared_scale": correlated["held"]
                - chosen["shared_scale"]["held"],
                "correlated_vs_same_scale": correlated["held"] - same_scale["held"],
                "paired_records": paired,
            }
        )

variograms = []
for ds, data in results.items():
    for bin_id in range(6):
        rows = [r for r in data["variograms"] if r["bin"] == bin_id]
        count = sum(r["pairs"] for r in rows)
        empirical = sum(r["squared_difference_sum"] for r in rows)
        shuffled = sum(r["shuffled_squared_difference_sum"] for r in rows)
        variograms.append(
            {
                "dataset": ds,
                "bin": bin_id,
                "pairs": count,
                "semivariance": empirical / (2 * count) if count else None,
                "shuffled_semivariance": shuffled / (2 * count) if count else None,
                "ratio_to_shuffle": empirical / shuffled if shuffled else None,
            }
        )
gate = all(
    s["correlated_vs_selected_shared_scale"] > 0 and s["correlated_vs_same_scale"] > 0
    for s in selections
)
scores = {
    "selections": selections,
    "variograms": variograms,
    "correlation_screen_pass": gate,
    "execution_bindings_verified": len(bindings),
    "track_arm_rows": sum(len(d["rows"]) for d in results.values()),
}
(HERE / "scores.json").write_text(json.dumps(scores, indent=2, allow_nan=False) + "\n")
with (HERE / "all-arms.csv").open("w") as stream:
    writer = csv.DictWriter(
        stream,
        fieldnames=[
            "dataset",
            "id",
            "family",
            "scale",
            "decay_s",
            "train",
            "held",
            "held_vs_original",
        ],
    )
    writer.writeheader()
    for ds in datasets:
        for arm in results[ds]["arms"]:
            writer.writerow(
                {
                    "dataset": ds,
                    **arm,
                    "held_vs_original": arm["held"] - arm_scores[ds]["iid_s100_t0"]["held"],
                }
            )

fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout="constrained")
xs = np.arange(3)
for offset, mode, label in (
    (-0.18, "within_dataset", "Target training selection"),
    (0.18, "donor_datasets", "Other datasets' training selection"),
):
    vals = [s["correlated_vs_selected_shared_scale"] for s in selections if s["selection"] == mode]
    axes[0].bar(xs + offset, vals, width=0.36, label=label)
axes[0].set_xticks(xs, datasets)
axes[0].axhline(0, color="black", lw=0.7)
axes[0].set_ylabel("Held gain vs selected shared-scale control (nats)")
axes[0].set_title("Does temporal correlation add predictive value?")
axes[0].legend(fontsize=8)
for ds in datasets:
    vals = [v["ratio_to_shuffle"] for v in variograms if v["dataset"] == ds and v["bin"] > 0]
    axes[1].plot(np.arange(5), vals, marker="o", label=ds)
axes[1].axhline(1, color="black", lw=0.7, linestyle="--")
axes[1].set_xticks(np.arange(5), ["(0,1]", "(1,5]", "(5,20]", "(20,60]", ">60"])
axes[1].set_xlabel("Within-track training-pair lag (seconds)")
axes[1].set_ylabel("Clipped residual semivariance / shuffled value")
axes[1].set_title("Training-only temporal structure (descriptive)")
axes[1].legend()
fig.suptitle("Fixed positions and offsets · all 24 records · no new geographic result")
fig.savefig(HERE / "covariance-shadow.png", dpi=170)
fig.savefig(HERE / "covariance-shadow.svg")
print(json.dumps(scores, indent=2))
