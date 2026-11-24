"""Bounded offline North comparison from owned words to a complete published fix."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
from runpy import run_path
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
LEASE = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
SOURCE = Path("/tmp/leo-regional-qZJKBw4W/public/0abe7b4514be674d9f5388e3")
MANIFEST = "0205ca2d10c1282f6c782c93a32d2bff1ae8a7b39ff959c93b4ca3613f0f07eb"
ARCHIVE = SOURCE.parent / "tle"
OFFER = Path("/tmp/leo-algo08v2-2x-bench/near-edge") / (SOURCE.name + ".json")
OFFER_PIN = "f4ff743e9f3d00bc18344143bffaaf7801276018dbd75b6ab2ec5207e887e891"
ARCHIVE_PIN = "sha256:7aa06cab0502bcac70645a41a219bb6d53f1077f329e6f7ed79eb59a8794feec"
LEAN_BINDING = "95567204662af5ab6105f36c3d9e70b54b20bd32ef1e862cb354c547b72c141c"
NAMED = Path("/dev/shm/leo-current-north-v3-control-01/stock")
PYTHON_ARGS = ("-B", "-m", "reports.ALGO08.v3.north_direct_multichunk")


def checked_lease():
    import fcntl

    # The parent flock process must hold this slot for the entire command.
    with LEASE.open("rb") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
    raise ValueError("Take the shared Gauss lease before processing samples")


def owned_inputs(smoke, spec):
    import empty_bootstrap as installed
    from leo.storage.short_window import ShortWindowReader
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

    from .seekable_eight_raw import clocks, elapsed
    from .sparse_cold_input import CACHE_LIBRARY, CACHE_SHA, frozen_function

    source = ShortWindowReader(SOURCE)
    if (SOURCE.resolve(strict=True) != SOURCE or source.manifest_sha256 != "sha256:"+MANIFEST
            or source.manifest.window_count != 1200 or len(source.manifest.chunks) != 19):
        raise ValueError("Expected the exact resident North simulation")
    chunks = source.manifest.chunks[:1] if smoke else source.manifest.chunks
    by_name = {}
    for chunk in chunks:
        by_name[chunk.index_relative_path] = chunk.index_bytes, chunk.index_sha256
        by_name[chunk.payload_relative_path] = chunk.compressed_bytes, chunk.compressed_sha256
    files = {name: pair[0] for name, pair in by_name.items()}
    require_tmpfs(SOURCE)
    files_and_root = files | {"manifest.json": (SOURCE/"manifest.json").stat().st_size}
    cache = run_path(str(HERE.parents[2]/"tools/pipeline_eval/qualification/cache_residency.py"))
    installed.checked(CACHE_LIBRARY, CACHE_SHA)
    query = cache["load_query"](CACHE_LIBRARY)
    observed = cache["cache_snapshot"]([(SOURCE, name, size) for name, size in files_and_root.items()],
                                       os.sysconf("SC_PAGE_SIZE"), query)
    if (observed["unavailable"] or observed["observed_members"] != len(files_and_root)
            or observed["cached_pages"] != observed["observed_file_pages"]):
        raise ValueError("Only fully resident original simulation pages are admitted")
    original = ShortWindowReader._member
    opened = Counter()

    def scoped(reader, name, size, pin):
        if reader.path != SOURCE or by_name.get(name) != (size, pin) or name in opened:
            raise ValueError("Unexpected source read during rehearsal preparation")
        data = original(reader, name, size, pin)
        opened[name] += len(data)
        return data

    suite = spec["paired_sha256"]
    hasher = Path(suite["library"])
    installed.checked(hasher, suite["sha256"])
    start = clocks()
    total = sum(chunk.window_count for chunk in chunks)
    with (patch.object(ShortWindowReader, "_member", scoped),
          frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")(), paired_decoded_hashes(hasher)):
        owned = tuple(source.windows(stop_sequence=total))
    cost = elapsed(start)
    if (opened != files or len(owned) != total or any(w.samples.flags.writeable or w.samples.shape != (200_000, 2, 2)
                                                     for w in owned)):
        raise ValueError("Rehearsal must share the actual complete, immutable CI16 windows")
    return source.manifest, chunks, owned, dict(clock=cost, resident=observed,
                                                               total_bytes=sum(w.samples.nbytes for w in owned),
                                                               original_reads=dict(opened))


def ordinary_capture(root, header, owned):
    from leo.storage.short_window import ShortWindowReader, ShortWindowWriter

    writer = ShortWindowWriter(root.parent, root.name, configuration=header.configuration, radio=header.radio,
                               receiver_ids=header.receiver_ids, chunk_windows=64, compression_level=1, schema_version=2)
    try:
        for w in owned:
            row = w.index
            writer.append(sequence=row.sequence, target_id=row.target_id, samples=w.samples,
                          acquisition=row.acquisition, powers=row.powers)
        reader = ShortWindowReader(writer.finish(stop_reason=header.stop_reason))
    except BaseException:
        writer.abort()
        raise
    if reader.path != root or reader.manifest.window_count != len(owned):
        raise ValueError("Ordinary writer did not seal the new requested recording")
    return reader.manifest_sha256, tuple(row.model_dump(mode="json") for row in reader.manifest.chunks)


def require_tmpfs(path):
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", str(path)], text=True).strip() != "tmpfs":
        raise ValueError(f"Expected tmpfs: {path}")


def publish_authority(arm_root, payload, pin, chunks, original, kind):
    from leo.storage.writer import _fsync_directory

    from .direct_packed_capture import close_file

    fields = ("chunk_index", "first_sequence", "window_count", "uncompressed_bytes", "uncompressed_sha256", "index_sha256")
    expected = [{key: getattr(row, key) for key in fields} for row in original]
    if [{key: row[key] for key in fields} for row in chunks] != expected or pin == "sha256:"+MANIFEST:
        raise ValueError("Each emitter must seal its own payload and all original logical raw/index fields")
    receipt = dict(kind=kind, schema="private-owned-north-publication-v1", recording=str(payload), archive_sha256=pin,
                   members=list(chunks), logical_members=expected)
    path = arm_root/"capture-authority.json"
    binding = close_file(path, receipt)
    _fsync_directory(arm_root)
    return receipt | {"binding_sha256": binding}


@contextmanager
def packed_port(open_capture):
    import empty_bootstrap as installed

    original = installed.staged_scanner
    opened = []

    class Segment:
        def __init__(self, entry, **scope):
            source = opened[0].segment(entry, **scope)
            self.reader = source.reader
            self.receiver_ids = source.receiver_ids
            self.radio = source.radio

        def windows(self):
            yield from opened[0].windows()

    def scanner(*args, **options):
        scan = original(*args, **options)
        if opened:
            raise ValueError("Expected one private packed scanner instance")
        opened.append(open_capture())
        stack.enter_context(patch.object(scan.FastScanStore, "inventory", inventory))
        scan.FastSegmentSource = Segment
        return scan

    def inventory(_store, recording, *, verify_windows=True):
        return opened[0].inventory(recording, verify_windows=verify_windows)

    with ExitStack() as stack:
        stack.enter_context(patch.object(installed, "staged_scanner", scanner))
        yield opened


def packed_child(recording, pin, codec, audit, argv):
    import combined_raw_research

    def open_capture():
        from .ci16_packing import Packing
        from .direct_packed_capture import Capture

        return Capture(recording, pin, Packing(codec))

    with packed_port(open_capture) as opened:
        combined_raw_research.main(argv)
    capture, = opened
    from .direct_packed_capture import close_file

    members = capture.document["chunks"]
    if (len(capture.audit) != len(members) or any(
            row["checks"]["full_checks"] != member["window_count"]
            or row["checks"]["decoded_bytes"] != member["uncompressed_bytes"]
            or row["encoded_blocks"] != 2*member["window_count"]
            for row, member in zip(capture.audit, members, strict=True))):
        raise ValueError("Publication did not complete independent packed readback")
    close_file(audit, dict(root_sha256=pin, members=capture.audit))


def bind_command(recording, output):
    from empty_bootstrap import checked
    from north_strict_read import LEAN

    command = json.loads(checked(LEAN/"binding.json", LEAN_BINDING))["command"]
    args = command[6:]
    for flag, previous, value in (("--recording", str(SOURCE), recording),
                                  ("--output", str(LEAN/"containing"), output)):
        offset = args.index(flag)+1
        if args[offset] != previous:
            raise ValueError("The source benchmark control unexpectedly changed")
        args[offset] = str(value)
    if (Path(command[5]).name != "combined_raw_research.py" or args[args.index("--archive")+1] != str(ARCHIVE)
            or args[args.index("--region")+1] != str(OFFER) or "--research-adaptive-position-map" not in args):
        raise ValueError("Expected the pinned 20/8 two-scan adaptive publication")
    return command[:4], args


IDENTITY = ("session_id", "input_manifest_sha256", "analysis_manifest_sha256", "raw_recording_authority_digest")


def normalized_native(packet):
    return {**packet, "provenance": {k: v for k, v in packet["provenance"].items() if k != "run_id"},
            "source": {k: v for k, v in packet["source"].items() if k not in IDENTITY}}


def check_native_authority(packet, inventory_path, root_pin, hashes):
    from leo.contracts.digests import canonical_digest

    source = packet["source"]
    raw = inventory_path.read_bytes()
    pin = "sha256:"+sha256(raw).hexdigest()
    inventory = json.loads(raw)
    if (inventory["segments"][0]["manifest_digest"] != root_pin or inventory["window_count"] != len(hashes)
            or source["session_id"] != "fast-"+pin[7:39] or source["input_manifest_sha256"] != pin
            or source["raw_recording_authority_digest"] != canonical_digest([pin, hashes])):
        raise ValueError("Signed packet does not bind the new capture and all original verified windows")


def smoke_run(root, source, original, owned, spec, sources, codec):
    from empty_bootstrap import bind_native
    from full_short_run import EIGHT_MS_SHA
    from leo.contracts.digests import canonical_digest
    from mixed_aperture_receiver import MixedApertureDetector
    from unified_short_bootstrap import receiver_import
    import empty_bootstrap as installed

    from .direct_packed_capture import Capture, write_capture
    from .seekable_eight_raw import SHORT, pinned_runtime, receive

    chunk, = original
    entry = dict(scope="one original North member", path=str(SOURCE), manifest_digest="sha256:"+MANIFEST, windows=64)
    scope, _, _ = pinned_runtime(root, spec, sources, codec.binary)
    stock, old = receive(entry, chunk.model_dump(mode="json"), "ordinary", scope)
    path = root/"packed"
    pin, packed = write_capture(path, source, owned, (64,), codec)
    seal = publish_authority(root, path, pin, packed["chunks"], original, "packed")
    capture = Capture(path, pin, codec)
    session, digest, inventory = capture.inventory(path)
    mixer = MixedApertureDetector(SHORT, EIGHT_MS_SHA, full_coverage=True)
    with (packed_port(lambda: capture), receiver_import(installed.RECEIVER.removesuffix(".py").replace("/", "."), scope.symbols)):
        scanner = installed.staged_scanner(sources, detector=mixer.detector)
        scanner.PINS["cancellation-factors.so"] = scope.detector[7:]
        actual = scanner.acquire(session, digest, inventory, scope.assets)
    bind_native(actual, session, digest, scope.detector[7:])
    hashes = [w.index.iq_sha256 for w in owned]
    if (normalized_native(actual) != normalized_native(stock)
            or actual["source"]["raw_recording_authority_digest"] != canonical_digest([digest, hashes])
            or capture.audit[0]["checks"]["full_checks"] != 64):
        raise ValueError("Packed source smoke did not reproduce signed original 20/8 opportunities")
    return dict(ordinary=old, packed=capture.audit, custody=seal, normalized_native_sha256=canonical_digest(normalized_native(actual)))


def run(root, smoke=False):
    from empty_bootstrap import BASELINE, RELEASE, checked, load_runtime

    checked_lease()
    _, spec, sources, _, _ = load_runtime()
    from aperture_trial import archive_identity, machine
    from full_short_physical import environment

    from .ci16_packing import Packing, SOURCE as CODEC_SOURCE
    from .direct_packed_capture import write_capture
    from .seekable_eight_raw import BUILD, clocks, elapsed

    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or set(host["threads"].values()) != {"1"} or os.environ.get("OMP_THREAD_LIMIT") != "1"):
        raise ValueError("Use one Gauss core and one numerical thread under the shared low-priority slot")
    if not root.is_absolute() or root.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Use a fresh absolute local tmpfs experiment root")
    if not smoke:
        checked(OFFER, OFFER_PIN)
        require_tmpfs(ARCHIVE)
        require_tmpfs(OFFER)
        archive = archive_identity(ARCHIVE)
        if archive["snapshots_sha256"] != ARCHIVE_PIN:
            raise ValueError("The exact causal North TLE archive changed")
        binary = json.loads(subprocess.check_output([str(BASELINE), "--verify"], text=True, timeout=60))
        if binary["version"] != "ALGO08v3" or binary["detector_sha256"] != spec["detector_sha256"]:
            raise ValueError("Expected installed named v3")
    root.mkdir()
    codec_path = root/"packing.so"
    subprocess.run([*BUILD, str(CODEC_SOURCE), "-o", str(codec_path)], check=True)
    codec = Packing(codec_path)
    header, original, owned, prepare = owned_inputs(smoke, spec)
    if smoke:
        result = smoke_run(root, header, original, owned, spec, sources, codec)
        (root/"smoke.json").write_text(json.dumps(dict(host=host, prepare=prepare, result=result), allow_nan=False)+"\n")
        return

    def child_cpu():
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        return usage.ru_utime+usage.ru_stime

    (root/"fonts").mkdir()
    (root/"tmp").mkdir()
    env = environment(root)
    python = RELEASE/"venv/bin/python"
    env["PYTHONPATH"] = os.pathsep.join(map(str, (HERE.parents[2], HERE, RELEASE/"src", RELEASE)))
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   check=True, timeout=25, env=env)
    per_arm = {}
    for kind in ("ordinary", "packed"):
        arm = root/kind
        arm.mkdir()
        capture, output = arm/"recording", arm/"publication"
        if kind == "ordinary":
            output.mkdir()
        base, args = bind_command(capture, output)
        begin, before = clocks(), child_cpu()
        if kind == "ordinary":
            pin, chunks = ordinary_capture(capture, header, owned)
            command = [str(BASELINE), "--recording", str(capture), "--archive", str(ARCHIVE),
                       "--region", str(OFFER), "--bulk-root", str(output)]
        else:
            pin, document = write_capture(capture, header, owned, tuple(row.window_count for row in original), codec)
            chunks = document["chunks"]
            command = [*base, *PYTHON_ARGS, "child", str(capture), "--pin", pin, "--codec", str(codec_path),
                       "--audit", str(arm/"verified-readback.json"), "--", *args]
        capture_authority = publish_authority(arm, capture, pin, chunks, original, kind)
        writer = elapsed(begin)
        with (arm/"stdout").open("xb") as out, (arm/"stderr").open("xb") as err:
            launched = clocks()
            child = subprocess.run(command, env=env, stdout=out, stderr=err, timeout=98)
            publication = elapsed(launched) | {"child_cpu_s": child_cpu()-before, "exit_code": child.returncode}
            total = elapsed(begin)
        per_arm[kind] = dict(capture=writer, publication=publication, total=total | {"cpu_ns": total["cpu_ns"]+round(1e9*publication["child_cpu_s"])},
                             authority=capture_authority, command=command, emitted_bytes=sum(p.stat().st_size for p in capture.rglob("*") if p.is_file()))
        result = dict(host=host, prepare=prepare, archive=archive, offer_sha256=OFFER_PIN, arms=per_arm,
                      owned_window_sha256=[w.index.iq_sha256 for w in owned], codec=codec.programme())
        (root/"timing.json").write_text(json.dumps(result, allow_nan=False)+"\n")
        if child.returncode:
            raise ValueError((arm/"stderr").read_text()[-2500:])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("smoke", "run", "child"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--pin")
    parser.add_argument("--codec", type=Path)
    parser.add_argument("--audit", type=Path)
    private, forwarded = parser.parse_known_args()
    if private.action == "child":
        if not forwarded or forwarded[0] != "--":
            parser.error("Forward the authentic combined publication arguments after --")
        packed_child(private.root, private.pin, private.codec, private.audit, forwarded[1:])
    else:
        if forwarded:
            parser.error(f"Unexpected arguments: {forwarded}")
        run(private.root, smoke=private.action == "smoke")
