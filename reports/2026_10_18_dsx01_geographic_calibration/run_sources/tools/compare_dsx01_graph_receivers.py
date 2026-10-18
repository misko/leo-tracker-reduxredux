"""Preliminary, label-free RX alignment of frozen DSX01 Graph tracklets."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from numpy.polynomial.legendre import legval

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "reports/2026_10_17_dsx01_all_scans_tracklets/graph"
OUTPUT = ROOT / "reports/2026_10_17_dsx01_graph_rx_alignment"
PERIOD = 1 / 4.4e-6
MIN_OVERLAP = 8.0
MIN_POINTS = 4
SHAPE_GATE = 300.0
MODE_RADIUS = 1500.0
ALIGNMENT_GATE = 450.0


def wrap(values):
    return (np.asarray(values) + PERIOD / 2) % PERIOD - PERIOD / 2


def predict(track, times):
    """Evaluate only inside existing pieces; never extrapolate across gaps."""
    times = np.asarray(times)
    values = np.full(times.shape, np.nan)
    for piece in track["pieces"]:
        mask = (times >= piece["start_s"]) & (times <= piece["end_s"])
        values[mask] = legval(
            (times[mask] - piece["reference_time_s"]) / piece["time_scale_s"],
            piece["coefficients_hz"],
        )
    return values


def load_tracks(directory=INPUT):
    tracks, hashes = [], {}
    for path in sorted(directory.glob("S*/recovered/results.json")):
        source = path.parent.parent.name
        summary = json.loads(path.read_text())
        assignments = path.with_name("assignments.csv")
        for p in (path, assignments):
            hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
        with assignments.open() as stream:
            rows = list(csv.DictReader(stream))
        for lane in summary["lanes"]:
            rx, channel = lane["receiver"], lane["channel"]
            for tid, original in enumerate(lane["tracks"]):
                members = [
                    r
                    for r in rows
                    if (int(r["receiver"]), int(r["channel"]), int(r["track_id"]))
                    == (rx, channel, tid)
                ]
                assert len(members) == len(original["indices"])
                order = np.argsort([float(r["time_s"]) for r in members])
                members = [members[i] for i in order]
                track = {
                    **original,
                    "source_id": source,
                    "receiver": rx,
                    "channel": channel,
                    "bank": "CH1-4" if channel <= 4 else "CH5-8",
                    "key": f"{source}-RX{rx}-CH{channel}-T{tid:03}",
                    "times": np.array([float(r["time_s"]) for r in members]),
                    "values": np.array(
                        [
                            float(r["measured_cfo_hz"]) + int(r["alias_lift"]) * PERIOD
                            for r in members
                        ]
                    ),
                    "observation_ids": [r["observation_id"] for r in members],
                    "rf_hz": float(members[0]["actual_rf_hz"]),
                }
                assert np.allclose(
                    track["values"] - predict(track, track["times"]),
                    [float(r["residual_hz"]) for r in members],
                    atol=1e-5,
                )
                tracks.append(track)
    assert len(tracks) == 676 and len({t["source_id"] for t in tracks}) == 5
    return tracks, hashes


def pair_tracks(left, right):
    if (left["source_id"], left["channel"], left["rf_hz"]) != (
        right["source_id"],
        right["channel"],
        right["rf_hz"],
    ):
        raise ValueError("Receiver pairs must share scan, channel and RF")
    lo = max(left["start_s"], right["start_s"])
    hi = min(left["end_s"], right["end_s"])
    if hi - lo < MIN_OVERLAP:
        return None
    inside = [t["times"][(t["times"] >= lo) & (t["times"] <= hi)] for t in (left, right)]
    if min(map(len, inside)) < MIN_POINTS:
        return None
    # Fixed quadrature samples describe fitted curves, not independent measurements.
    times = np.linspace(lo, hi, 129)
    delta = predict(right, times) - predict(left, times)
    valid = np.isfinite(delta)
    if valid.sum() < 65:
        return None
    times, delta = times[valid], delta[valid]
    delta = delta[0] + wrap(delta - delta[0])
    center = float(wrap(np.mean(delta)))
    delta = center + (delta - np.mean(delta))
    slope = float(np.polyfit(times - times.mean(), delta, 1)[0])
    return {
        "source_id": left["source_id"],
        "channel": left["channel"],
        "bank": left["bank"],
        "left_key": left["key"],
        "right_key": right["key"],
        "start_s": lo,
        "end_s": hi,
        "mid_s": float(times.mean()),
        "overlap_s": hi - lo,
        "left_overlap_points": len(inside[0]),
        "right_overlap_points": len(inside[1]),
        "offset_hz": center,
        "shape_rms_hz": float(np.std(delta)),
        "difference_slope_hz_s": slope,
        "both_supported": all(
            t["quality_status"] == "no_structure_detected" for t in (left, right)
        ),
        "times": times,
        "delta": delta,
    }


def candidates(tracks):
    groups = defaultdict(lambda: {1: [], 2: []})
    for track in tracks:
        groups[track["source_id"], track["channel"]][track["receiver"]].append(track)
    result = []
    for group in groups.values():
        for left in group[1]:
            for right in group[2]:
                pair = pair_tracks(left, right)
                if pair is not None:
                    result.append(pair)
    return result


def exclusive(pairs):
    """Conservative greedy one-to-one pairing; fragmented many-to-one is deferred."""
    used, kept = set(), []
    for pair in sorted(
        pairs, key=lambda p: (-p["overlap_s"], p["shape_rms_hz"], p["left_key"], p["right_key"])
    ):
        if pair["left_key"] not in used and pair["right_key"] not in used:
            kept.append(pair)
            used.update((pair["left_key"], pair["right_key"]))
    return kept


def modal_pairs(pairs, shape_gate=SHAPE_GATE):
    eligible = [p for p in pairs if p["shape_rms_hz"] <= shape_gate]
    if not eligible:
        return []
    proposals = []
    for seed in eligible:
        cluster = exclusive(
            [p for p in eligible if abs(wrap(p["offset_hz"] - seed["offset_hz"])) <= MODE_RADIUS]
        )
        proposals.append(cluster)
    return max(proposals, key=lambda group: (len(group), sum(p["overlap_s"] for p in group)))


def fit_group(pairs):
    """Equal pair weight; no pseudo-replication from quadrature samples."""
    x = np.array([p["mid_s"] - 150 for p in pairs])
    y = np.array([p["offset_hz"] for p in pairs])
    y = y[0] + wrap(y - y[0])
    constant = float(np.mean(y))
    if len(pairs) >= 3 and np.ptp(x) >= 30:
        intercept, slope = np.linalg.lstsq(np.column_stack((np.ones(len(x)), x)), y, rcond=None)[0]
    else:
        intercept, slope = constant, 0.0
    result = {
        "source_id": pairs[0]["source_id"],
        "bank": pairs[0]["bank"],
        "pairs": len(pairs),
        "channels": len({p["channel"] for p in pairs}),
        "both_supported_pairs": sum(p["both_supported"] for p in pairs),
        "constant_hz": constant,
        "affine_at_150s_hz": float(intercept),
        "affine_slope_hz_s": float(slope),
        "center_rms_constant_hz": float(np.sqrt(np.mean((y - constant) ** 2))),
        "center_rms_affine_hz": float(np.sqrt(np.mean((y - intercept - slope * x) ** 2))),
        "time_span_s": float(np.ptp(x)),
        "calibration_supported": len(pairs) >= 3 and len({p["channel"] for p in pairs}) >= 2,
    }
    const_ok, affine_ok = 0, 0
    for pair in pairs:
        t, delta = pair["times"], pair["delta"]
        pair["constant_rms_hz"] = float(np.sqrt(np.mean(wrap(delta - constant) ** 2)))
        pair["affine_rms_hz"] = float(
            np.sqrt(np.mean(wrap(delta - intercept - slope * (t - 150)) ** 2))
        )
        pair["constant_hz"] = constant
        pair["affine_at_150s_hz"] = float(intercept)
        pair["affine_slope_hz_s"] = float(slope)
        const_ok += pair["constant_rms_hz"] <= ALIGNMENT_GATE
        affine_ok += pair["affine_rms_hz"] <= ALIGNMENT_GATE
    result.update(constant_pairs_rms_le_450=const_ok, affine_pairs_rms_le_450=affine_ok)
    return result


def analyze(pairs, shape_gate=SHAPE_GATE):
    groups = defaultdict(list)
    for pair in pairs:
        groups[pair["source_id"], pair["bank"]].append(pair)
    fits, selected = [], []
    for _, group in sorted(groups.items()):
        matched = modal_pairs(group, shape_gate)
        if matched:
            fits.append(fit_group(matched))
            selected.extend(matched)
    return fits, selected


def shifted_receivers(tracks, shift_s=0, reverse=False):
    """Destroy simultaneous alignment while preserving each RX2 curve and samples."""
    output = [t for t in tracks if t["receiver"] == 1]
    for original in tracks:
        if original["receiver"] != 2:
            continue
        if reverse:
            track = copy.deepcopy(original)
            track["times"] = 300 - original["times"]
            track["start_s"], track["end_s"] = 300 - original["end_s"], 300 - original["start_s"]
            for piece in track["pieces"]:
                piece["start_s"], piece["end_s"] = 300 - piece["end_s"], 300 - piece["start_s"]
                piece["reference_time_s"] = 300 - piece["reference_time_s"]
                piece["coefficients_hz"] = [
                    c * (-1) ** i for i, c in enumerate(piece["coefficients_hz"])
                ]
            output.append(track)
            continue
        for amount in (shift_s, shift_s - 300):
            times = original["times"] + amount
            valid = (times >= 0) & (times < 300)
            if not valid.any():
                continue
            track = copy.deepcopy(original)
            track["times"] = times[valid]
            track["values"] = original["values"][valid]
            track["observation_ids"] = [
                o for o, keep in zip(original["observation_ids"], valid, strict=True) if keep
            ]
            track["start_s"] = max(0, original["start_s"] + amount)
            track["end_s"] = min(300, original["end_s"] + amount)
            pieces = []
            for piece in track["pieces"]:
                piece["start_s"] = max(0, piece["start_s"] + amount)
                piece["end_s"] = min(300, piece["end_s"] + amount)
                piece["reference_time_s"] += amount
                if piece["end_s"] > piece["start_s"]:
                    pieces.append(piece)
            track["pieces"] = pieces
            output.append(track)
    return output


def write_csv(path, rows):
    rows = [{k: v for k, v in r.items() if not isinstance(v, np.ndarray)} for r in rows]
    with path.open("w", newline="") as stream:
        fields = list(dict.fromkeys(k for row in rows for k in row))
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def save_figure(fig, output, name):
    fig.savefig(output / f"{name}.png", dpi=150, bbox_inches="tight")
    fig.savefig(output / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


def plot_offsets(pairs, fits, output):
    fig = plt.figure(figsize=(14, 12), constrained_layout=True)
    grid = fig.add_gridspec(3, 2)
    ax = fig.add_subplot(grid[0, :])
    selected = {(p["left_key"], p["right_key"]) for p in pairs}
    for index, source in enumerate(f"S{i:02}" for i in range(1, 6)):
        for bank, color, marker in (("CH1-4", "#276fa4", "o"), ("CH5-8", "#cc7933", "^")):
            group = [p for p in pairs if p["source_id"] == source and p["bank"] == bank]
            ax.scatter(
                [index + (p["mid_s"] - 150) / 800 for p in group],
                [p["offset_hz"] / 1000 for p in group],
                c=color,
                marker=marker,
                s=[25 + p["overlap_s"] for p in group],
                alpha=0.8,
                label=bank if index == 0 else None,
            )
    ax.set(
        xticks=range(5),
        xticklabels=[f"S{i:02}" for i in range(1, 6)],
        ylabel="RX2 − RX1 offset (kHz)",
        title=f"{len(selected)} shape-compatible, exclusive candidate pairs · modal groups only",
    )
    ax.legend(loc="upper right")
    ax.grid(alpha=0.2)
    for index, source in enumerate(("S01", "S03", "S04", "S05")):
        ax = fig.add_subplot(grid[1 + index // 2, index % 2])
        group = [p for p in pairs if p["source_id"] == source and p["bank"] == "CH1-4"]
        fit = next(f for f in fits if f["source_id"] == source and f["bank"] == "CH1-4")
        for p in group:
            ax.plot(p["times"], p["delta"] / 1000, color="#276fa4", alpha=0.35, lw=1)
            ax.scatter(p["mid_s"], p["offset_hz"] / 1000, color="#276fa4", s=25)
        t = np.array([0, 300])
        ax.axhline(fit["constant_hz"] / 1000, color="#656565", linestyle="--", label="Constant")
        ax.plot(
            t,
            (fit["affine_at_150s_hz"] + fit["affine_slope_hz_s"] * (t - 150)) / 1000,
            color="#c24539",
            label="Linear drift",
        )
        ax.set(
            title=f"{source} CH1–4 · drift {fit['affine_slope_hz_s']:+.2f} Hz/s",
            xlabel="Seconds into scan",
            ylabel="RX2 − RX1 (kHz)",
            xlim=(0, 300),
        )
        ax.grid(alpha=0.2)
        if index == 0:
            ax.legend()
    fig.suptitle(
        "DSX01 Graph tracklets: local offset agreement does not imply one constant calibration\n"
        "Same-channel comparisons; alias period 227.273 kHz; no extrapolation or satellite labels",
        fontsize=14,
    )
    save_figure(fig, output, "receiver-offsets")


def plot_examples(tracks, pairs, output):
    mapping = {t["key"]: t for t in tracks}
    examples = []
    for source, bank in (("S01", "CH5-8"), ("S03", "CH1-4"), ("S05", "CH1-4")):
        group = [
            p
            for p in pairs
            if p["source_id"] == source and p["bank"] == bank and p["both_supported"]
        ]
        examples.append(max(group, key=lambda p: p["overlap_s"]))
    fig, axes = plt.subplots(3, 3, figsize=(16, 11), constrained_layout=True)
    for row, pair in enumerate(examples):
        left, right = mapping[pair["left_key"]], mapping[pair["right_key"]]
        t = pair["times"]
        # Integer lift is unidentifiable; use the same lift in all three panels.
        lift = (
            round((predict(left, t)[0] + pair["offset_hz"] - predict(right, t)[0]) / PERIOD)
            * PERIOD
        )
        for col, mode in enumerate(
            ("Before receiver correction", "Scan/bank constant", "Scan/bank linear drift")
        ):
            ax = axes[row, col]
            for track, color, label in ((left, "#276fa4", "RX1"), (right, "#d47d2c", "RX2")):
                times = track["times"]
                m = (times >= pair["start_s"]) & (times <= pair["end_s"])
                x, y = times[m], track["values"][m].copy()
                curve = predict(track, t)
                if track["receiver"] == 2:
                    y += lift
                    curve += lift
                    if col == 1:
                        y -= pair["constant_hz"]
                        curve -= pair["constant_hz"]
                    if col == 2:
                        y -= pair["affine_at_150s_hz"] + pair["affine_slope_hz_s"] * (x - 150)
                        curve -= pair["affine_at_150s_hz"] + pair["affine_slope_hz_s"] * (t - 150)
                ax.scatter(x, y / 1000, s=18, color=color, label=label, alpha=0.8)
                ax.plot(t, curve / 1000, color=color, lw=1.2)
            rms_key = "constant_rms_hz" if col == 1 else "affine_rms_hz"
            subtitle = "" if col == 0 else f" · curve mismatch RMS {pair[rms_key]:.0f} Hz"
            ax.set(title=mode + subtitle, xlabel="Seconds into scan", ylabel="Lifted CFO (kHz)")
            ax.grid(alpha=0.2)
            if col == 0:
                ax.text(
                    0.02,
                    0.98,
                    f"{pair['source_id']} · CH{pair['channel']}\n"
                    f"{pair['left_key'].split('-')[-1]} / {pair['right_key'].split('-')[-1]}",
                    transform=ax.transAxes,
                    va="top",
                    fontsize=9,
                )
                ax.legend(loc="lower left")
        # Common y range for before/after panels within each example.
        lower = min(ax.get_ylim()[0] for ax in axes[row])
        upper = max(ax.get_ylim()[1] for ax in axes[row])
        for ax in axes[row]:
            ax.set_ylim(lower, upper)
    fig.suptitle(
        "Can RX1 and RX2 tracklets be united? Three illustrative, same-channel candidate pairs\n"
        "Dots = original GLRT observations; lines = frozen fits; "
        "correction learned across each scan/bank",
        fontsize=14,
    )
    save_figure(fig, output, "receiver-alignment-examples")
    fig, axes = plt.subplots(3, 2, figsize=(13, 10), constrained_layout=True)
    for row, pair in enumerate(examples):
        t = pair["times"]
        for col, mode in enumerate(("Constant correction", "Linear drift correction")):
            ax = axes[row, col]
            correction = (
                pair["constant_hz"]
                if col == 0
                else (pair["affine_at_150s_hz"] + pair["affine_slope_hz_s"] * (t - 150))
            )
            error = wrap(pair["delta"] - correction)
            ax.plot(t, error, color="#276fa4", lw=1.6)
            ax.axhline(0, color="#555555", lw=0.8)
            ax.axhspan(-ALIGNMENT_GATE, ALIGNMENT_GATE, color="#6aac78", alpha=0.12)
            ax.set(
                title=f"{pair['source_id']} CH{pair['channel']} · {mode}",
                xlabel="Seconds into scan",
                ylabel="Corrected RX2 fit − RX1 fit (Hz)",
            )
            ax.grid(alpha=0.2)
        limits = [ax.get_ylim() for ax in axes[row]]
        limit = max(abs(value) for pair_limits in limits for value in pair_limits)
        for ax in axes[row]:
            ax.set_ylim(-limit, limit)
    fig.suptitle(
        "Alignment differences on a Hz scale\n"
        "Fitted-curve differences, not independent noise samples; green = ±450 Hz reference",
        fontsize=14,
    )
    save_figure(fig, output, "receiver-alignment-differences")
    return [{k: v for k, v in p.items() if not isinstance(v, np.ndarray)} for p in examples]


def model_comparison(pairs, fits):
    """Compare nested descriptions on the same selected candidate pairs."""
    result = []
    for family in (
        "Global constant",
        "Constant per scan",
        "Constant per scan/bank",
        "Linear per scan/bank",
    ):
        buckets = defaultdict(list)
        for p in pairs:
            key = "all" if family == "Global constant" else p["source_id"]
            if "bank" in family:
                key = (p["source_id"], p["bank"])
            buckets[key].append(p)
        errors, center_errors, passing, parameters = [], [], 0, 0
        for group in buckets.values():
            if family == "Linear per scan/bank":
                f = next(
                    f
                    for f in fits
                    if (f["source_id"], f["bank"]) == (group[0]["source_id"], group[0]["bank"])
                )
                intercept, slope = f["affine_at_150s_hz"], f["affine_slope_hz_s"]
                parameters += 2 if len(group) >= 3 and f["time_span_s"] >= 30 else 1
            else:
                centers = np.array([p["offset_hz"] for p in group])
                intercept = centers[0] + np.mean(wrap(centers - centers[0]))
                slope = 0.0
                parameters += 1
            for p in group:
                e = wrap(p["delta"] - intercept - slope * (p["times"] - 150))
                errors.append(np.mean(e**2))
                center_errors.append(
                    float(wrap(p["offset_hz"] - intercept - slope * (p["mid_s"] - 150))) ** 2
                )
                passing += np.sqrt(np.mean(e**2)) <= ALIGNMENT_GATE
        result.append(
            {
                "model": family,
                "pairs": len(pairs),
                "parameters": parameters,
                "equal_pair_weight_curve_rms_hz": float(np.sqrt(np.mean(errors))),
                "pair_center_rms_hz": float(np.sqrt(np.mean(center_errors))),
                "pairs_curve_rms_le_450": int(passing),
            }
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    tracks, hashes = load_tracks()
    all_pairs = candidates(tracks)
    fits, pairs = analyze(all_pairs)
    write_csv(output / "all-overlapping-pairs.csv", all_pairs)
    write_csv(output / "selected-pairs.csv", pairs)
    write_csv(output / "offset-models.csv", fits)
    comparison = model_comparison(pairs, fits)
    write_csv(output / "correction-model-comparison.csv", comparison)
    supported_only = []
    for f in fits:
        subset = [
            p.copy()
            for p in pairs
            if p["source_id"] == f["source_id"] and p["bank"] == f["bank"] and p["both_supported"]
        ]
        if subset:
            supported_only.append(fit_group(subset))
    write_csv(output / "supported-track-sensitivity.csv", supported_only)
    controls = []
    for shift in (57, 113, 179):
        c = candidates(shifted_receivers(tracks, shift_s=shift))
        cf, cp = analyze(c)
        controls.append(
            {
                "control": f"RX2 circular shift {shift}s",
                "overlapping_pairs": len(c),
                "shape_compatible_pairs": sum(p["shape_rms_hz"] <= SHAPE_GATE for p in c),
                "modal_exclusive_pairs": len(cp),
                "groups_with_multi_channel_support": sum(f["calibration_supported"] for f in cf),
            }
        )
    c = candidates(shifted_receivers(tracks, reverse=True))
    cf, cp = analyze(c)
    controls.append(
        {
            "control": "RX2 time reversed",
            "overlapping_pairs": len(c),
            "shape_compatible_pairs": sum(p["shape_rms_hz"] <= SHAPE_GATE for p in c),
            "modal_exclusive_pairs": len(cp),
            "groups_with_multi_channel_support": sum(f["calibration_supported"] for f in cf),
        }
    )
    write_csv(output / "temporal-controls.csv", controls)
    sensitivity = []
    for gate in (150.0, 300.0, 450.0):
        fs, ps = analyze(copy.deepcopy(all_pairs), shape_gate=gate)
        for f in fs:
            sensitivity.append({"shape_gate_hz": gate, **f})
    write_csv(output / "shape-gate-sensitivity.csv", sensitivity)
    # Restore the primary model values after sensitivity fits mutate pair annotations.
    fits, pairs = analyze(all_pairs)
    plot_offsets(pairs, fits, output)
    examples = plot_examples(tracks, pairs, output)
    for path, expected in hashes.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    result = {
        "method": "Frozen Graph + shared recovery",
        "input_tracks": len(tracks),
        "overlapping_pairs": len(all_pairs),
        "shape_compatible_pairs": sum(p["shape_rms_hz"] <= SHAPE_GATE for p in all_pairs),
        "modal_exclusive_pairs": len(pairs),
        "groups": fits,
        "model_comparison": comparison,
        "controls": controls,
        "examples": examples,
        "parameters": {
            "alias_period_hz": PERIOD,
            "min_overlap_s": MIN_OVERLAP,
            "min_observations_per_rx_in_overlap": MIN_POINTS,
            "shape_rms_gate_hz": SHAPE_GATE,
            "modal_radius_hz": MODE_RADIUS,
            "curve_alignment_rms_gate_hz": ALIGNMENT_GATE,
        },
        "input_sha256": hashes,
        "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "interpretation": (
            "Exploratory candidate alignment, not identity validation or production merging; "
            "offsets modulo alias period. Equal pair weights, quadrature samples not independent "
            "data. CH1-4/CH5-8 is a descriptive frequency grouping, "
            "not an established hardware mechanism."
        ),
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k
                in (
                    "input_tracks",
                    "overlapping_pairs",
                    "shape_compatible_pairs",
                    "modal_exclusive_pairs",
                    "groups",
                    "controls",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
