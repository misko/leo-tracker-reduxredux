#!/usr/bin/env python3
"""Review the four-frequency, stride-10 30-MS/s qualification evidence."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("firmware_repo", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.firmware_repo))
    from tools.review_glrt_iq_probe import capture
    from tools.starlink_glrt_native_journal import records
    from tools.starlink_glrt_tracking_journal import review

    manifest = {}
    for line in (args.evidence / "SHA256SUMS").read_text().splitlines():
        sha, name = line.split("  ", 1)
        manifest[name] = sha

    result = {"schema": "radio20-30ms-sparse10-review/v1", "runs": []}
    for number in range(2, 10):
        name = f"run-sparse10-v{number}"
        root = args.evidence / name
        for path in root.iterdir():
            if path.is_file():
                assert manifest[f"{name}/{path.name}"] == digest(path)
        status = json.loads((root / "stdout.json").read_text())
        operator = json.loads((root / "operator.json").read_text())
        rows = [json.loads(line) for line in (root / "worker.jsonl").read_text().splitlines()]
        terminals = [row for row in rows if row.get("kind") == "native_terminal"]
        scans = [row for row in rows if row.get("kind") == "scan"]
        initial = scans[0]["window_start"] if scans else None
        capture_text = (root / "capture.txt").read_text().splitlines()
        final_wire = next(
            line.split(" ", 1)[1]
            for line in capture_text
            if line.startswith("capture_final_snapshot ")
        )
        capture(final_wire, 30_000_000)
        episodes = []
        for terminal in terminals:
            episode = terminal["native_episode"]
            journal = root / ("native.journal" if episode == 0 else f"native-{episode}.journal")
            try:
                checked = review(journal.read_bytes(), epoch=terminal["epoch"], rate=30_000_000)
                estimates = checked["estimates"]
                cadence = checked["cadence"]
                review_error = None
            except ValueError as error:
                retained, _ = records(journal.read_bytes())
                raw = [row.payload.decode().split() for row in retained if row.kind == "estimate"]
                estimates = [{"frame": int(row[2]), "rejection": int(row[8])} for row in raw]
                cadence_fields = next(
                    row.payload.decode().split()
                    for row in retained
                    if row.kind == "tracking_cadence"
                )
                cadence = {"stride": int(cadence_fields[1]), "results": int(cadence_fields[3])}
                review_error = str(error)
            assert cadence["stride"] == 10 and cadence["results"] == 751
            first, last = estimates[0]["frame"], estimates[-1]["frame"]
            episodes.append(
                {
                    "episode": episode,
                    "epoch": terminal["epoch"],
                    "attempt": terminal["attempt"],
                    "controller_result": terminal["result"],
                    "measurements": len(estimates),
                    "source_span_s": (last - first) / 750,
                    "first_frame": first,
                    "last_frame": last,
                    "supported": sum(row["rejection"] == 0 for row in estimates),
                    "rejections": dict(Counter(str(row["rejection"]) for row in estimates)),
                    "journal_review": "pass" if review_error is None else "fail",
                    "journal_review_error": review_error,
                    "detection_elapsed_s": (
                        (
                            next(
                                row["window_start"]
                                for row in scans
                                if row["attempt"] == terminal["attempt"]
                            )
                            - initial
                        )
                        / 2_500_000
                    ),
                }
            )
        after = operator["after"]["remote"]
        result["runs"].append(
            {
                "run": name,
                "lo_hz": operator["requested_lo_hz"],
                "capture_duration_s": status["blocks"] * 16384 / 2_500_000,
                "attempts": status["attempts"],
                "handoffs": status["handoffs"],
                "measurements": status["native_results"],
                "episodes": episodes,
                "capture_loss_check": "pass",
                "restored": operator["temporary_files_removed"]
                and after["serial"] == "1040005e0b100007100010000bf33a5d4d"
                and after["firmware"] == "glrt-iq-tracking-r30000000-v1"
                and after["all_buffer_enable"] == "0"
                and after["tx_lo_powerdown"] == "1"
                and after["tx_hardwaregain_db"] == "-80.000000",
            }
        )

    all_episodes = [episode for run in result["runs"] for episode in run["episodes"]]
    result["acceptance"] = {
        "target_source_span_s": 10,
        "target_measurements": 751,
        "completed_episodes": sum(
            episode["measurements"] == 751 and episode["journal_review"] == "pass"
            for episode in all_episodes
        ),
        "longest_source_span_s": max(
            (episode["source_span_s"] for episode in all_episodes), default=0
        ),
        "passed": False,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "sparse_summary.json").write_text(json.dumps(result, indent=2) + "\n")

    fig, axes = plt.subplots(2, 1, figsize=(11, 8), constrained_layout=True)
    labels, spans, supported, review_passed = [], [], [], []
    for run in result["runs"]:
        if not run["episodes"]:
            labels.append(f"{run['run']} (no handoff)")
            spans.append(0)
            supported.append(0)
            review_passed.append(True)
        for episode in run["episodes"]:
            labels.append(f"{run['run']} ep {episode['episode']}")
            spans.append(episode["source_span_s"])
            supported.append(episode["supported"])
            review_passed.append(episode["journal_review"] == "pass")
    y = range(len(labels))
    axes[0].barh(
        list(y), spans, color=["#2563eb" if passed else "#f59e0b" for passed in review_passed]
    )
    axes[0].axvline(10, color="#b91c1c", linestyle="--", label="10 s target")
    axes[0].set_yticks(list(y), labels)
    axes[0].invert_yaxis()
    axes[0].set_xlim(0, 10.7)
    axes[0].set_xlabel("Source-time span (s; one 30-MS/s measurement every 10 frames)")
    axes[0].set_title("Sparse 30-MS/s tracking episodes")
    axes[0].scatter([], [], marker="s", color="#2563eb", label="independent review passes")
    axes[0].scatter([], [], marker="s", color="#f59e0b", label="pre-fix stale authority record")
    axes[0].legend(loc="lower right")
    for index, (span, count) in enumerate(zip(spans, supported, strict=True)):
        axes[0].text(
            span + 0.08, index, f"{span:.3f} s; {count} supported", va="center", fontsize=8
        )

    labels = [f"{run['lo_hz'] / 1e9:.3f} GHz\n{run['run']}" for run in result["runs"]]
    duration = [run["capture_duration_s"] for run in result["runs"]]
    axes[1].bar(labels, duration, color="#d1d5db")
    for index, run in enumerate(result["runs"]):
        for episode in run["episodes"]:
            axes[1].scatter(
                index, episode["detection_elapsed_s"], color="#dc2626", marker="D", zorder=3
            )
        axes[1].text(
            index, duration[index] + 2, f"{run['attempts']} searches", ha="center", fontsize=8
        )
    axes[1].scatter([], [], color="#dc2626", marker="D", label="handoff")
    axes[1].set_ylabel("Exported-IQ dwell time (s)")
    axes[1].set_title("Four-frequency bounded campaign")
    axes[1].legend(loc="upper left")
    fig.savefig(args.output / "sparse_tracking_outcomes.png", dpi=180)


if __name__ == "__main__":
    main()
