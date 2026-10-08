"""Audit regional selection after all frozen reference-free inventory attempts."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((HERE.parent / name).read_bytes()).hexdigest() == digest
    rows, failures, regions = [], [], []
    for region in protocol["regions"]:
        data = json.loads((HERE / "results" / f"region-{region['index']:02d}.json").read_text())
        assert data["region"] == region
        assert (
            data["protocol_sha256"]
            == hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
        )
        regions.append(data)
        if data["status"] != "complete":
            failures.append(dict(region=region, error=data["error"]))
            continue
        for arm in data["document"]["methods"][0]["arms"]:
            selected = arm["selected"]
            rows.append(
                dict(
                    region=region,
                    arm=arm["name"],
                    score=selected["selection_score"],
                    error_km=selected["horizontal_error_m"] / 1000,
                    converged=selected["converged"],
                    candidate_count=len(selected["satellites"]),
                )
            )
        for fit in data["receipt"]["regional_fits"]:
            if fit["arm"] == "zero-c":
                assert fit["fit"]["vector"][6] == 0
    winners = {}
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    for ax, arm in zip(axes, ("fitted-c", "zero-c"), strict=True):
        selected = sorted(
            (r for r in rows if r["arm"] == arm and r["converged"]),
            key=lambda r: (r["score"], r["region"]["index"]),
        )
        winners[arm] = selected[0] if selected else None
        ax.scatter(
            [r["score"] for r in selected],
            [r["error_km"] for r in selected],
            label="Converged region winners",
        )
        if selected:
            ax.scatter(
                [selected[0]["score"]],
                [selected[0]["error_km"]],
                marker="*",
                s=180,
                color="tab:red",
                label="Lowest regional score",
            )
        ax.set(
            title=arm,
            xlabel="Regional selection score (includes calibration penalty)",
            ylabel="Position error (km; evaluation only)",
            yscale="log",
        )
        ax.axhline(1, color="grey", linestyle="--", linewidth=0.8)
        ax.legend(fontsize=8)
    fig.suptitle("35 reference-free regions: existing regional score selection")
    fig.savefig(HERE / "regional-selection.png", dpi=150)
    table = [
        "| Index | Source/rank | East,north km | c | Converged | Score | Error km | Candidates |",
        "|---:|---|---|---|---|---:|---:|---:|",
    ]
    for row in rows:
        r = row["region"]
        table.append(
            f"| {r['index']} | {r['source']}/{r['source_rank']} | {r['point']} | "
            f"{row['arm']} | {row['converged']} | {row['score']:.6f} | "
            f"{row['error_km']:.6f} | {row['candidate_count']} |"
        )
    (HERE / "regions.md").write_text("\n".join(table) + "\n")
    candidate_union = sorted(
        {
            n
            for r in regions
            if r["status"] == "complete"
            for a in r["document"]["methods"][0]["arms"]
            for n in a["selected"]["satellites"]
        }
    )
    result = dict(
        candidate_union=candidate_union,
        winners=winners,
        rows=rows,
        failures=failures,
        region_seconds=sum(r["elapsed_s"] for r in regions),
        canaries=sum(r.get("canary_passed", False) for r in regions),
        regional_fits=sum(len(r.get("receipt", {}).get("regional_fits", [])) for r in regions),
        failed_regional_fits=sum(
            not f["fit"]["converged"]
            for r in regions
            for f in r.get("receipt", {}).get("regional_fits", [])
        ),
    )
    (HERE / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
