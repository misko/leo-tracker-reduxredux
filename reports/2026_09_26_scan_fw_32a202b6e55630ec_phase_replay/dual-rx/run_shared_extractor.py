"""Run the historical simultaneous-IQ dual-RX pilot extractor on fixed windows."""

from __future__ import annotations

import csv
import importlib.util
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from leo.analysis.starlink.adaptive_dual_rx_phase_extract import (
    ReceiverPhaseSeed,
    extract_dual_receiver_phase_with_offset_authority_shared_residual,
)
from leo.analysis.starlink.templates import FRAME_RATE_HZ

HERE = Path(__file__).parent
REPORT = HERE.parent
CACHE = Path("/srv/bulk/leo-dev/scan-32a202-phase-replay-cache/selected-visits/cache-index.json")
RATE = 10_000_000


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


C = _module("phase_replay_common_shared", REPORT / "common.py")


def _primary(selected_ids: set[int]) -> dict[int, tuple[dict, dict]]:
    grouped = defaultdict(lambda: defaultdict(list))
    with (REPORT / "acquisition/candidate-inventory.csv").open() as stream:
        for row in csv.DictReader(stream):
            visit = int(row["visit_index"])
            if visit in selected_ids and row["passed_0p025_comparison_gate"] == "True":
                grouped[visit][int(row["receiver_id"])].append(row)
    output = {}
    for visit, receivers in grouped.items():
        if 0 not in receivers or 1 not in receivers:
            continue
        output[visit] = tuple(
            max(
                receivers[rx],
                key=lambda row: (float(row["fractional_margin"]), -int(row["candidate_rank"])),
            )
            for rx in (0, 1)
        )
    return output


def _admitted(selected_ids: set[int]) -> dict[int, list[tuple[dict, dict, float]]]:
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
                frequency_error = abs(float(left["pilot_relative_canonical_display_cfo_hz"])
                                      - float(right["pilot_relative_canonical_display_cfo_hz"]))
                if abs(_epoch(left) - _epoch(right)) <= 3 and frequency_error <= 2_000:
                    proposals.append((abs(_epoch(left) - _epoch(right)), left, right))
        pairs = []
        for _, left, right in sorted(proposals, key=lambda item: item[0]):
            frequency = float(left["pilot_relative_canonical_display_cfo_hz"])
            if any(abs(frequency - prior[2]) < 10_000 for prior in pairs):
                continue
            pairs.append((left, right, frequency))
        if len(pairs) >= 2:
            output[visit] = pairs[:2]
    return output


def _epoch(row: dict) -> float:
    return int(row["integer_epoch_sample"]) + float(row["fractional_epoch_offset_samples"])


def _extract(iq, edge, pair, start: int, stop: int, *, rx1_shift: int = 0):
    center_global = 0.5 * (start + stop)
    epoch_global = float(np.mean([_epoch(row) for row in pair]))
    period = RATE / FRAME_RATE_HZ
    epoch_near = epoch_global + round((center_global - epoch_global) / period) * period
    local_epoch = round(epoch_near - start)
    seeds = tuple(
        ReceiverPhaseSeed(
            acquired_cfo_hz=float(row["tracking_absolute_baseband_cfo_hz"]),
            reference_sample=_epoch(row) - start,
        )
        for row in pair
    )
    authority = seeds[1].acquired_cfo_hz - seeds[0].acquired_cfo_hz
    values = iq[start:stop]
    if rx1_shift:
        values = values.copy()
        values[:, 1] = iq[start + rx1_shift : stop + rx1_shift, 1]
    result = extract_dual_receiver_phase_with_offset_authority_shared_residual(
        values,
        RATE,
        edge,
        local_epoch,
        seeds,
        authority,
        common_reference_sample=center_global - start,
        frame_radius=max(2, math.ceil((stop - start) / period / 2)),
    ).observation
    # The extractor reports phase at its weighted frame center. Transport to the
    # declared physical midpoint so every mode and control shares one epoch.
    phase = result.wrapped_phase_rad + 2 * np.pi * result.relative_frequency_hz * (
        (center_global - start) - result.center_sample
    ) / RATE
    return {
        "phase_rad": float(np.angle(np.exp(1j * phase))),
        "resultant_length": result.resultant_length,
        "frame_count": result.independent_frame_count,
        "relative_frequency_hz": result.relative_frequency_hz,
        "fitted_center_global_sample": start + result.center_sample,
        "common_reference_global_sample": center_global,
        "authority_hz": authority,
    }


def main() -> None:
    selection = json.loads((REPORT / "selection.json").read_text())
    selected = {row["visit_index"]: row for row in selection["visits"]}
    primary = _primary(set(selected))
    modes = _admitted(set(selected))
    source = C.CachedReplayVisitSource(CACHE, REPORT / "selection.json")
    rows = []
    failures = []
    for visit_index, pair in primary.items():
        visit = source.read_visit(visit_index)
        iq = np.column_stack((visit.complex64(0), visit.complex64(1)))
        for duration_ms in (23, 47, 95):
            width = duration_ms * 10_000
            for start in range(0, 1_200_000 - width + 1, width):
                try:
                    exact = _extract(iq, selected[visit_index]["edge"], pair, start, start + width)
                    control_start = start + 200_000
                    if control_start + width > 1_200_000:
                        control_start = start - 200_000
                    wrong = _extract(
                        iq, selected[visit_index]["edge"], pair,
                        control_start, control_start + width,
                    )
                    rx_shift = 4093 if start + width + 4093 <= 1_200_000 else -4093
                    wrong_rx = _extract(
                        iq, selected[visit_index]["edge"], pair, start, start + width,
                        rx1_shift=rx_shift,
                    )
                except ValueError as error:
                    failures.append({"visit_index": visit_index, "duration_ms": duration_ms,
                                     "start_sample": start, "reason": str(error)})
                    continue
                rows.append({
                    "visit_index": visit_index,
                    "split": selected[visit_index]["split"],
                    "duration_ms": duration_ms,
                    "start_sample": start,
                    "device_counter_reference": selected[visit_index]["valid_start_counter"]
                    + round(exact["common_reference_global_sample"]),
                    "exact": exact,
                    "wrong_time_20ms": wrong,
                    "wrong_rx_time_4093_samples": wrong_rx,
                })
    two_mode = []
    for visit_index, admitted in modes.items():
        visit = source.read_visit(visit_index)
        iq = np.column_stack((visit.complex64(0), visit.complex64(1)))
        pairs = [item[:2] for item in admitted]
        for duration_ms in (23, 47, 95):
            width = duration_ms * 10_000
            for start in range(0, 1_200_000 - width + 1, width):
                try:
                    obs = [
                        _extract(iq, selected[visit_index]["edge"], pair, start, start + width)
                        for pair in pairs
                    ]
                    controls = [
                        _extract(
                            iq, selected[visit_index]["edge"], pair,
                            (start + 200_000 if start + 200_000 + width <= 1_200_000
                             else start - 200_000),
                            (start + 200_000 + width if start + 200_000 + width <= 1_200_000
                             else start - 200_000 + width),
                        )
                        for pair in pairs
                    ]
                    rx_shift = 4093 if start + width + 4093 <= 1_200_000 else -4093
                    wrong_rx = [
                        _extract(iq, selected[visit_index]["edge"], pair, start, start + width,
                                 rx1_shift=rx_shift)
                        for pair in pairs
                    ]
                except ValueError as error:
                    failures.append({"visit_index": visit_index, "duration_ms": duration_ms,
                                     "start_sample": start, "two_mode": True,
                                     "reason": str(error)})
                    continue
                two_mode.append({
                    "visit_index": visit_index,
                    "duration_ms": duration_ms,
                    "start_sample": start,
                    "device_counter_reference": selected[visit_index]["valid_start_counter"]
                    + round(obs[0]["common_reference_global_sample"]),
                    "mode_observations": obs,
                    "double_difference_rad": float(np.angle(np.exp(1j * (
                        obs[0]["phase_rad"] - obs[1]["phase_rad"])))),
                    "wrong_time_double_difference_rad": float(np.angle(np.exp(1j * (
                        controls[0]["phase_rad"] - controls[1]["phase_rad"])))),
                    "wrong_rx_time_double_difference_rad": float(np.angle(np.exp(1j * (
                        wrong_rx[0]["phase_rad"] - wrong_rx[1]["phase_rad"])))),
                })
    # Derange mode 1 across neighboring physical windows only after extraction.
    for row in two_mode:
        compatible = [r for r in two_mode if r["visit_index"] == row["visit_index"]
                      and r["duration_ms"] == row["duration_ms"]]
        peer = compatible[(compatible.index(row) + 1) % len(compatible)]
        row["deranged_window_double_difference_rad"] = float(np.angle(np.exp(1j * (
            row["mode_observations"][0]["phase_rad"]
            - peer["mode_observations"][1]["phase_rad"]))))
    document = {
        "schema": "scan-phase-historical-shared-residual/v1",
        "estimator": "extract_dual_receiver_phase_with_offset_authority_shared_residual",
        "phase_selection": False,
        "window_coordinate_rule": (
            "candidate lattice translated to slice-local coordinates; fitted phase transported "
            "to the physical slice midpoint using the fitted receiver-relative frequency"
        ),
        "counts": {"eligible": 128, "primary_visits": len(primary),
                   "primary_rows": len(rows), "two_mode_rows": len(two_mode),
                   "failures": len(failures)},
        "primary_rows": rows,
        "two_mode_rows": two_mode,
        "failures": failures,
    }
    (HERE / "method21-22-shared-residual.json").write_text(json.dumps(document, indent=2) + "\n")


if __name__ == "__main__":
    main()
