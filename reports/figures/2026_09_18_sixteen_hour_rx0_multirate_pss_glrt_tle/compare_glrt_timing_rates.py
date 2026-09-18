#!/usr/bin/env python3
"""Matched-policy known-delay GLRT timing check across retained scanner rates."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from leo.analysis.starlink.refinement_comparison import (
    comparison_errors,
    score_profiles,
    select_candidate,
    timing_difference,
)
from leo.contracts.scanner_refinement import ComparisonEvidenceV2
from leo.storage.scanner_refinement_source import comparison_source

RATES = (10_000_000, 15_000_000, 20_000_000)


def chosen_sessions(input_dir: Path) -> dict[int, list[str]]:
    with (input_dir / "sessions.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    result = {}
    for rate in RATES:
        ids = [r["session_id"] for r in rows if int(r["sample_rate_hz"]) == rate]
        indices = np.linspace(0, len(ids) - 1, 3).round().astype(int)
        result[rate] = [ids[i] for i in indices]
    return result


def delay(values: np.ndarray, rate: int, delay_ns: float) -> np.ndarray:
    phase = np.exp(
        -2j * np.pi * np.fft.fftfreq(len(values), 1 / rate) * delay_ns * 1e-9
    )
    return np.fft.ifft(np.fft.fft(values) * phase)


def selected_epoch(values: np.ndarray, rate: int, edge: str, phase: float | None):
    crop = round(rate * 0.0005)
    profiles, _ = score_profiles(values[crop : crop + rate // 50], rate, edge)
    return select_candidate(profiles["grid512"][0], phase)


def main(input_dir: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    inventory = chosen_sessions(input_dir)
    # Reuse every standardized 10 MS/s known-shift product in the cohort. This
    # is the same grid512 method below and avoids weakening that rate to three
    # arbitrarily sparse sessions.
    ten_ids = {
        r["session_id"]
        for r in csv.DictReader((input_dir / "sessions.csv").open())
        if int(r["sample_rate_hz"]) == 10_000_000
    }
    for session_id in sorted(ten_ids):
        path = Path("/srv/bulk/leo/scanner-refinement-comparisons") / session_id / "evidence.json"
        if not path.exists():
            continue
        evidence = ComparisonEvidenceV2.model_validate(json.loads(path.read_text()))
        for error in comparison_errors(evidence.rows):
            if error["case"] != "delay" or error["profile"] != "grid512":
                continue
            rows.append(
                {
                    "sample_rate_hz": 10_000_000,
                    "session_id": session_id,
                    "probe_id": error["probe_id"],
                    "target_index": "",
                    "injected_delay_ns": "",
                    "recovered": error["recovered"],
                    "delay_error_ns": error.get("delay_ns"),
                }
            )

    for rate, sessions in inventory.items():
        if rate == 10_000_000:
            continue
        for session_id in sessions:
            with comparison_source(Path("/srv/bulk/leo"), session_id) as source:
                # Retain the first scheduled interior visit for every target that
                # actually appears; sparse firmware captures may omit one target.
                probes = []
                seen_targets = set()
                for probe_id in source.probe_ids:
                    probe = source.read_probe(probe_id)
                    if probe.target_index not in seen_targets:
                        probes.append(probe)
                        seen_targets.add(probe.target_index)
                for probe in probes:
                    probe_id = probe.probe_id
                    seed = int(hashlib.sha256(("glrt-rate-delay-v1:" + probe_id).encode()).hexdigest()[:16], 16)
                    injected_ns = float(np.random.default_rng(seed).uniform(-300, 300))
                    baseline = selected_epoch(probe.samples, rate, probe.edge, None)
                    shifted = selected_epoch(
                        delay(probe.samples, rate, injected_ns),
                        rate,
                        probe.edge,
                        baseline.integer_epoch_s if baseline else None,
                    )
                    recovered = baseline is not None and shifted is not None
                    error_ns = None
                    if recovered:
                        error_ns = (
                            timing_difference(shifted.epoch_s, baseline.epoch_s) * 1e9
                            - injected_ns
                        )
                    rows.append(
                        {
                            "sample_rate_hz": rate,
                            "session_id": session_id,
                            "probe_id": probe_id,
                            "target_index": probe.target_index,
                            "injected_delay_ns": injected_ns,
                            "recovered": recovered,
                            "delay_error_ns": error_ns,
                        }
                    )
                    print(rate, session_id, probe_id, recovered, error_ns, flush=True)

    with (output / "glrt-timing-rate-probes.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {}
    for rate in RATES:
        group = [r for r in rows if r["sample_rate_hz"] == rate]
        errors = np.asarray([r["delay_error_ns"] for r in group if r["recovered"]], dtype=float)
        summary[str(rate)] = {
            "sessions": sorted({r["session_id"] for r in group}),
            "attempted": len(group),
            "recovered": len(errors),
            "recovery_percent": 100 * len(errors) / len(group),
            "delay_error_rms_ns": float(np.sqrt(np.mean(errors**2))) if len(errors) else None,
            "delay_error_median_absolute_ns": float(np.median(np.abs(errors))) if len(errors) else None,
            "delay_error_p90_absolute_ns": float(np.percentile(np.abs(errors), 90)) if len(errors) else None,
        }
    (output / "glrt-timing-rate-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    labels = ["10", "15", "20"]
    data = [
        [r["delay_error_ns"] for r in rows if r["sample_rate_hz"] == rate and r["recovered"]]
        for rate in RATES
    ]
    axes[0].boxplot(data, tick_labels=labels, showmeans=True)
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set_xlabel("Native capture rate (MS/s)")
    axes[0].set_ylabel("Recovered minus injected delay (ns)")
    axes[0].set_title("Conditional GLRT edge-pilot timing error")
    axes[0].grid(axis="y", alpha=0.25)
    axes[1].bar(
        labels,
        [summary[str(r)]["recovery_percent"] for r in RATES],
        color=["#1676a3", "#d28c28", "#6b8e23"],
    )
    axes[1].set_ylim(0, 100)
    axes[1].set_xlabel("Native capture rate (MS/s)")
    axes[1].set_ylabel("Known-delay probes recovered (%)")
    axes[1].set_title("Estimator availability on the same selection policy")
    for i, rate in enumerate(RATES):
        value = summary[str(rate)]
        axes[1].text(
            i,
            value["recovery_percent"] + 2,
            f'{value["recovered"]}/{value["attempted"]}',
            ha="center",
        )
    fig.suptitle("Fractional GLRT timing: deterministic retained-IQ known-delay check")
    fig.tight_layout()
    fig.savefig(output / "glrt-timing-by-sample-rate.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.input, args.output)
