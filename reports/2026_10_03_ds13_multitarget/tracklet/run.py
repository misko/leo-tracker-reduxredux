#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, sys, time
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import assignment_record, digest, load_scan, write_assignments  # noqa: E402
from tracklet import Settings, generate_candidates, label_alternatives, select_exclusive  # noqa: E402


def run_variant(name, settings, output_dir=HERE):
    output_dir = Path(output_dir)
    records, scans_out, tracks_out = [], [], []
    started = time.monotonic()
    for label in ("A", "B"):
        data = load_scan(label); arrays = data["arrays"]; tick = time.monotonic()
        paths = generate_candidates(arrays["times_s"], arrays["receiver"], arrays["channel"],
            arrays["catalog_numbers"], data["native_residual_hz"], settings,
            data["log_gain"], arrays["group"])
        chosen, solver = select_exclusive(paths)
        for track_id, path in enumerate(chosen):
            col = int(np.flatnonzero(arrays["catalog_numbers"] == path.catalog_number)[0])
            alternatives = label_alternatives(path, arrays["catalog_numbers"],
                data["native_residual_hz"], settings, log_gain=data["log_gain"])
            tracks_out.append({"scan": label, "track_id": track_id, "receiver": path.receiver,
                "channel": path.channel, "catalog_number": path.catalog_number,
                "points": len(path.rows), "score": path.score, "residual_score": path.residual_score,
                "transition_cost": path.transition_cost, "gap_cost": path.gap_cost,
                "whole_track_label_alternatives": alternatives})
            records.extend(assignment_record(data, row, col) for row in path.rows)
        scans_out.append({"scan": label, "session": data["session"], "rows": len(arrays["times_s"]),
            "catalogs": len(arrays["catalog_numbers"]), "proposals": len(paths),
            "selected_tracks": len(chosen), "selected_rows": sum(len(p.rows) for p in chosen),
            "solver": solver, "runtime_s": time.monotonic() - tick,
            "detection_probability": data["detection_probability"],
            "provenance": data["provenance"], "scope": data["scope"]})
    output = output_dir / "outputs" / ("assignments.csv" if name == "continuity" else f"assignments-{name}.csv")
    write_assignments(output, sorted(records, key=lambda r: (r["scan"], r["row_index"], r["catalog_number"])))
    receipt = {"schema": "ds13-bounded-tracklet-association/v2",
        "created_utc": datetime.now(UTC).isoformat(), "variant": name,
        "rf_variant": os.environ.get("DS13_RF_VARIANT", "archived"),
        "settings": asdict(settings), "runtime_s": time.monotonic() - started,
        "scans": scans_out, "tracks": tracks_out, "output_csv": str(output),
        "output_sha256": digest(output),
        "limitations": ["Frozen reference-position orbit/nuisance replay; Stage A review diagnostic only.",
            "MILP is exact only over heuristic DP proposals, not the coupled path/NORAD problem.",
            "Groups are observed positive peak opportunities; skipped groups do not imply empty windows.",
            "Whole-track alternatives expose close crossing labels; MAP probability is null.",
            "The fitted-c versus zero-c control is fixed-position in-sample fit sensitivity, not localization accuracy.",
            "No held-out, location-accuracy, or production claim is made.",
            "Tracks never join receiver/channel lanes or concatenate raw CFO across channels."]}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"receipt-{name}.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path(os.environ.get("DS13_TRACKLET_OUTPUT_DIR", HERE)))
    parser.add_argument("--continuity-only", action="store_true")
    args = parser.parse_args()
    base = Settings(residual_gate_hz=1000.0)
    receipts = [run_variant("continuity", base, args.output_dir)]
    if not args.continuity_only:
        receipts.append(run_variant("no-continuity", replace(base, continuity=False), args.output_dir))
    (args.output_dir / "summary.json").write_text(json.dumps({"stage": "A",
        "stage_b_status": "not run; requires review",
        "variants": [{"name": r["variant"], "runtime_s": r["runtime_s"], "scans": r["scans"]}
                     for r in receipts]}, indent=2) + "\n")
