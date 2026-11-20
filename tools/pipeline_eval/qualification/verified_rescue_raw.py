"""Measure later coded symbols at already estimated receiver coordinates."""

import json
import sys
from pathlib import Path
from time import process_time_ns

from leo.storage.fast_scan import FastSegmentSource

from ..variants.pilot_confirmation import PilotConfirmation


def measure_window(window, binding, confirmations):
    if (
        window.sequence != binding["sequence"]
        or window.iq_sha256 != binding["iq_sha256"]
        or window.acquisition["global_visit"] != binding["visit"]
        or window.acquisition["sample_start"] != binding["counter"]
        or window.target["channel"] != binding["channel"]
        or window.target["edge"] != binding["edge"]
    ):
        raise ValueError("raw samples or physical time differ from the detector visit")
    edge = binding["edge"]
    if edge not in confirmations:
        confirmations[edge] = PilotConfirmation(10_000_000, edge, minimum_margin=float("-inf"))
    proposals = [dict(receiver_id=lane, probe_start_ms=0, candidates=[]) for lane in (0, 1)]
    for entry in binding["gains"]:
        lane = entry["lane"]
        candidate = entry["winner"]
        if proposals[lane]["candidates"]:
            raise ValueError("duplicate winner for a receiver")
        proposals[lane]["candidates"].append(
            dict(
                epoch=candidate["integer_epoch_sample"],
                fractional_epoch=dict(
                    status="complete",
                    margin=candidate["fractional_margin"],
                    offset_samples=candidate["fractional_epoch_offset_samples"],
                    tracking_cfo_hz=candidate["fractional_tracking_cfo_hz"],
                ),
            )
        )
    start = process_time_ns()
    witness = confirmations[edge](window.samples, proposals)
    elapsed = process_time_ns() - start
    if set(witness) != {(g["lane"], 0) for g in binding["gains"]}:
        raise ValueError("a winning native packet lacks a late-symbol measurement")
    return dict(
        visit=binding["visit"],
        sequence=window.sequence,
        iq_sha256=window.iq_sha256,
        cpu_ns=elapsed,
        probes=[
            dict(
                lane=lane,
                frames=v.frames,
                block_z=list(v.block_z),
                pooled_z=v.pooled_z,
                passed=v.passed,
            )
            for (lane, _), v in sorted(witness.items())
        ],
    )


def stream(plan):
    expected = {s["visit"]: s for s in plan["visits"]}
    seen = set()
    confirmations = {}
    for segment, locator in enumerate(plan["segments"]):
        directory = Path(locator["path"]).resolve()
        if directory.name != "manifest.json" or not directory.is_relative_to(
            Path("/srv/bulk/leo/fast-scan-recordings").resolve()
        ):
            raise ValueError("recording outside the authenticated archive")
        source = FastSegmentSource(
            dict(path=str(directory.parent), manifest_digest="sha256:" + locator["sha256"])
        )
        for window in source.windows():
            visit = window.acquisition["global_visit"]
            if visit in expected:
                binding = expected[visit]
                if segment != binding["segment"] or visit in seen:
                    raise ValueError("duplicate or incorrectly segmented visit")
                seen.add(visit)
                print(json.dumps(measure_window(window, binding, confirmations)), flush=False)
    if seen != expected.keys():
        raise ValueError("missing recorded waveform for a proposed rescue")
    print(json.dumps(dict(complete=True, visits=len(seen))), flush=True)


if __name__ == "__main__":
    stream(json.load(sys.stdin))
