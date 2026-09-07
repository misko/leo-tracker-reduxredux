#!/usr/bin/env python3
"""Render a retrospective synthesis from committed evidence; never opens radio IQ."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "39146ee83d00523fbd37ba02179c87a5c241a017"
FIGURES = Path("reports/figures")
OUTPUT = FIGURES / "2026_09_07_continental_positioning_synthesis"
REPORT = Path("reports/2026_09_07_continental_positioning_synthesis.md")
REGIONAL = FIGURES / "2026_09_07_blind_regional_pnt/evaluation-expanded.json"
COHORT = FIGURES / "2026_09_07_eight_hour_scan_pnt/summary.json"
TIMING = FIGURES / "2026_09_03_0181_native25_fractional_glrt/analysis-summary.json"
FRACTIONAL = FIGURES / "2026_09_02_7fea_glrt_fractional_epoch/fractional-glrt-epoch-prototype.json"
QUALITY = FIGURES / "2026_08_27_170330_capture_quality/capture-quality-results.json"
OLD_SCORER = Path("tools/evaluate_scan_pnt_cohort.py")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_metrics(root: Path = ROOT) -> dict:
    def read(path):
        return json.loads((root / path).read_text())

    regional, cohort, timing, fractional = map(read, (REGIONAL, COHORT, TIMING, FRACTIONAL))
    polishes = [r for r in regional["polishes"] if r["fit_height"]]
    continental = next(r for r in polishes if r["region_km"] == 5000 and not r["fit_orbit_time"])
    conditional = next(r for r in cohort["pooled_positioning"] if r["scan_count"] == 3)
    conditional = next(r for r in conditional["modes"] if r["mode"] == "nominal")
    # A receiver cannot use these evaluation distances to choose its estimate.
    truth = regional["truth"]
    scorer_tree = ast.parse((root / OLD_SCORER).read_text())
    observer_call = next(
        node.value
        for node in scorer_tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "OBSERVER" for t in node.targets)
    )
    old_site = {k.arg: ast.literal_eval(k.value) for k in observer_call.keywords}
    lat, lon, lat0, lon0 = map(
        math.radians,
        (
            old_site["latitude_deg"],
            old_site["longitude_deg"],
            truth["latitude_deg"],
            truth["longitude_deg"],
        ),
    )
    a = math.sin((lat - lat0) / 2) ** 2
    a += math.cos(lat0) * math.cos(lat) * math.sin((lon - lon0) / 2) ** 2
    reference_separation = 2 * 6371008.8 * math.asin(math.sqrt(a))
    for row in regional["runs"] + regional["polishes"]:
        lat, lon, lat0, lon0 = map(
            math.radians,
            (
                row["latitude_deg"],
                row["longitude_deg"],
                truth["latitude_deg"],
                truth["longitude_deg"],
            ),
        )
        a = math.sin((lat - lat0) / 2) ** 2
        a += math.cos(lat0) * math.cos(lat) * math.sin((lon - lon0) / 2) ** 2
        distance = 2 * 6371008.8 * math.asin(math.sqrt(min(1.0, a)))
        if not math.isclose(distance, row["horizontal_error_m"], abs_tol=1e-6):
            raise ValueError("evaluation coordinate and reported horizontal error disagree")
    keys = (
        "region_km",
        "horizontal_error_m",
        "fit_orbit_time",
        "heldout_rms_hz",
        "latitude_deg",
        "longitude_deg",
        "episode_count",
    )
    return {
        "base_commit": BASE_COMMIT,
        "purpose": "retrospective_reporting_only",
        "headline": {
            "continental_unknown_position_m": continental["horizontal_error_m"],
            "conditional_three_scan_m": conditional["horizontal_error_m"],
            "conditional_association_uses_known_site": True,
            "same_accuracy_population": False,
            "same_evaluation_reference": False,
            "reference_coordinate_separation_m": reference_separation,
            "earlier_site_preset": old_site,
            "continental_evaluation_reference": truth,
        },
        "regional_unknown_height": [{k: r[k] for k in keys} for r in polishes],
        "continental_stages": [r for r in regional["runs"] if r["region_km"] == 5000],
        "wrong_time_controls": [r for r in regional["runs"] if r["run"].startswith("control-")],
        "pooled_known_site_association": cohort["pooled_positioning"],
        "scan_summary": {k: v for k, v in cohort.items() if k not in ("pooled_positioning",)},
        "native25_timing_fits": timing["fits"],
        "native25_cfo_comparison": timing["comparison"],
        "native25_runtime": timing["runtime"],
        "fractional_7fea_fits": fractional["fits"],
        "detector_quality_comparison": read(QUALITY),
        "sample_rate_theory": [
            {
                "sample_rate_msps": rate,
                "sample_interval_ns": 1000 / rate,
                "integer_rounding_rms_ns": 1000 / rate / math.sqrt(12),
                "one_sample_light_travel_m": 299792458 / (rate * 1e6),
                "ci16_one_rx_MB_s": 4 * rate,
                "ci16_two_rx_MB_s": 8 * rate,
            }
            for rate in (2.5, 5.0, 10.0, 25.0)
        ],
        "input_sha256": {
            str(p): sha(root / p)
            for p in (REGIONAL, COHORT, TIMING, FRACTIONAL, QUALITY, OLD_SCORER)
        },
    }


def save(fig, output, name):
    fig.savefig(output / name, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render(metrics, output):
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titleweight": "bold",
            "axes.grid": True,
            "grid.alpha": 0.18,
            "figure.dpi": 120,
        }
    )
    blue, orange, teal = "#2463a5", "#c36524", "#258477"
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.3), layout="constrained")
    rows = metrics["regional_unknown_height"]
    sizes = sorted({r["region_km"] for r in rows})
    x = np.arange(len(sizes))
    for timing, offset, color, label in (
        (False, -0.18, blue, "Nominal TLE"),
        (True, 0.18, orange, "Bounded orbit time"),
    ):
        y = [
            next(
                r["horizontal_error_m"]
                for r in rows
                if r["region_km"] == s and r["fit_orbit_time"] == timing
            )
            / 1000
            for s in sizes
        ]
        bars = axes[0].bar(x + offset, y, width=0.35, color=color, label=label)
        axes[0].bar_label(bars, fmt="%.2f", fontsize=9, padding=3)
    axes[0].set(
        xticks=x,
        xticklabels=[f"{s:,.0f}" for s in sizes],
        ylim=(0, 2.55),
        xlabel="Starting square side (km); all reuse the same RF corpus",
        ylabel="Horizontal error (km)",
        title="A · Unknown position and satellite identities",
    )
    axes[0].legend(loc="upper left", fontsize=9)
    pooled = metrics["pooled_known_site_association"]
    for mode, color, label in (
        ("nominal", blue, "Nominal TLE"),
        ("robust_nominal", teal, "Residual-downweighted nominal"),
        ("known_site_tau", orange, "Also calibrated at known site"),
    ):
        y = [
            next(m["horizontal_error_m"] for m in r["modes"] if m["mode"] == mode) / 1000
            for r in pooled
        ]
        axes[1].plot([r["scan_count"] for r in pooled], y, "o-", color=color, label=label)
    axes[1].annotate(
        "1.184 km\nknown-site association",
        (3, 1.183783),
        (5, 1.5),
        arrowprops={"arrowstyle": "->", "color": blue},
        color=blue,
    )
    axes[1].set(
        xlabel="Eligible scans accumulated",
        ylabel="Horizontal error (km)",
        ylim=(0, 1.85),
        xticks=[3, 6, 12, 18, 19],
        title="B · Location-assisted satellite selection",
    )
    axes[1].legend(loc="upper right", fontsize=8)
    fig.suptitle(
        "1.8 km continental localization / 1.2 km conditional result\n"
        "Different assumptions and reference coordinates; neither is a confidence radius",
        fontsize=15,
    )
    save(fig, output, "01-position-results-and-claim-boundaries.png")

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), layout="constrained")
    fit = metrics["native25_timing_fits"]
    fit_keys = ["low_fractional", "native25_integer", "native25_fractional", "pss"]
    labels = [
        "2.5 MS/s\nfractional GLRT",
        "25 MS/s\ninteger GLRT",
        "25 MS/s\nfractional GLRT",
        "25 MS/s\nPSS",
    ]
    values = [fit[k]["residual_rms_us"] * 1000 for k in fit_keys]
    bars = axes[0].bar(labels, values, color=[teal, "#7d8792", blue, orange])
    axes[0].bar_label(bars, fmt="%.1f", padding=3)
    axes[0].set(
        ylabel="Quadratic timing-fit residual RMS (ns)",
        ylim=(0, 53),
        title="A · Timing on selected common support",
    )
    cfo = metrics["native25_cfo_comparison"]
    values = [cfo[k]["residual_rms_hz"] for k in ("low_cfo_fit", "native25_cfo_fit")]
    bars = axes[1].bar(["2.5 MS/s GLRT", "25 MS/s GLRT"], values, color=[teal, blue])
    axes[1].bar_label(bars, fmt="%.0f", padding=3)
    axes[1].set(
        ylabel="Direct CFO-fit residual RMS (Hz)",
        ylim=(0, 1460),
        title="B · Better timing did not mean better CFO",
    )
    fig.suptitle(
        "Real capture 0181: sample rate changes observables differently\n"
        "89 retained native epochs / 133 requested; low-rate comparison has 242 points",
        fontsize=14,
    )
    save(fig, output, "02-measured-timing-and-cfo-tradeoff.png")

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), layout="constrained")
    rows = metrics["sample_rate_theory"]
    rates = [r["sample_rate_msps"] for r in rows]
    axes[0].plot(
        rates, [r["sample_interval_ns"] for r in rows], "o-", color=blue, label="One sample: 1 / fs"
    )
    axes[0].plot(
        rates,
        [r["integer_rounding_rms_ns"] for r in rows],
        "o--",
        color=orange,
        label="Uniform integer rounding: 1 / (fs √12)",
    )
    axes[0].set(
        xlabel="Complex sample rate (MS/s)",
        ylabel="Time (ns)",
        xticks=rates,
        title="A · Sampling arithmetic, not a physical accuracy bound",
    )
    axes[0].legend(fontsize=9)
    for key, color, label in (
        ("ci16_one_rx_MB_s", blue, "One RX, CI16"),
        ("ci16_two_rx_MB_s", teal, "Two RX, CI16"),
    ):
        axes[1].plot(rates, [r[key] for r in rows], "o-", color=color, label=label)
    axes[1].set(
        xlabel="Complex sample rate (MS/s)",
        ylabel="Uncompressed payload (decimal MB/s)",
        xticks=rates,
        title="B · Payload only; no protocol or storage overhead",
    )
    axes[1].legend()
    fig.suptitle(
        "Sample-rate design arithmetic\n"
        "Theoretical quantities; not new RF measurements or a positioning forecast",
        fontsize=14,
    )
    save(fig, output, "03-sampling-and-transport-theory.png")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    labels = [
        "250 km full",
        "125 km full",
        "125 → 25 km\nlocal patches",
        "50 km full",
        "50 → 10 km\nlocal patches",
        "10 → 2 km\nlocal patches",
    ]
    names = [
        "region5000-grid250",
        "region5000-grid125",
        "region5000-refined",
        "region5000-grid50",
        "region5000-local",
        "region5000-fine",
    ]
    values = [
        next(r["horizontal_error_m"] for r in metrics["continental_stages"] if r["run"] == name)
        / 1000
        for name in names
    ]
    axes[0].barh(labels[::-1], values[::-1], color=([orange] * 3 + [blue] * 3)[::-1])
    axes[0].set(
        xscale="log",
        xlabel="Horizontal error after evaluation reveal (km)",
        title="A · A missed continental mode survives local refinement",
    )
    for i, value in enumerate(values[::-1]):
        axes[0].text(value * 1.08, i, f"{value:,.2f}", va="center", fontsize=9)
    axes[0].set_xlim(0.6, 12000)
    for size in sizes:
        pair = [
            next(
                r
                for r in metrics["regional_unknown_height"]
                if r["region_km"] == size and r["fit_orbit_time"] == t
            )
            for t in (False, True)
        ]
        axes[1].annotate(
            "",
            (pair[1]["heldout_rms_hz"], pair[1]["horizontal_error_m"] / 1000),
            (pair[0]["heldout_rms_hz"], pair[0]["horizontal_error_m"] / 1000),
            arrowprops={"arrowstyle": "->", "color": "#888888"},
        )
        for row, color in zip(pair, (blue, orange), strict=True):
            axes[1].scatter(row["heldout_rms_hz"], row["horizontal_error_m"] / 1000, color=color)
        axes[1].annotate(
            f"{size:,.0f} km",
            (pair[0]["heldout_rms_hz"], pair[0]["horizontal_error_m"] / 1000),
            xytext=(292, {100: 1.77, 500: 1.82, 1000: 1.70, 2000: 1.54, 5000: 1.88}[size]),
            textcoords="data",
            fontsize=8,
            arrowprops={"arrowstyle": "-", "color": "#999999", "lw": 0.6},
        )
    axes[1].set(
        xlabel="Held-out CFO RMS (Hz)",
        ylabel="Horizontal error (km)",
        title="B · Orbit correction lowers RMS, worsens location",
        xlim=(260, 301),
        ylim=(1.45, 2.12),
    )
    axes[1].scatter([], [], color=blue, label="Nominal TLE")
    axes[1].scatter([], [], color=orange, label="Bounded orbit time")
    axes[1].legend(fontsize=9)
    fig.suptitle("Measured limits of search resolution and model flexibility", fontsize=15)
    save(fig, output, "04-search-and-model-bottlenecks.png")

    quality = metrics["detector_quality_comparison"]
    fig = plt.figure(figsize=(13, 8), layout="constrained")
    grid = fig.add_gridspec(2, 2, height_ratios=(1.1, 1))
    score = fig.add_subplot(grid[0, :])
    availability = fig.add_subplot(grid[1, 0])
    aggregate = fig.add_subplot(grid[1, 1])
    for key, label, color, offset in (
        ("prior", "26 Aug · CH3 lower · RX1", orange, -0.18),
        ("new", "27 Aug · CH4 lower · RX1", teal, 0.18),
    ):
        capture = quality["captures"][key]
        bins = np.asarray(quality["glrt_time_bins"][key])
        score.plot(bins[:, 0], bins[:, 1], "o-", color=color, markersize=3, label=label)
        score.fill_between(bins[:, 0], bins[:, 2], bins[:, 3], color=color, alpha=0.14)
        glrt = capture["glrt"]
        availability.plot(
            bins[:, 0],
            bins[:, 5] * 100,
            "o-",
            color=color,
            markersize=3,
            label=f"{label}: {glrt['passing_windows']:,}/{glrt['valid_windows']:,}",
        )
        values = [
            glrt["passing_median_exact_score"],
            glrt["passing_median_margin"],
            capture["known_pilot_hard_symbol_accuracy"],
        ]
        bars = aggregate.bar(np.arange(3) + offset, values, width=0.35, color=color, label=label)
        aggregate.bar_label(bars, fmt="%.3f", padding=3, fontsize=9)
    score.set(
        xlim=(0, 60),
        ylim=(0, 0.92),
        xlabel="Elapsed recording time (s)",
        ylabel="Exact known-pilot score",
        title="A · Two-second medians with 10th–90th percentile bands",
    )
    score.legend(loc="lower right", fontsize=9)
    availability.set(
        xlim=(0, 60),
        ylim=(40, 102),
        xlabel="Elapsed recording time (s)",
        ylabel="Margin-gate pass fraction (%)",
        title="B · Detection availability on valid windows",
    )
    availability.legend(loc="lower right", fontsize=8)
    aggregate.set(
        xticks=np.arange(3),
        xticklabels=["Median exact\nscore", "Median GLRT\nmargin", "Known-pilot\nsymbol accuracy"],
        ylim=(0, 0.85),
        ylabel="Unitless score or fraction",
        title="C · Selected receiver-path quality",
    )
    aggregate.legend(loc="upper left", fontsize=8)
    fig.suptitle(
        "Known-pilot detection in two 60 s recordings at 5 MS/s\n"
        "Channel, gain, bandwidth and recording time differ",
        fontsize=15,
    )
    save(fig, output, "05-detector-quality-by-recording.png")


def write_inventory(root, output):
    lines = [
        "# Related-report inventory",
        "",
        f"Source snapshot: `{BASE_COMMIT}`.",
        "",
        "All pre-existing top-level reports were screened for the synthesis. This is a",
        "discovery and provenance index, not a claim that every historical result is current.",
        "The main report identifies the detailed sources and superseding findings.",
        "",
        "| Report | Title | SHA-256 |",
        "|---|---|---|",
    ]
    files = {}
    for path in sorted((root / "reports").glob("*.md")):
        if path.name == REPORT.name:
            continue
        title = path.read_text().splitlines()[0].lstrip("# ").replace("|", "\\|")
        digest = sha(path)
        files[str(path.relative_to(root))] = digest
        lines.append(f"| [{path.stem}](../../{path.name}) | {title} | `{digest}` |")
    (output / "source-report-index.md").write_text("\n".join(lines) + "\n")
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    metrics = load_metrics()
    render(metrics, args.output)
    (args.output / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n")
    report_sources = write_inventory(ROOT, args.output)
    report_text = (ROOT / REPORT).read_text()
    targets = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", report_text)
    local = [
        (ROOT / REPORT).parent / t.split("#")[0]
        for t in targets
        if not t.startswith(("http:", "https:", "#"))
    ]
    for path in local:
        if path.resolve() == (args.output / "manifest.json").resolve():
            continue  # Written below after all other links and outputs are verified.
        if not path.exists():
            raise FileNotFoundError(path)
    artifacts = [p for p in args.output.iterdir() if p.name != "manifest.json"]
    manifest = {
        "base_commit": BASE_COMMIT,
        "scope": "committed summaries and figures; no raw-IQ replay, collection or deployment",
        "report_inventory_count": len(report_sources),
        "reports": report_sources,
        "numeric_inputs": metrics["input_sha256"],
        "report_sha256": sha(ROOT / REPORT),
        "generator_sha256": sha(Path(__file__)),
        "linked_pngs": {
            str(p.resolve().relative_to(ROOT)): sha(p) for p in local if p.suffix == ".png"
        },
        "outputs": {p.name: sha(p) for p in artifacts if p.is_file()},
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"Rendered 5 PNGs; indexed {len(report_sources)} reports; "
        f"verified {len(local)} local links."
    )


if __name__ == "__main__":
    main()
