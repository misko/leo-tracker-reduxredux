"""Profile a single original signed member with cold and naturally warm cache."""

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import asdict
import gzip
from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path
import resource
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from types import FunctionType, SimpleNamespace
from unittest.mock import patch

from . import receiver_ceiling_0169 as first, sparse_cold_input as release
from .centered_primary import ORIGINAL
from .full_short_cold import SHORT_SHA, freeze
from .mixed_aperture_receiver import FULL_RULE, INSTALLED_SHA, PILOT_SHA, MixedApertureDetector, NativePath
from .scout_readout_trial import check_machine, factor_bytes


FIRST_RECEIPT = Path(__file__).with_name("measurements") / "receiver-ceiling-0169.json.gz"
FIRST_RECEIPT_PIN = "ee76714eca005b03acd4b477172e9aafe9f38861f79dfe1c2294f323979e390e"
COMPACT_RECEIPT = FIRST_RECEIPT.with_name("direct-storage-0169.json.gz")
PREFIX_PACKET = Path("/dev/shm/leo-receiver-ceiling-0169-results01/1-full-short.json")
PREFIX_PIN = "2f9102ffead53766ccc71317243618ff415de7c537cd4bb81b7b8b57488eea13"
PAYLOAD = "iq-000001.ci16.zst"
PAYLOAD_PIN = "sha256:3ce0d40aaca2995cf28c7ab850ef6213081481abf126629150364b9769749d9f"
INDEX, INDEX_PIN = "windows-000001.jsonl", "sha256:39373f2895016322f91b8ca9f43875d6058a11cc3bfe418202f9f25ec8e8643b"
COMPRESSED, INDEX_BYTES = 78_620_639, 173_120
START, STOP = 64, 128


def member_one(model):
    if len(model.chunks) < 2 or model.receiver_ids != (0, 1) or model.sample_rate_hz != 10_000_000:
        raise ValueError("Missing the original stereo segment and second member")
    chunk = model.chunks[1]
    if (chunk.chunk_index, chunk.first_sequence, chunk.window_count, chunk.uncompressed_bytes) != (
            1, START, STOP-START, first.DECODED):
        raise ValueError("Member 1 has different window support")
    if (chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256,
            chunk.index_relative_path, chunk.index_bytes, chunk.index_sha256) != (
            PAYLOAD, COMPRESSED, PAYLOAD_PIN, INDEX, INDEX_BYTES, INDEX_PIN) or COMPRESSED > first.STAGE_CAP:
        raise ValueError("Member 1 differs from the frozen authority or byte bound")
    return chunk


def seed_streams(prefix):
    schedule = prefix["native_schedule"]
    if tuple(schedule["rule"]) != FULL_RULE or schedule["installed_sha256"] != INSTALLED_SHA or schedule[
            "short_primary_sha256"] != SHORT_SHA:
        raise ValueError("The earlier receipt belongs to another detector schedule")
    packet = prefix["packet"]
    probes = packet["source"]["probes"]
    streams = {}
    for a, b in zip(probes[::2], probes[1::2], strict=True):
        fields = ("visit_index", "edge", "channel", "actual_rf_hz", "valid_start_counter")
        if (a["receiver_id"], b["receiver_id"]) != (0, 1) or any(a[f] != b[f] for f in fields):
            raise ValueError("The earlier admitted probes are not ordered stereo pairs")
        key = a["edge"], a["channel"], a["actual_rf_hz"]
        count, previous = streams.get(key, (0, -1))
        counter = a["valid_start_counter"]
        if not 0 <= a["visit_index"] < START or counter <= previous:
            raise ValueError("The earlier stream counters are inconsistent")
        streams[key] = count+1, counter
    saved = {(r["edge"], r["channel"], r["rf_hz"]): (r["admitted"], r["final_valid_counter"])
             for r in schedule["streams"]}
    provenance = packet["provenance"]
    if (saved != streams or len(prefix["iq"]) != START or provenance["window_count"] != START
            or provenance["processed_windows"] != sum(n for n, _ in streams.values())
            or provenance["processed_windows"] + provenance["invalid_capture"] != START
            or len(packet["delivery_clocks"]) != START or not packet["clock_anchor"]):
        raise ValueError("Reconstructed scheduling state differs from the complete signed prefix")
    return streams


def source_binding():
    from leo.contracts.digests import canonical_digest

    binding = json.loads(release.verified(release.BINDING.with_name(first.CASE + ".json"), first.BINDING_PIN))
    inventory = json.loads(release.verified(first.INVENTORY, first.INVENTORY_PIN))
    if canonical_digest(inventory) != "sha256:" + first.INVENTORY_PIN:
        raise ValueError("The canonical original inventory differs")
    entry, manifest = first.scope_inventory(binding, inventory)
    return entry, manifest.with_name(PAYLOAD)


def prefix_bytes():
    if PREFIX_PACKET.is_file():
        return release.verified(PREFIX_PACKET, PREFIX_PIN)
    contents = json.loads(gzip.decompress(COMPACT_RECEIPT.read_bytes()))["prefix_worker_json"].encode()
    if sha256(contents).hexdigest() != PREFIX_PIN:
        raise ValueError("The archived scheduling seed differs from the original pinned receipt")
    return contents


class StageTimers:
    def __init__(self):
        self.rows = defaultdict(Counter)

    def call(self, name, function, *args, **kwargs):
        start = process_time_ns(), perf_counter_ns()
        try:
            return function(*args, **kwargs)
        finally:
            elapsed = process_time_ns()-start[0], perf_counter_ns()-start[1]
            self.rows[name].update(cpu_ns=elapsed[0], wall_ns=elapsed[1], calls=1)


@contextmanager
def verified_reader(spec, source, chunk, hasher, timers):
    from leo.storage import short_window
    from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256, paired_decoded_hashes

    buffer = release.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    scope = buffer.__wrapped__.__globals__
    descriptor, original_os = scope["read_regular"], scope["os"]
    zstd = short_window.zstd
    checks = []

    def read_descriptor(*args, **kwargs):
        start = resource.getrusage(resource.RUSAGE_SELF)
        result = timers.call("compressed_descriptor", descriptor, *args, **kwargs)
        stop = resource.getrusage(resource.RUSAGE_SELF)
        timers.rows["compressed_descriptor"].update(input_blocks=stop.ru_inblock-start.ru_inblock, bytes=len(result))
        return result

    class ObservedOS:
        def __getattr__(self, name):
            return getattr(original_os, name)

        def readv(self, *args):
            return timers.call("payload_read_syscalls", original_os.readv, *args)

        def read(self, *args):
            return timers.call("payload_read_syscalls", original_os.read, *args)

    class Decoder:
        def __init__(self):
            self.native = zstd.ZstdDecompressor()

        @contextmanager
        def stream_reader(self, compressed):
            with self.native.stream_reader(compressed) as reader:
                def read(count):
                    data = timers.call("zstd_read", reader.read, count)
                    timers.rows["zstd_read"]["bytes"] += len(data)
                    return data

                yield SimpleNamespace(read=read)

    def timed_member(reader, name, size, digest):
        expected = ((INDEX, INDEX_BYTES, INDEX_PIN), (PAYLOAD, COMPRESSED, PAYLOAD_PIN))
        if reader is not source.reader or len(checks) >= len(expected) or (name, size, digest) != expected[len(checks)]:
            raise ValueError("Read outside the frozen member and index")
        stage = "compressed_sha256" if name == PAYLOAD else "index_sha256"

        def hash_data(data):
            return timers.call(stage, original.__globals__["sha256_digest"], data)

        bound = FunctionType(original.__code__, original.__globals__ | {"sha256_digest": hash_data})
        data = timers.call("index_member", bound, reader, name, size, digest) if name == INDEX else bound(reader, name, size, digest)
        checks.append(dict(name=name, size=len(data), digest=digest))
        return data

    original = short_window.ShortWindowReader._member
    window_digest, decoded_digest = PairedSha256.window, PairedSha256.digest

    def hash_window(state, data):
        return timers.call("decoded_window_sha256", window_digest, state, data)

    def hash_decoded(state):
        return timers.call("decoded_member_sha256_final", decoded_digest, state)

    with (patch.dict(scope, {"os": ObservedOS(), "read_regular": read_descriptor}), buffer(),
          patch.object(short_window, "zstd", SimpleNamespace(ZstdDecompressor=Decoder, ZstdError=zstd.ZstdError)),
          patch.object(short_window.ShortWindowReader, "_member", timed_member),
          patch.object(PairedSha256, "window", hash_window), patch.object(PairedSha256, "digest", hash_decoded),
          paired_decoded_hashes(hasher)):
        yield checks
    if (len(checks) != 2 or timers.rows["compressed_descriptor"]["calls"] != 1
            or timers.rows["decoded_window_sha256"]["calls"] != chunk.window_count
            or timers.rows["decoded_member_sha256_final"]["calls"] != 1
            or timers.rows["zstd_read"]["bytes"] != chunk.uncompressed_bytes):
        raise ValueError("The released member did not complete all its verification stages")


def worker():
    from leo.contracts.digests import canonical_digest
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support
    from leo.storage.fast_scan import FastSegmentSource
    from tools.pipeline_eval.qualification.cache_residency import load_query
    from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256

    machine = check_machine()
    timers = StageTimers()
    entry, payload = source_binding()
    spec = json.loads(release.verified(release.PAYLOAD / "spec.json", release.SPEC_SHA))
    for name, pin in release.RUNTIME.items():
        release.verified(Path(import_module(name).__file__), pin)
    hasher = release.PAYLOAD / "paired-sha256.so"
    release.verified(hasher, spec["paired_sha256"]["sha256"])
    if not PairedSha256(hasher).hardware:
        raise ValueError("The released paired SHA-256 path is unavailable")
    release.verified(release.CACHE_LIBRARY, release.CACHE_SHA)
    query = load_query(release.CACHE_LIBRARY)

    def seeded_prefix():
        prior = json.loads(gzip.decompress(release.verified(FIRST_RECEIPT, FIRST_RECEIPT_PIN)))["documents"]["receipt"]["document"]
        sealed = next(row for row in prior["arms"] if row["pair"] == 1 and row["arm"] == "full-short")
        prefix = json.loads(prefix_bytes())
        packet = prefix["packet"]
        if (sealed["trace_sha256"] != PREFIX_PIN or prefix["iq"] != prior["iq_sha256"]
                or packet["source"]["session_id"] != first.SESSION
                or packet["source"]["input_manifest_sha256"] != "sha256:" + first.INVENTORY_PIN
                or packet["source"]["raw_recording_authority_digest"] != prior["raw_authority"]):
            raise ValueError("The prefix scheduling seed has different input authority")
        return packet, seed_streams(prefix)

    packet, streams = timers.call("prefix_seed", seeded_prefix)
    source = timers.call("source_setup", FastSegmentSource, entry, start_sequence=START, stop_sequence=STOP)
    chunk = member_one(source.reader.manifest)
    short = ORIGINAL / "short-primary.so"
    mix = MixedApertureDetector(short, SHORT_SHA, full_coverage=True)
    mix.schedule.streams.update(streams)
    policy = FastScanPolicyV2()
    generation = int(packet["source"]["stream_generation"].rsplit("-", 1)[1], 16)
    last_end = packet["last_sample_counter"]
    edge = "lower"
    traces, probes, exclusions, clocks, iq = [], [], [], [], []
    active, native = None, NativePath.run

    def tracked(self, samples, lane, center):
        result, elapsed = native(self, samples, lane, center)
        traces.append(dict(visit=active, receiver=lane, mode="full" if self.maximum == 2 else "short_primary",
                           factors=result))
        return result, elapsed

    context = mix.detector("cancellation", edge, binary=release.PAYLOAD / "receiver.so",
                           pilot=release.RELEASE / "assets" / (edge + ".f32"))
    receive = timers.call("native_context", context.__enter__)
    try:
        with verified_reader(spec, source, chunk, hasher, timers) as checks, patch.object(NativePath, "run", tracked):
            initial = first.snapshot(payload, COMPRESSED, query)
            start = process_time_ns(), perf_counter_ns()
            for window in source.windows():
                active = START + len(iq)
                capture, target = window.acquisition, window.target
                retune = json.loads(capture["retune_receipt"])
                if (window.sequence != active or capture["global_visit"] != active or target["edge"] != edge
                        or capture["generation"] != generation or capture["sample_start"] < last_end
                        or retune.get("utc_clock_bracket") is not None):
                    raise ValueError("The member changed the signed visit, pilot, hardware or clock sequence")
                last_end = capture["sample_end"]
                iq.append(window.iq_sha256)
                clocks.append(retune["host_delivery_clock"])
                if valid_window_support(capture, window.sample_rate_hz, window.samples.shape, source.receiver_ids, policy):
                    w = SimpleNamespace(acquisition=capture, target=target, samples=window.samples,
                                        sample_rate_hz=window.sample_rate_hz, receiver_ids=source.receiver_ids)
                    probes.extend(receive(w))
                else:
                    exclusions.append(dict(visit=active, sample_start=capture["sample_start"], sample_end=last_end,
                                           iq_sha256=window.iq_sha256, reason="invalid sample support or retune quality"))
            elapsed = dict(cpu_ns=process_time_ns()-start[0], wall_ns=perf_counter_ns()-start[1])
            final = first.snapshot(payload, COMPRESSED, query)
    finally:
        timers.call("native_context_exit", context.__exit__, *sys.exc_info())
    modes = mix.receipt()
    if (len(iq) != STOP-START or len(probes) + 2*len(exclusions) != 2*len(iq)
            or sum(modes["native_calls"].values()) != len(traces) or len(traces) != len(probes)
            or any((t["visit"], t["receiver"]) != (p["visit_index"], p["receiver_id"])
                   for t, p in zip(traces, probes, strict=True))):
        raise ValueError("Native paid lanes or whole window count differ from the signed path")
    body = dict(iq=iq, clock_anchor=packet["clock_anchor"], delivery_clocks=clocks, exclusions=exclusions,
                probes=probes, native=traces,
                schedule={k: v for k, v in modes.items() if k not in ("native_cpu_ns", "native_wall_ns")})
    return dict(machine=machine, member=chunk.model_dump(mode="json"), source=str(payload), acquire=elapsed,
                stages=timers.rows, reads=checks, before=initial, after=final, body=body,
                native_cpu_ns=modes["native_cpu_ns"], native_wall_ns=modes["native_wall_ns"],
                signed_output_sha256=canonical_digest(body), scheduled_from=PREFIX_PIN)


def result_budget(run):
    clock, stages = run["acquire"], run["stages"]
    descriptor = stages["compressed_descriptor"]
    allowance = COMPRESSED * 1000 / first.RATE_MB_S
    wait = max(0, descriptor["wall_ns"]-descriptor["cpu_ns"])
    excess = max(0, clock["wall_ns"]-allowance)
    overlap = max(0, clock["wall_ns"]-descriptor["wall_ns"])
    disjoint = {name: stages[name] for name in ("index_member", "compressed_descriptor", "compressed_sha256",
                                              "zstd_read", "decoded_window_sha256", "decoded_member_sha256_final")}
    remainder = {key: clock[key]-sum(s[key] for s in disjoint.values())-sum(run["native_"+key].values())
                 for key in ("cpu_ns", "wall_ns")}
    return dict(compressed_mb_s=COMPRESSED * 1000 / clock["wall_ns"], allowance_ns=allowance,
                descriptor_off_cpu_ns=wait, wall_excess_ns=excess, hide_fraction=excess/wait if wait else None,
                wall_without_descriptor_off_cpu_ns=clock["wall_ns"]-wait,
                ideal_member_local_overlap_floor_ns=max(descriptor["wall_ns"], overlap), disjoint_remainder=remainder)


def run(root):
    machine = check_machine()
    root = root.resolve()
    if root.parent != Path("/dev/shm"):
        raise ValueError("Use a fresh tmpfs output directory")
    root.mkdir(mode=0o700)
    runs = []
    for name in ("first", "repeat"):
        path = root / f"{name}.json"
        start = perf_counter_ns()
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        result = subprocess.run([sys.executable, "-BP", "-m", __spec__.name, "worker", str(path)],
                                check=False, timeout=25)
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        wall = perf_counter_ns()-start
        result.check_returncode()
        row = json.loads(path.read_bytes())
        row.update(process=dict(wall_ns=wall, cpu_s=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                                input_blocks=after.ru_inblock-before.ru_inblock, status=result.returncode),
                   order=name, budget=result_budget(row), raw_sha256=sha256(path.read_bytes()).hexdigest())
        runs.append(row)
    a, b = runs
    if a["body"] != b["body"] or any(factor_bytes(x["factors"]) != factor_bytes(y["factors"])
                                    for x, y in zip(a["body"]["native"], b["body"]["native"], strict=True)):
        raise ValueError("Naturally cold and resident verified signed outputs differ")
    evidence = a["body"]
    for row in runs:
        del row["body"]
    freeze(root / "receipt.json", dict(machine=machine, case=first.CASE, target_mb_s=first.RATE_MB_S, runs=runs,
           first_signed_prefix_sha256=PREFIX_PIN, first_receipt_sha256=FIRST_RECEIPT_PIN, signed_output=evidence,
           inventory_sha256=first.INVENTORY_PIN, compressed_sha256=PAYLOAD_PIN, new_physical_members=1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "worker"))
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        run(args.path)
    else:
        freeze(args.path, worker())
