"""Postfit GPS evaluation and frequency diagnostics for the next blind probes."""

import csv
import hashlib
import json
from collections import defaultdict

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from iterate_dsx01_position_nominations import OUTPUT as NOMINATIONS
from iterate_dsx01_position_nominations import AnchoredFamilies
from iterate_dsx01_profiled_identity import OUTPUT as IDENTITY
from localize_merged_track_catalogue import distance_km
from prototype_dsx01_family_consensus import OUTPUT as CONSENSUS
from prototype_dsx01_family_consensus import ConsensusFamilies
from prototype_dsx01_phase_priors import OUTPUT as PHASE
from prototype_dsx01_phase_priors import CausalPhaseFamilies
from prototype_dsx01_rf_clock import OUTPUT as CLOCK
from prototype_dsx01_rf_clock import RFClockFamilies
from prototype_s01_causal_shape import OUTPUT as SHAPE
from prototype_s01_causal_shape import PREVIOUS, CausalShapeFamilies
from prototype_s01_joint_radio_orbit import OUTPUT as JOINT
from prototype_s01_joint_radio_orbit import radio_problem
from prototype_s01_receiver_drift import OUTPUT as DRIFT
from prototype_s01_receiver_drift import receiver_problem

from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile, whitening

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUTPUT = ROOT / "reports/2026_10_18_dsx01_model_iterations"
REFERENCE = (37.849061591561885, -122.48574968092912)


def inputs():
    items = defaultdict(list)
    bindings = {}
    for budget in (2, 32):
        for case_dir in sorted((NOMINATIONS / f"seeds_{budget}").glob("DSX01-S0*")):
            end = case_dir / "endpoints.json"
            selected = json.loads(end.read_text()) if end.exists() else {}
            if end.exists():
                bindings[str(end)] = hashlib.sha256(end.read_bytes()).hexdigest()
            for path in sorted(case_dir.glob("*_iterations.json")):
                bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
                method = path.stem.removesuffix("_iterations")
                for record in json.loads(path.read_text()):
                    for arm, fit in record["fits"].items():
                        iteration = record["iteration"]
                        chosen = selected.get(f"{arm}/{method}", {}).get("selected_iteration")
                        items[case_dir.name].append(
                            dict(
                                experiment="nomination",
                                model="floor1",
                                variant=f"seeds{budget}_round{iteration}",
                                method=method,
                                arm=arm,
                                selected_round=chosen == iteration,
                                fit=fit,
                            )
                        )
    for kind, root in (("rf_clock", CLOCK), ("phase_prior", PHASE)):
        for path in sorted(root.glob("DSX01-S0*/endpoints.json")):
            bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            for key, fit in json.loads(path.read_text()).items():
                variant, arm, method = key.split("/")
                items[path.parent.name].append(
                    dict(
                        experiment=kind,
                        model=variant,
                        variant=variant,
                        method=method,
                        arm=arm,
                        selected_round=True,
                        fit=fit,
                    )
                )
    for path in sorted(CONSENSUS.glob("DSX01-S0*/*/endpoints.json")):
        bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        for key, fit in json.loads(path.read_text()).items():
            variant, arm = key.split("/")
            items[path.parent.parent.name].append(
                dict(
                    experiment="family_consensus",
                    model=variant,
                    variant=variant,
                    method=path.parent.name,
                    arm=arm,
                    selected_round=True,
                    fit=fit,
                )
            )
    for path in sorted(IDENTITY.glob("DSX01-S0*/*/iterations.json")):
        bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        endpoint = json.loads(path.with_name("endpoints.json").read_text())
        bindings[str(path.with_name("endpoints.json"))] = hashlib.sha256(
            path.with_name("endpoints.json").read_bytes()
        ).hexdigest()
        for record in json.loads(path.read_text()):
            for arm, fit in record["fits"].items():
                variant = f"profile_round{record['iteration']}"
                items[path.parent.parent.name].append(
                    dict(
                        experiment="profiled_identity",
                        model="floor1",
                        variant=variant,
                        method=path.parent.name,
                        arm=arm,
                        selected_round=endpoint[arm].get("selected_from")
                        == f"round{record['iteration']}",
                        fit=fit,
                    )
                )
    for path in sorted(SHAPE.glob("*/endpoints.json")):
        bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        bindings[str(PREVIOUS)] = hashlib.sha256(PREVIOUS.read_bytes()).hexdigest()
        for key, fit in json.loads(path.read_text()).items():
            variant, arm = key.split("/")
            items["DSX01-S01"].append(
                dict(
                    experiment="causal_shape",
                    model=variant,
                    variant=variant,
                    method=path.parent.name,
                    arm=arm,
                    selected_round=True,
                    fit=fit,
                )
            )
    for kind, root in (("joint_radio_orbit", JOINT), ("receiver_drift", DRIFT)):
        for path in sorted(root.glob("*/endpoints.json")):
            bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            for key, fit in json.loads(path.read_text()).items():
                variant, arm = key.split("/")
                items["DSX01-S01"].append(
                    dict(
                        experiment=kind,
                        model=variant,
                        variant=variant,
                        method=path.parent.name,
                        arm=arm,
                        selected_round=True,
                        fit=fit,
                    )
                )
    return items, bindings


def nominated_metrics(scan, item):
    fit, method, arm = item["fit"], item["method"], item["arm"]
    seed = dict(rows=fit["rows"], state=fit["state"])
    args = (scan, seed, method, arm == "fitted_c", fit["east_north_km"])
    if item["experiment"] == "receiver_drift":
        _, _, mean, _, shape = item["variant"].split("_")
        p = receiver_problem(*args, mean_sigma=float(mean), shape_sigma=float(shape))
    elif item["experiment"] == "joint_radio_orbit":
        sigma = float(item["variant"].removeprefix("wide_shape_sigma_"))
        p = radio_problem(*args, sigma=sigma)
    elif item["experiment"] == "causal_shape" and item["variant"] != "shape_sigma_0":
        p = CausalShapeFamilies(*args, sigma=float(item["variant"].removeprefix("shape_sigma_")))
    elif item["experiment"] == "family_consensus":
        p = ConsensusFamilies(*args, mode=item["variant"])
    elif item["experiment"] == "rf_clock" and item["variant"] != "rf_sigma_0":
        p = RFClockFamilies(*args, sigma=float(item["variant"].removeprefix("rf_sigma_")))
    elif item["experiment"] == "phase_prior":
        p = CausalPhaseFamilies(*args, mode=item["variant"])
    else:
        p = AnchoredFamilies(*args)
    p.alias = fit["aliases"]
    x = np.array(min(fit["fits"], key=lambda r: r["score"])["parameters"])
    state, (f, elevation) = p.decode(x), p.predicted(x)
    rows = []
    for i, row, block, alias in zip(p.members, p.rows, p.slices, p.alias, strict=True):
        t = scan.tracks[i]
        y = t["values"] - scan.hardware(t, state["beta"])
        if method == "receiver_smooth":
            y -= t["rf_hz"] / 11.5e9 * scan.rx_basis[i] @ state["smooth"][t["receiver"] - 1]
        predicted = t["rf_hz"] / 11.5e9 * f[block]
        cut = row["split_at"] if method == "penalized_split" else -1
        slices = (slice(None),) if cut <= 0 else (slice(0, cut), slice(cut, None))
        native, innovations, passing, aliases = [], [], True, []
        for part in slices:
            times = t["times"][part]
            w, volume = (
                (scan.ou[i] if method == "correlated_noise" else scan.white[i])
                if cut <= 0
                else whitening(times)
            )
            terms = profile(y[part], predicted[part], w, volume)
            noise = batch_noise_screen(terms["innovations"], times)
            passing &= bool(
                terms["rms"][0] <= 450
                and abs(terms["bias"][0]) <= 3000
                and noise["noise_screen_pass"][0]
            )
            native.extend(terms["residual"][0])
            innovations.extend(terms["innovations"][0])
            aliases.append(int(terms["alias"][0]))
        rows.append(
            dict(
                component=t["key"],
                norad=row["candidate_norad"],
                candidate_index=row["candidate_index"],
                points=len(y),
                compatible=passing and bool(elevation[block].min() >= 0),
                native_square_hz2=float(np.sum(np.array(native) ** 2)),
                innovation_square_hz2=float(np.sum(np.array(innovations) ** 2)),
                native_rms_hz=float(np.sqrt(np.mean(np.array(native) ** 2))),
                aliases_changed=sum(a != alias for a in aliases),
            )
        )
    while True:
        owners = defaultdict(set)
        shape_owners = defaultdict(set)
        for r, i in zip(rows, p.members, strict=True):
            if r["compatible"]:
                owners[r["candidate_index"]].add(scan.tracks[i]["channel"])
                shape_owners[r["candidate_index"]].add(
                    (scan.tracks[i]["receiver"], scan.tracks[i]["channel"])
                )
        changed = False
        for r in rows:
            if (
                r["compatible"]
                and r["candidate_index"] in state["extra"]
                and len(owners[r["candidate_index"]]) < 2
            ):
                r["compatible"] = False
                changed = True
            if (
                r["compatible"]
                and r["candidate_index"] in state.get("causal_shape_coefficients", {})
                and len(shape_owners[r["candidate_index"]]) < 2
            ):
                r["compatible"] = False
                changed = True
        if not changed:
            break
    n = sum(r["points"] for r in rows)
    accepted = [r for r in rows if r["compatible"]]
    na = sum(r["points"] for r in accepted)
    return dict(
        curved_points=n,
        accepted_nominated_curved_points=na,
        all_curved_native_rms_hz=float(
            np.sqrt(sum(r["native_square_hz2"] for r in rows) / max(1, n))
        ),
        accepted_native_rms_hz=float(
            np.sqrt(sum(r["native_square_hz2"] for r in accepted) / max(1, na))
        ),
        accepted_innovation_rms_hz=float(
            np.sqrt(sum(r["innovation_square_hz2"] for r in accepted) / max(1, na))
        ),
        aliases_changed=sum(r["aliases_changed"] for r in rows),
        tracks=rows,
    )


def run():
    OUTPUT.mkdir(exist_ok=True)
    items, bindings = inputs()
    summary, all_metrics, ablations = [], {}, []
    for case, records in sorted(items.items()):
        cache_path = OUTPUT / f"{case}_frequency_cache.json"
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
        scan = None
        for item in records:
            fit = item["fit"]
            key = "/".join([item[k] for k in ("experiment", "variant", "arm", "method")])
            digest = hashlib.sha256(json.dumps(fit, sort_keys=True).encode()).hexdigest()
            if key not in cache or cache[key]["fit_sha256"] != digest:
                scan = Scan(case) if scan is None else scan
                cache[key] = dict(fit_sha256=digest, **nominated_metrics(scan, item))
            metrics = cache[key]
            row = {k: item[k] for k in ("experiment", "variant", "arm", "method", "selected_round")}
            row.update(
                case=case,
                position_error_km=distance_km(
                    (fit["latitude_deg"], fit["longitude_deg"]), REFERENCE
                ),
                east_km=fit["east_north_km"][0],
                north_km=fit["east_north_km"][1],
                frequency_prior_score=fit["frequency_prior_score"],
                complexity_penalty=fit["complexity_penalty"],
                total_score=fit["score"],
                **{k: v for k, v in metrics.items() if k not in ("fit_sha256", "tracks")},
            )
            summary.append(row)
            all_metrics[f"{case}/{key}"] = metrics
        write(cache_path, cache)
        print(case, len(records), flush=True)
    by_key = {(r["case"], r["experiment"], r["variant"], r["method"], r["arm"]): r for r in summary}
    for row in summary:
        if row["arm"] != "c0":
            continue
        pair = by_key.get(
            (row["case"], row["experiment"], row["variant"], row["method"], "fitted_c")
        )
        if pair is None:
            continue
        matches = []
        for arm in ("c0", "fitted_c"):
            key = f"{row['case']}/{row['experiment']}/{row['variant']}/{arm}/{row['method']}"
            matches.append(
                {t["component"]: t for t in all_metrics[key]["tracks"] if t["compatible"]}
            )
        common = matches[0].keys() & matches[1].keys()
        n = sum(matches[0][k]["points"] for k in common)
        record = {k: row[k] for k in ("case", "experiment", "variant", "method")}
        record.update(
            common_curved_points=n,
            same_label_points=sum(
                matches[0][k]["points"]
                for k in common
                if matches[0][k]["norad"] == matches[1][k]["norad"]
            ),
        )
        for arm, rr in zip(("c0", "fitted_c"), matches, strict=True):
            record[f"native_rms_{arm}_hz"] = float(
                np.sqrt(sum(rr[k]["native_square_hz2"] for k in common) / max(1, n))
            )
            record[f"innovation_rms_{arm}_hz"] = float(
                np.sqrt(sum(rr[k]["innovation_square_hz2"] for k in common) / max(1, n))
            )
        ablations.append(record)
    for name, rows in (("evaluation_summary", summary), ("c_ablation", ablations)):
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
            evaluation_reference_read_only_by_reporter=True,
            reference=REFERENCE,
            frequency_metrics_are_nominated_curved_fragments_not_all_GLRT=True,
            all_RF_and_phase_prior_controls_exploratory=True,
        ),
    )
    fig, axes = plt.subplots(2, 3, figsize=(16, 9), constrained_layout=True)
    for ax, method in zip(axes.flat, METHODS, strict=True):
        rr = [
            r
            for r in summary
            if r["case"] == "DSX01-S01" and r["method"] == method and r["arm"] == "fitted_c"
        ]
        ax.bar(
            range(len(rr)),
            [r["position_error_km"] for r in rr],
            color=[
                "tab:blue"
                if r["experiment"] == "nomination"
                else "tab:orange"
                if r["experiment"] == "rf_clock"
                else "tab:green"
                for r in rr
            ],
        )
        ax.axhline(1, color="black", linestyle="--", linewidth=0.8)
        ax.set(
            title=method.replace("_", " "),
            ylabel="S01 position error (km)",
            xticks=range(len(rr)),
            xticklabels=[r["variant"] for r in rr],
        )
        ax.tick_params(axis="x", rotation=80, labelsize=7)
    fig.suptitle(
        "Blind 25 x 25 km Mill Valley: calibration, nomination, RF drift and causal phase controls"
    )
    fig.savefig(OUTPUT / "s01_model_iterations.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(3, 2, figsize=(12, 10), constrained_layout=True)
    for i, method in enumerate(("shared_phase", "family_rate", "orbit_em")):
        for arm, marker in (("c0", "o"), ("fitted_c", "x")):
            rows = [
                r
                for r in summary
                if r["experiment"] == "causal_shape" and r["method"] == method and r["arm"] == arm
            ]
            rows = sorted(rows, key=lambda r: float(r["variant"].removeprefix("shape_sigma_")))
            if not rows:
                continue
            sigma = [float(r["variant"].removeprefix("shape_sigma_")) for r in rows]
            axes[i, 0].plot(sigma, [r["position_error_km"] for r in rows], marker=marker, label=arm)
            axes[i, 1].plot(
                sigma,
                [r["accepted_nominated_curved_points"] for r in rows],
                marker=marker,
                label=arm,
            )
        axes[i, 0].axhline(1, color="black", linestyle="--", linewidth=0.7)
        axes[i, 0].set(
            title=method.replace("_", " "),
            xlabel="Causal error-direction prior sigma",
            ylabel="Position error (km)",
        )
        axes[i, 1].set(
            title="Strict gates at the frozen estimated site",
            xlabel="Causal error-direction prior sigma",
            ylabel="Accepted nominated curved GLRT",
        )
        for ax in axes[i]:
            ax.grid(alpha=0.2)
            ax.legend(fontsize=8)
    fig.suptitle(
        "Shared causal orbit-shape correction: "
        "frequency retention and accuracy are separate outcomes"
    )
    fig.savefig(OUTPUT / "causal_shape_tradeoff.png", dpi=160)
    plt.close(fig)
    modes = ("floor1", "causal_gaussian", "causal_student", "causal_3x")
    cases = sorted({r["case"] for r in summary})
    fig, axes = plt.subplots(2, 4, figsize=(20, 8), constrained_layout=True)
    for i, arm in enumerate(("c0", "fitted_c")):
        for j, mode in enumerate(modes):
            values = np.full((len(cases), len(METHODS)), np.nan)
            for row in summary:
                if (
                    row["experiment"] == "phase_prior"
                    and row["variant"] == mode
                    and row["arm"] == arm
                ):
                    values[cases.index(row["case"]), METHODS.index(row["method"])] = row[
                        "position_error_km"
                    ]
            ax = axes[i, j]
            im = ax.imshow(values, vmin=0, vmax=8, cmap="RdYlGn_r", aspect="auto")
            ax.set(
                title=f"{mode} / {arm}",
                xticks=range(len(METHODS)),
                xticklabels=METHODS,
                yticks=range(len(cases)),
                yticklabels=cases,
            )
            ax.tick_params(axis="x", rotation=60, labelsize=8)
            for a in range(len(cases)):
                for b in range(len(METHODS)):
                    if np.isfinite(values[a, b]):
                        ax.text(b, a, f"{values[a, b]:.2f}", ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=axes, label="Independent position error (km)", shrink=0.65)
    fig.savefig(OUTPUT / "causal_prior_accuracy.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(3, 2, figsize=(12, 10), constrained_layout=True)
    for i, method in enumerate(("shared_phase", "family_rate", "orbit_em")):
        for shape, style in ((0, "-"), (1, "--")):
            for arm, marker in (("c0", "o"), ("fitted_c", "x")):
                rows = [
                    r
                    for r in summary
                    if r["experiment"] == "receiver_drift"
                    and r["method"] == method
                    and r["arm"] == arm
                    and r["variant"].endswith(f"_shape_{shape}")
                ]
                rows.sort(key=lambda r: float(r["variant"].split("_")[2]))
                scales = [float(r["variant"].split("_")[2]) for r in rows]
                label = f"{arm}; shape sigma {shape}"
                for ax, metric in zip(
                    axes[i],
                    ("position_error_km", "accepted_nominated_curved_points"),
                    strict=True,
                ):
                    ax.plot(scales, [r[metric] for r in rows], style, marker=marker, label=label)
        axes[i, 0].axhline(1, color="black", linestyle=":", linewidth=0.8)
        axes[i, 0].set(title=method, ylabel="S01 error (km)")
        axes[i, 1].set(title="Strict gates at frozen estimated site", ylabel="Curved GLRT accepted")
        for ax in axes[i]:
            ax.set(xlabel="RX common drift prior sigma (Hz/s)")
            ax.grid(alpha=0.2)
            ax.legend(fontsize=7)
    fig.suptitle("RX common drift versus small band contrast: matched c controls")
    fig.savefig(OUTPUT / "receiver_common_drift.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    run()
