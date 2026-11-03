"""Render all-channel GLRT associations, residuals and unresolved observations."""

from __future__ import annotations

import csv
import html
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from numpy.polynomial.legendre import legval
from tune_full_data_tracklets import OUTPUT

LABELS = {
    "em": "Wrapped EM",
    "graph": "Graph paths",
    "hough": "Wrapped Hough",
    "mht": "Kalman beam / MHT",
    "baseline": "RANSAC reference",
}


def load_selected(method, trial_name=None):
    directory = OUTPUT / method
    selected = json.loads((directory / "selected.json").read_text())
    trial = directory / "trials" / (trial_name or selected["name"])
    summary = json.loads((trial / "results.json").read_text())
    with (trial / "assignments.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for key in ("receiver", "channel", "track_id", "piece_id", "alias_lift"):
            row[key] = int(row[key])
        for key in ("time_s", "measured_cfo_hz", "residual_hz"):
            row[key] = float(row[key]) if row[key] else None
    return selected, summary, rows


def render_method(
    method,
    summary,
    rows,
    directory=None,
    display_name=None,
    views=("associations", "unassociated", "residuals", "supported"),
):
    directory = directory or OUTPUT / method
    directory.mkdir(parents=True, exist_ok=True)
    label = display_name or LABELS[method]
    palette = plt.get_cmap("turbo")
    for view in views:
        fig, axes = plt.subplots(8, 2, figsize=(16, 22), sharex=True)
        for lane in summary["lanes"]:
            rx, ch = lane["receiver"], lane["channel"]
            ax = axes[ch - 1, rx - 1]
            group = [r for r in rows if (r["receiver"], r["channel"]) == (rx, ch)]
            unresolved = [r for r in group if r["track_id"] < 0]
            visible = [r for r in group if r["track_id"] >= 0]
            if view == "supported":
                visible = [r for r in visible if r["quality_status"] == "no_structure_detected"]
                background = [r for r in group if r not in visible]
            else:
                background = unresolved
            if view != "residuals":
                ax.scatter(
                    [r["time_s"] for r in background],
                    [r["measured_cfo_hz"] / 1000 for r in background],
                    s=12,
                    color="#939aa3",
                    alpha=0.7,
                    linewidths=0,
                    rasterized=True,
                )
                ax.set_ylim(
                    min(r["measured_cfo_hz"] for r in group) / 1000 - 5,
                    max(r["measured_cfo_hz"] for r in group) / 1000 + 5,
                )
            if view != "unassociated":
                for tid, track in enumerate(lane["tracks"]):
                    members = [r for r in visible if r["track_id"] == tid]
                    if not members:
                        continue
                    color = palette((tid * 0.61803398875) % 1)
                    ax.scatter(
                        [r["time_s"] for r in members],
                        [
                            r["residual_hz"] if view == "residuals" else r["measured_cfo_hz"] / 1000
                            for r in members
                        ],
                        s=12,
                        color=color,
                        alpha=0.85,
                        linewidths=0,
                        rasterized=True,
                    )
                    if view == "residuals":
                        continue
                    style = {
                        "no_structure_detected": "-",
                        "structure_flagged": "--",
                        "insufficient_support": ":",
                    }[track["quality_status"]]
                    for pid, piece in enumerate(track["pieces"]):
                        points = sorted(
                            (r for r in members if r["piece_id"] == pid), key=lambda r: r["time_s"]
                        )
                        for left, right in zip(points[:-1], points[1:], strict=True):
                            if (
                                left["alias_lift"] != right["alias_lift"]
                                or right["time_s"] - left["time_s"] > summary["config"]["max_gap_s"]
                            ):
                                continue
                            t = np.linspace(left["time_s"], right["time_s"], 8)
                            x = (t - piece["reference_time_s"]) / piece["time_scale_s"]
                            predicted = legval(x, piece["coefficients_hz"]) - (
                                left["alias_lift"] * summary["config"]["alias_spacing_hz"]
                            )
                            ax.plot(
                                t,
                                predicted / 1000,
                                color=color,
                                linestyle=style,
                                linewidth=0.85,
                                alpha=0.85,
                            )
                    mid = members[len(members) // 2]
                    ax.annotate(
                        str(tid),
                        (mid["time_s"], mid["measured_cfo_hz"] / 1000),
                        xytext=(3, 3),
                        textcoords="offset points",
                        fontsize=6,
                        color=color,
                    )
            if view == "residuals":
                for y in (-450, 0, 450):
                    ax.axhline(y, color="#999999", linewidth=0.6, linestyle="-" if y == 0 else "--")
                ax.set_ylim(-480, 480)
            ax.set_title(
                f"RX{rx} · CH{ch} · {lane['track_count']} tracks · "
                f"{lane['assigned']}/{lane['observations']} fit · {len(unresolved)} unresolved",
                loc="left",
                fontsize=10,
            )
            ax.set_xlim(0, 300)
            ax.grid(alpha=0.18)
        titles = {
            "associations": "GLRT CFO and fitted polynomial tracklets",
            "unassociated": "Unassociated GLRT observations only",
            "residuals": "Residuals of every fitted observation",
            "supported": "Supported fits with no detected residual structure",
        }
        fig.suptitle(
            f"DSX01 S01 · {label} · {titles[view]}\n"
            f"{summary['track_count']} lane-level tracks; {summary['assigned']:,} fitted; "
            f"{summary['unresolved']:,} unresolved",
            fontsize=16,
            y=0.996,
        )
        fig.supxlabel("Time since first-sample estimate (s)")
        fig.supylabel("Fitted residual (Hz)" if view == "residuals" else "Measured GLRT CFO (kHz)")
        notes = {
            "associations": "Gray: unresolved. Lines: solid = no structure detected; "
            "dashed = flagged; dotted = fewer than 20 points per piece.",
            "unassociated": "Same time and frequency scales as the association panels.",
            "supported": "Gray includes unresolved, flagged and insufficient-support points.",
            "residuals": "All points used in fitting. Residual checks are descriptive; "
            "they do not establish correct physical identities.",
        }
        fig.text(0.5, 0.024, notes[view], ha="center", fontsize=10)
        fig.tight_layout(rect=(0.025, 0.035, 1, 0.96))
        for extension in ("png", "pdf"):
            fig.savefig(directory / f"{view}.{extension}", dpi=140)
        plt.close(fig)
    with (directory / "unassociated.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(r for r in rows if r["track_id"] < 0)


def main(render=True):
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False})
    records = []
    sections = []
    for method in LABELS:
        selected, summary, rows = load_selected(method)
        if render:
            render_method(method, summary, rows)
        search = json.loads((OUTPUT / method / "search.json").read_text())
        raw_best = max((r for r in search if "rank" in r), key=lambda r: r["assigned"])
        alternative = ""
        if method == "em" and raw_best["name"] != selected["name"]:
            if render:
                _, alternative_summary, alternative_rows = load_selected(method, raw_best["name"])
                render_method(
                    method,
                    alternative_summary,
                    alternative_rows,
                    directory=OUTPUT / method / "maximum-coverage",
                    display_name="Wrapped EM · maximum raw coverage",
                )
            alternative = (
                f"<p>Maximum raw coverage alternative: {raw_best['assigned']:,} associations; "
                f"{raw_best['residual_quality']['no_structure_detected']['associated_points']:,} "
                "supported without detected structure. "
                '<a href="em/maximum-coverage/associations.png">GLRT fits</a> · '
                '<a href="em/maximum-coverage/unassociated.png">Unassociated</a> · '
                '<a href="em/maximum-coverage/residuals.png">Residuals</a></p>'
            )
        q = summary["residual_quality"]
        record = {
            "method": method,
            "trial": selected["name"],
            "trials": len(search),
            "tracks": summary["track_count"],
            "pieces": summary["piece_count"],
            "associated": summary["assigned"],
            "unassociated": summary["unresolved"],
            "supported_no_structure": q["no_structure_detected"]["associated_points"],
            "structure_flagged": q["structure_flagged"]["associated_points"],
            "insufficient_support": q["insufficient_support"]["associated_points"],
            "rms_hz": summary["residual_diagnostics"]["rms_hz"],
            "maximum_raw_associations_trial": raw_best["name"],
            "maximum_raw_associations": raw_best["assigned"],
        }
        records.append(record)
        cards = "".join(
            f'<a href="{method}/{view}.png"><figure><img loading="lazy" '
            f'src="{method}/{view}.png"><figcaption>{title}</figcaption></figure></a>'
            for view, title in (
                ("associations", "All associations"),
                ("unassociated", "Unassociated only"),
                ("supported", "Supported, no structure detected"),
                ("residuals", "Residuals"),
            )
        )
        sections.append(
            f'<section id="{method}"><h2>{html.escape(LABELS[method])}</h2>'
            f"<p>{record['tracks']} tracks; {record['associated']:,} associated; "
            f"{record['unassociated']:,} unresolved; {record['supported_no_structure']:,} "
            f"supported with no detected structure. Selected trial: "
            f'<a href="{method}/trials/{selected["name"]}/results.json">'
            f"{html.escape(selected['name'])}</a>. "
            f'<a href="{method}/trials/{selected["name"]}/assignments.csv">'
            "All assignments CSV</a> · "
            f'<a href="{method}/unassociated.csv">Unassociated CSV</a> · '
            f'<a href="{method}/search.json">All tuning trials</a> · '
            f'<a href="{method}/selected-validation.json">Controls</a></p>'
            f'{alternative}<div class="cards">{cards}</div></section>'
        )
    (OUTPUT / "summary.json").write_text(json.dumps(records, indent=2) + "\n")
    with (OUTPUT / "comparison.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    fig, ax = plt.subplots(figsize=(12, 5))
    left = np.zeros(len(records))
    for key, label, color in (
        ("supported_no_structure", "Supported; no structure detected", "#277f68"),
        ("insufficient_support", "Insufficient diagnostic support", "#75a4c8"),
        ("structure_flagged", "Residual structure flagged", "#e4aa4b"),
        ("unassociated", "Unassociated", "#c1c6cd"),
    ):
        values = np.array([r[key] for r in records])
        ax.barh([LABELS[r["method"]] for r in records], values, left=left, label=label, color=color)
        left += values
    ax.invert_yaxis()
    ax.set(
        xlim=(0, 4797),
        xlabel="Original GLRT observations (4,797 total)",
        title="DSX01 S01 · Full-data tuned polynomial association",
    )
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2, frameon=False)
    fig.tight_layout()
    fig.savefig(OUTPUT / "comparison.png", dpi=160, bbox_inches="tight")
    fig.savefig(OUTPUT / "comparison.pdf", bbox_inches="tight")
    plt.close(fig)
    document = (
        '<!doctype html><meta charset="utf-8"><title>DSX01 S01 tracklet review</title>'
        "<style>body{font:16px system-ui;margin:30px auto;max-width:1500px;color:#182433}"
        ".cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}"
        "img{width:100%}figure{margin:0}section{margin:42px 0}a{color:#155e8b}</style>"
        "<h1>DSX01 S01: full-data polynomial association</h1>"
        "<p>All 4,797 GLRT observations; eight channels and two receivers. "
        "Degree ≤4, positive complexity penalties, 450 Hz residual gate. "
        "Selection maximizes supported points with no detected residual structure, "
        "then total associations. All points participate in fitting. "
        "These are lane-level curves, not satellite counts. Click a plot to enlarge.</p>"
        '<img src="comparison.png" style="max-width:1000px">' + "".join(sections)
    )
    (OUTPUT / "review.html").write_text(document)
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
