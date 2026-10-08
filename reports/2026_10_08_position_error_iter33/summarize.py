"""Compare actual refits and objective-selected starts, preserving failed outcomes."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    sigmas = sorted(plan["relative_sigmas_s"])
    cases = {}
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    for i, label in enumerate(plan["cases"]):
        raw = json.loads((HERE / "results" / f"{label}.json").read_text())
        rows = raw["candidates"]
        assert len(rows) == 16
        arms = {}
        for j, arm in enumerate(("fitted-c", "zero-c")):
            selected = {}
            for sigma in sigmas:
                pair = [r for r in rows if r["arm"] == arm and r["relative_sigma_s"] == sigma]
                eligible = [r for r in pair if r["converged"]]
                best = (
                    min(
                        eligible,
                        key=lambda r: (r["objective"], r["initialization"] != "original-start"),
                    )
                    if eligible
                    else None
                )
                selected[str(sigma)] = (
                    None
                    if best is None
                    else {
                        k: best[k]
                        for k in (
                            "initialization",
                            "error_km",
                            "objective",
                            "posterior_rms_hz",
                            "relative_timing_rms_s",
                            "stationarity",
                        )
                    }
                )
            for name in ("original-start", "zero-timing-start"):
                values = [
                    next(
                        r
                        for r in rows
                        if r["arm"] == arm
                        and r["relative_sigma_s"] == s
                        and r["initialization"] == name
                    )
                    for s in sigmas
                ]
                axes[i, j].plot(sigmas, [r["error_km"] for r in values], marker="o", label=name)
                for s, row in zip(sigmas, values, strict=True):
                    if not row["converged"]:
                        axes[i, j].scatter(s, row["error_km"], marker="x", s=90, color="red")
            axes[i, j].plot(
                sigmas,
                [
                    np.nan if selected[str(s)] is None else selected[str(s)]["error_km"]
                    for s in sigmas
                ],
                linestyle="--",
                color="black",
                label="Lowest converged score",
            )
            axes[i, j].set(
                title=label + " " + arm,
                xlabel="Relative timing sigma (s)",
                ylabel="Position error (km)",
            )
            axes[i, j].axhline(1, color="gray", linewidth=1)
            axes[i, j].legend(fontsize=8)
            axes[i, j].grid(alpha=0.2)
            arms[arm] = selected
        cases[label] = dict(
            selected=arms,
            failures=[
                {k: r[k] for k in ("relative_sigma_s", "initialization", "arm", "stationarity")}
                for r in rows
                if not r["converged"]
            ],
        )
    fig.savefig(HERE / "timing-prior-refits.png", dpi=160)
    (HERE / "summary.json").write_text(json.dumps(dict(cases=cases), indent=2) + "\n")
    print(json.dumps(cases, indent=2))


if __name__ == "__main__":
    main()
