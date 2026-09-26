"""Build a bounded, synchronized real-data input for multitrack modelling."""

from __future__ import annotations

import csv
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parents[2]
DUAL = REPORT / "dual-rx" / "run_shared_extractor.py"
WINDOW_SAMPLES = 70_000
CAPTURE_SAMPLES = 1_200_000
CHOSEN_VISITS = [14, 52, 73, 74, 1074, 1711, 1734, 1735]


def _load_shared():
    spec = importlib.util.spec_from_file_location("multitrack_shared_extractor", DUAL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _extract_in_common_gauge(shared, iq, edge, pair, start, stop, authority_hz):
    """Extract a mode while applying the visit's single RX1-RX0 authority."""
    center = 0.5 * (start + stop)
    epoch = float(np.mean([shared._epoch(row) for row in pair]))
    period = shared.RATE / shared.FRAME_RATE_HZ
    local_epoch = round(epoch + round((center - epoch) / period) * period - start)
    seeds = tuple(shared.ReceiverPhaseSeed(
        acquired_cfo_hz=float(row["tracking_absolute_baseband_cfo_hz"]),
        reference_sample=shared._epoch(row) - start,
    ) for row in pair)
    result = shared.extract_dual_receiver_phase_with_offset_authority_shared_residual(
        iq[start:stop], shared.RATE, edge, local_epoch, seeds, authority_hz,
        common_reference_sample=center - start,
        frame_radius=max(2, math.ceil((stop - start) / period / 2)),
    ).observation
    phase = result.wrapped_phase_rad + 2 * np.pi * result.relative_frequency_hz * (
        center - start - result.center_sample
    ) / shared.RATE
    return {
        "phase_rad": float(np.angle(np.exp(1j * phase))),
        "resultant_length": result.resultant_length,
        "frame_count": result.independent_frame_count,
        "relative_frequency_hz": result.relative_frequency_hz,
        "common_reference_global_sample": center,
    }


def build() -> tuple[list[dict], dict]:
    shared = _load_shared()
    audit = shared._module("multitrack_audit_offsets", REPORT / "single-track/audit_offsets.py")
    with (REPORT / "capture-audit/visit-inventory.csv").open() as stream:
        visits = {int(row["visit_index"]): row for row in csv.DictReader(stream)}
    admitted = shared._admitted(set(CHOSEN_VISITS))
    primary = shared._primary(set(CHOSEN_VISITS))

    # Selection uses only acquisition/template quantities, never extracted phase.
    chosen = [visit for visit in CHOSEN_VISITS if visit in admitted]
    rows: list[dict] = []
    mode_records: list[dict] = []
    for visit_index in chosen:
        iq = audit.load(visit_index)
        primary_pair = primary[visit_index]
        authority_hz = (
            float(primary_pair[1]["tracking_absolute_baseband_cfo_hz"])
            - float(primary_pair[0]["tracking_absolute_baseband_cfo_hz"])
        )
        for mode_index, (left, right, canonical_cfo) in enumerate(admitted[visit_index]):
            mode_records.append({
                "visit_index": visit_index,
                "mode": f"m{mode_index}",
                "canonical_cfo_hz": canonical_cfo,
                "rx0_tracking_cfo_hz": float(left["tracking_absolute_baseband_cfo_hz"]),
                "rx1_tracking_cfo_hz": float(right["tracking_absolute_baseband_cfo_hz"]),
                "rx0_epoch_sample": shared._epoch(left),
                "rx1_epoch_sample": shared._epoch(right),
                "rx0_candidate_rank": int(left["candidate_rank"]),
                "rx1_candidate_rank": int(right["candidate_rank"]),
                "alias_group": f"visit-{visit_index}-canonical-{round(canonical_cfo / 10000)}",
            })
        for start in range(0, CAPTURE_SAMPLES - WINDOW_SAMPLES + 1, WINDOW_SAMPLES):
            for mode_index, pair_with_frequency in enumerate(admitted[visit_index]):
                observation = _extract_in_common_gauge(
                    shared, iq, visits[visit_index]["edge"], pair_with_frequency[:2],
                    start, start + WINDOW_SAMPLES, authority_hz,
                )
                rows.append({
                    "group_id": f"visit-{visit_index}",
                    "mode": f"m{mode_index}",
                    "time_s": observation["common_reference_global_sample"] / shared.RATE,
                    "phase_rad": observation["phase_rad"],
                    "valid": True,
                    "weight": observation["resultant_length"],
                    "retune_id": f"visit-{visit_index}",
                    "visit_index": visit_index,
                    "window_start_sample": start,
                    "split": "training" if start < 280_000 else "evaluation",
                    "device_counter": int(visits[visit_index]["valid_start_counter"])
                    + round(observation["common_reference_global_sample"]),
                    "frame_count": observation["frame_count"],
                    "relative_frequency_hz": observation["relative_frequency_hz"],
                    "common_rx1_minus_rx0_authority_hz": authority_hz,
                    "canonical_cfo_hz": pair_with_frequency[2],
                    "alias_group": f"visit-{visit_index}-canonical-{round(pair_with_frequency[2] / 10000)}",
                })
    metadata = {
        "schema": "scan-phase-multitrack-observations/v1",
        "real_data": True,
        "phase_selection": False,
        "selection_rule": "fixed phase-blind eight-visit subset: earliest 14/52, consecutive pairs 73/74 and 1734/1735, and prior diagnostic visits 1074/1711",
        "window_samples": WINDOW_SAMPLES,
        "sample_rate_hz": shared.RATE,
        "chosen_visits": chosen,
        "mode_records": mode_records,
        "association_limit": "Distinct canonical CFO/epoch template modes; alias groups prevent duplicate candidates, but distinct emitters are not established.",
        "cross_dwell_limit": "Visits 73/74 are the sole same-target, same-channel adjacent candidate pair among the chosen visits. Visits 1734/1735 have different targets/channels and remain independent groups; no cross-channel mode association is asserted.",
        "shared_support": "Modes in a visit/window use identical IQ samples and physical midpoint.",
        "common_gauge": "Every mode in a visit uses the strongest primary pair's single RX1-minus-RX0 authority and midpoint reference; each mode retains its own template epoch.",
        "split_policy": "Within each visit, first four 7 ms windows are training and subsequent windows are held evaluation support.",
        "row_count": len(rows),
    }
    return rows, metadata


def main() -> None:
    rows, metadata = build()
    fields = list(rows[0])
    with (HERE / "observations.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (HERE / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    np.savez_compressed(HERE / "observations.npz", **{
        key: np.asarray([row[key] for row in rows]) for key in fields
    })


if __name__ == "__main__":
    main()
