"""Postfit-only GPS evaluation of common receiver drift and height controls."""

import csv
import hashlib
import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from localize_merged_track_catalogue import distance_km
from prototype_dsx01_receiver_geometry import OUTPUT, geometry_problem
from report_dsx01_model_iterations import REFERENCE, nominated_metrics

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def scales(variant):
    _, mean, _, height = variant.split("_")
    return float(mean), float(height)


def evaluate():
    summary, comparisons, bindings = [], [], {}
    for case_dir in sorted(OUTPUT.glob("DSX01-S0*")):
        scan = None
        for method_dir in sorted(case_dir.iterdir()):
            source = method_dir / "endpoints.json"
            if not source.exists():
                continue
            bindings[str(source.relative_to(ROOT))] = hashlib.sha256(
                source.read_bytes()
            ).hexdigest()
            fits = json.loads(source.read_text())
            cache_path = method_dir / "frequency_cache.json"
            cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
            for key, fit in fits.items():
                variant, arm = key.split("/")
                mean, height = scales(variant)
                item = dict(
                    experiment="receiver_geometry",
                    variant=variant,
                    arm=arm,
                    method=method_dir.name,
                    fit=fit,
                )
                digest = hashlib.sha256(json.dumps(fit, sort_keys=True).encode()).hexdigest()
                if key not in cache or cache[key]["fit_sha256"] != digest:
                    scan = Scan(case_dir.name) if scan is None else scan

                    def factory(*args, ms=mean, hs=height):
                        return geometry_problem(*args, mean_sigma=ms, height_sigma=hs)

                    cache[key] = dict(
                        fit_sha256=digest,
                        **nominated_metrics(scan, item, problem_factory=factory),
                    )
                metrics = cache[key]
                drifts = np.array(fit["state"]["beta"])[4:8] / 150
                row = dict(
                    case=case_dir.name,
                    method=method_dir.name,
                    variant=variant,
                    arm=arm,
                    mean_prior_sigma_hz_s=mean,
                    height_prior_sigma_m=height,
                    height_m=fit["state"].get("altitude_m", 0.0),
                    latitude_deg=fit["latitude_deg"],
                    longitude_deg=fit["longitude_deg"],
                    position_error_km=distance_km(
                        (fit["latitude_deg"], fit["longitude_deg"]), REFERENCE
                    ),
                    total_score=fit["score"],
                    frequency_prior_score=fit["frequency_prior_score"],
                    complexity_penalty=fit["complexity_penalty"],
                    **{f"band_drift_{k}_hz_s": v for k, v in enumerate(drifts)},
                    **{k: v for k, v in metrics.items() if k not in ("tracks", "fit_sha256")},
                )
                summary.append(row)
            for key, fit in fits.items():
                if not key.endswith("/c0"):
                    continue
                variant = key.removesuffix("/c0")
                other = f"{variant}/fitted_c"
                if other not in fits:
                    continue
                matched = []
                for arm in ("c0", "fitted_c"):
                    matched.append(
                        {
                            r["component"]: r
                            for r in cache[f"{variant}/{arm}"]["tracks"]
                            if r["compatible"]
                        }
                    )
                common = matched[0].keys() & matched[1].keys()
                n = sum(matched[0][k]["points"] for k in common)
                record = dict(
                    case=case_dir.name,
                    method=method_dir.name,
                    variant=variant,
                    common_curved_points=n,
                    same_label_points=sum(
                        matched[0][k]["points"]
                        for k in common
                        if matched[0][k]["norad"] == matched[1][k]["norad"]
                    ),
                    matching_nominations=fit["rows"] == fits[other]["rows"],
                    matching_aliases=fit["aliases"] == fits[other]["aliases"],
                    matching_geographic_starts=fit["starts"] == fits[other]["starts"],
                )
                for arm, rows in zip(("c0", "fitted_c"), matched, strict=True):
                    record[f"native_rms_{arm}_hz"] = float(
                        np.sqrt(sum(rows[k]["native_square_hz2"] for k in common) / max(1, n))
                    )
                    record[f"innovation_rms_{arm}_hz"] = float(
                        np.sqrt(sum(rows[k]["innovation_square_hz2"] for k in common) / max(1, n))
                    )
                comparisons.append(record)
            write(cache_path, cache)
        print(case_dir.name, sum(r["case"] == case_dir.name for r in summary), flush=True)
    for name, rows in (("evaluation_summary", summary), ("c_ablation", comparisons)):
        write(OUTPUT / f"{name}.json", rows)
        if rows:
            with (OUTPUT / f"{name}.csv").open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
    write(
        OUTPUT / "evaluation_binding.json",
        dict(
            inputs_sha256=bindings,
            reference_GPS_only_used_after_fit=True,
            reference=REFERENCE,
            counts_are_nominated_curved_points_not_all_GLRT=True,
        ),
    )
    return summary, comparisons


def plot(summary):
    cases = [f"DSX01-S0{k}" for k in range(1, 6)]
    fig, axes = plt.subplots(2, 2, figsize=(17, 10), constrained_layout=True)
    for i, arm in enumerate(("c0", "fitted_c")):
        for j, mean in enumerate((5.0, 10.0)):
            values = np.full((5, 6), np.nan)
            for r in summary:
                if r["arm"] == arm and r["variant"] == f"mean_{mean:g}_height_0":
                    values[cases.index(r["case"]), METHODS.index(r["method"])] = r[
                        "position_error_km"
                    ]
            ax = axes[i, j]
            im = ax.imshow(values, vmin=0, vmax=6, cmap="RdYlGn_r", aspect="auto")
            ax.set(
                title=f"RX mean sigma {mean:g} Hz/s / {arm}",
                xticks=range(6),
                xticklabels=METHODS,
                yticks=range(5),
                yticklabels=cases,
            )
            ax.tick_params(axis="x", rotation=35, labelsize=9)
            for a, b in np.ndindex(values.shape):
                if np.isfinite(values[a, b]):
                    ax.text(b, a, f"{values[a, b]:.2f}", ha="center", va="center")
    fig.colorbar(im, ax=axes, label="Independent position error (km)", shrink=0.65)
    fig.suptitle("Common RX drift, small band contrast; fixed zero height")
    fig.savefig(OUTPUT / "all_scan_drift_accuracy.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(17, 5), constrained_layout=True)
    for method in METHODS:
        for arm, style in (("c0", "-o"), ("fitted_c", "--x")):
            rows = [
                r
                for r in summary
                if r["case"] == "DSX01-S01"
                and r["method"] == method
                and r["arm"] == arm
                and r["mean_prior_sigma_hz_s"] == 10
            ]
            rows.sort(key=lambda r: r["height_prior_sigma_m"])
            for ax, metric in zip(
                axes,
                ("position_error_km", "height_m", "accepted_nominated_curved_points"),
                strict=True,
            ):
                ax.plot(
                    [r["height_prior_sigma_m"] for r in rows],
                    [r[metric] for r in rows],
                    style,
                    label=f"{method}/{arm}",
                )
    for ax, label in zip(
        axes, ("Position error (km)", "Fitted height (m)", "Accepted curved GLRT"), strict=True
    ):
        ax.set(xlabel="Height prior sigma (m); 0 = fixed zero height", ylabel=label)
        ax.grid(alpha=0.2)
    axes[0].axhline(1, color="black", linestyle=":")
    axes[2].legend(fontsize=7)
    fig.savefig(OUTPUT / "s01_height_sensitivity.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    rows, _ = evaluate()
    plot(rows)
