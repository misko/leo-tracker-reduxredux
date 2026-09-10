"""Archive the completed controlled-timing experiment and render its figures."""

import gzip
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RUN = Path("/tmp/leo-fair-long-replay.orZxJT/final")
FIGURES = REPO / "reports/figures/2026_09_10_scanner_fair_long_replay"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def archive(source, name, *, data=None):
    if data is None:
        data = source.read_bytes()
    target = HERE / (name + ".gz")
    compressed = gzip.compress(data, mtime=0)
    if target.exists():
        assert target.read_bytes() == compressed, "refuse to replace original evidence"
    else:
        with target.open("xb") as stream:
            stream.write(compressed)
    return {"path": name + ".gz", "original_bytes": len(data), "original_sha256": sha(data)}


def main():
    receipt = json.loads((RUN / "receipt.json").read_bytes())
    assert receipt["completed"] and len(receipt["cases"]) == 12
    originals = [archive(RUN / "receipt.json", "receipt.json")]
    # Preserve the tested baseline, not subsequently edited working-tree files.
    for name, expected in receipt["sources"].items():
        data = subprocess.check_output(
            ["git", "show", "c9c34213e384091979d84c246a33001dcc8fd630:" + name], cwd=REPO
        )
        assert sha(data) == expected
        originals.append(archive(None, "source-" + name.replace("/", "--"), data=data))
    results = []
    for case in receipt["cases"]:
        path = RUN / case["path"]
        assert sha(path.read_bytes()) == case["sha256"]
        row = json.loads(path.read_bytes())
        assert row["sampled_model"]["exact_dispatch_agreement"]
        assert not row["actual"]["starved_targets"]
        assert not row["actual"]["protection"]["disabled"]
        assert sha((REPO / row["snapshot_path"]).read_bytes()) == row["snapshot_sha256"]
        results.append(row)
        originals.append(archive(path, path.parent.name + ".json"))
    for name in ("sdk.so.build.json", "worker.build.json"):
        originals.append(archive(RUN / "build" / name, name))
    regression = RUN.parent / "regression.xml"
    suite = ET.fromstring(regression.read_bytes()).find("testsuite")
    assert suite.get("tests") == "91"
    assert all(suite.get(key) == "0" for key in ("errors", "failures", "skipped"))
    originals.append(archive(regression, "regression.xml"))
    # Preserve the discovered artificial-clock regression, not as a passing gate.
    originals.append(
        archive(Path("/tmp/leo-fair-gated-harness-tests.xml"), "before-clock-correction.xml")
    )
    figures(results)
    tracked = [p for p in HERE.iterdir() if p.is_file() and p.name != "index.json"]
    tracked += list(FIGURES.glob("*.png"))
    index = {
        "scope": receipt["scope"],
        "originals": originals,
        "files": [
            {
                "path": str(p.relative_to(REPO)),
                "bytes": p.stat().st_size,
                "sha256": sha(p.read_bytes()),
            }
            for p in sorted(tracked)
        ],
    }
    with (HERE / "index.json").open("w") as stream:
        json.dump(index, stream, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {
                "files": len(tracked),
                "cases": len(results),
                "checked": sum(r["actual"]["screened"] for r in results),
                "visits": sum(r["actual"]["visits"] for r in results),
            }
        )
    )


def figures(results):
    FIGURES.mkdir(parents=True, exist_ok=True)
    sessions = list(dict.fromkeys(r["session_id"] for r in results))
    rates = {r["session_id"]: r["sample_rate_hz"] / 1e6 for r in results}
    labels = [f"{rates[s]:g} MS/s\n{s[9:15]}" for s in sessions]
    x = np.arange(len(sessions))
    fig, axes = plt.subplots(2, 1, figsize=(11.5, 7.5), sharex=True, constrained_layout=True)
    for j, (profile, title, color) in enumerate(
        (
            ("median", "Constant median cost", "#227c9d"),
            ("p99", "Constant p99 cost", "#e59c38"),
            ("resampled_jitter", "Resampled costs + owner jitter", "#7d5ba6"),
        )
    ):
        rows = [
            next(r for r in results if r["session_id"] == s and r["profile"] == profile)
            for s in sessions
        ]
        axes[0].bar(
            x + (j - 1) * 0.25,
            [r["actual"]["screening_percent"] for r in rows],
            width=0.23,
            color=color,
            label=title,
        )
        axes[1].bar(
            x + (j - 1) * 0.25,
            [
                max(t["maximum_source_screen_gap_ms"] for t in r["actual"]["per_target"]) / 1000
                for r in rows
            ],
            width=0.23,
            color=color,
        )
    axes[0].set(ylabel="Detector dispatch coverage (%)", ylim=(0, 110))
    axes[0].legend(loc="upper center", ncols=3, fontsize=9)
    axes[1].set(ylabel="Worst target source gap (s)", xticks=x, xticklabels=labels, ylim=(0, 4.7))
    axes[1].axhline(2.5, color="#666666", ls="--", lw=1, label="Freshness trigger, not a guarantee")
    axes[1].legend(loc="upper left", fontsize=9)
    for ax in axes:
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
    fig.suptitle(
        "Full 300-second saved schedules through the actual fair SDK\n"
        "Synthetic IQ and controlled timing — not live duty or RF recall",
        fontsize=14,
    )
    fig.savefig(FIGURES / "coverage-and-freshness.png", dpi=160)
    plt.close(fig)
    selected = next(
        r
        for r in results
        if r["session_id"] == "scan-hop-b5521c5e306d0bd3" and r["profile"] == "resampled_jitter"
    )
    fig, ax = plt.subplots(figsize=(12, 4.6), constrained_layout=True)
    for target in range(8):
        times = [
            c["ready_ms"] / 1000 for c in selected["actual"]["checks"] if c["target"] == target
        ]
        ax.scatter(times, [target] * len(times), marker="|", s=70, color="#227c9d")
    ax.set(
        xlim=(0, 301),
        yticks=range(8),
        yticklabels=[f"CH{i % 4 + 1}{'L' if i < 4 else 'U'}" for i in range(8)],
        xlabel="Source time since first retained dwell (s)",
        ylabel="Checked target",
    )
    ax.grid(axis="x", alpha=0.2)
    ax.set_title(
        "5 MS/s jitter scenario: every target continues receiving checks\n"
        "Markers are synthetic replay admissions, not signal detections or satellite tracks"
    )
    fig.savefig(FIGURES / "jitter-target-checks.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
