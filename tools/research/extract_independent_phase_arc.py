"""Extract pilot frames from only the fresh-training independent arc visits."""

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
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from tools.research.extract_longarc_phase import frame_opportunities


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def training_rows(binding: dict) -> list[dict]:
    partition = {
        row["visit_index"]: row["partition"] for row in binding["fresh_random_whole_visit_split"]
    }
    observations = {row["visit_index"]: row for row in binding["observations"]}
    if set(partition) != set(observations):
        raise ValueError("fresh split and bound observations differ")
    selected = [observations[index] for index, role in partition.items() if role == "train"]
    if len(selected) != 15 or sum(role == "held" for role in partition.values()) != 12:
        raise ValueError("expected frozen 15/12 fresh split")
    return selected


def seed_values(observation: dict) -> list[float]:
    dealiased_native = observation["normalized_cfo_hz"] / observation["rf_normalization_scale"]
    if abs(dealiased_native - observation["dealiased_native_cfo_hz"]) > 1e-6:
        raise ValueError("bound dealiased native CFO changed")
    values = [
        observation["acquired_cfo_hz"],
        observation["fractional_tracking_cfo_hz"],
        dealiased_native,
    ]
    return list(dict.fromkeys(values))


def run(binding_path: Path, output_path: Path, bulk_root: Path) -> None:
    if output_path.exists():
        raise ValueError("fresh output path required")
    binding = json.loads(binding_path.read_text())
    selected = training_rows(binding)
    protocol = {
        "binding_sha256": digest(binding_path),
        "source_sha256": {
            "extractor": digest(Path(__file__)),
            "pilot": digest(Path(pilot_module.__file__)),
            "templates": digest(Path(template_module.__file__)),
        },
        "read_scope": "only 15 fresh-random train visits; 12 fresh-held and 19 old-reserved unread",
        "frame_policy": "four adjacent complete frames nearest each whole20ms group center",
        "inner_calibration_groups": [0, 3, 5],
        "inner_diagnostic_groups": [1, 2, 4],
        "seed_policy": (
            "deduplicated acquired, refined, and dealiased-native normalized_cfo/scale; "
            "relative_alias_index is provenance and is not arithmetically added"
        ),
        "fractional_epoch_corrected": False,
        "fractional_epoch_policy": (
            "preserve canonical integer frame lattice; prior timing sensitivity was negative"
        ),
    }
    source_store = AdaptiveHopIqStore(bulk_root, read_only=True)
    rows = []
    try:
        with AdaptiveHopAnalysisInputStore(source_store).source(binding["session_id"]) as source:
            if source.input_manifest_sha256 != binding["input_manifest_sha256"]:
                raise ValueError("capture manifest changed")
            geometry = source.receipt.plan.geometry
            if geometry.sample_rate_hz != binding["sample_rate_hz"]:
                raise ValueError("sample rate changed")
            for observation in selected:
                if (
                    source.visits[observation["iq_ordinal"]].event.visit_index
                    != observation["visit_index"]
                ):
                    raise ValueError("IQ ordinal no longer binds the visit")
                iq = source.read_visit(observation["iq_ordinal"])
                receiver_column = geometry.receiver_ids.index(observation["receiver_id"])
                if geometry.receiver_ids != (0, 1) or iq.shape[1] != 2:
                    raise ValueError("receiver column contract changed")
                rows.append(_extract_row(binding, observation, iq, receiver_column, protocol))
    finally:
        source_store.close()
    payload = {
        "schema": "independent-training-phase-frames/v1",
        "protocol": protocol,
        "completed_train_visits": len(rows),
        "fresh_held_visits_read": 0,
        "old_reserved_visits_read": 0,
        "summary": {
            "calibration_even_eligible_counts": [
                row["frame_coverage"]["calibration_even_eligible"] for row in rows
            ],
            "diagnostic_odd_eligible_counts": [
                row["frame_coverage"]["diagnostic_odd_eligible"] for row in rows
            ],
            "zero_calibration_even_visits": sum(
                row["frame_coverage"]["calibration_even_eligible"] == 0 for row in rows
            ),
            "zero_diagnostic_odd_visits": sum(
                row["frame_coverage"]["diagnostic_odd_eligible"] == 0 for row in rows
            ),
            "diagnostic_exact_coherence_mean": float(
                np.mean([row["train_odd_diagnostic"]["exact_coherence"] for row in rows])
            ),
            "diagnostic_control_coherence_mean": float(
                np.mean([row["train_odd_diagnostic"]["control_coherence"] for row in rows])
            ),
        },
        "rows": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output_path, "xt") as stream:
        json.dump(serial(payload), stream, allow_nan=False, separators=(",", ":"))


def _extract_row(binding, observation, iq, receiver_column, protocol):
    rate = binding["sample_rate_hz"]
    epoch = round(observation["probe_start_ms"] * rate / 1000) + observation["integer_epoch_sample"]
    opportunities = frame_opportunities(len(iq), rate, epoch)
    if len(opportunities) != 24 or {group for group, _ in opportunities} != set(range(6)):
        raise ValueError("expected 24 opportunities across six groups")
    branches = []
    for seed in seed_values(observation):
        frames = []
        content = round(302 * rate * template_module.OFDM_SYMBOL_DURATION_S)
        for group, start in opportunities:
            measured = estimate_edge_pilot_frame_complex_split(
                iq[start - 1 : start + content + 1, receiver_column],
                rate,
                frame_start_sample=start,
                acquisition_absolute_cfo_hz=seed,
                edge=observation["edge"],
            )
            frames.append(
                {
                    "group_id": group,
                    "frame": serial(asdict(measured)),
                    "session_time_s": (
                        observation["valid_start_counter"]
                        - binding["source_first_counter"]
                        + measured.reference_sample
                    )
                    / rate,
                }
            )
        group_margin = []
        for group in protocol["inner_calibration_groups"]:
            values = [
                row["frame"]["even"]["coherence_margin"]
                if row["frame"]["even"] is not None and not row["frame"]["even"]["search_boundary"]
                else 0.0
                for row in frames
                if row["group_id"] == group
            ]
            group_margin.append(float(np.mean(values)))
        branches.append(
            {
                "seed_cfo_hz": seed,
                "calibration_even_margin": float(np.mean(group_margin)),
                "frames": frames,
            }
        )
    chosen = int(np.argmax([branch["calibration_even_margin"] for branch in branches]))
    diagnostic = [
        row["frame"]["odd"]
        for row in branches[chosen]["frames"]
        if row["group_id"] in protocol["inner_diagnostic_groups"]
        and row["frame"]["odd"] is not None
    ]
    calibration_eligible = sum(
        row["group_id"] in protocol["inner_calibration_groups"]
        and row["frame"]["training_supported"]
        and row["frame"]["even"] is not None
        for row in branches[chosen]["frames"]
    )
    diagnostic_eligible = sum(
        row["group_id"] in protocol["inner_diagnostic_groups"]
        and row["frame"]["training_supported"]
        and row["frame"]["odd"] is not None
        for row in branches[chosen]["frames"]
    )
    return {
        "observation": observation,
        "selected_seed_index": chosen,
        "branches": branches,
        "train_odd_diagnostic": {
            "frame_count": len(diagnostic),
            "exact_coherence": float(np.mean([item["exact_coherence"] for item in diagnostic])),
            "control_coherence": float(np.mean([item["control_coherence"] for item in diagnostic])),
        },
        "frame_coverage": {
            "calibration_even_opportunities": 12,
            "calibration_even_eligible": calibration_eligible,
            "diagnostic_odd_opportunities": 12,
            "diagnostic_odd_eligible": diagnostic_eligible,
        },
        "iq_sha256": hashlib.sha256(iq.tobytes()).hexdigest(),
        "iq_shape": list(iq.shape),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--binding",
        type=Path,
        default=Path("reports/figures/2026_09_23_independent_phase/binding.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/figures/2026_09_23_independent_phase/train-frames.json.gz"),
    )
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    args = parser.parse_args()
    run(args.binding, args.output, args.bulk_root)
