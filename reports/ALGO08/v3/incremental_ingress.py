"""Compare provisional DSP and whole compressed validation on a staged member."""

import argparse
from contextlib import contextmanager
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import stat
from time import perf_counter_ns, process_time_ns, sleep
from types import SimpleNamespace
from unittest.mock import patch

from . import direct_storage_0169 as direct, receiver_ceiling_0169 as ceiling, sparse_cold_input as release
from .full_short_cold import freeze
from .mixed_aperture_receiver import MixedApertureDetector
from .scout_readout_trial import check_machine, factor_bytes


STAGED = Path("/dev/shm/leo-receiver-ceiling-0169-results01")
SCOPE_PIN = "95a438f0904e4568b6f2a3618b7fbf691c29d0e2d352fd3727cc83d35b72aa9a"
DIRECT_PIN = "1cfa963cd4f0afdad16dfe8dc88e5003efa315f1cc4b763fda29850dd710c035"
BLOCK = 1 << 20


def regular_scope(fd, size):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != size:
        raise ValueError("The input is no longer the bounded signed regular file")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def read_exact(fd, count):
    data = os.read(fd, count)
    if len(data) != count:
        raise ValueError("The staged compressed read ended early")
    return data


def measure_arrivals(path, size, pin):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    digest, stamps = sha256(), []
    try:
        binding = regular_scope(fd, size)
        start = process_time_ns(), perf_counter_ns()
        for offset in range(0, size, BLOCK):
            data = read_exact(fd, min(BLOCK, size-offset))
            stamps.append(perf_counter_ns()-start[1])
            digest.update(data)
        cpu, wall = process_time_ns()-start[0], perf_counter_ns()-start[1]
        if os.read(fd, 1) or regular_scope(fd, size) != binding or digest.hexdigest() != pin.removeprefix("sha256:"):
            raise ValueError("Timed arrival calibration changed the signed compressed source")
    finally:
        os.close(fd)
    return stamps, dict(cpu_ns=cpu, wall_ns=wall, obtained_bytes=size)


class Delivery:
    """Observe actual demand or enforce elapsed-time release boundaries."""

    def __init__(self, size, deadlines, *, corrupt=False):
        self.size = size
        self.deadlines = deadlines
        self.paced_chunks = deadlines is not None and deadlines[0] != deadlines[-1]
        self.corrupt = corrupt
        self.origin = self.last_byte = None
        self.offset = self.positive_reads = self.read_cpu_ns = self.read_wall_ns = self.sleep_ns = 0

    def ready(self, count):
        if self.origin is None:
            self.origin = perf_counter_ns()
        end = self.offset+count
        if count <= 0 or end > self.size:
            raise ValueError("The compressed delivery exceeded its exact byte boundary")
        if self.deadlines is None:
            return
        remaining = self.deadlines[(end-1)//BLOCK] - (perf_counter_ns()-self.origin)
        if remaining > 0:
            start = perf_counter_ns()
            sleep(remaining/1e9)
            self.sleep_ns += perf_counter_ns()-start

    def transfer(self, size, read, *args):
        self.ready(size)
        start = process_time_ns(), perf_counter_ns()
        result = read(*args)
        self.read_cpu_ns += process_time_ns()-start[0]
        self.read_wall_ns += perf_counter_ns()-start[1]
        count = result if isinstance(result, int) else len(result)
        if not 0 < count <= size:
            raise ValueError("The staged compressed delivery did not make progress")
        self.positive_reads += 1
        self.offset += count
        if self.offset == self.size:
            self.last_byte = perf_counter_ns()
        return result

    def readv(self, fd, vectors):
        if len(vectors) != 1:
            raise ValueError("The released compressed descriptor changed")
        buffer, = vectors
        count = min(len(buffer), BLOCK) if self.paced_chunks else len(buffer)
        target = buffer[:count]
        length = self.transfer(count, os.readv, fd, [target])
        if self.corrupt and self.last_byte is not None:
            target[length-1] ^= 1
        return length

    def receipt(self):
        return {k: getattr(self, k) for k in ("offset", "positive_reads", "read_cpu_ns", "read_wall_ns", "sleep_ns")}


class CompressedFeed:
    """Take ownership of bounded input objects and prove the member before commit."""

    def __init__(self, fd, delivery, pin):
        self.fd, self.delivery, self.pin = fd, delivery, pin
        self.original = regular_scope(fd, delivery.size)
        self.hash = sha256()
        self.high_water = self.hash_cpu_ns = 0
        self.finished = False

    def read(self, count):
        if not 0 <= count <= BLOCK:
            raise ValueError("Zstandard requested more than one bounded compressed block")
        count = min(count, self.delivery.size-self.delivery.offset)
        if not count:
            return b""
        data = self.delivery.transfer(count, read_exact, self.fd, count)
        if self.delivery.corrupt and self.delivery.last_byte is not None:
            data = data[:-1] + bytes((data[-1] ^ 1,))
        self.high_water = max(self.high_water, len(data))
        start = process_time_ns()
        self.hash.update(data)
        self.hash_cpu_ns += process_time_ns()-start
        return data

    def finish(self):
        from leo.storage.errors import BundleCorruptionError

        if (self.delivery.offset != self.delivery.size or os.read(self.fd, 1)
                or regular_scope(self.fd, self.delivery.size) != self.original
                or self.hash.hexdigest() != self.pin.removeprefix("sha256:")):
            raise BundleCorruptionError("provisional compressed member did not pass final authority")
        self.finished = True


@contextmanager
def provisional_decoder(path, member, delivery):
    from leo.storage import short_window

    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    original_member = short_window.ShortWindowReader._member
    zstd = short_window.zstd
    feed = None

    def member_port(reader, name, extent, digest):
        nonlocal feed
        if name == member["index_relative_path"]:
            return original_member(reader, name, extent, digest)
        if (feed is not None or reader.path / name != path or (name, extent, digest) != (
                member["payload_relative_path"], member["compressed_bytes"], member["compressed_sha256"])):
            raise ValueError("The decoder asked for a different compressed member")
        feed = CompressedFeed(fd, delivery, digest)
        return feed

    class ZstdDecoder:
        def __init__(self):
            self.decoder = zstd.ZstdDecompressor()

        @contextmanager
        def stream_reader(self, source):
            if source is not feed:
                raise ValueError("The bounded decoder did not receive its originating feed")
            with self.decoder.stream_reader(source, read_size=BLOCK, closefd=False) as reader:
                yield reader
            source.finish()

    try:
        with (patch.object(short_window.ShortWindowReader, "_member", member_port),
              patch.object(short_window, "zstd", SimpleNamespace(ZstdError=zstd.ZstdError, ZstdDecompressor=ZstdDecoder))):
            metadata = {}
            yield metadata
            if feed is None or not feed.finished:
                raise ValueError("The result escaped without final compressed verification")
            metadata.update(hash_cpu_ns=feed.hash_cpu_ns, max_read_object_bytes=feed.high_water)
    finally:
        os.close(fd)


@contextmanager
def paced_whole_read(delivery):
    frozen = release.frozen_function

    def config(spec, filename, symbol):
        function = frozen(spec, filename, symbol)
        if (filename, symbol) != ("receiver_ingress.py", "compressed_input_buffer"):
            return function

        class ObservedOS:
            def __getattr__(self, name):
                return getattr(os, name)

            def readv(self, fd, vectors):
                return delivery.readv(fd, vectors)

        @contextmanager
        def buffer():
            with patch.dict(function.__wrapped__.__globals__, {"os": ObservedOS()}), function():
                yield

        return buffer

    with patch.object(release, "frozen_function", config):
        yield


def staged_scope():
    from leo.contracts.multirate_window_recording import ShortWindowManifestV2

    scope = json.loads(release.verified(STAGED / "scope.json", SCOPE_PIN))
    segment = Path(scope["entry"]["path"])
    if segment.parent != STAGED or segment.resolve(strict=True) != segment or STAGED.resolve(strict=True) != STAGED:
        raise ValueError("Only the previous signed tmpfs scope is authorized")
    manifest = segment / "manifest.json"
    if manifest.resolve(strict=True) != manifest:
        raise ValueError("The staged manifest must remain local")
    content = release.verified(manifest, scope["entry"]["manifest_digest"])
    member = ceiling.first_member(ShortWindowManifestV2.model_validate_json(content)).model_dump(mode="json")
    if member != scope["member"]:
        raise ValueError("The original staged member differs")
    for name in (member["payload_relative_path"], member["index_relative_path"]):
        path = segment / name
        if path.resolve(strict=True) != path or path.stat().st_dev != STAGED.stat().st_dev:
            raise ValueError("The staged input may not resolve outside tmpfs")
    return segment / member["payload_relative_path"], member


def run_arm(mode, output, deadlines, path, member, expected, *, corrupt=False):
    from leo.contracts.digests import canonical_digest
    from leo.storage.errors import BundleCorruptionError
    from leo.storage.fast_scan import FastSegmentSource, immutable_json

    delivery = Delivery(member["compressed_bytes"], deadlines, corrupt=corrupt)
    provisional, tally = {}, dict(verified_windows=0, completed_stereo=0)
    paid_clock = dict(cpu_ns=0, wall_ns=0)
    original_windows, detector = FastSegmentSource.windows, MixedApertureDetector.detector

    def checked_windows(source):
        for window in original_windows(source):
            if window.samples.flags.writeable:
                raise ValueError("DSP was offered a mutable window")
            tally.setdefault("first_owned", perf_counter_ns())
            tally["verified_windows"] += 1
            yield window

    @contextmanager
    def paid(*args, **kwargs):
        with detector(*args, **kwargs) as receive:
            def visit(window):
                tally.setdefault("first_dsp_start", perf_counter_ns())
                start = process_time_ns(), perf_counter_ns()
                rows = receive(window)
                paid_clock["cpu_ns"] += process_time_ns()-start[0]
                paid_clock["wall_ns"] += perf_counter_ns()-start[1]
                tally.setdefault("first_dsp_finish", perf_counter_ns())
                tally["completed_stereo"] += 1
                return rows

            yield visit

    usage = resource.getrusage(resource.RUSAGE_SELF)
    begin = process_time_ns(), perf_counter_ns()
    open_path = provisional_decoder(path, member, delivery) if mode == "incremental" else paced_whole_read(delivery)
    result, error = None, None
    try:
        with (open_path as provisional, patch.object(FastSegmentSource, "windows", checked_windows),
              patch.object(MixedApertureDetector, "detector", paid)):
            result = ceiling.acquire(STAGED, "full-short")
        tally["verified"] = perf_counter_ns()
        if corrupt:
            raise ValueError("The corrupted duplicate survived the original checks")
        immutable_json(output, result["packet"])
        tally["sealed"] = perf_counter_ns()
    except BundleCorruptionError as exc:
        if not corrupt:
            raise
        error = dict(type=type(exc).__name__, detail=str(exc), cause=type(exc.__cause__).__name__)
    finish = process_time_ns(), perf_counter_ns()
    end_usage = resource.getrusage(resource.RUSAGE_SELF)
    if (error is None) != output.is_file():
        raise ValueError("A corrupted member produced a seal")
    native_clock = acquisition = None
    if result is not None:
        if any(canonical_digest(result[key]) != canonical_digest(expected[key])
               for key in ("iq", "packet", "trace", "original_member_reads")) or any(
                factor_bytes(a["factors"]) != factor_bytes(b["factors"])
                for a, b in zip(result["trace"], expected["trace"], strict=True)):
            raise ValueError("Signed lane factors changed under compressed delivery")
        native_clock = result["native_cpu_ns"]
        acquisition = {key: result[key] for key in ("acquire_cpu_ns", "acquire_wall_ns", "native_schedule",
                                                    "native_wall_ns", "original_member_reads")}
    return dict(mode=mode, corrupt=corrupt, error=error, dropped_stereo=tally["completed_stereo"] if error else 0,
                verified_windows=tally["verified_windows"], completed_stereo=tally["completed_stereo"],
                elapsed_ns=finish[1]-begin[1], cpu_ns=finish[0]-begin[0], sealed=output.is_file(),
                packet_sha256=sha256(output.read_bytes()).hexdigest() if output.is_file() else None,
                stats=provisional, delivery=delivery.receipt(), acquisition=acquisition,
                native_cpu_ns=native_clock, paid_callback=paid_clock,
                events_ns={k: v-begin[1] for k, v in dict(tally, demand=delivery.origin,
                           last_byte=delivery.last_byte).items() if k not in ("verified_windows", "completed_stereo") and v is not None},
                peak_rss_kib=end_usage.ru_maxrss, minor_faults=end_usage.ru_minflt-usage.ru_minflt,
                process_input_blocks=end_usage.ru_inblock-usage.ru_inblock)


def run(root):
    from tools.pipeline_eval.qualification.cache_residency import load_query

    machine = check_machine()
    root = root.resolve()
    if root.parent != Path("/dev/shm"):
        raise ValueError("Use a fresh tmpfs experiment directory")
    root.mkdir(mode=0o700)
    path, member = staged_scope()
    signed = json.loads(direct.prefix_bytes())
    release.verified(release.CACHE_LIBRARY, release.CACHE_SHA)
    query = load_query(release.CACHE_LIBRARY)
    start = ceiling.snapshot(path, ceiling.COMPRESSED, query)
    stamps, calibration = measure_arrivals(path, ceiling.COMPRESSED, ceiling.PAYLOAD_PIN)
    archive = json.loads(gzip.decompress(release.verified(direct.COMPACT_RECEIPT, DIRECT_PIN)))
    endpoint = json.loads(archive["acquisition_json"])["runs"][0]["stages"]["compressed_descriptor"]["wall_ns"]
    profiles = {"immediate": [0]*len(stamps), "measured_tmpfs": stamps, "cold_completion_only": [endpoint]*len(stamps)}
    experiments = {}
    for name, deadlines in profiles.items():
        experiments[name] = [[run_arm(mode, root/f"{name}-{index}-{mode}.json", deadlines, path, member, signed)
                             for mode in order] for index, order in enumerate(
                                 (("whole", "incremental"), ("incremental", "whole")), 1)]
    corrupt = [run_arm(mode, root/f"corrupt-{mode}.json", profiles["measured_tmpfs"], path, member, signed, corrupt=True)
               for mode in ("whole", "incremental")]
    end = ceiling.snapshot(path, ceiling.COMPRESSED, query)
    if (start["cached_pages"] != start["observed_file_pages"] or start["cached_pages"] != end["cached_pages"]
            or len({arm["packet_sha256"] for pair in experiments.values() for order in pair for arm in order}) != 1
            or corrupt[0]["dropped_stereo"] != 0 or corrupt[1]["dropped_stereo"] < 1):
        raise ValueError("Expected exactly one common seal and a rejected after-use replay")
    freeze(root / "receipt.json", dict(machine=machine, scope_sha256=SCOPE_PIN, archived_mixed_sha256=direct.PREFIX_PIN,
                        member=member, staged_source=str(path), new_original_reads=0, read_block_bytes=BLOCK,
                        arrival_ready_ns=profiles, measured_tmpfs_calibration=calibration, source_cache=[start, end],
                        cold_source_receipt_sha256=DIRECT_PIN, experiments=experiments, discarded=corrupt))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    run(parser.parse_args().root)
