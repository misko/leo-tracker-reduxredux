"""Evaluate already frozen multiscan means and medians separately from fits."""

import csv
import hashlib
import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS
from localize_merged_track_catalogue import distance_km
from prototype_dsx01_continuous_position import OUTPUT, VARIANTS

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REFERENCE = (37.849061591561885, -122.48574968092912)


def run():
    source = OUTPUT / "consensus_endpoints.json"
    fits = json.loads(source.read_text())
    rows = []
    for key, fit in fits.items():
        rule, variant, arm, method = key.split("/")
        rows.append(
            dict(
                rule=rule,
                variant=variant,
                arm=arm,
                method=method,
                latitude_deg=fit["latitude_deg"],
                longitude_deg=fit["longitude_deg"],
                position_error_km=distance_km(
                    (fit["latitude_deg"], fit["longitude_deg"]), REFERENCE
                ),
                frequency_refit=False,
                all_five_scans_used=True,
            )
        )
    write(OUTPUT / "consensus_evaluation.json", rows)
    write(
        OUTPUT / "consensus_evaluation_binding.json",
        dict(
            endpoint_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            evaluation_reference_read_after_saved_consensus=True,
            evaluation_reference=REFERENCE,
            independent_generalization_evidence=False,
            all_rules_models_and_c_arms_reported=True,
        ),
    )
    with (OUTPUT / "consensus_evaluation.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    fig, axes = plt.subplots(2, 2, figsize=(15, 9), constrained_layout=True)
    for i, rule in enumerate(("mean", "coordinate_median")):
        for j, arm in enumerate(("c0", "fitted_c")):
            values = np.array(
                [
                    [
                        next(
                            r["position_error_km"]
                            for r in rows
                            if (r["rule"], r["variant"], r["arm"], r["method"])
                            == (rule, variant, arm, method)
                        )
                        for method in METHODS
                    ]
                    for variant in VARIANTS
                ]
            )
            ax = axes[i, j]
            im = ax.imshow(values, vmin=0, vmax=3, cmap="RdYlGn_r", aspect="auto")
            ax.set(
                title=f"{rule.replace('_', ' ')} / {arm}",
                xticks=range(len(METHODS)),
                xticklabels=METHODS,
                yticks=range(len(VARIANTS)),
                yticklabels=VARIANTS,
            )
            ax.tick_params(axis="x", rotation=40)
            for a in range(len(VARIANTS)):
                for b in range(len(METHODS)):
                    ax.text(b, a, f"{values[a, b]:.3f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=axes, label="Five-scan site error (km)", shrink=0.75)
    fig.suptitle(
        "Blind estimates combined after fitting; one common site, no joint frequency refit"
    )
    fig.savefig(OUTPUT / "consensus_accuracy.png", dpi=150)
    plt.close(fig)
    audit_path = OUTPUT / "DSX01-S01/oracle_continuous_bias.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text())
        fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
        for ax, method in zip(axes.flat, METHODS, strict=True):
            row = audit[f"continuous/fitted_c/{method}"]
            families = list(row["families"].items())[:6]
            ax.bar(
                [n for n, _ in families],
                [v["data_loss_delta"] for _, v in families],
                color="tab:red",
                alpha=0.8,
            )
            ax.axhline(0, color="black", linewidth=0.7)
            ax.set(
                title=method.replace("_", " "),
                xlabel="Candidate NORAD (identity unverified)",
                ylabel="Data cost at blind fit minus GPS fit",
            )
            ax.tick_params(axis="x", rotation=40)
            ax.grid(axis="y", alpha=0.15)
        fig.suptitle(
            "S01 oracle audit: families rewarding the displaced fit; "
            "nuisance terms refitted at both sites"
        )
        fig.savefig(OUTPUT / "s01_family_bias_attribution.png", dpi=150)
        plt.close(fig)


if __name__ == "__main__":
    run()
