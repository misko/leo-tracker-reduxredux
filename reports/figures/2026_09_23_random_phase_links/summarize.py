"""Summarize the random-group phase-link replay across sample rates."""

from __future__ import annotations

import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent


def _median(values):
    return None if not values else float(np.median(values))


def run() -> None:
    with gzip.open(ROOT / "comparison.json.gz", "rt") as source:
        comparison = json.load(source)
    rows = []
    by_rate = defaultdict(list)
    for source in comparison["rows"]:
        output = {
            "session_id": source["session_id"],
            "visit": source["visit"],
            "sample_rate_msps": source["sample_rate_hz"] / 1e6,
            "state": source["state"],
            "supported": False,
            "tracked_coherence": None,
            "wrong_pair_coherence": None,
            "band_phase_resultant": None,
            "conditional_composite_log_factor": None,
            "applied_phase_log_factor": None,
            "shared_candidate_weights_equal": None,
            "link_score_state": None,
            "reason": source.get("reason"),
        }
        if source["state"] == "replayed":
            phase = source["random_phase"]
            score = source["association_research_score"]
            diagnostic = score["phase_only_diagnostic"]
            link = diagnostic["links"][0]
            hypotheses = score["applied_hypothesis_weights"]
            output.update(
                supported=bool(phase["supported"]),
                tracked_coherence=float(phase["tracked_coherence"]),
                wrong_pair_coherence=float(phase["wrong_pair_coherence"]),
                band_phase_resultant=float(phase["band_phase_resultant"]),
                conditional_composite_log_factor=float(link["conditional_composite_log_factor"]),
                applied_phase_log_factor=float(hypotheses[0]["phase_log_factor"]),
                shared_candidate_weights_equal=bool(
                    np.isclose(
                        hypotheses[0]["normalized_conditional_weight"],
                        hypotheses[1]["normalized_conditional_weight"],
                    )
                ),
                link_score_state=link["state"],
            )
        rows.append(output)
        by_rate[output["sample_rate_msps"]].append(output)

    summary = []
    for rate, group in sorted(by_rate.items()):
        replayed = [item for item in group if item["state"] == "replayed"]
        supported = [item for item in replayed if item["supported"]]
        summary.append(
            {
                "sample_rate_msps": rate,
                "selected_count": len(group),
                "replayed_count": len(replayed),
                "failure_count": len(group) - len(replayed),
                "supported_count": len(supported),
                "median_tracked_coherence": _median(
                    [item["tracked_coherence"] for item in replayed]
                ),
                "median_wrong_pair_coherence": _median(
                    [item["wrong_pair_coherence"] for item in replayed]
                ),
                "median_supported_conditional_composite_log_factor": _median(
                    [item["conditional_composite_log_factor"] for item in supported]
                ),
                "all_shared_candidate_weights_equal": all(
                    item["shared_candidate_weights_equal"] for item in replayed
                ),
            }
        )
    (ROOT / "summary.json").write_text(
        json.dumps(
            {
                "seed": comparison["seed"],
                "validation": "random whole 20 ms groups; A predicts held B",
                "interpretation": "capture-level common-waveform evidence only",
                "source_binding": "unavailable without candidate membership or isolation",
                "geometric_phase_claimed": False,
                "satellite_identity_claimed": False,
                "rates": summary,
            },
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
    with (ROOT / "per-dwell.csv").open("w", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=tuple(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    figure, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    colors = {2.5: "#0072B2", 10.0: "#E69F00", 15.0: "#009E73"}
    for rate, group in sorted(by_rate.items()):
        replayed = [item for item in group if item["state"] == "replayed"]
        for supported, marker in ((True, "o"), (False, "x")):
            selected = [item for item in replayed if item["supported"] is supported]
            axes[0].scatter(
                [item["wrong_pair_coherence"] for item in selected],
                [item["tracked_coherence"] for item in selected],
                label=f"{rate:g} MS/s {'pass' if supported else 'fail'}",
                color=colors[rate],
                marker=marker,
            )
            axes[1].scatter(
                [rate] * len(selected),
                [item["applied_phase_log_factor"] for item in selected],
                color=colors[rate],
                marker=marker,
            )
    limit = max(axes[0].get_xlim()[1], axes[0].get_ylim()[1])
    axes[0].plot([0, limit], [0, limit], color="0.5", linestyle="--", linewidth=1)
    axes[0].set(xlabel="Wrong-pair coherence", ylabel="Same-link coherence")
    axes[0].legend(frameon=False)
    axes[1].axhline(0, color="0.5", linewidth=1)
    axes[1].set(
        xlabel="Sample rate (MS/s)",
        ylabel="Applied capture-link composite log factor",
    )
    figure.suptitle("Random-group held-B receiver-link validation")
    figure.savefig(ROOT / "random-phase-links-by-rate.png", dpi=180)
    plt.close(figure)


if __name__ == "__main__":
    run()
