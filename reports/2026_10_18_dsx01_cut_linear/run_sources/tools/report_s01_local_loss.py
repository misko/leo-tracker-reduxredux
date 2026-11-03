"""Plot sampled research loss surfaces, GPS-start paths and multiscale slopes."""

import argparse
import csv
import html
import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS
from localize_merged_track_catalogue import distance_km
from probe_s01_local_loss import OUTPUT, REFERENCE, ROOT

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
from matplotlib.lines import Line2D

LABELS = dict(
    shared_phase="Shared phase",
    family_rate="Satellite family rate",
    orbit_em="Orbital MAP / EM-like",
    penalized_split="Penalized subdivision",
    correlated_noise="Correlated noise",
    receiver_smooth="Smooth receiver error",
)


def gradient(samples, key, h):
    """Central and one-sided coordinate slopes in loss units per kilometer."""
    zero = samples[0.0, 0.0]["metrics"][key]["score"]
    g, positive, negative = [], [], []
    for axis in range(2):
        p, m = [0.0, 0.0], [0.0, 0.0]
        p[axis], m[axis] = h, -h
        plus = samples[tuple(p)]["metrics"][key]["score"]
        minus = samples[tuple(m)]["metrics"][key]["score"]
        g.append((plus - minus) / (2 * h))
        positive.append((plus - zero) / h)
        negative.append((zero - minus) / h)
    return dict(
        central_east_north=g, positive_east_north=positive, negative_east_north=negative, step_km=h
    )


def data_term(fit):
    return sum(
        min(r["points"], 50) * (min(r["cost"] / r["points"], 36) if r["compatible"] else 36)
        for r in fit["rows"]
        if r["active_curvature"]
    )


def run():
    warm = OUTPUT.name == "warm_restart"
    earlier = json.loads(
        (
            ROOT
            / "reports/2026_10_18_dsx01_retention_localization"
            / "DSX01-S01/refined_endpoints.json"
        ).read_text()
    )
    surfaces = {m: json.loads((OUTPUT / f"{m}_surface.json").read_text()) for m in METHODS}
    samples = {m: {tuple(r["east_north_km"]): r for r in a["samples"]} for m, a in surfaces.items()}
    endpoints = {m: json.loads((OUTPUT / f"{m}_endpoints.json").read_text()) for m in METHODS}
    truths = {m: json.loads((OUTPUT / f"{m}_truth_all_tracks.json").read_text()) for m in METHODS}
    records, derivatives, changes = [], [], {}
    for method in METHODS:
        for arm in ("c0", "fitted_c"):
            key = f"{arm}/{method}"
            a = surfaces[method]
            start, end = truths[method][key], endpoints[method][key]
            point = a["endpoints"][key]["final_east_north_km"]
            minimum = min(samples[method].values(), key=lambda r: r["metrics"][key]["score"])
            g = gradient(samples[method], key, 0.5)
            record = dict(
                method=method,
                arm=arm,
                truth_loss=start["score"],
                endpoint_loss=end["score"],
                loss_change=end["score"] - start["score"],
                endpoint_east_km=point[0],
                endpoint_north_km=point[1],
                endpoint_error_km=distance_km(
                    (end["latitude_deg"], end["longitude_deg"]), REFERENCE
                ),
                stationary_stencil_km=a["endpoints"][key]["stationary_stencil_scale_km"],
                best_sample_east_km=minimum["east_north_km"][0],
                best_sample_north_km=minimum["east_north_km"][1],
                best_sample_loss=minimum["metrics"][key]["score"],
                truth_curved_points=sum(
                    r["points"] for r in start["rows"] if r["compatible"] and r["active_curvature"]
                ),
                endpoint_curved_points=sum(
                    r["points"] for r in end["rows"] if r["compatible"] and r["active_curvature"]
                ),
                truth_data_term=data_term(start),
                endpoint_data_term=data_term(end),
                truth_prior_complexity_term=start["score"] - data_term(start),
                endpoint_prior_complexity_term=end["score"] - data_term(end),
                slope_east_h0_5=g["central_east_north"][0],
                slope_north_h0_5=g["central_east_north"][1],
                extra_locations=a["additional_locations_used"],
                initial_step_km=a.get("initial_step_km", 2.0),
                fine_start=a.get("fine_start", False),
            )
            records.append(record)
            for h in (0.125, 0.5, 1.0):
                derivatives.append(
                    dict(method=method, arm=arm, **gradient(samples[method], key, h))
                )
            before = {r["component"]: r for r in start["rows"] if r["active_curvature"]}
            after = {r["component"]: r for r in end["rows"] if r["active_curvature"]}
            changes[key] = dict(
                gained=[
                    k for k, v in after.items() if v["compatible"] and not before[k]["compatible"]
                ],
                lost=[
                    k for k, v in after.items() if not v["compatible"] and before[k]["compatible"]
                ],
                relabeled=[
                    dict(component=k, old=before[k]["candidate_norad"], new=v["candidate_norad"])
                    for k, v in after.items()
                    if v["compatible"]
                    and before[k]["compatible"]
                    and v["candidate_norad"] != before[k]["candidate_norad"]
                ],
            )
            common = [k for k in before if before[k]["compatible"] and after[k]["compatible"]]
            count = sum(before[k]["points"] for k in common)
            record.update(
                common_curved_points=count,
                common_curve_native_rms_truth_hz=float(
                    np.sqrt(
                        sum(before[k]["points"] * before[k]["rms_hz"] ** 2 for k in common)
                        / max(1, count)
                    )
                ),
                common_curve_native_rms_endpoint_hz=float(
                    np.sqrt(
                        sum(after[k]["points"] * after[k]["rms_hz"] ** 2 for k in common)
                        / max(1, count)
                    )
                ),
                common_curved_points_same_label=sum(
                    before[k]["points"]
                    for k in common
                    if before[k]["candidate_norad"] == after[k]["candidate_norad"]
                ),
                previous_blind_error_km=distance_km(
                    (earlier[key]["latitude_deg"], earlier[key]["longitude_deg"]), REFERENCE
                ),
                previous_blind_loss=earlier[key]["score"],
            )
    write(OUTPUT / "summary.json", records)
    write(OUTPUT / "gradients.json", derivatives)
    write(OUTPUT / "curved_membership_changes.json", changes)
    c_ablation = []
    for method in METHODS:
        for location, fits in (("gps", truths[method]), ("local_endpoint", endpoints[method])):
            pair = [fits[f"{arm}/{method}"] for arm in ("c0", "fitted_c")]
            rows = [
                {
                    r["component"]: r
                    for r in fit["rows"]
                    if r["active_curvature"] and r["compatible"]
                }
                for fit in pair
            ]
            common = rows[0].keys() & rows[1].keys()
            count = sum(rows[0][k]["points"] for k in common)
            result = dict(
                method=method,
                location=location,
                common_curved_points=count,
                same_label_points=sum(
                    rows[0][k]["points"]
                    for k in common
                    if rows[0][k]["candidate_norad"] == rows[1][k]["candidate_norad"]
                ),
            )
            for arm, fit, data in zip(("c0", "fitted_c"), pair, rows, strict=True):
                result[f"native_rms_{arm}_hz"] = (
                    float(
                        np.sqrt(
                            sum(data[k]["points"] * data[k]["rms_hz"] ** 2 for k in common) / count
                        )
                    )
                    if count
                    else None
                )
                result[f"innovation_rms_{arm}_hz"] = (
                    float(
                        np.sqrt(
                            sum(np.sum(np.array(data[k]["innovations_hz"]) ** 2) for k in common)
                            / count
                        )
                    )
                    if count
                    else None
                )
                result[f"score_{arm}"] = fit["score"]
                result[f"position_error_{arm}_km"] = distance_km(
                    (fit["latitude_deg"], fit["longitude_deg"]), REFERENCE
                )
            c_ablation.append(result)
    write(OUTPUT / "c_ablation.json", c_ablation)
    with (OUTPUT / "c_ablation.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(c_ablation[0]))
        writer.writeheader()
        writer.writerows(c_ablation)
    with (OUTPUT / "summary.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    # Same log colour transformation across all models/arms. The interpolation
    # is display only; no optimizer or confidence calculation consumes it.
    maximum = 0.0
    for method in METHODS:
        for arm in ("c0", "fitted_c"):
            values = np.array(
                [r["metrics"][f"{arm}/{method}"]["score"] for r in samples[method].values()]
            )
            maximum = max(maximum, float(np.log10(1 + values.max() - values.min())))
    levels = np.linspace(0, maximum, 25)

    def map_panel(ax, method, arm, *, span=10.0, color_levels=None):
        key = f"{arm}/{method}"
        points = np.array(list(samples[method]))
        values = np.array([samples[method][tuple(p)]["metrics"][key]["score"] for p in points])
        if span < 10:
            keep = np.max(abs(points), axis=1) <= span
            points, values = points[keep], values[keep]
        triangulation = mtri.Triangulation(points[:, 0], points[:, 1])
        image = ax.tricontourf(
            triangulation,
            np.log10(1 + values - values.min()),
            levels=levels if color_levels is None else color_levels,
            cmap="viridis_r",
        )
        ax.scatter(points[:, 0], points[:, 1], color="k", s=3, alpha=0.25)
        path = np.array([r["east_north_km"] for r in surfaces[method]["paths"][key]])
        coarse_file = (
            OUTPUT / method / "coarse_start" / f"{method}_surface.json"
            if warm
            else OUTPUT / "coarse_start" / f"{method}_surface.json"
        )
        if surfaces[method].get("fine_start", False) and coarse_file.exists():
            old_path = np.array(
                [r["east_north_km"] for r in json.loads(coarse_file.read_text())["paths"][key]]
            )
            ax.plot(old_path[:, 0], old_path[:, 1], color="silver", ls="--", lw=1)
            ax.scatter(*old_path[-1], marker="X", s=65, color="silver", edgecolors="k", zorder=7)
        ax.plot(path[:, 0], path[:, 1], "w.-", lw=1.4, ms=5)
        p = path[-1]
        ax.scatter([0], [0], marker="*", s=150, color="white", edgecolors="k", zorder=6)
        ax.scatter([p[0]], [p[1]], marker="o", s=70, color="#ff7f0e", edgecolors="k", zorder=7)
        best = points[np.argmin(values)]
        ax.scatter(
            [best[0]],
            [best[1]],
            marker="s",
            s=40,
            facecolors="none",
            edgecolors="#ff36dd",
            lw=1.5,
            zorder=8,
        )
        d = -np.array(gradient(samples[method], key, 0.5)["central_east_north"])
        if np.linalg.norm(d):
            d *= (0.35 if span < 10 else 1.8) / np.linalg.norm(d)
            ax.arrow(
                0,
                0,
                d[0],
                d[1],
                width=0.005 if span < 10 else 0.04,
                head_width=0.07 if span < 10 else 0.4,
                color="red",
                zorder=5,
            )
        ax.add_patch(plt.Circle((0, 0), 10, fill=False, color="k", lw=0.7))
        r = next(r for r in records if r["method"] == method and r["arm"] == arm)
        ax.set(
            xlabel="East of true position (km)",
            ylabel="North of true position (km)",
            xlim=(-span, span),
            ylim=(-span, span),
            aspect="equal",
            title=f"{LABELS[method]} · {'fitted c' if arm == 'fitted_c' else 'c = 0'}\n"
            f"GPS-start endpoint error {r['endpoint_error_km']:.3f} km",
        )
        ax.grid(alpha=0.15)
        return image

    legend = [
        Line2D(
            [],
            [],
            marker="*",
            color="white",
            markeredgecolor="k",
            ls="none",
            label="True position / local start",
        ),
        Line2D(
            [],
            [],
            marker="o",
            color="#ff7f0e",
            markeredgecolor="k",
            ls="none",
            label="Endpoint reached from GPS",
        ),
        Line2D([], [], marker="s", color="#ff36dd", ls="none", label="Best sampled point"),
        Line2D([], [], color="red", label="Descent direction: 0.5 km central stencil"),
    ]
    if any(a.get("fine_start", False) for a in surfaces.values()):
        legend.append(
            Line2D(
                [],
                [],
                marker="X",
                color="silver",
                markeredgecolor="k",
                ls="--",
                label="2 km-start endpoint and path",
            )
        )
    step_label = (
        "125 m initial step"
        if all(a.get("fine_start", False) for a in surfaces.values())
        else "2 km initial step"
    )
    for arm in ("c0", "fitted_c"):
        fig, axes = plt.subplots(3, 2, figsize=(13, 15), layout="constrained")
        for ax, method in zip(axes.flat, METHODS, strict=True):
            image = map_panel(ax, method, arm)
        fig.colorbar(
            image,
            ax=list(axes.flat),
            shrink=0.7,
            label="log10(1 + loss − minimum sampled loss), each panel",
        )
        fig.legend(handles=legend, loc="outside lower center", fontsize=8, ncols=2)
        fig.suptitle(
            "DSX01 S01 · 10 km radius about GPS · "
            + ("consistent warm calibration restart\n" if warm else "cold calibration restart\n")
            + step_label
            + "; dots are evaluations; contour interpolation is display only"
        )
        fig.savefig(OUTPUT / f"{arm}_loss_surfaces.png", dpi=165)
        plt.close(fig)
        zoom_maximum = 0.0
        for method in METHODS:
            values = np.array(
                [
                    r["metrics"][f"{arm}/{method}"]["score"]
                    for p, r in samples[method].items()
                    if max(abs(x) for x in p) <= 1.25
                ]
            )
            zoom_maximum = max(zoom_maximum, float(np.log10(1 + values.max() - values.min())))
        zoom_levels = np.linspace(0, zoom_maximum, 25)
        fig, axes = plt.subplots(3, 2, figsize=(13, 15), layout="constrained")
        for ax, method in zip(axes.flat, METHODS, strict=True):
            image = map_panel(ax, method, arm, span=1.25, color_levels=zoom_levels)
        fig.colorbar(
            image,
            ax=list(axes.flat),
            shrink=0.7,
            label="log10(1 + loss − lowest sampled loss within this view)",
        )
        fig.legend(handles=legend, loc="outside lower center", fontsize=8, ncols=2)
        fig.suptitle(
            "S01 GPS neighbourhood · "
            + step_label
            + " · "
            + ("warm calibration restart\n" if warm else "cold calibration restart\n")
            + "Local samples only; blank areas lie outside their convex hull"
        )
        fig.savefig(OUTPUT / f"{arm}_gps_zoom.png", dpi=165)
        plt.close(fig)
    fig, axes = plt.subplots(3, 2, figsize=(10, 13), layout="constrained")
    for ax, method in zip(axes.flat, METHODS, strict=True):
        for h, color in zip(
            (0.125, 0.5, 1.0), ("steelblue", "darkorange", "seagreen"), strict=True
        ):
            direction = -np.array(
                gradient(samples[method], f"fitted_c/{method}", h)["central_east_north"]
            )
            magnitude = np.linalg.norm(direction)
            if magnitude:
                direction /= magnitude
                ax.arrow(
                    0,
                    0,
                    *direction,
                    color=color,
                    width=0.015,
                    head_width=0.09,
                    length_includes_head=True,
                )
            ax.plot([], [], color=color, label=f"h={h:g} km; |slope|={magnitude:.1f}/km")
        ax.add_patch(plt.Circle((0, 0), 1, fill=False, color="gray", lw=0.7))
        ax.axhline(0, color="gray", lw=0.5)
        ax.axvline(0, color="gray", lw=0.5)
        ax.set(
            xlim=(-1.2, 1.2),
            ylim=(-1.2, 1.2),
            aspect="equal",
            title=LABELS[method],
            xlabel="East direction",
            ylabel="North direction",
        )
        ax.legend(fontsize=7, loc="upper right")
    fig.suptitle(
        "S01 fitted c: finite-difference descent directions at GPS\n"
        "Arrows show direction only; different step sizes can cross different gates"
    )
    fig.savefig(OUTPUT / "fitted_c_gradient_directions.png", dpi=165)
    plt.close(fig)
    for method in METHODS:
        fig, axes = plt.subplots(2, 2, figsize=(13, 11), layout="constrained")
        for ax, arm in zip(axes[0], ("c0", "fitted_c"), strict=True):
            image = map_panel(ax, method, arm)
        fig.colorbar(image, ax=list(axes[0]), shrink=0.7, label="log10(1 + Δ sampled loss)")
        frozen = json.loads((OUTPUT / f"{method}_frozen_cuts.json").read_text())
        key = f"fitted_c/{method}"
        zero = samples[method][0.0, 0.0]["metrics"][key]["score"]
        for axis, color, label in ((0, "steelblue", "East/west"), (1, "darkorange", "North/south")):
            rows = [r for r in frozen if r["axis"] == axis]
            x = [r["displacement_km"] for r in rows]
            fixed = [r["scores"][key] - zero for r in rows]
            profiled = [
                samples[method][(v, 0.0) if axis == 0 else (0.0, v)]["metrics"][key]["score"] - zero
                for v in x
            ]
            axes[1, 0].plot(x, profiled, "o-", color=color, ms=4, label=label + ", refitted")
            axes[1, 0].plot(x, fixed, "s--", color=color, ms=3, label=label + ", fixed calibration")
        axes[1, 0].axhline(0, color="k", lw=0.6)
        axes[1, 0].set(
            xlabel="Displacement from GPS (km)",
            ylabel="Loss − loss at GPS",
            title="Fitted c: refitting versus frozen GPS calibration",
        )
        axes[1, 0].legend(fontsize=7)
        for arm in ("c0", "fitted_c"):
            path = surfaces[method]["paths"][f"{arm}/{method}"]
            y = np.array([r["score"] for r in path])
            axes[1, 1].plot(range(len(y)), y - y[0], "o-", label=arm, ms=4)
        axes[1, 1].set(
            xlabel="Accepted local-search move",
            ylabel="Loss − initial loss at GPS",
            title="Descent starting at the correct position",
        )
        axes[1, 1].legend()
        for ax in axes[1]:
            ax.grid(alpha=0.2)
        fig.suptitle(
            LABELS[method] + " · same observations, causal candidates and paired c budgets"
        )
        fig.savefig(OUTPUT / f"{method}_detail.png", dpi=165)
        plt.close(fig)
    # Compact local HTML gallery, generated from the measured tables.
    columns = [
        "method",
        "arm",
        "endpoint_east_km",
        "endpoint_north_km",
        "endpoint_error_km",
        "truth_loss",
        "endpoint_loss",
        "stationary_stencil_km",
    ]
    table = "<table><tr>" + "".join(f"<th>{html.escape(k)}</th>" for k in columns) + "</tr>"
    for r in records:
        table += "<tr>" + "".join(f"<td>{html.escape(str(r[k]))}</td>" for k in columns) + "</tr>"
    table += "</table>"
    note = (
        "GPS defines the diagnostic region and starting point; this is not blind evaluation. "
        "Loss includes hard gates, clutter and complexity terms. "
        "It is not a calibrated probability. "
        + (
            "Every position uses a consistent improved GPS-calibration restart "
            if warm
            else "Every position uses the existing cold initializer "
        )
        + "with three nuisance-update rounds; "
        "this is the effective algorithm surface, not a proven exact profile likelihood. "
        "Dots are evaluated locations; contours are linear visual interpolation. Local endpoints "
        "are stencil minima to the recorded scale, not mathematical/global optimum guarantees."
    )
    gallery = "".join(
        f"<h2>{html.escape(LABELS[m])}</h2><img src='{m}_detail.png'>" for m in METHODS
    )
    (OUTPUT / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>S01 local loss</title>"
        "<style>body{font:16px sans-serif;max-width:1500px;margin:2em auto}"
        "img{width:100%}table{border-collapse:collapse}"
        "td,th{padding:8px;border:1px solid #bbb}</style>"
        f"<h1>DSX01 S01: truth-centred local loss</h1><p>{html.escape(note)}</p>" + table + gallery
    )
    write(
        OUTPUT / "report_provenance.json",
        dict(
            reporting_inputs="truth-centred diagnostic; reference intentionally available",
            surface_not_normalized_probability=True,
            prior_blind_comparison_modified=False,
            source=str((ROOT / "tools/report_s01_local_loss.py").relative_to(ROOT)),
        ),
    )
    if warm:
        cold = json.loads((OUTPUT.parent / "summary.json").read_text())
        comparison = []
        for row in records:
            old = next(r for r in cold if (r["method"], r["arm"]) == (row["method"], row["arm"]))
            comparison.append(
                dict(
                    method=row["method"],
                    arm=row["arm"],
                    cold_truth_loss=old["truth_loss"],
                    warm_truth_loss=row["truth_loss"],
                    cold_endpoint_loss=old["endpoint_loss"],
                    warm_endpoint_loss=row["endpoint_loss"],
                    cold_endpoint_error_km=old["endpoint_error_km"],
                    warm_endpoint_error_km=row["endpoint_error_km"],
                    warm_endpoint_east_north_km=[row["endpoint_east_km"], row["endpoint_north_km"]],
                    cold_endpoint_east_north_km=[old["endpoint_east_km"], old["endpoint_north_km"]],
                )
            )
        write(OUTPUT / "branch_comparison.json", comparison)
    print(json.dumps(records), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warm", action="store_true")
    if parser.parse_args().warm:
        OUTPUT = OUTPUT / "warm_restart"
    run()
