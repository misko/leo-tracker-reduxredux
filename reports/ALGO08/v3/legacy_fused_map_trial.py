"""Match first acquisition plus map creation on one original DS30-0016 member."""

import argparse
from collections import Counter
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import patch

import numpy as np

from leo.contracts.digests import canonical_digest, sha256_digest
from leo.storage import short_window
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader
from tools.pipeline_eval.qualification.blind_compact_run import _probe, factor_candidate
from tools.pipeline_eval.qualification.cache_residency import load_query
from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

from . import legacy_block_multi as multi, legacy_block_seek as core, legacy_fused_map as fused
from . import sparse_cold_input as release
from .full_short_run import EIGHT_MS_SHA
from .future_capture_storage import ORIGINAL, qualified
from .legacy_block_multi_trial import CENSUS, CENSUS_PIN, NAMES, ORDINAL, verified_reader
from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, NativePath, StereoSchedule, strongest
from .seekable_eight_raw import SHORT
from .seekable_member_trial import clock, elapsed, window_from
from .zstd_physical_structure import view_for

MAP_PIN = "sha256:9c998a1c40c848ab8c28a82f497190e6ce105eb1ae366e64cce5deed59c88d9d"
ORDERS = (("stock", "fused"), ("fused", "stock"))


def analyze(reader, chunk, visits, natives, *, load=None):
    schedule = StereoSchedule(full_coverage=True)
    targets = {row["target_id"]: row for row in reader.manifest.configuration["targets"]}
    counts, time, raw, probes, support = Counter(), Counter(), [], [], []
    issued = 0
    for issued, (row, samples) in enumerate(visits, 1):
        if row.sequence != chunk.first_sequence + issued - 1:
            raise BundleCorruptionError("Original visit order changed at the receiver")
        if not qualified(row.acquisition):
            counts["invalid"] += 1
            continue
        target = targets[row.target_id]
        _, mode = schedule.visit("lower", target, row.acquisition)
        counts[mode] += 1
        full = mode == "full"
        if load is not None:
            samples = load(row, full=full)
        window = window_from(row, target, samples)
        span = memoryview(samples.reshape(-1)).cast("B")
        support.append((row.sequence, sha256_digest(span if full else span[:multi.PREFIX])))
        center = target["rf_center_hz"] - target["lnb_lo_hz"] - row.acquisition["actual_if_center_hz"]
        for lane in window.receiver_ids:
            measurements, (cpu, wall) = natives[mode].run(samples, lane, center)
            time.update(cpu_ns=cpu, wall_ns=wall)
            raw.append((row.sequence, mode, lane, measurements))
            best = strongest([
                factor_candidate(rank, epoch, status="complete", offset=offset, cfo=hz,
                                 exact=exact, control=roll, margin=exact-roll)
                for rank, epoch, offset, hz, exact, roll in measurements
            ])
            probes.append(_probe(window, lane, [best] if best is not None else []))
    if issued != chunk.window_count:
        raise ValueError("Receiver failed to consume all original visits")
    evidence = dict(window_spans=canonical_digest(support), raw_native=canonical_digest(raw),
                    selected=canonical_digest(probes), visits=dict(counts), lanes=len(raw),
                    positive=sum(bool(item["candidates"]) for item in probes),
                    residual=sum(item[0] != 0 for _, _, _, values in raw for item in values))
    return evidence, dict(time)


def run_attempt(mode, census, natives, fused_library, hasher, path):
    start = clock()
    reader, chunk = verified_reader(census)
    if mode == "fused":
        (result, native), map_metrics = fused.analyze_and_seal(
            reader, chunk, fused_library, hasher,
            lambda visits: analyze(reader, chunk, ((v.index, v.samples) for v in visits), natives), path)
    else:
        visits = reader.windows(start_sequence=chunk.first_sequence, stop_sequence=chunk.first_sequence + chunk.window_count)
        result, native = analyze(reader, chunk, ((v.index, v.samples) for v in visits), natives)
        map_metrics = None
    return result, dict(timing=elapsed(start), native_receiver=native, map=map_metrics)


def guard_corruption(reader, chunk, native, hasher, path):
    normal = short_window.ScannerIqStore._read_regular

    def changed(name, size):
        data = normal(name, size)
        if name == reader.path / chunk.payload_relative_path:
            if not isinstance(data, memoryview) or not isinstance(data.obj, np.ndarray):
                raise ValueError("Expected private original ingress storage")
            data.obj[-3] ^= 1
        return data

    called = False

    def observer(_):
        nonlocal called
        called = True
        raise ValueError("Corrupt acquisition reached the detector callback")

    with patch.object(short_window.ScannerIqStore, "_read_regular", staticmethod(changed)):
        try:
            fused.analyze_and_seal(reader, chunk, native, hasher, observer, path)
        except BundleCorruptionError as error:
            if f"short-window member changed: {chunk.payload_relative_path}" != str(error):
                raise
            message = str(error)
        else:
            raise ValueError("Corrupt original escaped compressed authentication")
    if path.exists() or called:
        raise ValueError("Rejected original acquired a map or detector view")
    return dict(rejected=message, map_exists=path.exists(), detector_callback=called)


def run(root):
    setting = subprocess.check_output(("ionice", "-p", str(os.getpid())), text=True).strip()
    if (root.parent.resolve() != Path("/dev/shm") or os.sched_getaffinity(0) != {2}
            or os.getpriority(os.PRIO_PROCESS, 0) != 15 or setting != "best-effort: prio 7"
            or not Path(ShortWindowReader.windows.__code__.co_filename).is_relative_to(release.RELEASE)):
        raise ValueError("Use the shared single-core Gauss slot and exact installed stock reader")
    census = json.loads(release.verified(CENSUS, CENSUS_PIN))[ORDINAL]
    release.verified(release.CACHE_LIBRARY, release.CACHE_SHA)
    cache, view = view_for(ORIGINAL.path, NAMES, load_query(release.CACHE_LIBRARY))
    if view is None or cache["filesystem"] != "tmpfs" or any(
            (ORIGINAL.path / name).resolve(strict=True) != ORIGINAL.path / name for name in NAMES):
        raise ValueError("Only the currently resident original member may be opened")
    spec = json.loads(release.verified(release.PAYLOAD / "spec.json", release.SPEC_SHA))
    ingress = release.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    full = release.PAYLOAD / "receiver.so"
    hasher = release.PAYLOAD / "paired-sha256.so"
    release.verified(hasher, spec["paired_sha256"]["sha256"])
    release.verified(full, INSTALLED_SHA)
    release.verified(SHORT, EIGHT_MS_SHA)
    pilot = np.frombuffer(release.verified(release.RELEASE / "assets/lower.f32", PILOT_SHA["lower"]), dtype="<f4")
    reader, chunk = verified_reader(census)
    root.mkdir(mode=0o700)
    fused_path, ready_path = root / "first-pass.so", root / "ready.so"
    build = dict(fused=fused.build(fused_path), selective=core.build(ready_path))
    fused_library, selected_library = fused.load(fused_path), core.load(ready_path)
    reference, runs = None, []
    with ExitStack() as stack:
        natives = {label: NativePath(location, pilot, label) for label, location in (
            ("full", full), ("short_primary", SHORT))}
        for engine in natives.values():
            stack.callback(engine.close)
        for index, order in enumerate(ORDERS, 1):
            run_ = {}
            result_path = root / f"paired{index}.map"
            for mode in order:
                with core.one_member(ORIGINAL.path, chunk), ingress(), paired_decoded_hashes(hasher):
                    evidence, timing = run_attempt(mode, census, natives, fused_library, hasher, result_path)
                if reference is None:
                    reference = evidence
                if (evidence != reference or mode == "fused" and
                        (timing["map"]["map_sha256"] != MAP_PIN or timing["map"]["exceptional_ordinals"] != (120, 135, 676))):
                    raise ValueError("Fused original detector or certified established map changed")
                run_[mode] = timing
            runs.append(run_)
        with core.one_member(ORIGINAL.path, chunk), ingress():
            select = multi.Selective(reader, chunk, result_path.read_bytes(), MAP_PIN, selected_library)
            stack.callback(select.close)
            ready_evidence, _ = analyze(reader, chunk, ((row, None) for row in select.rows), natives, load=select.read)
            if ready_evidence != reference:
                raise ValueError("Fused map failed its matching selective reader's signed sample or detector gate")
            refusal = guard_corruption(reader, chunk, fused_library, hasher, root / "corrupt.map")
    receipt = dict(case="DS30-0016", global_member=ORDINAL, source=str(ORIGINAL.path),
                   original=core.identity(reader, chunk), residency=cache, native_build=build,
                   policy=dict(cpu_affinity=[2], nice=15, ionice=setting, schedule="isolated member 20/8"),
                   orders=ORDERS, runs=runs, evidence=reference, ready_evidence=ready_evidence,
                   ready_map_sha256=MAP_PIN, ready_requests=dict(select.requests), corruption=refusal,
                   receiver_sha256=INSTALLED_SHA, short_sha256=EIGHT_MS_SHA)
    with (root / "result.json").open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    run(parser.parse_args().out)
