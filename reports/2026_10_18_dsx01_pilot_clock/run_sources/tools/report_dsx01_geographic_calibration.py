"""Report all S05 discovery, initialization and transmitter-clock controls."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from localize_merged_track_catalogue import distance_km
from profile_dsx01_geographic_calibration import OUTPUT, geometry_problem, incumbents
from prototype_dsx01_calibration_modes import OUTPUT as CENTER_MODES
from prototype_dsx01_calibration_modes import choose_pair
from prototype_dsx01_causal_clock import clock_problem, lock_aliases
from prototype_dsx01_channel_clock import channel_problem
from prototype_dsx01_continuous_position import CENTER
from prototype_dsx01_frame_bias import frame_problem
from prototype_dsx01_phase_forecast import forecast_problem, phase_prior
from prototype_dsx01_separate_rf_calibration import rf_problem
from prototype_dsx01_wide_causal_phase import causal_problem
from report_dsx01_model_iterations import REFERENCE, nominated_metrics

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def records(case):
    for method in METHODS:
        name, pair = choose_pair(incumbents(case, method))
        for arm, fit in pair.items():
            yield dict(experiment="incumbent", variant=name, method=method, arm=arm, fit=fit)
        path = CENTER_MODES / case / method / "endpoints_by_mode.json"
        for variant, pair in json.loads(path.read_text()).items():
            for arm, fit in pair.items():
                yield dict(
                    experiment="center",
                    variant=variant,
                    method=method,
                    arm=arm,
                    fit=fit,
                    source=str(path),
                )
        path = OUTPUT / case / method / "fine_fits.json"
        for variant, pair in json.loads(path.read_text()).items():
            for arm, fit in pair.items():
                yield dict(
                    experiment="geographic",
                    variant=variant,
                    method=method,
                    arm=arm,
                    fit=fit,
                    source=str(path),
                )
        for experiment in (
            "warm_start_ablation",
            "separate_rf",
            "causal_phase",
            "satellite_clock",
            "channel_clock",
            "frame_bias",
            "phase_forecast",
        ):
            path = OUTPUT / experiment / case / method / "endpoints.json"
            if not path.exists():
                continue
            for key, fit in json.loads(path.read_text()).items():
                variant, arm = key.rsplit("/", 1) if "/" in key else ("phase_forecast", key)
                yield dict(
                    experiment=experiment,
                    variant=variant,
                    method=method,
                    arm=arm,
                    fit=fit,
                    source=str(path),
                )


def factory(item, scan):
    experiment, variant = item["experiment"], item["variant"]
    if experiment == "separate_rf":
        return lambda *args: rf_problem(*args, mode=variant)
    if experiment == "causal_phase":
        return lambda *args: causal_problem(*args, mode=variant)
    if experiment == "satellite_clock":
        phase, sigma = variant.split("_clock")
        return lambda *args: clock_problem(*args, phase_mode=phase, clock_sigma=float(sigma))
    if experiment == "channel_clock":
        grouping, rate = variant.split("_rate")
        return lambda *args: channel_problem(*args, grouping=grouping, rate_sigma=float(rate))
    if experiment == "frame_bias":
        sigma = float(variant.removeprefix("independent_sigma_"))
        return lambda *args: frame_problem(*args, independent_sigma=sigma)
    if experiment == "phase_forecast":
        means = phase_prior(scan.case)["phase_mean_s"]
        return lambda *args: forecast_problem(*args, means=means)
    return lambda *args: geometry_problem(*args, mean_sigma=10, height_sigma=0)


def table(name, rows):
    write(OUTPUT / f"{name}.json", rows)
    if not rows:
        return
    with (OUTPUT / f"{name}.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(case="DSX01-S05"):
    scan = Scan(case)
    summary = []
    metrics = {}
    bindings = {}
    source_names = [
        "profile_dsx01_geographic_calibration.py",
        "dsx01_warm_initialization.py",
        "prototype_dsx01_orbit_marginal.py",
        "prototype_dsx01_channel_clock.py",
        "prototype_dsx01_frame_bias.py",
        "prototype_dsx01_phase_forecast.py",
        "report_dsx01_model_iterations.py",
    ]
    source_hash = hashlib.sha256(
        b"".join((ROOT / "tools" / n).read_bytes() for n in source_names)
    ).hexdigest()
    cache_path = OUTPUT / f"{case}_frequency_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    all_records = list(records(case))
    for item in all_records:
        fit = item["fit"]
        key = "/".join(item[k] for k in ("experiment", "variant", "method", "arm"))
        digest = hashlib.sha256(
            (json.dumps(fit, sort_keys=True) + source_hash).encode()
        ).hexdigest()
        if "source" in item:
            bindings[item["source"]] = hashlib.sha256(Path(item["source"]).read_bytes()).hexdigest()
        if key not in cache or cache[key]["fit_sha256"] != digest:
            model = factory(item, scan)

            def locked(*args, constructor=model, aliases=fit["aliases"]):
                p = constructor(*args)
                lock_aliases(p, aliases)
                return p

            cache[key] = dict(
                fit_sha256=digest, **nominated_metrics(scan, item, problem_factory=locked)
            )
            write(cache_path, cache)
        metric = cache[key]
        metrics[key] = metric
        accepted = [r for r in metric["tracks"] if r["compatible"]]
        best = min(fit["fits"], key=lambda r: r["score"])
        summary.append(
            dict(
                case=case,
                **{k: item[k] for k in ("experiment", "variant", "method", "arm")},
                position_error_km=distance_km(
                    (fit["latitude_deg"], fit["longitude_deg"]), REFERENCE
                ),
                frequency_prior_score=fit["frequency_prior_score"],
                complexity_penalty=fit["complexity_penalty"],
                total_score=fit["score"],
                accepted_fragments=len(accepted),
                points_per_accepted_fragment=metric["accepted_nominated_curved_points"]
                / max(1, len(accepted)),
                evaluations=sum(f["evaluations"] for f in fit["fits"]),
                best_evaluations=best["evaluations"],
                seconds=fit.get("seconds", 0),
                **{k: v for k, v in metric.items() if k not in ("tracks", "fit_sha256")},
            )
        )
    pairs = []
    for item in all_records:
        if item["arm"] != "c0":
            continue
        other = next(
            r
            for r in all_records
            if r["arm"] == "fitted_c"
            and all(item[k] == r[k] for k in ["experiment", "variant", "method"])
        )
        for field in ["rows", "aliases", "starts"]:
            assert item["fit"][field] == other["fit"][field], (
                item["experiment"],
                item["variant"],
                field,
            )
        prefix = "/".join(item[k] for k in ("experiment", "variant", "method"))
        rr = [
            {r["component"]: r for r in metrics[prefix + "/" + arm]["tracks"] if r["compatible"]}
            for arm in ("c0", "fitted_c")
        ]
        common = rr[0].keys() & rr[1].keys()
        n = sum(rr[0][k]["points"] for k in common)
        row = {k: item[k] for k in ["experiment", "variant", "method"]}
        row.update(
            common_points=n,
            same_label_points=sum(
                rr[0][k]["points"] for k in common if rr[0][k]["norad"] == rr[1][k]["norad"]
            ),
        )
        for arm, rrr in zip(("c0", "fitted_c"), rr, strict=True):
            row[f"native_rms_{arm}_hz"] = float(
                np.sqrt(sum(rrr[k]["native_square_hz2"] for k in common) / max(1, n))
            )
        pairs.append(row)
    table("evaluation_summary", summary)
    table("c_ablation", pairs)
    write(
        OUTPUT / "evaluation_binding.json",
        dict(
            inputs_sha256=bindings,
            evaluation_GPS_report_only=True,
            nominated_curved_points_only=True,
            matched_c_pairs=len(pairs),
        ),
    )
    plot(summary, case)
    print("evaluated", len(summary), "matched c pairs", len(pairs), flush=True)
    return summary


def plot(summary, case):
    fig, axes = plt.subplots(2, 3, figsize=(17, 10), constrained_layout=True)
    truth = np.array(
        [
            (REFERENCE[1] - CENTER[1]) * 111.32 * np.cos(np.deg2rad(CENTER[0])),
            (REFERENCE[0] - CENTER[0]) * 111,
        ]
    )
    for ax, method in zip(axes.flat, METHODS, strict=True):
        nodes = json.loads((OUTPUT / case / method / "grid_nodes.json").read_text())
        grid = np.full((5, 5), np.nan)
        for node in nodes:
            e, n = node["east_north_km"]
            grid[int(round((n + 12.5) / 6.25)), int(round((e + 12.5) / 6.25))] = node["score"]
        im = ax.imshow(
            grid - grid.min(),
            origin="lower",
            extent=(-15.625, 15.625, -15.625, 15.625),
            cmap="viridis",
            aspect="equal",
        )
        ax.plot(*truth, "w*", markersize=11, label="GPS (evaluation only)")
        fine = json.loads((OUTPUT / case / method / "fine_fits.json").read_text())
        for pair in fine.values():
            history = np.array([r["parameters"][:2] for r in pair["c0"]["fits"][0]["history"]])
            ax.plot(
                history[:, 0], history[:, 1], "-o", markersize=2, linewidth=0.8, color="tab:orange"
            )
        ax.set(
            title=method,
            xlabel="East of Mill Valley centre (km)",
            ylabel="North (km)",
            xlim=(-13, 13),
            ylim=(-13, 13),
        )
        fig.colorbar(im, ax=ax, label="Δ coarse c0 objective (6-step nuisance profiles)")
    fig.savefig(OUTPUT / "s05_geographic_calibration_surfaces.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), constrained_layout=True)
    for ax, arm in zip(axes, ("c0", "fitted_c"), strict=True):
        for variant, shift in [("legacy_clipped", -0.18), ("restored", 0.18)]:
            rr = {
                r["method"]: r
                for r in summary
                if r["experiment"] == "warm_start_ablation"
                and r["variant"] == variant
                and r["arm"] == arm
            }
            ax.bar(
                np.arange(len(METHODS)) + shift,
                [rr[m]["best_evaluations"] for m in METHODS],
                width=0.32,
                label=variant,
            )
        ax.set(
            title=arm,
            ylabel="Residual evaluations",
            xticks=range(len(METHODS)),
            xticklabels=METHODS,
        )
        ax.tick_params(axis="x", rotation=45, labelsize=8)
        ax.legend()
    fig.savefig(OUTPUT / "warm_start_evaluation_ablation.png", dpi=160)
    plt.close(fig)
    rows = [
        r
        for r in summary
        if r["method"] == "receiver_smooth"
        and r["experiment"] in ["satellite_clock", "channel_clock", "frame_bias", "phase_forecast"]
    ]
    names = sorted({r["experiment"] + "/" + r["variant"] for r in rows})
    fig, ax = plt.subplots(figsize=(18, 6), constrained_layout=True)
    for arm, shift in [("c0", -0.18), ("fitted_c", 0.18)]:
        rr = {r["experiment"] + "/" + r["variant"]: r for r in rows if r["arm"] == arm}
        ax.bar(
            np.arange(len(names)) + shift,
            [rr[n]["position_error_km"] for n in names],
            width=0.32,
            label=arm,
        )
    ax.set(
        ylabel="Independent S05 position error (km)", xticks=range(len(names)), xticklabels=names
    )
    ax.tick_params(axis="x", rotation=65, labelsize=8)
    ax.axhline(1, color="black", linestyle=":")
    ax.legend()
    fig.savefig(OUTPUT / "s05_transmitter_clock_controls.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    run()
