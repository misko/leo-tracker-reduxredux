"""Postfit-only GPS evaluation of bounded S05 causal repair experiments."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from build_dsx01_causal_forecast import OUTPUT
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from localize_merged_track_catalogue import distance_km
from prototype_dsx01_causal_repairs import repair_problem
from prototype_dsx01_complete_uncertainty import complete_problem
from prototype_dsx01_glrt_weighting import weighted_scan
from prototype_dsx01_receiver_geometry import OUTPUT as BASELINE
from prototype_dsx01_receiver_geometry import geometry_problem
from prototype_dsx01_shell_radius import shell_problem
from report_dsx01_model_iterations import REFERENCE, nominated_metrics

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def records(case):
    for method in METHODS:
        source = BASELINE / case / method / "endpoints.json"
        original = json.loads(source.read_text())
        for arm in ("c0", "fitted_c"):
            yield dict(
                experiment="baseline",
                variant="baseline",
                arm=arm,
                method=method,
                source=str(source),
                fit=original[f"mean_10_height_0/{arm}"],
            )
        path = OUTPUT / case / method / "endpoints.json"
        for key, fit in json.loads(path.read_text()).items():
            variant, arm = key.split("/")
            yield dict(
                experiment="repair",
                variant=variant,
                arm=arm,
                method=method,
                source=str(path),
                fit=fit,
            )
        path = OUTPUT / "score_weighting" / case / method / "endpoints.json"
        if path.exists():
            for arm, fit in json.loads(path.read_text()).items():
                yield dict(
                    experiment="scores",
                    variant="glrt_weighting",
                    arm=arm,
                    method=method,
                    source=str(path),
                    fit=fit,
                )
        path = (
            ROOT
            / "reports/2026_10_18_dsx01_receiver_identity"
            / case
            / method
            / "mean_10_iterations.json"
        )
        if path.exists():
            rounds = json.loads(path.read_text())
            choices = [
                ("incumbent", {a: original[f"mean_10_height_0/{a}"] for a in ("c0", "fitted_c")})
            ]
            choices.extend((r["iteration"], r["fits"]) for r in rounds)
            selected, fits = min(choices, key=lambda pair: pair[1]["c0"]["score"])
            for arm, fit in fits.items():
                yield dict(
                    experiment="identity",
                    variant="c0_selected_identity",
                    arm=arm,
                    method=method,
                    source=str(path),
                    fit=fit,
                    selected_round=selected,
                )
        for path in sorted(
            (OUTPUT / "complete_uncertainty" / case / method).glob("*/endpoints.json")
        ):
            for key, fit in json.loads(path.read_text()).items():
                variant, arm = key.split("/")
                yield dict(
                    experiment="complete",
                    variant=f"{path.parent.name}_{variant}",
                    arm=arm,
                    method=method,
                    source=str(path),
                    fit=fit,
                )
        for path in sorted((OUTPUT / "shell_radius" / case / method).glob("*/endpoints.json")):
            for arm, fit in json.loads(path.read_text()).items():
                yield dict(
                    experiment="shell",
                    variant=f"{path.parent.name}_shell",
                    arm=arm,
                    method=method,
                    source=str(path),
                    fit=fit,
                )


def run(case="DSX01-S05"):
    summary, metrics, bindings = [], {}, {}
    scan = Scan(case)
    weighted = None
    # Cache keys include all new numerical sources to avoid stale gate results.
    source_names = [
        "prototype_dsx01_causal_repairs.py",
        "prototype_dsx01_complete_uncertainty.py",
        "prototype_dsx01_glrt_weighting.py",
        "build_dsx01_causal_forecast.py",
        "prototype_dsx01_shell_radius.py",
    ]
    source_hash = hashlib.sha256(
        b"".join((ROOT / "tools" / n).read_bytes() for n in source_names)
    ).hexdigest()
    cache_path = OUTPUT / f"{case}_frequency_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    for item in records(case):
        fit = item["fit"]
        bindings[item["source"]] = hashlib.sha256(Path(item["source"]).read_bytes()).hexdigest()
        key = "/".join(item[k] for k in ("experiment", "variant", "method", "arm"))
        digest = hashlib.sha256(
            (json.dumps(fit, sort_keys=True) + source_hash).encode()
        ).hexdigest()
        use_scan = scan
        if item["experiment"] == "repair":

            def factory(*args, name=item["variant"]):
                return repair_problem(*args, variant=name)
        elif item["experiment"] == "complete":
            _, likelihood, scale = item["variant"].split("_")

            def factory(*args, ll=likelihood, s=float(scale)):
                return complete_problem(*args, likelihood=ll, scale=s)
        elif item["experiment"] == "shell":
            factory = shell_problem
        else:

            def factory(*args):
                return geometry_problem(*args, mean_sigma=10, height_sigma=0)

            if item["experiment"] == "scores":
                if weighted is None:
                    weighted, _ = weighted_scan(case)
                use_scan = weighted

        def locked_factory(*args, fac=factory, aliases=fit["aliases"]):
            p = fac(*args)
            p.problem.alias = list(aliases)
            return p

        if key not in cache or cache[key]["fit_sha256"] != digest:
            cache[key] = dict(
                fit_sha256=digest,
                **nominated_metrics(use_scan, item, problem_factory=locked_factory),
            )
            write(cache_path, cache)
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
                accepted_fragments=len(accepted),
                points_per_accepted_fragment=metric["accepted_nominated_curved_points"]
                / max(1, len(accepted)),
                selected_identity_round=item.get("selected_round", ""),
                **{k: v for k, v in metric.items() if k not in ("tracks", "fit_sha256")},
            )
        )
    pairs = []
    for r in summary:
        if r["arm"] != "c0":
            continue
        prefix = "/".join(r[k] for k in ("experiment", "variant", "method"))
        rr = [
            {t["component"]: t for t in metrics[prefix + "/" + arm]["tracks"] if t["compatible"]}
            for arm in ("c0", "fitted_c")
        ]
        common = rr[0].keys() & rr[1].keys()
        n = sum(rr[0][k]["points"] for k in common)
        row = {k: r[k] for k in ("case", "experiment", "variant", "method")}
        row.update(
            common_points=n,
            same_label_points=sum(
                rr[0][k]["points"] for k in common if rr[0][k]["norad"] == rr[1][k]["norad"]
            ),
        )
        for arm, rs in zip(("c0", "fitted_c"), rr, strict=True):
            row[f"native_rms_{arm}_hz"] = float(
                np.sqrt(sum(rs[k]["native_square_hz2"] for k in common) / max(1, n))
            )
        pairs.append(row)
    for name, rows in [("evaluation_summary", summary), ("c_ablation", pairs)]:
        write(OUTPUT / f"{name}.json", rows)
        with (OUTPUT / f"{name}.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    write(
        OUTPUT / "evaluation_binding.json",
        dict(
            inputs_sha256=bindings, reporter_reads_GPS_only=True, nominated_curved_points_only=True
        ),
    )
    plot(summary, case)
    print("evaluated", len(summary), "paired", len(pairs), flush=True)
    return summary


def plot(summary, case):
    variants = [
        "baseline",
        "causal_forecast",
        "family_consensus",
        "band_curvature",
        "glrt_weighting",
        "c0_selected_identity",
    ]
    fig, axes = plt.subplots(2, 3, figsize=(17, 9), constrained_layout=True)
    for ax, method in zip(axes.flat, METHODS, strict=True):
        for arm, offset in [("c0", -0.17), ("fitted_c", 0.17)]:
            rows = {r["variant"]: r for r in summary if r["arm"] == arm and r["method"] == method}
            ax.bar(
                np.arange(len(variants)) + offset,
                [rows.get(v, {}).get("position_error_km", np.nan) for v in variants],
                width=0.32,
                label=arm,
            )
        ax.axhline(1, color="black", linestyle=":")
        ax.set(
            title=method,
            ylabel="Position error (km)",
            xticks=range(len(variants)),
            xticklabels=variants,
        )
        ax.tick_params(axis="x", rotation=55, labelsize=8)
        ax.grid(axis="y", alpha=0.2)
        ax.legend(fontsize=8)
    fig.savefig(OUTPUT / "s05_repair_accuracy.png", dpi=160)
    plt.close(fig)
    oracle = json.loads((OUTPUT / "oracle_only" / case / "baseline_drivers.json").read_text())
    fig, axes = plt.subplots(2, 3, figsize=(17, 8), constrained_layout=True)
    for ax, method in zip(axes.flat, METHODS, strict=True):
        families = list(oracle[method]["families"].items())[:6]
        ax.barh(
            [n for n, _ in families],
            [r["blind_minus_oracle_cost"] for _, r in families],
            color="tab:orange",
        )
        ax.invert_yaxis()
        ax.set(title=method, xlabel="Wrong-position minus GPS family data cost")
        ax.axvline(0, color="black")
        ax.grid(axis="x", alpha=0.2)
    fig.savefig(OUTPUT / "s05_family_drivers.png", dpi=160)
    plt.close(fig)
    if any(r["experiment"] == "complete" for r in summary):
        rows = [r for r in summary if r["experiment"] in ("complete", "shell")]
        names = sorted({r["variant"] for r in rows})
        fig, axes = plt.subplots(1, 2, figsize=(14, 5), constrained_layout=True)
        for arm, offset in [("c0", -0.17), ("fitted_c", 0.17)]:
            rr = {r["variant"]: r for r in rows if r["arm"] == arm}
            for ax, key in zip(
                axes, ["position_error_km", "accepted_nominated_curved_points"], strict=True
            ):
                ax.bar(
                    np.arange(len(names)) + offset,
                    [rr[n][key] for n in names],
                    width=0.32,
                    label=arm,
                )
                ax.set(xticks=range(len(names)), xticklabels=names)
                ax.tick_params(axis="x", rotation=50, labelsize=8)
                ax.legend()
        axes[0].set_ylabel("Independent position error (km)")
        axes[0].axhline(1, color="black", linestyle=":")
        axes[1].set_ylabel("Accepted nominated curved points")
        fig.savefig(OUTPUT / "s05_complete_orbit_controls.png", dpi=160)
        plt.close(fig)


if __name__ == "__main__":
    run()
