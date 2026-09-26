#!/usr/bin/env python3
"""Bounded same-cohort acquisition mechanism ablations."""

from __future__ import annotations

import argparse
import dataclasses
import json
import time
from pathlib import Path

from replay_acquisition import INPUT_MANIFEST_SHA256, SESSION_ID
from run_legacy_ablation import SparseConfig

from leo.analysis.starlink.pilot_search_geometry import compile_pilot_search_geometry
from leo.analysis.starlink.templates import edge_frequencies_hz
from leo.contracts.starlink_frequency import starlink_edge_rf_center_frequency_hz
from leo.scanner.detector import Glrt64SearchGeometry, analyze_glrt64_dwell
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore


def run(root: Path, out: Path, visit: int, mode: str):
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"visit-{visit:06d}.{mode}.json"
    if dest.exists():
        return
    store = AdaptiveHopAnalysisInputStore(AdaptiveHopIqStore(root, read_only=True))
    started = time.monotonic()
    with store.source(SESSION_ID) as source:
        if source.input_manifest_sha256 != INPUT_MANIFEST_SHA256:
            raise ValueError("manifest")
        samples = source.read_visit(visit)
        event = source.visits[visit].event
        cap = source.receipt.plan.geometry
        half = min(cap.sample_rate_hz, cap.bandwidth_hz) / 2
        nominal = (
            starlink_edge_rf_center_frequency_hz(event.target.channel, event.target.edge)
            - cap.lnb_lo_hz
            - event.actual_lo_frequency_hz
        )
        offsets = edge_frequencies_hz(event.target.edge)
        observable = min(
            nominal + float(offsets.min()) + half, half - nominal - float(offsets.max())
        )
        width = observable if mode == "wider_coverage" else min(800_000.0, observable)
        refs = tuple(
            compile_pilot_search_geometry(
                receiver_id=x,
                starlink_channel=event.target.channel,
                edge=event.target.edge,
                tuned_center_frequency_hz=event.actual_lo_frequency_hz,
                sample_rate_hz=cap.sample_rate_hz,
                rf_bandwidth_hz=cap.bandwidth_hz,
                residual_cfo_min_hz=-width,
                residual_cfo_max_hz=width,
                lnb_lo_hz=cap.lnb_lo_hz,
            ).frequency_reference
            for x in (0, 1)
        )
        fallback = tuple(range(2, 302, 14)) if mode in ("fallback", "shortlist22") else ()
        geometry = Glrt64SearchGeometry(refs, -width, width, fallback)
        cfg = SparseConfig(maximum_acquisition_candidates=22 if mode == "shortlist22" else 8)
        analysis = analyze_glrt64_dwell(
            samples, cfg, edge=event.target.edge, search_geometry=geometry
        )
    dest.write_text(
        json.dumps(
            {
                "schema": "scan-acquisition-mechanism-ablation/v1",
                "visit_index": visit,
                "mode": mode,
                "runtime_seconds": time.monotonic() - started,
                "residual_half_width_hz": width,
                "analysis": dataclasses.asdict(analysis),
            },
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("visit", type=int)
    p.add_argument("mode", choices=("tuning_only", "wider_coverage", "fallback", "shortlist22"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--root", type=Path, default=Path("/srv/bulk/leo"))
    a = p.parse_args()
    run(a.root, a.output, a.visit, a.mode)
