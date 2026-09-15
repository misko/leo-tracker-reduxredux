"""Full-budget 120 ms negative controls for the eight-hour PSS replay."""

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.analysis.starlink.pss_bandwidth import PssCaptureBand, acquire_pss_band
from leo.analysis.starlink.pss_search import compile_pss_projection, project_pss_block
from leo.analysis.starlink.pss_tracker import PssTracker, observations_from_search
from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.replay_scanner_pss_bandwidth import BANK


def run() -> dict:
    rows = []
    for kind in ("noise", "tone", "pilot_only"):
        for edge, center in (("lower", -115_195_312.5), ("upper", 115_195_312.5)):
            trackers = {label: PssTracker(label) for label in ("native10", "derived2p5")}
            for block in range(6):
                rng = np.random.default_rng(91500 + block)
                iq = (rng.normal(size=1_200_000) + 1j * rng.normal(size=1_200_000)).astype(
                    "complex64"
                )
                if kind == "tone":
                    iq += 10 * np.exp(2j * np.pi * 250_000 * np.arange(len(iq)) / 10e6)
                elif kind == "pilot_only":
                    pilot = qin_edge_pilot_frame(10e6, edge=edge)
                    iq += 10 * np.resize(pilot, len(iq))
                projection = compile_pss_projection(
                    input_sample_rate_hz=10_000_000,
                    input_center_frequency_hz=center,
                    rf_bandwidth_hz=10_000_000,
                    target_center_frequency_hz=center,
                    channel_reference_hz=0,
                )
                narrow = project_pss_block(
                    iq,
                    projection,
                    input_device_sample_start=block * 10_000_000,
                    continuity_segment_index=block,
                )
                for label, rate, values, start in (
                    ("native10", 10_000_000, iq, block * 10_000_000),
                    ("derived2p5", 2_500_000, narrow.samples, narrow.output_device_sample_start),
                ):
                    band = PssCaptureBand(rate, center, -rate / 2, rate / 2)
                    result = acquire_pss_band(
                        values,
                        band,
                        device_sample_start=start,
                        continuity_segment_index=block,
                        frequency_offsets_hz=BANK,
                    )
                    estimate = trackers[label].update(
                        label, (start + len(values) / 2) / rate, observations_from_search(result)
                    )
                    rows.append(
                        dict(
                            kind=kind,
                            edge=edge,
                            block=block,
                            band=label,
                            detected=any(h.qualified_candidates for h in result.hypotheses),
                            max_z=max(c.robust_z for h in result.hypotheses for c in h.candidates),
                            estimate=asdict(estimate),
                        )
                    )
            print(kind, edge, "complete", flush=True)
    return dict(
        seed_base=91500,
        blocks_per_kind_edge=6,
        duration_s=0.12,
        frequency_bank_hz=BANK,
        rows=rows,
        detections=dict(Counter(f"{r['kind']}:{r['band']}" for r in rows if r["detected"])),
        tracking_states=dict(Counter(r["estimate"]["state"] for r in rows)),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(run(), indent=2) + "\n")
