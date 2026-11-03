"""Plot fresh single-dwell ARM runs; verify all non-timing row fields first."""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def call(name):
    entries = [json.loads(line) for line in (HERE / name).read_text().splitlines()]
    calls = [entry["result"] for entry in entries if "result" in entry]
    assert len(calls) == 1
    result = calls[0]
    assert (result["rate_hz"], result["dwell_ms"], result["stride_ms"]) == (2500000, 120, 120)
    assert [row["receiver_id"] for row in result["rows"]] == [0, 1]
    return result


def science(result):
    return [{key: value for key, value in row.items() if key != "timings_ms"}
            for row in result["rows"]]


def main():
    control, optimized = (call("signal-" + name + ".jsonl") for name in ("control", "ordinary"))
    assert science(control) == science(optimized), "Scientific output mismatch"
    quiet_control, quiet_optimized = (call(name + ".jsonl") for name in ("control", "ordinary"))
    assert science(quiet_control) == science(quiet_optimized)
    selection = json.loads((HERE / "signal-selection.json").read_text())
    case = selection["case"]
    actual_hash = (HERE / "signal-input-hash.log").read_text().split()[0]
    assert actual_hash == case["raw_sha256"]
    colors = ("#3264AD", "#E58C2F")
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    fig.suptitle("Original ARM detector: native control vs optimized ordinary\n"
                 f"DS9 visit {case['visit_index']} · 2.5 MS/s · 20 ms probe per RX in a 120 ms dwell",
                 fontsize=15)
    for rx, ax in enumerate(axes[0]):
        rows = [result["rows"][rx]["candidates"] for result in (control, optimized)]
        x = np.arange(len(rows[0]))
        for index, (label, candidates) in enumerate(zip(("Native control", "Optimized ordinary"), rows)):
            ax.bar(x + (index - .5) * .35, [c["margin"] for c in candidates],
                   width=.35, color=colors[index], label=label)
        ax.axhline(.025, color="#B53B42", linestyle="--", label="Passing gate: 0.025")
        ax.set(title=f"RX{rx}: candidate GLRT margins", xlabel="Candidate rank", ylabel="Exact score − control score")
        ax.set_xticks(x)
        ax.set_ylim(0, max(c["margin"] for c in rows[0]) * 1.25)
        ax.grid(axis="y", alpha=.18)
        ax.legend(fontsize=8)
    ax = axes[1, 0]
    for rx, color in enumerate(("#3264AD", "#27916C")):
        candidates = control["rows"][rx]["candidates"]
        x = [c["epoch"] / 2500 for c in candidates]
        y = [c["tracking_cfo_hz"] / 1000 for c in candidates]
        ax.scatter(x, y, facecolors="none", edgecolors=color, s=120, label=f"RX{rx} control")
        other = optimized["rows"][rx]["candidates"]
        ax.scatter([c["epoch"] / 2500 for c in other],
                   [c["tracking_cfo_hz"] / 1000 for c in other],
                   marker="x", color=color, s=60, label=f"RX{rx} optimized")
    ax.set(title="Candidate coordinates overlap exactly", xlabel="Detector epoch (ms)", ylabel="Tracking CFO (kHz)")
    ax.grid(alpha=.18)
    ax.legend(fontsize=8)
    ax = axes[1, 1]
    times = [result["call_wall_ms"] for result in (control, optimized)]
    bars = ax.bar(["Native control", "Optimized ordinary"], times, color=colors, width=.55)
    ax.bar_label(bars, labels=[f"{time:.2f} ms" for time in times], padding=5)
    ax.axhline(120, color="#B53B42", linestyle="--", label="120 ms dwell budget")
    ax.set(title=f"Detector call: {times[0] / times[1]:.2f}× speedup", ylabel="Wall time (ms)", ylim=(0, 140))
    ax.grid(axis="y", alpha=.18)
    ax.legend(fontsize=8, loc="lower left")
    fig.supxlabel("One fresh call per build on PLUTO+ · saved IQ · setup/file preload excluded · signal-selected example, not a timing distribution", fontsize=9)
    fig.savefig(HERE / "comparison.png", dpi=180)
    fig.savefig(HERE / "comparison.pdf")
    summary = {
        "session_id": case["session_id"], "visit": case["visit_index"],
        "all_nontiming_rows_exact": True,
        "retained_candidates": sum(len(row["candidates"]) for row in control["rows"]),
        "passing_candidates": sum(c["margin"] >= .025 for row in control["rows"] for c in row["candidates"]),
        "control_wall_ms": times[0], "optimized_wall_ms": times[1], "speedup": times[0] / times[1],
        "quiet_example": {"all_nontiming_rows_exact": True,
                          "control_wall_ms": quiet_control["call_wall_ms"],
                          "optimized_wall_ms": quiet_optimized["call_wall_ms"],
                          "candidate_count": sum(len(r["candidates"]) for r in quiet_control["rows"])},
        "scope": "Two saved dwells, one call per build per dwell; no RF or full-scan qualification",
        "result_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in HERE.glob("*.jsonl")},
    }
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
