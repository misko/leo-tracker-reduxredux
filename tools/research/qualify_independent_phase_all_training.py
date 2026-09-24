"""Audit fixed acquired-NCO split-pilot branches on all fresh training dwells.

This is an end-to-end diagnostic of the raw-NCO branches, not an alias
resolver.  It intentionally reads only the frozen 15-dwell training partition,
uses no odd-fold value in its summaries, and makes no branch winner.
"""

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
from tools.research.extract_independent_phase_arc import serial, training_rows
from tools.research.extract_longarc_phase import frame_opportunities

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "reports/figures/2026_09_23_independent_phase"
SYMBOL_DURATION_S = 4.4e-6
FOLD_PERIOD_HZ = 1 / (2 * SYMBOL_DURATION_S)
CALIBRATION_GROUPS = (0, 3, 5)
SHIFTS = (-1, 0, 1)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signed_fold_remainder(values: np.ndarray | float) -> np.ndarray | float:
    """Return the deterministic nearest-lattice residual in [-A/2, A/2]."""
    return np.asarray(values) - FOLD_PERIOD_HZ * np.rint(np.asarray(values) / FOLD_PERIOD_HZ)


def even_summary(frames: list[dict]) -> dict:
    """Summarize only calibration-even evidence; no branch is selected here."""
    calibration = [frame for frame in frames if frame["group_id"] in CALIBRATION_GROUPS]
    usable = [
        frame
        for frame in calibration
        if frame["frame"]["training_supported"]
        and frame["frame"]["even"] is not None
        and not frame["frame"]["even"]["search_boundary"]
    ]
    group_means = []
    for group in CALIBRATION_GROUPS:
        group_frames = [frame for frame in frames if frame["group_id"] == group]
        margins = [
            frame["frame"]["even"]["coherence_margin"]
            if frame["frame"]["even"] is not None and not frame["frame"]["even"]["search_boundary"]
            else 0.0
            for frame in group_frames
        ]
        group_means.append(float(np.mean(margins)))
    return {
        "all_24_training_supported_mask": [
            bool(frame["frame"]["training_supported"]) for frame in frames
        ],
        "calibration_even_usable_mask": [
            bool(
                frame["frame"]["training_supported"]
                and frame["frame"]["even"] is not None
                and not frame["frame"]["even"]["search_boundary"]
            )
            for frame in calibration
        ],
        "calibration_even_usable_count": len(usable),
        "calibration_even_equal_group_margin": float(np.mean(group_means)),
        "calibration_even_group_margins": group_means,
        "calibration_even_absolute_cfo_hz": [
            float(frame["frame"]["even"]["absolute_cfo_hz"]) for frame in usable
        ],
    }


def modulo_difference(candidate: dict, reference: dict) -> dict:
    """Compare calibration-even CFO lists without choosing a lattice branch."""
    if candidate["calibration_even_usable_mask"] != reference["calibration_even_usable_mask"]:
        return {"comparable": False, "reason": "different_usable_even_support_mask"}
    candidate_values = np.asarray(candidate["calibration_even_absolute_cfo_hz"], float)
    reference_values = np.asarray(reference["calibration_even_absolute_cfo_hz"], float)
    difference = np.asarray(signed_fold_remainder(candidate_values - reference_values), float)
    return {
        "comparable": True,
        "shared_even_frame_count": len(difference),
        "mean_signed_modulo_difference_hz": float(np.mean(difference)) if len(difference) else None,
        "maximum_absolute_modulo_difference_hz": (
            float(np.max(np.abs(difference))) if len(difference) else None
        ),
    }


def run(binding_path: Path, output_path: Path, bulk_root: Path) -> None:
    if output_path.exists():
        raise ValueError("fresh qualification output required")
    binding = json.loads(binding_path.read_text())
    observations = training_rows(binding)
    if len(observations) != 15:
        raise ValueError("qualification requires exactly the frozen 15 training dwells")
    rows = []
    store = AdaptiveHopIqStore(bulk_root, read_only=True)
    try:
        with AdaptiveHopAnalysisInputStore(store).source(binding["session_id"]) as source:
            if source.input_manifest_sha256 != binding["input_manifest_sha256"]:
                raise ValueError("capture manifest changed")
            geometry = source.receipt.plan.geometry
            if geometry.sample_rate_hz != binding["sample_rate_hz"] or geometry.receiver_ids != (
                0,
                1,
            ):
                raise ValueError("capture geometry changed")
            rate = geometry.sample_rate_hz
            content = round(302 * rate * template_module.OFDM_SYMBOL_DURATION_S)
            for observation in observations:
                ordinal = observation["iq_ordinal"]
                if source.visits[ordinal].event.visit_index != observation["visit_index"]:
                    raise ValueError("IQ ordinal no longer binds visit")
                iq = source.read_visit(ordinal)
                if iq.ndim != 2 or iq.shape[1] != 2:
                    raise ValueError("receiver-column contract changed")
                receiver = geometry.receiver_ids.index(observation["receiver_id"])
                epoch = (
                    round(observation["probe_start_ms"] * rate / 1000)
                    + observation["integer_epoch_sample"]
                )
                opportunities = frame_opportunities(len(iq), rate, epoch)
                if len(opportunities) != 24 or {group for group, _ in opportunities} != set(
                    range(6)
                ):
                    raise ValueError("expected fixed 24-frame opportunity set")
                branches = []
                for shift in SHIFTS:
                    seed = float(observation["acquired_cfo_hz"] + shift * FOLD_PERIOD_HZ)
                    frames = []
                    for group, start in opportunities:
                        measured = estimate_edge_pilot_frame_complex_split(
                            iq[start - 1 : start + content + 1, receiver],
                            rate,
                            frame_start_sample=start,
                            acquisition_absolute_cfo_hz=seed,
                            edge=observation["edge"],
                        )
                        frames.append({"group_id": group, "frame": serial(asdict(measured))})
                    branches.append(
                        {
                            "shift_fold_periods": shift,
                            "seed_cfo_hz": seed,
                            "even": even_summary(frames),
                        }
                    )
                reference = next(row["even"] for row in branches if row["shift_fold_periods"] == 0)
                for branch in branches:
                    branch["modulo_difference_to_acquired"] = modulo_difference(
                        branch["even"], reference
                    )
                rows.append({"visit_index": observation["visit_index"], "branches": branches})
    finally:
        store.close()
    payload = {
        "schema": "independent-phase-all-training-acquired-branch-qualification/v1",
        "scope": "all and only 15 frozen fresh-training dwells; no held or old-reserved IQ",
        "fixed_branch_policy": "acquired seed plus (-A, 0, +A), A=1/(2*4.4us)",
        "selection_policy": "none; this diagnostic never chooses a branch",
        "odd_dependency": "none; output summarizes only calibration-even evidence",
        "fold_period_hz": FOLD_PERIOD_HZ,
        "shifts_fold_periods": list(SHIFTS),
        "fresh_training_visits_read": len(rows),
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
        DIRECTORY / "train-all-branch-qualification.json",
        Path("/srv/bulk/leo"),
    )
