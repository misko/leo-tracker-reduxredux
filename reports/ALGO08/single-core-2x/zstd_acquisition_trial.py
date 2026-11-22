"""Compare verified ingress on two complete chunks through conditional acquisition."""

import argparse
import json
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from unittest.mock import patch

from leo.contracts.digests import canonical_digest
from leo.storage.fast_scan import FastSegmentSource
from leo.storage.short_window import ShortWindowReader
from tools import algo08_scan
from tools.pipeline_eval.variants.experimental.paired_sha256 import (
    PairedSha256,
    paired_decoded_hashes,
)
from tools.pipeline_eval.variants.experimental.receiver_arena_ingress import rotating_arenas
from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer
from tools.pipeline_eval.variants.experimental.receiver_zstd_arena import runtime
from tools.pipeline_eval.variants.experimental.residual_receiver import (
    DETECTOR_SHA256,
    ResidualReceiver,
)


def _pin(directory, name, source, expected_sha256):
    content = Path(source).read_bytes()
    if sha256(content).hexdigest() != expected_sha256:
        raise ValueError(f"{name} differs from its reviewed digest")
    destination = directory / name
    destination.write_bytes(content)
    return destination


def _acquire(inventory, assets, paired, arenas):
    limit = inventory["window_count"]
    reader_cpu = 0.0

    class Prefix(FastSegmentSource):
        def __init__(self, entry):
            super().__init__(entry, stop_sequence=limit)

        def windows(self):
            nonlocal reader_cpu
            iterator = super().windows()
            while True:
                start = process_time()
                window = next(iterator, None)
                reader_cpu += process_time() - start
                if window is None:
                    break
                yield window

    receiver = ResidualReceiver()
    verifier = paired_decoded_hashes(paired) if arenas is None else arenas.install(paired)
    counts_before = arenas.counts.copy() if arenas else None
    faults_before = getrusage(RUSAGE_SELF).ru_minflt
    start_cpu, start_wall = process_time(), perf_counter()
    with (
        patch.object(algo08_scan, "FastSegmentSource", Prefix),
        patch.object(algo08_scan, "detector", receiver.detector),
        compressed_input_buffer(),
        verifier,
    ):
        recording = Path(inventory["segments"][0]["path"])
        data = algo08_scan.acquire(recording.name, canonical_digest(inventory), inventory, assets)
    total_cpu, total_wall = process_time() - start_cpu, perf_counter() - start_wall
    provenance, source = data["provenance"], data["source"]
    counts = (arenas.counts - counts_before) if arenas else None
    if counts is not None and counts["decoded"] != 2:
        raise ValueError("Expected both sealed chunks to take the arena path")
    return dict(
        acquisition_cpu_s=total_cpu,
        acquisition_wall_s=total_wall,
        reader_cpu_s=reader_cpu,
        minor_faults=getrusage(RUSAGE_SELF).ru_minflt - faults_before,
        peak_process_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
        receiver=receiver.receipt(),
        arenas=counts,
        processed=provenance["processed_windows"],
        exclusions=provenance["invalid_capture"],
        raw_sha256=source["raw_recording_authority_digest"],
        factors_sha256=canonical_digest(source["probes"]),
        detections_sha256=canonical_digest(data),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("manifest_sha256")
    parser.add_argument("assets", type=Path)
    parser.add_argument("detector", type=Path)
    parser.add_argument("--paired", nargs=2, required=True, metavar=("LIBRARY", "SHA256"))
    parser.add_argument("--zstd", nargs=2, required=True, metavar=("LIBRARY", "SHA256"))
    parser.add_argument("--first", choices=("arena", "stream"), default="stream")
    parser.add_argument("--repeats", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 8:
        parser.error("Expected between one and eight in-process repeats")
    reader = ShortWindowReader(args.recording)
    if reader.manifest_sha256 != "sha256:" + args.manifest_sha256:
        raise ValueError("Recording manifest differs from its reviewed digest")
    chunks = reader.manifest.chunks[:2]
    if [chunk.window_count for chunk in chunks] != [64, 64]:
        raise ValueError("Expected two complete 64-window chunks")
    inventory = dict(
        segments=[dict(path=str(args.recording), manifest_digest=reader.manifest_sha256)],
        window_count=128,
    )

    measurements = []
    with TemporaryDirectory(prefix="algo08-arena-acquisition-") as scratch, ExitStack() as stack:
        work = Path(scratch)
        assets = work / "assets"
        assets.mkdir()
        _pin(assets, "cancellation-factors.so", args.detector, DETECTOR_SHA256)
        for name in ("upper.f32", "lower.f32"):
            _pin(assets, name, args.assets / name, algo08_scan.PINS[name])
        paired = _pin(work, "paired-sha256.so", *args.paired)
        if not PairedSha256(paired).hardware:
            raise ValueError("The matched verifier requires the paired SHA-256 path")
        zstd = runtime(_pin(work, "libzstd.so.1", *args.zstd))
        reusable = stack.enter_context(rotating_arenas(zstd))
        # Preload the same release receiver and prime the file cache from these
        # two chunks. First-use arena allocation is still timed in each cold arm.
        control = _acquire(inventory, assets, paired, None)
        expected = {
            name: control[name] for name in ("raw_sha256", "factors_sha256", "detections_sha256")
        }
        order = (args.first, "stream" if args.first == "arena" else "arena")
        for condition in ("fresh", "reused"):
            if condition == "reused":
                _acquire(inventory, assets, paired, reusable)
            for repeat in range(args.repeats):
                for mode in order if repeat % 2 == 0 else reversed(order):
                    if mode == "stream":
                        row = _acquire(inventory, assets, paired, None)
                    elif condition == "fresh":
                        with rotating_arenas(zstd) as fresh:
                            row = _acquire(inventory, assets, paired, fresh)
                    else:
                        row = _acquire(inventory, assets, paired, reusable)
                    if any(row[key] != digest for key, digest in expected.items()):
                        raise ValueError("Verified raw authority or exact detector factors changed")
                    measurements.append(dict(condition=condition, repeat=repeat, mode=mode, **row))

    print(
        json.dumps(
            dict(
                recording=str(args.recording),
                manifest_sha256=reader.manifest_sha256,
                chunks=[chunk.model_dump() for chunk in chunks],
                detector_sha256=DETECTOR_SHA256,
                paired_sha256=args.paired[1],
                libzstd_sha256=args.zstd[1],
                measurements=measurements,
            ),
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
