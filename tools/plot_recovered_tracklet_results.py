"""Plot frozen recovered GLRT associations, unresolved points and each track's RMS."""

from __future__ import annotations

import csv
import html
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from evaluate_polynomial_tracklets import REPO, digest
from render_full_data_tracklet_review import LABELS, render_method

INPUT = REPO / "reports/2026_10_17_dsx01_residual_review"
OUTPUT = INPUT / "track-plots"


def load_method(method):
    directory = INPUT / method / "support2"
    summary = json.loads((directory / "results.json").read_text())
    with (directory / "assignments.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for key in ("receiver", "channel", "track_id", "piece_id", "alias_lift"):
            row[key] = int(row[key])
        for key in ("time_s", "measured_cfo_hz", "residual_hz"):
            row[key] = float(row[key]) if row[key] else None
    return summary, rows


def track_statistics(method, summary, rows):
    """Independently compute every RMS from exported original-observation residuals."""
    records = []
    for lane in summary["lanes"]:
        rx, ch = lane["receiver"], lane["channel"]
        group = [r for r in rows if (r["receiver"], r["channel"]) == (rx, ch)]
        for tid, track in enumerate(lane["tracks"]):
            members = [r for r in group if r["track_id"] == tid]
            assert len(members) == len(track["indices"])
            residuals = np.array([r["residual_hz"] for r in members])
            rms = float(np.sqrt(np.mean(residuals**2)))
            np.testing.assert_allclose(rms, track["residual_rms_hz"], rtol=1e-10, atol=1e-6)
            records.append(
                {
                    "method": method,
                    "receiver": rx,
                    "channel": ch,
                    "track_id": tid,
                    "track_key": f"RX{rx}-CH{ch}-T{tid:03d}",
                    "points": len(members),
                    "pieces": len(track["pieces"]),
                    "max_degree": max(p["degree"] for p in track["pieces"]),
                    "start_s": min(r["time_s"] for r in members),
                    "end_s": max(r["time_s"] for r in members),
                    "rms_hz": rms,
                    "mean_residual_hz": float(residuals.mean()),
                    "maximum_absolute_residual_hz": float(np.max(abs(residuals))),
                    "quality_status": track["quality_status"],
                    "recovery_stage": track.get("recovery_stage", "original"),
                }
            )
    assert len(records) == summary["track_count"]
    assert sum(r["points"] for r in records) == summary["assigned"]
    assert len(rows) == summary["observations"] == 4797
    return records


def plot_rms(method, summary, records, directory, maximum):
    fig, axes = plt.subplots(8, 2, figsize=(16, 22), sharey=True)
    palette = plt.get_cmap("turbo")
    hatch = {"no_structure_detected": "", "structure_flagged": "xx", "insufficient_support": "///"}
    for ch in range(1, 9):
        for rx in (1, 2):
            ax = axes[ch - 1, rx - 1]
            group = [r for r in records if (r["receiver"], r["channel"]) == (rx, ch)]
            for r in group:
                color = palette((r["track_id"] * 0.61803398875) % 1)
                ax.bar(
                    r["track_id"],
                    r["rms_hz"],
                    color=color,
                    width=0.72,
                    edgecolor="#465462",
                    linewidth=0.45,
                    hatch=hatch[r["quality_status"]],
                )
                ax.annotate(
                    str(r["points"]),
                    (r["track_id"], r["rms_hz"]),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha="center",
                    fontsize=7,
                )
            ax.axhline(150, linestyle="--", linewidth=0.7, color="#65717b")
            ax.set(xticks=[r["track_id"] for r in group], ylim=(0, maximum))
            ax.tick_params(axis="x", labelsize=8)
            ax.set_title(f"RX{rx} · CH{ch} · {len(group)} tracks", loc="left", fontsize=10)
            ax.grid(axis="y", alpha=0.2)
    fig.suptitle(
        f"DSX01 S01 · {LABELS[method]} · Residual RMS for every track\n"
        f"{summary['track_count']} tracks; {summary['assigned']:,} associated; "
        f"{summary['unresolved']:,} unassociated",
        fontsize=16,
        y=0.995,
    )
    fig.supxlabel("Track ID within each receiver/channel (same IDs and colors as GLRT plots)")
    fig.supylabel("Polynomial-fit residual RMS (Hz)")
    fig.text(
        0.5,
        0.024,
        "Number above bar = points. Hatches: /// provisional short support; "
        "xx residual structure flagged. Dashed line = assumed 150 Hz noise scale.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=(0.025, 0.04, 1, 0.96))
    for extension in ("png", "pdf"):
        fig.savefig(directory / f"track-rms.{extension}", dpi=140)
    plt.close(fig)


def main(render=True):
    data = {method: load_method(method) for method in LABELS}
    statistics = {method: track_statistics(method, *data[method]) for method in LABELS}
    maximum = max(180.0, max(r["rms_hz"] for group in statistics.values() for r in group) * 1.2)
    sections, all_records, manifest, method_records, table_rows = [], [], {}, [], []
    for method, label in LABELS.items():
        summary, rows = data[method]
        directory = OUTPUT / method
        records = statistics[method]
        if render:
            render_method(
                method, summary, rows, directory=directory, views=("associations", "unassociated")
            )
            plot_rms(method, summary, records, directory, maximum)
        metrics = {
            "method": method,
            "observations": summary["observations"],
            "associated": summary["assigned"],
            "associated_percent": 100 * summary["assigned"] / summary["observations"],
            "tracks": len(records),
            "mean_points_per_track": summary["assigned"] / len(records),
            "mean_track_duration_s": float(np.mean([r["end_s"] - r["start_s"] for r in records])),
        }
        method_records.append(metrics)
        plot_links = "".join(
            f'<td><a href="{method}/{stem}.png">{title}</a></td>'
            for stem, title in (
                ("associations", "GLRT"),
                ("unassociated", "Unassociated"),
                ("track-rms", "RMS"),
            )
        )
        table_rows.append(
            f'<tr><td><a href="#{method}">{html.escape(label)}</a></td>'
            f"<td>{metrics['associated_percent']:.2f}%</td><td>{metrics['tracks']}</td>"
            f"<td>{metrics['mean_points_per_track']:.2f}</td>"
            f"<td>{metrics['mean_track_duration_s']:.2f}</td>{plot_links}</tr>"
        )
        all_records.extend(records)
        with (directory / "track-rms.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
        cards = "".join(
            f'<figure><a href="{method}/{stem}.png"><img loading="lazy" '
            f'src="{method}/{stem}.png" alt="{html.escape(label)}: {title}"></a>'
            f'<figcaption>{title} · <a href="{method}/{stem}.pdf">PDF</a></figcaption></figure>'
            for stem, title in (
                ("associations", "GLRT colored by track"),
                ("unassociated", "Unassociated GLRT"),
                ("track-rms", "RMS for every track"),
            )
        )
        sections.append(
            f'<section id="{method}"><h2>{html.escape(label)}</h2>'
            f"<p>{summary['track_count']} tracks · {summary['assigned']:,} associated · "
            f"{summary['unresolved']:,} unassociated · "
            f"{metrics['associated_percent']:.2f}% associated · "
            f"mean {metrics['mean_points_per_track']:.2f} points / "
            f"{metrics['mean_track_duration_s']:.2f} s per track · "
            f'<a href="{method}/track-rms.csv">Per-track RMS CSV</a></p>'
            f'<div class="cards">{cards}</div></section>'
        )
        source = INPUT / method / "support2"
        manifest[method] = {
            "policy": "support2",
            "tracks": summary["track_count"],
            "assigned": summary["assigned"],
            "unassociated": summary["unresolved"],
            "results_sha256": digest(source / "results.json"),
            "assignments_sha256": digest(source / "assignments.csv"),
        }
        print("PLOTTED", method, manifest[method], flush=True)
    with (OUTPUT / "method-summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(method_records[0]))
        writer.writeheader()
        writer.writerows(method_records)
    with (OUTPUT / "all-track-rms.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(all_records[0]))
        writer.writeheader()
        writer.writerows(all_records)
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    document = (
        '<!doctype html><meta charset="utf-8"><title>DSX01 GLRT tracks and RMS</title>'
        "<style>body{font:16px system-ui;margin:28px auto;max-width:1600px;color:#182433}"
        ".cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}"
        "figure{margin:0}img{width:100%;height:auto}section{margin:40px 0}a{color:#155e8b}"
        "table{border-collapse:collapse;width:100%}th,td{padding:9px;border-bottom:1px solid #ddd;"
        "text-align:right}th:first-child,td:first-child{text-align:left}"
        "@media(max-width:900px){.cards{grid-template-columns:1fr}}</style>"
        "<h1>DSX01 S01: GLRT associations and per-track RMS</h1>"
        "<p>Latest recovered results, including the sparse-support trial: minimum eight points; "
        "two points per coefficient; degree ≤4; 450 Hz residual gate. All 4,797 points retained. "
        "Each figure covers eight channels and both receivers. Click an image to enlarge.</p>"
        "<p>Track colors and IDs match within a method and receiver/channel. Gray points are "
        "unassociated. RMS is the in-sample polynomial-fit residual RMS. Short tracks remain "
        "provisional; low RMS alone does not establish residual whiteness or physical identity.</p>"
        "<p>"
        + " · ".join(f'<a href="#{m}">{html.escape(label)}</a>' for m, label in LABELS.items())
        + ' · <a href="all-track-rms.csv">All per-track RMS values (CSV)</a></p>'
        + "<table><thead><tr><th>Method</th><th>Associated</th><th>Tracks</th>"
        "<th>Mean points/track</th><th>Mean duration (s)</th><th>GLRT</th>"
        "<th>Unassociated</th><th>RMS</th></tr></thead><tbody>"
        + "".join(table_rows)
        + "</tbody></table>"
        "<p>Association percentage uses all 4,797 observations. Mean duration is the "
        "unweighted mean of last minus first observation time per track. "
        '<a href="method-summary.csv">Download summary CSV</a></p>' + "".join(sections)
    )
    (OUTPUT / "review.html").write_text(document)


if __name__ == "__main__":
    main()
