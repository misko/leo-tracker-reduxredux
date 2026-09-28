"""Bounded public-port freeze and pilot split measurement; no pose reads."""

import argparse
import hashlib
import inspect
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

from ds7_cfo_wave2_freeze import freeze  # noqa: E402
from ds789_pilot_split import evaluate_frame  # noqa: E402
from leo.application.scanner_trajectory import project_scanner_candidates  # noqa: E402
from leo.storage.adaptive_hop import AdaptiveHopIqStore  # noqa: E402
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore  # noqa: E402

from leo.analysis.qam.pilot import _complete_frame_starts, _KnownPilotDemodulator  # noqa: E402
from leo.analysis.research import frame_cfo  # noqa: E402
from leo.analysis.starlink import (  # noqa: E402
    OFDM_SYMBOL_DURATION_S,
    StarlinkEdge,
    qin_edge_pilot_symbols,
)

INPUTS = {
    "DS7": "reports/2026_09_27_ds7_wave1/baseline/exports/scan-fw-5f7bf896e4552887-tracks.json",
    "DS8": "reports/2026_09_28_ds89_baseline_transfer/exports/DS8-001/observations.json",
    "DS9": "reports/2026_09_28_ds89_baseline_transfer/exports/DS9-001/observations.json",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", choices=INPUTS)
    parser.add_argument("stage", choices=("freeze", "measure"))
    args = parser.parse_args()
    target = HERE / args.dataset
    target.mkdir(exist_ok=True)
    source = ROOT / INPUTS[args.dataset]
    baseline = json.loads(source.read_text())
    store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        raw = store.load(baseline["session_id"])
    finally:
        store.close()
    assert raw.input_manifest_sha256 == baseline["manifest_sha256"]
    assert raw.analysis_manifest_sha256 == baseline["analysis_manifest_sha256"]
    probes = {(p.visit_index, p.receiver_id, p.probe_index): p for p in raw.probes}
    points = {p.candidate_id: p for p in project_scanner_candidates(raw)}
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        published = store.inspect(raw.session_id)
        assert published.manifest_sha256 == raw.input_manifest_sha256
        receipt = published.manifest.receipt
        if args.stage == "freeze":
            spec = freeze(raw, baseline, None, visits_per_partition=1)
            assert len(spec["windows"]) == 4
            spec["baseline_path"] = INPUTS[args.dataset]
            spec["baseline_sha256"] = digest(source)
            spec["selection"] = (
                "earliest all-training and all-held common visits; first candidate ID per receiver"
            )
            spec["methods"] = ["baseline", "ordinary", "robust"]
            spec["held_policy"] = "within-frame alternating even-Qin rows, no temporal line"
            spec["iq_limit_bytes"] = 64 * 1024**2
            spec["chunk_limit_bytes"] = 256 * 1024**2
            spec["compute_limit_seconds"] = 120
            spec["runtime_sha256"] = {
                inspect.getfile(obj): digest(inspect.getfile(obj))
                for obj in (
                    frame_cfo,
                    _KnownPilotDemodulator,
                    AdaptiveHopIqStore,
                    ScannerTrackingInputStore,
                    project_scanner_candidates,
                )
            }
            selected = {w["visit_index"] for w in spec["windows"]}
            chunks = [
                c
                for c in published.manifest.chunks
                if any(
                    c.first_visit_index <= v < c.first_visit_index + c.visit_count for v in selected
                )
            ]
            spec["unique_chunk_uncompressed_bytes"] = sum(c.uncompressed_bytes for c in chunks)
            spec["returned_visit_bytes"] = sum(
                receipt.visits[v].valid_sample_count * 8 for v in selected
            )
            assert spec["returned_visit_bytes"] <= spec["iq_limit_bytes"]
            assert spec["unique_chunk_uncompressed_bytes"] <= spec["chunk_limit_bytes"]
            for w in spec["windows"]:
                probe = probes[(w["visit_index"], w["receiver_id"], w["probe_index"])]
                point = points[w["candidate_id"]]
                (candidate,) = [
                    c for c in probe.candidates if c.candidate_rank == point.candidate_rank
                ]
                w["integer_epoch_sample"] = candidate.integer_epoch_sample
                w["fractional_epoch_offset_samples"] = candidate.fractional_epoch_offset_samples
                w["probe_payload_start_sample"] = probe.payload_start_sample
                w["visit_payload_start_sample"] = sum(
                    v.valid_sample_count for v in receipt.visits[: w["visit_index"]]
                )
                assert candidate.fractional_tracking_cfo_hz == w["acquisition_bound_cfo_hz"]
            write(target / "spec.json", spec)
            return
        spec = json.loads((target / "spec.json").read_text())
        assert digest(source) == spec["baseline_sha256"]
        assert raw.analysis_manifest_sha256 == spec["analysis_manifest_sha256"]
        assert raw.raw_recording_authority_digest == spec["raw_recording_authority_sha256"]
        for path, sha in spec["runtime_sha256"].items():
            assert digest(path) == sha
        reader = store.reader(raw.session_id, expected=published)
        try:
            visits = {
                v: reader.read_visit_ci16(v)[1]
                for v in sorted({w["visit_index"] for w in spec["windows"]})
            }
        finally:
            reader.close()
    finally:
        store.close()
    assert sum(v.nbytes for v in visits.values()) == spec["returned_visit_bytes"]
    even = np.arange(0, 300, 2)
    times = (even.astype(float) - even.mean()) * OFDM_SYMBOL_DURATION_S
    archive = {"times_s": times}
    windows = []
    for wi, w in enumerate(spec["windows"]):
        packed = visits[w["visit_index"]]
        probe = probes[(w["visit_index"], w["receiver_id"], w["probe_index"])]
        assert probe.payload_start_sample == w["probe_payload_start_sample"]
        start = probe.payload_start_sample - w["visit_payload_start_sample"]
        count = round(raw.probe_ms * raw.sample_rate_hz / 1000)
        assert start >= 0 and start + count <= len(packed)
        values = packed[start : start + count, w["receiver_id"]]
        samples = values[:, 0].astype(float) + 1j * values[:, 1].astype(float)
        epoch = round(w["integer_epoch_sample"] + w["fractional_epoch_offset_samples"])
        starts = _complete_frame_starts(len(samples), raw.sample_rate_hz, epoch)
        demod = _KnownPilotDemodulator(
            samples, raw.sample_rate_hz, StarlinkEdge(w["edge"]), w["acquisition_bound_cfo_hz"]
        )
        expected = qin_edge_pilot_symbols(StarlinkEdge(w["edge"]))
        frames = []
        for fi, frame_start in enumerate(starts):
            matched = demod.frame(frame_start)[even] * np.conj(expected[even])
            key = f"w{wi}_f{fi}"
            archive[key] = matched
            seed = 2026092800 + wi * 100 + fi
            frames.append(
                {
                    "matrix_key": key,
                    "seed": seed,
                    "frame_start": int(frame_start),
                    **evaluate_frame(matched, times, seed=seed),
                }
            )
        windows.append(
            {
                "window_index": wi,
                "candidate_id": w["candidate_id"],
                "receiver_id": w["receiver_id"],
                "visit_index": w["visit_index"],
                "frames": frames,
                "state": "returned" if frames else "no_complete_frames",
            }
        )
    with (target / "matrices.npz").open("xb") as stream:
        np.savez_compressed(stream, **archive)
    write(
        target / "result.json",
        {
            "dataset_id": args.dataset,
            "spec_sha256": digest(target / "spec.json"),
            "matrices_sha256": digest(target / "matrices.npz"),
            "windows": windows,
        },
    )


if __name__ == "__main__":
    main()
