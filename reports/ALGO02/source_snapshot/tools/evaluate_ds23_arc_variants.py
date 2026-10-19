"""Compare three conditional multi-peak association prototypes on two saved scans."""

import argparse
import json
import time
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from associate_merged_track_catalogue import write
from evaluate_ds23_phase_refreshed import FreshScan
from investigate_ds23_visible_arcs import SOURCE, frozen
from prototype_dsx01_continuous_position import latlon

from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
from leo.analysis.research.visible_arc_variants import (
    deduplicate,
    em_association,
    frequency,
    graph_proposals,
    greedy_repair,
    joint_selection,
    make_hypotheses,
    wrap,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/2026_10_18_ds23_arc_variants"
CASES = {"DS23-0342": (2, 60.0, 140.0), "DS23-0039": (1, 134.0, 240.0)}


def read(path):
    return json.loads(path.read_text())


def prepare(case, arm):
    channel, lo, hi = CASES[case]
    document = read(SOURCE / case / "tracking.json")
    anchor = document["timing"]["session_start_device_sample_counter"]
    raw = []
    for number, probe in enumerate(document["probes"]):
        t = (probe["valid_start_counter"] - anchor) / document["sample_rate_hz"] + document[
            "probe_ms"
        ] / 2000
        if probe["receiver_id"] != 0 or probe["channel"] != channel or not lo <= t <= hi:
            continue
        for c in probe["candidates"]:
            if c["passed_fractional_margin_gate"]:
                raw.append(
                    dict(
                        time_s=t,
                        probe=number,
                        cfo_hz=c["fractional_tracking_cfo_hz"],
                        margin=c["fractional_margin"],
                        rank=c["candidate_rank"],
                    )
                )
    representatives, clusters = deduplicate(
        [p["cfo_hz"] for p in raw], [p["margin"] for p in raw], [p["probe"] for p in raw]
    )
    candidates = [dict(raw[i], cluster_members=clusters[k]) for k, i in enumerate(representatives)]
    candidates.sort(key=lambda p: (p["time_s"], float(wrap(p["cfo_hz"]))))
    scan = FreshScan(SOURCE / case, noise_mode="radio")
    calibration = frozen(case, arm)
    t = np.array([p["time_s"] for p in candidates])
    rf = next(
        o["actual_rf_hz"]
        for o in read(SOURCE / case / "observations.json")
        if o["receiver"] == 1 and o["channel"] == channel
    )
    dummy = dict(receiver=1, channel=channel, times=t, rf_hz=rf, bank="CH1-4")
    radio = scan.hardware(dummy, np.array(calibration["state"]["beta"]))
    radio += rf / 11.5e9 * projected_receiver_basis(t) @ np.array(calibration["state"]["smooth"])[0]
    probes = np.array([p["probe"] for p in candidates])
    margin = np.array([p["margin"] for p in candidates])
    quality = margin.copy()
    for p in np.unique(probes):
        mask = probes == p
        quality[mask] /= max(margin[mask])
    data = dict(
        times=t,
        values=wrap(np.array([p["cfo_hz"] for p in candidates]) - radio),
        probes=probes,
        quality=quality,
        radio_hz=radio,
        rf_hz=rf,
        sigma=scan.radio_sigma_hz,
        site=latlon(calibration["endpoint"]),
    )
    geometry = prepare_phase_geometry(scan.sky, t)
    nominal, elevation, derivative = phase_linear_frequency(geometry, *data["site"], rf_hz=rf)
    winners = []
    for p in np.unique(probes):
        ix = np.flatnonzero(probes == p)
        winners.append(int(ix[np.argmax(margin[ix])]))
    return scan, data, candidates, np.asarray(winners), nominal, derivative, elevation, calibration


def describe(result, scan, data, candidates, winners):
    assigned = np.flatnonzero(result["assignment"] >= 0)
    for track in result["tracks"]:
        track["norad"] = int(scan.norads[track["candidate_index"]])
        ix = track["indices"]
        track["points"] = len(ix)
        track["start_s"] = float(min(data["times"][ix]))
        track["end_s"] = float(max(data["times"][ix]))
        track["winning_points"] = len(np.intersect1d(ix, winners))
        track["secondary_points"] = len(ix) - track["winning_points"]
        track["canonical_peak_ids"] = [
            f"p{candidates[i]['probe']}-r{candidates[i]['rank']}" for i in ix
        ]
    result["summary"] = dict(
        tracks=len(result["tracks"]),
        assigned_peaks=len(assigned),
        associated_winners=len(np.intersect1d(assigned, winners)),
        winning_probes=len(winners),
        associated_winner_percent=100 * len(np.intersect1d(assigned, winners)) / len(winners),
        secondary_peaks=len(assigned) - len(np.intersect1d(assigned, winners)),
        associated_probe_coverage=len(np.unique(data["probes"][assigned])),
        ambiguous_peaks=len(result["ambiguous_indices"]),
    )
    return result


def run(case, arm, allow_duplicates=False):
    OUT.mkdir(exist_ok=True)
    began = time.monotonic()
    scan, data, candidates, winners, nominal, derivative, elevation, calibration = prepare(
        case, arm
    )
    preparation_s = time.monotonic() - began
    print(
        case,
        arm,
        "canonical peaks",
        len(candidates),
        "probes",
        len(winners),
        "causal satellites",
        len(scan.norads),
        flush=True,
    )
    start = time.monotonic()
    paths = graph_proposals(data["times"], data["values"])
    hypotheses, attempts = make_hypotheses(scan.sky, data, nominal, derivative, elevation, paths)
    proposal_s = time.monotonic() - start
    print(
        case,
        arm,
        "hypotheses",
        len(hypotheses),
        "attempts",
        len(attempts),
        "proposal seconds",
        proposal_s,
        flush=True,
    )
    results = {}
    start = time.monotonic()
    results["greedy_graph_repair"] = describe(
        greedy_repair(scan.sky, data, hypotheses), scan, data, candidates, winners
    )
    results["greedy_graph_repair"]["selection_s"] = time.monotonic() - start
    start = time.monotonic()
    joint, pool, choices = joint_selection(
        scan.sky, data, hypotheses, duplicate_overlap=None if allow_duplicates else 0.6
    )
    results["joint_paths"] = describe(joint, scan, data, candidates, winners)
    results["joint_paths"]["selection_s"] = time.monotonic() - start
    print(case, arm, "joint selection", results["joint_paths"]["summary"], flush=True)
    start = time.monotonic()
    results["satellite_EM"] = describe(
        em_association(scan.sky, data, pool, choices), scan, data, candidates, winners
    )
    if "map_assignment_result" in results["satellite_EM"]:
        describe(results["satellite_EM"]["map_assignment_result"], scan, data, candidates, winners)
    results["satellite_EM"]["selection_s"] = time.monotonic() - start
    for name, result in results.items():
        print(case, arm, name, result["summary"], flush=True)
    write(
        OUT / f"{case}_{arm}{'_duplicate_ablation' if allow_duplicates else ''}.json",
        dict(
            case=case,
            arm=arm,
            candidates=candidates,
            winners=winners,
            times=data["times"],
            values=data["values"],
            radio_hz=data["radio_hz"],
            probes=data["probes"],
            quality=data["quality"],
            site=data["site"],
            rf_hz=data["rf_hz"],
            sigma_hz=data["sigma"],
            calibration_endpoint=calibration["endpoint"],
            all_causal_satellites=len(scan.norads),
            hypotheses=hypotheses,
            attempts=attempts,
            paths=paths,
            results=results,
            preparation_s=preparation_s,
            common_proposal_s=proposal_s,
            total_s=time.monotonic() - began,
            GPS_used=False,
            future_TLE_used=False,
            position_and_receiver_calibration_fixed=True,
            allow_duplicate_explanations=allow_duplicates,
            scope="Requested receiver/channel intervals; position is fixed.",
        ),
    )
    if not allow_duplicates:
        plot(case, arm, scan, data, candidates, winners, results)


def plot(case, arm, scan, data, candidates, winners, results):
    t = data["times"]
    raw = np.array([p["cfo_hz"] for p in candidates])
    # Same display-only affine subtraction across methods; no correction enters inference.
    b = np.polyfit(t[winners], raw[winners], 1)
    trend = np.polyval(b, t)
    original_results = results
    results = {
        name: (
            dict(result["map_assignment_result"], ambiguous_indices=result["ambiguous_indices"])
            if "map_assignment_result" in result
            else result
        )
        for name, result in results.items()
    }
    fig, axes = plt.subplots(3, 2, figsize=(16, 12), sharex=True)
    associated_display = []
    for row, (name, result) in enumerate(results.items()):
        ax, rx = axes[row]
        ax.scatter(t, (raw - trend) / 1000, c=".8", s=12, label="Other canonical GLRT peaks")
        ax.scatter(
            t[winners],
            (raw[winners] - trend[winners]) / 1000,
            facecolors="none",
            edgecolors="black",
            s=40,
            label="Original winning peaks",
        )
        for track in result["tracks"]:
            ix = np.asarray(track["indices"])
            pred = (
                frequency(
                    scan.sky,
                    track["candidate_index"],
                    t[ix],
                    track["orbit"]["parameters"],
                    data["site"],
                    data["rf_hz"],
                )
                + data["radio_hz"][ix]
            )
            display = pred + wrap(raw[ix] - pred)
            gauge = np.rint(np.median((raw[ix] - pred) / (1 / 4.4e-6))) * (1 / 4.4e-6)
            pred, display = pred + gauge, display + gauge
            associated_display.extend(((display - trend[ix]) / 1000).tolist())
            color = f"C{len(ax.lines) % 10}"
            ax.scatter(t[ix], (display - trend[ix]) / 1000, s=24, c=color)
            ax.plot(
                t[ix],
                (pred - trend[ix]) / 1000,
                c=color,
                label=f"{track['norad']}: {len(ix)} points",
            )
            rx.plot(
                t[ix],
                track["orbit"]["residual_hz"],
                ".-",
                c=color,
                label=f"{track['norad']}: {track['orbit']['rms_hz']:.0f} Hz RMS",
            )
        s = result["summary"]
        extra = (
            f"; {len(result['ambiguous_indices'])} lower-confidence assignments"
            if name == "satellite_EM"
            else ""
        )
        ax.set(
            title=f"{name}: {s['tracks']} tracks, {s['associated_winners']}/{len(winners)} winners "
            f"+ {s['secondary_peaks']} secondary peaks{extra}",
            ylabel="CFO minus common line (kHz)",
        )
        rx.set(title="Satellite residuals", ylabel="Residual (Hz)")
        for a in (ax, rx):
            a.grid(alpha=0.2)
            a.legend(fontsize=8, loc="best")
    lower, upper = (
        (min(associated_display), max(associated_display))
        if associated_display
        else (-110.0, 110.0)
    )
    pad = max(3.0, 0.12 * (upper - lower))
    for ax in axes[:, 0]:
        ax.set_ylim(lower - pad, upper + pad)
    axes[-1, 0].set_xlabel("Time since scan start (s)")
    axes[-1, 1].set_xlabel("Time since scan start (s)")
    fig.suptitle(
        f"{case} RX1 CH{CASES[case][0]}: multi-peak prototypes ({arm}); fixed RF-derived position"
    )
    fig.tight_layout()
    fig.savefig(OUT / f"{case}_{arm}.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(3, 1, figsize=(14, 11), sharex=True, sharey=True)
    for ax, (name, result) in zip(axes, original_results.items(), strict=True):
        assignment = np.asarray(result["assignment"])
        other = np.flatnonzero(assignment < 0)
        missing = np.intersect1d(other, winners)
        ax.scatter(t, wrap(raw - trend) / 1000, c=".85", s=14, label="Canonical peaks")
        ax.scatter(
            t[other],
            wrap(raw[other] - trend[other]) / 1000,
            c=".45",
            s=17,
            label="Unassociated canonical peaks",
        )
        ax.scatter(
            t[missing],
            wrap(raw[missing] - trend[missing]) / 1000,
            c="crimson",
            marker="x",
            s=45,
            label=f"Unassociated winners ({len(missing)})",
        )
        uncertain = np.asarray(result["ambiguous_indices"], int)
        if len(uncertain):
            ax.scatter(
                t[uncertain],
                wrap(raw[uncertain] - trend[uncertain]) / 1000,
                c="orange",
                marker="s",
                s=25,
                label="EM conditional posterior <0.8",
            )
        ax.set(title=name, ylabel="Circular CFO minus common line (kHz)")
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8, loc="best")
    axes[-1].set_xlabel("Time since scan start (s)")
    fig.suptitle(f"{case}: remaining GLRT evidence ({arm}); aliases folded for display")
    fig.tight_layout()
    fig.savefig(OUT / f"{case}_{arm}_unassociated.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=list(CASES), required=True)
    parser.add_argument("--arm", choices=["c0", "fitted_c"], required=True)
    parser.add_argument("--allow-duplicate-models", action="store_true")
    args = parser.parse_args()
    run(args.case, args.arm, args.allow_duplicate_models)
