"""Measure bounded catalogue work at the signed member reader's demand boundary."""

import argparse
import json
import os
import resource
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from threading import get_native_id
from time import perf_counter_ns, process_time_ns, sleep, thread_time_ns
from unittest.mock import patch

from . import catalogue_prime
from . import full_short_cold as signed
from . import sparse_cold_input as frozen
from .ready_io import Trace

STAGED = Path("/dev/shm/leo-seekable-member-0008-case1")
SIGNED_PREFIX = Path("/dev/shm/leo-v3-ready-io-original-0008/detections.json")
SHORT = Path("/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so")
WINDOWS = 24
MEMBER_WINDOWS = 8
SOURCE_CAP = 75 * 1024**2
SOURCE_DECODE_CAP = 100 * 1024**2
PREFIX_CAP = 32 * 1024**2
ARCHIVE_CAP = 64 * 1024**2
PRIME_CAP = 4 * 1024**2
INJECT_S = 0.16
HOURS_48 = 48 * catalogue_prime.HOUR_NS


def stage(output, request):
    from leo.contracts.digests import canonical_digest
    from leo.storage.short_window import ShortWindowReader, ShortWindowWriter

    (segment,) = STAGED.glob("fast*/manifest.json")
    source = ShortWindowReader(segment.parent)
    chunk = source.manifest.chunks[0]
    source_bytes = sum(
        (source.path / p).stat().st_size
        for p in (
            "manifest.json",
            chunk.index_relative_path,
            chunk.payload_relative_path,
        )
    )
    if (
        source.manifest_sha256 != request["manifests"][0][1]
        or source_bytes > SOURCE_CAP
        or chunk.uncompressed_bytes > SOURCE_DECODE_CAP
        or chunk.first_sequence
        or chunk.window_count != 64
    ):
        raise ValueError("The staged source is outside the frozen first-member bound")
    writer = ShortWindowWriter(
        output,
        source.manifest.session_id,
        schema_version=2,
        chunk_windows=MEMBER_WINDOWS,
        configuration=source.manifest.configuration,
        radio=source.manifest.radio,
        receiver_ids=source.manifest.receiver_ids,
    )
    hashes = []
    for index, samples in (
        (read.index, read.samples) for read in source.windows(stop_sequence=WINDOWS)
    ):
        writer.append(
            sequence=index.sequence,
            target_id=index.target_id,
            samples=samples,
            acquisition=index.acquisition,
            powers=index.powers,
        )
        hashes.append(index.iq_sha256)
    destination = writer.finish(stop_reason="temporary verified playback prefix")
    reader = ShortWindowReader(destination)
    members = [
        [name, size, digest]
        for c in reader.manifest.chunks
        for name, size, digest in (
            (c.index_relative_path, c.index_bytes, c.index_sha256),
            (c.payload_relative_path, c.compressed_bytes, c.compressed_sha256),
        )
    ]
    stored = (destination / "manifest.json").stat().st_size + sum(n for _, n, _ in members)
    if stored > PREFIX_CAP or len(members) != 6 or len(hashes) != WINDOWS:
        raise ValueError("The staged playback exceeded its frozen prefix scope")
    entry = dict(path=str(destination), manifest_digest=reader.manifest_sha256, windows=WINDOWS)
    inventory = dict(segments=[entry], window_count=WINDOWS)
    return dict(
        entry=entry,
        inventory_digest=canonical_digest(inventory),
        session=request["session"],
        source_manifest_sha256=source.manifest_sha256,
        source_bytes=source_bytes,
        decoded_source_bytes=chunk.uncompressed_bytes,
        prefix_bytes=stored,
        source_chunk=chunk.model_dump(mode="json"),
        members=members,
        iq_sha256=hashes,
    )


def refs_at(archive, cutoff):
    return [
        r
        for r in archive.list_snapshots("space-track")
        if 0 <= cutoff - r.collected_utc_ns <= HOURS_48
    ]


class DemandTrace:
    def __init__(self, archive, parser_type, arm, delay):
        self.archive, self.parser_type = archive, parser_type
        self.arm, self.delay = arm, delay
        self.parser = parser_type()
        self.cutoff = None
        self.plan = None
        self.primed = set()
        self.disabled = False
        self.trace = Trace()
        self.active_hold = None
        self.holds, self.demands, self.primes, self.queries, self.demand_reads = [], [], [], [], []

    def fetch(self, operation, root, name, size, stats):
        self.trace.reader, self.trace.member = get_native_id(), name
        value = operation(root, name, size, stats)
        if self.delay:
            start = perf_counter_ns()
            self.active_hold = name
            try:
                sleep(self.delay)
            finally:
                self.active_hold = None
                self.holds.append(dict(member=name, start_ns=start, end_ns=perf_counter_ns()))
        if self.arm == "fallback" and name == "iq-000002.ci16.zst":
            return None
        return value

    def receive(self, operation, window):
        if window.acquisition["global_visit"] == 0:
            anchor = json.loads(window.acquisition["retune_receipt"])["utc_clock_bracket"]
            if anchor["sample_counter"] != window.acquisition["sample_start"]:
                raise ValueError("Unbound first-window cutoff")
            self.cutoff = anchor["before"]["realtime_ns"]
        return self.trace.receive(operation, window)

    def prime(self, member):
        from leo.operations.tle_archive import TleArchiveError

        start, cpu = perf_counter_ns(), thread_time_ns()
        ref, size, error = None, 0, None
        read_time, parse_time = None, None
        try:
            if self.plan is None:
                distinct = {r.sha256: r for r in reversed(refs_at(self.archive, self.cutoff))}
                self.plan = deque(reversed(tuple(distinct.values())))
            if (
                not self.plan
                or self.plan[0].byte_size + sum(r["bytes"] for r in self.primes) > PRIME_CAP
            ):
                self.disabled = True
                return
            ref = self.plan.popleft()
            read_start, read_cpu = perf_counter_ns(), thread_time_ns()
            content = self.archive.read(ref)
            size = ref.byte_size
            read_time = dict(
                start_ns=read_start, end_ns=perf_counter_ns(), cpu_ns=thread_time_ns() - read_cpu
            )
            if self.arm == "fallback" and self.primed:
                raise ValueError("injected speculative parser failure")
            parse_start, parse_cpu = perf_counter_ns(), thread_time_ns()
            self.parser(content)
            parse_time = dict(
                start_ns=parse_start, end_ns=perf_counter_ns(), cpu_ns=thread_time_ns() - parse_cpu
            )
            self.primed.add(ref.sha256)
        except (OSError, ValueError, TleArchiveError) as err:
            error = f"{type(err).__name__}: {err}"
            self.parser = self.parser_type()
            self.primed.clear()
            self.disabled = True
        finally:
            self.primes.append(
                dict(
                    member=member,
                    source=ref.path.name if ref else None,
                    digest=ref.sha256 if ref else None,
                    bytes=size,
                    error=error,
                    read=read_time,
                    parse=parse_time,
                    start_ns=start,
                    end_ns=perf_counter_ns(),
                    cpu_ns=thread_time_ns() - cpu,
                )
            )

    def demand(self, future, member):
        start = perf_counter_ns()
        ready = future.done()
        read_active = self.trace.active is not None and self.trace.member == member
        simulated_hold = self.active_hold == member
        if (
            self.arm != "serial"
            and not self.disabled
            and not ready
            and self.cutoff is not None
            and (read_active or simulated_hold)
        ):
            self.prime(member)
        wait_start = perf_counter_ns()
        result = future.result()
        end = perf_counter_ns()
        self.demands.append(
            dict(
                member=member,
                start_ns=start,
                wait_start_ns=wait_start,
                end_ns=end,
                ready_at_demand=ready,
                active_read=read_active,
                simulated_hold=simulated_hold,
                speculative_hit=result is not None,
                join_ns=end - wait_start,
            )
        )
        return result


def run_arm(output, fixture, request, spec, label, arm, delay):
    from contextlib import contextmanager

    from sgp4.exporter import export_tle

    from leo.contracts.digests import canonical_digest
    from leo.operations.causal_tle_catalogue import causal_catalogue
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.fast_scan import FastSegmentSource
    from leo.storage.scanner import ScannerIqStore
    from tools.pipeline_eval.variants import algo08_causal_reuse
    from tools.pipeline_eval.variants.experimental import receiver_member_prefetch as prefetch
    from tools.pipeline_eval.variants.experimental.tle_records import batch_records

    archive = TleArchiveReader(Path(request["local_archive"]["root"]))
    trace = DemandTrace(archive, algo08_causal_reuse.CausalPreparationParser, arm, delay)
    readv = os.readv
    original_read = ScannerIqStore._read_regular
    original_windows = FastSegmentSource.windows
    detector = signed.MixedApertureDetector.detector
    load = frozen.frozen_function
    assets = output / "assets"

    class Pending:
        def __init__(self, future, member):
            self.future, self.member = future, member

        def result(self):
            return trace.demand(self.future, self.member)

        def cancel(self):
            return self.future.cancel()

    class ReaderPool(ThreadPoolExecutor):
        def submit(self, operation, root, name, size, stats):
            return Pending(super().submit(trace.fetch, operation, root, name, size, stats), name)

    def instrumented_read(path, maximum_bytes):
        start, cpu = perf_counter_ns(), thread_time_ns()
        result = original_read(path, maximum_bytes)
        if path.parent == Path(fixture["entry"]["path"]):
            trace.demand_reads.append(
                dict(
                    member=path.name,
                    bytes=len(result),
                    start_ns=start,
                    end_ns=perf_counter_ns(),
                    cpu_ns=thread_time_ns() - cpu,
                )
            )
        return result

    def instrumented_readv(fd, buffers):
        if get_native_id() == trace.trace.reader:
            return trace.trace.read(readv, fd, buffers)
        path = Path(os.readlink(f"/proc/self/fd/{fd}"))
        start, cpu = perf_counter_ns(), thread_time_ns()
        count = readv(fd, buffers)
        if path.parent == Path(fixture["entry"]["path"]):
            trace.demand_reads.append(
                dict(
                    member=path.name,
                    bytes=count,
                    start_ns=start,
                    end_ns=perf_counter_ns(),
                    cpu_ns=thread_time_ns() - cpu,
                )
            )
        return count

    @contextmanager
    def instrumented_detector(instance, *args, **kwargs):
        with detector(instance, *args, **kwargs) as receive:
            yield lambda window: trace.receive(receive, window)

    def installed_function(specification, source, attribute):
        result = load(specification, source, attribute)
        return (
            prefetch.compressed_member_prefetch
            if attribute == "compressed_member_lookahead"
            else result
        )

    def consume(ref):
        start, cpu = perf_counter_ns(), thread_time_ns()
        body = archive_read(ref)
        trace.queries.append(
            dict(
                source=ref.path.name,
                digest=ref.sha256,
                collection_utc_ns=ref.collected_utc_ns,
                bytes=ref.byte_size,
                hit=body in trace.parser.catalogues,
                start_ns=start,
                end_ns=perf_counter_ns(),
                cpu_ns=thread_time_ns() - cpu,
            )
        )
        return body

    archive_read = archive.read
    before = resource.getrusage(resource.RUSAGE_SELF)
    io = frozen.io_snapshot()
    start, cpu = perf_counter_ns(), process_time_ns()
    result_path = output / f"{label}.detections.json"
    with (
        batch_records(Path(spec["tle_parser"]["library"])) as native_counts,
        patch.object(prefetch, "ThreadPoolExecutor", ReaderPool),
        patch.object(os, "readv", instrumented_readv),
        patch.object(ScannerIqStore, "_read_regular", staticmethod(instrumented_read)),
        patch.object(frozen, "frozen_function", installed_function),
        patch.object(signed.MixedApertureDetector, "detector", instrumented_detector),
        patch.object(frozen, "WINDOWS", WINDOWS),
    ):
        acquisition = signed.scope("full-short", assets, SHORT, spec, fixture, result_path)
        seal = perf_counter_ns()
        packet = json.loads(result_path.read_bytes())
        cutoff = packet["clock_anchor"]["before"]["realtime_ns"]
        if cutoff != trace.cutoff or cutoff != request["causal_cutoff_utc_ns"]:
            raise ValueError("The later query must use the exact authenticated cutoff")
        chosen = refs_at(archive, cutoff)
        if sum(r.byte_size for r in chosen) > ARCHIVE_CAP:
            raise ValueError("Ordinary causal query exceeds its read bound")
        parse_events = []

        def parse(text):
            t0, c0 = perf_counter_ns(), thread_time_ns()
            value = trace.parser(text)
            parse_events.append(
                dict(
                    source=trace.queries[-1]["source"],
                    start_ns=t0,
                    end_ns=perf_counter_ns(),
                    cpu_ns=thread_time_ns() - c0,
                )
            )
            return value

        query_start, query_cpu = perf_counter_ns(), process_time_ns()
        with patch.object(archive, "read", consume):
            result = causal_catalogue(archive, cutoff, element_parser=parse)
        stop, total_cpu = perf_counter_ns(), process_time_ns() - cpu
        query_time = dict(
            start_ns=query_start,
            end_ns=stop,
            cpu_ns=process_time_ns() - query_cpu,
            cutoff_utc_ns=cutoff,
            max_age_s=172800,
            provider="space-track",
        )
        counts = dict(native_counts)
    if (
        os.readv is not readv
        or prefetch.ThreadPoolExecutor is not ThreadPoolExecutor
        or ScannerIqStore._read_regular is not original_read
        or FastSegmentSource.windows is not original_windows
        or signed.MixedApertureDetector.detector is not detector
    ):
        raise ValueError("Experiment patches were not restored")
    after = resource.getrusage(resource.RUSAGE_SELF)
    final_io = frozen.io_snapshot()
    member_bytes = {name: size for name, size, _ in fixture["members"]}
    observed = Counter()
    for row in (*trace.demand_reads, *trace.trace.reads):
        observed[row["member"]] += row["bytes"]
    expected = member_bytes | {
        "manifest.json": (Path(fixture["entry"]["path"]) / "manifest.json").stat().st_size
    }
    if arm == "fallback":
        expected["iq-000002.ci16.zst"] *= 2
    if observed != expected:
        raise ValueError(
            f"Measured acquisition transferred a different member byte ledger {observed}"
        )
    if (
        acquisition["decoded_iq_hashes"] != fixture["iq_sha256"]
        or len(trace.demands) != 2
        or [r["source"] for r in trace.queries] != [r.path.name for r in chosen]
        or result.snapshot_count != len(chosen)
    ):
        raise ValueError("Acquisition or authoritative query coverage changed")
    witness = canonical_digest(
        [
            result.provenance,
            result.catalogue.names,
            [export_tle(sat) for sat in result.catalogue.satellites],
        ]
    )
    return dict(
        label=label,
        arm=arm,
        simulated_delay_s=delay,
        start_ns=start,
        end_ns=stop,
        cpu_ns=total_cpu,
        input_blocks=after.ru_inblock - before.ru_inblock,
        peak_rss_kib=after.ru_maxrss,
        proc_read_bytes=final_io["read_bytes"] - io["read_bytes"],
        acquisition=acquisition,
        sealed_acquisition_at_ns=seal,
        readiness=trace.trace.work,
        reads=trace.trace.reads,
        controlled_holds=trace.holds,
        demands=trace.demands,
        demand_reads=trace.demand_reads,
        paid_member_bytes=sum(observed.values()),
        paid_primes=trace.primes,
        query=query_time,
        query_reads=trace.queries,
        query_parses=parse_events,
        parser=trace.parser.stats,
        native_parser=counts,
        query_digest=witness,
        query_count=len(result.provenance),
        patched_ports_restored=True,
    )


def run(output, fixture_path=None):
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    machine = signed.check_machine()
    spec = json.loads(frozen.verified(frozen.PAYLOAD / "spec.json", frozen.SPEC_SHA))
    request = json.loads(frozen.verified(catalogue_prime.REQUEST, catalogue_prime.REQUEST_PIN))
    for name, digest in frozen.RUNTIME.items():
        frozen.verified(Path(import_module(name).__file__), digest)
    for name in (
        "tools.pipeline_eval.variants.algo08_causal_reuse",
        "tools.pipeline_eval.variants.experimental.tle_records",
    ):
        frozen.verified(
            Path(import_module(name).__file__), spec["sources"][name.replace(".", "/") + ".py"]
        )
    archive = TleArchiveReader(Path(request["local_archive"]["root"]))
    refs = archive.list_snapshots("space-track")
    if (
        canonical_digest({r.path.name: r.sha256 for r in refs})
        != request["local_archive"]["snapshots_sha256"]
    ):
        raise ValueError("The same verified causal archive is required in every branch")
    frozen.verified(SHORT, signed.SHORT_SHA)
    frozen.verified(frozen.PAYLOAD / "receiver.so", spec["detector_sha256"])
    frozen.verified(frozen.PAYLOAD / "paired-sha256.so", spec["paired_sha256"]["sha256"])
    frozen.verified(Path(spec["tle_parser"]["library"]), spec["tle_parser"]["sha256"])
    frozen.verified(frozen.RELEASE / "assets/lower.f32", signed.PILOT_SHA["lower"])
    prior = json.loads(frozen.verified(SIGNED_PREFIX, signed.PRIOR_SHORT_DETECTION_SHA))
    output.mkdir()
    assets = output / "assets"
    assets.mkdir()
    (assets / "cancellation-factors.so").symlink_to(frozen.PAYLOAD / "receiver.so")
    (assets / "lower.f32").symlink_to(frozen.RELEASE / "assets/lower.f32")
    t0, c0 = perf_counter_ns(), process_time_ns()
    if fixture_path is None:
        fixture = stage(output, request)
    else:
        fixture = json.loads(fixture_path.read_bytes())
        segment = Path(fixture["entry"]["path"]).resolve(strict=True)
        if segment.parent != fixture_path.parent or Path("/dev/shm") not in segment.parents:
            raise ValueError("The staging receipt must bind its own existing tmpfs prefix")
        if (
            fixture["source_manifest_sha256"] != request["manifests"][0][1]
            or fixture["prefix_bytes"] > PREFIX_CAP
        ):
            raise ValueError("The existing derived prefix differs from its original authority")
        if (
            sum(p.stat().st_size for p in segment.iterdir() if p.is_file())
            != fixture["prefix_bytes"]
        ):
            raise ValueError("The existing derived prefix changed size")
    staging = dict(wall_ns=perf_counter_ns() - t0, cpu_ns=process_time_ns() - c0)
    signed.freeze(output / "fixture.json", fixture)
    arms = [
        ("natural-a-serial", "serial", 0),
        ("natural-a-overlap", "overlap", 0),
        ("natural-b-overlap", "overlap", 0),
        ("natural-b-serial", "serial", 0),
        ("controlled-a-serial", "serial", INJECT_S),
        ("controlled-a-overlap", "overlap", INJECT_S),
        ("controlled-b-overlap", "overlap", INJECT_S),
        ("controlled-b-serial", "serial", INJECT_S),
        ("controlled-fallback", "fallback", INJECT_S),
    ]
    runs = []
    for label, arm, delay in arms:
        row = run_arm(output, fixture, request, spec, label, arm, delay)
        packed = json.loads((output / f"{label}.detections.json").read_bytes())
        if (
            packed["source"]["probes"] != prior["source"]["probes"][: 2 * WINDOWS]
            or packed["delivery_clocks"] != prior["delivery_clocks"][:WINDOWS]
            or packed["clock_anchor"] != prior["clock_anchor"]
        ):
            raise ValueError("Original signed factors or physical source clocks changed")
        signed.freeze(output / f"{label}.json", row)
        runs.append(row)
    base = runs[0]
    keys = ("source", "digest", "collection_utc_ns", "bytes")
    for row in runs:
        if (
            row["acquisition"]["sealed_detection_sha256"]
            != base["acquisition"]["sealed_detection_sha256"]
            or row["query_digest"] != base["query_digest"]
            or [[q[k] for k in keys] for q in row["query_reads"]]
            != [[q[k] for k in keys] for q in base["query_reads"]]
        ):
            raise ValueError("Signals or the ordinary causal query changed")
    signed.freeze(
        output / "result.json",
        dict(
            machine=machine,
            fixture=fixture,
            staging=staging,
            bound_bytes=dict(
                source=SOURCE_CAP, prefix=PREFIX_CAP, archive=ARCHIVE_CAP, prime=PRIME_CAP
            ),
            source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
            signed_asset_spec=frozen.SPEC_SHA,
            archived_signal_sha256=signed.PRIOR_SHORT_DETECTION_SHA,
            archive_sha256=request["local_archive"]["snapshots_sha256"],
            runs=runs,
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    cli.add_argument("--fixture", type=Path)
    args = cli.parse_args()
    run(args.output, args.fixture)
