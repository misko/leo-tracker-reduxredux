"""Full-scan plots from fresh ARM and standard-server detector receipts."""
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
GATE = .025


def read_arm():
    folder = HERE / "arm-v2"
    complete = json.loads((folder / "completion.json").read_text())
    assert complete["status"] == "PASS" and complete["visits"] == 2215
    inventory = json.loads((folder / "inventory.json").read_text())
    assert [item["visit"] for item in inventory] == list(range(2215))
    candidates, runtimes, seen = [], [], set()
    for path in sorted(folder.glob("batch-*.jsonl")):
        begin = int(path.stem.split("-")[1])
        calls = [row["result"] for line in path.read_text().splitlines()
                 if "result" in (row := json.loads(line))]
        assert len(calls) == min(16, 2215 - begin)
        for index, call in enumerate(calls):
            visit = begin + index
            assert visit not in seen and call["sequence"] == index
            seen.add(visit)
            source = inventory[visit]
            assert (call["rate_hz"], call["dwell_ms"], call["stride_ms"]) == (2500000, 120, 120)
            assert [row["receiver_id"] for row in call["rows"]] == [0, 1]
            runtimes.append({"visit": visit, "time": source["capture_time_s"], "ms": call["call_wall_ms"]})
            for row in call["rows"]:
                assert row["probe_index"] == 0 and row["probe_start_ms"] == 0
                assert row["candidate_count"] == len(row["candidates"])
                for rank, candidate in enumerate(row["candidates"]):
                    assert all(math.isfinite(candidate[field]) for field in ("margin", "tracking_cfo_hz", "acquired_cfo_hz"))
                    assert type(candidate["epoch"]) is int
                    candidates.append({"visit": visit, "time": source["capture_time_s"],
                        "rx": row["receiver_id"], "rank": rank,
                        "channel": source["event"]["target"]["channel"],
                        "margin": candidate["margin"], "cfo": candidate["tracking_cfo_hz"],
                        "epoch": candidate["epoch"], "acquired_cfo": candidate["acquired_cfo_hz"],
                        "passing": candidate["margin"] >= GATE})
    assert seen == set(range(2215))
    return inventory, candidates, runtimes


def read_server(inventory):
    candidates, runtimes = [], []
    summary = json.loads((HERE / "server/summary.json").read_text())
    assert summary["schema"] == "org.leo.standard-server-full-scan-summary/v1"
    assert summary["status"] == "pass" and summary["fresh_processing"] is True
    assert summary["visits"] == 2215 and summary["receiver_windows"] == 4430
    dependencies = summary["dependencies"]
    assert dependencies["session_id"] == "scan-fw-f363c7f29141d0b1"
    assert dependencies["recording_manifest_sha256"] == "sha256:b74c950fb172433dab804ddd14b46a3f4c6c1d2e85a09855b0bfdff5da78e015"
    assert dependencies["schedule"] == {
        "dwell_ms": 120, "fallback_anchor_symbols": list(range(2, 302, 14)),
        "margin_gate": GATE, "maximum_candidates": 8, "probe_ms": 20,
        "probe_stride_ms": 120, "sample_rate_hz": 2500000}
    paths = sorted((HERE / "server/visits").glob("visit-*.json"))
    assert len(paths) == len(inventory)
    unavailable = 0
    for source, path in zip(inventory, paths, strict=True):
        receipt = json.loads(path.read_text())
        visit = source["visit"]
        assert receipt["schema"] == "org.leo.standard-server-full-scan-visit/v1"
        assert receipt["task_digest"] == summary["task_digest"]
        assert receipt["visit"] == visit and receipt["status"] == "pass"
        assert receipt["source"]["event"] == source["event"]
        assert receipt["source"]["raw_sha256"] == source["raw_sha256"]
        assert receipt["source"]["raw_bytes"] == 2400000
        assert set(receipt["candidates"]) == {"0", "1"}
        runtimes.append({"visit": visit, "time": source["capture_time_s"],
                         "ms": receipt["timing_s"]["detector_wall"] * 1000})
        for rx in (0, 1):
            rows = receipt["candidates"][str(rx)]
            assert len(rows) == 8
            for rank, candidate in enumerate(rows):
                assert candidate["receiver_id"] == rx and candidate["probe_index"] == 0
                assert candidate["rank"] == rank
                if candidate["fractional_status"] != "complete":
                    assert candidate["fractional_margin"] is None
                    assert not candidate["passed_fractional_margin_gate"]
                    unavailable += 1
                    continue
                margin, cfo = candidate["fractional_margin"], candidate["fractional_tracking_cfo_hz"]
                assert math.isfinite(margin) and math.isfinite(cfo)
                assert math.isfinite(candidate["acquired_cfo_hz"]) and type(candidate["epoch"]) is int
                assert (margin >= GATE) == candidate["passed_fractional_margin_gate"]
                candidates.append({"visit": visit, "time": source["capture_time_s"],
                    "rx": rx, "rank": rank, "channel": source["event"]["target"]["channel"],
                    "margin": margin, "cfo": cfo, "epoch": candidate["epoch"],
                    "acquired_cfo": candidate["acquired_cfo_hz"], "passing": margin >= GATE})
    assert len(candidates) + unavailable == summary["candidates"]
    assert sum(point["passing"] for point in candidates) == summary["passing_candidates"]
    return candidates, runtimes, unavailable


def match_passing(arm, server):
    """Existing diagnostic rule: one-to-one greedy epoch<=2 samples, CFO<=10kHz."""
    groups = [defaultdict(list), defaultdict(list)]
    for output, values in zip(groups, (arm, server)):
        for point in values:
            if point["passing"]:
                output[point["visit"], point["rx"]].append(point)
    matches = []
    for key in sorted(groups[0].keys() | groups[1].keys()):
        left, right = groups[0][key], groups[1][key]
        edges = []
        for i, a in enumerate(left):
            for j, b in enumerate(right):
                delta = abs(a["epoch"] - b["epoch"]) % 3333
                epoch = min(delta, 3333 - delta)
                cfo = abs(a["acquired_cfo"] - b["acquired_cfo"])
                if epoch <= 2 and cfo <= 10000:
                    edges.append((epoch, cfo, i, j))
        used_left, used_right = set(), set()
        for epoch, cfo, i, j in sorted(edges):
            if i in used_left or j in used_right:
                continue
            used_left.add(i); used_right.add(j)
            matches.append({"visit": key[0], "rx": key[1],
                "arm_rank": left[i]["rank"], "server_rank": right[j]["rank"],
                "epoch_delta_samples": epoch, "acquired_cfo_delta_hz": cfo})
    return matches


def plot_science(arm, server, duration, field, ylabel, filename, passing_only=False):
    fig, axes = plt.subplots(2, 2, figsize=(14, 8), sharex=True, sharey=True, layout="constrained")
    labels = ("Optimized ordinary ARM", "Standard server")
    colors = {1: "#3264AD", 2: "#E58C2F", 3: "#27916C", 4: "#A354A1"}
    for column, (label, points) in enumerate(zip(labels, (arm, server))):
        for rx in (0, 1):
            ax = axes[rx, column]
            for channel, color in colors.items():
                subset = [point for point in points if point["rx"] == rx and
                          point["channel"] == channel and (not passing_only or point["passing"])]
                values = [point[field] / (1000 if field == "cfo" else 1) for point in subset]
                ax.scatter([point["time"] for point in subset], values, s=5, alpha=.55,
                           linewidths=0, color=color, label=f"CH{channel}", rasterized=True)
            if field == "margin":
                ax.axhline(GATE, color="#B53B42", linestyle="--", linewidth=1, label="Gate 0.025")
            score = "integer score" if column == 0 else "fractional score"
            ax.set_title(f"{label}\nRX{rx} · {score}")
            ax.set_xlim(0, duration)
            ax.grid(alpha=.15)
            ax.set_ylabel(ylabel)
            if rx == 1:
                ax.set_xlabel("Original dwell start time relative to first dwell (s)")
            if rx == 0:
                ax.legend(ncols=5 if field == "margin" else 4, fontsize=8, loc="upper right")
    fig.suptitle("Full saved DS9 scan · 2,215 dwells · 2.5 MS/s · first 20 ms/RX every dwell", fontsize=15)
    fig.supxlabel("Candidates are placed at their original probe/dwell start; same IQ, different acquisition/scoring algorithms.", fontsize=10)
    fig.savefig(HERE / (filename + ".png"), dpi=180, bbox_inches="tight")
    fig.savefig(HERE / (filename + ".pdf"), bbox_inches="tight")
    plt.close(fig)


def plot_counts_runtime(arm, server, arm_times, server_times, duration):
    fig, axes = plt.subplots(2, 1, figsize=(13, 7), layout="constrained")
    bins = np.arange(0, math.ceil(duration) + 1, 1)
    for label, candidates, times, color in (
            ("Optimized ordinary ARM", arm, arm_times, "#3264AD"),
            ("Standard server", server, server_times, "#E58C2F")):
        counts, _ = np.histogram([p["time"] for p in candidates if p["passing"]], bins)
        axes[0].stairs(counts, bins, color=color, label=f"{label}: {sum(counts):,} passing candidates")
        axes[1].scatter([p["time"] for p in times], [p["ms"] for p in times],
                        s=5, alpha=.5, color=color, label=label)
    axes[0].set(ylabel="Passing candidates / 1 s", title="GLRT detections across the complete recorded scan")
    axes[1].axhline(120, color="#B53B42", linestyle="--", label="120 ms dwell duration")
    axes[1].set(ylabel="Detector wall time per dwell (ms)", xlabel="Original dwell start time relative to first dwell (s)")
    for ax in axes:
        ax.set_xlim(0, duration); ax.grid(alpha=.15); ax.legend(fontsize=9)
    fig.supxlabel("Runtime scopes are recorded in the report; ARM transfer/preload excluded. One execution per dwell, no live RF.", fontsize=9)
    fig.savefig(HERE / "counts-and-runtime.png", dpi=180)
    fig.savefig(HERE / "counts-and-runtime.pdf")
    plt.close(fig)


def main():
    inventory, arm, arm_times = read_arm()
    server, server_times, unavailable = read_server(inventory)
    duration = inventory[-1]["capture_time_s"] + .120
    plot_science(arm, server, duration, "margin", "GLRT margin", "glrt-vs-time")
    plot_science(arm, server, duration, "cfo", "Tracking CFO (kHz)", "detections-vs-time", True)
    plot_counts_runtime(arm, server, arm_times, server_times, duration)
    matches = match_passing(arm, server)
    passing_arm = sum(p["passing"] for p in arm)
    passing_server = sum(p["passing"] for p in server)

    def distribution(times):
        values = np.array([point["ms"] for point in times])
        assert np.isfinite(values).all() and (values >= 0).all()
        return {"mean_ms": float(values.mean()), "median_ms": float(np.median(values)),
                "p95_ms": float(np.quantile(values, .95, method="higher")),
                "maximum_ms": float(values.max()), "sum_detector_s": float(values.sum() / 1000),
                "at_least_120ms": int((values >= 120).sum())}

    summary = {"session": "scan-fw-f363c7f29141d0b1", "visits": len(inventory),
        "receiver_windows": 2 * len(inventory), "capture_span_s": duration,
        "all_raw_and_event_authority_equal": True,
        "arm": {"retained_candidates": len(arm), "passing_candidates": passing_arm,
                "runtime": distribution(arm_times)},
        "server": {"retained_candidates": len(server) + unavailable,
                   "complete_fractional_candidates": len(server),
                   "unavailable_fractional_candidates": unavailable,
                   "passing_candidates": passing_server, "runtime": distribution(server_times)},
        "diagnostic_matching": {"rule": "Passing-only one-to-one greedy; circular integer epoch <=2 samples (period3333), acquired CFO <=10000Hz; not rank equality or false-positive classification",
            "matched_passing_candidates": len(matches),
            "server_passing_recovery_fraction": len(matches) / passing_server if passing_server else None},
        "scope": "Fresh saved full scan; ARM ordinary integer vs standard server fractional algorithms; no live capture or pipeline location qualification"}
    (HERE / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n")
    (HERE / "matched-passing.json").write_text(json.dumps(matches, indent=2) + "\n")
    hashes = {str(path.relative_to(HERE)): hashlib.sha256(path.read_bytes()).hexdigest()
              for pattern in ("arm-v2/batch-*.jsonl", "server/visits/visit-*.json",
                              "server/summary.json", "arm-v2/inventory.json", "arm-v2/completion.json")
              for path in sorted(HERE.glob(pattern))}
    (HERE / "comparison-input-hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
