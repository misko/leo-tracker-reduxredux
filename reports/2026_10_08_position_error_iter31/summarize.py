"""Report oracle branch diagnostics without converting them into operational accuracy."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from branch import error_km  # noqa: E402

from leo.contracts.regional_position import RegionalPrior  # noqa: E402

HERE = Path(__file__).resolve().parent


def main():
    cases = {}
    stages = (
        "region",
        "joint-100",
        "remove-5",
        "post-200",
        "drift-50",
        "control-refit",
        "slope-0.25",
    )
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), layout="constrained")
    for ax, name in zip(axes, ("retained", "discarded"), strict=True):
        raw = json.loads((HERE / "results" / f"{name}.json").read_text())
        result = dict(arms={}, regional_starts=[], removed=raw["upstream"].get("removed", []))
        for row in raw["receipt"]["regional_fits"]:
            fit = row["fit"]
            result["regional_starts"].append(
                dict(
                    arm=row["arm"],
                    start=row["start"],
                    converged=fit["converged"],
                    error_km=error_km(RegionalPrior(), fit["vector"], raw["document"]),
                    objective=fit["objective"],
                    stationarity=fit["stationarity"],
                )
            )
        for arm in ("fitted-c", "zero-c"):
            chosen = next(
                a["selected"] for a in raw["document"]["methods"][0]["arms"] if a["name"] == arm
            )
            sequence = dict(
                region=dict(
                    error_km=chosen["horizontal_error_m"] / 1000,
                    objective=chosen["objective"],
                    converged=chosen["converged"],
                    rms_hz=chosen["posterior_rms_hz"],
                )
            )
            for s, rows in {**raw["upstream"]["stages"], **raw["extended"]["stages"]}.items():
                r = rows[arm]
                sequence[s] = dict(
                    error_km=r["error_km"],
                    objective=r["objective"],
                    converged=r["converged"],
                    rms_hz=r["posterior_rms_hz"],
                )
            result["arms"][arm] = sequence
            ax.plot(stages, [sequence[s]["error_km"] for s in stages], marker="o", label=arm)
        ax.set(title=name + " coarse region", ylabel="Position error (km)")
        ax.set_ylim(0, 65)
        ax.axhline(1, color="gray", linewidth=1)
        ax.tick_params(axis="x", rotation=35, labelsize=8)
        ax.legend()
        ax.grid(alpha=0.2)
        cases[name] = result
    output = dict(scope="Oracle diagnostic, no operational branch selection", cases=cases)
    (HERE / "summary.json").write_text(json.dumps(output, indent=2) + "\n")
    fig.savefig(HERE / "branch-comparison.png", dpi=160)
    for name, case in cases.items():
        print(name, case["regional_starts"])
        for arm, rows in case["arms"].items():
            print(arm, "final", rows["slope-0.25"])


if __name__ == "__main__":
    main()
