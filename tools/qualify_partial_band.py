#!/usr/bin/env python3
"""Bounded independent null trials and paired saved-IQ low-rate qualification.

This tool reads the public capture store and writes only a selected report file.
It never acquires RF, alters captures, or changes production jobs.
"""

import argparse
import json
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from scipy import signal

from leo.analysis.starlink.partial_band import analyze_partial_band_probe
from leo.analysis.starlink.pilot_search_geometry import compile_pilot_search_geometry
from leo.contracts.digests import sha256_digest
from leo.contracts.partial_band import PartialBandConfigurationV1
from leo.scanner.detector import Glrt64SearchGeometry, analyze_glrt64_dwell
from leo.storage.adaptive_hop import AdaptiveHopIqStore


def null_trial(seed):
    rng = np.random.default_rng(seed)
    high = (rng.normal(size=50000) + 1j * rng.normal(size=50000)).astype(np.complex64)
    taps = signal.firwin(65, 550000.0, fs=2500000.0, window=("kaiser", 8.0))
    x = signal.resample_poly(high, 1, 2, window=taps)
    result = analyze_partial_band_probe(x, edge="upper", split_seed=seed)
    return dict(
        seed=seed,
        passed=any(c.passed for c in result.candidates),
        maximum_evaluation_score=max(c.evaluation_score for c in result.candidates),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--session-id", default="scan-fw-1c2ffb0e3c09fe8f")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--null-trials", type=int, default=1000)
    args = parser.parse_args()
    if not 1 <= args.null_trials <= 2000:
        parser.error("null trial budget must be 1..2000")
    started = time.monotonic()
    with ProcessPoolExecutor(
        max_workers=4, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        nulls = list(pool.map(null_trial, range(10000, 10000 + args.null_trials), chunksize=8))
    print(
        json.dumps(dict(null_trials=len(nulls), false_candidates=sum(n["passed"] for n in nulls))),
        flush=True,
    )
    store = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    capture = store.inspect(args.session_id)
    receipt = capture.manifest.receipt
    visits = receipt.visits
    geometry = receipt.plan.geometry
    if geometry.sample_rate_hz != 2500000:
        raise ValueError("paired reference must be captured at 2.5 MS/s")
    rng = np.random.default_rng(20261003)
    selected = sorted(
        int(i)
        for ch in (1, 2, 3, 4)
        for i in rng.choice(
            [i for i, v in enumerate(visits) if v.event.target.channel == ch], size=4, replace=False
        )
    )
    cfg = SimpleNamespace(
        dwell_samples=50000,
        probe_samples=50000,
        probe_stride_ms=20,
        probe_stride_samples=50000,
        scheduled_probe_count=1,
        sample_rate_hz=2500000,
        receiver_ids=(0, 1),
        probe_ms=20,
        glrt64_margin_gate=0.025,
        maximum_acquisition_candidates=8,
    )
    rows = []
    with store.reader(args.session_id, expected=capture) as reader:
        for ordinal in selected:
            if time.monotonic() - started > 540:
                raise TimeoutError("qualification exhausted its bounded compute budget")
            visit, ci16 = reader.read_visit_ci16(ordinal)
            values = ci16[:, :, 0].astype(np.float32) + 1j * ci16[:, :, 1].astype(np.float32)
            # Filter the entire valid dwell before selecting a corresponding window.
            taps = signal.firwin(65, 550000.0, fs=2500000.0, window=("kaiser", 8.0))
            low = signal.resample_poly(values, 1, 2, axis=0, window=taps)
            calibrations = tuple(
                compile_pilot_search_geometry(
                    receiver_id=rx,
                    starlink_channel=visit.event.target.channel,
                    edge=visit.event.target.edge,
                    tuned_center_frequency_hz=visit.event.actual_lo_frequency_hz,
                    sample_rate_hz=2500000,
                    rf_bandwidth_hz=geometry.bandwidth_hz,
                    residual_cfo_min_hz=-400000.0,
                    residual_cfo_max_hz=400000.0,
                    lnb_lo_hz=geometry.lnb_lo_hz,
                ).frequency_reference
                for rx in (0, 1)
            )
            baseline = analyze_glrt64_dwell(
                values[:50000],
                cfg,
                edge=visit.event.target.edge,
                search_geometry=Glrt64SearchGeometry(
                    receiver_calibrations=calibrations,
                    residual_cfo_min_hz=-400000.0,
                    residual_cfo_max_hz=400000.0,
                    fallback_anchor_symbols=tuple(range(2, 302, 14)),
                ),
            )
            for rx in (0, 1):
                result = analyze_partial_band_probe(
                    low[:25000, rx], edge=str(visit.event.target.edge)
                )
                reference = next(p for p in baseline.probes if p.receiver_id == rx)
                rows.append(
                    dict(
                        visit_index=ordinal,
                        channel=visit.event.target.channel,
                        edge=str(visit.event.target.edge),
                        receiver_id=rx,
                        source_ci16_sha256=sha256_digest(np.ascontiguousarray(ci16).tobytes()),
                        reference_candidates=[asdict(c) for c in reference.candidates],
                        partial_candidates=[c.model_dump(mode="json") for c in result.candidates],
                    )
                )
            print(
                json.dumps(dict(paired_visits=len(rows) // 2, total_visits=len(selected))),
                flush=True,
            )
    store.close()
    report = dict(
        schema_version=1,
        configuration=PartialBandConfigurationV1().model_dump(mode="json"),
        source_session_id=args.session_id,
        source_manifest_sha256=capture.manifest_sha256,
        selection_seed=20261003,
        selection_policy="four random complete visits per recorded channel; first 20ms; both RX",
        baseline_search_hz=[-400000, 400000],
        partial_search_hz=[-800000, 800000],
        comparison_scope=(
            "Compare matched candidates only inside the shared search range; "
            "native scan is not paired with this recording"
        ),
        null_model=(
            "independent proper complex Gaussian noise, filtered at 2.5 MS/s "
            "then decimated; seeds 10000 onward"
        ),
        null_trials=nulls,
        paired_probes=rows,
        elapsed_s=time.monotonic() - started,
        limitations=[
            "Empirical null trials do not prove field-wide false-alarm probability",
            "Receiver filter is approximate; scientific output remains candidate-only",
        ],
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(dict(report=str(args.output), elapsed_s=report["elapsed_s"])), flush=True)


if __name__ == "__main__":
    main()
