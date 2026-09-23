"""Bounded, two-direction forced pilot measurements for all both-RX detections."""

import argparse
import gzip
import hashlib
import itertools
import json
import time
from pathlib import Path

import numpy as np

from leo.analysis.starlink.adaptive_dual_rx_phase import (
    coherent_pilot_frames,
    pilot_symbol_reference_offsets_s,
)
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S, qin_edge_pilot_frame
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from tools.research import adaptive_coherence_metrics as metrics
from tools.research import replay_adaptive_multiscale_phase_refined as frontend

OUT = frontend.ROOT / "reports/figures/2026_09_23_relaxed_adaptive_coherence"
BINDINGS = [
    frontend.ROOT / "reports/figures/2026_09_23_scan_glrt_multiplicity" / name
    for name in ("relaxed-rx0-anchor-binding.json", "reciprocal-rx1-anchor-binding.json")
]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sources(row, arm):
    return row.get("anchor_sources") or row[f"rx{arm}_anchor_sources"]


def extract(iq, spec, raw_offset, edge, fs):
    candidate, starts, train, arm = (spec[k] for k in ("candidate", "starts", "train", "arm"))
    exact = qin_edge_pilot_frame(fs, edge)
    control = qin_edge_pilot_frame(fs, edge, symbol_roll=17)
    offsets = pilot_symbol_reference_offsets_s(fs, OFDM_SYMBOL_DURATION_S, np.arange(2, 66), exact)
    fraction = candidate["fractional_epoch"]
    reference = (candidate["epoch"] + fraction) / fs
    native = candidate["acquired_cfo_hz"]
    f0 = native if arm == 0 else native - raw_offset
    models = ((reference, 0.0, f0), (reference, 0.0, f0 + raw_offset))
    coeff, controls, wrong, residuals = [], [], [], []
    for receiver in (0, 1):
        model = models[receiver]
        ex = frontend.symbol_correlations(iq, starts, 0, model, receiver, exact, fraction)
        co = frontend.symbol_correlations(iq, starts, 0, model, receiver, control, fraction)
        _, _, residual, _ = coherent_pilot_frames(
            ex[train], co[train], offsets, OFDM_SYMBOL_DURATION_S
        )
        frames, control_frames, _, _ = coherent_pilot_frames(
            ex, co, offsets, OFDM_SYMBOL_DURATION_S, forced_residual_hz=residual
        )
        wx = frontend.symbol_correlations(iq, starts, 37, model, receiver, exact, fraction)
        wrong_frames, _, _, _ = coherent_pilot_frames(
            wx, wx, offsets, OFDM_SYMBOL_DURATION_S, forced_residual_hz=residual
        )
        coeff.append(frames)
        controls.append(control_frames)
        wrong.append(wrong_frames)
        residuals.append(residual)
    times = frontend.frame_origin_times(starts, 0, fraction, fs)
    stats = metrics.source_metrics(*coeff, controls, wrong, times, train)
    restore = frontend.frontend.carrier_phase(models[1], 0.06) - frontend.frontend.carrier_phase(
        models[0], 0.06
    )
    product = coeff[1] * np.conj(coeff[0]) * np.exp(1j * restore)
    weights = np.sqrt(abs(coeff[0]) * abs(coeff[1]))
    frame = {
        "times": times,
        "train": train,
        "product": product,
        "weights": weights,
        "metrics": stats,
    }
    saved = {
        "times": times.tolist(),
        "train": train.tolist(),
        "product_real": product.real.tolist(),
        "product_imag": product.imag.tolist(),
        "weights": weights.tolist(),
    }
    return (
        {
            "arm": arm,
            "anchor_index": spec["anchor_index"],
            "candidate": candidate,
            "within_frame_residual_hz": residuals,
            "metrics": stats,
            "failure": None,
        },
        frame,
        saved,
    )


def run(shard=0, shards=1):
    if not 0 <= shard < shards:
        raise ValueError("invalid shard")
    suffix = f"-part-{shard}" if shards > 1 else ""
    bindings = [json.loads(p.read_text()) for p in BINDINGS]
    maps = [{r["visit_index"]: r for r in b["rows"]} for b in bindings]
    if maps[0].keys() != maps[1].keys():
        raise ValueError("reciprocal cohorts differ")
    OUT.mkdir(parents=True, exist_ok=True)
    document = {
        "binding_sha256": [digest(p) for p in BINDINGS],
        "source_sha256": digest(__file__),
        "metrics_sha256": digest(metrics.__file__),
        "protocol_sha256": digest(
            frontend.ROOT / "reports/2026_09_23_relaxed_adaptive_coherence_protocol.md"
        ),
        "shard": shard,
        "shards": shards,
        "rows": [],
    }
    start_clock = time.monotonic()
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        with (
            AdaptiveHopAnalysisInputStore(store).source(bindings[0]["session_id"]) as source,
            gzip.open(OUT / f"frames{suffix}.jsonl.gz", "wt") as frame_file,
        ):
            if source.input_manifest_sha256 != bindings[0]["input_manifest_sha256"]:
                raise ValueError("capture binding changed")
            for visit_id in sorted(maps[0])[shard::shards]:
                bound = maps[0][visit_id]
                fs = bound["sample_rate_hz"]
                frontend.frontend.FS = fs
                if source.visits[bound["iq_ordinal"]].event.visit_index != visit_id:
                    raise ValueError("visit ordinal changed")
                iq = source.read_visit(bound["iq_ordinal"])
                specs = []
                for arm in (0, 1):
                    for index, candidate in enumerate(sources(maps[arm][visit_id], arm)):
                        starts = frontend.frontend.frame_starts(
                            candidate["epoch"], 0, round(0.12 * fs)
                        )
                        specs.append(
                            {
                                "arm": arm,
                                "anchor_index": index,
                                "candidate": candidate,
                                "starts": starts,
                                "train": frontend.frontend.split_frames(len(starts), 126),
                            }
                        )
                raw_starts = metrics.common_training_starts(
                    [(s["starts"], s["train"]) for s in specs], len(iq), round(fs / 750)
                )
                row = {
                    "visit_index": visit_id,
                    "channel": bound["channel"],
                    "time_s": bound["time_s"],
                    "strict_pairs": bound["strict_phase_blind_pair_count"],
                    "strict_reference": bound["strict_reference_two_source"],
                    "raw_training_windows": len(raw_starts),
                    "sources": [],
                    "pairs": [],
                    "failure": None,
                }
                try:
                    offset = metrics.common_raw_offset(iq, raw_starts, fs)
                except ValueError as error:
                    row["failure"] = str(error)
                    document["rows"].append(row)
                    continue
                row["raw_receiver_offset_hz"] = offset
                frames = {}
                for spec in specs:
                    key = (spec["arm"], spec["anchor_index"])
                    try:
                        result, frame, saved = extract(iq, spec, offset, bound["edge"], fs)
                        frames[key] = frame
                        frame_file.write(
                            json.dumps(
                                {
                                    "visit_index": visit_id,
                                    "arm": key[0],
                                    "anchor_index": key[1],
                                    **saved,
                                }
                            )
                            + "\n"
                        )
                    except ValueError as error:
                        result = {
                            "arm": key[0],
                            "anchor_index": key[1],
                            "candidate": spec["candidate"],
                            "failure": str(error),
                        }
                    row["sources"].append(result)
                for arm in (0, 1):
                    keys = sorted(key for key in frames if key[0] == arm)
                    for left, right in itertools.combinations(keys, 2):
                        row["pairs"].append(
                            {
                                "arm": arm,
                                "anchors": [left[1], right[1]],
                                **metrics.pair_metrics(frames[left], frames[right]),
                            }
                        )
                document["rows"].append(row)
                if len(document["rows"]) % 10 == 0:
                    print(
                        f"Worker {shard}: {len(document['rows'])} visits; "
                        f"elapsed {time.monotonic() - start_clock:.1f}s",
                        flush=True,
                    )
                    (OUT / f"partial-results{suffix}.json").write_text(
                        json.dumps(document, indent=2) + "\n"
                    )
    finally:
        store.close()
    document["elapsed_s"] = time.monotonic() - start_clock
    (OUT / f"results{suffix}.json").write_text(json.dumps(document, indent=2) + "\n")
    print(f"Complete: {len(document['rows'])} visits in {document['elapsed_s']:.1f}s", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    args = parser.parse_args()
    run(args.shard, args.shards)
