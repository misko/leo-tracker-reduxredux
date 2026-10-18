"""Read existing GLRT frame epochs; do not collect or reprocess RF."""

import hashlib
import json
from pathlib import Path


def frame_epochs(document, scores):
    source = document["source"]
    fs = source["sample_rate_hz"]
    anchor = document["clock_anchor"]["sample_counter"]
    lookup = {
        (r["receiver"], r["channel"], r["valid_start_counter"]): oid for oid, r in scores.items()
    }
    if len(lookup) != len(scores):
        raise ValueError("duplicate score-window identity")
    result = {}
    for probe in source["probes"]:
        eligible = [c for c in probe["candidates"] if c["passed_fractional_margin_gate"] is True]
        if not eligible:
            continue
        peak = max(eligible, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]))
        key = (probe["receiver_id"] + 1, probe["channel"], probe["valid_start_counter"])
        oid = lookup[key]
        if abs(peak["fractional_tracking_cfo_hz"] - scores[oid]["measured_cfo_hz"]) > 1e-8:
            raise ValueError("winning CFO differs")
        epoch = peak["integer_epoch_sample"] + peak["fractional_epoch_offset_samples"]
        start = probe["valid_start_counter"] + round(probe["probe_start_ms"] * fs / 1000)
        elapsed = (start - anchor + epoch) / fs
        result[oid] = dict(
            receiver=key[0],
            channel=key[1],
            probe_device_counter=start,
            integer_epoch_sample=peak["integer_epoch_sample"],
            fractional_epoch_offset_samples=peak["fractional_epoch_offset_samples"],
            frame_epoch_elapsed_s=elapsed,
            frame_phase_modulo_s=elapsed % (1 / 750),
            fractional_margin=peak["fractional_margin"],
        )
    if result.keys() != scores.keys():
        raise ValueError("frame epoch inventory differs from frozen scores")
    return result


def run():
    root = Path(__file__).resolve().parents[1]
    sources = json.loads(
        (root / "reports/2026_10_16_dsx01_fast_association_losses/sources.json").read_text()
    )
    scores = json.loads(
        (root / "reports/2026_10_18_dsx01_causal_repairs/glrt_scores.json").read_text()
    )
    result = {}
    for source in sources:
        case = "DSX01-" + source["source_id"]
        raw = Path(source["tracking_input_path"]).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != scores[case]["source_sha256"]:
            raise ValueError("source bytes changed")
        document = json.loads(raw)
        result[case] = dict(
            source_sha256=digest,
            source_origin_utc_ns=source["first_sample_estimate_utc_ns"],
            sample_rate_hz=document["source"]["sample_rate_hz"],
            frame_period_s=1 / 750,
            detector_integer_phase_ring_samples=round(document["source"]["sample_rate_hz"] / 750),
            physical_frame_period_samples=document["source"]["sample_rate_hz"] / 750,
            extraction_is_delay_coordinate_not_yet_validated_pseudorange=True,
            epochs=frame_epochs(document, scores[case]["scores"]),
        )
    return result


if __name__ == "__main__":
    print(json.dumps(run()))
