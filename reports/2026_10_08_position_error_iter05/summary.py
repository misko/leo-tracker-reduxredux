"""Report full-cohort fallback separately from the matched RF ablation."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent


def metrics(before, after):
    before, after = np.asarray(before), np.asarray(after)
    return dict(
        count=len(before),
        mean_before_km=float(before.mean()),
        mean_after_km=float(after.mean()),
        median_before_km=float(np.median(before)),
        median_after_km=float(np.median(after)),
        p95_before_km=float(np.percentile(before, 95)),
        p95_after_km=float(np.percentile(after, 95)),
        worst_before_km=float(before.max()),
        worst_after_km=float(after.max()),
        improved=int((after < before - 0.001).sum()),
        worsened=int((after > before + 0.001).sum()),
    )


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    labels = protocol["labels"]
    documents = {
        label: json.loads((HERE / "results" / f"{label}.json").read_text()) for label in labels
    }
    cases = []
    for label, doc in documents.items():
        rows = {(r["variant"], r["arm"]): r for r in doc["candidates"]}
        published = {a["name"]: a["selected"] for a in doc["published_arms"]}
        arms = {}
        for arm in ("fitted-c", "zero-c"):
            control, joint = rows["matched-control", arm], rows["joint-wide", arm]
            baseline = published[arm]["horizontal_error_m"] / 1000
            arms[arm] = dict(
                published_error_km=baseline,
                control=control,
                joint=joint,
                operational_error_km=joint["error_km"] if joint["converged"] else baseline,
                fallback=not joint["converged"],
            )
        cases.append(dict(label=label, session_id=doc["session_id"], arms=arms))
    result = dict(cases=cases, operational={}, matched={})
    for arm in ("fitted-c", "zero-c"):
        rows = [c["arms"][arm] for c in cases]
        operational = metrics(
            [r["published_error_km"] for r in rows], [r["operational_error_km"] for r in rows]
        )
        operational["fallback_count"] = sum(r["fallback"] for r in rows)
        result["operational"][arm] = operational
        paired = [r for r in rows if r["control"]["converged"] and r["joint"]["converged"]]
        matched = metrics(
            [r["control"]["error_km"] for r in paired], [r["joint"]["error_km"] for r in paired]
        )
        matched["rms_before_hz"] = float(
            np.mean([r["control"]["posterior_rms_hz"] for r in paired])
        )
        matched["rms_after_hz"] = float(np.mean([r["joint"]["posterior_rms_hz"] for r in paired]))
        result["matched"][arm] = matched
    op = result["operational"]["fitted-c"]
    gate = protocol["candidate_gate"]
    result["gates"] = dict(
        all34_available=len(cases) == 34,
        mean_improvement=op["mean_after_km"]
        <= op["mean_before_km"] * (1 - gate["mean_relative_reduction_minimum"]),
        p95=op["p95_after_km"] <= op["p95_before_km"] * gate["p95_ratio_maximum"],
        worst=op["worst_after_km"] <= op["worst_before_km"] * gate["worst_ratio_maximum"],
        convergence=1 - op["fallback_count"] / 34
        >= gate["joint_fitted_convergence_fraction_minimum"],
        validation_mean_below_1km=op["mean_after_km"] < 1,
    )
    (HERE / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), layout="constrained")
    for ax, arm in zip(axes, ("fitted-c", "zero-c"), strict=True):
        rows = [c["arms"][arm] for c in cases]
        for name, key in [
            ("Deployed-policy baseline", "published_error_km"),
            ("Frozen joint candidate + fallback", "operational_error_km"),
        ]:
            errors = sorted(r[key] for r in rows)
            ax.step(errors, np.arange(1, 35) / 34, where="post", label=name)
        ax.axvline(1, color="black", linestyle="--", linewidth=1)
        ax.set_xscale("symlog", linthresh=1)
        ax.set_xlim(
            0, max(max(r["published_error_km"], r["operational_error_km"]) for r in rows) * 1.05
        )
        ax.set(
            title=f"DS17 reserved validation: {arm}",
            xlabel="Position error (km)",
            ylabel="Fraction of all 34 scans",
        )
        ax.legend(fontsize=8)
        ax.grid(alpha=0.2)
    fig.savefig(HERE / "validation-cdf.png", dpi=160)
    plt.close(fig)
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}, indent=2))


if __name__ == "__main__":
    main()
