"""Trace ready signed receiver work during two bounded original-member prefetches."""

import argparse
import json
import os
from contextlib import contextmanager
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from threading import get_native_id
from time import perf_counter_ns, thread_time_ns
from unittest.mock import patch

from . import full_short_cold as signed
from . import sparse_cold_input as frozen


def intersection(work, reads):
    """Bound CPU in pending syscall windows without assigning it uniformly in time."""
    lower = upper = bracketed = samples = d_samples = 0
    for row in work:
        start, stop, cpu = (row[key] for key in ("start_ns", "end_ns", "cpu_ns"))
        pending = sum(max(0, min(stop, r["end_ns"]) - max(start, r["start_ns"])) for r in reads)
        if not 0 <= pending <= stop - start or not 0 <= cpu <= stop - start:
            raise ValueError("Invalid one-worker syscall or compute clock")
        lower += max(0, cpu - (stop - start - pending))
        upper += min(cpu, pending)
        before, after = row["before"], row["after"]
        samples += sum(sample is not None for sample in (before, after))
        blocked = [sample for sample in (before, after) if sample and sample["state"] == "D"]
        d_samples += len(blocked)
        if len(blocked) == 2 and before["call"] == after["call"]:
            bracketed += cpu
    return dict(pending_read_cpu_lower_ns=lower, pending_read_cpu_upper_ns=upper,
                d_state_bracket_cpu_ns=bracketed, state_samples=samples, d_state_samples=d_samples)


class Trace:
    def __init__(self):
        self.reader = None
        self.active = None
        self.member = None
        self.reads = []
        self.work = []

    def task_state(self):
        active = self.active
        if active is None:
            return None
        status = Path(f"/proc/self/task/{self.reader}")
        state = (status / "stat").read_text().rsplit(") ", 1)[1][0]
        wait_channel = (status / "wchan").read_text().strip() if state == "D" else None
        return dict(call=active, state=state, wchan=wait_channel)

    def read(self, readv, fd, buffers):
        if self.reader != get_native_id():
            return readv(fd, buffers)
        call = len(self.reads)
        self.active = call
        start = perf_counter_ns()
        cpu = thread_time_ns()
        size = None
        try:
            size = readv(fd, buffers)
            return size
        finally:
            elapsed_cpu = thread_time_ns() - cpu
            stop = perf_counter_ns()
            self.active = None
            self.reads.append(dict(call=call, member=self.member, start_ns=start, end_ns=stop,
                                   cpu_ns=elapsed_cpu, bytes=size))

    def receive(self, operation, window):
        before = self.task_state()
        start = perf_counter_ns()
        cpu = thread_time_ns()
        result = operation(window)
        elapsed_cpu = thread_time_ns() - cpu
        stop = perf_counter_ns()
        after = self.task_state()
        self.work.append(dict(visit=window.acquisition["global_visit"], start_ns=start,
                              end_ns=stop, cpu_ns=elapsed_cpu, before=before, after=after))
        return result


def probe(output, short_binary):
    from leo.contracts.digests import canonical_digest
    from leo.storage.short_window import ShortWindowReader
    from tools.pipeline_eval.qualification.cache_residency import cache_snapshot, load_query
    from tools.pipeline_eval.variants.experimental import receiver_member_prefetch as prefetch

    machine = signed.check_machine()
    spec = json.loads(frozen.verified(frozen.PAYLOAD / "spec.json", frozen.SPEC_SHA))
    for name, digest in frozen.RUNTIME.items():
        frozen.verified(Path(import_module(name).__file__), digest)
    hasher = frozen.PAYLOAD / "paired-sha256.so"
    frozen.verified(hasher, spec["paired_sha256"]["sha256"])
    frozen.verified(frozen.PAYLOAD / "receiver.so", spec["detector_sha256"])
    frozen.verified(short_binary, signed.SHORT_SHA)
    archived_path, = (frozen.ARCHIVE / "fast-scan-automatic-work").glob("*/detections.json")
    archived = json.loads(frozen.verified(archived_path, frozen.ARCHIVED_DETECTION_SHA))
    session = archived["source"]["session_id"]
    inventory_path = frozen.ARCHIVE / "fast-scan-inputs" / f"{session}.json"
    inventory = json.loads(inventory_path.read_bytes())
    inventory_digest = canonical_digest(inventory)
    entry = inventory["segments"][0]
    path = Path(entry["path"])
    binding = json.loads(frozen.verified(frozen.BINDING, frozen.BINDING_SHA))
    pin = binding["case"]["recording"]["segments"][0]
    if (inventory_digest != archived["source"]["input_manifest_sha256"]
            or path / "manifest.json" != Path("/srv/bulk") / pin["path"]
            or entry["manifest_digest"] != "sha256:" + pin["sha256"]):
        raise ValueError("Original first segment differs from the frozen recording binding")
    segment = ShortWindowReader(path)
    chunks = segment.manifest.chunks[:frozen.MEMBERS]
    if (segment.manifest_sha256 != entry["manifest_digest"] or len(chunks) != frozen.MEMBERS
            or sum(c.compressed_bytes for c in chunks) > frozen.MAX_COMPRESSED
            or any(c.window_count != frozen.WINDOWS_PER_MEMBER for c in chunks)):
        raise ValueError("Unexpected sealed three-member input scope")

    output.mkdir()
    assets = output / "assets"
    assets.mkdir()
    (assets / "cancellation-factors.so").symlink_to(frozen.PAYLOAD / "receiver.so")
    (assets / "lower.f32").symlink_to(frozen.RELEASE / "assets/lower.f32")
    frozen.verified(frozen.CACHE_LIBRARY, frozen.CACHE_SHA)
    query = load_query(frozen.CACHE_LIBRARY)
    members = [(path, chunk.payload_relative_path, chunk.compressed_bytes) for chunk in chunks]
    page_size = os.sysconf("SC_PAGE_SIZE")
    trace = Trace()
    readv, fetch = os.readv, prefetch.prefetch_member
    detector = signed.MixedApertureDetector.detector
    installed_function = frozen.frozen_function

    def fetch_member(root, name, size, stats):
        trace.reader, trace.member = get_native_id(), name
        return fetch(root, name, size, stats)

    @contextmanager
    def trace_detector(instance, *args, **kwargs):
        with detector(instance, *args, **kwargs) as receive:
            yield lambda window: trace.receive(receive, window)

    def frozen_function(specification, source, attribute):
        original = installed_function(specification, source, attribute)
        if attribute == "compressed_member_lookahead":
            return prefetch.compressed_member_prefetch
        return original

    before = [cache_snapshot([member], page_size, query) for member in members]
    with (
        patch.object(prefetch, "prefetch_member", fetch_member),
        patch.object(os, "readv", lambda fd, buffers: trace.read(readv, fd, buffers)),
        patch.object(signed.MixedApertureDetector, "detector", trace_detector),
        patch.object(frozen, "frozen_function", frozen_function),
    ):
        row = signed.scope("full-short", assets, short_binary, spec, dict(
            entry=entry, session=session, inventory_digest=inventory_digest,
        ), output / "detections.json")
    after = [cache_snapshot([member], page_size, query) for member in members]
    if (row["sealed_detection_sha256"] != signed.PRIOR_SHORT_DETECTION_SHA
            or row["overlap"]["hits"] != len(chunks) - 1 or row["overlap"]["fallback"]
            or sum(r["bytes"] for r in trace.reads) != sum(c.compressed_bytes for c in chunks[1:])):
        raise ValueError("Signed detections or the prefetch input scope differ")

    intervals = intersection(trace.work, trace.reads)
    for r in trace.reads:
        r["off_thread_cpu_ns"] = max(0, r["end_ns"] - r["start_ns"] - r["cpu_ns"])
    signed.freeze(output / "receipt.json", dict(
        source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), machine=machine,
        elapsed_clock="CLOCK_MONOTONIC via perf_counter_ns", compute_clock="thread_time_ns",
        case="DS30-0008", manifest_sha256=segment.manifest_sha256,
        inventory_sha256=inventory_digest,
        frozen_spec_sha256=frozen.SPEC_SHA,
        original_members=[[str(root / name), size] for root, name, size in members],
        member_pins=[chunk.model_dump(mode="json") for chunk in chunks],
        cache_before=before, cache_after=after, cache_management=False, acquisition=row,
        overlap=intervals, reads=trace.reads, work=trace.work,
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("short_binary", type=Path)
    args = parser.parse_args()
    probe(args.output, args.short_binary)
