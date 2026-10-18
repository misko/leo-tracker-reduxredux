"""Postfit-only evaluation GPS markers and galleries for audited regional maps."""

# ruff: noqa: E501

import csv
import hashlib
import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from dsx01_inference_audit import CENTER
from localize_merged_track_catalogue import distance_km
from map_dsx01_clean_region import SPECS
from run_dsx01_clean_region import OUTPUT

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri

REFERENCE = (37.849061591561885, -122.48574968092912)
TRUTH = np.array(
    [
        (REFERENCE[1] - CENTER[1]) * 111.32 * np.cos(np.deg2rad(CENTER[0])),
        (REFERENCE[0] - CENTER[0]) * 111.0,
    ]
)
LEGACY = (
    "shared_phase",
    "family_rate",
    "orbit_em",
    "penalized_split",
    "correlated_noise",
    "receiver_smooth",
)
LINEAR = ("joint", "shape", "continuation", "white_joint", "white_shape")
EXPECTED = (*SPECS, *[f"legacy_{v}" for v in LEGACY], *[f"linear_{v}" for v in LINEAR])


def draw(ax, data, arm, *, title=None):
    row = data["arms"][arm]
    xy, z = np.array(row["map_points"]), np.array(row["loss"])
    endpoint = np.array(row["fit"]["parameters"])[:2]
    probes = row["multistart_probes"]
    minimum = min(float(z.min()), row["fit"]["score"], *[p["score"] for p in probes])
    triangulation = mtri.Triangulation(xy[:, 0], xy[:, 1])
    mesh = ax.tripcolor(
        triangulation, np.log1p(np.maximum(0, z - minimum)), shading="gouraud", cmap="viridis"
    )
    interp = mtri.LinearTriInterpolator(triangulation, z)
    e, n = np.meshgrid(np.arange(-8, 8.01, 4), np.arange(-8, 8.01, 4))
    mask = e**2 + n**2 < 8.5**2
    ge, gn = interp.gradient(e[mask], n[mask])
    norm = np.sqrt(ge**2 + gn**2)
    ax.quiver(
        e[mask],
        n[mask],
        -ge / np.maximum(norm, 1e-12),
        -gn / np.maximum(norm, 1e-12),
        color="white",
        alpha=0.7,
        scale=14,
        width=0.004,
    )
    for probe in probes:
        history = np.array([r["parameters"][:2] for r in probe["history"]])
        if len(history):
            ax.plot(history[:, 0], history[:, 1], color="tomato", lw=0.8, alpha=0.65)
        p = np.array(probe["parameters"])[:2]
        ax.plot(*p, "x", color="tomato", ms=5)
    ax.plot(*endpoint, "o", mfc="none", mec="cyan", ms=8, mew=1.5, label="regional-search endpoint")
    ax.plot(*TRUTH, "*", color="magenta", ms=10, label="GPS, postfit only")
    ax.plot(0, 0, "+", color="black", ms=9, label="regional center")
    stops = row.get("map_profile_stops", [])
    if stops:
        limited = np.array([s == "iteration_budget" for s in stops])
        if limited.any():
            ax.scatter(
                xy[limited, 0],
                xy[limited, 1],
                s=8,
                c="black",
                alpha=0.6,
                label="nuisance refit budget limit",
            )
    ax.add_patch(plt.Circle((0, 0), 10, fill=False, color="black", lw=0.8))
    ax.set(
        xlim=(-12.5, 12.5),
        ylim=(-12.5, 12.5),
        aspect="equal",
        title=title or f"{data['method']} / {arm}",
        xlabel="East from regional center (km)",
        ylabel="North (km)",
    )
    ax.grid(alpha=0.15)
    return mesh


def table(rows):
    header = (
        "| Method | S01 | S02 | S03 | S04 | S05 |\n| --- | ---: | ---: | ---: | ---: | ---: |\n"
    )
    for method in EXPECTED:
        values = []
        for k in range(1, 6):
            selected = [r for r in rows if r["case"] == f"DSX01-S0{k}" and r["method"] == method]
            by_arm = {r["arm"]: r for r in selected}
            values.append(
                f"{by_arm['c0']['error_km']:.3f} / {by_arm['fitted_c']['error_km']:.3f}"
                if len(by_arm) == 2
                else "pending"
            )
        header += f"| {method} | " + " | ".join(values) + " |\n"
    return header


def run():
    paths = sorted(OUTPUT.glob("DSX*/surfaces/*/result.json"))
    rows, bindings, values = [], {}, {}
    for path in paths:
        data = json.loads(path.read_text())
        case, method = data["case"], data["method"]
        bindings[str(path.relative_to(OUTPUT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        values[case, method] = data
        figure = path.with_name("loss_gradient.png")
        if not figure.exists() or method.startswith("legacy_"):
            fig, axes = plt.subplots(1, 2, figsize=(12, 5.8), layout="constrained")
            for ax, arm in zip(axes, ("c0", "fitted_c"), strict=True):
                mesh = draw(ax, data, arm, title=f"{case}: {method} / {arm}")
                fig.colorbar(
                    mesh,
                    ax=ax,
                    label="log(1 + loss above best sampled/optimized value)",
                    shrink=0.75,
                )
            axes[0].legend(loc="upper right", fontsize=7)
            fig.suptitle(
                "10 km disk; 25 × 25 km search bounds. White: downhill; red: optimization paths.\nAssignments fixed after fresh full-catalogue node search; GPS marker is evaluation only.",
                fontsize=10,
            )
            fig.savefig(figure, dpi=140)
            plt.close(fig)
        for arm, row in data["arms"].items():
            fit = row["fit"]
            endpoint = np.array(fit["parameters"])[:2]
            center = row["multistart_probes"][0]
            xy = np.array(center["parameters"])[:2]
            center_latlon = (
                CENTER[0] + xy[1] / 111.0,
                CENTER[1] + xy[0] / (111.32 * np.cos(np.deg2rad(CENTER[0]))),
            )
            probes = row["multistart_probes"]
            best = min([fit, *probes], key=lambda p: p["score"])
            rows.append(
                dict(
                    case=case,
                    method=method,
                    arm=arm,
                    latitude_deg=row["endpoint_latlon"][0],
                    longitude_deg=row["endpoint_latlon"][1],
                    east_km=float(endpoint[0]),
                    north_km=float(endpoint[1]),
                    error_km=distance_km(row["endpoint_latlon"], REFERENCE),
                    center_start_error_km=distance_km(center_latlon, REFERENCE),
                    center_start_east_km=float(xy[0]),
                    center_start_north_km=float(xy[1]),
                    endpoint_gradient_norm=float(np.linalg.norm(row["gradient_at_endpoint"])),
                    center_gradient_east=float(row["gradient_at_center"][0]),
                    center_gradient_north=float(row["gradient_at_center"][1]),
                    score=float(fit["score"]),
                    best_probe_improvement=float(fit["score"] - best["score"]),
                    optimizer_stop=fit.get("stopped", str(fit.get("converged"))),
                    map_points=len(row["map_points"]),
                    curve_residual_rms_hz=row.get("residual_rms_hz"),
                    assignment_scope="conditional on freshly selected same-scan hypothesis",
                    surface_profile_budget=row.get("map_profile_iteration_budget", "integrated"),
                    loss_plot=str(figure.relative_to(OUTPUT)),
                )
            )
    if rows:
        with (OUTPUT / "position_and_gradient_summary.csv").open("w") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    write(OUTPUT / "position_and_gradient_summary.json", rows)
    write(OUTPUT / "map_bindings.json", bindings)
    cold_comparison = []
    for k in range(1, 6):
        case = f"DSX01-S0{k}"
        old_path = (
            OUTPUT.parent
            / "2026_10_18_dsx01_satellite_prior_controls"
            / case
            / "normal/endpoints.json"
        )
        if (case, "normal") not in values or not old_path.exists():
            continue
        old = json.loads(old_path.read_text())["fits"]["fitted_c"]
        current = values[case, "normal"]
        old_labels = {r["component"]: r["candidate_norad"] for r in old["rows"]}
        new_labels = {
            r["component"]: r["candidate_norad"]
            for r in current["selected_assignment_node"]["seed"]["rows"]
        }
        cold_comparison.append(
            dict(
                case=case,
                previous_inherited_blind_error_km=distance_km(
                    [old["latitude_deg"], old["longitude_deg"]], REFERENCE
                ),
                fresh_error_km=distance_km(
                    current["arms"]["fitted_c"]["endpoint_latlon"], REFERENCE
                ),
                changed_fragment_labels=sum(old_labels[c] != n for c, n in new_labels.items()),
                old_result_read_only_after_inference=True,
                old_result_sha256=hashlib.sha256(old_path.read_bytes()).hexdigest(),
            )
        )
    write(OUTPUT / "fresh_vs_previous_baseline.json", cold_comparison)
    for k in range(1, 6):
        case = f"DSX01-S0{k}"
        lines = [
            f"# {case}: audited regional loss and gradient maps\n",
            "Each figure shows zero/fitted c with identical observations, assignment and aliases. GPS is postfit only. These are conditional-assignment surfaces, not exhaustive satellite marginalization.\n",
        ]
        for method in EXPECTED:
            if (case, method) in values:
                lines.append(f"## {method}\n\n![{method}](surfaces/{method}/loss_gradient.png)\n")
            else:
                lines.append(f"## {method}\n\nPending.\n")
        (OUTPUT / case / "README.md").write_text("\n".join(lines))
    featured = (
        "legacy_shared_phase",
        "legacy_orbit_em",
        "normal",
        "clock_variance",
        "full_trend",
        "linear_white_joint",
        "frame_linked_300",
    )
    fig, axes = plt.subplots(
        len(featured), 5, figsize=(20, 4 * len(featured)), layout="constrained"
    )
    for i, method in enumerate(featured):
        for j in range(5):
            case = f"DSX01-S0{j + 1}"
            ax = axes[i, j]
            if (case, method) in values:
                draw(ax, values[case, method], "fitted_c", title=f"{case} / {method}")
                ax.set_xlabel("East (km)")
            else:
                ax.text(0.5, 0.5, "Pending", ha="center", transform=ax.transAxes)
                ax.set_axis_off()
    fig.suptitle(
        "Fresh regional discovery: conditional loss, downhill directions and convergence\n25 × 25 km box; 10 km mapped disk. Magenta GPS markers enter only this reporter."
    )
    fig.savefig(OUTPUT / "overview.png", dpi=130)
    plt.close(fig)
    sample_methods = (
        "legacy_shared_phase",
        "legacy_orbit_em",
        "normal",
        "clock_variance",
        "linear_white_joint",
        "frame_linked_300",
    )
    fig, axes = plt.subplots(2, 3, figsize=(15, 10), layout="constrained")
    for ax, method in zip(axes.ravel(), sample_methods, strict=True):
        if ("DSX01-S01", method) in values:
            mesh = draw(ax, values["DSX01-S01", method], "fitted_c", title=method)
            fig.colorbar(mesh, ax=ax, shrink=0.7, label="log(1 + Δloss)")
    axes[0, 0].legend(loc="upper left", fontsize=6)
    fig.suptitle(
        "S01: fresh regional searches, fitted c. Each panel has its own loss scale.\n"
        "White: downhill; red: optimization paths; cyan: regional endpoint; magenta: evaluation GPS."
    )
    fig.savefig(OUTPUT / "S01_comparison.png", dpi=140)
    plt.close(fig)
    expected_count = 5 * len(EXPECTED)
    text = f"""# DSX01: causal input audit and fresh regional loss surfaces

**{len(paths)} / {expected_count} scan/configuration maps are complete.** There are six original graph association methods, 38 current correction/prior configurations and five linear-transfer configurations. These are 49 configurations, not 49 independent algorithms.

The search box is **25 × 25 km**, centered at **37.906° N, −122.545° E**. It extends ±12.5 km east/north. Maps sample a **10 km radius around that regional center**, on a 2 km grid; continuous optimizers refine endpoints. GPS is never a search start or center for these maps.

The new branch generates calibration proposals from zero, scores the entire regional Starlink candidate bank (S01 1,707; S02 1,479; S03 1,422; S04 1,427; S05 1,424), and refreshes identities at every one of the 25 regional discovery nodes. It does not read earlier fitted positions, radio states, label/alias lists or following-TLE diagnostics. Quality weights and linear nominations are regenerated from fresh same-scan evidence. A runtime read guard rejects old endpoint/seed/diagnostic inputs, and each result records actual report files opened.

**The surfaces still condition on each configuration's selected assignment branch.** Finite proposals and label refresh do not prove a global optimum over all satellite/alias combinations. A smooth conditional basin does not establish satellite identity. This qualification also applies to the convergence paths. The six original methods use 48-iteration nuisance profiles with a sparse Jacobian tested against the unchanged finite-difference objective. Initial two-step maps failed longer-refit controls and are preserved as superseded diagnostics. Saved per-pixel stop reasons expose incomplete profiling; a finite budget is not an exact global profile. Newer methods integrate nuisance coefficients (or use their declared variational approximation) at each pixel. Colors are per-method loss differences, not comparable calibrated probabilities.

The nominal/previous TLE audit requires **both collection time and element epoch ≤ the pre-scan cutoff**, checks element bytes against provenance, and binds nominal element text and bank bytes to their original hashes. The causal-history inputs cover every regional candidate. The service archive is unreadable in this session: histories therefore use available verified pre-cutoff catalogue exports, with explicitly incomplete historical depth. Earlier exports contribute orbital records only; no other scan's radio, calibration or location estimate is used. No following TLE enters the new inference.

Original graph partitions are radio-only; no points are withheld. The curved fits retain the original 12,724 curved observations. Linear methods may add nominated linear geometry but do not use linears to calibrate hardware. Candidate selection retains the existing broad 250 km visibility bank around 37.5°, −122.0° and a Starlink-name restriction. These are declared model/region assumptions, not a hand-picked satellite-ID list. The 25 km search box lies inside that broad bank region.

GLRT300 remeasurement applies to curved observations. Added linear fragments retain their original CFO and 150 Hz point-noise assumption.

Hyperparameters were developed on DSX01. Removing explicit GPS inputs does not turn this corpus into an independent new-location validation set. Published older GPS-conditioned/following-TLE diagnostics remain historical artifacts and are excluded from the new branch.

![Representative methods across five scans](overview.png)

## Position errors

Errors are km, **c0 / fitted c**. GPS evaluates already-saved fits only. No GPS winner is assembled into an algorithm. Frequency residual RMS and loss/gradient details are separate columns in [the CSV](position_and_gradient_summary.csv). No raw objective is ranked across different likelihood-power designs or different inference approximations.

{table(rows)}

The [fresh-versus-previous baseline comparison](fresh_vs_previous_baseline.json) records changed labels and position errors. Earlier experiments could inherit better hypotheses from earlier blind processing of the same scan. Their performance does not establish that a new zero-initialized run will rediscover those hypotheses. This is not evidence that those earlier fits used evaluation GPS; the finite discovery/search protocols differ. Earlier results are read only by this postfit reporter and never fed to the fresh fits.

## All figures and convergence details

"""
    text += "\n".join(
        f"- [{case} gallery]({case}/README.md)" for case in [f"DSX01-S0{k}" for k in range(1, 6)]
    )
    text += "\n\nEach two-panel figure shows c0/fitted c, downhill arrows, the regional fit endpoint, and three optimizer probes (regional center and the two lowest disk samples). Red trajectories are accepted optimizer iterates. The 10 km circle is the mapping boundary; optimization stays within the full square.\n"
    validation_path = OUTPUT / "validation.json"
    if validation_path.exists():
        validation = json.loads(validation_path.read_text())
        pixel_stops = sum(w.get("pixels", 0) for w in validation["warnings"])
        text += (
            "\n## Numerical checks and input evidence\n\n"
            f"The audit reports {len(validation['completed'])} completed scan/configuration maps, "
            f"{len(validation['incomplete'])} pending, and {pixel_stops} legacy pixels that reached "
            "the nuisance-refit iteration limit across both c arms. Those pixels are finite-budget "
            "approximations; do not interpret the legacy maps as certified global profile surfaces. "
            "Exact per-pixel stop reasons remain in each result JSON.\n\n"
            "[Input audit](INPUT_AUDIT.md), [validation](validation.json), "
            "[GPS perturbation check](gps_invariance.json), [objective replay](endpoint_replay.json), "
            "[input hashes](input_bindings.json), [map hashes](map_bindings.json), "
            "[completed checks and limitations](VALIDATION.md), "
            "[matched tighter precision check](precision_cap_check.json).\n"
        )
    (OUTPUT / "README.md").write_text(text)
    print(len(paths), expected_count, len(rows), flush=True)


if __name__ == "__main__":
    run()
