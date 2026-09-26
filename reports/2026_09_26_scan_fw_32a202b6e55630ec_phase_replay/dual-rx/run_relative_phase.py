"""Run the production response-normalized relative-phase kernel on the cohort."""

from __future__ import annotations

import csv
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


def _common():
    spec = importlib.util.spec_from_file_location("phase_replay_common", REPORT / "common.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


C = _common()


def _pairs() -> dict[int, tuple[dict, dict]]:
    grouped = defaultdict(lambda: defaultdict(list))
    with (REPORT / "acquisition/candidate-inventory.csv").open() as stream:
        for row in csv.DictReader(stream):
            if row["passed_0p025_comparison_gate"] == "True":
                grouped[int(row["visit_index"])][int(row["receiver_id"])].append(row)
    result = {}
    for visit, by_rx in grouped.items():
        if 0 in by_rx and 1 in by_rx:
            result[visit] = tuple(
                max(
                    by_rx[receiver],
                    key=lambda row: (
                        float(row["fractional_margin"]),
                        -int(row["candidate_rank"]),
                    ),
                )
                for receiver in (0, 1)
            )
    return result


def main() -> None:
    selection = json.loads((REPORT / "selection.json").read_text())
    source = C.CachedReplayVisitSource(CACHE, REPORT / "selection.json")
    pairs = _pairs()
    rows = []
    for selected in selection["visits"]:
        visit_index = selected["visit_index"]
        base = {key: selected[key] for key in ("visit_index", "target_index", "channel", "split")}
        if visit_index not in pairs:
            rows.append({**base, "status": "no_dual_rx_acquisition"})
            continue
        visit = source.read_visit(visit_index)
        iq = np.column_stack((visit.complex64(0), visit.complex64(1)))
        candidates = pairs[visit_index]
        epoch = [
            int(row["integer_epoch_sample"]) + float(row["fractional_epoch_offset_samples"])
            for row in candidates
        ]
        probe = PairedPilotProbe(
            start_sample=0,
            epoch_sample=round(np.mean(epoch)),
            seeds=tuple(
                ReceiverPhaseSeed(
                    acquired_cfo_hz=float(row["tracking_absolute_baseband_cfo_hz"]),
                    reference_sample=value,
                )
                for row, value in zip(candidates, epoch, strict=True)
            ),
        )
        try:
            result = extract_relative_phase(iq, 10_000_000, selected["edge"], [probe])
        except (ValueError, FloatingPointError) as error:
            rows.append({**base, "status": "failed", "reason": str(error)})
            continue
        rows.append(
            {
                **base,
                "status": "completed",
                "supported": result["supported"],
                "relative_cfo_hz": result["relative_cfo_hz"],
                "relative_cfo_rate_hz_s": result["relative_cfo_rate_hz_s"],
                "fractional_delay_samples": result["fractional_delay_samples"],
                "tracked_coherence": result["tracked_coherence"],
                "wrong_time_coherence": result["wrong_time_coherence"],
                "band_phase_resultant": result["band_phase_resultant"],
                "band_phase_rms_deg": result["band_phase_rms_deg"],
                "retained_bandwidth_hz": result["retained_bandwidth_hz"],
                "pilot_held_count": result["pilot_held_count"],
            }
        )
    output = HERE / "method23-relative-phase.json"
    output.write_text(json.dumps(rows) + "\n")
    evaluation = [r for r in rows if r["split"] == "evaluation" and r["status"] == "completed"]
    summary = {
        "schema": "scan-phase-replay-method23/v1",
        "counts": {
            "eligible": 128,
            "completed": sum(r["status"] == "completed" for r in rows),
            "supported": sum(r.get("supported", False) for r in rows),
            "evaluation_completed": len(evaluation),
            "evaluation_supported": sum(r.get("supported", False) for r in evaluation),
        },
        "evaluation_medians": {
            key: float(np.median([r[key] for r in evaluation]))
            for key in (
                "tracked_coherence",
                "wrong_time_coherence",
                "band_phase_resultant",
                "band_phase_rms_deg",
                "retained_bandwidth_hz",
            )
        },
        "pilot_holdout_limitation": (
            "sparse acquisition supplies only the first 20 ms probe; production broadband "
            "frequency-held response is evaluated, but no second-half pilot probe is available"
        ),
    }
    (HERE / "method23-relative-phase-summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
