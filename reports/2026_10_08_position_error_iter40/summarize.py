"""Plot matched historical and recovered-seed downstream trajectories."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
STAGES = ("joint-100", "remove-5", "post-200", "drift-50", "control-refit", "slope-0.25")


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((HERE.parent / name).read_bytes()).hexdigest() == digest
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    table = [
        "| Case | Route | Stage | c | Converged | Error km | RMS Hz |",
        "|---|---|---|---|---|---:|---:|",
    ]
    operational = []
    for k, label in enumerate(protocol["cases"]):
        for mode in ("control", "recovered"):
            data = json.loads((HERE / "results" / f"{label}-{mode}.json").read_text())
            if mode == "control":
                assert data["canary_passed"]
            stages = {**data["upstream"]["stages"], **data["extended"]["stages"]}
            operational.append(
                dict(
                    label=label,
                    mode=mode,
                    operational=data["extended"]["operational"],
                    removed=data["upstream"].get("removed"),
                    stopped=data["upstream"]["stopped"],
                )
            )
            for j, arm in enumerate(("fitted-c", "zero-c")):
                names, values = [], []
                for name in STAGES:
                    if name not in stages:
                        continue
                    row = stages[name][arm]
                    if arm == "zero-c":
                        assert row["vector"][6] == 0
                        if "rf_drift_coefficients" in row:
                            assert row["rf_drift_coefficients"] == [0, 0]
                    assert row["converged"] == (row["stationarity"] <= 0.001)
                    names.append(name)
                    values.append(row["error_km"])
                    table.append(
                        f"| {label} | {mode} | {name} | {arm} | {row['converged']} | "
                        f"{row['error_km']:.6f} | {row['posterior_rms_hz']:.3f} |"
                    )
                axes[k, j].plot(names, values, marker="o", label=mode)
                axes[k, j].tick_params(axis="x", labelrotation=25)
                axes[k, j].set(title=f"{label} / {arm}", ylabel="Position error (km)")
        for ax in axes[k]:
            ax.axhline(1, color="grey", linestyle="--", linewidth=0.8)
            ax.legend()
    fig.suptitle("Downstream replay: fixed sigma 2 s; identical stage rules")
    fig.savefig(HERE / "downstream.png", dpi=150)
    (HERE / "stages.md").write_text("\n".join(table) + "\n")
    (HERE / "operational.json").write_text(json.dumps(operational, indent=2) + "\n")
    for row in operational:
        print(
            row["label"],
            row["mode"],
            row["stopped"],
            row["removed"],
            {arm: r["error_km"] for arm, r in row["operational"].items()},
        )


if __name__ == "__main__":
    main()
