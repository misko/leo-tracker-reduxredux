"""Dense phase-blind method-21/22 replay with the historical shared extractor."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
REPORT = HERE.parent
DENSE = Path("/srv/bulk/leo/experiments/scan-fw-32a202-phase-replay/acquisition-dense-v1")
CACHE = Path("/srv/bulk/leo-dev/scan-32a202-phase-replay-cache/selected-visits/cache-index.json")


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


C = _module("phase_replay_common_dense_shared", REPORT / "common.py")
S = _module("phase_replay_shared_runner", HERE / "run_shared_extractor.py")


def _probe_pairs(document):
    grouped = {}
    for probe in document["product"]["probes"]:
        grouped.setdefault(probe["probe_index"], {})[probe["receiver_id"]] = probe
    output = []
    for probe_index, receivers in sorted(grouped.items()):
        if set(receivers) != {0, 1}:
            continue
        admitted = {
            rx: [row for row in receivers[rx]["candidates"] if row["passed_fractional_margin_gate"]]
            for rx in (0, 1)
        }
        winners = []
        for rx in (0, 1):
            if not admitted[rx]:
                break
            winners.append(max(admitted[rx], key=lambda row: (
                row["fractional_margin"], -row["candidate_rank"])))
        if len(winners) != 2:
            continue
        start = probe_index * 200_000
        normalized = []
        for row in winners:
            row = dict(row)
            row["integer_epoch_sample"] += start
            row["tracking_absolute_baseband_cfo_hz"] = row["fractional_tracking_cfo_hz"]
            normalized.append(row)
        output.append((probe_index, tuple(normalized), admitted))
    return output


def main():
    selection = json.loads((REPORT / "selection.json").read_text())
    source = C.CachedReplayVisitSource(CACHE, REPORT / "selection.json")
    rows = []
    mode_inventory = []
    accounting = []
    for selected in selection["visits"]:
        visit_index = selected["visit_index"]
        path = DENSE / f"visit-{visit_index:06d}.corrected-dense.json"
        if not path.exists():
            accounting.append({"visit_index": visit_index, "status": "dense_pending"})
            continue
        probes = _probe_pairs(json.loads(path.read_text()))
        training = [item for item in probes if item[0] <= 2]
        if not training:
            accounting.append({"visit_index": visit_index, "status": "no_training_half_pair"})
            continue
        probe_index, pair, _ = training[0]
        visit = source.read_visit(visit_index)
        iq = np.column_stack((visit.complex64(0), visit.complex64(1)))
        for duration_ms in (23, 47, 95):
            width = duration_ms * 10_000
            for start in range(0, 1_200_000 - width + 1, width):
                exact = S._extract(iq, selected["edge"], pair, start, start + width)
                rx_shift = 4093 if start + width + 4093 <= 1_200_000 else -4093
                control = S._extract(
                    iq, selected["edge"], pair, start, start + width, rx1_shift=rx_shift
                )
                rows.append({
                    "visit_index": visit_index,
                    "split": selected["split"],
                    "seed_probe_index": probe_index,
                    "duration_ms": duration_ms,
                    "start_sample": start,
                    "exact": exact,
                    "wrong_rx_time_4093_samples": control,
                })
        # Preserve every phase-blind admitted mode combination on all six probes.
        for current_probe, _, admitted in probes:
            proposals = []
            for left in admitted[0]:
                for right in admitted[1]:
                    canonical_left = left.get("pilot_relative_canonical_display_cfo_hz")
                    canonical_right = right.get("pilot_relative_canonical_display_cfo_hz")
                    proposals.append({
                        "rx0_rank": left["candidate_rank"],
                        "rx1_rank": right["candidate_rank"],
                        "rx0_tracking_cfo_hz": left["fractional_tracking_cfo_hz"],
                        "rx1_tracking_cfo_hz": right["fractional_tracking_cfo_hz"],
                        "rx0_epoch_sample": current_probe * 200_000
                        + left["integer_epoch_sample"] + left["fractional_epoch_offset_samples"],
                        "rx1_epoch_sample": current_probe * 200_000
                        + right["integer_epoch_sample"] + right["fractional_epoch_offset_samples"],
                        "canonical_separation_hz": (
                            abs(canonical_left - canonical_right)
                            if canonical_left is not None and canonical_right is not None else None
                        ),
                    })
            mode_inventory.append({"visit_index": visit_index, "probe_index": current_probe,
                                   "pair_combinations": proposals})
        accounting.append({"visit_index": visit_index, "status": "completed",
                           "seed_probe_index": probe_index})
    per_visit = [
        {
            "visit_index": visit_index,
            "split": selected_row["split"],
            "duration_ms": duration,
            "exact_median": float(np.median([
                row["exact"]["resultant_length"] for row in rows
                if row["visit_index"] == visit_index and row["duration_ms"] == duration
            ])),
            "wrong_rx_time_median": float(np.median([
                row["wrong_rx_time_4093_samples"]["resultant_length"] for row in rows
                if row["visit_index"] == visit_index and row["duration_ms"] == duration
            ])),
        }
        for visit_index, selected_row in (
            (row["visit_index"], row) for row in selection["visits"]
        )
        for duration in (23, 47, 95)
        if any(item["visit_index"] == visit_index and item["duration_ms"] == duration
               for item in rows)
    ]
    by_split = {}
    for split in ("development", "evaluation"):
        by_split[split] = {}
        for duration in (23, 47, 95):
            group = [row for row in per_visit
                     if row["split"] == split and row["duration_ms"] == duration]
            by_split[split][str(duration)] = {
                "visit_count": len(group),
                "median_of_visit_exact_medians": float(np.median([
                    row["exact_median"] for row in group])) if group else None,
                "median_of_visit_wrong_rx_time_medians": float(np.median([
                    row["wrong_rx_time_median"] for row in group])) if group else None,
            }
    document = {
        "schema": "scan-phase-dense-shared-residual/v1",
        "policy": "earliest phase-blind passing dual-RX probe in training half (0,1,2)",
        "counts": {"eligible": 128, "dense_present": sum(
            row["status"] != "dense_pending" for row in accounting),
            "completed_visits": sum(row["status"] == "completed" for row in accounting),
            "rows": len(rows)},
        "per_visit_median_resultant": per_visit,
        "by_split": by_split,
        "accounting": accounting,
        "rows": rows,
        "all_probe_mode_inventory": mode_inventory,
    }
    (HERE / "method21-22-dense-shared-residual.json").write_text(
        json.dumps(document) + "\n"
    )


if __name__ == "__main__":
    main()
