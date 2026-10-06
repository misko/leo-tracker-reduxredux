"""Bounded score-blind saved-probe acquisition; matched CFO coarse lattices."""

import argparse
import hashlib
import json
import time
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
from bandwidth_replay import filter_decimate

from leo.analysis.starlink.acquisition import (
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
    acquire_symbolwise,
)
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_scores, refine_glrt64_epochs
from leo.storage.adaptive_hop import AdaptiveHopIqStore


def settings(fs, limit):
    return SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=-limit,
        residual_cfo_max_hz=limit,
        maximum_probe_samples=fs // 50,
        retained_candidate_count=8,
        candidate_epoch_separation_samples=fs // 500000,
        candidate_cfo_separation_hz=10000,
        anchor_symbols=tuple(range(2, 302, 14)),
    )


def run(iq, fs, nominal, edge, limit, rx, budget=8):
    started = time.monotonic()
    cfg = replace(settings(fs, limit), retained_candidate_count=budget)
    cal = ReceiverFrequencyCalibration(str(rx), nominal, "0" * 64)
    result = acquire_symbolwise(iq, fs, cal, edge=edge, config=cfg)
    candidates = result.candidates
    epochs = tuple(c.refined_epoch_sample for c in candidates)
    cfos = tuple(c.absolute_cfo_hz for c in candidates)
    integer = (
        conditioned_glrt64_scores(iq, fs, epoch_samples=epochs, acquired_cfo_hz=cfos, edge=edge)
        if candidates
        else ()
    )
    refined = (
        refine_glrt64_epochs(
            iq,
            fs,
            integer_epoch_samples=epochs,
            acquired_cfo_hz=cfos,
            edge=edge,
            expected_integer_scores=integer,
        )
        if candidates
        else ()
    )
    scores = []
    for candidate, seed, refinement in zip(candidates, integer, refined, strict=True):
        scores.append(
            dict(
                acquisition=asdict(candidate),
                integer_glrt=asdict(seed),
                fractional_glrt=asdict(refinement),
            )
        )
    return dict(
        elapsed_seconds=time.monotonic() - started,
        config=asdict(cfg),
        status=result.status,
        candidates=scores,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    raw = args.spec.read_bytes()
    spec = json.loads(raw)
    out = dict(
        spec_sha256=hashlib.sha256(raw).hexdigest(),
        selection=(
            "One hash-selected retained visit per high-rate scan (CH1 lower, CH4 upper), "
            "probe 60–80ms, both RX. No published score consulted; "
            "scan selection still follows original cohort."
        ),
        settings=dict(
            full_limit_hz=800000,
            narrow_limit_hz=400000,
            narrow_reason=(
                "Conservative subset of ±429687.5 tone-center domain, "
                "preserves 80kHz coarse lattice as exact subset of full search."
            ),
            physical_epoch_separation_s=2e-6,
            candidate_budget=8,
            sample_support_s=0.020,
            minimum_frame_support=2,
            null=(
                "One deterministic broadband Gaussian RX0 probe per scan with matched "
                "original PSD; acquisition on all three treatments"
            ),
        ),
        rows=[],
    )
    args.output.write_text(json.dumps(out, indent=2))
    started = time.monotonic()
    store = AdaptiveHopIqStore(Path(spec["bulk_root"]), read_only=True)
    for scan in [s for s in spec["scans"] if s["rate"] == 10000000]:
        with store.reader(scan["session_id"]) as reader:
            channel = 1 if scan["edge"] == "lower" else 4
            visits = [
                (i, v)
                for i, v in enumerate(reader.session.manifest.receipt.visits)
                if v.event.target.channel == channel
            ]
            index, meta = min(
                visits,
                key=lambda t: hashlib.sha256(
                    f"20261006:{scan['session_id']}:{t[1].event.visit_index}".encode()
                ).hexdigest(),
            )
            visit, ci16 = reader.read_visit_ci16(index)
            assert visit.event.visit_index == meta.event.visit_index
            nominal = -312500 if scan["edge"] == "lower" else 312500
            for rx in (0, 1):
                vals = ci16[600000:800000, rx, :]
                iq = vals[:, 0].astype(float) + 1j * vals[:, 1].astype(float)
                assert len(iq) == 200000
                probes = [("saved_iq", iq)]
                if rx == 0:
                    seed = (
                        int(hashlib.sha256(scan["session_id"].encode()).hexdigest()[:8], 16)
                        ^ 20261006
                    )
                    rng = np.random.default_rng(seed)
                    null = (rng.normal(size=len(iq)) + 1j * rng.normal(size=len(iq))) * np.sqrt(
                        np.mean(abs(iq) ** 2) / 2
                    )
                    probes.append(("gaussian_null", null))
                for kind, x in probes:
                    low, _, _ = filter_decimate(x, nominal)
                    row = dict(
                        session_id=scan["session_id"],
                        split=scan["split"],
                        edge=scan["edge"],
                        visit_index=visit.event.visit_index,
                        channel=channel,
                        receiver_id=rx,
                        probe_start_ms=60,
                        kind=kind,
                        input_manifest_sha256=reader.session.manifest_sha256,
                        iq_sha256=hashlib.sha256(vals.astype("<i2").tobytes()).hexdigest()
                        if kind == "saved_iq"
                        else hashlib.sha256(x.astype("<c16").tobytes()).hexdigest(),
                    )
                    for label, signal, fs, center, limit in (
                        ("full", x, 10000000, nominal, 800000),
                        ("search_only", x, 10000000, nominal, 400000),
                        ("digitally_narrowed", low, 2500000, 0, 400000),
                    ):
                        row[label] = run(signal, fs, center, scan["edge"], limit, rx)
                        print(
                            scan["split"],
                            scan["session_id"],
                            rx,
                            kind,
                            label,
                            round(row[label]["elapsed_seconds"], 2),
                            flush=True,
                        )
                    out["rows"].append(row)
                    args.output.write_text(json.dumps(out, indent=2))
                    if time.monotonic() - started > 450:
                        out["stopped_at_runtime_bound"] = True
                        args.output.write_text(json.dumps(out, indent=2))
                        store.close()
                        return
    store.close()
    out["elapsed_seconds"] = time.monotonic() - started
    args.output.write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
