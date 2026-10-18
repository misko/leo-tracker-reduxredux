"""Postfit GPS/frequency evaluation; future-TLE diagnostics stay separate."""

import csv
import hashlib
import json

import matplotlib
import numpy as np
from analyze_dsx01_fixed_site import ecef_states
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from localize_merged_track_catalogue import distance_km
from probe_dsx01_scan_influence import OUTPUT
from prototype_dsx01_orbit_marginal import marginal_problem, variant_options
from prototype_dsx01_receiver_geometry import geometry_problem
from prototype_dsx01_receiver_timing import timing_problem
from report_dsx01_model_iterations import REFERENCE, nominated_metrics
from sgp4.api import Satrec

from leo.sky.propagation import ElementSetCatalogue

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def write_table(name, rows):
    write(OUTPUT / f"{name}.json", rows)
    if rows:
        with (OUTPUT / f"{name}.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


def following_scan(case):
    scan = Scan(case)
    rows = json.loads((OUTPUT / "orbit_history_and_following_diagnostic.json").read_text())[case][
        "candidates"
    ]
    available = {
        int(n): r["first_following_newer_version"]
        for n, r in rows.items()
        if r["first_following_newer_version"] is not None
    }
    nums = tuple(available)
    cat = ElementSetCatalogue(
        tuple(map(str, nums)), nums, tuple(Satrec.twoline2rv(*available[n]["lines"]) for n in nums)
    )
    p, v, good = ecef_states(cat, scan.receipt["origin_utc_ns"], scan.sky["time_s"])
    assert good.all()
    indexes = [int(np.flatnonzero(scan.norads == n)[0]) for n in nums]
    scan.sky["position_km"][indexes] = p
    scan.sky["velocity_km_s"][indexes] = v
    return scan


def run():
    summary, comparisons = [], []
    bindings = {}
    model_hash = hashlib.sha256(
        b"".join(
            (ROOT / p).read_bytes()
            for p in [
                "tools/prototype_dsx01_orbit_marginal.py",
                "tools/report_dsx01_model_iterations.py",
                "src/leo/analysis/research/orbit_uncertainty.py",
                "src/leo/analysis/research/retained_track_likelihood.py",
            ]
        )
    ).hexdigest()
    cases = [f"DSX01-S0{k}" for k in range(1, 6)]
    for case in cases:
        scan = Scan(case)
        cache_path = OUTPUT / f"{case}_frequency_cache.json"
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
        records = []
        for p in sorted((OUTPUT / "marginal" / case).glob("*/endpoints.json")):
            bindings[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
            for key, fit in json.loads(p.read_text()).items():
                variant, arm = key.split("/")
                records.append(
                    dict(
                        experiment="marginal",
                        variant=variant,
                        method=p.parent.name,
                        arm=arm,
                        fit=fit,
                    )
                )
        for p in sorted((OUTPUT / "timing" / case).glob("*/endpoints.json")):
            bindings[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
            for key, fit in json.loads(p.read_text()).items():
                variant, arm = key.split("/")
                records.append(
                    dict(
                        experiment="timing", variant=variant, method=p.parent.name, arm=arm, fit=fit
                    )
                )
        metrics = {}
        for item in records:
            fit, variant = item["fit"], item["variant"]
            key = "/".join(item[k] for k in ("experiment", "variant", "method", "arm"))
            digest = hashlib.sha256(
                (json.dumps(fit, sort_keys=True) + model_hash).encode()
            ).hexdigest()
            if item["experiment"] == "marginal":
                options = variant_options(variant)

                def factory(*args, config=options):
                    return marginal_problem(*args, **config)
            else:
                sigma = float(variant.removeprefix("time_sigma_"))

                def factory(*args, s=sigma):
                    return timing_problem(*args, sigma=s)

            if key not in cache or cache[key]["fit_sha256"] != digest:
                metric = nominated_metrics(scan, item, problem_factory=factory)
                details = {}
                if item["experiment"] == "marginal":
                    p = factory(
                        scan,
                        dict(rows=fit["rows"], state=fit["state"]),
                        item["method"],
                        item["arm"] == "fitted_c",
                        fit["east_north_km"],
                    )
                    p.problem.alias = fit["aliases"]
                    x = np.array(min(fit["fits"], key=lambda r: r["score"])["parameters"])
                    _, stats, coeff, _, nom, _, modes = p.problem.calculate(p.native_parameters(x))
                    linear = nom.copy()
                    for j, a in coeff.items():
                        use = p.flat_labels == p.local_j[j]
                        linear[use] += modes[use] @ a
                    exact, _ = p.predicted(x)
                    q = np.concatenate(
                        [
                            np.full(len(scan.tracks[i]["times"]), scan.tracks[i]["rf_hz"] / 11.5e9)
                            for i in p.members
                        ]
                    )
                    differences = q * (exact - linear)
                    details = dict(
                        conditional_geometry_linearization_rms_hz=float(
                            np.sqrt(np.mean(differences**2))
                        ),
                        conditional_geometry_linearization_max_hz=float(abs(differences).max()),
                        clutter_families=sum(v["signal_probability"] < 0.5 for v in stats.values()),
                    )
                else:
                    details = dict(
                        conditional_geometry_linearization_rms_hz=0.0,
                        conditional_geometry_linearization_max_hz=0.0,
                        clutter_families=0,
                    )
                cache[key] = dict(fit_sha256=digest, **metric, **details)
            metric = cache[key]
            metrics[key] = metric
            accepted = [r for r in metric["tracks"] if r["compatible"]]
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
                    **{k: v for k, v in metric.items() if k not in ("fit_sha256", "tracks")},
                    accepted_fragments=len(accepted),
                    points_per_accepted_fragment=metric["accepted_nominated_curved_points"]
                    / max(1, len(accepted)),
                )
            )
        for item in records:
            if item["arm"] != "c0":
                continue
            keys = [
                "/".join([item["experiment"], item["variant"], item["method"], a])
                for a in ("c0", "fitted_c")
            ]
            if keys[1] not in metrics:
                continue
            rr = [
                {r["component"]: r for r in metrics[k]["tracks"] if r["compatible"]} for k in keys
            ]
            common = rr[0].keys() & rr[1].keys()
            n = sum(rr[0][k]["points"] for k in common)
            record = dict(
                case=case,
                **{k: item[k] for k in ("experiment", "variant", "method")},
                common_curved_points=n,
                same_label_points=sum(
                    rr[0][k]["points"] for k in common if rr[0][k]["norad"] == rr[1][k]["norad"]
                ),
            )
            for arm, r in zip(("c0", "fitted_c"), rr, strict=True):
                record[f"native_rms_{arm}_hz"] = float(
                    np.sqrt(sum(r[k]["native_square_hz2"] for k in common) / max(1, n))
                )
                record[f"innovation_rms_{arm}_hz"] = float(
                    np.sqrt(sum(r[k]["innovation_square_hz2"] for k in common) / max(1, n))
                )
            comparisons.append(record)
        write(cache_path, cache)
        print(case, len(records), flush=True)
    write_table("evaluation_summary", summary)
    write_table("c_ablation", comparisons)
    future = []
    future_comparisons = []
    for p in sorted((OUTPUT / "following_diagnostic").glob("DSX01-S0*/endpoints.json")):
        bindings[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
        case = p.parent.name
        scans = dict(causal=Scan(case), following=following_scan(case))
        paired_metrics = {}
        for key, fit in json.loads(p.read_text()).items():
            version, arm = key.split("/")
            item = dict(
                experiment="following", variant=version, method="shared_phase", arm=arm, fit=fit
            )
            metric = nominated_metrics(
                scans[version],
                item,
                problem_factory=lambda *args: geometry_problem(
                    *args, mean_sigma=10, height_sigma=0
                ),
            )
            paired_metrics[(version, arm)] = metric
            future.append(
                dict(
                    case=case,
                    version=version,
                    arm=arm,
                    future_diagnostic_not_causal_solution=version == "following",
                    position_error_km=distance_km(
                        (fit["latitude_deg"], fit["longitude_deg"]), REFERENCE
                    ),
                    frequency_prior_score=fit["frequency_prior_score"],
                    **{k: v for k, v in metric.items() if k != "tracks"},
                )
            )
        for version in ("causal", "following"):
            rr = [
                {
                    r["component"]: r
                    for r in paired_metrics[(version, arm)]["tracks"]
                    if r["compatible"]
                }
                for arm in ("c0", "fitted_c")
            ]
            common = rr[0].keys() & rr[1].keys()
            n = sum(rr[0][k]["points"] for k in common)
            record = dict(
                case=case,
                version=version,
                future_diagnostic_not_causal_solution=version == "following",
                common_curved_points=n,
                same_label_points=sum(
                    rr[0][k]["points"] for k in common if rr[0][k]["norad"] == rr[1][k]["norad"]
                ),
            )
            for arm, r in zip(("c0", "fitted_c"), rr, strict=True):
                for label, field in (
                    ("native", "native_square_hz2"),
                    ("innovation", "innovation_square_hz2"),
                ):
                    record[f"{label}_rms_{arm}_hz"] = float(
                        np.sqrt(sum(r[k][field] for k in common) / max(1, n))
                    )
            future_comparisons.append(record)
    write_table("following_diagnostic_summary", future)
    write_table("following_diagnostic_c_ablation", future_comparisons)
    write(
        OUTPUT / "evaluation_binding.json",
        dict(
            input_sha256=bindings,
            reference_GPS_read_by_reporter_only=True,
            reference=REFERENCE,
            frequency_metrics_nominated_curved_only_not_all_GLRT=True,
            future_TLE_results_diagnostic_only=True,
        ),
    )
    plot(summary)
    return summary, comparisons, future


def plot(summary):
    cases = [f"DSX01-S0{k}" for k in range(1, 6)]
    variants = ["student_none", "student_physical", "hierarchy_physical"]
    fig, axes = plt.subplots(2, 3, figsize=(18, 8), constrained_layout=True)
    for i, arm in enumerate(("c0", "fitted_c")):
        for j, variant in enumerate(variants):
            values = np.full((5, 6), np.nan)
            for r in summary:
                if r["experiment"] == "marginal" and r["arm"] == arm and r["variant"] == variant:
                    values[cases.index(r["case"]), METHODS.index(r["method"])] = r[
                        "position_error_km"
                    ]
            ax = axes[i, j]
            im = ax.imshow(values, vmin=0, vmax=6, cmap="RdYlGn_r", aspect="auto")
            ax.set(
                title=f"{variant} / {arm}",
                xticks=range(6),
                xticklabels=METHODS,
                yticks=range(5),
                yticklabels=cases,
            )
            ax.tick_params(axis="x", rotation=45, labelsize=8)
            for a, b in np.ndindex(values.shape):
                if np.isfinite(values[a, b]):
                    ax.text(b, a, f"{values[a, b]:.2f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=axes, label="Independent position error (km)", shrink=0.65)
    fig.savefig(OUTPUT / "marginal_accuracy.png", dpi=160)
    plt.close(fig)
    rows = [r for r in summary if r["case"] == "DSX01-S01" and r["method"] == "shared_phase"]
    names = sorted({r["variant"] for r in rows})
    fig, axes = plt.subplots(1, 2, figsize=(16, 5), constrained_layout=True)
    for arm, offset in [("c0", -0.17), ("fitted_c", 0.17)]:
        rr = {r["variant"]: r for r in rows if r["arm"] == arm}
        for ax, key in zip(
            axes, ["position_error_km", "accepted_nominated_curved_points"], strict=True
        ):
            ax.bar(
                np.arange(len(names)) + offset,
                [rr.get(n, {}).get(key, np.nan) for n in names],
                width=0.32,
                label=arm,
            )
            ax.set(xticks=range(len(names)), xticklabels=names)
            ax.tick_params(axis="x", rotation=65, labelsize=8)
            ax.legend()
            ax.grid(axis="y", alpha=0.2)
    axes[0].axhline(1, color="black", linestyle=":")
    axes[0].set_ylabel("Independent S01 error (km)")
    axes[1].set_ylabel("Accepted nominated curved GLRT")
    fig.savefig(OUTPUT / "s01_uncertainty_controls.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    run()
