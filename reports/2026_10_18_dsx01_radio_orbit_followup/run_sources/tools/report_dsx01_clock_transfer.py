"""Postfit-only DSX01 transfer evaluation; GPS never enters inference tools."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, Scan
from dsx01_clock_transfer_models import (
    MODES,
    PointMixtureFamilies,
    grouped_mixture_profile,
    transfer_problem,
)
from localize_merged_track_catalogue import distance_km
from profile_dsx01_geographic_calibration import geometry_problem
from prototype_dsx01_causal_clock import lock_aliases
from prototype_dsx01_glrt_weighting import variance_samples
from prototype_dsx01_remeasured_position import apply_measurements
from prototype_s01_receiver_drift import ReceiverDriftProblem
from report_dsx01_model_iterations import REFERENCE, nominated_metrics
from run_dsx01_clock_transfer import MEASUREMENTS, OUTPUT, measurement_path, read_pairs
from run_dsx01_common_clock import clock_problem

matplotlib.use("Agg")
import matplotlib.pyplot as plt

CASES = tuple(f"DSX01-S0{k}" for k in range(1, 6))


def fingerprint(fit):
    return hashlib.sha256(json.dumps(fit, sort_keys=True).encode()).hexdigest()


def records():
    for path in sorted((OUTPUT / "parents").glob("*/*/endpoints.json")):
        case, method = path.parent.parent.name, path.parent.name
        for measurement, record in json.loads(path.read_text()).items():
            yield dict(
                kind="parent",
                case=case,
                method=method,
                mode="wide_floor",
                measurement=measurement,
                proposal="incumbent",
                selected=True,
                source=str(path),
                fits=record["fits"],
                reused=bool(record.get("reused_from")),
            )
    for path in sorted((OUTPUT / "priors").glob("*/*/attempts.json")):
        case, mode = path.parent.parent.name, path.parent.name
        chosen = json.loads((path.parent / "selected.json").read_text())
        for key, record in json.loads(path.read_text()).items():
            measurement, proposal = key.split("/")
            yield dict(
                kind="prior",
                case=case,
                method="receiver_smooth",
                mode=mode,
                measurement=measurement,
                proposal=proposal,
                selected=chosen[measurement]["selected_proposal"] == key,
                source=str(path),
                fits=record["fits"],
                reused=False,
            )
    for path in sorted((OUTPUT / "common_clock").glob("*/*/endpoints.json")):
        case, mode = path.parent.parent.name, path.parent.name
        for key, record in json.loads(path.read_text()).items():
            measurement, clock = key.split("/")
            yield dict(
                kind="clock",
                case=case,
                method="receiver_smooth",
                mode=mode,
                measurement=measurement,
                proposal=clock,
                selected=True,
                source=str(path),
                fits=record["fits"],
                reused=False,
            )
    for path in sorted((OUTPUT / "identity_iterations").glob("*/rounds.json")):
        case = path.parent.name
        for record in json.loads(path.read_text()):
            for name, attempt in record["attempts"].items():
                if attempt.get("reused_from"):
                    continue
                yield dict(
                    kind="identity",
                    case=case,
                    method="receiver_smooth",
                    mode="point_mixture",
                    measurement="glrt300",
                    proposal=f"round{record['iteration']}/{name}",
                    selected=False,
                    source=str(path),
                    fits=attempt["fits"],
                    reused=False,
                )


def factory_for(item, fit, pairs):
    if item["kind"] == "identity":
        protocol = json.loads(
            (OUTPUT / "identity_iterations" / item["case"] / "protocol.json").read_text()
        )
        allowed = {tuple(p) for p in protocol["fixed_pair_observation_ids"]}
        pairs = [p for p in pairs if tuple(p["observation_ids"]) in allowed]

    def factory(*args):
        if item["kind"] == "parent":
            p = geometry_problem(*args, mean_sigma=10, height_sigma=0)
        elif item["kind"] == "clock":
            clock = json.loads((OUTPUT / "clock_brackets.json").read_text())[item["case"]]
            p = clock_problem(
                *args,
                kind=item["mode"],
                clock=clock,
                pairs=pairs,
                enabled=item["proposal"] == "clock1",
            )
        else:
            p = transfer_problem(*args, pairs=pairs, mode=item["mode"])
        lock_aliases(p, fit["aliases"])
        return p

    return factory


def pair_audit(scan, fit, pairs, method):
    lookup = {
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
                * (scan.rx_basis[i] @ np.asarray(state["smooth"][t["receiver"] - 1]))
            )
        hardware.append(h)
    residuals = []
    agreeing_residuals = []
    agree = 0
    for p in pairs:
        if not p["frame_coherent"] or not p["both_original_curved"]:
            continue
        indices = [lookup[o] for o in p["observation_ids"]]
        values = [scan.tracks[i]["values"][k] - hardware[i][k] for i, k in indices]
        period = 1 / 4.4e-6
        residuals.append((values[0] - values[1] + period / 2) % period - period / 2)
        same_label = (
            labels[scan.tracks[indices[0][0]]["key"]] == labels[scan.tracks[indices[1][0]]["key"]]
        )
        agree += same_label
        if same_label:
            agreeing_residuals.append(residuals[-1])
    r = np.asarray(residuals)
    return dict(
        pairs=len(r),
        same_label_pairs=int(agree),
        same_label_rms_hz=(
            float(np.sqrt(np.mean(np.square(agreeing_residuals)))) if agreeing_residuals else None
        ),
        rms_hz=float(np.sqrt(np.mean(r * r))),
        centered_rms_hz=float(np.std(r)),
    )


def point_information(problem, parameters):
    p = problem
    x = np.asarray(parameters)
    while hasattr(p, "problem"):
        if isinstance(p, ReceiverDriftProblem):
            x = p.native_parameters(x)
        p = p.problem
    if not isinstance(p, PointMixtureFamilies):
        return None
    state = p.decode(x)
    f, _ = p.predicted(x)
    values = np.concatenate(
        [p.scan.tracks[i]["values"] + a / 4.4e-6 for i, a in zip(p.members, p.alias, strict=True)]
    )
    raw = (
        values
        - p.hardware_design @ state["beta"]
        - p.flat_rf * f
        - p.smooth_design @ state["smooth"].ravel()
    )
    common = (
        raw[p.common_left] + np.where(p.common_right >= 0, raw[np.maximum(0, p.common_right)], 0)
    ) * p.common_factor
    result = grouped_mixture_profile(common, p.constant_design, p.common_groups, p.group_count)
    gamma = result["signal_probability"]
    weights = np.empty(len(raw))
    weights[p.common_left] = gamma
    paired = p.common_right >= 0
    weights[p.common_right[paired]] = gamma[paired]
    tracks = []
    for i, sl in zip(p.members, p.slices, strict=True):
        t = p.scan.tracks[i]
        w = weights[sl]
        tt = t["times"]
        y = t["values"]
        a = np.column_stack((np.ones(len(tt)), (tt - tt.mean()) / max(1, np.ptp(tt))))
        beta = np.linalg.lstsq(a * np.sqrt(w[:, None]), y * np.sqrt(w), rcond=None)[0]
        curvature = float(np.sqrt(np.sum(w * (y - a @ beta) ** 2) / max(w.sum(), 1e-20)))
        tracks.append(
            dict(
                component=t["key"],
                weighted_affine_residual_rms_hz=curvature,
                effective_signal_points=float(w.sum() ** 2 / max(w @ w, 1e-20)),
                sum_signal_weight=float(w.sum()),
            )
        )
    return dict(
        common_coordinates=len(gamma),
        broad_coordinate_fraction=float(np.mean(gamma < 0.5)),
        mean_common_signal_responsibility=float(np.mean(gamma)),
        original_curves=len(tracks),
        weighted_curvature_below250_with12_signal_weight=sum(
            r["weighted_affine_residual_rms_hz"] < 250 and r["sum_signal_weight"] >= 12
            for r in tracks
        ),
        tracks=tracks,
    )


def run():
    items = list(records())
    summary = []
    details = {}
    ablations = []
    bindings = {}
    objective_checks = []
    final = {}
    for case in CASES:
        p = OUTPUT / "identity_iterations" / case / "selected.json"
        if p.exists():
            final[case] = {a: fingerprint(f) for a, f in json.loads(p.read_text())["fits"].items()}
    scans = {}
    pair_data = {}
    radio_noise = {}
    scores = json.loads(
        (OUTPUT.parent / "2026_10_18_dsx01_causal_repairs/glrt_scores.json").read_text()
    )
    for case in CASES:
        points = json.loads(measurement_path(case).read_text())["points"]
        pair_data[case] = read_pairs(case)[0]
        for measurement in MEASUREMENTS:
            scan = Scan(case)
            metadata = apply_measurements(scan, points, measurement)
            scans[case, measurement] = scan
            _, squares = variance_samples(scan, scores[case]["scores"])
            radio_noise[case + "/" + measurement] = dict(
                measurement_metadata=metadata,
                polynomial_leverage_corrected_rms_hz=float(np.sqrt(np.mean(squares))),
            )
    for n, item in enumerate(items):
        case = item["case"]
        scan = scans[case, item["measurement"]]
        fits = item["fits"]
        assert (
            fits["c0"]["rows"] == fits["fitted_c"]["rows"]
            and fits["c0"]["aliases"] == fits["fitted_c"]["aliases"]
            and fits["c0"]["starts"] == fits["fitted_c"]["starts"]
        )
        bindings[item["source"]] = hashlib.sha256(Path(item["source"]).read_bytes()).hexdigest()
        key = "/".join(
            [item[k] for k in ["kind", "case", "method", "mode", "measurement", "proposal"]]
        )
        pair_metrics = {}
        for arm, fit in fits.items():
            factory = factory_for(item, fit, pair_data[case])
            metrics = nominated_metrics(
                scan, dict(fit=fit, method=item["method"], arm=arm), problem_factory=factory
            )
            p = factory(
                scan,
                dict(rows=fit["rows"], state=fit["state"]),
                item["method"],
                arm == "fitted_c",
                fit["east_north_km"],
            )
            x = np.asarray(min(fit["fits"], key=lambda r: r["score"])["parameters"])
            residual = p.residual(x)
            actual = float(residual @ residual)
            assert abs(actual - fit["frequency_prior_score"]) < 1e-5, (
                key,
                arm,
                actual,
                fit["frequency_prior_score"],
            )
            audit = pair_audit(scan, fit, pair_data[case], item["method"])
            information = point_information(p, x)
            pair_metrics[arm] = metrics
            accepted = [r for r in metrics["tracks"] if r["compatible"]]
            detail = dict(metrics=metrics, pair_audit=audit, point_information=information)
            details[key + "/" + arm] = detail
            summary.append(
                dict(
                    **{
                        k: item[k]
                        for k in [
                            "kind",
                            "case",
                            "method",
                            "mode",
                            "measurement",
                            "proposal",
                            "selected",
                            "reused",
                        ]
                    },
                    arm=arm,
                    identity_final=final.get(case, {}).get(arm) == fingerprint(fit),
                    position_error_km=distance_km(
                        (fit["latitude_deg"], fit["longitude_deg"]), REFERENCE
                    ),
                    frequency_prior_score=fit["frequency_prior_score"],
                    total_score=fit["score"],
                    accepted_nominated_curved_points=metrics["accepted_nominated_curved_points"],
                    accepted_curves=len(accepted),
                    native_rms_hz=metrics["accepted_native_rms_hz"],
                    innovation_rms_hz=metrics["accepted_innovation_rms_hz"],
                    pair_residual_rms_hz=audit["rms_hz"],
                    pair_same_label_points=audit["same_label_pairs"],
                    fitted_common_UTC_shift_s=fit["state"].get("common_utc_shift_s", 0),
                    broad_coordinate_fraction=information["broad_coordinate_fraction"]
                    if information
                    else None,
                    weighted_curvature_below250=information[
                        "weighted_curvature_below250_with12_signal_weight"
                    ]
                    if information
                    else None,
                )
            )
            objective_checks.append(
                dict(key=key + "/" + arm, absolute_error=abs(actual - fit["frequency_prior_score"]))
            )
        a, b = [
            {r["component"]: r for r in pair_metrics[arm]["tracks"] if r["compatible"]}
            for arm in ["c0", "fitted_c"]
        ]
        common = a.keys() & b.keys()
        count = sum(a[k]["points"] for k in common)
        ablations.append(
            dict(
                key=key,
                common_points=count,
                same_label_points=sum(
                    a[k]["points"] for k in common if a[k]["norad"] == b[k]["norad"]
                ),
                native_rms_c0_hz=float(
                    np.sqrt(sum(a[k]["native_square_hz2"] for k in common) / max(count, 1))
                ),
                native_rms_fitted_c_hz=float(
                    np.sqrt(sum(b[k]["native_square_hz2"] for k in common) / max(count, 1))
                ),
            )
        )
        if n % 20 == 0:
            print(json.dumps(dict(evaluated_pairs=n + 1, total_pairs=len(items))), flush=True)
    write(OUTPUT / "evaluation_summary.json", summary)
    write(OUTPUT / "frequency_details.json", details)
    write(OUTPUT / "c_ablation.json", ablations)
    write(OUTPUT / "evaluation_bindings.json", bindings)
    write(OUTPUT / "radio_noise.json", radio_noise)
    write(OUTPUT / "objective_replay_checks.json", objective_checks)
    for name, rows in [("evaluation_summary", summary), ("c_ablation", ablations)]:
        with (OUTPUT / (name + ".csv")).open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    write(
        OUTPUT / "evaluation_validation.json",
        dict(
            evaluated_fit_records=len(summary),
            matched_c_pairs=len(ablations),
            new_fit_records=sum(not r["reused"] for r in summary),
            reused_fit_records=sum(r["reused"] for r in summary),
            all_objectives_recomputed=True,
            matched_c_nominations_aliases_starts=True,
            total_original_curved_points=12724,
            new_remeasured_points=10365,
            GPS_reporting_only=True,
            uniform_all_scan_sub1km_not_established=True,
        ),
    )
    plot(summary, radio_noise)
    print(json.dumps(dict(records=len(summary), matched_pairs=len(ablations))), flush=True)


def heat(ax, values, rows, title):
    matrix = np.asarray(values)
    image = ax.imshow(matrix, vmin=0, vmax=8, cmap="YlOrRd", aspect="auto")
    ax.set(
        xticks=range(5),
        xticklabels=[c[-3:] for c in CASES],
        yticks=range(len(rows)),
        yticklabels=rows,
        title=title,
    )
    for (r, c), v in np.ndenumerate(matrix):
        ax.text(
            c,
            r,
            f"{v:.3f}",
            ha="center",
            va="center",
            fontsize=8,
            color="white" if v > 4 else "black",
        )
    return image


def plot(summary, noise):
    plt.rcParams.update({"font.size": 9})
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, measurement in zip(axes, MEASUREMENTS, strict=True):
        values = [
            [
                next(
                    r["position_error_km"]
                    for r in summary
                    if r["kind"] == "parent"
                    and r["method"] == m
                    and r["case"] == c
                    and r["measurement"] == measurement
                    and r["arm"] == "fitted_c"
                )
                for c in CASES
            ]
            for m in METHODS
        ]
        im = heat(ax, values, METHODS, measurement + "; fitted c")
    fig.subplots_adjust(left=0.13, right=0.84, wspace=0.42)
    fig.colorbar(im, cax=fig.add_axes([0.9, 0.15, 0.015, 0.7]), label="Position error (km)")
    fig.savefig(OUTPUT / "parent_transfer_accuracy.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    for row, arm in enumerate(["c0", "fitted_c"]):
        for col, measurement in enumerate(MEASUREMENTS):
            values = [
                [
                    next(
                        r["position_error_km"]
                        for r in summary
                        if r["kind"] == "prior"
                        and r["selected"]
                        and r["mode"] == m
                        and r["case"] == c
                        and r["measurement"] == measurement
                        and r["arm"] == arm
                    )
                    for c in CASES
                ]
                for m in MODES
            ]
            im = heat(axes[row, col], values, MODES, measurement + "; " + arm)
    fig.subplots_adjust(left=0.12, right=0.84, hspace=0.35, wspace=0.45)
    fig.colorbar(im, cax=fig.add_axes([0.9, 0.15, 0.015, 0.7]), label="Position error (km)")
    fig.savefig(OUTPUT / "uniform_prior_accuracy.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    for k, kind in enumerate(["parents", "tight_pairs"]):
        for case in CASES:
            rows = {
                r["proposal"]: r
                for r in summary
                if r["kind"] == "clock"
                and r["mode"] == kind
                and r["case"] == case
                and r["measurement"] == "glrt300"
                and r["arm"] == "fitted_c"
            }
            if len(rows) == 2:
                axes[k].plot(
                    [0, 1],
                    [rows["clock0"]["position_error_km"], rows["clock1"]["position_error_km"]],
                    "o-",
                    label=case[-3:],
                )
        axes[k].axhline(1, color="gray", ls=":")
        axes[k].set(
            xticks=[0, 1],
            xticklabels=["Matched zero-clock", "Bounded common UTC"],
            ylabel="Position error (km)",
            title=kind,
        )
        axes[k].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUTPUT / "common_clock_effects.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    for case in CASES:
        before = next(
            r
            for r in summary
            if r["kind"] == "prior"
            and r["mode"] == "point_mixture"
            and r["selected"]
            and r["case"] == case
            and r["measurement"] == "glrt300"
            and r["arm"] == "fitted_c"
        )
        candidates = [
            r
            for r in summary
            if r["case"] == case and r["identity_final"] and r["arm"] == "fitted_c"
        ]
        after = candidates[-1] if candidates else before
        axes[0].plot(
            [0, 1], [before["position_error_km"], after["position_error_km"]], "o-", label=case[-3:]
        )
        axes[1].plot(
            [0, 1],
            [before["accepted_nominated_curved_points"], after["accepted_nominated_curved_points"]],
            "o-",
            label=case[-3:],
        )
    for ax in axes:
        ax.set(xticks=[0, 1], xticklabels=["Fixed labels", "EM-like final"])
        ax.legend(fontsize=8)
    axes[0].set_ylabel("Position error (km)")
    axes[0].axhline(1, color="gray", ls=":")
    axes[1].set_ylabel("Accepted nominated curved points")
    fig.tight_layout()
    fig.savefig(OUTPUT / "identity_iteration_effects.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    x = np.arange(5)
    for i, measurement in enumerate(MEASUREMENTS):
        axes[0].bar(
            x + (i - 0.5) * 0.35,
            [noise[c + "/" + measurement]["polynomial_leverage_corrected_rms_hz"] for c in CASES],
            width=0.35,
            label=measurement,
        )
    axes[0].set(
        xticks=x, xticklabels=[c[-3:] for c in CASES], ylabel="Radio polynomial residual scale (Hz)"
    )
    axes[0].legend()
    diagnostic = json.loads((OUTPUT / "radio_curvature_diagnostic.json").read_text())
    for i, measurement in enumerate(MEASUREMENTS):
        fraction = [
            sum(r["active_curvature"] for r in diagnostic[c + "/" + measurement])
            / len(diagnostic[c + "/" + measurement])
            for c in CASES
        ]
        axes[1].bar(x + (i - 0.5) * 0.35, fraction, width=0.35, label=measurement)
    axes[1].set(
        xticks=x,
        xticklabels=[c[-3:] for c in CASES],
        ylim=(0, 1.05),
        ylabel="Original curved tracks passing robust radio check",
    )
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(OUTPUT / "radio_measurement_transfer.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    run()
