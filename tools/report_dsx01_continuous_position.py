"""Evaluate frozen Mill Valley fits; reference GPS enters only this reporter."""

import csv
import hashlib
import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, Scan
from localize_merged_track_catalogue import distance_km
from prototype_dsx01_continuous_position import (
    CENTER,
    OUTPUT,
    VARIANTS,
    native_point,
    numpy_state,
)

from leo.analysis.research.phase_linear_geometry import phase_linear_frequency

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REFERENCE = (37.849061591561885, -122.48574968092912)
COLORS = dict(continuous="tab:blue", shape_only="tab:orange", family_balanced="tab:green")


def run():
    summary = []
    ablations = []
    all_endpoints = {}
    inputs = {}
    raw_counts = {}
    with (OUTPUT.parent / "2026_10_18_dsx01_retention_localization/per_scan.csv").open() as f:
        for row in csv.DictReader(f):
            raw_counts[row["case"]] = int(row["raw_points"])
    pool_path = OUTPUT / "pooled/endpoints.json"
    pooled = json.loads(pool_path.read_text()) if pool_path.exists() else {}
    if pooled:
        inputs[str(pool_path)] = hashlib.sha256(pool_path.read_bytes()).hexdigest()
    for case_dir in sorted(OUTPUT.glob("DSX01-S0*")):
        path = case_dir / "endpoints.json"
        if not path.exists():
            continue
        endpoints = json.loads(path.read_text())
        ablation_path = case_dir / "support_ablation/endpoints.json"
        if ablation_path.exists():
            endpoints.update(json.loads(ablation_path.read_text()))
            inputs[str(ablation_path)] = hashlib.sha256(ablation_path.read_bytes()).hexdigest()
        for key, fit in pooled.items():
            if case_dir.name in fit["states"]:
                # One common site estimate, evaluated on each scan's separate
                # receiver calibration. Pool runtime is recorded once / scan.
                endpoints["pool_" + key] = dict(
                    fit,
                    state=fit["states"][case_dir.name],
                    elapsed_seconds=fit["elapsed_seconds"] / len(fit["states"]),
                )
        all_endpoints[case_dir.name] = endpoints
        inputs[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        audit_path = case_dir / "frozen_position_associations.json"
        audited = json.loads(audit_path.read_text()) if audit_path.exists() else {}
        scan = None
        for key, fit in endpoints.items():
            variant, arm, method = key.split("/")
            digest = hashlib.sha256(json.dumps(fit, sort_keys=True).encode()).hexdigest()
            if key not in audited or audited[key].get("fitted_endpoint_sha256") != digest:
                scan = Scan(case_dir.name) if scan is None else scan
                xy = native_point(scan, fit["east_north_km"])
                base = phase_linear_frequency(
                    scan.geometry, fit["latitude_deg"], fit["longitude_deg"]
                )
                score, rows, _, _ = scan.association(
                    numpy_state(fit["state"]), base, xy, method, all_tracks=True
                )
                audited[key] = dict(
                    score=score,
                    rows=rows,
                    fitted_endpoint_sha256=digest,
                    position_changed_during_association=False,
                )
                write(audit_path, audited)
            accepted = [r for r in audited[key]["rows"] if r["compatible"]]
            count = sum(r["points"] for r in accepted)
            curved = [r for r in accepted if r["active_curvature"]]
            cn = sum(r["points"] for r in curved)
            record = dict(
                case=case_dir.name,
                variant=variant,
                arm=arm,
                method=method,
                latitude_deg=fit["latitude_deg"],
                longitude_deg=fit["longitude_deg"],
                position_error_km=distance_km(
                    (fit["latitude_deg"], fit["longitude_deg"]), REFERENCE
                ),
                continuous_objective=fit["score"],
                strict_composite_score=audited[key]["score"],
                associated_points=count,
                raw_points=raw_counts[case_dir.name],
                percent_associated=100 * count / raw_counts[case_dir.name],
                accepted_curved_points=cn,
                association_segments=sum(r["parts"] for r in accepted),
                points_per_segment=count / max(1, sum(r["parts"] for r in accepted)),
                curved_native_rms_hz=float(
                    np.sqrt(sum(r["points"] * r["rms_hz"] ** 2 for r in curved) / max(1, cn))
                ),
                elapsed_seconds=fit["elapsed_seconds"],
                evaluation_GPS_used_only_after_endpoint_freeze=True,
            )
            summary.append(record)
        for variant in sorted({k.split("/")[0] for k in endpoints}):
            for method in METHODS:
                keys = [f"{variant}/{arm}/{method}" for arm in ("c0", "fitted_c")]
                if not all(key in audited for key in keys):
                    continue
                rows = [
                    {
                        r["component"]: r
                        for r in audited[key]["rows"]
                        if r["compatible"] and r["active_curvature"]
                    }
                    for key in keys
                ]
                common = rows[0].keys() & rows[1].keys()
                count = sum(rows[0][k]["points"] for k in common)
                ablation = dict(
                    case=case_dir.name,
                    variant=variant,
                    method=method,
                    common_curved_points=count,
                    same_label_points=sum(
                        rows[0][k]["points"]
                        for k in common
                        if rows[0][k]["candidate_norad"] == rows[1][k]["candidate_norad"]
                    ),
                )
                for arm, rr in zip(("c0", "fitted_c"), rows, strict=True):
                    ablation["native_rms_" + arm + "_hz"] = float(
                        np.sqrt(
                            sum(rr[k]["points"] * rr[k]["rms_hz"] ** 2 for k in common)
                            / max(1, count)
                        )
                    )
                    ablation["innovation_rms_" + arm + "_hz"] = float(
                        np.sqrt(
                            sum(np.sum(np.asarray(rr[k]["innovations_hz"]) ** 2) for k in common)
                            / max(1, count)
                        )
                    )
                ablations.append(ablation)
    write(OUTPUT / "evaluation_summary.json", summary)
    write(OUTPUT / "c_ablation.json", ablations)
    for name, rows in (("evaluation_summary", summary), ("c_ablation", ablations)):
        if rows:
            with (OUTPUT / f"{name}.csv").open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    write(
        OUTPUT / "evaluation_binding.json",
        dict(
            reference_used_only_after_saved_endpoints=True,
            evaluation_reference=REFERENCE,
            endpoint_files_sha256=inputs,
            completed_fits=len(summary),
            intended_full_matrix_size=180,
            satellite_identity_truth_unavailable=True,
        ),
    )
    if not summary:
        return
    cases = sorted(all_endpoints)
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), constrained_layout=True)
    ref = np.array(
        [
            (REFERENCE[1] - CENTER[1]) * 111.32 * np.cos(np.deg2rad(CENTER[0])),
            (REFERENCE[0] - CENTER[0]) * 111,
        ]
    )
    s01 = all_endpoints.get("DSX01-S01", {})
    for ax, method in zip(axes.flat, METHODS, strict=True):
        for variant in VARIANTS:
            key = f"{variant}/fitted_c/{method}"
            if key not in s01:
                continue
            fit = s01[key]
            for result in fit["fits"]:
                track = np.array([r["parameters"][:2] for r in result["history"]])
                ax.plot(*track.T, color=COLORS[variant], alpha=0.4, linewidth=0.8)
            xy = fit["east_north_km"]
            ax.scatter(*xy, color=COLORS[variant], s=38, label=variant.replace("_", " "))
        ax.scatter(*ref, color="black", marker="*", s=100, label="GPS (evaluation only)")
        ax.scatter(0, 0, color="grey", marker="+", s=60)
        ax.set(
            title=method.replace("_", " "),
            xlim=(-12.5, 12.5),
            ylim=(-12.5, 12.5),
            xlabel="East of Mill Valley (km)",
            ylabel="North of Mill Valley (km)",
        )
        ax.grid(alpha=0.2)
        ax.set_aspect("equal")
    axes.flat[0].legend(fontsize=7)
    fig.suptitle("S01: blind 25 x 25 km starts; continuous fixed-family prototypes; fitted c")
    fig.savefig(OUTPUT / "s01_blind_paths.png", dpi=160)
    plt.close(fig)
    extra_variants = sorted({r["variant"] for r in summary if r["variant"] not in VARIANTS})
    if extra_variants:
        fig, axes = plt.subplots(
            len(extra_variants),
            2,
            figsize=(15, 3 * len(extra_variants)),
            squeeze=False,
            constrained_layout=True,
        )
        for i, variant in enumerate(extra_variants):
            for column, arm in enumerate(("c0", "fitted_c")):
                matrix = np.full((len(cases), len(METHODS)), np.nan)
                for row in summary:
                    if row["arm"] == arm and row["variant"] == variant:
                        matrix[cases.index(row["case"]), METHODS.index(row["method"])] = row[
                            "position_error_km"
                        ]
                ax = axes[i, column]
                im = ax.imshow(matrix, vmin=0, vmax=10, cmap="RdYlGn_r", aspect="auto")
                ax.set(
                    title=f"{variant.replace('_', ' ')} / {arm}",
                    xticks=range(len(METHODS)),
                    xticklabels=METHODS,
                    yticks=range(len(cases)),
                    yticklabels=cases,
                )
                ax.tick_params(axis="x", rotation=45)
                for ii in range(len(cases)):
                    for jj in range(len(METHODS)):
                        if np.isfinite(matrix[ii, jj]):
                            ax.text(
                                jj,
                                ii,
                                f"{matrix[ii, jj]:.2f}",
                                ha="center",
                                va="center",
                                fontsize=8,
                            )
        fig.colorbar(im, ax=axes, label="Position error (km)", shrink=0.5)
        fig.suptitle(
            "Support, prior and pooled-site ablations; shared-site rows are one common estimate"
        )
        fig.savefig(OUTPUT / "extended_position_accuracy.png", dpi=150)
        plt.close(fig)
    fig, axes = plt.subplots(2, 3, figsize=(16, 8), constrained_layout=True)
    for axis, arm in enumerate(("c0", "fitted_c")):
        for column, variant in enumerate(VARIANTS):
            matrix = np.full((len(cases), len(METHODS)), np.nan)
            for row in summary:
                if row["arm"] == arm and row["variant"] == variant:
                    matrix[cases.index(row["case"]), METHODS.index(row["method"])] = row[
                        "position_error_km"
                    ]
            ax = axes[axis, column]
            im = ax.imshow(matrix, vmin=0, vmax=10, cmap="RdYlGn_r", aspect="auto")
            ax.set(
                title=f"{variant.replace('_', ' ')} / {arm}",
                xticks=range(len(METHODS)),
                xticklabels=METHODS,
                yticks=range(len(cases)),
                yticklabels=cases,
            )
            ax.tick_params(axis="x", rotation=55)
            for i in range(len(cases)):
                for j in range(len(METHODS)):
                    if np.isfinite(matrix[i, j]):
                        ax.text(j, i, f"{matrix[i, j]:.2f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=axes, label="Independent position error (km)", shrink=0.75)
    fig.suptitle("Paired c ablation: position accuracy, separate from frequency fit")
    fig.savefig(OUTPUT / "position_accuracy_matrix.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    run()
