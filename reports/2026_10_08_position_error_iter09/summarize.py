"""Compare constrained reference profiles and attribute score differences."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent


def main():
    labels = json.loads((HERE / "protocol.json").read_text())["labels"]
    cases = []
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), layout="constrained")
    for label, ax in zip(labels, axes.flat, strict=True):
        initial = json.loads((HERE / "results" / f"{label}.json").read_text())
        original_path = json.loads((HERE / "continuation" / f"{label}.json").read_text())
        path = json.loads((HERE / "retried" / f"{label}.json").read_text())
        arms = {}
        for arm in ("fitted-c", "zero-c"):
            selected = next(
                r for r in initial["rows"] if r["arm"] == arm and r["phase"] == "selected-fixed"
            )
            candidates = [
                (r["phase"], r)
                for r in initial["rows"]
                if r["arm"] == arm
                and r["phase"] in ("reference-warm", "reference-cold")
                and r["converged"]
            ]
            continuation = next(a for a in path["arms"] if a["arm"] == arm)
            steps = continuation["steps"]
            old_steps = next(a for a in original_path["arms"] if a["arm"] == arm)["steps"]
            if len(steps) == path["step_count"] and steps[-1]["converged"]:
                candidates.append(("continuation", steps[-1]))
            source, reference = min(candidates, key=lambda r: r[1]["objective"])
            delta = {
                k: reference["decomposition"][k] - selected["decomposition"][k]
                for k in (
                    "data_nll",
                    "common_penalty",
                    "relative_penalty",
                    "clock_penalty",
                    "total",
                )
            }
            groups = {
                g: v - selected["decomposition"]["grouped_nll"][g]
                for g, v in reference["decomposition"]["grouped_nll"].items()
            }
            np.testing.assert_allclose(sum(groups.values()), delta["data_nll"], atol=1e-7, rtol=0)
            arms[arm] = dict(
                reference_source=source,
                selected_error_km=selected["error_km"],
                delta=delta,
                grouped_data_delta=groups,
                group_counts=initial["group_counts"],
                path_completed=len(steps) == path["step_count"] and steps[-1]["converged"],
                original_path_completed=(
                    len(old_steps) == original_path["step_count"] and old_steps[-1]["converged"]
                ),
                retries=sum(len(r["attempts"]) - 1 for r in steps),
                reference_stationarity=reference["stationarity"],
                direct_scores={
                    r["phase"]: r["objective"] for r in initial["rows"] if r["arm"] == arm
                },
                continuation_endpoint_score=steps[-1]["objective"],
                released=continuation["released"],
            )
            ax.plot(
                [0] + [r["fraction"] for r in steps],
                [0] + [r["objective"] - selected["objective"] for r in steps],
                "o-",
                markersize=3,
                label=arm,
            )
        ax.set(
            title=label,
            xlabel="Fraction of path from selected position to reference",
            ylabel="Score minus selected-position score",
        )
        ax.axhline(0, color="black", linewidth=0.7)
        ax.grid(alpha=0.2)
        ax.legend()
        cases.append(dict(label=label, arms=arms))
    fig.savefig(HERE / "profile-paths.png", dpi=160)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    for case, ax in zip(cases, axes.flat, strict=True):
        groups = case["arms"]["fitted-c"]["grouped_data_delta"]
        keys = sorted(groups, key=lambda k: abs(groups[k]), reverse=True)[:8]
        values = [groups[k] for k in keys]
        ax.barh(
            ["unassigned" if k == "0" else k for k in keys],
            values,
            color=["tab:red" if v > 0 else "tab:blue" for v in values],
        )
        ax.invert_yaxis()
        ax.axvline(0, color="black", linewidth=0.7)
        ax.set(title=case["label"], xlabel="Reference minus selected data NLL (fitted-c)")
        ax.grid(axis="x", alpha=0.2)
    fig.savefig(HERE / "group-attribution.png", dpi=160)
    (HERE / "summary.json").write_text(json.dumps(dict(cases=cases), indent=2) + "\n")
    for c in cases:
        for arm, r in c["arms"].items():
            print(
                c["label"],
                arm,
                r["reference_source"],
                r["delta"],
                "path",
                r["path_completed"],
                "released",
                r["released"]["error_km"] if r["released"] else None,
            )


if __name__ == "__main__":
    main()
