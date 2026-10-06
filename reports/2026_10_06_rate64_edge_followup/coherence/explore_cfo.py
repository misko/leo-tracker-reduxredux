"""Explicitly exploratory matched CFO extension after primary evaluation.

The original timing-only evaluation remains the primary frozen comparison.
This extension uses identical three CFO cells for every selected candidate,
both templates, and their symbol-shift controls; no new acquisition.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

from analyze import (
    TIMING_OFFSETS,
    AdaptiveHopIqStore,
    matched_surface,
    per_tone_projection,
)

CFO_GRID = (-20000.0, 0.0, 20000.0)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--primary", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    spec = json.loads(args.spec.read_text())
    primary_bytes = args.primary.read_bytes()
    primary = json.loads(primary_bytes)
    by_key = {(r["session_id"], r["lane"]): r for r in primary["results"]}
    report = {
        "status": "exploratory; grid chosen after primary development and evaluation inspection",
        "settings": {
            "cfo_offsets_hz": CFO_GRID,
            "timing_offsets_samples": TIMING_OFFSETS,
            "selection": "maximize margin across identical 21 timing/CFO cells",
            "trial_inventory": "both templates and shifted controls for all 62 selected candidates",
        },
        "primary_results_sha256": hashlib.sha256(primary_bytes).hexdigest(),
        "results": [],
    }
    args.output.write_text(json.dumps(report, indent=2))
    store = AdaptiveHopIqStore(Path(spec["bulk_root"]), read_only=True)
    started = time.monotonic()
    try:
        for scan in spec["scans"]:
            fs, edge, sid = scan["rate"], scan["edge"], scan["session_id"]
            with store.reader(sid) as reader:
                retained = {
                    v.event.visit_index: i
                    for i, v in enumerate(reader.session.manifest.receipt.visits)
                }
                for e in sorted(scan["examples"], key=lambda e: e["visit_index"]):
                    original = by_key[(sid, e["lane"])]
                    assert reader.session.manifest_sha256 == original["input_manifest_sha256"]
                    visit, raw = reader.read_visit_ci16(retained[e["visit_index"]])
                    start = e["probe_start_ms"] * fs // 1000
                    raw = raw[start : start + fs // 50, e["receiver_id"], :]
                    assert (
                        hashlib.sha256(raw.astype("<i2").tobytes()).hexdigest()
                        == original["probe_ci16_sha256"]
                    )
                    iq = raw[:, 0].astype(float) + 1j * raw[:, 1].astype(float)
                    w = e["candidate"]
                    epoch, fraction, cfo = (
                        w["integer_epoch_sample"],
                        w["fractional_epoch_offset_samples"],
                        w["acquired_cfo_hz"],
                    )
                    result = {
                        k: original[k]
                        for k in (
                            "session_id",
                            "split",
                            "rate",
                            "edge",
                            "channel",
                            "receiver_id",
                            "lane",
                        )
                    }
                    for physical in (False, True):
                        for shifted in (False, True):
                            key = ("plus_symbol_" if shifted else "") + (
                                "physical" if physical else "legacy"
                            )
                            trials = []
                            for delta in CFO_GRID:
                                surface = (
                                    original[key]
                                    if delta == 0
                                    else matched_surface(
                                        iq,
                                        fs,
                                        edge,
                                        epoch,
                                        fraction,
                                        cfo + delta,
                                        physical=physical,
                                        shift=round(fs * 4.4e-6) if shifted else 0,
                                    )
                                )
                                trials.extend(
                                    {"acquired_cfo_offset_hz": delta, **trial}
                                    for trial in surface["trials"]
                                )
                            result[key] = {
                                "best": max(trials, key=lambda t: t["margin"]),
                                "trials": trials,
                            }
                    chosen = result["physical"]["best"]
                    result["projection"] = per_tone_projection(
                        iq,
                        fs,
                        edge,
                        epoch,
                        fraction + chosen["offset_samples"],
                        chosen["tracking_cfo_hz"],
                    )
                    report["results"].append(result)
                    report["elapsed_seconds"] = time.monotonic() - started
                    args.output.write_text(json.dumps(report, indent=2))
                    print(
                        len(report["results"]),
                        sid,
                        e["lane"],
                        original["physical"]["best"]["margin"],
                        chosen["margin"],
                        flush=True,
                    )
    finally:
        store.close()


if __name__ == "__main__":
    main()
