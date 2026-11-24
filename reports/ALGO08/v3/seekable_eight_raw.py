"""Verified seekable input to the unchanged signed native 20/8 ms acquisition."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager, nullcontext
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import seekable_member as seek
from mixed_aperture_receiver import NativePath


SHORT = Path("/var/tmp/leo-v3-eight-ms-build-padded/8ms/short-primary.so")
DENSE = Path("/dev/shm/leo-seekable-member-0008-case1/result.json")
DENSE_SHA = "b1f310a05ade750be8e6dbf09f455baa27b71cb7dcd03334130a285a852d6cd6"
HELD = Path("/dev/shm/leo-receiver-ceiling-0169-results01/scope.json")
HELD_SHA = "95a438f0904e4568b6f2a3618b7fbf691c29d0e2d352fd3727cc83d35b72aa9a"
ORDERS = (("ordinary", "complete_encoded", "on_demand"), ("on_demand", "complete_encoded", "ordinary"))
PREFIX = seek.EIGHT_MS_SAMPLES
TRANSFER_CPU_MS = 25


class CommittedSamples:
    """Logical source shape with no raw data pointer until a checked engine requests a real array."""

    dtype = np.dtype("<i2")
    flags = SimpleNamespace(c_contiguous=True)
    shape = (seek.SAMPLES, 2, 2)

    def __init__(self, reader, sequence, loads):
        self.reader, self.sequence, self.loads = reader, sequence, loads
        self.full = self.samples = None

    def realize(self, full):
        if self.samples is None:
            raw = self.reader.read(self.sequence, full=full)
            self.full = full
            self.samples = np.frombuffer(raw, dtype=self.dtype).reshape(seek.SAMPLES if full else PREFIX, 2, 2)
            self.loads[self.sequence] = "full" if full else "short_primary"
        elif full != self.full:
            raise ValueError("The fixed visit cannot switch its declared native aperture")
        return self.samples


@contextmanager
def original_member_only(entry, chunk, counters):
    from leo.storage.short_window import ShortWindowReader

    allowed = {chunk[f"{kind}_relative_path"]: (chunk[extent], chunk[pin]) for kind, extent, pin in (
        ("payload", "compressed_bytes", "compressed_sha256"), ("index", "index_bytes", "index_sha256"))}
    stock = ShortWindowReader._member

    def member(reader, name, size, wanted):
        if reader.path != Path(entry["path"]) or allowed.get(name) != (size, wanted):
            raise ValueError("Waveform access lies outside the authenticated local one-member scope")
        value = stock(reader, name, size, wanted)
        counters[name] += size
        return value

    with patch.object(ShortWindowReader, "_member", member):
        yield


@contextmanager
def member_source(scan, entry, chunk, reader, loads):
    original = scan.FastSegmentSource
    call = NativePath.run

    def with_aperture(engine, samples, lane, center):
        if type(samples) is not CommittedSamples or engine.maximum not in (1, 2):
            raise ValueError("The derivative requires the checked full or 8 ms native engines")
        return call(engine, samples.realize(full=engine.maximum == 2), lane, center)

    class Member(original):
        def __init__(self, value):
            if value != entry:
                raise ValueError("The packed input provider is bound to one original segment")
            super().__init__(value, stop_sequence=chunk["window_count"])
            if self.reader.manifest.chunks[0].model_dump(mode="json") != chunk:
                raise ValueError("The original complete-member extent changed")
            if reader is not None and (reader.manifest_sha256 != self.manifest_digest
                    or reader.chunk.model_dump(mode="json") != chunk or any(r.target_id not in self.targets for r in reader.rows)):
                raise ValueError("The rooted object is bound to a different original manifest, target or member")

        def windows(self):
            if reader is None:
                yield from super().windows()
                return
            # The manifest and index bind the complete logical signal geometry.
            # Invalid captures never request a buffer from either C engine.
            for row in reader.rows:
                yield SimpleNamespace(
                    acquisition=row.acquisition, target=self.targets[row.target_id], receiver_ids=self.receiver_ids,
                    sample_rate_hz=reader.manifest.sample_rate_hz, iq_sha256=row.iq_sha256,
                    samples=CommittedSamples(reader, row.sequence, loads),
                )

    with patch.object(scan, "FastSegmentSource", Member):
        with (patch.object(NativePath, "run", with_aperture) if reader is not None else nullcontext()):
            yield


def clocks():
    use = resource.getrusage(resource.RUSAGE_SELF)
    return process_time_ns(), perf_counter_ns(), use.ru_inblock, use.ru_majflt


def elapsed(start):
    return dict(zip(("cpu_ns", "wall_ns", "input_blocks", "major_faults"),
                    (a - b for a, b in zip(clocks(), start, strict=True)), strict=True))


def source(case):
    from empty_bootstrap import checked

    if case == "DS30-0008":
        doc = json.loads(checked(DENSE, DENSE_SHA))
        return doc["source"], doc["original_member"]
    doc = json.loads(checked(HELD, HELD_SHA))
    return doc["entry"], doc["member"]


def residency(entry, chunk):
    from empty_bootstrap import checked
    from full_short_physical import CACHE_LIB, CACHE_SHA
    from next_resident_8ms import fully_resident
    from tools.pipeline_eval.qualification.cache_residency import cache_snapshot, load_query

    segment = Path(entry["path"])
    if segment.resolve(strict=True) != segment or segment.stat().st_dev != Path("/dev/shm").stat().st_dev:
        raise ValueError("Use only the already staged private tmpfs original")
    checked(CACHE_LIB, CACHE_SHA)
    checks = [(segment, "manifest.json", (segment/"manifest.json").stat().st_size),
              (segment, chunk["index_relative_path"], chunk["index_bytes"]),
              (segment, chunk["payload_relative_path"], chunk["compressed_bytes"])]
    census = cache_snapshot(checks, os.sysconf("SC_PAGE_SIZE"), load_query(CACHE_LIB))
    if not fully_resident(census) or census["members"] != 3:
        raise ValueError(f"Not all pinned source metadata and waveform bytes are resident: {census}")
    return census


def receive(root, entry, chunk, mode, objects):
    from empty_bootstrap import bind_native, staged_scanner
    from full_short_run import EIGHT_MS_SHA
    from leo.contracts.digests import canonical_digest
    from mixed_aperture_receiver import MixedApertureDetector
    from unified_short_bootstrap import receiver_import
    import empty_bootstrap as staged

    if mode not in ORDERS[0]:
        raise ValueError("Unrecognized verification boundary")
    scope = objects
    pin, loads, originals = scope.detector, {}, Counter()
    inventory = dict(segments=[entry], window_count=chunk["window_count"])
    inventory_digest = canonical_digest(inventory)
    session = "fast-" + inventory_digest[7:39]
    start = clocks()
    with ExitStack() as stack:
        mixer = MixedApertureDetector(SHORT, EIGHT_MS_SHA, full_coverage=True)
        scan = staged_scanner(scope.sources, detector=mixer.detector)
        scan.PINS["cancellation-factors.so"] = pin[7:]
        scanner_name = staged.RECEIVER.removesuffix(".py").replace("/", ".")
        stack.enter_context(receiver_import(scanner_name, scope.symbols))
        stack.enter_context(original_member_only(entry, chunk, originals))
        before_reader = clocks()
        reader = None
        encoded = None
        if mode == "ordinary":
            stack.enter_context(scope.buffer())
            stack.enter_context(scope.paired(scope.hasher))
        else:
            reader = stack.enter_context(seek.open_member(root / "split", scope.root_pin,
                                                         codec=scope.codec, prefix_samples=PREFIX))
            if mode == "complete_encoded":
                begin = clocks()
                reader.verify_encoded()
                encoded = elapsed(begin)
        ready = elapsed(before_reader)
        stack.enter_context(member_source(scan, entry, chunk, reader, loads))
        native = scan.acquire(session, inventory_digest, inventory, scope.assets)
        counts = {"metadata_bytes": chunk["index_bytes"] + (Path(entry["path"])/"manifest.json").stat().st_size,
                  "payload_bytes": originals[chunk["payload_relative_path"]],
                  "decoded_bytes": chunk["uncompressed_bytes"], "full_checks": chunk["window_count"]}
        if reader is None:
            if counts["payload_bytes"] != chunk["compressed_bytes"] or originals[chunk["index_relative_path"]] != chunk["index_bytes"]:
                raise ValueError("The ordinary path did not authenticate the complete original")
        else:
            visits = Counter(loads.values())
            if originals or visits != mixer.visits or reader.full_checks != visits["full"]:
                raise ValueError("A derivative visit either fell through or omitted its native aperture")
            counts = reader.counts() | {"encoded_blocks_preverified": reader.verified_encoded_frames,
                                        "original_manifest_bytes": (Path(entry["path"])/"manifest.json").stat().st_size}
    bind_native(native, session, inventory_digest, pin[7:])
    work = elapsed(start)
    return native, dict(timing=work, setup_and_member_authentication=ready, full_encoded_authentication=encoded,
                        reads=counts, loads=loads, native=mixer.receipt(), original_member_reads=dict(originals),
                        detector_sha256=pin, original_member_sha256=chunk["uncompressed_sha256"])


def convert(root, entry, chunk, scope):
    from leo.storage.short_window import ShortWindowReader

    counters = Counter()
    encoder = dict(split_encode_and_hash_cpu_ns=0)
    start = clocks()
    with original_member_only(entry, chunk, counters), scope.buffer(), scope.paired(scope.hasher):
        reader = ShortWindowReader(Path(entry["path"]))
        if reader.manifest_sha256 != entry["manifest_digest"]:
            raise ValueError("Original source differs from its independent manifest commitment")
        pin = seek.create(reader, 0, root/"split", costs=encoder, codec=scope.codec, prefix_samples=PREFIX)
    capture = elapsed(start)
    start = clocks()
    with seek.open_member(root / "split", pin, codec=scope.codec, prefix_samples=PREFIX) as reader:
        if reader.verify_all() != chunk["uncompressed_sha256"]:
            raise ValueError("Independent complete archival readback did not reproduce the original input")
        verification = reader.counts()
    readback = elapsed(start)
    return dict(root_pin=pin, creation=capture, readback=readback, readback_bytes=verification, original_reads=dict(counters),
                stored_bytes=sum(p.stat().st_size for p in (root/"split").iterdir()),
                codec_blocks=scope.codec.counts(), **encoder)


@contextmanager
def corrupt_tail(root, scope, sequence):
    path = root / "split" / scope.codec.part_files[1]
    with seek.open_member(root / "split", scope.root_pin, codec=scope.codec, prefix_samples=PREFIX) as reader:
        offset = reader.records[sequence]["parts"][1][0]
    path.chmod(0o600)
    try:
        with path.open("rb+") as file:
            file.seek(offset)
            original = file.read(1)
            file.seek(offset)
            file.write(bytes([original[0] ^ 1]))
            file.flush()
            try:
                yield
            finally:
                file.seek(offset)
                file.write(original)
    finally:
        path.chmod(0o400)


def exercise_corruption(root, entry, chunk, scope, reference, skipped):
    def rejects(call):
        try:
            call()
        except ValueError as error:
            return str(error)
        raise ValueError("Expected corrupt bytes to fail verification")

    start = clocks()
    with corrupt_tail(root, scope, skipped):
        full_error = rejects(lambda: receive(root, entry, chunk, "complete_encoded", scope))
        same = receive(root, entry, chunk, "on_demand", scope)[0] == reference
        with seek.open_member(root/"split", scope.root_pin, codec=scope.codec, prefix_samples=PREFIX) as reader:
            requested_error = rejects(lambda: reader.read(skipped, full=True))
    if not same or full_error != "Seekable member digest mismatch" or requested_error != full_error:
        raise ValueError("The corruption exercise changed the fixed interpretation of unread tails")
    return dict(visit=skipped, complete_encoded_error=full_error, requested_tail_error=requested_error,
                unrequested_corruption_preserved_output=same, timing=elapsed(start))


def run(root, case):
    from aperture_trial import write
    from reports.ALGO08.v3.ci16_packed_storage_trial import BUILD
    from reports.ALGO08.v3.ci16_packing import Packing, SOURCE
    from dense_geographic_trial import host
    from eight_ms_native_receiver import prepare
    from empty_bootstrap import checked, load_runtime, receiver_symbols
    from full_short_run import EIGHT_MS_SHA, checked_recipe
    from leo.contracts.digests import canonical_digest
    from reports.ALGO08.v3.sparse_cold_input import frozen_function
    import empty_bootstrap as staged

    if root.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Stage the private derivative in tmpfs")
    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Commit the source and protocol before converting the original member")
    revision = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    machine = host()
    entry, chunk = source(case)
    before = residency(entry, chunk)
    root.mkdir()
    start = clocks()
    binary = root / "packing.so"
    compiled = resource.getrusage(resource.RUSAGE_CHILDREN)
    subprocess.run([*BUILD, str(SOURCE), "-o", str(binary)], check=True)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    compilation = elapsed(start) | {"compiler_cpu_s": after.ru_utime + after.ru_stime - compiled.ru_utime - compiled.ru_stime,
                                    "compiler_input_blocks": after.ru_inblock - compiled.ru_inblock}
    start = clocks()
    _, specification, source_files, _, _ = load_runtime()
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

    checked(SHORT, EIGHT_MS_SHA)
    original_abi = Path(specification["detector"])
    checked(original_abi, specification["detector_sha256"])
    hasher = staged.PAYLOAD / "paired-sha256.so"
    checked(hasher, specification["paired_sha256"]["sha256"])
    assets = root / "assets"
    assets.mkdir()
    (assets / "cancellation-factors.so").symlink_to(original_abi)
    for edge in ("lower", "upper"):
        (assets / (edge+".f32")).symlink_to(staged.RELEASE/"assets"/(edge+".f32"))
    recipe = checked_recipe(eight_ms=True)
    scope = SimpleNamespace(sources=source_files, detector=canonical_digest(recipe), symbols=receiver_symbols(source_files),
                            assets=assets, codec=Packing(binary), hasher=hasher, paired=paired_decoded_hashes,
                            buffer=frozen_function(specification, "receiver_ingress.py", "compressed_input_buffer"))
    startup = elapsed(start)
    write(root/"binding.json", dict(case=case, original=entry, member=chunk, machine=machine, recipe=recipe,
         detector=scope.detector, source_pins={name: sha256((HERE/name).read_bytes()).hexdigest()
              for name in ("seekable_eight_raw.py", "seekable_member.py", "seekable-eight-raw-protocol.md", "mixed_aperture_receiver.py")},
         codec=scope.codec.programme(), checkout=revision, initial_residency=before))
    creation = convert(root, entry, chunk, scope)
    # Commit the digest independently of the private sidecar before any read.
    write(root/"attested-root.json", dict(bound_original=entry["manifest_digest"], **creation))
    scope.root_pin = json.loads((root/"attested-root.json").read_bytes())["root_pin"]
    records, reference = [], None
    for i, order in enumerate(ORDERS):
        row = {}
        for mode in order:
            census = residency(entry, chunk)
            native, record = receive(root, entry, chunk, mode, scope)
            if reference is None:
                reference = native
            if native != reference:
                raise ValueError("The verified native authority, exclusions, clocks or exact factor bytes changed")
            start = clocks()
            native_source = native["source"]
            selected, _, _, choice = prepare(native, recipe, native_source["session_id"], native_source["input_manifest_sha256"],
                                             root / f"{i+1}-{mode}-eof.json")
            seal = elapsed(start)
            row[mode] = dict(record, input_census=census, complete_native_digest=canonical_digest(native),
                             selected_native_digest=canonical_digest(selected), eof_choice=choice["choice"], eof_and_receipt=seal)
        records.append(row)
    reference_selected = {row[mode]["selected_native_digest"] for row in records for mode in ORDERS[0]}
    if len(reference_selected) != 1:
        raise ValueError("The original EOF receiver selection diverged")
    short = records[0]["on_demand"]["loads"]
    unused = next(visit for visit, role in short.items() if role == "short_primary")
    corrupt = exercise_corruption(root, entry, chunk, scope, reference, unused)
    ending = residency(entry, chunk)
    write(root/"original-native.json", reference)
    write(root/"result.json", dict(case=case, orders=ORDERS, records=records, startup=startup, compilation=compilation,
         creation=creation, corrupt_tail=corrupt, final_residency=ending,
         original_analysis_sha256=reference["source"]["analysis_manifest_sha256"],
         original_authority=reference["source"]["raw_recording_authority_digest"],
         exact_native_parity=True, exact_eof_parity=True, admitted=reference["provenance"]["processed_windows"],
         invalid=reference["provenance"]["invalid_capture"], raw_waveform_origin="already resident private tmpfs",
         independent_member_eligible=all((r["ordinary"]["timing"]["cpu_ns"]-r["complete_encoded"]["timing"]["cpu_ns"])/1e6
                                         >= TRANSFER_CPU_MS for r in records)))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("--case", choices=("DS30-0008", "DS30-0169"), default="DS30-0008")
    args = cli.parse_args()
    run(args.root, args.case)
