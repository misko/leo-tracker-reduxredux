"""Archive saved-IQ ARM measurements, not radio data or deployed binaries."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

RUN = Path("/tmp/leo-pending240-real-iq-v2.IBKRmm")
CORPUS = Path("/tmp/leo-dwell-worker-20260908-vg66yo9u")


def collect(archive, sha, figures):
    prepared = json.loads((RUN / "prepared.json").read_bytes())
    result = json.loads((RUN / "arm-results.json").read_bytes())
    assert result["completed"] and result["all_candidates_match_desktop"]
    assert result["original_dwells"] == len(prepared["rows"]) == 96
    assert result["executions"] == len(result["results"]) == 288
    assert result["prepared_sha256"] == sha((RUN / "prepared.json").read_bytes())
    assert result["script_sha256"] == sha((RUN / "run_arm.py").read_bytes())
    assert prepared["source_script_sha256"] == sha((RUN / "prepare.py").read_bytes())
    names = [
        "prepared.json",
        "arm-results.json",
        "arm-preflight.json",
        "arm-postflight.json",
        "prepare.py",
        "run_arm.py",
        "arm-dwell-replay.build.json",
        "desktop-dwell-replay.build.json",
        "legacy-dwell-replay.build.json",
        "all-deploy-tests.xml",
        "scanner-integration.xml",
        "scanner-integration-configured.xml",
    ] + [f"arm-batch-{i:02}.json" for i in range(16)]
    originals = [archive(RUN / name, "saved-iq/" + name) for name in names]
    # Preserve the frozen comparison configuration and its original references.
    # Raw .pack/.rank IQ and executable payloads are intentionally not published.
    for rate in (2500000, 5000000):
        manifest = CORPUS / str(rate) / "manifest.json"
        assert sha(manifest.read_bytes()) == prepared["source_sha256"][str(manifest)]
        originals.append(archive(manifest, f"saved-iq/frozen-{rate}.json"))
    summary = {}
    fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
    for rate, color in ((2500000, "#217b91"), (5000000, "#b94b5b")):
        times = np.array(
            [
                row["result"]["total_wall_ms"]
                for row in result["results"]
                if row["result"]["rate_hz"] == rate
            ]
        )
        assert len(times) == 144 and np.all(np.isfinite(times)) and np.all(times > 0)
        rows = [r for r in prepared["rows"] if r["metadata"]["rate_hz"] == rate]
        stats = dict(
            zip(
                ("p50", "p95", "p99", "max"),
                map(float, np.percentile(times, [50, 95, 99, 100])),
                strict=True,
            )
        )
        summary[str(rate)] = dict(
            wall_ms=stats,
            dwells=len(rows),
            executions=len(times),
            current_positive=sum(r["positive_gate"] for r in rows),
            frozen_positive=sum(r["legacy_positive_gate"] for r in rows),
        )
        ax.step(
            np.sort(times),
            np.arange(1, 145) * 100 / 144,
            where="post",
            color=color,
            label=f"{rate / 1e6:g} MS/s: median {stats['p50']:.1f}, p99 {stats['p99']:.1f} ms",
        )
    ax.axvline(120, color="#59626a", linestyle="--", label="120 ms dwell duration")
    ax.set(
        xlabel="Direct numerical detector wall time on radio ARM (ms)",
        ylabel="Cumulative executions (%)",
        ylim=(0, 102),
        xlim=(40, 126),
    )
    ax.grid(alpha=0.2)
    ax.legend(loc="lower right")
    fig.suptitle("Saved real RX1 IQ: 96 dwells, 288 ARM executions", fontsize=15)
    fig.supxlabel(
        "No streaming/IRQ contention or RF collection; not live capture duty or recall.",
        fontsize=10,
    )
    fig.savefig(figures / "saved-iq-arm-timing.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    return originals, summary
