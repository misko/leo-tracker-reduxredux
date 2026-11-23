"""Measure destination faults in the pinned descriptor on the prior tmpfs member."""

import argparse
from collections import Counter
from contextlib import contextmanager
import json
import os
from pathlib import Path
import resource
import stat
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from . import receiver_ceiling_0169 as ceiling, sparse_cold_input as release
from .direct_storage_0169 import prefix_bytes
from .full_short_cold import freeze
from .scout_readout_trial import check_machine, factor_bytes
from .signed_ingress_reuse import CompressedSlots, bind_allocator


STAGED = Path("/dev/shm/leo-receiver-ceiling-0169-results01")
SCOPE_PIN = "95a438f0904e4568b6f2a3618b7fbf691c29d0e2d352fd3727cc83d35b72aa9a"
ORDERS = (("stock", "pool", "prefault"), ("prefault", "pool", "stock")) * 3


def clocks():
    cpu, wall = process_time_ns(), perf_counter_ns()
    r = resource.getrusage(resource.RUSAGE_SELF)
    return Counter(cpu_ns=cpu, wall_ns=wall, user_cpu_s=r.ru_utime, system_cpu_s=r.ru_stime,
                   minor_faults=r.ru_minflt, major_faults=r.ru_majflt, input_blocks=r.ru_inblock)


class Monitor:
    def __init__(self):
        self.stats = {}
        self.allocations = []

    def time(self, stage, op, *args, **kwargs):
        begin = clocks()
        try:
            return op(*args, **kwargs)
        finally:
            end = clocks()
            end.subtract(begin)
            self.stats.setdefault(stage, Counter()).update(end)
            self.stats[stage]["calls"] += 1


def touch_pages(destination, page_size):
    destination[::page_size] = 0
    destination[-1] = 0


class Allocator:
    def __init__(self, monitor, mode, pool):
        self.monitor = monitor
        self.mode = mode
        self.pool = pool

    def empty(self, size, dtype):
        if size != ceiling.COMPRESSED or dtype != np.uint8:
            raise ValueError("Descriptor allocation exceeds or differs from the single signed member")
        allocate = self.pool.empty if self.mode == "pool" else np.empty
        destination = self.monitor.time("allocation", allocate, size, dtype)
        self.monitor.allocations.append(dict(bytes=destination.nbytes, pointer_page_offset=destination.ctypes.data % os.sysconf("SC_PAGE_SIZE")))
        if self.mode == "prefault":
            self.monitor.time("pre_touch", touch_pages, destination, os.sysconf("SC_PAGE_SIZE"))
        return destination


@contextmanager
def watch_buffer(buffer, monitor, allocator):
    scope = buffer.__wrapped__.__globals__
    original, os_module = scope["read_regular"], scope["os"]

    class ObservedOS:
        def __getattr__(self, name):
            return getattr(os_module, name)

        def readv(self, *args):
            return monitor.time("readv", os_module.readv, *args)

        def read(self, *args):
            return monitor.time("read_eof", os_module.read, *args)

    with patch.dict(scope, {"os": ObservedOS()}):
        descriptor = bind_allocator(original, allocator)

        def read(*args, **kwargs):
            return monitor.time("descriptor", descriptor, *args, **kwargs)

        with patch.dict(scope, {"read_regular": read}), buffer():
            yield


def tmpfs_member(scope):
    from leo.contracts.multirate_window_recording import ShortWindowManifestV2

    root = STAGED.resolve(strict=True)
    segment = Path(scope["entry"]["path"])
    if root.parent != Path("/dev/shm") or segment.parent != root or segment.resolve(strict=True) != segment:
        raise ValueError("The experiment may read only the previously staged tmpfs member")
    manifest = segment / "manifest.json"
    content = release.verified(manifest, scope["entry"]["manifest_digest"])
    chunk = ceiling.first_member(ShortWindowManifestV2.model_validate_json(content))
    if chunk.model_dump(mode="json") != scope["member"]:
        raise ValueError("Existing staged scope differs from the manifest")
    for filename, required_length in ((chunk.payload_relative_path, chunk.compressed_bytes),
                                     (chunk.index_relative_path, chunk.index_bytes), (manifest.name, len(content))):
        path = segment / filename
        info = path.lstat()
        if (path.resolve(strict=True) != path or info.st_dev != root.stat().st_dev or not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1 or info.st_size != required_length):
            raise ValueError("The prior tmpfs file changed or resolves outside its staging scope")
    return segment / chunk.payload_relative_path


def read_once(mode, pool, expected, query, path):
    from leo.contracts.digests import canonical_digest

    monitor = Monitor()
    allocator = Allocator(monitor, mode, pool)
    frozen_function = release.frozen_function

    def configured(spec, filename, symbol):
        original = frozen_function(spec, filename, symbol)
        if (filename, symbol) == ("receiver_ingress.py", "compressed_input_buffer"):
            return lambda: watch_buffer(original, monitor, allocator)
        return original

    before = ceiling.snapshot(path, ceiling.COMPRESSED, query)
    count = pool.counts.copy()
    beginning = clocks()
    with patch.object(release, "frozen_function", configured):
        result = ceiling.acquire(STAGED, "full-short")
    aggregate = clocks()
    aggregate.subtract(beginning)
    after = ceiling.snapshot(path, ceiling.COMPRESSED, query)
    pool_delta = pool.counts.copy()
    pool_delta.subtract(count)
    expected_stages = ("allocation", "readv", "read_eof", "descriptor")
    if (len(monitor.allocations) != 1 or any(monitor.stats[stage]["calls"] != 1 for stage in expected_stages)
            or before["cached_pages"] != before["observed_file_pages"] or before["cached_pages"] != after["cached_pages"]
            or monitor.stats["descriptor"]["input_blocks"] != 0):
        raise ValueError("Timed read differs from one wholly resident staged descriptor")
    if any(canonical_digest(result[k]) != canonical_digest(expected[k])
           for k in ("iq", "packet", "trace", "original_member_reads")) or any(
            factor_bytes(a["factors"]) != factor_bytes(b["factors"])
            for a, b in zip(result["trace"], expected["trace"], strict=True)):
        raise ValueError("Destination choice altered the ordered signed result")
    capacity = sum(buffer.nbytes for buffer, _ in pool.slots)
    live = sum(owner() is not None for _, owner in pool.slots)
    if live or capacity > 2*ceiling.COMPRESSED or pool_delta["fallback"]:
        raise ValueError("The previous decoder still owns a buffer or fell back unexpectedly")
    return dict(mode=mode, stages=monitor.stats, allocation=monitor.allocations[0], scope_clock=aggregate,
                source_start=before, source_end=after, acquired={k: result[k] for k in
                    ("acquire_cpu_ns", "acquire_wall_ns", "native_cpu_ns", "native_wall_ns")},
                pool_counts_delta=pool_delta, pool_retained_bytes=capacity, pool_live_loans_after=live,
                peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def run(output):
    from tools.pipeline_eval.qualification.cache_residency import load_query

    machine = check_machine()
    if output.resolve().parent != Path("/dev/shm"):
        raise ValueError("Use a fresh tmpfs output file")
    scope = json.loads(release.verified(STAGED / "scope.json", SCOPE_PIN))
    path = tmpfs_member(scope)
    expected = json.loads(prefix_bytes())
    release.verified(release.CACHE_LIBRARY, release.CACHE_SHA)
    query = load_query(release.CACHE_LIBRARY)
    start = clocks()
    pool = CompressedSlots(ceiling.COMPRESSED)
    setup = clocks()
    setup.subtract(start)
    seed = read_once("pool", pool, expected, query, path)
    pairs = [dict(order=order, arms=[read_once(arm, pool, expected, query, path) for arm in order]) for order in ORDERS]
    expected_modes = {"allocation": 1, "reuse": len(ORDERS)}
    if pool.counts != expected_modes or seed["pool_counts_delta"] != {"allocation": 1}:
        raise ValueError("The measured sequence did not reuse exactly one independently owned destination")
    p = expected["packet"]
    freeze(output, dict(machine=machine, authorized_tmpfs_path=str(path), manifest_scope_sha256=SCOPE_PIN,
                        member=scope["member"], pool_setup=setup, pool_first_use=seed, pairs=pairs,
                        pool_final_counts=pool.counts, original_archive_payload_bytes=0,
                        comparisons=dict(exact_named_mixed_prefix=True, decoded_window_hashes=len(expected["iq"]),
                        native_factors=sum(len(t["factors"]) for t in expected["trace"]), native_lanes=len(expected["trace"]),
                        native_schedule=expected["native_schedule"], selected=sum(len(row["candidates"]) for row in p["source"]["probes"]),
                        raw_authority=p["source"]["raw_recording_authority_digest"],
                        signed_analysis=p["source"]["analysis_manifest_sha256"])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
