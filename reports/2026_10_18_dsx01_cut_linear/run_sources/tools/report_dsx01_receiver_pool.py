"""Evaluate saved joint-site fits; GPS remains isolated to reporting."""

import csv
import hashlib
import json
from collections import defaultdict

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, Scan
from localize_merged_track_catalogue import distance_km
from prototype_dsx01_continuous_position import CENTER, GRID
from prototype_dsx01_receiver_geometry import OUTPUT, SOURCE, geometry_problem
from report_dsx01_model_iterations import REFERENCE, nominated_metrics

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def tables(name, rows):
    write(OUTPUT / f"{name}.json", rows)
    if rows:
        with (OUTPUT / f"{name}.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)


def run():
    fits = {}
    bindings = {}
    for p in sorted((OUTPUT / "pooled").glob("*/mean_*_endpoints.json")):
        mean = float(p.name.removeprefix("mean_").removesuffix("_endpoints.json"))
        fits[mean, p.parent.name] = json.loads(p.read_text())
        bindings[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    frequency, metrics = {}, []
    for number in range(1, 6):
        case = f"DSX01-S0{number}"
        cache_path = OUTPUT / "pooled" / f"{case}_frequency_cache.json"
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
        scan = None
        for (mean, method), arms in fits.items():
            seed_path = SOURCE / case / f"{method}_center.json"
            seed = json.loads(seed_path.read_text())
            for arm, fit in arms.items():
                key = f"{mean:g}/{method}/{arm}"
                digest = hashlib.sha256(json.dumps(fit, sort_keys=True).encode()).hexdigest()
                if key not in cache or cache[key]["fit_sha256"] != digest:
                    scan = Scan(case) if scan is None else scan
                    initial = geometry_problem(
                        scan,
                        seed,
                        method,
                        arm == "fitted_c",
                        (0, 0),
                        mean_sigma=mean,
                        height_sigma=0,
                    )
                    local = dict(
                        rows=seed["rows"],
                        state=fit["states"][case],
                        aliases=initial.alias,
                        east_north_km=fit["east_north_km"],
                        fits=[dict(parameters=fit["local_parameters"][case], score=fit["score"])],
                    )
                    item = dict(fit=local, method=method, arm=arm, experiment="receiver_geometry")

                    def factory(*args, ms=mean):
                        return geometry_problem(*args, mean_sigma=ms, height_sigma=0)

                    cache[key] = dict(
                        fit_sha256=digest, **nominated_metrics(scan, item, problem_factory=factory)
                    )
                frequency[case, mean, method, arm] = cache[key]
                metrics.append(
                    dict(
                        case=case,
                        mean_sigma=mean,
                        method=method,
                        arm=arm,
                        **{
                            k: v for k, v in cache[key].items() if k not in ("tracks", "fit_sha256")
                        },
                    )
                )
        write(cache_path, cache)
        print(case, len(cache), flush=True)
    comparisons = []
    for (mean, method), _arms in fits.items():
        native = {a: 0.0 for a in ("c0", "fitted_c")}
        innovation = {a: 0.0 for a in native}
        common_points = 0
        for number in range(1, 6):
            case = f"DSX01-S0{number}"
            accepted = [
                {
                    r["component"]: r
                    for r in frequency[case, mean, method, a]["tracks"]
                    if r["compatible"]
                }
                for a in ("c0", "fitted_c")
            ]
            common = accepted[0].keys() & accepted[1].keys()
            common_points += sum(accepted[0][k]["points"] for k in common)
            for a, rr in zip(native, accepted, strict=True):
                native[a] += sum(rr[k]["native_square_hz2"] for k in common)
                innovation[a] += sum(rr[k]["innovation_square_hz2"] for k in common)
        comparisons.append(
            dict(
                mean_sigma=mean,
                method=method,
                common_accepted_curved_points=common_points,
                **{
                    f"native_rms_{a}_hz": float(np.sqrt(v / max(1, common_points)))
                    for a, v in native.items()
                },
                **{
                    f"innovation_rms_{a}_hz": float(np.sqrt(v / max(1, common_points)))
                    for a, v in innovation.items()
                },
            )
        )
    summary = []
    for (mean, method), arms in fits.items():
        for arm, fit in arms.items():
            rr = [frequency[f"DSX01-S0{k}", mean, method, arm] for k in range(1, 6)]
            n = sum(r["curved_points"] for r in rr)
            na = sum(r["accepted_nominated_curved_points"] for r in rr)
            summary.append(
                dict(
                    mean_sigma=mean,
                    method=method,
                    arm=arm,
                    latitude_deg=fit["latitude_deg"],
                    longitude_deg=fit["longitude_deg"],
                    position_error_km=distance_km(
                        (fit["latitude_deg"], fit["longitude_deg"]), REFERENCE
                    ),
                    frequency_prior_score=fit["score"],
                    curved_points=n,
                    accepted_nominated_curved_points=na,
                    all_curved_native_rms_hz=float(
                        np.sqrt(
                            sum(r["all_curved_native_rms_hz"] ** 2 * r["curved_points"] for r in rr)
                            / n
                        )
                    ),
                    accepted_native_rms_hz=float(
                        np.sqrt(
                            sum(
                                r["accepted_native_rms_hz"] ** 2
                                * r["accepted_nominated_curved_points"]
                                for r in rr
                            )
                            / max(1, na)
                        )
                    ),
                )
            )
    transfer = []
    by_method = defaultdict(list)
    for p in sorted((OUTPUT / "pooled_transfer").glob("DSX01-S0*/*.json")):
        bindings[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
        for arm, record in json.loads(p.read_text()).items():
            row = {k: v for k, v in record.items() if k not in ("rows",)}
            transfer.append(row)
            by_method[record["method"], arm].append(record)
    totals = []
    for (method, arm), records in sorted(by_method.items()):
        n = sum(r["associated_points"] for r in records)
        raw = sum(r["raw_points"] for r in records)
        segments = sum(r["association_segments"] for r in records)
        totals.append(
            dict(
                method=method,
                arm=arm,
                scans=len(records),
                associated_points=n,
                raw_points=raw,
                percent_associated=100 * n / raw,
                association_segments=segments,
                points_per_segment=n / max(1, segments),
            )
        )
    for name, rows in [
        ("pooled_summary", summary),
        ("pooled_c_ablation", comparisons),
        ("pooled_frequency_per_scan", metrics),
        ("pooled_transfer_summary", transfer),
        ("pooled_transfer_totals", totals),
    ]:
        tables(name, rows)
    exact_rows = []
    exact_by_case = {}
    exact_fit_path = OUTPUT / "pooled_exact_refinement/endpoints.json"
    if exact_fit_path.exists():
        exact_fits = json.loads(exact_fit_path.read_text())
        for path in sorted((OUTPUT / "pooled_exact_transfer").glob("DSX01-S0*/orbit_em.json")):
            records = json.loads(path.read_text())
            exact_by_case[path.parent.name] = records
            exact_rows.extend({k: v for k, v in r.items() if k != "rows"} for r in records.values())
        exact_totals = []
        for arm, fit in exact_fits.items():
            rr = [r for r in exact_rows if r["arm"] == arm]
            n = sum(r["associated_points"] for r in rr)
            raw = sum(r["raw_points"] for r in rr)
            segments = sum(r["association_segments"] for r in rr)
            exact_totals.append(
                dict(
                    arm=arm,
                    position_error_km=distance_km(
                        (fit["latitude_deg"], fit["longitude_deg"]), REFERENCE
                    ),
                    frequency_prior_score=fit["score"],
                    associated_points=n,
                    raw_points=raw,
                    percent_associated=100 * n / max(1, raw),
                    association_segments=segments,
                    points_per_segment=n / max(1, segments),
                )
            )
        common_count = same_label = 0
        squares = dict(c0=0.0, fitted_c=0.0)
        for records in exact_by_case.values():
            rr = [
                {r["component"]: r for r in records[a]["rows"] if r["compatible"]} for a in squares
            ]
            common = rr[0].keys() & rr[1].keys()
            common_count += sum(rr[0][k]["points"] for k in common)
            same_label += sum(
                rr[0][k]["points"]
                for k in common
                if rr[0][k]["candidate_norad"] == rr[1][k]["candidate_norad"]
            )
            for a, r in zip(squares, rr, strict=True):
                squares[a] += sum(
                    float(np.sum(np.asarray(r[k]["residual_hz"]) ** 2)) for k in common
                )
        exact_ablation = [
            dict(
                common_points=common_count,
                same_label_points=same_label,
                **{
                    f"native_rms_{a}_hz": float(np.sqrt(v / max(1, common_count)))
                    for a, v in squares.items()
                },
            )
        ]
        tables("exact_transfer_per_scan", exact_rows)
        tables("exact_joint_summary", exact_totals)
        tables("exact_joint_c_ablation", exact_ablation)
    write(
        OUTPUT / "pooled_evaluation_binding.json",
        dict(
            inputs_sha256=bindings,
            evaluation_reference_only_in_reporter=True,
            site_assumed_stationary=True,
            c_comparison_frequency_and_position_reported_separately=True,
        ),
    )
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), constrained_layout=True)
    x = np.arange(len(METHODS))
    for mean, color in [(0, "tab:gray"), (10, "tab:blue")]:
        for arm, offset, alpha in [("c0", -0.11, 1), ("fitted_c", 0.11, 0.55)]:
            y = [
                next(
                    (
                        r["position_error_km"]
                        for r in summary
                        if r["method"] == m and r["arm"] == arm and r["mean_sigma"] == mean
                    ),
                    np.nan,
                )
                for m in METHODS
            ]
            axes[0].plot(
                x + offset,
                y,
                "o" if mean else "s",
                color=color,
                alpha=alpha,
                label=f"{'original band priors' if mean == 0 else 'RX mean sigma 10'} / {arm}",
            )
    axes[0].axhline(1, color="black", linestyle=":")
    axes[0].set(ylabel="Joint static-site error (km)", title="Matched tight versus shared RX drift")
    for arm, offset in [("c0", -0.16), ("fitted_c", 0.16)]:
        y = [
            next(
                (r["percent_associated"] for r in totals if r["method"] == m and r["arm"] == arm),
                np.nan,
            )
            for m in METHODS
        ]
        axes[1].bar(x + offset, y, width=0.3, label=arm)
    axes[1].set(
        ylabel="% of all original GLRT associated",
        title="Frozen joint-site transfer, common RX drift",
    )
    for ax in axes:
        ax.set(xticks=x, xticklabels=METHODS)
        ax.tick_params(axis="x", rotation=35)
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.2)
    fig.savefig(OUTPUT / "pooled_accuracy_and_coverage.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(11, 10), constrained_layout=True)
    reference = [
        (REFERENCE[1] - CENTER[1]) * 111.32 * np.cos(np.deg2rad(CENTER[0])),
        (REFERENCE[0] - CENTER[0]) * 111,
    ]
    for row, mean in enumerate((0.0, 10.0)):
        for col, arm in enumerate(("c0", "fitted_c")):
            ax = axes[row, col]
            fit = fits[mean, "orbit_em"][arm]
            grid = np.array(GRID)
            ax.scatter(
                grid[:, 0], grid[:, 1], s=10, c="gray", alpha=0.45, label="25 grid evaluations"
            )
            for k, trial in enumerate(fit["fits"]):
                points = np.array([r["parameters"][:2] for r in trial["history"]])
                ax.plot(points[:, 0], points[:, 1], "-o", markersize=2, label=f"start {k + 1}")
            ax.scatter(*reference, marker="*", s=140, c="black", label="evaluation GPS")
            ax.scatter(*fit["east_north_km"], marker="x", s=80, c="red", label="saved endpoint")
            error = distance_km((fit["latitude_deg"], fit["longitude_deg"]), REFERENCE)
            label = "original band priors" if not mean else "shared RX drift"
            ax.set(
                title=f"{label} / {arm}: {error:.3f} km",
                xlim=(-13, 13),
                ylim=(-13, 13),
                xlabel="East of Mill Valley centre (km)",
                ylabel="North of Mill Valley centre (km)",
            )
            ax.set_aspect("equal")
            ax.grid(alpha=0.15)
    axes[0, 0].legend(fontsize=7, loc="upper left")
    fig.suptitle("Blind joint orbital fits: geographic paths; no GPS term in optimization")
    fig.savefig(OUTPUT / "pooled_orbital_paths.png", dpi=160)
    plt.close(fig)
    return summary, comparisons, totals


if __name__ == "__main__":
    run()
