"""Compare cold v3 advice and a whole-member worker on a verified saved prefix."""

import argparse
from contextlib import closing, contextmanager
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import stat
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns, thread_time_ns
from unittest.mock import patch


PAYLOAD = Path("/opt/leo-algo08/algo08v3/payload")
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
BINDING = Path("/srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0008.json")
ARCHIVE = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/v3-bounds-DS30-0008-pair/baseline")
CACHE_LIBRARY = Path("/tmp/leo-algo08v2-2x-bench/ds30-cache-residency.so")
SPEC_SHA = "652f8573e2fdec746dd318849c82992eb7786f014e8dbc393c0352b54e421e46"
BINDING_SHA = "a9ced88711b3a8174e47f7a337e2d5a497642c81eb4a7b5c877c2402d607f77a"
MANIFEST_SHA = "5ffe3ed98feb37f7f7ada44dbf34d2af9d3fcadce567fd3cdbb7e31965a02759"
ARCHIVED_DETECTION_SHA = "2df28e68ea845576ea5e8a02057bce32983dbafb469fa2c4f710a3d89729fa85"
CACHE_SHA = "4f10e0a2e23121e184ee7d37767f55c29fefc158f4182a2dd99c4268ff2ce6ab"
PREFETCH_SHA = "05b3b619429e1e35c9e9f811b3a68e68df6a6f6b37e7c05338dccd91fb0db8cc"
RUNTIME = {
    "tools.algo08_scan": "573d6608597f1619785688769e7504a4ad8ac30dd71fecd37876c678ed4aca53",
    "tools.pipeline_eval.qualification.blind_compact_run":
        "2fd4596da78d6fd0a472b183c02e7636322eeb9cfb107d60df56424b38acfe85",
    "leo.storage.fast_scan": "db79b4e50c10a3b948c69c86a464fb57a226b0dbb2955cf90d8ae83db3f39527",
    "leo.storage.short_window": "0884ab7ca630d59dd041e50e0ef89cd847ca842c11097f8bde06b869645eafa2",
    "leo.scanner.fast_scan_analysis": "51f513ddeea44ca7caf3d8fd27988a9180f8f86078a3901804a0bc7ee351fe14",
    "tools.pipeline_eval.variants.experimental.paired_sha256":
        "95485b5598d9f003c87cf1475418a75fc82cfecbce8518f8279b4f124b61240f",
    "tools.pipeline_eval.variants.experimental.receiver_member_prefetch": PREFETCH_SHA,
}
EXPERIMENTAL = "tools/pipeline_eval/variants/experimental"
MEMBERS, WINDOWS_PER_MEMBER = 3, 64
WINDOWS = MEMBERS * WINDOWS_PER_MEMBER
MAX_COMPRESSED = 250_000_000
ORDERS = (("advice", "prefetch"), ("prefetch", "advice"))
SOURCE_DIR = Path("/srv/bulk/leo/fast-scan-recordings")


def verified(path, expected):
    content = path.read_bytes()
    if sha256(content).hexdigest() != expected.removeprefix("sha256:"):
        raise ValueError(f"Unexpected source digest: {path}")
    return content


def copy_bounded(source, destination, *, limit, expected_hash, exact_size=None):
    """Copy one bounded stream while authenticating the exact original bytes."""
    written, digest = 0, sha256()
    while block := source.read(min(1 << 20, limit - written + 1)):
        if written + len(block) > limit:
            raise ValueError("Private copy exceeds its frozen byte bound")
        digest.update(block)
        destination.write(block)
        written += len(block)
    if (exact_size is not None and written != exact_size
            or digest.hexdigest() != expected_hash.removeprefix("sha256:")):
        raise ValueError("Private copy differs from its authenticated source")
    return written


def source_member_name(name):
    path = Path(name)
    if path.name != name or name in ("", ".", ".."):
        raise ValueError("Expected a basename in the frozen segment")
    return name


def stage_file(original, destination, **kwargs):
    # The archived RF files are readable through the existing capture account.
    command = ["sudo", "-n", "-u", "leo", "cat", "--", str(original)]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL) as proc:
        with closing(proc.stdout), destination.open("xb") as out:
            try:
                size = copy_bounded(proc.stdout, out, **kwargs)
            except BaseException:
                proc.kill()
                raise
            out.flush()
            os.fsync(out.fileno())
        if proc.wait() != 0:
            raise RuntimeError(f"Read-only origin copy failed: {original.name}")
    return size


def copy_prefix(private, entry):
    from leo.contracts.multirate_window_recording import ShortWindowManifestV2

    original = Path(entry["path"])
    if (SOURCE_DIR not in original.parents or ".." in original.parts
            or entry["manifest_digest"] != "sha256:" + MANIFEST_SHA):
        raise ValueError("Unexpected original capture authority")
    segment = private / source_member_name(original.name)
    segment.mkdir(mode=0o700)
    manifest = segment / "manifest.json"
    stage_file(original / manifest.name, manifest, limit=1 << 20, expected_hash=MANIFEST_SHA)
    model = ShortWindowManifestV2.model_validate_json(verified(manifest, MANIFEST_SHA))
    chunks = tuple(model.chunks[:MEMBERS])
    if (len(chunks) != MEMBERS or model.sample_rate_hz != 10_000_000 or model.receiver_ids != (0, 1)
            or sum(chunk.compressed_bytes for chunk in chunks) > MAX_COMPRESSED
            or any((chunk.first_sequence, chunk.window_count, chunk.uncompressed_bytes) !=
                   (number * WINDOWS_PER_MEMBER, WINDOWS_PER_MEMBER, 102_400_000)
                   for number, chunk in enumerate(chunks))):
        raise ValueError("Unexpected signed member geometry")
    member_paths = []
    for chunk in chunks:
        for name, size, digest in (
            (chunk.index_relative_path, chunk.index_bytes, chunk.index_sha256),
            (chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256),
        ):
            base = source_member_name(name)
            stage_file(original / base, segment / base, limit=size, exact_size=size, expected_hash=digest)
        member_paths.append(segment / chunk.payload_relative_path)
    return dict(entry, path=str(segment)), chunks, tuple(member_paths)


def private_identity(path, root):
    if (root.resolve(strict=True) != root or root not in path.parents
            or root.stat().st_mode & 0o077 or root.stat().st_uid != os.getuid()):
        raise ValueError("Cold cache control requires an owner-private trial root")
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.getuid() or info.st_dev != root.stat().st_dev
            or path.resolve(strict=True) != path):
        raise ValueError("Cache control is limited to independent private file inodes")
    return info.st_dev, info.st_ino, info.st_size


def cache_pages(path, root, identity, query, *, cold):
    if private_identity(path, root) != identity:
        raise ValueError("The scope of private cache control changed")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino, info.st_size) != identity or info.st_nlink != 1:
            raise ValueError("Unexpected cache observation descriptor")
        if cold:
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
        return query(fd, info.st_size)
    finally:
        os.close(fd)


def expected_prefix(native, cutoff):
    return [row if row["visit_index"] < cutoff else dict(row, candidates=[])
            for row in native["source"]["probes"] if row["visit_index"] < WINDOWS]


def frozen_function(spec, file, function):
    path = PAYLOAD / EXPERIMENTAL / file
    body = verified(path, spec["sources"][f"{EXPERIMENTAL}/{file}"])
    bindings = {"__name__": __name__, "__file__": str(path)}
    exec(compile(body, str(path), "exec"), bindings)
    return bindings[function]


def io_snapshot():
    return {key: int(value) for key, value in
            (line.split(":", 1) for line in Path("/proc/self/io").read_text().splitlines())}


def measure(arm, assets, hasher, spec, scoped_entry, native, inventory_digest, compressed_bytes, *, buffer, advice):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastSegmentSource
    from tools import algo08_scan
    from tools.pipeline_eval.qualification import blind_compact_run as blind
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes
    from tools.pipeline_eval.variants.experimental.receiver_member_prefetch import compressed_member_prefetch
    from .first_third_ingress import admitted_prefix

    histories, callbacks, digests = [], [], []
    plan = None
    stock_detector = algo08_scan.detector
    stock_history = blind.Continuation

    class Bounded(FastSegmentSource):
        def __init__(self, entry):
            super().__init__(entry, stop_sequence=WINDOWS)

        def windows(self):
            with closing(super().windows()) as stream:
                for window in stream:
                    digests.append(window.iq_sha256)
                    yield window

    def continuation():
        history = stock_history()
        histories.append(history)
        return history

    @contextmanager
    def detector(*args, **kwargs):
        with stock_detector(*args, **kwargs) as stock:
            history, = histories

            def visit(window):
                index = window.acquisition["global_visit"]
                paid = index < plan.cutoff
                cpu = thread_time_ns()
                if paid:
                    rows = stock(window)
                else:
                    rows = [blind._probe(window, lane, []) for lane in window.receiver_ids]
                    for probe in rows:
                        history.select(probe)
                callbacks.append((index, paid, thread_time_ns() - cpu))
                return rows

            yield visit

    forecast = advice if arm == "advice" else compressed_member_prefetch
    before_io = io_snapshot()
    before = resource.getrusage(resource.RUSAGE_SELF)
    cpu, wall = process_time_ns(), perf_counter_ns()
    with (buffer(), paired_decoded_hashes(hasher), forecast() as overlap,
          patch.object(algo08_scan, "detector", detector),
          patch.object(algo08_scan, "FastSegmentSource", Bounded),
          patch.object(blind, "Continuation", continuation),
          patch.dict(algo08_scan.PINS, {"cancellation-factors.so": spec["detector_sha256"]})):
        plan_start = thread_time_ns()
        plan = admitted_prefix([scoped_entry], [WINDOWS])
        plan_cpu = thread_time_ns() - plan_start
        doc = algo08_scan.acquire(native["source"]["session_id"], inventory_digest,
                                  dict(segments=[scoped_entry], window_count=WINDOWS), assets)
    cpu_ns, wall_ns = process_time_ns() - cpu, perf_counter_ns() - wall
    after_io = io_snapshot()
    after = resource.getrusage(resource.RUSAGE_SELF)
    expected = expected_prefix(native, plan.cutoff)
    source = doc["source"]
    raw = canonical_digest([inventory_digest, digests])
    selected = [row for row in source["probes"] if row["candidates"]]
    if (len(digests) != WINDOWS or source["probes"] != expected or source["raw_recording_authority_digest"] != raw
            or doc["clock_anchor"] != native["clock_anchor"] or doc["delivery_clocks"] != native["delivery_clocks"][:WINDOWS]
            or doc["provenance"]["excluded_windows"] !=
            [row for row in native["provenance"]["excluded_windows"] if row["visit"] < WINDOWS]
            or source["analysis_manifest_sha256"] != canonical_digest([
                "cancellation", raw, spec["detector_sha256"], expected])
            or (plan.count, plan.admitted, plan.keep, plan.cutoff, len(selected)) != (192, 192, 64, 64, 19)
            or [index for index, _, _ in callbacks] != list(range(WINDOWS))
            or sum(paid for _, paid, _ in callbacks) != plan.keep):
        raise ValueError("Verified input, emitted probes or paying cutoff differs from the frozen archive")
    input_blocks = after.ru_inblock - before.ru_inblock
    delta_io = {key: after_io[key] - value for key, value in before_io.items()}
    return dict(arm=arm, cpu_ns=cpu_ns, wall_ns=wall_ns, overlap=asdict(overlap),
                resource_input_blocks=input_blocks, process_io_delta=delta_io,
                effective_compressed_MB_per_s=compressed_bytes * 1000/wall_ns,
                charged_MB_per_s=delta_io["read_bytes"] * 1000/wall_ns,
                plan_cpu_ns=plan_cpu, callback_cpu_ns=sum(time for _, _, time in callbacks),
                paid_callback_cpu_ns=sum(time for _, paid, time in callbacks if paid),
                visits=plan.count, paid_visits=plan.keep, emitted_probes=len(expected),
                selected=len(selected), selected_sha256=canonical_digest(selected),
                selected_probe_keys=[[r["visit_index"], r["receiver_id"]] for r in selected],
                probes_sha256=canonical_digest(expected), raw_authority=raw,
                clock_sha256=canonical_digest(doc["delivery_clocks"]),
                acquisition_sha256=canonical_digest(doc))


def run(parent):
    from importlib import import_module
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.cache_residency import load_query, pages
    from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256
    from .scout_readout_trial import PILOT_SHA, check_machine

    machine = check_machine()
    parent = parent.resolve(strict=True)
    if Path("/srv/bulk/leo-dev") not in (parent, *parent.parents):
        raise ValueError("Use the local research XFS staging area")
    fs = subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", parent], text=True).strip()
    if fs != "xfs":
        raise ValueError("Expected local XFS")
    spec = json.loads(verified(PAYLOAD / "spec.json", SPEC_SHA))
    for name, expected in RUNTIME.items():
        verified(Path(import_module(name).__file__), expected)
    receiver, hasher = PAYLOAD / "receiver.so", PAYLOAD / "paired-sha256.so"
    verified(receiver, spec["detector_sha256"])
    verified(hasher, spec["paired_sha256"]["sha256"])
    if not PairedSha256(hasher).hardware:
        raise ValueError("Expected hardware paired SHA-256")
    verified(CACHE_LIBRARY, CACHE_SHA)
    query = load_query(CACHE_LIBRARY)
    buffer = frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    advice = frozen_function(spec, "receiver_member_lookahead.py", "compressed_member_lookahead")
    native_path, = (ARCHIVE / "fast-scan-automatic-work").glob("*/detections.json")
    native = json.loads(verified(native_path, ARCHIVED_DETECTION_SHA))
    session = native["source"]["session_id"]
    inventory = json.loads((ARCHIVE / "fast-scan-inputs" / f"{session}.json").read_bytes())
    inventory_hash = canonical_digest(inventory)
    first = inventory["segments"][0]
    binding = json.loads(verified(BINDING, BINDING_SHA))["case"]["recording"]["segments"][0]
    if (inventory_hash != native["source"]["input_manifest_sha256"]
            or Path(first["path"]) / "manifest.json" != Path("/srv/bulk") / binding["path"]
            or first["manifest_digest"] != "sha256:" + binding["sha256"]):
        raise ValueError("Expected original input inventory matching the signed native archive")
    with TemporaryDirectory(dir=parent, prefix="leo-private-sparse-cold-") as tmp:
        private = Path(tmp)
        scoped, chunks, members = copy_prefix(private, first)
        identities = tuple(private_identity(path, private) for path in members)
        compressed = sum(chunk.compressed_bytes for chunk in chunks)
        expected_pages = [pages(chunk.compressed_bytes, os.sysconf("SC_PAGE_SIZE")) for chunk in chunks]
        assets = private / "assets"
        assets.mkdir()
        (assets / "cancellation-factors.so").symlink_to(receiver)
        pilot = RELEASE / "assets/lower.f32"
        verified(pilot, PILOT_SHA["lower"])
        (assets / "lower.f32").symlink_to(pilot)
        pairs = []
        for order in ORDERS:
            pair = []
            for arm in order:
                before = [cache_pages(file, private, info, query, cold=True)
                          for file, info in zip(members, identities, strict=True)]
                if any(before):
                    raise ValueError("Private payload pages remained resident")
                row = measure(arm, assets, hasher, spec, scoped, native, inventory_hash, compressed,
                              buffer=buffer, advice=advice)
                row["start_cache_pages"] = before
                row["end_cache_pages"] = [cache_pages(file, private, info, query, cold=False)
                                          for file, info in zip(members, identities, strict=True)]
                read = row["overlap"]
                if arm == "prefetch" and (read["submitted"], read["hits"], read["hit_bytes"], read["fallback"]) != (
                        MEMBERS-1, MEMBERS-1, sum(chunk.compressed_bytes for chunk in chunks[1:]), 0):
                    raise ValueError("The async worker did not supply both original expected members")
                if arm == "advice" and (read["submitted"], read["submitted_bytes"]) != (MEMBERS-1, 2 * 16*1024**2):
                    raise ValueError("The released advisory arm did not issue both capped hints")
                pair.append(row)
            pairs.append(pair)
        flat = [row for pair in pairs for row in pair]
        for field in ("acquisition_sha256", "raw_authority", "probes_sha256", "selected_sha256"):
            if len({row[field] for row in flat}) != 1:
                raise ValueError(f"Matched arms differed at {field}")
        return dict(machine=machine, filesystem=fs, kernel=os.uname().release, orders=ORDERS,
                    specification_sha256=SPEC_SHA, reader_sha256=RUNTIME, manifest_sha256=MANIFEST_SHA,
                    archived_stock_sha256=ARCHIVED_DETECTION_SHA, inventory_sha256=inventory_hash,
                    cache_library_sha256=CACHE_SHA, compressed_bytes=compressed,
                    decoded_bytes=sum(chunk.uncompressed_bytes for chunk in chunks),
                    selected_verified_index_and_payloads=[chunk.model_dump(mode="json") for chunk in chunks],
                    expected_payload_pages=expected_pages, runs=pairs, expected_prefix_paid=64,
                    timed_logical_compressed_bytes=compressed * len(flat), staging_copy_compressed_bytes=compressed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parent", type=Path, nargs="?", default=Path("/srv/bulk/leo-dev"))
    print(json.dumps(run(parser.parse_args().parent), indent=2, allow_nan=False))
