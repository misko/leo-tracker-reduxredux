#!/usr/bin/env python3
"""Qualify six response-free samples from two older eight-hour scan groups."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def selected_groups(inventory):
    wanted = {"2026-09-21T00:00:00+00:00", "2026-09-21T08:00:00+00:00"}
    output = []
    for group in inventory["utc_8h_groups"]:
        if group["utc_8h_start"] not in wanted:
            continue
        ids = group["session_ids"]
        indices = (0, len(ids) // 2, len(ids) - 1)
        output.append((group, [(index, ids[index]) for index in indices]))
    if len(output) != 2:
        raise ValueError("expected both frozen long groups")
    return output


WORKER = r'''
import json,sys,traceback
from pathlib import Path
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
archive=TleArchiveReader(Path('/var/lib/leo/tle'))
rows=[]
try:
  for sid in sys.argv[1:]:
    try:
      source=store.load(sid)
      base={
        'session_id':sid,
        'capture_mode':source.capture_mode,
        'sample_rate_hz':source.sample_rate_hz,
        'radio_id':source.radio_id,
        'stream_generation':source.stream_generation,
        'input_manifest_sha256':source.input_manifest_sha256,
        'analysis_manifest_sha256':source.analysis_manifest_sha256,
        'raw_recording_authority_digest':source.raw_recording_authority_digest,
        'capture_start_utc_ns':source.capture_start_utc_ns,
        'capture_end_utc_ns':source.capture_end_utc_ns,
        'receiver_ids':sorted(set(p.receiver_id for p in source.probes)),
        'channels':sorted(set(p.channel for p in source.probes)),
        'actual_rf_hz':sorted(set(p.actual_rf_hz for p in source.probes)),
        'probe_count':len(source.probes),
        'timing_qualified':source.timing.qualified,
        'timing_algorithm':source.timing.algorithm_version,
        'first_sample_estimate_utc_ns':source.timing.first_sample_estimate_utc_ns,
        'first_sample_bracket_width_ns':source.timing.first_sample_bracket_width_ns,
      }
      try:
        prepared=prepare_adaptive_tle_position_inputs(sid,inputs=store,archive=archive)
        masks=[value for track in prepared.tracks for value in track.training_mask]
        spans=[float(track.times_s[-1]-track.times_s[0]) for track in prepared.tracks]
        base.update({
          'current_position_input_status':'ready',
          'reconstructed_track_count':prepared.reconstructed_track_count,
          'eligible_3s_track_count':prepared.eligible_track_count,
          'eligible_observation_count':prepared.eligible_observation_count,
          'training_observation_count':sum(masks),
          'reserved_observation_count':len(masks)-sum(masks),
          'track_span_s_min':min(spans) if spans else None,
          'track_span_s_median':sorted(spans)[len(spans)//2] if spans else None,
          'track_span_s_max':max(spans) if spans else None,
          'trajectory_digest':prepared.trajectory_digest,
          'evidence_sha256':prepared.evidence_sha256,
          'snapshot_digest':prepared.snapshot_digest,
          'snapshot_collected_utc_ns':prepared.snapshot_collected_utc_ns,
          'causal_tle_candidate_count':len(prepared.candidate_indices),
          'start_matches_timing_authority':prepared.start_utc_ns==source.timing.first_sample_estimate_utc_ns,
        })
      except Exception as error:
        base.update({
          'current_position_input_status':'unavailable',
          'position_input_error_type':type(error).__name__,
          'position_input_error':str(error),
          'fallback_tracking_source_available':bool(source.probes),
        })
      rows.append(base)
    except Exception as error:
      rows.append({'session_id':sid,'load_status':'unavailable','error_type':type(error).__name__,'error':str(error)})
finally:
  store.close()
print(json.dumps(rows,sort_keys=True,default=lambda value:value.item()))
'''


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh output required")
    inventory = json.loads(args.inventory.read_text())
    groups = selected_groups(inventory)
    selected = [sid for _, rows in groups for _, sid in rows]
    command = ["sudo", "-n", "-u", "leo", sys.executable, "-c", WORKER, *selected]
    completed = subprocess.run(command, capture_output=True, text=True, check=True, timeout=300)
    by_id = {row["session_id"]: row for row in json.loads(completed.stdout)}
    output_groups = []
    for group, choices in groups:
        rows = []
        for role, (index, sid) in zip(("first", "middle", "last"), choices, strict=True):
            rows.append({"selection_role": role, "source_index": index, **by_id[sid]})
        output_groups.append(
            {
                "utc_8h_start": group["utc_8h_start"],
                "source_scan_count": group["scan_count"],
                "max_inter_capture_gap_s": group["max_inter_capture_gap_s"],
                "qualified_samples": rows,
            }
        )
    all_rows = [row for group in output_groups for row in group["qualified_samples"]]
    result = {
        "schema": "older-long-block-position-qualification/v1",
        "selection": "first, floor(n/2), last in each metadata-frozen group",
        "position_outcome_used_for_selection": False,
        "selected_session_ids": selected,
        "summary": {
            "sampled_scans": len(all_rows),
            "current_position_input_ready": sum(
                row.get("current_position_input_status") == "ready" for row in all_rows
            ),
            "eligible_3s_tracks": sum(row.get("eligible_3s_track_count", 0) for row in all_rows),
            "eligible_observations": sum(
                row.get("eligible_observation_count", 0) for row in all_rows
            ),
            "training_observations": sum(
                row.get("training_observation_count", 0) for row in all_rows
            ),
            "reserved_observations": sum(
                row.get("reserved_observation_count", 0) for row in all_rows
            ),
        },
        "groups": output_groups,
        "bindings": {"inventory": digest(args.inventory), "qualifier": digest(Path(__file__))},
    }
    args.output.mkdir(parents=True)
    (args.output / "qualification.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(json.dumps(result["summary"], indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
