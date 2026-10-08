"""Compare matched controls and all eligible clock starts within each prior."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def key(row):
    return (
        row["objective"],
        row["initialization"] != "continued-original",
        row["source_initialization"] != "original-start",
        row["initialization"],
    )


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((HERE.parent / name).read_bytes()).hexdigest() == digest, name
    rows, rejections = [], []
    for label in protocol["cases"]:
        paths = [
            HERE.parent / "2026_10_08_position_error_iter36/results" / f"{label}.json",
            *sorted((HERE / "results").glob(f"{label}-*.json")),
        ]
        assert len(paths) == 4
        for path in paths:
            data = json.loads(path.read_text())
            sigma = data.get("relative_sigma_s", 2)
            source = data.get("source_initialization", "original-start")
            rejections.extend(
                dict(label=label, sigma=sigma, source=source, **r) for r in data["rejected"]
            )
            for r in data["candidates"]:
                assert r["converged"] == (r["stationarity"] <= 0.001)
                assert max(abs(r["vector"][3]), abs(r["vector"][5])) <= 60 + 1e-7
                if r["arm"] == "zero-c":
                    assert r["vector"][6] == 0
                rows.append(dict(label=label, sigma=sigma, source_initialization=source, **r))
    selected = []
    table = [
        "| Case | Sigma s | c | Control km | All-start selected km | Source | Start |",
        "|---|---:|---|---:|---:|---|---|",
    ]
    for label in protocol["cases"]:
        for sigma in (2, 0.75):
            for arm in ("fitted-c", "zero-c"):
                subset = [
                    r
                    for r in rows
                    if r["label"] == label
                    and r["sigma"] == sigma
                    and r["arm"] == arm
                    and r["converged"]
                ]
                control = min(
                    (r for r in subset if r["initialization"] == "continued-original"), key=key
                )
                winner = min(subset, key=key)
                selected.append(
                    dict(label=label, sigma=sigma, arm=arm, control=control, selected=winner)
                )
                table.append(
                    f"| {label} | {sigma} | {arm} | {control['error_km']:.6f} | "
                    f"{winner['error_km']:.6f} | {winner['source_initialization']} | "
                    f"{winner['initialization']} |"
                )
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    for k, label in enumerate(protocol["cases"]):
        for j, arm in enumerate(("fitted-c", "zero-c")):
            subset = [s for s in selected if s["label"] == label and s["arm"] == arm]
            x = np.arange(len(subset))
            axes[k, j].bar(
                x - 0.18,
                [s["control"]["error_km"] for s in subset],
                0.36,
                label="Best scored continuation control",
            )
            axes[k, j].bar(
                x + 0.18,
                [s["selected"]["error_km"] for s in subset],
                0.36,
                label="Best scored including pair proposals",
            )
            axes[k, j].set_xticks(x, [f"sigma {s['sigma']} s" for s in subset])
            axes[k, j].set(title=f"{label} / {arm}", ylabel="Position error (km)")
            axes[k, j].axhline(1, color="grey", linestyle="--", linewidth=0.8)
            axes[k, j].legend(fontsize=7)
    fig.suptitle("Clock proposals × timing prior: select only within a fixed prior")
    fig.savefig(HERE / "interaction.png", dpi=150)
    (HERE / "comparison.md").write_text("\n".join(table) + "\n")
    (HERE / "summary.json").write_text(
        json.dumps(dict(selected=selected, rows=rows, rejected=rejections), indent=2) + "\n"
    )
    print("\n".join(table))
    print(
        "Fits",
        len(rows),
        "failed",
        sum(not r["converged"] for r in rows),
        "rejected seeds",
        len(rejections),
    )


if __name__ == "__main__":
    main()
