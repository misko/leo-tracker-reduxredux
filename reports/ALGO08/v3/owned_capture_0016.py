"""Price both complete DS30-0016 capture writers on the same staged CI16 words."""

import argparse
import json
import os
from collections import Counter
from hashlib import sha256
from pathlib import Path
from runpy import run_path
from unittest.mock import patch

STAGE = Path("/dev/shm/leo-v3-guarded-selective-0016-stage01")
STAGE_PIN = "daaffec8a4e8d944db2989c108b547ee81ce38cb53b41344de38617d9a2a139a"
STRICT = Path("/dev/shm/leo-v3-strict-cairo-0016-result01")
STRICT_MAP_PIN = "3bf73850eb526bc909ed81c244eb16d6a81f8ea8ec8330ef08fd07be722666e5"
CODEC_PIN = "ed03bfb0d075d8e94c616a39f0d03ad05f79ab4b37df02cf1fca52127013557e"
MANIFESTS = (
    ("1530e4a7376f569f52d2b41dfdfc732489b036df73a8cff9b0feabecbc8cb3cc", 512, 8),
    ("48c9225baa0327877da41508a17ccca3175808670a174470142ecf228e1cc2a3", 296, 5),
)
WINDOWS, MEMBER_COUNT = 808, 13
ORDERS = (("ordinary", "packed"), ("packed", "ordinary"))
LOGICAL = ("chunk_index", "first_sequence", "window_count", "uncompressed_bytes",
           "uncompressed_sha256", "index_sha256")
ROOT_NAME = "capture-authority.json"
SCHEMA = "private-owned-0016-recording-envelope-v1"
MAX_BYTES = 3 * 1024**3


def checked(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"Unexpected authority digest: {path}")
    return data


def logical(chunks):
    return [{key: row[key] for key in LOGICAL} for row in chunks]


def validate_segments(segments, declared_windows):
    """Bind segment order, lifecycle and complete local member coverage."""
    first = 0
    for index, segment in enumerate(segments):
        chunks = segment["members"]
        if (index != segment["ordinal"] or first != segment["global_first"]
                or segment["directory"] != f"segment-{index:08d}" or not chunks):
            raise ValueError("Recording authority has reversed or omitted segments")
        if (segment["status"], bool(segment["failure"])) not in (
            ("complete", False), ("incomplete", True),
        ):
            raise ValueError("Recording authority changed the source lifecycle")
        local = 0
        for index, member in enumerate(chunks):
            if (member["chunk_index"] != index or member["first_sequence"] != local
                    or not 1 <= member["window_count"] <= 64):
                raise ValueError("Recording authority has incomplete member coverage")
            local += member["window_count"]
        if segment["windows"] != local:
            raise ValueError("Segment window count differs from its member coverage")
        first += local
    if first != declared_windows:
        raise ValueError("Recording window count differs from its segment coverage")


def segment_authority(index, first, reader, manifest_pin, chunks):
    header = reader.manifest
    source = [row.model_dump(mode="json") for row in header.chunks]
    if manifest_pin == reader.manifest_sha256 or logical(chunks) != logical(source):
        raise ValueError("A fresh capture must seal the original logical input with its own root")
    return dict(ordinal=index, global_first=first, directory=f"segment-{index:08d}",
                manifest_sha256=manifest_pin, original_manifest_sha256=reader.manifest_sha256,
                windows=header.window_count, status=header.status, failure=header.failure,
                stop_reason=header.stop_reason, members=list(chunks))


def ordinary_capture(path, header, windows):
    from leo.storage.short_window import ShortWindowReader, ShortWindowWriter

    writer = ShortWindowWriter(
        path.parent, path.name, configuration=header.configuration, radio=header.radio,
        receiver_ids=header.receiver_ids, chunk_windows=64, compression_level=1, schema_version=2,
    )
    try:
        for window in windows:
            row = window.index
            writer.append(sequence=row.sequence, target_id=row.target_id, samples=window.samples,
                          acquisition=row.acquisition, powers=row.powers)
        writer.finish(stop_reason=header.stop_reason, failure=header.failure)
    except BaseException:
        writer.abort()
        raise
    sealed = ShortWindowReader(path)
    if (sealed.manifest.status, sealed.manifest.stop_reason, sealed.manifest.failure) != (
        header.status, header.stop_reason, header.failure,
    ):
        raise ValueError("The ordinary writer changed the original recorder stop evidence")
    return sealed.manifest_sha256, [row.model_dump(mode="json") for row in sealed.manifest.chunks]


def hydrate(reader, ingress, paired, hasher):
    from leo.storage.short_window import ShortWindowReader

    allowed = {key: (size, pin) for chunk in reader.manifest.chunks for key, size, pin in (
        (chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256),
        (chunk.index_relative_path, chunk.index_bytes, chunk.index_sha256),
    )}
    opened = Counter()
    original = ShortWindowReader._member

    def scoped(source, name, size, pin):
        if source.path != reader.path or allowed.get(name) != (size, pin) or opened[name]:
            raise ValueError("Waveform read outside the exact staged segment")
        data = original(source, name, size, pin)
        opened[name] = len(data)
        return data

    with (patch.object(ShortWindowReader, "_member", scoped), ingress(), paired(hasher)):
        windows = tuple(reader.windows())
    if (len(windows) != reader.manifest.window_count
            or opened != {name: pair[0] for name, pair in allowed.items()}
            or any(w.samples.flags.writeable or w.samples.shape != (200_000, 2, 2) for w in windows)):
        raise ValueError("Expected complete original immutable stereo windows")
    return windows, dict(opened)


def verify_ports(roots, documents, pins, codec, ingress, paired, hasher):
    from leo.storage.fast_scan import FastScanStore, FastSegmentSource

    from .direct_packed_capture import Capture
    from .seekable_eight_raw import clocks, elapsed

    result = {}
    for mode, root in roots.items():
        start = clocks()
        authority = json.loads(checked(root / ROOT_NAME, pins[mode]))
        if authority != documents[mode]:
            raise ValueError("Archive recording envelope changed")
        validate_segments(authority["segments"], authority["windows"])
        scanner = FastScanStore(root)
        if mode == "ordinary":
            _, _, inventory = scanner.inventory(root, verify_windows=False)
            entries = inventory["segments"]
            expected_pins = [segment["manifest_sha256"] for segment in authority["segments"]]
            if [entry["manifest_digest"] for entry in entries] != expected_pins:
                raise ValueError("The released inventory rejected the ordinary capture authority")
            with ingress(), paired(hasher):
                hashes = [w.iq_sha256 for entry in entries for w in FastSegmentSource(entry).windows()]
            audits, compatibility = [], "accepted by released FastScanStore"
        else:
            try:
                scanner.inventory(root, verify_windows=False)
            except ValueError as error:
                if str(error) != "no sealed fast-scan segments":
                    raise
                compatibility = str(error)
            else:
                raise ValueError("The installed inventory unexpectedly recognized a private format")
            hashes, audits = [], []
            for segment in authority["segments"]:
                capture = Capture(root / segment["directory"], segment["manifest_sha256"], codec,
                                  reuse_prefix_sha=True)
                hashes.extend(window.iq_sha256 for window in capture.windows())
                if len(capture.audit) != len(segment["members"]):
                    raise ValueError("Private reader omitted a complete member")
                for audit, member in zip(capture.audit, segment["members"], strict=True):
                    if (audit["original_decoded_sha256"] != member["uncompressed_sha256"]
                            or audit["encoded_blocks"] != 2 * member["window_count"]
                            or audit["checks"]["full_checks"] != member["window_count"]):
                        raise ValueError("Private reader omitted an encoded or decoded check")
                audits.extend(capture.audit)
        result[mode] = dict(clock=elapsed(start), hashes=hashes, audit=audits,
                            released_compatibility=compatibility)
    return result


def compare_strict(roots, documents):
    folder = STRICT / "conversion"
    authority = json.loads(checked(folder / "map.json", STRICT_MAP_PIN))
    if authority["codec_sha256"] != "sha256:" + CODEC_PIN:
        raise ValueError("The replacement and derivative codecs differ")
    previous = {(row["manifest_sha256"], row["chunk_index"]): row for row in authority["members"]}
    matches = []
    for segment in documents["packed"]["segments"]:
        for member in segment["members"]:
            name = roots["packed"] / segment["directory"] / member["directory"]
            old = previous.pop((segment["original_manifest_sha256"], member["chunk_index"]))
            former = checked(folder / old["directory"] / "seek.json", old["seek_sha256"])
            current = checked(name / "seek.json", member["seek_sha256"])
            if json.loads(former)["records"] != json.loads(current)["records"]:
                raise ValueError("The durable writer changed strict packed payload commitments")
            matches.append(dict(member=member["chunk_index"], segment=segment["ordinal"],
                                prior_seek=old["seek_sha256"], current_seek=member["seek_sha256"]))
    if previous:
        raise ValueError("The direct writer did not reproduce every strict derivative member")
    return matches


def total_bytes(root):
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def run(output):
    from .empty_bootstrap import load_runtime

    _, spec, _, _, runtime = load_runtime()
    from leo.contracts.digests import canonical_digest
    from leo.storage.short_window import ShortWindowReader
    from leo.storage.writer import _fsync_directory
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes
    from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer

    from .aperture_trial import machine as current_machine
    from .ci16_packing import Packing
    from .direct_packed_capture import close_file, write_capture
    from .north_direct_multichunk import checked_lease, require_tmpfs
    from .seekable_eight_raw import clocks, elapsed
    from .sparse_cold_input import CACHE_LIBRARY, CACHE_SHA

    checked_lease()
    machine = current_machine()
    if (machine["cpu"] != [2] or machine["nice"] < 15 or "prio 7" not in machine["ionice"]
            or set(machine["threads"].values()) != {"1"} or os.environ.get("OMP_THREAD_LIMIT") != "1"):
        raise ValueError("Expected one low-priority Gauss core under the shared slot")
    custody = json.loads(checked(STAGE / "staging.json", STAGE_PIN))
    origin = STAGE / Path(custody["recording"]).name
    require_tmpfs(origin)
    if output.parent.resolve(strict=True) != Path("/dev/shm") or custody["case"] != "DS30-0016":
        raise ValueError("Expected the staged capture and a fresh tmpfs root")
    if len(tuple(origin.glob("*/manifest.json"))) != len(MANIFESTS):
        raise ValueError("Staged recording has unexpected segment coverage")
    library = STRICT / "packing.so"
    checked(library, CODEC_PIN)
    codec = Packing(library)
    checked(CACHE_LIBRARY, CACHE_SHA)
    cache_tools = Path(__file__).resolve().parents[3] / "tools/pipeline_eval/qualification/cache_residency.py"
    cache = run_path(str(cache_tools))
    query = cache["load_query"](CACHE_LIBRARY)
    hasher = Path(spec["paired_sha256"]["library"])
    roots = {mode: output / mode for mode in ORDERS[0]}
    output.mkdir(mode=0o700)
    for root in roots.values():
        root.mkdir(mode=0o700)
    documents = {mode: dict(schema=SCHEMA, mode=mode, windows=WINDOWS, segments=[])
                 for mode in roots}
    windows_sha, stages, first, upper = [], [], 0, 0
    for i, ((manifest_pin, count, chunks), order) in enumerate(zip(MANIFESTS, ORDERS, strict=True)):
        source = ShortWindowReader(origin / f"{origin.name}-segment-{i:08d}")
        header = source.manifest
        if (source.manifest_sha256 != "sha256:" + manifest_pin or count != header.window_count
                or chunks != len(header.chunks)):
            raise ValueError("Original segment differs from the staged signed custody")
        names = [(source.path, "manifest.json", (source.path / "manifest.json").stat().st_size)]
        for chunk in header.chunks:
            names.extend(((source.path, chunk.index_relative_path, chunk.index_bytes),
                          (source.path, chunk.payload_relative_path, chunk.compressed_bytes)))
        state = cache["cache_snapshot"](names, os.sysconf("SC_PAGE_SIZE"), query)
        if (state["observed_members"] != len(names) or state["unavailable"]
                or state["cached_pages"] != state["observed_file_pages"]):
            raise ValueError("Only the staged fully resident original bytes are allowed")
        start = clocks()
        owned, reads = hydrate(source, compressed_input_buffer, paired_decoded_hashes, hasher)
        hydrated = elapsed(start)
        if hydrated["input_blocks"]:
            raise ValueError("The staged waveform hydration charged external reads")
        decoded_bytes = sum(window.samples.nbytes for window in owned)
        if decoded_bytes + total_bytes(output) + 2 * sum(size for _, _, size in names) >= MAX_BYTES:
            raise ValueError("The paired output and owned source exceed the memory budget")
        visits = [window.index.acquisition["global_visit"] for window in owned]
        if visits != list(range(first, first + count)):
            raise ValueError("The full original global visit order changed")
        windows_sha.extend(window.index.iq_sha256 for window in owned)
        arm_clocks = {}
        for mode in order:
            path = roots[mode] / f"segment-{i:08d}"
            start = clocks()
            if mode == "ordinary":
                pin, current = ordinary_capture(path, header, owned)
            else:
                pin, private = write_capture(path, header, owned,
                                             tuple(row.window_count for row in header.chunks),
                                             codec, reuse_prefix_sha=True)
                current = private["chunks"]
            arm_clocks[mode] = elapsed(start)
            documents[mode]["segments"].append(segment_authority(i, first, source, pin, current))
        original = [row.model_dump(mode="json") for row in header.chunks]
        if original != documents["ordinary"]["segments"][-1]["members"]:
            raise ValueError("The ordinary writer did not reproduce the original compressed seals")
        upper = max(upper, decoded_bytes + total_bytes(output)
                    + max(chunk.compressed_bytes for chunk in header.chunks))
        if upper > MAX_BYTES:
            raise ValueError("The actual dual-format retained extent exceeded 3 GiB")
        del owned
        stages.append(dict(segment=i, order=order, hydrate=hydrated, reads=reads, cache=state,
                           decoded_bytes=decoded_bytes, writer=arm_clocks))
        first += count
    if (first != WINDOWS or canonical_digest([custody["inventory"], windows_sha]) != custody["raw_authority"]):
        raise ValueError("Exact staged recording authority did not reproduce")

    pins, commit_cost = {}, {}
    for mode, root in roots.items():
        validate_segments(documents[mode]["segments"], WINDOWS)
        start = clocks()
        pins[mode] = close_file(root / ROOT_NAME, documents[mode])
        _fsync_directory(root)
        _fsync_directory(output)
        commit_cost[mode] = elapsed(start)
    check = verify_ports(roots, documents, pins, codec, compressed_input_buffer,
                         paired_decoded_hashes, hasher)
    if any(row.pop("hashes") != windows_sha for row in check.values()):
        raise ValueError("A fresh archive did not independently reproduce every original window")
    strict_members = compare_strict(roots, documents)
    if len(strict_members) != MEMBER_COUNT:
        raise ValueError("Expected every strict derivative member")
    receipt = dict(case="DS30-0016", source_custody_sha256=STAGE_PIN, source=stages, runtime=runtime,
                   machine=machine, roots=pins, commit=commit_cost, readback=check,
                   documents=documents, owned_window_sha256=canonical_digest(windows_sha),
                   codec=codec.programme(), strict_member_commitments=strict_members,
                   max_accounted_iq_bytes=upper, storage={mode: total_bytes(root)
                                                         for mode, root in roots.items()},
                   worker_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    close_file(output / "receipt.json", receipt)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
