"""Postfit evaluation only: radio remeasurement, RX differences and position."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, Scan
from localize_merged_track_catalogue import distance_km
from profile_dsx01_geographic_calibration import geometry_problem
from prototype_dsx01_causal_clock import lock_aliases
from prototype_dsx01_glrt_weighting import variance_samples
from prototype_dsx01_pair_difference import pair_problem
from prototype_dsx01_remeasured_position import OUTPUT, VARIANTS, apply_measurements
from prototype_dsx01_remeasured_prior_controls import prior_problem
from report_dsx01_model_iterations import REFERENCE, nominated_metrics

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


def records():
    roots = [
        ("wide_floor", OUTPUT / "localization/DSX01-S05"),
        ("tight_causal", OUTPUT / "prior_controls/DSX01-S05/tight_causal"),
    ]
    for mode, root in roots:
        for path in sorted(root.glob("*/endpoints.json")):
            for variant, record in json.loads(path.read_text()).items():
                yield dict(
                    mode=mode,
                    variant=variant,
                    method=path.parent.name,
                    source=str(path),
                    pairs=False,
                    record=record,
                )
    for path in sorted((OUTPUT / "pair_difference/DSX01-S05").glob("*/*/endpoints.json")):
        for key, record in json.loads(path.read_text()).items():
            variant, pair = key.split("/")
            yield dict(
                mode="pair_" + path.parent.parent.name,
                variant=variant,
                method=path.parent.name,
                source=str(path),
                pairs=pair == "pairs1",
                record=record,
            )
    for path in sorted((OUTPUT / "pair_prior_control/DSX01-S05").glob("*/endpoints.json")):
        for variant, record in json.loads(path.read_text()).items():
            yield dict(
                mode="pair_matched_wide_causal",
                variant=variant,
                method=path.parent.name,
                source=str(path),
                pairs=True,
                record=record,
            )


def receiver_audit(scan, fit, pairs, method):
    index = {
        oid: (i, k) for i in scan.curved for k, oid in enumerate(scan.tracks[i]["observation_ids"])
    }
    state = fit["state"]
    hardware = []
    labels = {r["component"]: r["candidate_index"] for r in fit["rows"]}
    for i, t in enumerate(scan.tracks):
        h = scan.hardware(t, state["beta"])
        if method == "receiver_smooth":
            h += (
                t["rf_hz"]
                / 11.5e9
                * (scan.rx_basis[i] @ np.array(state["smooth"][t["receiver"] - 1]))
            )
        hardware.append(h)
    rows = []
    period = 1 / 4.4e-6
    for p in pairs:
        if p["channel"] > 4 or not p["frame_coherent"] or not p["both_original_curved"]:
            continue
        z = []
        candidate = []
        for oid in p["observation_ids"]:
            i, k = index[oid]
            z.append(scan.tracks[i]["values"][k] - hardware[i][k])
            candidate.append(labels[scan.tracks[i]["key"]])
        rows.append(
            dict(
                observation_ids=p["observation_ids"],
                time_s=p["time_s"],
                residual_hz=float((z[0] - z[1] + period / 2) % period - period / 2),
                same_candidate=candidate[0] == candidate[1],
            )
        )
    r = np.array([v["residual_hz"] for v in rows])
    return dict(
        points=len(r),
        mean_hz=float(r.mean()),
        rms_hz=float(np.sqrt(np.mean(r * r))),
        centered_rms_hz=float(np.std(r)),
        same_candidate_pairs=sum(p["same_candidate"] for p in rows),
        records=rows,
    )


def run():
    measurement = OUTPUT / "remeasurement/DSX01-S05/measurements.json"
    points = json.loads(measurement.read_text())["points"]
    pairs = json.loads(
        (
            OUTPUT.parent
            / "2026_10_18_dsx01_geographic_calibration/frame_coherent_calibration.json"
        ).read_text()
    )["DSX01-S05"]["pairs"]
    scans = {}
    for variant in VARIANTS:
        scan = Scan("DSX01-S05")
        apply_measurements(scan, points, variant)
        scans[variant] = scan
    summary = []
    details = {}
    bindings = {}
    ablation = []
    validation = []
    for item in records():
        scan = scans[item["variant"]]
        fits = item["record"]["fits"]
        assert fits["c0"]["rows"] == fits["fitted_c"]["rows"]
        assert fits["c0"]["aliases"] == fits["fitted_c"]["aliases"]
        assert fits["c0"]["starts"] == fits["fitted_c"]["starts"]
        bindings[item["source"]] = hashlib.sha256(Path(item["source"]).read_bytes()).hexdigest()
        key = "/".join([item["mode"], item["method"], item["variant"], str(int(item["pairs"]))])
        local = {}
        for arm, fit in fits.items():

            def factory(*args, mode=item["mode"], use_pairs=item["pairs"], aliases=fit["aliases"]):
                if mode.startswith("pair_"):
                    p = pair_problem(
                        *args,
                        pairs=pairs,
                        mode=mode.removeprefix("pair_").removeprefix("matched_"),
                        use_pairs=use_pairs,
                    )
                elif mode == "tight_causal":
                    p = prior_problem(*args, mode="tight_causal")
                else:
                    p = geometry_problem(*args, mean_sigma=10, height_sigma=0)
                lock_aliases(p, aliases)
                return p

            m = nominated_metrics(
                scan, dict(fit=fit, method=item["method"], arm=arm), problem_factory=factory
            )
            p = factory(
                scan,
                dict(rows=fit["rows"], state=fit["state"]),
                item["method"],
                arm == "fitted_c",
                fit["east_north_km"],
            )
            x = np.array(min(fit["fits"], key=lambda r: r["score"])["parameters"])
            z = p.residual(x)
            replay = float(z @ z)
            assert abs(replay - fit["frequency_prior_score"]) < 1e-5, (
                key,
                arm,
                replay,
                fit["frequency_prior_score"],
            )
            hardware = receiver_audit(scan, fit, pairs, item["method"])
            local[arm] = m
            details[key + "/" + arm] = dict(metrics=m, receiver_audit=hardware)
            summary.append(
                dict(
                    mode=item["mode"],
                    method=item["method"],
                    variant=item["variant"],
                    pairs=item["pairs"],
                    arm=arm,
                    position_error_km=distance_km(
                        (fit["latitude_deg"], fit["longitude_deg"]), REFERENCE
                    ),
                    frequency_prior_score=fit["frequency_prior_score"],
                    total_score=fit["score"],
                    accepted_nominated_curved_points=m["accepted_nominated_curved_points"],
                    accepted_fragments=sum(r["compatible"] for r in m["tracks"]),
                    native_rms_hz=m["accepted_native_rms_hz"],
                    innovation_rms_hz=m["accepted_innovation_rms_hz"],
                    differential_RX_rms_hz=hardware["rms_hz"],
                    differential_RX_centered_rms_hz=hardware["centered_rms_hz"],
                    max_abs_band_rate_hz_s=float(
                        np.max(abs(np.array(fit["state"]["beta"])[4:8] / 150))
                    ),
                    corrected_GLRT_points=item["record"]["measurement_metadata"]["corrected"],
                )
            )
        left, right = [
            {r["component"]: r for r in local[a]["tracks"] if r["compatible"]}
            for a in ["c0", "fitted_c"]
        ]
        common = left.keys() & right.keys()
        n = sum(left[k]["points"] for k in common)
        ablation.append(
            dict(
                key=key,
                common_points=n,
                same_label_points=sum(
                    left[k]["points"] for k in common if left[k]["norad"] == right[k]["norad"]
                ),
                native_rms_c0_hz=float(
                    np.sqrt(sum(left[k]["native_square_hz2"] for k in common) / max(1, n))
                ),
                native_rms_fitted_c_hz=float(
                    np.sqrt(sum(right[k]["native_square_hz2"] for k in common) / max(1, n))
                ),
            )
        )
        validation.append(
            dict(key=key, matched_rows_aliases_starts=True, recomputed_objectives=True)
        )
    write(OUTPUT / "evaluation_summary.json", summary)
    write(OUTPUT / "frequency_and_pair_details.json", details)
    write(OUTPUT / "c_ablation.json", ablation)
    write(OUTPUT / "evaluation_bindings.json", bindings)
    scores = json.loads(
        (OUTPUT.parent / "2026_10_18_dsx01_causal_repairs/glrt_scores.json").read_text()
    )["DSX01-S05"]["scores"]
    radio_noise = {}
    for variant, scan in scans.items():
        _, squares = variance_samples(scan, scores)
        radio_noise[variant] = dict(
            samples=len(squares),
            polynomial_leverage_corrected_rms_hz=float(np.sqrt(np.mean(squares))),
            absolute_residuals_hz=np.sqrt(squares),
        )
    write(OUTPUT / "radio_noise.json", radio_noise)
    write(
        OUTPUT / "fit_validation.json",
        dict(
            records=len(summary),
            matched_c_pairs=len(ablation),
            checks=validation,
            original_curved_observation_ids_unique=True,
            original_curved_points=len(points),
            GPS_used_only_after_fit=True,
        ),
    )
    for name, rows in [("evaluation_summary", summary), ("c_ablation", ablation)]:
        with (OUTPUT / (name + ".csv")).open("w") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    plot(summary)
    print(
        json.dumps(dict(evaluated_records=len(summary), matched_c_pairs=len(ablation))), flush=True
    )


def plot(summary):
    plt.rcParams.update({"font.size": 9})
    # Per-frame radio evidence uses independent eight-tone gains, not the GLRT refiner.
    frames = json.loads((OUTPUT / "DSX01-S05/window_results.json").read_text())["rows"]
    fig, axes = plt.subplots(2, 4, figsize=(16, 7), sharex=True)
    for ax, row in zip(axes.flat, frames, strict=True):
        y = np.array([v["residual_cfo_hz"] for v in row["individual"]])
        t = np.arange(len(y)) / 750 * 1000
        ax.plot(t, y, "o-", ms=3)
        ax.axhline(0, color="gray", lw=0.8)
        ax.set_title(row["track"] + f"\nt={row['time_s']:.1f}s")
        ax.set_xlabel("Frame start offset (ms)")
        ax.set_ylabel("CFO − original GLRT (Hz)")
    fig.suptitle("Independent frame carrier estimates within eight existing 20-ms windows")
    fig.tight_layout()
    fig.savefig(OUTPUT / "within_window_carrier.png", dpi=170)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(11, 4))
    for row in frames:
        x = row["number"]
        h = [v["symbol_clock_ppm"] for v in row["halves"]]
        ax.plot([x, x], h, "-", color="gray")
        ax.scatter([x, x], h, color="gray", marker="x")
        ax.scatter(x, row["joint"]["symbol_clock_ppm"], color="tab:blue", s=35)
    ax.axhline(0, color="black", lw=0.5)
    ax.set(
        xticks=range(8),
        xlabel="Selected window",
        ylabel="Received symbol-clock offset (ppm)",
        title="Whole-window estimate (blue) and time halves (gray; not confidence intervals)",
    )
    fig.tight_layout()
    fig.savefig(OUTPUT / "symbol_clock_consistency.png", dpi=170)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    radio_noise = json.loads((OUTPUT / "radio_noise.json").read_text())
    point_data = json.loads((OUTPUT / "remeasurement/DSX01-S05/measurements.json").read_text())[
        "points"
    ]
    for variant in VARIANTS:
        info = radio_noise[variant]
        values = np.sort(info["absolute_residuals_hz"])
        axes[0].plot(
            values,
            np.arange(1, len(values) + 1) / len(values),
            label=f"{variant}: RMS {info['polynomial_leverage_corrected_rms_hz']:.1f} Hz",
        )
        if variant != "original":
            delta = [
                r[variant]["residual_cfo_hz"] for r in point_data.values() if r[variant]["accepted"]
            ]
            axes[1].hist(delta, bins=np.linspace(-400, 400, 60), histtype="step", label=variant)
    axes[0].set(
        xlim=(0, 600),
        xlabel="Leverage-corrected radio polynomial |residual| (Hz)",
        ylabel="Empirical fraction",
        title="Radio-only noise check; original pieces and degrees",
    )
    axes[1].set(xlabel="Accepted CFO correction (Hz)", ylabel="Points", title="Refinement changes")
    for ax in axes:
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUTPUT / "remeasurement_noise.png", dpi=170)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for ax, mode in zip(axes, ["wide_floor", "tight_causal"], strict=True):
        for method in METHODS:
            r = {
                s["variant"]: s
                for s in summary
                if s["mode"] == mode and s["method"] == method and s["arm"] == "fitted_c"
            }
            if len(r) == 4:
                ax.plot(range(4), [r[v]["position_error_km"] for v in VARIANTS], "o-", label=method)
        ax.axhline(1, color="black", ls=":")
        ax.set(
            xticks=range(4),
            xticklabels=["Original", "Fine 64", "Full 300", "Midpoint 300"],
            ylabel="Position error (km)",
            title=mode,
        )
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUTPUT / "s05_remeasurement_accuracy.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for mode, color in [("pair_tight_causal", "tab:blue"), ("pair_wide_causal", "tab:orange")]:
        for v in VARIANTS:
            rr = {
                s["pairs"]: s
                for s in summary
                if s["mode"] == mode and s["variant"] == v and s["arm"] == "fitted_c"
            }
            if len(rr) != 2:
                continue
            a, b = rr[False], rr[True]
            axes[0].plot(
                [a["differential_RX_rms_hz"], b["differential_RX_rms_hz"]],
                [a["position_error_km"], b["position_error_km"]],
                "o-",
                color=color,
                label=mode + "/" + v,
            )
            axes[0].annotate(
                "",
                xy=(b["differential_RX_rms_hz"], b["position_error_km"]),
                xytext=(a["differential_RX_rms_hz"], a["position_error_km"]),
                arrowprops=dict(arrowstyle="->", color=color),
            )
            if v != "midpoint300":
                axes[0].annotate(
                    v,
                    (b["differential_RX_rms_hz"], b["position_error_km"]),
                    xytext=(5, -10 if v == "glrt64" else 5),
                    textcoords="offset points",
                    fontsize=8,
                )
    axes[0].axhline(1, color="black", ls=":")
    axes[0].set(
        xlabel="80 timing-coherent RX pair residual RMS (Hz)",
        ylabel="Position error (km)",
        title="Pair constraint (fitted c): control → mean/difference model",
    )
    axes[0].legend(
        handles=[
            Line2D([0], [0], color="tab:blue", label="Tight causal"),
            Line2D([0], [0], color="tab:orange", label="Wide causal"),
        ],
        loc="center right",
        fontsize=8,
    )
    for row in summary:
        if row["mode"] == "pair_matched_wide_causal" and row["arm"] == "fitted_c":
            axes[0].scatter(
                row["differential_RX_rms_hz"],
                row["position_error_km"],
                color="tab:green",
                marker="*",
                s=60,
            )
    settle = json.loads((OUTPUT / "settling_profile.json").read_text())["results"]
    for g, d in settle.items():
        x = np.array(d["tau_grid_ms"][:-1])
        y = np.array(d["weighted_sse"])
        axes[1].plot(x, 100 * (y[:-1] / y[-1] - 1), label="RX/band " + g)
    axes[1].set(
        xscale="log",
        xlabel="Assumed exponential settling time (ms)",
        ylabel="Cost above free-linear model (%)",
        title="Linear ramps do not identify a settled-frequency correction",
    )
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUTPUT / "pair_calibration_and_settling.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    run()
