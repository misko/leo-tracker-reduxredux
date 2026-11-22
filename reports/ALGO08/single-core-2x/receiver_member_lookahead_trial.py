"""Time bounded advice on a private sealed synthetic acquisition."""

import argparse
from contextlib import nullcontext
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import stat
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from leo.contracts.digests import canonical_digest
from leo.storage.fast_scan import FastScanStore
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from tools import algo08_scan
from tools.pipeline_eval.qualification import waveform_site_model as waveform
from tools.pipeline_eval.qualification.cache_residency import load_query
from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256, paired_decoded_hashes
from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer
from tools.pipeline_eval.variants.experimental.receiver_member_lookahead import (
    PREFIX_BYTES, compressed_member_lookahead,
)


WINDOWS = 12
CHUNK_WINDOWS = 4
REPEATS = 4


def generated_recording(private):
    target = dict(target_id="t", edge="lower", channel=1, rf_center_hz=2_000_000, lnb_lo_hz=0)
    writer = ShortWindowWriter(
        private, "private-iq", configuration=dict(sample_rate_hz=10_000_000, window_ms=20, targets=[target]),
        radio={"serial": "private-synthetic"}, receiver_ids=(0, 1), chunk_windows=CHUNK_WINDOWS,
        schema_version=2,
    )
    lower = waveform.pulse_bank()["lower"]
    for visit in range(WINDOWS):
        start = 4_000_000 * visit
        plant = dict(epoch=499 + 7 * visit, period=40_000 / 3, actual_cfo_hz=230_000 - 37 * visit,
                     slope_hz_s=600., amplitude=1800.)
        secondary = dict(plant, epoch=2477 + 6 * visit, actual_cfo_hz=-410_000 - 29 * visit) if visit % 2 else None
        record = dict(sample_seed=761 + visit, tone_hz=181_000, tone_amplitude=160., planted=[plant, secondary])
        iq = waveform.iq(record, {"sample_rate_truth_hz": 10_000_000}, lower)
        clocks = dict(host_delivery_clock={"synthetic_visit": visit},
                      utc_clock_bracket={"sample_counter": start} if visit == 0 else None)
        acquisition = dict(
            global_visit=visit, generation=1, sample_start=start, sample_end=start + 200_000,
            retune_receipt=json.dumps(clocks), complete=True, validity_authority="provider_attested",
            validity_includes_guard=True, quality_flags=[], actual_if_center_hz=target["rf_center_hz"],
        )
        writer.append(sequence=visit, target_id="t", samples=iq, acquisition=acquisition, powers=({}, {}))
    return writer.finish(stop_reason="synthetic-benchmark")


def synthetic_members(recording):
    manifest = ShortWindowReader(recording).manifest
    members = []
    for chunk in manifest.chunks:
        path = recording / chunk.payload_relative_path
        info = path.stat()
        if info.st_size != chunk.compressed_bytes or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Unexpected private fixture file")
        members.append((path, (info.st_dev, info.st_ino, info.st_size)))
    return members


def cache_pages(members, query, *, cold):
    """Drop pages only for freshly generated, inode-matched private fixtures."""
    pages = []
    for path, expected in members:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino, info.st_size) != expected or info.st_nlink != 1:
                raise ValueError("Private synthetic fixture changed")
            if cold:
                os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
            pages.append(query(fd, info.st_size))
        finally:
            os.close(fd)
    return pages


def measure(assets, hasher, intake, *, hinted):
    usage = resource.getrusage(resource.RUSAGE_SELF)
    cpu, wall = process_time_ns(), perf_counter_ns()
    with compressed_input_buffer(), paired_decoded_hashes(hasher):
        with compressed_member_lookahead() if hinted else nullcontext() as advice:
            doc = algo08_scan.acquire(*intake, assets)
    wall, cpu = perf_counter_ns() - wall, process_time_ns() - cpu
    after = resource.getrusage(resource.RUSAGE_SELF)
    if doc["provenance"]["processed_windows"] != WINDOWS:
        raise ValueError("Generated acquisition did not exercise all native windows")
    return dict(
        cpu_ns=cpu, wall_ns=wall, input_blocks=after.ru_inblock - usage.ru_inblock,
        involuntary_switches=after.ru_nivcsw - usage.ru_nivcsw,
        hints=asdict(advice) if advice is not None else None,
        acquisition_sha256=canonical_digest(doc),
        raw_authority=doc["source"]["raw_recording_authority_digest"],
        selected=sum(len(row["candidates"]) for row in doc["source"]["probes"]),
        probes_sha256=canonical_digest(doc["source"]["probes"]),
    )


def run(parent, receiver, assets, hasher, cache_library):
    parent = parent.resolve(strict=True)
    qnap = Path("/mnt/qnap01")
    if parent == qnap or qnap in parent.parents:
        raise ValueError("Synthetic fixtures require local writable storage")
    query = load_query(cache_library)
    page_size = os.sysconf("SC_PAGE_SIZE")
    receiver_digest = sha256(receiver.read_bytes()).hexdigest()
    hasher_digest = sha256(hasher.read_bytes()).hexdigest()
    if not PairedSha256(hasher).hardware:
        raise ValueError("Expected the paired SHA-256 ingress used by the reviewed receiver")
    with TemporaryDirectory(dir=parent, prefix="leo-private-lookahead-") as directory:
        private = Path(directory)
        recording = generated_recording(private)
        members = synthetic_members(recording)
        intake = FastScanStore(private).inventory(recording, verify_windows=False)
        local_assets = private / "assets"
        local_assets.mkdir()
        (local_assets / "cancellation-factors.so").symlink_to(receiver.resolve())
        (local_assets / "lower.f32").symlink_to((assets / "lower.f32").resolve())
        results = {}
        initial_digest = None
        with patch.dict(algo08_scan.PINS, {"cancellation-factors.so": receiver_digest}):
            for cold in (True, False):
                pairs = []
                for repeat in range(REPEATS):
                    pair = {}
                    order = ("hint", "control") if repeat % 2 else ("control", "hint")
                    for name in order:
                        pages = cache_pages(members, query, cold=cold)
                        row = measure(local_assets, hasher, intake, hinted=name == "hint")
                        row["starting_cache_pages"] = pages
                        if initial_digest is None:
                            initial_digest = row["acquisition_sha256"]
                        elif row["acquisition_sha256"] != initial_digest:
                            raise ValueError("Look-ahead changed verified acquisition")
                        if row["hints"] is not None:
                            if row["hints"]["submitted"] != len(members) - 1:
                                raise ValueError("Expected one successful advisory request per private transition")
                        pair[name] = row
                    pairs.append(dict(order=order, **pair))
                results["page_cache_cold_request" if cold else "warm"] = dict(
                    pairs=pairs, median_wall_delta_ms=median(
                        (pair["hint"]["wall_ns"] - pair["control"]["wall_ns"]) / 1e6 for pair in pairs),
                    median_cpu_delta_ms=median(
                        (pair["hint"]["cpu_ns"] - pair["control"]["cpu_ns"]) / 1e6 for pair in pairs),
                )
        return dict(
            private_parent=str(parent), page_size=page_size, saved_recordings=0,
            chunks=[size for _, (_, _, size) in members], window_count=WINDOWS, hint_cap=PREFIX_BYTES,
            receiver_sha256=receiver_digest, hasher_sha256=hasher_digest,
            linux_kernel=os.uname().release, results=results,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "receiver", "assets", "hasher", "cache_library"):
        parser.add_argument(name, type=Path)
    print(json.dumps(run(**vars(parser.parse_args())), indent=2, allow_nan=False))
