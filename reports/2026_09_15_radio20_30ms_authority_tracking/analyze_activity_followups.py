#!/usr/bin/env python3
"""Summarize retained radio-local activity/follow-up qualification cycles."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_passes(root: Path) -> bool:
    manifest = root / "SHA256SUMS"
    if not manifest.exists():
        return False
    for row in manifest.read_text().splitlines():
        expected, name = row.split("  ", 1)
        if sha256(root / name) != expected:
            return False
    return True


def json_lines(path: Path) -> list[dict]:
    return [json.loads(row) for row in path.read_text().splitlines()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_root", type=Path)
    parser.add_argument("raid_root", type=Path)
    parser.add_argument("firmware_repo", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.firmware_repo))
    from tools.starlink_glrt_tracking_journal import review

    result = {"schema": "radio20-30ms-activity-followup-review/v1", "cycles": []}
    for number in range(1, 14):
        name = f"activity-followup-20260915-v{number}"
        root = args.evidence_root / name
        if not root.exists():
            root = args.evidence_root.parent / name
        if not root.exists():
            continue
        operator = json.loads((root / "operator.json").read_text())
        raw_parent = root / "stdout.json"
        parent = json.loads(raw_parent.read_text()) if raw_parent.exists() and raw_parent.stat().st_size else operator.get("parent")
        los = operator["los"]
        children = []
        retained = root / "retained/evidence"
        if retained.exists():
            for child in sorted(retained.glob("visit-*"), key=lambda p: int(p.name[6:])):
                index = int(child.name[6:])
                status = json.loads((child / "stdout.json").read_text())
                rows = json_lines(child / "worker.jsonl")
                powers = [value for row in rows if row.get("kind") == "candidate_order"
                          for value in row.get("single_pilot_power", [])]
                episodes = []
                for terminal in (row for row in rows if row.get("kind") == "native_terminal"):
                    episode = terminal["native_episode"]
                    journal = child / ("native.journal" if episode == 0 else f"native-{episode}.journal")
                    checked = review(journal.read_bytes(), epoch=terminal["epoch"], rate=30_000_000)
                    estimates = checked["estimates"]
                    episodes.append({
                        "episode": episode,
                        "epoch": terminal["epoch"],
                        "controller_result": terminal["result"],
                        "measurements": len(estimates),
                        "supported": sum(row["rejection"] == 0 for row in estimates),
                        "rejections": dict(Counter(str(row["rejection"]) for row in estimates)),
                        "source_span_s": ((estimates[-1]["frame"] - estimates[0]["frame"]) / 750
                                          if len(estimates) > 1 else 0),
                        "faults": checked["final"].faults,
                        "cdc_drops": checked["final"].cdc_drops,
                        "pacer_drops": checked["final"].pacer_drops,
                        "journal_review": "pass",
                    })
                children.append({
                    "visit": index,
                    "role": "followup" if index == len(los) else "scout",
                    "lo_hz": los[parent["selected_index"]] if index == len(los) else los[index],
                    "blocks": status["blocks"],
                    "source_duration_s": status["blocks"] * 16384 / 2_500_000,
                    "attempts": status["attempts"],
                    "handoffs": status["handoffs"],
                    "native_results": status["native_results"],
                    "native_completed_runs": status["native_completed_runs"],
                    "reacquisitions": status["reacquisitions"],
                    "maximum_single_pilot_power": max(powers, default=None),
                    "episodes": episodes,
                })
        result["cycles"].append({
            "cycle": f"v{number}",
            "operator_status": operator["status"],
            "los_hz": los,
            "parent": parent,
            "children": children,
            "retained_evidence": retained.exists(),
            "ssd_manifest_pass": manifest_passes(root),
            "raid_manifest_pass": manifest_passes(args.raid_root / name),
            "radio_restored": operator.get("radio_restored", False),
        })

    complete = [cycle for cycle in result["cycles"] if cycle["parent"] and cycle["parent"]["track_complete"]]
    episodes = [episode for cycle in result["cycles"] for child in cycle["children"]
                for episode in child["episodes"]]
    result["acceptance"] = {
        "target_measurements": 751,
        "target_source_span_s": 10,
        "completed_cycles": len(complete),
        "followup_cycles": sum(bool(cycle["parent"] and cycle["parent"]["followup_started"])
                               for cycle in result["cycles"]),
        "longest_episode_measurements": max((episode["measurements"] for episode in episodes), default=0),
        "longest_episode_source_span_s": max((episode["source_span_s"] for episode in episodes), default=0),
        "passed": bool(complete),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "activity_followup_summary.json").write_text(json.dumps(result, indent=2) + "\n")

    cycles = [cycle for cycle in result["cycles"] if cycle["parent"]]
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), constrained_layout=True)
    labels = [cycle["cycle"] for cycle in cycles]
    colors = ["#16a34a" if cycle["parent"]["track_complete"] else
              "#f59e0b" if cycle["parent"]["followup_started"] else "#94a3b8" for cycle in cycles]
    maxima = [max((child["maximum_single_pilot_power"] or 0 for child in cycle["children"]
                   if child["role"] == "scout"), default=0) for cycle in cycles]
    axes[0].bar(labels, maxima, color=colors)
    axes[0].axhline(0.04, color="#b91c1c", linestyle="--", label="retained-activity trigger (0.04)")
    axes[0].set_ylabel("Maximum retained single-pilot power")
    axes[0].set_title("Radio-local 30-MS/s activity cycles")
    axes[0].legend(loc="upper right")

    episode_rows = [(cycle["cycle"], episode) for cycle in cycles for child in cycle["children"]
                    for episode in child["episodes"]]
    names = [f"{cycle} ep {episode['episode']}" for cycle, episode in episode_rows]
    spans = [episode["source_span_s"] for _, episode in episode_rows]
    supported = [episode["supported"] for _, episode in episode_rows]
    axes[1].barh(names, spans, color="#2563eb")
    axes[1].axvline(10, color="#b91c1c", linestyle="--", label="10 s target")
    axes[1].invert_yaxis(); axes[1].set_xlim(0, 10.5)
    axes[1].set_xlabel("FPGA episode source-time span (s)")
    axes[1].set_title("Triggered sparse follow-up episodes")
    axes[1].legend(loc="lower right")
    for index, ((_, episode), span, count) in enumerate(zip(episode_rows, spans, supported, strict=True)):
        long = span > 9
        axes[1].text(span - 0.08 if long else span + 0.08, index,
                     f"{episode['measurements']} results; {count} supported",
                     ha="right" if long else "left", va="center", fontsize=8,
                     color="white" if long else "black")
    fig.savefig(args.output / "activity_followup_outcomes.png", dpi=180)


if __name__ == "__main__":
    main()
