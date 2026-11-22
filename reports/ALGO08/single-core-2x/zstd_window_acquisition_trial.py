"""Compare low-memory streams through the frozen all-scan acquisition entry point."""

import argparse
import json
from hashlib import sha256
from importlib.util import find_spec
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from unittest.mock import patch

import zstandard as zstd

from leo.contracts.digests import canonical_digest
from leo.storage.fast_scan import FastSegmentSource
from leo.storage.short_window import ShortWindowReader
from tools import algo08_scan
from tools.pipeline_eval.variants.experimental.paired_sha256 import (
    PairedSha256,
    paired_decoded_hashes,
)
from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer
from tools.pipeline_eval.variants.experimental.receiver_window_ingress import WindowStreams


def _load(path, expected):
    content = Path(path).read_bytes()
    if sha256(content).hexdigest() != expected:
        raise ValueError(f"Input differs from its frozen digest: {path}")
    return content


def _acquire(inventory, assets, paired, native_digest, mode):
    reader_cpu = 0.0

    class Prefix(FastSegmentSource):
        def __init__(self, entry):
            super().__init__(entry, stop_sequence=inventory["window_count"])

        def windows(self):
            nonlocal reader_cpu
            iterator = super().windows()
            while True:
                start = process_time()
                window = next(iterator, None)
                reader_cpu += process_time() - start
                if window is None:
                    return
                yield window

    decoder = None if mode == "release" else WindowStreams(loan_buffers=mode == "readinto")
    verifier = paired_decoded_hashes(paired) if decoder is None else decoder.install(paired)
    faults_before = getrusage(RUSAGE_SELF).ru_minflt
    start_cpu, start_wall = process_time(), perf_counter()
    with (
        patch.object(algo08_scan, "FastSegmentSource", Prefix),
        patch.dict(algo08_scan.PINS, {"cancellation-factors.so": native_digest}),
        compressed_input_buffer(),
        verifier,
    ):
        session = Path(inventory["segments"][0]["path"]).name
        data = algo08_scan.acquire(session, canonical_digest(inventory), inventory, assets)
    cpu, wall = process_time() - start_cpu, perf_counter() - start_wall
    if decoder is not None and decoder.counts["streams"] != 2:
        raise ValueError("The decoder comparison must cover both chunks")
    if mode == "readinto" and decoder.counts["loaned_windows"] != 128:
        raise ValueError("Expected 128 decoded-window loans")
    return dict(
        mode=mode,
        acquisition_cpu_s=cpu,
        acquisition_wall_s=wall,
        reader_cpu_s=reader_cpu,
        minor_faults=getrusage(RUSAGE_SELF).ru_minflt - faults_before,
        peak_process_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
        processed=data["provenance"]["processed_windows"],
        reader_counts=decoder.counts if decoder is not None else None,
        raw_sha256=data["source"]["raw_recording_authority_digest"],
        factors_sha256=canonical_digest(data["source"]["probes"]),
        detections_sha256=canonical_digest(data),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("manifest_sha256")
    parser.add_argument("assets", type=Path)
    parser.add_argument("spec", type=Path)
    parser.add_argument("spec_sha256")
    parser.add_argument("--repeats", type=int, default=6)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 8:
        parser.error("Expected between one and eight repeats")
    spec = json.loads(_load(args.spec, args.spec_sha256))
    if spec["schedule"] != "all" or spec["ingress"] != "paired-sha256":
        raise ValueError("Expected the full-scan candidate's paired-SHA ingress")
    reader = ShortWindowReader(args.recording)
    if reader.manifest_sha256 != "sha256:" + args.manifest_sha256:
        raise ValueError("Changed manifest")
    chunks = reader.manifest.chunks[:2]
    if [chunk.window_count for chunk in chunks] != [64, 64]:
        raise ValueError("Expected two complete chunks")
    inventory = dict(
        segments=[dict(path=str(args.recording), manifest_digest=reader.manifest_sha256)],
        window_count=128,
    )
    rows = []
    with TemporaryDirectory(prefix="algo08-window-acq-") as temp:
        assets = Path(temp)
        detector = spec["detector_sha256"]
        (assets / "cancellation-factors.so").write_bytes(_load(spec["detector"], detector))
        for name in ("upper.f32", "lower.f32"):
            (assets / name).write_bytes(_load(args.assets / name, algo08_scan.PINS[name]))
        paired = assets / "paired-sha256.so"
        pin = spec["paired_sha256"]
        paired.write_bytes(_load(pin["library"], pin["sha256"]))
        if not PairedSha256(paired).hardware:
            raise ValueError("Expected paired SHA support in every arm")
        expected = _acquire(inventory, assets, paired, detector, "release")
        modes = ("release", "persistent", "readinto")
        for repeat in range(args.repeats):
            start = repeat % len(modes)
            order = modes[start:] + modes[:start]
            for mode in order if repeat % 2 == 0 else reversed(order):
                result = _acquire(inventory, assets, paired, detector, mode)
                if any(
                    result[key] != expected[key]
                    for key in ("raw_sha256", "factors_sha256", "detections_sha256")
                ):
                    raise ValueError("Acquisition differs from verified ingress control")
                rows.append(dict(repeat=repeat, **result))
    backend = Path(find_spec("zstandard.backend_c").origin)
    print(
        json.dumps(
            dict(
                recording=str(args.recording),
                manifest_sha256=reader.manifest_sha256,
                chunks=[chunk.model_dump() for chunk in chunks],
                spec_sha256=args.spec_sha256,
                detector_sha256=detector,
                paired_sha256=pin["sha256"],
                zstandard=zstd.__version__,
                zstd=zstd.ZSTD_VERSION,
                zstandard_backend_sha256=sha256(backend.read_bytes()).hexdigest(),
                rows=rows,
            ),
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
