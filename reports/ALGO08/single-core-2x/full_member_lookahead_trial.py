"""Time two 16 MiB lookahead transitions on a private full-size XFS fixture."""

import argparse
import json
import os
import resource
import subprocess
from contextlib import nullcontext
from dataclasses import asdict
from functools import partial
from hashlib import sha256
from pathlib import Path
from statistics import mean, median
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import zstandard as zstd

from leo.contracts.digests import canonical_digest
from leo.contracts.multirate_window_recording import ShortWindowManifestV2
from leo.storage.fast_scan import FastScanStore
from leo.storage.short_window import ShortWindowWriter
from tools import algo08_scan
from tools.pipeline_eval.qualification import waveform_site_model as waveform
from tools.pipeline_eval.qualification.cache_residency import load_query, pages
from tools.pipeline_eval.variants.experimental.paired_sha256 import (
    PairedSha256,
    paired_decoded_hashes,
)
from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer
from tools.pipeline_eval.variants.experimental.receiver_member_lookahead import (
    PREFIX_BYTES,
    compressed_member_lookahead,
)
from tools.pipeline_eval.variants.experimental.receiver_member_prefetch import compressed_member_prefetch

from .receiver_member_lookahead_trial import cache_pages, synthetic_members

CHUNKS = 3
WINDOWS_PER_CHUNK = 64
WINDOWS = CHUNKS * WINDOWS_PER_CHUNK
WINDOW_BYTES = 1_600_000
MIN_COMPRESSED = 77_000_000
MAX_COMPRESSED = 80_000_000
COLD_PAIRS = 3
WARM_PAIRS = 2
ALGO08V3 = "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f"


def geometry(content, expected):
    if sha256(content).hexdigest() != expected:
        raise ValueError("Certified reference manifest changed")
    manifest = ShortWindowManifestV2.model_validate_json(content)
    chunks = manifest.chunks[:CHUNKS]
    if len(chunks) != CHUNKS or any(
        chunk.window_count != WINDOWS_PER_CHUNK
        or chunk.uncompressed_bytes != WINDOWS_PER_CHUNK * WINDOW_BYTES
        or not MIN_COMPRESSED <= chunk.compressed_bytes <= MAX_COMPRESSED
        for chunk in chunks
    ):
        raise ValueError("Reference does not have the required full-sized geometry")
    return tuple(chunk.compressed_bytes for chunk in chunks)


def samples(visit, pilot):
    planted = dict(
        epoch=499 + 7 * visit,
        period=40_000 / 3,
        actual_cfo_hz=230_000 - 37 * visit,
        slope_hz_s=600.0,
        amplitude=1800.0,
    )
    secondary = (
        dict(planted, epoch=2477 + 6 * visit, actual_cfo_hz=-410_000 - 29 * visit)
        if visit % 2
        else None
    )
    record = dict(
        sample_seed=761 + visit, tone_hz=181_000, tone_amplitude=160.0, planted=[planted, secondary]
    )
    return waveform.iq(record, {"sample_rate_truth_hz": 10_000_000}, pilot)


def rescale(values, divisor):
    return ((values.astype("i4") * 100) // divisor).astype("<i2")


def fit_scale(pilot, reference):
    """Choose an amplitude scaling on four separate generated training windows."""
    training = [samples(WINDOWS + i, pilot) for i in range(4)]
    sizes = {}
    target = mean(reference) / WINDOWS_PER_CHUNK * len(training)
    for divisor in range(125, 401, 5):
        compressor = zstd.ZstdCompressor(level=1, write_checksum=True, write_content_size=False)
        stream = compressor.compressobj()
        sizes[divisor] = sum(len(stream.compress(rescale(values, divisor))) for values in training)
        sizes[divisor] += len(stream.flush())
    return min(sizes, key=lambda divisor: abs(sizes[divisor] - target)), sizes


def generated_recording(private, reference):
    target = dict(target_id="t", edge="lower", channel=1, rf_center_hz=2_000_000, lnb_lo_hz=0)
    writer = ShortWindowWriter(
        private,
        "private-iq",
        configuration=dict(sample_rate_hz=10_000_000, window_ms=20, targets=[target]),
        radio={"serial": "private-full-member-synthetic"},
        receiver_ids=(0, 1),
        chunk_windows=WINDOWS_PER_CHUNK,
        schema_version=2,
    )
    pilot = waveform.pulse_bank()["lower"]
    divisor, fit = fit_scale(pilot, reference)
    for visit in range(WINDOWS):
        start = 4_000_000 * visit
        clocks = dict(
            host_delivery_clock={"synthetic_visit": visit},
            utc_clock_bracket={"sample_counter": start} if visit == 0 else None,
        )
        acquisition = dict(
            global_visit=visit,
            generation=1,
            sample_start=start,
            sample_end=start + 200_000,
            retune_receipt=json.dumps(clocks),
            complete=True,
            validity_authority="provider_attested",
            validity_includes_guard=True,
            quality_flags=[],
            actual_if_center_hz=target["rf_center_hz"],
        )
        writer.append(
            sequence=visit,
            target_id="t",
            samples=rescale(samples(visit, pilot), divisor),
            acquisition=acquisition,
            powers=({}, {}),
        )
    return writer.finish(stop_reason="synthetic-full-member-benchmark"), divisor, fit


def measure(assets, hasher, intake, *, arm, buffer=compressed_input_buffer,
            hint=compressed_member_lookahead, hashes=paired_decoded_hashes):
    forecast = {
        "control": nullcontext,
        "hint": hint,
        "prefetch": compressed_member_prefetch,
    }[arm]
    usage = resource.getrusage(resource.RUSAGE_SELF)
    cpu, wall = process_time_ns(), perf_counter_ns()
    with (
        buffer(),
        hashes(hasher),
        forecast() as overlap,
    ):
        doc = algo08_scan.acquire(*intake, assets)
    wall, cpu = perf_counter_ns() - wall, process_time_ns() - cpu
    after = resource.getrusage(resource.RUSAGE_SELF)
    if doc["provenance"]["processed_windows"] != WINDOWS:
        raise ValueError("Expected full acquisition of all generated windows")
    if arm == "hint" and (overlap.attempts, overlap.submitted, overlap.submitted_bytes) != (
        CHUNKS - 1,
        CHUNKS - 1,
        (CHUNKS - 1) * PREFIX_BYTES,
    ):
        raise ValueError("Expected two capped advisory requests")
    row = dict(
        cpu_ns=cpu,
        wall_ns=wall,
        input_blocks=after.ru_inblock - usage.ru_inblock,
        voluntary_switches=after.ru_nvcsw - usage.ru_nvcsw,
        involuntary_switches=after.ru_nivcsw - usage.ru_nivcsw,
        hints=asdict(overlap) if arm == "hint" else None,
        acquisition_sha256=canonical_digest(doc),
        raw_authority=doc["source"]["raw_recording_authority_digest"],
        selected=sum(len(row["candidates"]) for row in doc["source"]["probes"]),
        probes_sha256=canonical_digest(doc["source"]["probes"]),
    )
    if arm == "prefetch":
        row["prefetch"] = asdict(overlap)
    return row


def verified_start(members, query, expected_pages, *, cold):
    start = cache_pages(members, query, cold=cold)
    if start != ([0] * len(members) if cold else expected_pages):
        raise ValueError(f"Unmatched private compressed-file page cache: {start}")
    return start


def prefetch_comparison(spec):
    if canonical_digest(spec) != ALGO08V3 or spec.get("member_lookahead") is not True:
        raise ValueError("Prefetch requires the frozen ALGO08v3 hint control")
    if len(os.sched_getaffinity(0)) != 1:
        raise ValueError("Prefetch comparison requires the process and its read thread pinned to one CPU")


def frozen_context(build, spec, filename, constructor):
    name = f"tools/pipeline_eval/variants/experimental/{filename}"
    path = build / name
    contents = path.read_bytes()
    if sha256(contents).hexdigest() != spec["sources"][name]:
        raise ValueError(f"Frozen acquisition adapter changed: {filename}")
    bindings = {"__name__": __name__, "__file__": str(path)}
    exec(compile(contents, str(path), "exec"), bindings)
    return bindings[constructor]


def run(parent, reference, reference_sha256, build, build_sha256, cache_library, *, prefetch=False):
    parent = parent.resolve(strict=True)
    qnap = Path("/mnt/qnap01")
    if parent == qnap or qnap in parent.parents:
        raise ValueError("Generated fixtures belong on private local storage")
    fs = subprocess.run(
        ["findmnt", "-no", "FSTYPE", "-T", str(parent)], check=True, text=True, capture_output=True
    ).stdout.strip()
    if fs != "xfs":
        raise ValueError("Expected the local XFS filesystem")
    target = geometry(reference.read_bytes(), reference_sha256)
    config = (build / "spec.json").read_bytes()
    if sha256(config).hexdigest() != build_sha256:
        raise ValueError("Reviewed build specification changed")
    spec = json.loads(config)
    if spec["schedule"] != "all" or spec["ingress"] != "paired-sha256":
        raise ValueError("Expected the reviewed full-scan acquisition build")
    timed = measure
    if prefetch:
        prefetch_comparison(spec)
        timed = partial(
            measure,
            buffer=frozen_context(build, spec, "receiver_ingress.py", "compressed_input_buffer"),
            hint=frozen_context(build, spec, "receiver_member_lookahead.py", "compressed_member_lookahead"),
            hashes=frozen_context(build, spec, "paired_sha256.py", "paired_decoded_hashes"),
        )
    control, candidate = ("hint", "prefetch") if prefetch else ("control", "hint")
    receiver, hasher = Path(spec["detector"]), Path(spec["paired_sha256"]["library"])
    if (
        sha256(receiver.read_bytes()).hexdigest() != spec["detector_sha256"]
        or (sha256(hasher.read_bytes()).hexdigest() != spec["paired_sha256"]["sha256"])
        or not PairedSha256(hasher).hardware
    ):
        raise ValueError("Expected the reviewed receiver and paired SHA-256 verifier")

    query, page_size = load_query(cache_library), os.sysconf("SC_PAGE_SIZE")
    pilot = algo08_assets() / "lower.f32"
    with TemporaryDirectory(dir=parent, prefix="leo-private-full-member-") as directory:
        private = Path(directory)
        recording, divisor, fit = generated_recording(private, target)
        members = synthetic_members(recording)
        sizes = [size for _, (_, _, size) in members]
        if len(sizes) != CHUNKS or any(
            not MIN_COMPRESSED <= size <= MAX_COMPRESSED for size in sizes
        ):
            raise ValueError(f"Generated member sizes differ from certified geometry: {sizes}")
        expected_pages = [pages(size, page_size) for size in sizes]
        expected_blocks = sum(expected_pages) * page_size // 512
        intake = FastScanStore(private).inventory(recording, verify_windows=False)
        assets = private / "assets"
        assets.mkdir()
        (assets / "cancellation-factors.so").symlink_to(receiver.resolve())
        (assets / "lower.f32").symlink_to(pilot.resolve())
        results = {}
        with patch.dict(algo08_scan.PINS, {"cancellation-factors.so": spec["detector_sha256"]}):
            # Prime detector code and the privately allocated filesystem extents.
            # Compressed page state is separately verified before every timed arm.
            expected = timed(assets, hasher, intake, arm=control)
            if not expected["selected"]:
                raise ValueError("Generated fixture did not exercise selected receiver factors")
            for condition, pair_count in (("cold", COLD_PAIRS), ("warm", WARM_PAIRS)):
                pairs = []
                for repeat in range(pair_count):
                    pair = {}
                    order = (candidate, control) if repeat % 2 else (control, candidate)
                    for arm in order:
                        start = verified_start(
                            members, query, expected_pages, cold=condition == "cold"
                        )
                        row = timed(assets, hasher, intake, arm=arm)
                        row["starting_cache_pages"] = start
                        if row["acquisition_sha256"] != expected["acquisition_sha256"]:
                            raise ValueError("I/O overlap changed verified acquisition output")
                        if arm == "prefetch":
                            read = row["prefetch"]
                            if (read["submitted"], read["hits"], read["hit_bytes"], read["fallback"]) != (
                                CHUNKS - 1, CHUNKS - 1, sum(sizes[1:]), 0,
                            ):
                                raise ValueError("Expected two fully consumed speculative member reads")
                        pair[arm] = row
                    pairs.append(dict(order=order, **pair))
                results[condition] = dict(
                    pairs=pairs,
                    median_wall_saved_ms=median(
                        (pair[control]["wall_ns"] - pair[candidate]["wall_ns"]) / 1e6
                        for pair in pairs
                    ),
                    median_cpu_saved_ms=median(
                        (pair[control]["cpu_ns"] - pair[candidate]["cpu_ns"]) / 1e6 for pair in pairs
                    ),
                )
        return dict(
            private_parent=str(parent),
            filesystem=fs,
            reference_sha256=reference_sha256,
            reference_compressed_bytes=target,
            generated_compressed_bytes=sizes,
            scale_divisor=divisor,
            scale_fit_compressed_bytes=fit,
            window_count=WINDOWS,
            detector_sha256=spec["detector_sha256"],
            specification_sha256=build_sha256,
            hasher_sha256=spec["paired_sha256"]["sha256"],
            cachestat_helper_sha256=sha256(cache_library.read_bytes()).hexdigest(),
            page_size=page_size,
            expected_compressed_file_pages=expected_pages,
            expected_cold_blocks=expected_blocks,
            hint_prefix_bytes=PREFIX_BYTES,
            logical_compressed_bytes_all_acquisitions=sum(sizes)
            * (1 + 2 * (COLD_PAIRS + WARM_PAIRS)),
            linux_kernel=os.uname().release,
            code_and_extent_warmup=expected,
            results=results,
        )


def algo08_assets():
    release = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/assets")
    if sha256((release / "lower.f32").read_bytes()).hexdigest() != algo08_scan.PINS["lower.f32"]:
        raise ValueError("Expected the reviewed lower pilot")
    return release


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parent", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("reference_sha256")
    parser.add_argument("build", type=Path)
    parser.add_argument("build_sha256")
    parser.add_argument("cache_library", type=Path)
    parser.add_argument("--prefetch", action="store_true", help="compare the frozen v3 hint with one full read")
    print(json.dumps(run(**vars(parser.parse_args())), indent=2, allow_nan=False))
