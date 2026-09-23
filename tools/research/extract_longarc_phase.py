"""Replay fixed pilot frame opportunities from a sealed long-arc source binding."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

import leo.analysis.qam.pilot as pilot_module
import leo.analysis.starlink.templates as template_module
from leo.analysis.qam.pilot import estimate_edge_pilot_frame_complex_split
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def serial(value):
    if isinstance(value, dict):
        return {key: serial(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(item) for item in value]
    if isinstance(value, np.ndarray):
        return serial(value.tolist())
    if isinstance(value, complex):
        return [value.real, value.imag]
    if isinstance(value, np.generic):
        return serial(value.item())
    return value


def frame_opportunities(sample_count, rate, epoch):
    """Four adjacent complete frames nearest each 20ms group center, IQ-blind."""
    content = round(302 * rate * OFDM_SYMBOL_DURATION_S)
    group_samples = round(rate * 0.02)
    output = []
    for group in range(sample_count // group_samples):
        left, right = group * group_samples, (group + 1) * group_samples
        frames = [epoch + round(offset * rate / 750) for offset in range(-100, 101)]
        frames = [start for start in frames if left <= start - 1 and start + content + 1 <= right]
        if len(frames) < 4:
            raise ValueError("group has fewer than four complete pilot frame opportunities")
        center = (left + right) / 2
        index = min(
            range(len(frames) - 3),
            key=lambda i: abs((frames[i] + frames[i + 3] + content) / 2 - center),
        )
        output.extend((group, start) for start in frames[index : index + 4])
    return output


def save(path, value):
    with gzip.open(path, "wt") as target:
        json.dump(serial(value), target, allow_nan=False, separators=(",", ":"))


def run(binding_path, output, limit):
    binding = json.loads(binding_path.read_text())
    output.mkdir(parents=True, exist_ok=True)
    checkpoints = output / "rows"
    checkpoints.mkdir(exist_ok=True)
    protocol = dict(
        binding_sha256=digest(binding_path),
        source_sha256={
            "extractor": digest(__file__),
            "pilot": digest(pilot_module.__file__),
            "templates": digest(template_module.__file__),
        },
        frame_policy=(
            "four adjacent full frames nearest each whole20ms center; no IQ-dependent choice"
        ),
        seed_policy=(
            "frozen GLRT acquired, refined, and historically lifted native CFO; deduplicate"
        ),
        inner_calibration_groups=[0, 3, 5],
        inner_response_groups=[1, 2, 4],
        outer_partition="binding.phase_random_whole_visit_partition",
        phase_continuity_across_visits=False,
        fractional_epoch_corrected=False,
    )
    identity = hashlib.sha256(json.dumps(protocol, sort_keys=True).encode()).hexdigest()
    outer = {
        r["visit_index"]: r["partition"]
        for r in binding["phase_random_whole_visit_partition"]["rows"]
    }
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    rows = []
    processed = 0
    try:
        with AdaptiveHopAnalysisInputStore(store).source(binding["session_id"]) as source:
            if source.input_manifest_sha256 != binding["source_input_manifest_sha256"]:
                raise ValueError("capture binding changed")
            for bound in binding["observations"]:
                path = checkpoints / f"visit-{bound['visit_index']}.json.gz"
                if path.exists():
                    with gzip.open(path, "rt") as saved:
                        row = json.load(saved)
                    if row["protocol_sha256"] != identity:
                        raise ValueError("stale checkpoint: use a fresh output directory")
                    rows.append(row)
                    continue
                if processed >= limit:
                    break
                if source.visits[bound["iq_ordinal"]].event.visit_index != bound["visit_index"]:
                    raise ValueError("IQ ordinal no longer identifies bound visit")
                iq = source.read_visit(bound["iq_ordinal"])
                rate = binding["sample_rate_hz"]
                epoch = round(bound["probe_start_ms"] * rate / 1000) + bound["integer_epoch_sample"]
                opportunities = frame_opportunities(len(iq), rate, epoch)
                if {group for group, _ in opportunities} != set(range(6)):
                    raise ValueError("expected six complete 20ms groups per dwell")
                seeds = list(
                    dict.fromkeys(
                        [
                            bound["acquired_cfo_hz"],
                            bound["fractional_tracking_cfo_hz"],
                            bound["fractional_tracking_cfo_hz"]
                            + bound["historical_pilot_alias_index"] / 4.4e-6,
                        ]
                    )
                )
                branches = []
                content = round(302 * rate * OFDM_SYMBOL_DURATION_S)
                for seed in seeds:
                    frames = []
                    for group, start in opportunities:
                        measured = estimate_edge_pilot_frame_complex_split(
                            iq[start - 1 : start + content + 1, bound["receiver_id"]],
                            rate,
                            frame_start_sample=start,
                            acquisition_absolute_cfo_hz=seed,
                            edge=bound["edge"],
                        )
                        relative_counter = (
                            bound["valid_start_counter"]
                            - binding["source_first_counter"]
                            + measured.reference_sample
                        )
                        frames.append(
                            dict(
                                group_id=group,
                                frame=serial(asdict(measured)),
                                session_time_s=relative_counter / rate,
                            )
                        )
                    # Local calibration is an explicit input even for an outer-held visit;
                    # constellation parameters may not learn from that visit's response.
                    group_scores = []
                    for group in protocol["inner_calibration_groups"]:
                        group_scores.append(
                            np.mean(
                                [
                                    r["frame"]["even"]["coherence_margin"]
                                    if r["frame"]["even"]
                                    and not r["frame"]["even"]["search_boundary"]
                                    else 0.0
                                    for r in frames
                                    if r["group_id"] == group
                                ]
                            )
                        )
                    branches.append(
                        dict(
                            seed_cfo_hz=seed,
                            calibration_even_margin=float(np.mean(group_scores)),
                            frames=frames,
                        )
                    )
                chosen = int(np.argmax([b["calibration_even_margin"] for b in branches]))
                row = dict(
                    protocol_sha256=identity,
                    observation=bound,
                    outer_partition=outer[bound["visit_index"]],
                    iq_sha256=hashlib.sha256(iq.tobytes()).hexdigest(),
                    iq_shape=list(iq.shape),
                    selected_seed_index=chosen,
                    branches=branches,
                )
                save(path, row)
                rows.append(row)
                processed += 1
                print(
                    bound["visit_index"],
                    outer[bound["visit_index"]],
                    len(seeds),
                    round(branches[chosen]["calibration_even_margin"], 5),
                    flush=True,
                )
    finally:
        store.close()
    save(
        output / "frames.json.gz",
        dict(
            protocol=protocol,
            protocol_sha256=identity,
            expected_visit_count=len(binding["observations"]),
            completed_visit_count=len(rows),
            rows=rows,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--binding",
        type=Path,
        default=Path("reports/figures/2026_09_23_longarc_phase/binding.json"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("reports/figures/2026_09_23_longarc_phase/replay")
    )
    parser.add_argument("--limit", type=int, default=78)
    args = parser.parse_args()
    run(args.binding, args.output, args.limit)
