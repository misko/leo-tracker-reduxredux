#!/usr/bin/env python3
"""Render truthful report-only summaries for selected live scanner reports."""

# ruff: noqa: E402, I001

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt


_DECISION_COLORS = {
    "active": "#1f9d68",
    "no_detection": "#60727a",
    "inconclusive": "#c94c4c",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://127.0.0.1:8090")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--scan-id", action="append", required=True)
    args = parser.parse_args()

    items = _scanner_items(args.api_base)
    by_id = {item["report"]["scan_id"]: item for item in items}
    missing = [scan_id for scan_id in args.scan_id if scan_id not in by_id]
    if missing:
        raise SystemExit(f"selected scans are not in the first 100 reports: {missing}")

    args.output_root.mkdir(parents=True, exist_ok=True)
    for scan_id in args.scan_id:
        item = by_id[scan_id]
        stem = f"{item['scanned_at'].replace('-', '').replace(':', '')}_{scan_id}"
        (args.output_root / f"{stem}.json").write_text(
            json.dumps(item, indent=2) + "\n",
            encoding="utf-8",
        )
        (args.output_root / f"{stem}.md").write_text(
            _markdown_report(item),
            encoding="utf-8",
        )
        _render_png(item, args.output_root / f"{stem}.png")


def _scanner_items(api_base: str) -> list[dict[str, Any]]:
    query = urlencode({"cursor": 0, "limit": 100})
    with urlopen(f"{api_base.rstrip('/')}/api/v1/scanner/reports?{query}", timeout=10) as response:
        payload = json.load(response)
    return list(payload["items"])


def _render_png(item: dict[str, Any], output_path: Path) -> None:
    report = item["report"]
    configuration = report["configuration"]
    results = report["results"]
    gate = float(configuration["glrt64_margin_gate"])
    labels = [
        f"CH{row['target']['channel']}\n{row['target']['edge'][0].upper()}" for row in results
    ]
    margins = [
        float(row["best_margin"]) if row["best_margin"] is not None else 0.0 for row in results
    ]
    colors = [_DECISION_COLORS[row["decision"]] for row in results]

    figure = plt.figure(figsize=(13.5, 8.2), dpi=160, constrained_layout=True)
    grid = figure.add_gridspec(3, 1, height_ratios=(2.1, 1.1, 0.13))
    margin_axis = figure.add_subplot(grid[0])
    cfo_axis = figure.add_subplot(grid[1])
    footer_axis = figure.add_subplot(grid[2])

    bars = margin_axis.bar(range(len(results)), margins, color=colors, width=0.72)
    margin_axis.axhline(
        gate,
        color="#d08b27",
        linestyle="--",
        linewidth=1.4,
        label=f"configured margin gate = {gate:.4f}",
    )
    margin_axis.axhline(0.0, color="#20282b", linewidth=0.8)
    margin_axis.set_xticks(range(len(results)), labels)
    margin_axis.set_ylabel("Best persisted GLRT64 margin")
    margin_axis.set_title(
        "Best margin by channel edge\n"
        "Bar color is the final decision; a gate crossing alone is not an active decision",
        loc="left",
        fontweight="bold",
    )
    margin_axis.grid(axis="y", alpha=0.22)
    margin_axis.legend(loc="upper right")
    margin_axis.set_ylim(
        min(0.0, min(margins, default=0.0) * 1.08),
        max(gate * 1.8, max(margins, default=gate) * 1.18),
    )
    for bar, margin in zip(bars, margins, strict=True):
        margin_axis.annotate(
            f"{margin:.4f}",
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
            rotation=35,
        )

    active_indexes: list[int] = []
    active_cfo: list[float] = []
    active_receivers: list[int] = []
    for index, result in enumerate(results):
        detection = result["first_detection"]
        if detection is None:
            continue
        active_indexes.append(index)
        active_cfo.append(float(detection["tracking_cfo_hz"]) / 1_000.0)
        active_receivers.append(int(detection["receiver_id"]))
    if active_indexes:
        for receiver_id, marker in ((0, "o"), (1, "s")):
            selected = [
                index for index, value in enumerate(active_receivers) if value == receiver_id
            ]
            if not selected:
                continue
            cfo_axis.scatter(
                [active_indexes[index] for index in selected],
                [active_cfo[index] for index in selected],
                marker=marker,
                s=70,
                color="#2d6ea3" if receiver_id == 0 else "#8d5aa6",
                label=f"RX{receiver_id} first confirmed hit",
                zorder=3,
            )
        cfo_axis.axhline(0.0, color="#20282b", linewidth=0.8)
        cfo_axis.legend(loc="best")
    else:
        cfo_axis.set_yticks([])
        cfo_axis.text(
            0.5,
            0.5,
            "No confirmed hit was persisted for this scan",
            transform=cfo_axis.transAxes,
            ha="center",
            va="center",
            fontsize=12,
            color="#60727a",
        )
    cfo_axis.set_xticks(range(len(results)), labels)
    cfo_axis.set_xlim(-0.7, len(results) - 0.3)
    cfo_axis.set_ylabel("Tracking CFO (kHz)")
    cfo_axis.set_title("First confirmed GLRT64 hit", loc="left", fontweight="bold")
    cfo_axis.grid(alpha=0.22)

    active_count = sum(result["decision"] == "active" for result in results)
    figure.suptitle(
        f"Scanner GLRT64 report summary · {report['scan_id']}\n"
        f"{item['scanned_at']} · {active_count}/{len(results)} active edges · "
        f"20 ms probes / 10 ms stride · candidate-only; no payload decoding",
        fontsize=14,
        fontweight="bold",
    )
    footer_axis.axis("off")
    footer_axis.text(
        0.5,
        0.5,
        (
            f"Radio {report['radio_id']} · capture {report['capture_elapsed_ms']:.1f} ms · "
            f"analysis {report['analysis_elapsed_ms']:.1f} ms · "
            "report-only archive: per-window series was not persisted, "
            "so no temporal curve is inferred"
        ),
        ha="center",
        va="center",
        fontsize=8.5,
        color="#4f5e63",
        transform=footer_axis.transAxes,
    )
    figure.savefig(
        output_path,
        format="png",
        dpi=160,
        metadata={"Software": "leo-tracker scanner report renderer"},
    )
    plt.close(figure)


def _markdown_report(item: dict[str, Any]) -> str:
    report = item["report"]
    configuration = report["configuration"]
    results = report["results"]
    active = [row for row in results if row["decision"] == "active"]
    inconclusive = [row for row in results if row["decision"] == "inconclusive"]
    lines = [
        f"# Scanner report `{report['scan_id']}`",
        "",
        "## Summary",
        "",
        f"- Scanned at: `{item['scanned_at']}`",
        f"- Radio: `{report['radio_id']}` / serial `{report['radio_serial']}`",
        f"- State: `{'partial' if inconclusive else 'complete'}`",
        f"- Active edges: {len(active)} of {len(results)}",
        f"- Capture elapsed: {report['capture_elapsed_ms']:.3f} ms",
        f"- Analysis elapsed: {report['analysis_elapsed_ms']:.3f} ms",
        f"- Evidence: candidate-only `{report['candidate_only']}`; "
        f"payload decoded `{report['payload_decoded']}`",
        "",
        "## Configuration",
        "",
        "| Field | Value |",
        "|---|---:|",
    ]
    for key in (
        "schema_version",
        "band_plan_id",
        "lnb_lo_hz",
        "sample_rate_hz",
        "bandwidth_hz",
        "dwell_ms",
        "probe_ms",
        "kernel_buffers",
        "receiver_ids",
        "gain_mode",
        "gain_db",
        "glrt64_margin_gate",
        "maximum_acquisition_candidates",
    ):
        value = configuration[key]
        rendered = ", ".join(str(part) for part in value) if isinstance(value, list) else str(value)
        lines.append(f"| `{key}` | `{rendered}` |")
    lines.extend(
        [
            "",
            "The configured 20 ms probes use a 10 ms stride. For this 80 ms dwell, "
            "the seven scheduled starts are 0, 10, 20, 30, 40, 50, and 60 ms.",
            "",
            "## Channel-edge results",
            "",
            "| Target | Decision | RF center | Applied IF | Best margin | "
            "First RX | Tracking CFO |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for result in results:
        target = result["target"]
        detection = result["first_detection"]
        receiver = "—" if detection is None else f"RX{detection['receiver_id']}"
        tracking_cfo = "—" if detection is None else f"{detection['tracking_cfo_hz']:,.3f} Hz"
        lines.append(
            "| "
            f"CH{target['channel']} {target['edge']} | `{result['decision']}` | "
            f"{target['rf_center_hz']:,} Hz | "
            f"{_fmt_int(result['actual_if_center_hz'])} | "
            f"{_fmt_float(result['best_margin'], 6)} | "
            f"{receiver} | {tracking_cfo} |"
        )
    for result in results:
        target = result["target"]
        detection = result["first_detection"]
        lines.extend(
            [
                "",
                f"### CH{target['channel']} {target['edge']}",
                "",
                f"- Decision: `{result['decision']}`",
                f"- RF / requested IF / applied IF: `{target['rf_center_hz']}` / "
                f"`{result['requested_if_center_hz']}` / `{result['actual_if_center_hz']}` Hz",
                f"- Tune / listen: `{_fmt_float(result['tune_ms'], 3)}` / "
                f"`{_fmt_float(result['listen_ms'], 3)}` ms",
                f"- Best margin: `{_fmt_float(result['best_margin'], 9)}`",
                f"- IQ SHA-256: `{result['iq_sha256'] or 'unavailable'}`",
                f"- Reason: {result['reason']}",
            ]
        )
        if detection is not None:
            lines.extend(
                [
                    f"- First confirmed receiver/probe/start: `RX{detection['receiver_id']}` / "
                    f"`{detection['probe_index']}` / `{detection['probe_start_ms']} ms`",
                    f"- Candidate rank / epoch: `{detection['candidate_rank']}` / "
                    f"`{detection['epoch_sample']}`",
                    f"- Acquired / residual / tracking CFO: `{detection['acquired_cfo_hz']:.6f}` / "
                    f"`{detection['residual_cfo_hz']:.6f}` / "
                    f"`{detection['tracking_cfo_hz']:.6f}` Hz",
                    f"- Exact / control / margin: `{detection['exact_score']:.9f}` / "
                    f"`{detection['control_score']:.9f}` / `{detection['margin']:.9f}`",
                ]
            )
    lines.extend(
        [
            "",
            "## Artifact limitation",
            "",
            "This historical scanner version persisted the report and IQ digests only. "
            "It did not persist the seven per-window GLRT64 series or PNG products. The "
            "companion PNG is rendered strictly from this report's best margins and first "
            "confirmed hits; it does not infer a temporal GLRT64 curve.",
            "",
        ]
    )
    return "\n".join(lines)


def _fmt_int(value: int | None) -> str:
    return "—" if value is None else f"{value:,} Hz"


def _fmt_float(value: float | None, digits: int) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


if __name__ == "__main__":
    main()
