"""Diagnostic two-mode Qin double differences on phase-blind sparse candidates."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from leo.analysis.starlink.adaptive_dual_rx_phase_extract import ReceiverPhaseSeed
from leo.analysis.starlink.relative_phase import PairedPilotProbe, extract_relative_phase

HERE = Path(__file__).parent
REPORT = HERE.parent
CACHE = Path("/srv/bulk/leo-dev/scan-32a202-phase-replay-cache/selected-visits/cache-index.json")


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


C = _module("phase_replay_common", REPORT / "common.py")
P = _module("phase_replay_pilot_runner", HERE / "run_pilot.py")


def _admitted(selected_ids):
    grouped = defaultdict(lambda: defaultdict(list))
    with (REPORT / "acquisition/candidate-inventory.csv").open() as stream:
        for row in csv.DictReader(stream):
            visit = int(row["visit_index"])
            if visit in selected_ids and row["passed_0p025_comparison_gate"] == "True":
                grouped[visit][int(row["receiver_id"])].append(row)
    output = {}
    for visit, receivers in grouped.items():
        proposals = []
        for left in receivers.get(0, []):
            for right in receivers.get(1, []):
                left_epoch = int(left["integer_epoch_sample"]) + float(
                    left["fractional_epoch_offset_samples"]
                )
                right_epoch = int(right["integer_epoch_sample"]) + float(
                    right["fractional_epoch_offset_samples"]
                )
                frequency_error = abs(
                    float(left["pilot_relative_canonical_display_cfo_hz"])
                    - float(right["pilot_relative_canonical_display_cfo_hz"])
                )
                if abs(left_epoch - right_epoch) <= 3 and frequency_error <= 2_000:
                    proposals.append((abs(left_epoch - right_epoch), left, right))
        pairs = []
        for _, left, right in sorted(proposals, key=lambda item: item[0]):
            frequency = float(left["pilot_relative_canonical_display_cfo_hz"])
            if any(abs(frequency - prior[2]) < 10_000 for prior in pairs):
                continue
            pairs.append((left, right, frequency))
        if len(pairs) >= 2:
            output[visit] = pairs[:2]
    return output


def _products(visit, selected, pair):
    frames = [
        P._frames(visit.complex64(receiver), pair[receiver], selected["edge"])
        for receiver in (0, 1)
    ]
    output = []
    for left in frames[0]:
        right = min(
            frames[1], key=lambda row: abs(row["reference_sample"] - left["reference_sample"])
        )
        if abs(right["reference_sample"] - left["reference_sample"]) > 3:
            continue
        reference = 0.5 * (left["reference_sample"] + right["reference_sample"])
        restoration = np.exp(
            2j
            * np.pi
            * (right["absolute_cfo_hz"] - left["absolute_cfo_hz"])
            * reference
            / 10_000_000
        )
        product = np.sum(np.conj(left["channel"]) * right["channel"] * restoration)
        output.append((selected["valid_start_counter"] + round(reference), product))
    return output


def main():
    selection = json.loads((REPORT / "selection.json").read_text())
    selected = {row["visit_index"]: row for row in selection["visits"]}
    source = C.CachedReplayVisitSource(CACHE, REPORT / "selection.json")
    modes = _admitted(set(selected))
    rows = []
    simultaneous = []
    failures = []
    for visit_index, pairs in modes.items():
        visit = source.read_visit(visit_index)
        series = [_products(visit, selected[visit_index], pair[:2]) for pair in pairs]
        second = {counter: value for counter, value in series[1]}
        common = [
            (counter, value, second[counter]) for counter, value in series[0] if counter in second
        ]
        for index, (counter, first, other) in enumerate(common):
            rows.append(
                {
                    "visit_index": visit_index,
                    "split": selected[visit_index]["split"],
                    "device_counter_reference": counter,
                    "mode0_display_cfo_hz": pairs[0][2],
                    "mode1_display_cfo_hz": pairs[1][2],
                    "double_difference_rad": float(np.angle(first * np.conj(other))),
                    "deranged_control_rad": float(
                        np.angle(first * np.conj(common[(index + 7) % len(common)][2]))
                    ),
                }
            )
        mode_observations = []
        iq = np.column_stack((visit.complex64(0), visit.complex64(1)))
        for left, right, _ in pairs:
            epoch = [
                int(row["integer_epoch_sample"]) + float(row["fractional_epoch_offset_samples"])
                for row in (left, right)
            ]
            probe = PairedPilotProbe(
                start_sample=0,
                epoch_sample=round(np.mean(epoch)),
                seeds=tuple(
                    ReceiverPhaseSeed(
                        acquired_cfo_hz=float(row["tracking_absolute_baseband_cfo_hz"]),
                        reference_sample=value,
                    )
                    for row, value in zip((left, right), epoch, strict=True)
                ),
            )
            try:
                result = extract_relative_phase(
                    iq, 10_000_000, selected[visit_index]["edge"], [probe]
                )
            except ValueError as error:
                failures.append(
                    {
                        "visit_index": visit_index,
                        "mode_index": len(mode_observations),
                        "reason": str(error),
                    }
                )
                continue
            if result["pilot_rows"]:
                mode_observations.append(result["pilot_rows"][0])
            else:
                failures.append(
                    {
                        "visit_index": visit_index,
                        "mode_index": len(mode_observations),
                        "reason": "production kernel returned no matched pilot row",
                        "pilot_failures": result["pilot_failures"],
                    }
                )
        if len(mode_observations) == 2:
            common_time = float(np.mean([row["time_s"] for row in mode_observations]))
            transported = [
                row["pilot_phase_rad"]
                + 2 * np.pi * row["pilot_residual_frequency_hz"] * (common_time - row["time_s"])
                for row in mode_observations
            ]
            simultaneous.append(
                {
                    "visit_index": visit_index,
                    "device_counter_reference": selected[visit_index]["valid_start_counter"]
                    + round(common_time * 10_000_000),
                    "wrapped_double_difference_rad": float(
                        np.angle(np.exp(1j * (transported[0] - transported[1])))
                    ),
                    "mode_time_separation_samples": abs(
                        mode_observations[0]["time_s"] - mode_observations[1]["time_s"]
                    )
                    * 10_000_000,
                    "variant": "simultaneous_iq_response_normalized_common_time_transport",
                }
            )
    phase = np.asarray([row["double_difference_rad"] for row in rows])
    control = np.asarray([row["deranged_control_rad"] for row in rows])
    document = {
        "schema": "scan-phase-replay-method21-two-mode-diagnostic/v1",
        "status": "diagnostic_candidate_only",
        "phase_blind_two_mode_visits": sorted(modes),
        "selection_policy": {
            "receiver_pair_epoch_tolerance_samples": 3,
            "receiver_pair_canonical_cfo_tolerance_hz": 2000,
            "distinct_mode_minimum_canonical_cfo_separation_hz": 10000,
            "alias_policy": (
                "canonical separation prevents counting a 227272.727 Hz symbol alias "
                "as another emitter"
            ),
            "phase_used_for_selection": False,
        },
        "candidate_pairs": {
            str(visit): [
                {
                    "canonical_cfo_hz": frequency,
                    "receivers": [
                        {
                            key: row[key]
                            for key in (
                                "receiver_id",
                                "candidate_rank",
                                "integer_epoch_sample",
                                "fractional_epoch_offset_samples",
                                "tracking_absolute_baseband_cfo_hz",
                                "pilot_relative_canonical_display_cfo_hz",
                                "pilot_alias_lift",
                            )
                        }
                        for row in (left, right)
                    ],
                }
                for left, right, frequency in pairs
            ]
            for visit, pairs in modes.items()
        },
        "input_hashes": {
            "selection": "sha256:"
            + hashlib.sha256((REPORT / "selection.json").read_bytes()).hexdigest(),
            "candidate_inventory": "sha256:"
            + hashlib.sha256(
                (REPORT / "acquisition/candidate-inventory.csv").read_bytes()
            ).hexdigest(),
        },
        "rows": rows,
        "simultaneous_common_time_rows": simultaneous,
        "simultaneous_kernel_failures": failures,
        "metrics": {
            "row_count": len(rows),
            "double_difference_r": float(abs(np.mean(np.exp(1j * phase)))) if len(phase) else None,
            "deranged_control_r": float(abs(np.mean(np.exp(1j * control))))
            if len(control)
            else None,
        },
        "limitation": (
            "two frequency-separated phase-blind modes are candidates, "
            "not proven distinct emitters; "
            "the same-source/multipath ambiguity remains"
        ),
    }
    (HERE / "method21-two-mode-diagnostic.json").write_text(json.dumps(document, indent=2) + "\n")


if __name__ == "__main__":
    main()
