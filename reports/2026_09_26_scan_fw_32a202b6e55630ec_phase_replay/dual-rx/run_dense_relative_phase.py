"""Incremental method-23 replay using frozen corrected dense acquisition."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

from leo.analysis.starlink.adaptive_dual_rx_phase_extract import ReceiverPhaseSeed
from leo.analysis.starlink.relative_phase import PairedPilotProbe, extract_relative_phase

HERE = Path(__file__).parent
REPORT = HERE.parent
CACHE = Path("/srv/bulk/leo-dev/scan-32a202-phase-replay-cache/selected-visits/cache-index.json")
DENSE = Path("/srv/bulk/leo/experiments/scan-fw-32a202-phase-replay/acquisition-dense-v1")


def _common():
    spec = importlib.util.spec_from_file_location("phase_replay_common", REPORT / "common.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


C = _common()


def _probes(document):
    by_probe = {}
    for probe in document["product"]["probes"]:
        by_probe.setdefault(probe["probe_index"], {})[probe["receiver_id"]] = probe
    result = []
    for probe_index, receivers in sorted(by_probe.items()):
        if set(receivers) != {0, 1}:
            continue
        winners = []
        for receiver in (0, 1):
            admitted = [
                row
                for row in receivers[receiver]["candidates"]
                if row["passed_fractional_margin_gate"]
            ]
            if not admitted:
                break
            winners.append(
                max(
                    admitted,
                    key=lambda row: (row["fractional_margin"], -row["candidate_rank"]),
                )
            )
        if len(winners) != 2:
            continue
        start = probe_index * 200_000
        epochs = [
            row["integer_epoch_sample"] + row["fractional_epoch_offset_samples"] for row in winners
        ]
        result.append(
            PairedPilotProbe(
                start_sample=start,
                epoch_sample=round(np.mean(epochs)),
                seeds=tuple(
                    ReceiverPhaseSeed(row["fractional_tracking_cfo_hz"], epoch)
                    for row, epoch in zip(winners, epochs, strict=True)
                ),
            )
        )
    return result


def main():
    selection = json.loads((REPORT / "selection.json").read_text())
    source = C.CachedReplayVisitSource(CACHE, REPORT / "selection.json")
    rows = []
    for selected in selection["visits"]:
        visit_index = selected["visit_index"]
        path = DENSE / f"visit-{visit_index:06d}.corrected-dense.json"
        base = {key: selected[key] for key in ("visit_index", "target_index", "channel", "split")}
        if not path.exists():
            rows.append({**base, "status": "dense_pending"})
            continue
        probes = _probes(json.loads(path.read_text()))
        training = [probe for probe in probes if probe.start_sample + 200_000 <= 600_000]
        evaluation = [probe for probe in probes if probe.start_sample >= 600_000]
        if not training:
            rows.append(
                {
                    **base,
                    "status": "no_training_half_acquisition",
                    "paired_probe_count": len(probes),
                }
            )
            continue
        visit = source.read_visit(visit_index)
        iq = np.column_stack((visit.complex64(0), visit.complex64(1)))
        try:
            result = extract_relative_phase(iq, 10_000_000, selected["edge"], probes)
        except ValueError as error:
            rows.append({**base, "status": "failed", "reason": str(error)})
            continue
        rows.append(
            {
                **base,
                "status": "completed",
                "paired_probe_count": len(probes),
                "training_probe_count": len(training),
                "evaluation_probe_count": len(evaluation),
                "supported": result["supported"],
                "tracked_coherence": result["tracked_coherence"],
                "wrong_time_coherence": result["wrong_time_coherence"],
                "band_phase_resultant": result["band_phase_resultant"],
                "band_phase_rms_deg": result["band_phase_rms_deg"],
                "pilot_held_count": result["pilot_held_count"],
                "pilot_held_rms_deg": result["pilot_held_rms_deg"],
            }
        )
    (HERE / "method23-dense-relative-phase.json").write_text(json.dumps(rows) + "\n")
    complete = [row for row in rows if row["status"] == "completed"]
    held = [
        row
        for row in complete
        if row["pilot_held_count"] and row["pilot_held_rms_deg"] is not None
    ]
    by_split = {}
    for split in ("development", "evaluation"):
        split_complete = [row for row in complete if row["split"] == split]
        split_held = [row for row in held if row["split"] == split]
        by_split[split] = {
            "completed": len(split_complete),
            "supported": sum(row["supported"] for row in split_complete),
            "with_pilot_holdout": len(split_held),
            "pilot_held_rms_median_deg": (
                float(np.median([row["pilot_held_rms_deg"] for row in split_held]))
                if split_held
                else None
            ),
        }
    summary = {
        "schema": "scan-phase-replay-method23-dense/v1",
        "dense_files_present": sum(row["status"] != "dense_pending" for row in rows),
        "counts": {
            "eligible": 128,
            "completed": len(complete),
            "supported": sum(row["supported"] for row in complete),
            "with_pilot_holdout": len(held),
            "no_training_half_acquisition": sum(
                row["status"] == "no_training_half_acquisition" for row in rows
            ),
        },
        "pilot_held_rms_median_deg": float(np.median([row["pilot_held_rms_deg"] for row in held]))
        if held
        else None,
        "by_split": by_split,
        "completion_state": "complete"
        if len(rows) == 128 and all(row["status"] != "dense_pending" for row in rows)
        else "incremental",
    }
    (HERE / "method23-dense-relative-phase-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
