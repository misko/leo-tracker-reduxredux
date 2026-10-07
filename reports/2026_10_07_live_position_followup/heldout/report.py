"""Render paired frequency prediction diagnostics separately from position error."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

HERE = Path(__file__).resolve().parent


def main():
    data = json.loads((HERE / "results.json").read_text())
    rows = data["results"]
    comparisons = []
    for session in dict.fromkeys(r["session"] for r in rows):
        for fold in ("late-time", "channel"):
            for method in ("T1AT", "V16"):
                for arm in ("fitted-c", "zero-c"):
                    pair = {
                        r["hypothesis"]: r
                        for r in rows
                        if (r["session"], r["fold"], r["method"], r["arm"])
                        == (session, fold, method, arm)
                    }
                    near, far = pair["near"], pair["far"]
                    assert near["test_ids_sha256"] == far["test_ids_sha256"]
                    comparisons.append(
                        dict(
                            session=session,
                            fold=fold,
                            method=method,
                            arm=arm,
                            test_count=near["test_count"],
                            far_minus_near_nll_per_window=far["heldout"]["nll_per_window"]
                            - near["heldout"]["nll_per_window"],
                            near_error_km=near["position_error_m"] / 1000,
                            far_error_km=far["position_error_m"] / 1000,
                            both_converged=near["converged"] and far["converged"],
                        )
                    )
    (HERE / "comparisons.json").write_text(json.dumps(comparisons, indent=2))
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    for ax, session in zip(axes, dict.fromkeys(r["session"] for r in rows), strict=True):
        items = [r for r in comparisons if r["session"] == session]
        labels = [f"{r['fold']} {r['method']} {r['arm']}" for r in items]
        values = [r["far_minus_near_nll_per_window"] for r in items]
        bars = ax.barh(labels, values, color=["#267d48" if v > 0 else "#b35734" for v in values])
        for bar, item in zip(bars, items, strict=True):
            if not item["both_converged"]:
                bar.set_hatch("///")
                bar.set_edgecolor("#333333")
                bar.set_linewidth(0.5)
        ax.axvline(0, color="black", lw=0.7)
        ax.set_title(session.removeprefix("scan-fw-"))
        ax.set_xlabel(
            "Frozen heldout NLL/window: far minus near\n"
            "positive favors near (conditional diagnostic)"
        )
        ax.invert_yaxis()
    fig.suptitle("Training refits; full-data bank and calibration proposals retained")
    fig.legend(
        handles=[
            Patch(
                facecolor="white",
                edgecolor="#333333",
                hatch="///",
                label="At least one training fit did not converge",
            )
        ],
        loc="outside lower center",
    )
    fig.savefig(HERE / "heldout.png", dpi=160)
    print(json.dumps(dict(elapsed_s=data["elapsed_s"], comparisons=comparisons), indent=2))


if __name__ == "__main__":
    main()
