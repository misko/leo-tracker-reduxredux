#!/usr/bin/env python3
"""Build paper figures from committed measurements; no RF collection or inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon

from leo.analysis.research.regional_doppler import Region

ROOT = Path(__file__).resolve().parents[1]
BASE = "e24387b0eedfde687cd8c4fab528c9ac56ec3387"
REPORT = Path("reports/2026_09_08_starlink_doppler_localization_paper.md")
OUTPUT = Path("reports/figures/2026_09_08_starlink_doppler_paper")
SYNTHESIS = Path("reports/figures/2026_09_07_continental_positioning_synthesis/metrics.json")
REGIONAL = Path("reports/figures/2026_09_07_blind_regional_pnt")
SCANS = Path("reports/figures/2026_09_07_eight_hour_scan_pnt")
BLUE, ORANGE, GREEN, RED = "#2463a5", "#bc6426", "#258477", "#ac3846"
FIGURES = (
    "01-measurement-chain.png",
    "02-waveform-and-pilot-evidence.png",
    "03-doppler-normalization-and-holdout.png",
    "04-recording-timeline-and-tracks.png",
    "05-geographic-search-and-position.png",
    "06-position-and-model-comparisons.png",
    "07-sample-rate-and-resolution.png",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def separation(a, b):
    lat, lon, lat0, lon0 = np.deg2rad(
        [a["latitude_deg"], a["longitude_deg"], b["latitude_deg"], b["longitude_deg"]]
    )
    h = math.sin((lat - lat0) / 2) ** 2
    h += math.cos(lat) * math.cos(lat0) * math.sin((lon - lon0) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1, h)))


def load_data(root=ROOT):
    inputs = {}

    def read(path):
        inputs[str(path)] = sha(root / path)
        return json.loads((root / path).read_text())

    metrics = read(SYNTHESIS)
    evaluation = read(REGIONAL / "evaluation-expanded.json")
    scans = [read(p.relative_to(root)) for p in sorted((root / SCANS / "results").glob("*.json"))]
    scans.sort(key=lambda r: r["inventory"]["reference_utc_ns"])
    first = read(SCANS / "evidence" / f"{scans[0]['session_id']}.json")
    last = read(SCANS / "evidence" / f"{scans[-1]['session_id']}.json")
    series = {r["tracklet_id"]: r for r in first["series"]}
    pairs = [
        (series[r["left_tracklet_id"]], series[r["right_tracklet_id"]])
        for r in first["edge_merges"]
    ]
    pair = max(
        pairs,
        key=lambda p: (
            min(max(p[0]["t_s"]), max(p[1]["t_s"])) - max(min(p[0]["t_s"]), min(p[1]["t_s"]))
        ),
    )
    final = next(
        r
        for r in evaluation["polishes"]
        if r["region_km"] == 5000 and r["fit_height"] and not r["fit_orbit_time"]
    )
    for row in evaluation["runs"] + evaluation["polishes"]:
        if not math.isclose(
            separation(row, evaluation["truth"]), row["horizontal_error_m"], abs_tol=1e-6
        ):
            raise ValueError("Published coordinate/error mismatch")
    land = read(REGIONAL / "natural-earth-110m-land.geojson")
    map_source = read(REGIONAL / "map-source.json")
    return {
        "metrics": metrics,
        "evaluation": evaluation,
        "scans": scans,
        "pair": pair,
        "pair_session": scans[0]["session_id"],
        "last": last,
        "final": final,
        "land": land,
        "map_source": map_source,
        "inputs": inputs,
    }


def save(fig, output, number):
    fig.savefig(output / FIGURES[number - 1], dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def measurement_chain(output):
    fig, ax = plt.subplots(figsize=(12, 5.2), layout="constrained")
    ax.set(xlim=(0, 12), ylim=(0, 5.4))
    ax.axis("off")
    nodes = [
        (0.15, 3.3, "Satellite emission\nKnown pilots / PSS\nChanging propagation range"),
        (3.15, 3.3, "LNB and radio\nDownconversion / filtering\nIQ and device timing"),
        (6.15, 3.3, "Pilot GLRT\nFrame timing / CFO\nFractional peak estimates"),
        (9.15, 3.3, "Doppler episodes\nResolve CFO ambiguity\nCombine compatible edges"),
        (9.15, 0.5, "Geographic search\nCompare candidate orbits\nRetain spatial alternatives"),
        (6.15, 0.5, "Local position fit\nTraining-selected identities\nSource frequency offsets"),
        (3.15, 0.5, "Position evaluation\nWithheld reference\nHorizontal error / controls"),
    ]
    for x, y, label in nodes:
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                2.65,
                1.15,
                boxstyle="round,pad=.05",
                facecolor="#edf3f6",
                edgecolor="#688294",
            )
        )
        ax.text(x + 1.325, y + 0.575, label, ha="center", va="center", fontsize=9)
    for a, b in zip(nodes[:-1], nodes[1:], strict=True):
        x, y, _ = a
        xx, yy, _ = b
        start, end = (
            ((x + 2.7, y + 0.575), (xx - 0.07, yy + 0.575))
            if xx > x
            else (
                ((x + 1.325, y - 0.05), (xx + 1.325, yy + 1.2))
                if yy < y
                else ((x - 0.07, y + 0.575), (xx + 2.7, yy + 0.575))
            )
        )
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=14, color=BLUE))
    ax.text(7.8, 2.15, "UTC + archived TLEs\nSGP4 satellite motion", ha="center", fontsize=9)
    ax.add_patch(
        FancyArrowPatch(
            (9.2, 2.15), (10.475, 2.15), arrowstyle="-|>", mutation_scale=14, color=BLUE
        )
    )
    ax.text(
        1.45,
        1.35,
        "PSS timing research\nSeparate observable;\nposition integration proposed",
        ha="center",
        fontsize=9,
        color=GREEN,
    )
    ax.set_title("Continental-search measurement and inference chain", pad=12)
    save(fig, output, 1)


def waveform(data, output):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2), layout="constrained")
    tones = np.array(
        [-820.3125, -585.9375, -351.5625, -117.1875, 117.1875, 351.5625, 585.9375, 820.3125]
    )
    axes[0].vlines(tones / 1000, 0, 1, color=BLUE, lw=2)
    axes[0].scatter(tones / 1000, np.ones(8), color=BLUE, s=20)
    axes[0].set(
        xlim=(-1.25, 1.25),
        ylim=(0, 1.7),
        yticks=[],
        xlabel="Offset from edge-band centre (MHz)",
        title="A · Known edge-pilot geometry (schematic)",
    )
    axes[0].text(0, 1.5, "8 tones · outermost separation 1.640625 MHz", ha="center", fontsize=9)
    axes[0].text(
        0,
        1.12,
        "300 known symbol positions per frame\n4.4 µs symbols · 750 frames/s",
        ha="center",
        fontsize=9,
    )
    quality = data["metrics"]["detector_quality_comparison"]
    for key, label, color in (
        ("prior", "26 Aug · CH3 lower", ORANGE),
        ("new", "27 Aug · CH4 lower", GREEN),
    ):
        rows = np.asarray(quality["glrt_time_bins"][key])
        axes[1].plot(rows[:, 0], rows[:, 1], color=color, label=label)
        axes[1].fill_between(rows[:, 0], rows[:, 2], rows[:, 3], color=color, alpha=0.15)
    axes[1].set(
        xlim=(0, 60),
        ylim=(0, 0.95),
        xlabel="Elapsed recording time (s)",
        ylabel="Exact-pilot score",
        title="B · Measured pilot detection at 5 MS/s",
    )
    axes[1].legend(fontsize=9)
    save(fig, output, 2)


def trajectories(data, output):
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), layout="constrained")
    for row, color in zip(data["pair"], (BLUE, ORANGE), strict=True):
        order = np.argsort(row["t_s"])
        t, y = np.asarray(row["t_s"])[order], np.asarray(row["y_hz"])[order]
        split = int(0.6 * len(t))
        centered = y - y[:split].mean()
        axes[0].plot(
            t,
            centered * row["actual_rf_hz"] / 11.2e9 / 1000,
            ".-",
            color=color,
            markersize=3,
            label=f"{row['edge']} · {row['actual_rf_hz'] / 1e9:.4f} GHz",
        )
        axes[1].plot(t, centered / 1000, ".-", color=color, markersize=3)
        axes[2].scatter(t[:split], centered[:split] / 1000, color=color, s=12)
        axes[2].scatter(t[split:], centered[split:] / 1000, edgecolor=color, facecolor="none", s=18)
        axes[2].axvline((t[split - 1] + t[split]) / 2, color=color, alpha=0.4)
    for ax, title in zip(
        axes,
        ("A · Actual RF", "B · Rescaled to 11.2 GHz", "C · Filled: training; hollow: held out"),
        strict=True,
    ):
        ax.set(xlabel="Time within scan (s)", ylabel="Offset-centred CFO (kHz)", title=title)
    axes[0].legend(fontsize=8)
    save(fig, output, 3)


def recordings(data, output):
    fig = plt.figure(figsize=(12, 8), layout="constrained")
    grid = fig.add_gridspec(3, 2, height_ratios=(0.65, 1, 1))
    timeline = fig.add_subplot(grid[0, :])
    for scan in data["scans"]:
        inv = scan["inventory"]
        rate = inv["sample_rate_hz"] / 1e6
        time = mdates.date2num(datetime.fromtimestamp(inv["reference_utc_ns"] / 1e9, UTC))
        timeline.broken_barh(
            [(time, 300 / 86400)], (rate - 0.5, 1), facecolors=BLUE if rate == 2.5 else ORANGE
        )
    timeline.xaxis.set_major_locator(mdates.HourLocator(interval=1, tz=UTC))
    timeline.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=UTC))
    timeline.set(
        yticks=(2.5, 5),
        ylim=(1.5, 6),
        ylabel="MS/s",
        xlabel="7 September 2026 UTC",
        title="A · 24 five-minute recordings across eight hours",
    )
    axes = [fig.add_subplot(grid[1 + i // 2, i % 2]) for i in range(4)]
    for row in data["last"]["series"]:
        axes[row["channel"] - 1].scatter(
            row["t_s"],
            np.asarray(row["y_hz"]) / 1000,
            s=7,
            alpha=0.65,
            color=BLUE if row["edge"] == "lower" else ORANGE,
            marker="o" if row["receiver"] == 0 else "x",
        )
    for i, ax in enumerate(axes):
        ax.set(
            xlim=(0, 300),
            xlabel="Time within 15:40 UTC scan (s)",
            ylabel="CFO at 11.2 GHz (kHz)",
            title=f"{chr(66 + i)} · Channel {i + 1}",
        )
    save(fig, output, 4)


def geographic(data, output):
    fig = plt.figure(figsize=(13, 7), layout="constrained")
    grid = fig.add_gridspec(2, 2, width_ratios=(1.5, 1))
    world = fig.add_subplot(grid[:, 0])
    refinement = fig.add_subplot(grid[0, 1])
    local = fig.add_subplot(grid[1, 1])
    for feature in data["land"]["features"]:
        geo = feature["geometry"]
        polygons = [geo["coordinates"]] if geo["type"] == "Polygon" else geo["coordinates"]
        for polygon in polygons:
            points = np.asarray(polygon[0])
            if np.ptp(points[:, 0]) < 180:
                world.add_patch(Polygon(points, facecolor="#eceeea", edgecolor="#a6aea6", lw=0.5))
    region = Region(43.6914344, -106.8991205, 5000, 5000)
    v = np.linspace(-2500, 2500, 101)
    east = np.r_[v, np.full(101, 2500), v[::-1], np.full(101, -2500), -2500]
    north = np.r_[np.full(101, -2500), v, np.full(101, 2500), v[::-1], -2500]
    lat, lon = region.coordinates(east, north)
    world.plot(lon, lat, color=BLUE, lw=1.5, label="5,000 × 5,000 km search bounds")
    truth = data["evaluation"]["truth"]
    rows = {r["run"]: r for r in data["metrics"]["continental_stages"]}
    names = ("grid250", "grid125", "refined", "grid50", "local", "fine")
    labels = (
        "250 km grid",
        "125 km grid",
        "25 km patches",
        "50 km grid",
        "10 km patches",
        "2 km patches",
    )
    for i, (name, label) in enumerate(zip(names, labels, strict=True)):
        row = rows[f"region5000-{name}"]
        color = ORANGE if i < 3 else BLUE
        world.scatter(
            row["longitude_deg"],
            row["latitude_deg"],
            color=color,
            s=30,
            marker="x" if i < 3 else "o",
        )
        if i < 3:
            world.annotate(
                label,
                (row["longitude_deg"], row["latitude_deg"]),
                xytext=((-110, 38), (-85, 47), (-100, 45))[i],
                textcoords="data",
                arrowprops={"arrowstyle": "-", "color": ORANGE, "lw": 0.7},
                fontsize=8,
            )
    world.scatter(
        truth["longitude_deg"],
        truth["latitude_deg"],
        color=RED,
        marker="*",
        s=100,
        label="Evaluation coordinate",
    )
    world.set(
        xlim=(min(lon) - 3, max(lon) + 3),
        ylim=(min(lat) - 3, max(lat) + 3),
        xlabel="Longitude (degrees)",
        ylabel="Latitude (degrees)",
        title="A · Search bounds and selected positions",
    )
    world.legend(loc="lower right", fontsize=8)
    for ax, limits, title in (
        (refinement, (-13, 5, -4, 4), "B · Successful refinement branch"),
        (local, (-0.5, 2.8, -0.5, 1.4), "C · Final position and reference"),
    ):
        for name, label, color, marker in (
            ("grid50", "50 km grid", "#7d8792", "s"),
            ("local", "10 km patches", GREEN, "s"),
            ("fine", "2 km patches", ORANGE, "s"),
            (None, "Continuous fit", BLUE, "o"),
        ):
            row = data["final"] if name is None else rows[f"region5000-{name}"]
            e, n = local_offsets(row, truth)
            if limits[0] <= e <= limits[1] and limits[2] <= n <= limits[3]:
                ax.scatter(e, n, color=color, marker=marker, s=35, label=label)
        ax.scatter(0, 0, marker="*", color=RED, s=90, label="Evaluation")
        ax.set(
            xlim=limits[:2],
            ylim=limits[2:],
            xlabel="East of reference (km)",
            ylabel="North of reference (km)",
            title=title,
            aspect="equal",
        )
        ax.legend(fontsize=7, loc="upper left" if ax is refinement else "lower left")
    e, n = local_offsets(data["final"], truth)
    local.plot([0, e], [0, n], "--", color=BLUE, lw=1)
    local.text(0.65, 0.55, "1.805 km\nhorizontal error", fontsize=9)
    save(fig, output, 5)


def local_offsets(row, reference):
    """Small-angle display coordinates only; reported errors use great circles."""
    north = 6371.0088 * np.deg2rad(row["latitude_deg"] - reference["latitude_deg"])
    east = (
        6371.0088
        * np.cos(np.deg2rad(reference["latitude_deg"]))
        * np.deg2rad(row["longitude_deg"] - reference["longitude_deg"])
    )
    return east, north


def comparisons(data, output):
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2), layout="constrained")
    metrics = data["metrics"]
    rows = metrics["regional_unknown_height"]
    sizes = sorted({r["region_km"] for r in rows})
    for timing, offset, color, label in (
        (False, -0.18, BLUE, "Nominal orbit"),
        (True, 0.18, ORANGE, "Fitted orbit time"),
    ):
        values = [
            next(
                r["horizontal_error_m"]
                for r in rows
                if r["region_km"] == size and r["fit_orbit_time"] == timing
            )
            / 1000
            for size in sizes
        ]
        bars = axes[0].bar(np.arange(5) + offset, values, width=0.35, color=color, label=label)
        axes[0].bar_label(bars, fmt="%.2f", fontsize=7, padding=2)
    axes[0].set(
        xticks=np.arange(5),
        xticklabels=[f"{s:g}" for s in sizes],
        ylim=(0, 2.65),
        xlabel="Starting square side (km)",
        ylabel="Horizontal error (km)",
        title="A · Unknown position / identities",
    )
    axes[0].legend(fontsize=8)
    for size in sizes:
        pair = [
            next(r for r in rows if r["region_km"] == size and r["fit_orbit_time"] == t)
            for t in (False, True)
        ]
        axes[1].annotate(
            "",
            (pair[1]["heldout_rms_hz"], pair[1]["horizontal_error_m"] / 1000),
            (pair[0]["heldout_rms_hz"], pair[0]["horizontal_error_m"] / 1000),
            arrowprops={"arrowstyle": "->", "color": "#777777"},
        )
        for row, color in zip(pair, (BLUE, ORANGE), strict=True):
            axes[1].scatter(
                row["heldout_rms_hz"], row["horizontal_error_m"] / 1000, color=color, s=25
            )
    axes[1].set(
        xlabel="Held-out CFO RMS (Hz)",
        ylabel="Horizontal error (km)",
        title="B · Orbit-time fitting changes both",
    )
    for mode, color, label in (
        ("nominal", BLUE, "Nominal orbit"),
        ("known_site_tau", ORANGE, "Orbit calibrated at supplied site"),
    ):
        pooled = metrics["pooled_known_site_association"]
        y = [
            next(m["horizontal_error_m"] for m in r["modes"] if m["mode"] == mode) / 1000
            for r in pooled
        ]
        axes[2].plot([r["scan_count"] for r in pooled], y, "o-", color=color, label=label)
    axes[2].set(
        xticks=(3, 6, 12, 18, 19),
        ylim=(0, 1.65),
        xlabel="Scans accumulated",
        ylabel="Horizontal error (km)",
        title="C · Location-assisted associations",
    )
    axes[2].legend(fontsize=7)
    axes[2].text(
        0.04,
        0.88,
        "Different evaluation reference\n1.184 km at three scans",
        transform=axes[2].transAxes,
        fontsize=8,
    )
    save(fig, output, 6)


def sample_rate(data, output):
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), layout="constrained")
    m = data["metrics"]
    keys = ("low_fractional", "native25_integer", "native25_fractional", "pss")
    labels = ("2.5 MS/s\nfractional", "25 MS/s\ninteger", "25 MS/s\nfractional", "25 MS/s\nPSS")
    bars = axes[0, 0].bar(
        labels,
        [m["native25_timing_fits"][k]["residual_rms_us"] * 1000 for k in keys],
        color=(GREEN, "#888888", BLUE, ORANGE),
    )
    axes[0, 0].bar_label(bars, fmt="%.1f", padding=2)
    axes[0, 0].set(
        ylim=(0, 55), ylabel="Timing-fit RMS (ns)", title="A · Measured timing on selected support"
    )
    bars = axes[0, 1].bar(
        ("2.5 MS/s GLRT", "25 MS/s GLRT"),
        [
            m["native25_cfo_comparison"][k]["residual_rms_hz"]
            for k in ("low_cfo_fit", "native25_cfo_fit")
        ],
        color=(GREEN, BLUE),
    )
    axes[0, 1].bar_label(bars, fmt="%.0f", padding=2)
    axes[0, 1].set(
        ylim=(0, 1450), ylabel="CFO-fit RMS (Hz)", title="B · Measured CFO on paired radios"
    )
    rows = m["sample_rate_theory"]
    rates = [r["sample_rate_msps"] for r in rows]
    for key, label, color in (
        ("sample_interval_ns", "Sample interval", BLUE),
        ("integer_rounding_rms_ns", "Uniform rounding RMS", ORANGE),
    ):
        axes[1, 0].plot(rates, [r[key] for r in rows], "o-", label=label, color=color)
    axes[1, 0].set(
        xlabel="Complex rate (MS/s)",
        ylabel="Time (ns)",
        title="C · Sampling arithmetic (theory)",
        xticks=rates,
    )
    axes[1, 0].legend(fontsize=8)
    for key, label, color in (
        ("ci16_one_rx_MB_s", "One receiver input", BLUE),
        ("ci16_two_rx_MB_s", "Two receiver inputs", GREEN),
    ):
        axes[1, 1].plot(rates, [r[key] for r in rows], "o-", label=label, color=color)
    axes[1, 1].set(
        xlabel="Complex rate (MS/s)",
        ylabel="CI16 payload (decimal MB/s)",
        title="D · Uncompressed transport (theory)",
        xticks=rates,
    )
    axes[1, 1].legend(fontsize=8)
    save(fig, output, 7)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.titleweight": "bold",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.18,
        }
    )
    data = load_data()
    measurement_chain(args.output)
    for function in (waveform, trajectories, recordings, geographic, comparisons, sample_rate):
        function(data, args.output)
    summary = {
        "evidence_commit": BASE,
        "scope": "publication from committed observations; no new RF or position inference",
        "headline": data["metrics"]["headline"],
        "continental_position": data["final"],
        "scan_count": len(data["scans"]),
        "episode_count": sum(len(s["episodes"]) for s in data["scans"]),
        "valid_visits": sum(s["inventory"]["visit_count"] for s in data["scans"]),
        "figure3_session": data["pair_session"],
        "figure3_tracklet_ids": [r["tracklet_id"] for r in data["pair"]],
        "figure4_session": data["scans"][-1]["session_id"],
        "continental_searches": data["metrics"]["continental_stages"],
    }
    (args.output / "data-summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    text = (ROOT / REPORT).read_text()
    targets = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text)
    for target in targets:
        if target.startswith(("https:", "http:", "#")):
            continue
        path = (ROOT / REPORT).parent / target.split("#")[0]
        if path.name != "manifest.json" and not path.exists():
            raise FileNotFoundError(path)
    manifest = {
        "evidence_commit": BASE,
        "report_sha256": sha(ROOT / REPORT),
        "generator_sha256": sha(Path(__file__)),
        "inputs": data["inputs"],
        "outputs": {name: sha(args.output / name) for name in (*FIGURES, "data-summary.json")},
        "figure_semantics": {
            "01": "conceptual diagram",
            "02": "schematic geometry and measured detector scores",
            "03": "measured RF trajectories",
            "04": "measured scan inventory and RF trajectories",
            "05": "evaluated search positions on sourced map; local axes approximate",
            "06": "measured positioning experiments with distinct assistance",
            "07": "measured timing/CFO and separately labelled design arithmetic",
        },
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"Rendered {len(FIGURES)} PNGs; "
        f"verified {len(data['inputs'])} source files and paper links."
    )


if __name__ == "__main__":
    main()
