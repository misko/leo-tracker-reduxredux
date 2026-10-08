"""Inspect accepted RF-drift corrections and verify the strict ablation."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    documents = [
        json.loads((HERE / "results" / f"{label}.json").read_text()) for label in protocol["labels"]
    ]
    assert len(documents) == 107
    variants = [v for v in protocol["variants"] if v != "static-control"]
    fig, axes = plt.subplots(1, len(variants), figsize=(14, 4), layout="constrained")
    summary = {}
    for ax, variant in zip(axes, variants, strict=True):
        rows = []
        for document in documents:
            for result in document["candidates"]:
                if result["arm"] == "zero-c":
                    assert result["vector"][6] == 0
                    assert result["rf_drift_coefficients"] == [0, 0]
            result = next(
                r
                for r in document["candidates"]
                if r["variant"] == variant and r["arm"] == "fitted-c"
            )
            rows.append(
                dict(
                    label=document["label"],
                    converged=result["converged"],
                    coefficients=result["rf_drift_coefficients"] if result["converged"] else [0, 0],
                    raw_coefficients=result["rf_drift_coefficients"],
                    fallback=None if result["converged"] else "static post200 operational result",
                )
            )
        values = np.asarray([r["coefficients"] for r in rows])
        assert np.max(abs(values)) <= 1000 + 1e-7
        summary[variant] = dict(
            rows=rows,
            median=np.median(values, axis=0).tolist(),
            p95_absolute=np.percentile(abs(values), 95, axis=0).tolist(),
            max_absolute=np.max(abs(values), axis=0).tolist(),
            bound_labels=[
                r["label"] for r in rows if max(abs(np.asarray(r["coefficients"]))) >= 1000 - 1e-5
            ],
        )
        for prefix, color, title in (
            ("DS17", "tab:orange", "DS17"),
            ("NEW", "tab:green", "Newer"),
            ("S", "tab:blue", "DS16"),
        ):
            mask = np.array([r["label"].startswith(prefix) for r in rows])
            ax.scatter(values[mask, 0], values[mask, 1], s=20, alpha=0.65, label=title, color=color)
        ax.axhline(0, color="black", linewidth=1)
        ax.axvline(0, color="black", linewidth=1)
        ax.set(title=variant, xlabel="RX0: Hz / GHz / 100 s", ylabel="RX1: Hz / GHz / 100 s")
        ax.grid(alpha=0.2)
        ax.legend()
    (HERE / "coefficient-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig.savefig(HERE / "rf-drift-coefficients.png", dpi=160)
    print(
        json.dumps(
            {v: {k: value for k, value in r.items() if k != "rows"} for v, r in summary.items()},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
