#!/usr/bin/env python3
"""Summarize the four bounded 30-MS/s coarse-authority qualification runs."""
from __future__ import annotations

import argparse
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
    from tools.starlink_glrt_tracking_journal import review

    manifest = {}
    for line in (args.evidence / "SHA256SUMS").read_text().splitlines():
        sha, name = line.split("  ", 1)
        manifest[name] = sha

    result = {"schema": "radio20-30ms-coarse-authority-review/v1", "runs": []}
    for number in (3, 4, 5, 6):
        name = f"run-v{number}"
        root = args.evidence / name
        files = sorted(path for path in root.iterdir() if path.is_file())
        assert all(manifest[f"{name}/{path.name}"] == digest(path) for path in files)
        status = json.loads((root / "stdout.json").read_text())
        operator = json.loads((root / "operator.json").read_text())
        rows = [json.loads(line) for line in (root / "worker.jsonl").read_text().splitlines()]
        scans = [row for row in rows if row.get("kind") == "scan"]
        terminals = [row for row in rows if row.get("kind") == "native_terminal"]
        observer = [json.loads(line) for line in (root / "observer.jsonl").read_text().splitlines()]
        measurements = [row for row in observer if row.get("kind") == "measurement"]

        capture_text = (root / "capture.txt").read_text().splitlines()
        final_wire = next(line.split(" ", 1)[1] for line in capture_text
                          if line.startswith("capture_final_snapshot "))
        capture(final_wire, 30_000_000)

        episodes = []
        for terminal in terminals:
            episode = terminal["native_episode"]
            journal_name = "native.journal" if episode == 0 else f"native-{episode}.journal"
            checked = review((root / journal_name).read_bytes(), epoch=terminal["epoch"], rate=30_000_000)
            episode_measurements = [row for row in measurements if row["episode"] == episode]
            episodes.append({
                "episode": episode,
                "epoch": terminal["epoch"],
                "attempt": terminal["attempt"],
                "controller_result": terminal["result"],
                "fpga_results": len(checked["heads"]),
                "source_duration_s": len(checked["heads"]) / 750,
                "native_supported": checked["supported"],
                "coarse_measurements": len(episode_measurements),
                "coarse_supported": sum(row["accepted"] for row in episode_measurements),
                "detection_elapsed_s": ((next(row["window_start"] for row in scans
                                                if row["attempt"] == terminal["attempt"])
                                           - scans[0]["window_start"]) / 2_500_000),
            })

        after = operator["after"]["remote"]
        result["runs"].append({
            "run": name,
            "probe_status": status["status"],
            "capture_duration_s": status["blocks"] * 16384 / 2_500_000,
            "attempts": status["attempts"],
            "handoffs": status["handoffs"],
            "native_results": status["native_results"],
            "episodes": episodes,
            "capture_loss_check": "pass",
            "restored": operator["temporary_files_removed"]
                        and after["serial"] == "1040005e0b100007100010000bf33a5d4d"
                        and after["firmware"] == "glrt-iq-tracking-r30000000-v1"
                        and after["all_buffer_enable"] == "0"
                        and after["tx_lo_powerdown"] == "1"
                        and after["tx_hardwaregain_db"] == "-80.000000",
        })

    result["acceptance"] = {
        "required_source_duration_s": 10,
        "required_repeat_count": 2,
        "observed_complete_count": sum(
            episode["source_duration_s"] >= 10
            for run in result["runs"] for episode in run["episodes"]),
        "passed": False,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")

    fig, axes = plt.subplots(2, 1, figsize=(11, 7.5), constrained_layout=True)
    labels, widths, colors, annotations = [], [], [], []
    for run in result["runs"]:
        if not run["episodes"]:
            labels.append(run["run"] + " (no handoff)")
            widths.append(0)
            colors.append("#9ca3af")
            annotations.append("0")
        for episode in run["episodes"]:
            labels.append(f"{run['run']} episode {episode['episode']}")
            widths.append(episode["source_duration_s"])
            fraction = episode["native_supported"] / episode["fpga_results"]
            colors.append(plt.cm.viridis(0.2 + 0.7 * fraction))
            annotations.append(f"{episode['fpga_results']} results; {episode['native_supported']} native-supported")
    y = list(range(len(labels)))
    axes[0].barh(y, widths, color=colors)
    axes[0].axvline(10, color="#b91c1c", linestyle="--", label="10 s acceptance target")
    axes[0].set_yticks(y, labels)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("Tracked signal time (s at 750 FPGA measurements/s)")
    axes[0].set_title("Continuous scheduled FPGA episodes")
    axes[0].legend(loc="lower right")
    for index, (width, label) in enumerate(zip(widths, annotations, strict=True)):
        axes[0].text(max(width, 0.03) + 0.08, index, label, va="center", fontsize=8)
    axes[0].set_xlim(0, 10.8)

    run_labels = [run["run"] for run in result["runs"]]
    durations = [run["capture_duration_s"] for run in result["runs"]]
    axes[1].bar(run_labels, durations, color="#d1d5db", label="30-MS/s qualification dwell")
    for index, run in enumerate(result["runs"]):
        for episode in run["episodes"]:
            axes[1].scatter(index, episode["detection_elapsed_s"], color="#dc2626", marker="D", zorder=3)
        axes[1].text(index, durations[index] + 3, f"{run['attempts']} searches", ha="center", fontsize=8)
    axes[1].scatter([], [], color="#dc2626", marker="D", label="handoff")
    axes[1].set_ylabel("Elapsed exported-IQ time (s)")
    axes[1].set_title("Handoffs within each bounded dwell")
    axes[1].legend(loc="upper left")
    fig.savefig(args.output / "tracking_outcomes.png", dpi=180)


if __name__ == "__main__":
    main()
