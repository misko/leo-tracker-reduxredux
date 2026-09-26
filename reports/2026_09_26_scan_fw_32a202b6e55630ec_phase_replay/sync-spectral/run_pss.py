#!/usr/bin/env python3
"""Native-rate independent and GLRT-conditioned PSS timing replay."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.analysis.standard.native_pss import starlink_pss_channel_reference_hz
from leo.analysis.starlink.pss_timing import search_pss_frame_timing

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SPEC = importlib.util.spec_from_file_location("phase_common_pss", ROOT / "common.py")
assert SPEC and SPEC.loader
COMMON = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = COMMON
SPEC.loader.exec_module(COMMON)

SSS_SPEC = importlib.util.spec_from_file_location("phase_sss_template", HERE / "sss_template.py")
assert SSS_SPEC and SSS_SPEC.loader
SSS = importlib.util.module_from_spec(SSS_SPEC)
SSS_SPEC.loader.exec_module(SSS)


def sss_native10_template(edge: str) -> np.ndarray:
    """Synthesize the captured eight-tone SSS edge slice on the native grid."""
    indexes = {"upper": np.arange(488, 496), "lower": np.arange(528, 536)}[edge]
    signed = np.where(indexes < 512, indexes, indexes - 1024)
    reference_offset = 312_500.0 if edge == "upper" else -312_500.0
    frequencies = (signed - np.mean(signed)) * 234_375.0 + reference_offset
    time_s = np.arange(44, dtype=float) / 10_000_000
    design = np.exp(2j * np.pi * (time_s[:, None] - 2 / 15 * 1e-6) * frequencies)
    template = np.asarray(design @ SSS.sss_edge_symbols(edge), np.complex64)
    return template / np.linalg.norm(template)


def pss_timed_sss(values: np.ndarray, pss: dict, template: np.ndarray) -> dict | None:
    """Measure SSS at PSS supplied epochs; this is not independent acquisition."""
    if not pss["windows"]:
        return None
    frequency = float(pss["nominal_frequency_offset_hz"])
    rows = []
    n = np.arange(template.size)
    carrier = np.exp(2j * np.pi * frequency * n / 10_000_000)
    reference = template * carrier
    for window in pss["windows"]:
        start = int(window["measured_local_sample"]) + 44
        stop = start + template.size
        if start < 0 or stop > values.size:
            continue
        observed = values[start:stop]
        correlation = np.vdot(reference, observed)
        power = float(abs(correlation) ** 2 / max(np.vdot(observed, observed).real, 1e-30))
        rows.append({"local_sample": start, "normalized_match_power": power,
                     "correlation_phase_cycles": float(np.angle(correlation) / (2 * np.pi))})
    return {"timing_source": "PSS", "frame_count": len(rows), "windows": rows}


def conditioned_cfo(path: Path) -> dict[tuple[int, int], float]:
    out = {}
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            key = int(row["visit_index"]), int(row["receiver_id"])
            score = float(row["fractional_margin"])
            if key not in out or score > out[key][0]:
                out[key] = score, float(row["pilot_relative_raw_cfo_hz"])
    return {key: value[1] for key, value in out.items()}


def run(index: Path, selection: Path, candidates: Path, output: Path) -> None:
    source = COMMON.CachedReplayVisitSource(index, selection)
    selected = json.loads(selection.read_text())
    cfo = conditioned_cfo(candidates)
    completed = set()
    if output.exists():
        completed = {json.loads(line)["visit_index"] for line in output.read_text().splitlines()}
    independent_bank = tuple(float(value) for value in range(-1_200_000, 1_200_001, 100_000))
    with output.open("a") as stream:
        for item in selected["visits"]:
            visit = item["visit_index"]
            if visit in completed:
                continue
            arrays = source.read_visit(visit)
            center_hz = item["channel"] * 250_000_000 + 940_000_000
            reference_hz = starlink_pss_channel_reference_hz(item["channel"], item["edge"])
            slice_center = center_hz - reference_hz
            rows = []
            for receiver in (0, 1):
                values = arrays.complex64(receiver)[:625_000]
                sss_template = sss_native10_template(item["edge"])
                common = dict(
                    global_device_sample_start=arrays.coordinates.valid_start_counter,
                    continuity_segment_index=visit,
                    slice_center_offset_hz=slice_center,
                )
                blind = search_pss_frame_timing(
                    values,
                    10_000_000,
                    nominal_frequency_offset_hz=0.0,
                    frequency_offsets_hz=independent_bank,
                    **common,
                )
                conditioned = None
                if (visit, receiver) in cfo:
                    seed = cfo[visit, receiver]
                    conditioned = search_pss_frame_timing(
                        values,
                        10_000_000,
                        nominal_frequency_offset_hz=seed,
                        frequency_offsets_hz=(seed,),
                        **common,
                    )
                sss_blind = search_pss_frame_timing(
                    values,
                    10_000_000,
                    nominal_frequency_offset_hz=0.0,
                    frequency_offsets_hz=independent_bank,
                    template_samples=sss_template,
                    **common,
                )
                rows.append(
                    {
                        "receiver_id": receiver,
                        "independent_blind": asdict(blind),
                        "glrt_conditioned": asdict(conditioned) if conditioned else None,
                        "independent_sss": asdict(sss_blind),
                        "pss_timed_sss": (
                            pss_timed_sss(values, asdict(conditioned), sss_template)
                            if conditioned else None
                        ),
                    }
                )
            stream.write(
                json.dumps(
                    {
                        "schema": "scan-native-pss-timing/v1",
                        "visit_index": visit,
                        "split": item["split"],
                        "window_ms": 62.5,
                        "results": rows,
                        "sss_status": "published_eight_tone_native10_template",
                        "continuity": "within_dwell_only_no_125ms_or_250ms_synthesis",
                    },
                    sort_keys=True,
                )
                + "\n"
            )
            stream.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.index, args.selection, args.candidates, args.output)


if __name__ == "__main__":
    main()
