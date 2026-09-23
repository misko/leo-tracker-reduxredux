"""Training-only qualification of the split-pilot CFO alias lattice."""

from __future__ import annotations

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
from tools.research.extract_independent_phase_arc import serial
from tools.research.extract_longarc_phase import frame_opportunities

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "reports/figures/2026_09_23_independent_phase"
VISITS = (603, 711, 610)
CALIBRATION_GROUPS = (0, 3, 5)
DIAGNOSTIC_GROUPS = (1, 2, 4)
SYMBOL_DURATION_S = 4.4e-6
HALF_PERIOD_HZ = 1 / (2 * SYMBOL_DURATION_S)
FULL_PERIOD_HZ = 1 / SYMBOL_DURATION_S


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def branch_seeds(observation: dict) -> list[dict]:
    """Return the predeclared seed family; no response enters its construction."""
    acquired = float(observation["acquired_cfo_hz"])
    values = [
        ("acquired_minus_full", acquired - FULL_PERIOD_HZ),
        ("acquired_minus_half", acquired - HALF_PERIOD_HZ),
        ("acquired", acquired),
        ("acquired_plus_half", acquired + HALF_PERIOD_HZ),
        ("acquired_plus_full", acquired + FULL_PERIOD_HZ),
        ("archived_refined", float(observation["fractional_tracking_cfo_hz"])),
    ]
    return [{"label": label, "seed_cfo_hz": value} for label, value in values]


def summarize_frames(frames: list[dict], groups: tuple[int, ...]) -> dict:
    selected = [row for row in frames if row["group_id"] in groups]
    output = {}
    for parity in ("even", "odd"):
        folds = [row["frame"][parity] for row in selected if row["frame"][parity] is not None]
        eligible = [
            row["frame"][parity]
            for row in selected
            if row["frame"]["training_supported"] and row["frame"][parity] is not None
        ]
        output[parity] = {
            "present_count": len(folds),
            "eligible_count": len(eligible),
            "mean_exact_coherence": float(np.mean([row["exact_coherence"] for row in folds])),
            "mean_control_coherence": float(
                np.mean([row["control_coherence"] for row in folds])
            ),
            "mean_coherence_margin": float(np.mean([row["coherence_margin"] for row in folds])),
            "mean_eligible_absolute_cfo_hz": (
                float(np.mean([row["absolute_cfo_hz"] for row in eligible]))
                if eligible
                else None
            ),
        }
    return output


def run(binding_path: Path, output_path: Path, bulk_root: Path) -> None:
    if output_path.exists():
        raise ValueError("fresh output path required")
    binding = json.loads(binding_path.read_text())
    observations = {row["visit_index"]: row for row in binding["observations"]}
    split = {
        row["visit_index"]: row["partition"]
        for row in binding["fresh_random_whole_visit_split"]
    }
    if any(split.get(visit) != "train" for visit in VISITS):
        raise ValueError("qualification population is not entirely training")
    rows = []
    store = AdaptiveHopIqStore(bulk_root, read_only=True)
    try:
        with AdaptiveHopAnalysisInputStore(store).source(binding["session_id"]) as source:
            if source.input_manifest_sha256 != binding["input_manifest_sha256"]:
                raise ValueError("capture manifest changed")
            geometry = source.receipt.plan.geometry
            if geometry.sample_rate_hz != binding["sample_rate_hz"]:
                raise ValueError("sample rate changed")
            rate = geometry.sample_rate_hz
            content = round(302 * rate * template_module.OFDM_SYMBOL_DURATION_S)
            for visit in VISITS:
                observation = observations[visit]
                ordinal = observation["iq_ordinal"]
                if source.visits[ordinal].event.visit_index != visit:
                    raise ValueError("IQ ordinal changed")
                iq = source.read_visit(ordinal)
                receiver = geometry.receiver_ids.index(observation["receiver_id"])
                epoch = round(observation["probe_start_ms"] * rate / 1000) + observation[
                    "integer_epoch_sample"
                ]
                opportunities = frame_opportunities(len(iq), rate, epoch)
                if len(opportunities) != 24:
                    raise ValueError("expected 24 frozen frame opportunities")
                branches = []
                for branch in branch_seeds(observation):
                    frames = []
                    for group, start in opportunities:
                        measured = estimate_edge_pilot_frame_complex_split(
                            iq[start - 1 : start + content + 1, receiver],
                            rate,
                            frame_start_sample=start,
                            acquisition_absolute_cfo_hz=branch["seed_cfo_hz"],
                            edge=observation["edge"],
                        )
                        frames.append({"group_id": group, "frame": serial(asdict(measured))})
                    calibration = summarize_frames(frames, CALIBRATION_GROUPS)
                    diagnostic = summarize_frames(frames, DIAGNOSTIC_GROUPS)
                    branches.append(
                        {**branch, "calibration": calibration, "diagnostic": diagnostic}
                    )
                winner = int(
                    np.argmax(
                        [row["calibration"]["even"]["mean_coherence_margin"] for row in branches]
                    )
                )
                rows.append(
                    {
                        "visit_index": visit,
                        "role": (
                            "suspected_half_alias"
                            if visit in (603, 711)
                            else "ordinary_control"
                        ),
                        "winner_from_calibration_even_only": winner,
                        "branches": branches,
                    }
                )
    finally:
        store.close()
    payload = {
        "schema": "independent-phase-alias-qualification/v1",
        "scope": "three predeclared fresh-training visits only; no held IQ",
        "visit_indices": list(VISITS),
        "half_period_hz": HALF_PERIOD_HZ,
        "full_period_hz": FULL_PERIOD_HZ,
        "selection_policy": "maximum calibration-group even coherence margin only",
        "odd_is_diagnostic_only": True,
        "fresh_held_visits_read": 0,
        "old_reserved_visits_read": 0,
        "binding_sha256": digest(binding_path),
        "source_sha256": {
            "qualification": digest(Path(__file__)),
            "pilot": digest(Path(pilot_module.__file__)),
            "templates": digest(Path(template_module.__file__)),
        },
        "rows": rows,
    }
    output_path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    run(
        DIRECTORY / "binding.json",
        DIRECTORY / "train-branch-qualification.json",
        Path("/srv/bulk/leo"),
    )
