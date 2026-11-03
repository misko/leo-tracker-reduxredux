"""Evaluation and scientific figures for the ALGO01 DS23-0217 investigation."""

import argparse
import csv

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from associate_merged_track_catalogue import write
from dsx01_inference_audit import disk_grid
from investigate_algo01_ds23_0217 import CASE, OUT, SOURCE, context, fixed, read
from matplotlib.patches import Circle
from prototype_dsx01_continuous_position import CENTER
from report_algo01_ds23_sample import REFERENCE, position_error
from report_ds23_phase_refreshed import plots

REFERENCE_XY = np.array(
    [
        (REFERENCE[1] - CENTER[1]) * 111.32 * np.cos(np.deg2rad(CENTER[0])),
        (REFERENCE[0] - CENTER[0]) * 111,
    ]
)


def prepare():
    directory = SOURCE / CASE
    baseline = read(directory / "result.json")
    arms = {}
    for arm in ("c0", "fitted_c"):
        d = baseline["arms"][arm]
        metrics = [
            dict(r, native_rms_hz=r["conditional_residual_gate"]["rms_hz"])
            for r in d["metrics"]["tracks"]
        ]
        arms[arm] = dict(
            all_graph_associations=dict(tracks=d["association_tracks"]),
            metrics=dict(tracks=metrics),
        )
    plots(OUT, read(directory / "observations.json"), read(directory / "tracks.json"), arms)
    axis, points = disk_grid(step_km=1)
    regional = np.asarray(points)
    local_axis = np.arange(-2, 2.001, 0.25)
    local = REFERENCE_XY + np.array([(a, b) for a in local_axis for b in local_axis])
    write(
        OUT / "surface_request.json",
        dict(
            points=np.vstack([regional, local]),
            regional_count=len(regional),
            regional_axis=axis,
            local_axis=local_axis,
            reference_xy=REFERENCE_XY,
            regional_radius_km=10,
            regional_spacing_km=1,
            local_half_width_km=2,
            local_spacing_km=0.25,
            GPS_used_only_to_define_explicit_diagnostic_local_view=True,
            production_initialization_unchanged=True,
        ),
    )


def surfaces():
    request = read(OUT / "surface_request.json")
    rows = [r for k in range(8) for r in read(OUT / f"grid_{k:02d}.json")["rows"]]
    rows.sort(key=lambda r: r["index"])
    assert len(rows) == len(request["points"])
    audit = read(OUT / "audit.json")
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 11))
    for col, arm in enumerate(("c0", "fitted_c")):
        costs = np.array([r["arms"][arm]["score"] for r in rows])
        endpoint = audit["arms"][arm]["endpoint"]
        n = request["regional_count"]
        for rowid, (axis, points, z, shift) in enumerate(
            (
                (
                    np.array(request["regional_axis"]),
                    np.array(request["points"][:n]),
                    costs[:n],
                    np.zeros(2),
                ),
                (
                    np.array(request["local_axis"]),
                    np.array(request["points"][n:]),
                    costs[n:],
                    REFERENCE_XY,
                ),
            )
        ):
            ax = axes[rowid, col]
            points = points - shift
            image = np.full((len(axis), len(axis)), np.nan)
            for point, value in zip(points, z, strict=True):
                ix = int(np.argmin(abs(axis - point[0])))
                iy = int(np.argmin(abs(axis - point[1])))
                image[iy, ix] = value - endpoint["score"]
            finite = image[np.isfinite(image)]
            lo, hi = min(0, float(finite.min())), float(np.percentile(finite, 95))
            levels = np.unique(np.r_[np.linspace(lo, max(hi, 1), 22), 0])
            color = ax.contourf(axis, axis, image, levels=levels, cmap="viridis", extend="both")
            contour_levels = [
                v for v in (0.5, 2, 5, 10, 20, 50, 100) if finite.min() < v < finite.max()
            ]
            if contour_levels:
                contours = ax.contour(
                    axis,
                    axis,
                    image,
                    levels=contour_levels,
                    colors="white",
                    linewidths=0.65,
                    alpha=0.7,
                )
                ax.clabel(contours, fontsize=7)
            dy, dx = np.gradient(image, axis, axis)
            stride = 2 if rowid == 0 else 3
            xx, yy = np.meshgrid(axis, axis)
            norm = np.hypot(dx, dy)
            scale = 0.55 if rowid == 0 else 0.15
            ax.quiver(
                xx[::stride, ::stride],
                yy[::stride, ::stride],
                (-dx / np.maximum(norm, 1e-10) * scale)[::stride, ::stride],
                (-dy / np.maximum(norm, 1e-10) * scale)[::stride, ::stride],
                angles="xy",
                scale_units="xy",
                scale=1,
                color="#ffb958",
                width=0.004,
            )
            truth = REFERENCE_XY - shift
            fitted = np.array(endpoint["endpoint_east_north_km"]) - shift
            ax.scatter(
                *truth, marker="*", s=210, c="red", edgecolor="white", zorder=10, label="True site"
            )
            ax.scatter(
                *fitted,
                marker="X",
                s=100,
                c="magenta",
                edgecolor="white",
                zorder=10,
                label="ALGO01 endpoint",
            )
            if rowid == 0:
                ax.add_patch(Circle((0, 0), 10, fill=False, color="white", ls="--", lw=1))
                ax.set(
                    xlim=(-10.5, 10.5),
                    ylim=(-10.5, 10.5),
                    xlabel="East from regional center (km)",
                    ylabel="North from regional center (km)",
                )
            else:
                ax.set(
                    xlim=(-2, 2),
                    ylim=(-2, 2),
                    xlabel="East from true site (km)",
                    ylabel="North from true site (km)",
                )
            ax.set_title(
                f"{arm}: {'10 km regional disk' if rowid == 0 else 'gradient around true site'}"
            )
            ax.set_aspect("equal")
            ax.legend(fontsize=7, loc="upper left")
            fig.colorbar(color, ax=ax, label="Loss minus saved endpoint loss")
    fig.suptitle(
        "DS23-0217: conditional phase-refreshed loss and normalized descent directions\n"
        "Satellite labels, aliases and 795 calibration points fixed; nuisances refit at each pixel"
    )
    fig.tight_layout()
    fig.savefig(OUT / "loss_gradient_10km.png", dpi=155)
    plt.close(fig)


def restarts():
    records = [read(p) for p in sorted(OUT.glob("restart_[0-9][0-9].json"))]
    assert len(records) == 81
    fig, axes = plt.subplots(1, 2, figsize=(15, 7.5))
    summaries = []
    for ax, arm in zip(axes, ("c0", "fitted_c"), strict=True):
        for r in records:
            d = r["arms"][arm]
            color = plt.colormaps["tab10"](d["final_mode"] % 10)
            start = np.asarray(r["start"])
            ax.scatter(*start, s=20, facecolor="#d33532", edgecolor="black", lw=0.5, zorder=5)
            ax.annotate(
                f"S{r['start_id']:02d}",
                start,
                xytext=(3, 3),
                textcoords="offset points",
                fontsize=5.5,
            )
            for h in d["history"]:
                trace = np.asarray([t["point"] for t in h["descent"]["trace"]])
                if len(trace):
                    ax.plot(trace[:, 0], trace[:, 1], c=color, alpha=0.24, lw=0.8)
            endpoint = np.asarray(d["endpoint_east_north_km"])
            ax.scatter(*endpoint, s=28, marker="x", c=[color], lw=1.4, zorder=7)
            summaries.append(
                dict(
                    start_id=r["start_id"],
                    arm=arm,
                    start_east_km=start[0],
                    start_north_km=start[1],
                    endpoint_east_km=endpoint[0],
                    endpoint_north_km=endpoint[1],
                    error_km=position_error(d["endpoint_latlon"]),
                    final_mode=d["final_mode"],
                    score=d["score"],
                    branch_switches=sum(len(h["descent"]["switches"]) for h in d["history"]),
                    max_last_phase_change_s=d["last_phase_change_s"],
                )
            )
        ax.scatter(
            *REFERENCE_XY,
            marker="*",
            s=220,
            c="limegreen",
            edgecolor="black",
            zorder=10,
            label="True site (evaluation only)",
        )
        ax.add_patch(Circle((0, 0), 10, fill=False, color=".4", ls="--"))
        ax.set(
            xlim=(-12.6, 12.6),
            ylim=(-12.6, 12.6),
            aspect="equal",
            xlabel="East from regional center (km)",
            ylabel="North from regional center (km)",
            title=arm,
        )
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    fig.suptitle(
        "DS23-0217: 81 starts on a 2 km grid in the 10 km regional disk\n"
        "Circles = starts; lines = accepted position steps; X = endpoints; color = final RF branch"
    )
    fig.tight_layout()
    fig.savefig(OUT / "convergence_10km.png", dpi=165)
    plt.close(fig)
    with (OUT / "restart_comparison.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    write(
        OUT / "restart_summary.json",
        {
            arm: dict(
                error_range_km=[
                    min(r["error_km"] for r in summaries if r["arm"] == arm),
                    max(r["error_km"] for r in summaries if r["arm"] == arm),
                ],
                modes=sorted({r["final_mode"] for r in summaries if r["arm"] == arm}),
                switches=sum(r["branch_switches"] for r in summaries if r["arm"] == arm),
            )
            for arm in ("c0", "fitted_c")
        },
    )


def finite_hessian(function, x, step=0.05):
    x = np.asarray(x, float)
    axes = np.eye(2) * step
    h = np.zeros((2, 2))
    center = function(x)
    for k in range(2):
        h[k, k] = (function(x + axes[k]) - 2 * center + function(x - axes[k])) / step**2
    h[0, 1] = h[1, 0] = (
        function(x + axes[0] + axes[1])
        - function(x + axes[0] - axes[1])
        - function(x - axes[0] + axes[1])
        + function(x - axes[0] - axes[1])
    ) / (4 * step**2)
    return h


def details():
    """Explicit oracle diagnostics; these do not select an inference result."""
    from collections import Counter

    from audit_ds23_algo01_coverage import retained_metrics
    from dsx01_joint_exact_mean import exact_conditional_frequency
    from map_dsx01_clean_region import finite_gradient

    scan, node, keep, baseline = context()
    arms = {}
    blocks = ("weighted_data_cost", "gamma_cost", "logvolume", "all_priors")
    for arm in ("c0", "fitted_c"):
        saved = baseline["arms"][arm]["record"]
        x = np.asarray(saved["endpoint_east_north_km"])
        p, endpoint = fixed(scan, node, keep, arm, x)
        pp, truth = fixed(scan, node, keep, arm, REFERENCE_XY)

        def value(xy, arm=arm):
            return fixed(scan, node, keep, arm, xy)[1]["score"]

        hessian = finite_hessian(value, x)
        eigenvalues = np.linalg.eigvalsh(hessian)
        gradients = {}
        for name in blocks:

            def component(xy, name=name, arm=arm):
                d = fixed(scan, node, keep, arm, xy)[1]
                return sum(d["prior_cost"].values()) if name == "all_priors" else d[name]

            gradients[name] = finite_gradient(component, REFERENCE_XY)
        differences = {
            name: (
                sum(truth["prior_cost"].values()) - sum(endpoint["prior_cost"].values())
                if name == "all_priors"
                else truth[name] - endpoint[name]
            )
            for name in blocks
        }
        assert abs(sum(differences.values()) - (truth["score"] - endpoint["score"])) < 1e-6
        exact, _, _ = exact_conditional_frequency(p, x)
        linear, _ = p.conditional_frequency(x)
        arms[arm] = dict(
            truth_minus_endpoint_loss=truth["score"] - endpoint["score"],
            loss_component_differences=differences,
            component_gradients_at_true_site=gradients,
            profiled_position_hessian=hessian,
            hessian_eigenvalues=eigenvalues,
            delta_loss_one_axis_scales_km=np.sqrt(2 / eigenvalues),
            curvature_scales_are_not_calibrated_confidence_intervals=True,
            exact_vs_linearized_frequency_max_hz=float(np.max(abs(exact - linear))),
            gates_at_true_site=retained_metrics(pp, REFERENCE_XY),
        )
    rows = []
    for kind in ("family", "track", "prior"):
        for path in sorted(OUT.glob(f"{kind}_[0-9][0-9].json")):
            d = read(path)
            for arm, result in d["arms"].items():
                rows.append(
                    dict(
                        kind=kind,
                        target=d["target"],
                        arm=arm,
                        deleted_points=d["deleted_points"],
                        error_km=position_error(result["endpoint_latlon"]),
                        RMS_hz=result["RMS_hz"],
                        score=result["score"],
                    )
                )
    with (OUT / "interventions.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    fig, axes = plt.subplots(1, 3, figsize=(17, 6))
    for kind, ax in zip(("family", "track"), axes[:2], strict=True):
        chosen = sorted(
            [r for r in rows if r["kind"] == kind and r["arm"] == "c0"], key=lambda r: r["error_km"]
        )
        if kind == "track":
            chosen = chosen[:10]
        labels = [r["target"].replace("DS23-0217-", "").split("-RF")[0] for r in chosen]
        ax.barh(labels, [r["error_km"] for r in chosen], color="steelblue")
        ax.axvline(
            position_error(baseline["arms"]["c0"]["record"]["endpoint_latlon"]),
            c="black",
            ls="--",
            label="Full ALGO01",
        )
        ax.invert_yaxis()
        ax.set(
            xlabel="Position error after deletion (km)", title=f"Delete one {kind}: c=0 influence"
        )
        ax.tick_params(axis="y", labelsize=8)
        ax.legend(fontsize=8)
    ax = axes[2]
    controls = [r for r in rows if r["kind"] == "prior" and r["arm"] == "c0"]
    for i, r in enumerate(controls):
        other = next(
            q
            for q in rows
            if q["kind"] == "prior" and q["arm"] == "fitted_c" and q["target"] == r["target"]
        )
        ax.barh(
            i - 0.18, r["error_km"], height=0.36, color="steelblue", label="c=0" if i == 0 else None
        )
        ax.barh(
            i + 0.18,
            other["error_km"],
            height=0.36,
            color="darkorange",
            label="fitted c" if i == 0 else None,
        )
    ax.set(
        yticks=np.arange(len(controls)),
        yticklabels=[r["target"] for r in controls],
        xlabel="Position error (km)",
        title="Fixed generic model sensitivities",
    )
    ax.invert_yaxis()
    ax.legend(fontsize=8)
    for ax in axes:
        ax.grid(axis="x", alpha=0.2)
        ax.set_axisbelow(True)
    fig.suptitle(
        "DS23-0217: no single deletion or tested generic prior/noise control resolves the error\n"
        "Deletion plots are influence diagnostics, not a GPS-based rejection policy"
    )
    fig.tight_layout()
    fig.savefig(OUT / "influence_and_controls.png", dpi=150)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 5))
    for i, arm in enumerate(("c0", "fitted_c")):
        vals = [arms[arm]["loss_component_differences"][k] for k in blocks]
        ax.bar(np.arange(len(blocks)) + (i - 0.5) * 0.34, vals, width=0.34, label=arm)
    ax.axhline(0, c="black", lw=0.8)
    ax.set(
        xticks=np.arange(len(blocks)),
        xticklabels=[
            "Weighted data",
            "Grouped-noise Gamma cost",
            "Nuisance log-volume",
            "All nuisance priors",
        ],
        ylabel="Loss at true site minus loss at fitted site",
        title="The combined nuisance priors slightly favor the true site",
    )
    ax.legend()
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT / "loss_decomposition.png", dpi=150)
    plt.close(fig)
    write(
        OUT / "details.json",
        dict(
            arms=arms,
            interventions=rows,
            explicit_GPS_diagnostic=True,
            original_algorithm_and_results_unchanged=True,
            successful_interventions_by_kind=dict(Counter(r["kind"] for r in rows)),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage", required=True, choices=("prepare", "surfaces", "restarts", "details")
    )
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    {"prepare": prepare, "surfaces": surfaces, "restarts": restarts, "details": details}[
        args.stage
    ]()
