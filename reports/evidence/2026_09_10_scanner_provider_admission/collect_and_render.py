"""Reproduce saved-evidence admission cases; GET-only API collection, no radio.

JSON outputs are create-only. For offline rerender, supply --offline and fresh
--output-root / --figure-root directories. Snapshots remain in this directory.
The simulated worker never evaluates IQ or assigns signal labels.
"""

import argparse
import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import matplotlib
import matplotlib.pyplot as plt
import numpy as np

from tools.evaluate_scanner_admission import evaluate

matplotlib.use("Agg")


ROOT = Path(__file__).parent
FIGURES = ROOT.parents[1] / "figures/2026_09_10_scanner_provider_admission"
CASES = (
    ("scan-hop-b5521c5e306d0bd3", "saved"),
    ("scan-hop-bef2de33984fbfd1", "persistent"),
    ("scan-hop-ff2ddd107a031611", "persistent"),
    ("scan-hop-125ccf74f6736019", "adaptive"),
)


def save_json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output-root", type=Path, default=ROOT)
    parser.add_argument("--figure-root", type=Path, default=FIGURES)
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    summaries = []
    for session, kind in CASES:
        path = ROOT / f"{session}.json.gz"
        if not path.exists():
            if kind == "saved":
                original = ROOT.parent / "2026_09_10_scanner_cooperative_skips_checkpoint"
                payload = (original / "production-snapshot.json.gz").read_bytes()
            else:
                if args.offline:
                    raise ValueError(f"offline snapshot missing: {session}")
                responses = {}
                prefix = "adaptive" if kind == "adaptive" else "persistent"
                detail_version = "v1" if kind == "adaptive" else "v3"
                with httpx.Client(base_url="http://127.0.0.1:8090", timeout=30) as client:
                    for name, url in {
                        "detail": f"/api/{detail_version}/scanner/{prefix}-sessions/{session}",
                        "glrt": f"/api/v1/scanner/{prefix}-sessions/{session}/glrt",
                    }.items():
                        response = client.get(url)
                        response.raise_for_status()
                        responses[name] = {
                            "path": url,
                            "status": response.status_code,
                            "response_sha256": hashlib.sha256(response.content).hexdigest(),
                            "body": response.json(),
                        }
                payload = gzip.compress(
                    json.dumps(
                        {
                            "observed_utc": datetime.now(UTC).isoformat(),
                            "scope": "GET-only published metadata; no new IQ hashing or RF",
                            "responses": responses,
                        }
                    ).encode(),
                    mtime=0,
                )
            with path.open("xb") as stream:
                stream.write(payload)
        source = path.read_bytes()
        result = evaluate(json.loads(gzip.decompress(source)))
        result["snapshot_sha256"] = hashlib.sha256(source).hexdigest()
        with (args.output_root / f"{session}-model.json.gz").open("xb") as stream:
            stream.write(gzip.compress(json.dumps(result, allow_nan=False).encode(), mtime=0))
        for scenario in result["scenarios"]:
            scenario.pop("checks")
        summaries.append(result)
    save_json(args.output_root / "summary.json", summaries)
    args.figure_root.mkdir(parents=True, exist_ok=True)
    labels = ["CH1L", "CH2L", "CH3L", "CH4L", "CH1U", "CH2U", "CH3U", "CH4U"]
    first = summaries[0]
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), constrained_layout=True)
    choices = [("Observed deployed", first["observed"])]
    names = {
        "immediate": "Model: idle-only / every 2nd",
        "every_3": "Model: every 3rd",
        "oldest_target_one_pending": "Model: oldest target, one pending",
        "freshness_guard_one_pending": "Model: freshness guard, one pending",
    }
    for scenario in first["scenarios"]:
        if (
            scenario["cost_basis"] == "wall_median"
            and scenario["additional_serial_reserve_ms"] == 20
            and scenario["policy"] in names
        ):
            choices.append((names[scenario["policy"]], scenario))
    x = np.arange(8)
    for i, (name, scenario) in enumerate(choices):
        offset = (i - 2) * 0.16
        axes[0].bar(
            x + offset,
            [t["screening_percent"] for t in scenario["per_target"]],
            width=0.15,
            label=name,
        )
        axes[1].bar(
            x + offset,
            [t["maximum_source_screen_gap_ms"] / 1000 for t in scenario["per_target"]],
            width=0.15,
            label=name,
        )
    axes[0].set_ylabel("Screened dwells (%)")
    axes[0].set_ylim(0, 105)
    axes[0].legend(fontsize=8, ncol=2)
    axes[1].set_ylabel("Longest source screening gap (s; log)")
    axes[1].set_yscale("log")
    for ax in axes:
        ax.set_xticks(x, labels)
        ax.grid(axis="y", alpha=0.2)
    fig.suptitle(
        "Saved 5 MS/s schedule: capture coverage is not screening freshness\n"
        "Models assume median worker wall time + 20 ms serial reserve; not live results"
    )
    fig.savefig(args.figure_root / "target-admission.png", dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(11, 6), constrained_layout=True)
    markers = ["o", "s", "^", "D"]
    colors = {name: f"C{i}" for i, name in enumerate(names)}
    for j, result in enumerate(summaries):
        for scenario in result["scenarios"]:
            policy = scenario["policy"]
            if policy not in names or policy == "immediate":
                continue
            ax.scatter(
                scenario["screening_percent"],
                max(t["maximum_source_screen_gap_ms"] for t in scenario["per_target"]) / 1000,
                color=colors[policy],
                marker=markers[j],
                alpha=0.75,
                label=(
                    f"{result['sample_rate_hz'] / 1e6:g} MS/s "
                    f"{result['session_id'][-4:]} · {policy}"
                ),
            )
    handles, text = ax.get_legend_handles_labels()
    unique = dict(zip(text, handles, strict=True))
    ax.legend(unique.values(), unique.keys(), fontsize=6, ncol=2)
    ax.set_xlabel("Model admitted dwell coverage (%)")
    ax.set_ylabel("Worst target source screening gap (s; log)")
    ax.set_yscale("log")
    ax.grid(alpha=0.2)
    ax.set_title(
        "Four saved schedules, median / p99 wall cost, +0 / +20 ms reserve\n"
        "Each point is a counterfactual scenario, not measured detector performance"
    )
    fig.savefig(args.figure_root / "coverage-freshness-tradeoff.png", dpi=160)
    plt.close(fig)
    print(
        json.dumps(
            {"sessions": len(summaries), "scenarios": sum(len(s["scenarios"]) for s in summaries)}
        )
    )


if __name__ == "__main__":
    main()
