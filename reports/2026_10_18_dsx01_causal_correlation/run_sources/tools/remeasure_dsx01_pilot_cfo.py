"""One bounded existing-IQ pass on the original curved population of one scan."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from dsx01_glrt_remeasurement import evaluate
from probe_dsx01_pilot_clock import ROOT, write


def run(case, output, selection):
    from leo.storage.fast_scan import FastScanStore, FastSegmentSource

    started = time.monotonic()
    ids = set(json.loads(selection.read_text()))
    if not 1 <= len(ids) <= 3000:
        raise ValueError("bounded single-scan assay permits at most 3000 original points")
    sources = json.loads(
        (ROOT / "reports/2026_10_16_dsx01_fast_association_losses/sources.json").read_text()
    )
    source = next(s for s in sources if "DSX01-" + s["source_id"] == case)
    payload = Path(source["tracking_input_path"]).read_bytes()
    if "sha256:" + hashlib.sha256(payload).hexdigest() != source["tracking_input_sha256"]:
        raise ValueError("original tracking input changed")
    source_doc = json.loads(payload)["source"]
    if source_doc["sample_rate_hz"] != 2_500_000 or source_doc["probe_ms"] != 20:
        raise ValueError("assay is qualified for existing 20-ms 2.5-MS/s windows only")
    scores = json.loads(
        (ROOT / "reports/2026_10_18_dsx01_causal_repairs/glrt_scores.json").read_text()
    )[case]
    if scores["source_sha256"] != hashlib.sha256(payload).hexdigest():
        raise ValueError("frozen score source differs")
    lookup = {
        (v["receiver"], v["channel"], v["valid_start_counter"]): k
        for k, v in scores["scores"].items()
        if k in ids
    }
    byvisit = {}
    for probe in source_doc["probes"]:
        key = (probe["receiver_id"] + 1, probe["channel"], probe["valid_start_counter"])
        if key not in lookup:
            continue
        winner = max(
            (c for c in probe["candidates"] if c["passed_fractional_margin_gate"]),
            key=lambda c: (c["fractional_margin"], -c["candidate_rank"]),
        )
        oid = lookup[key]
        if (
            abs(winner["fractional_tracking_cfo_hz"] - scores["scores"][oid]["measured_cfo_hz"])
            > 1e-8
        ):
            raise ValueError("original winning CFO differs")
        byvisit.setdefault(probe["visit_index"], []).append((oid, probe, winner))
    if sum(map(len, byvisit.values())) != len(ids):
        raise ValueError("original curved observation inventory differs")
    output.mkdir(parents=True, exist_ok=False)
    write(
        output / "protocol.json",
        dict(
            case=case,
            original_points=len(ids),
            selection_sha256=hashlib.sha256(selection.read_bytes()).hexdigest(),
            selected_observation_ids=sorted(ids),
            original_source_sha256=source["tracking_input_sha256"],
            maximum_elapsed_seconds=600,
            no_new_RF=True,
            no_satellite_or_GPS_selection=True,
            acquisition_epochs_aliases_and_original_graph_partition_frozen=True,
            variants=["glrt64", "glrt300", "midpoint300"],
            frequency_grid_size=16384,
            rejected_refinements_keep_original_measurement=True,
            sources_sha256={
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [Path(__file__), ROOT / "tools/dsx01_glrt_remeasurement.py"]
            },
        ),
    )
    inventory = FastScanStore("/srv/bulk/leo").source(
        source_doc["session_id"], source_doc["input_manifest_sha256"]
    )
    results = {}
    for segment in inventory["segments"]:
        adapter = FastSegmentSource(segment)
        for window in adapter.windows():
            if time.monotonic() - started > 600:
                raise TimeoutError("bounded existing-IQ assay exceeded600seconds")
            for oid, probe, winner in byvisit.get(window.acquisition["global_visit"], []):
                if (
                    oid in results
                    or probe["valid_start_counter"] != window.acquisition["sample_start"]
                ):
                    raise ValueError("duplicate or mismatched physical IQ support")
                raw = window.samples[:, adapter.receiver_ids.index(probe["receiver_id"]), :]
                iq = raw[:, 0].astype(np.float64) + 1j * raw[:, 1].astype(np.float64)
                measured = winner["fractional_tracking_cfo_hz"]
                r = evaluate(
                    iq,
                    winner["integer_epoch_sample"],
                    winner["fractional_epoch_offset_samples"],
                    measured,
                    probe["edge"],
                )
                results[oid] = dict(
                    receiver=probe["receiver_id"] + 1,
                    channel=probe["channel"],
                    visit_index=probe["visit_index"],
                    valid_start_counter=probe["valid_start_counter"],
                    original_cfo_hz=measured,
                    iq_sha256=window.iq_sha256,
                    segment_manifest_sha256=segment["manifest_digest"],
                    **r,
                )
                if len(results) % 100 == 0:
                    write(
                        output / "progress.json",
                        dict(points=len(results), seconds=time.monotonic() - started),
                    )
                    print(
                        json.dumps(dict(points=len(results), seconds=time.monotonic() - started)),
                        flush=True,
                    )
            if len(results) == len(ids):
                break
        if len(results) == len(ids):
            break
    if results.keys() != ids:
        raise ValueError("not all original curved points were remeasured")

    def encode(value):
        if isinstance(value, np.ndarray):
            return value.tolist()
        raise TypeError(type(value).__name__)

    (output / "measurements.json").write_text(
        json.dumps(
            dict(case=case, points=results, seconds=time.monotonic() - started),
            default=encode,
            allow_nan=False,
        )
        + "\n"
    )
    print(json.dumps(dict(completed=len(results), seconds=time.monotonic() - started)), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="DSX01-S05")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    a = parser.parse_args()
    run(a.case, a.output, a.selection)
