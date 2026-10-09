"""Retrospective fixed-endpoint audit; no fitting or operational selection."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from receipt_loader import merged_result

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent / "2026_10_09_position_error_iter78"


def slope_energy(fit):
    # vector = 8 core parameters + N-1 relative timing coordinates.
    # clock = smooth receiver coefficients + N-1 slope coordinates + 2 RF drift terms.
    count = len(fit["vector"]) - 8
    assert count > 0
    coordinates = np.asarray(fit["clock_coefficients"][-(count + 2):-2]) / 100
    assert len(coordinates) == count and np.isfinite(coordinates).all()
    return float(coordinates @ coordinates)


def reweight(fit, source_sigma, target_sigma):
    assert source_sigma > 0 and target_sigma > 0
    return fit["objective"] + 0.5 * slope_energy(fit) * (
        1 / target_sigma**2 - 1 / source_sigma**2
    )


def main():
    path = ORIGINAL / "protocol.json"
    plan = json.loads(path.read_text())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rows = []
    for binding in plan["members"]:
        result = merged_result(binding, digest, ORIGINAL, HERE)
        if result["status"] != "complete":
            continue
        for arm in ("fitted-c", "zero-c"):
            narrow = result["raw"]["0.25"][arm]
            wide = result["raw"]["0.5"][arm]
            rows.append(dict(
                label=binding["member"]["inventory_label"], arm=arm,
                both_qualified=narrow["converged"] and wide["converged"],
                error_before_km=narrow["error_km"], error_after_km=wide["error_km"],
                error_delta_km=wide["error_km"] - narrow["error_km"],
                rms_delta_hz=wide["posterior_rms_hz"] - narrow["posterior_rms_hz"],
                slope_norm_before_hz_s=slope_energy(narrow)**0.5,
                slope_norm_after_hz_s=slope_energy(wide)**0.5,
                wide_minus_narrow_at_sigma025=(
                    reweight(wide, 0.5, 0.25) - narrow["objective"]
                ),
                wide_minus_narrow_at_sigma05=(
                    wide["objective"] - reweight(narrow, 0.25, 0.5)
                ),
                endpoint_distance_km=float(np.linalg.norm(
                    np.asarray(wide["vector"][:2]) - narrow["vector"][:2]
                )),
            ))
    (HERE / "slope-audit.json").write_text(json.dumps(rows, indent=2) + "\n")
    qualified = [r for r in rows if r["both_qualified"] and r["arm"] == "fitted-c"]
    qualified.sort(key=lambda r: r["error_delta_km"], reverse=True)
    lines = [
        "# Retrospective slope-prior endpoint audit", "",
        f"{len(rows)} raw arm pairs available; "
        f"{len(qualified)} fitted-c pairs qualify at both priors.",
        "No new fit, reference-guided inference, or winner selection occurs. This audit uses "
        "reference errors only to describe failures after inference. It is consumed-data research.",
        "",
        "For each unchanged endpoint, changing only sigma changes objective by "
        "0.5 × squared slope norm × (1/target_sigma² − 1/source_sigma²). "
        "The orthonormal satellite basis preserves this norm. This compares endpoints under "
        "the same objective; it does not directly compare scores from different models.", "",
        "Positive score delta means the wider-prior endpoint loses to the control endpoint "
        "under that column's fixed model. Raw unqualified fits remain in JSON but do not "
        "enter the table. Operational fallbacks remain in the main cohort report.", "",
        "| Largest fitted-c regressions | Before km | After km | Shift km | RMS delta Hz | "
        "Slope norm before/after Hz/s | Score delta at .25 | Score delta at .5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in qualified[:8]:
        lines.append(
            f"| {r['label']} | {r['error_before_km']:.3f} | {r['error_after_km']:.3f} | "
            f"{r['endpoint_distance_km']:.3f} | {r['rms_delta_hz']:+.3f} | "
            f"{r['slope_norm_before_hz_s']:.3f}/{r['slope_norm_after_hz_s']:.3f} | "
            f"{r['wide_minus_narrow_at_sigma025']:+.3f} | "
            f"{r['wide_minus_narrow_at_sigma05']:+.3f} |"
        )
    lines += ["", "This audit can distinguish a changed regularization preference from "
              "a convergence failure at these endpoints. It cannot prove the global optimum, "
              "identify a physical cause for a particular satellite slope, or justify choosing "
              "sigma per scan from known position errors."]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for arm, ax in zip(("fitted-c", "zero-c"), axes, strict=True):
        selected = [r for r in rows if r["arm"] == arm and r["both_qualified"]]
        for dataset in ("DS16", "DS17", "DS18"):
            group = [r for r in selected if r["label"].startswith(dataset)]
            ax.scatter(
                [r["slope_norm_after_hz_s"] - r["slope_norm_before_hz_s"] for r in group],
                [r["error_delta_km"] for r in group],
                label=f"{dataset}: {len(group)}", alpha=0.7, s=22,
            )
        ax.axhline(0, color="gray", linestyle="--")
        ax.set(title=arm, xlabel="Change in satellite slope norm, Hz/s",
               ylabel="Position error change, km (+ is worse)")
        ax.legend()
    fig.suptitle("Retrospective endpoint audit; only pairs qualified under both priors")
    fig.savefig(HERE / "slope-audit.png", dpi=170)
    plt.close(fig)
    lines += ["", "![Slope flexibility and position changes](slope-audit.png)"]
    (HERE / "SLOPE_AUDIT.md").write_text("\n".join(lines) + "\n")
    print(len(rows), "raw endpoint pairs audited")


if __name__ == "__main__":
    main()
