"""Verified seekable input to the unchanged signed native 20/8 ms acquisition."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager, nullcontext
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
from runpy import run_path
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from mixed_aperture_receiver import NativePath


SHORT = Path("/var/tmp/leo-v3-eight-ms-build-padded/8ms/short-primary.so")
SHORT_BUILD = "3ee8b9ceb4ec5b8b910520a673309f1799e632618b525d8234058c63d22f86b1"
DENSE = Path("/dev/shm/leo-seekable-member-0008-case1/result.json")
DENSE_SHA = "b1f310a05ade750be8e6dbf09f455baa27b71cb7dcd03334130a285a852d6cd6"
DENSE_TRIAL = Path("/dev/shm/leo-v3-seekable-eight-dense-result02")
DENSE_TRIAL_SHA = "322714ed8300c535c027fb597e42766c6db9b73462998b3cc2a2fb6943a34503"
HELD = Path("/dev/shm/leo-receiver-ceiling-0169-results01/scope.json")
HELD_SHA = "95a438f0904e4568b6f2a3618b7fbf691c29d0e2d352fd3727cc83d35b72aa9a"
ORDERS = (("ordinary", "complete_encoded", "on_demand"), ("on_demand", "complete_encoded", "ordinary"))
PREFIX, ORIGINAL_SAMPLES = 80_000, 200_000
TRANSFER_CPU_MS = 25
BUILD = ("cc", "-std=c11", "-O3", "-fPIC", "-shared", "-mssse3", "-Wall", "-Wextra", "-Werror")


class CommittedSamples:
    """Logical source shape with no raw data pointer until a checked engine requests a real array."""

    dtype = np.dtype("<i2")
    flags = SimpleNamespace(c_contiguous=True)
    shape = (ORIGINAL_SAMPLES, 2, 2)

    def __init__(self, reader, sequence, loads):
        self.reader, self.sequence, self.loads = reader, sequence, loads
        self.full = self.samples = None

    def realize(self, full):
        if self.samples is None:
            raw = self.reader.read(self.sequence, full=full)
            self.full = full
            self.samples = np.frombuffer(raw, dtype=self.dtype).reshape(ORIGINAL_SAMPLES if full else PREFIX, 2, 2)
            self.loads[self.sequence] = "full" if full else "short_primary"
        elif full != self.full:
            raise ValueError("The fixed visit cannot switch its declared native aperture")
        return self.samples


@contextmanager
def original_member_only(entry, chunk, counters, read_clocks=None):
    from leo.storage.short_window import ShortWindowReader

    allowed = {chunk[f"{kind}_relative_path"]: (chunk[extent], chunk[pin]) for kind, extent, pin in (
        ("payload", "compressed_bytes", "compressed_sha256"), ("index", "index_bytes", "index_sha256"))}
    stock = ShortWindowReader._member

    def member(reader, name, size, wanted):
        if reader.path != Path(entry["path"]) or allowed.get(name) != (size, wanted):
            raise ValueError("Waveform access lies outside the authenticated local one-member scope")
        start = clocks()
        value = stock(reader, name, size, wanted)
        if read_clocks is not None:
            read_clocks[name] = elapsed(start)
        counters[name] += size
        return value

    with patch.object(ShortWindowReader, "_member", member):
        yield


@contextmanager
def member_source(scan, entry, chunk, reader, loads, io_costs):
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
            start = clocks()
            super().__init__(value, stop_sequence=chunk["window_count"])
            if self.reader.manifest.chunks[0].model_dump(mode="json") != chunk:
                raise ValueError("The original complete-member extent changed")
            if reader is not None and (reader.manifest_sha256 != self.manifest_digest
                    or reader.chunk.model_dump(mode="json") != chunk or any(r.target_id not in self.targets for r in reader.rows)):
                raise ValueError("The rooted object is bound to a different original manifest, target or member")
            io_costs["source_manifest"] = elapsed(start)

        def windows(self):
            if reader is None:
                included = Counter()
                start = clocks()
                for window in super().windows():
                    included.update(elapsed(start))
                    yield window
                    start = clocks()
                included.update(elapsed(start))
                io_costs["original_iterator"] = dict(included)
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


def residency(entry, chunk, observer):
    from empty_bootstrap import checked
    from full_short_physical import CACHE_LIB, CACHE_SHA
    from next_resident_8ms import fully_resident

    segment = Path(entry["path"])
    if segment.resolve(strict=True) != segment or segment.stat().st_dev != Path("/dev/shm").stat().st_dev:
        raise ValueError("Use only the already staged private tmpfs original")
    checked(CACHE_LIB, CACHE_SHA)
    checks = [(segment, "manifest.json", (segment/"manifest.json").stat().st_size),
              (segment, chunk["index_relative_path"], chunk["index_bytes"]),
              (segment, chunk["payload_relative_path"], chunk["compressed_bytes"])]
    census = observer["cache_snapshot"](checks, os.sysconf("SC_PAGE_SIZE"), observer["load_query"](CACHE_LIB))
    if not fully_resident(census) or census["members"] != 3:
        raise ValueError(f"Not all pinned source metadata and waveform bytes are resident: {census}")
    return census


def receive(entry, chunk, mode, scope):
    from empty_bootstrap import bind_native
    from full_short_run import EIGHT_MS_SHA
    from leo.contracts.digests import canonical_digest
    from leo.contracts.multirate_window_recording import ShortWindowIndexV2
    from mixed_aperture_receiver import MixedApertureDetector
    from unified_short_bootstrap import receiver_import
    import empty_bootstrap as staged
    import seekable_member as seek

    if mode not in ORDERS[0]:
        raise ValueError("Unrecognized verification boundary")
    pin, loads, originals = scope.detector, {}, Counter()
    io_costs, descriptor_costs, index_costs = {}, {}, Counter()
    original_index = ShortWindowIndexV2.model_validate_json

    def parse_index(*args, **options):
        began = clocks()
        result = original_index(*args, **options)
        index_costs.update(elapsed(began))
        index_costs["rows"] += 1
        return result

    inventory = dict(segments=[entry], window_count=chunk["window_count"])
    inventory_digest = canonical_digest(inventory)
    session = "fast-" + inventory_digest[7:39]
    start = clocks()
    with ExitStack() as stack:
        mixer = MixedApertureDetector(SHORT, EIGHT_MS_SHA, full_coverage=True)
        scan = scope.scan
        scanner_name = staged.RECEIVER.removesuffix(".py").replace("/", ".")
        stack.enter_context(patch.object(scan, "detector", mixer.detector))
        stack.enter_context(receiver_import(scanner_name, scope.symbols))
        stack.enter_context(original_member_only(entry, chunk, originals, descriptor_costs))
        stack.enter_context(patch.object(ShortWindowIndexV2, "model_validate_json", staticmethod(parse_index)))
        stack.enter_context(scope.buffer())
        stack.enter_context(scope.paired(scope.hasher))
        prefetch = stack.enter_context(scope.prefetch())
        before_reader = clocks()
        reader = None
        encoded = None
        if mode != "ordinary":
            reader = stack.enter_context(seek.open_member(scope.split, scope.root_pin,
                                                         codec=scope.codec, prefix_samples=PREFIX))
            if mode == "complete_encoded":
                begin = clocks()
                reader.verify_encoded()
                encoded = elapsed(begin)
        ready = elapsed(before_reader)
        stack.enter_context(member_source(scan, entry, chunk, reader, loads, io_costs))
        start_acquire = clocks()
        native = scan.acquire(session, inventory_digest, inventory, scope.assets)
        acquire = elapsed(start_acquire)
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
    start_bind = clocks()
    bind_native(native, session, inventory_digest, pin[7:])
    bind_cost = elapsed(start_bind)
    work = elapsed(start)
    if prefetch.submitted or prefetch.hits:
        raise ValueError("The one-member comparison must read no following waveform member")
    return native, dict(timing=work, setup_and_member_authentication=ready, full_encoded_authentication=encoded,
                        acquire=acquire, post_acquire_native_bind=bind_cost, index_model_parse=dict(index_costs),
                        released_member_descriptors=descriptor_costs, source_timings=io_costs, prefetch=asdict(prefetch),
                        reads=counts, loads=loads, native=mixer.receipt(), original_member_reads=dict(originals),
                        detector_sha256=pin, original_member_sha256=chunk["uncompressed_sha256"])


def convert(root, entry, chunk, scope):
    from leo.storage.short_window import ShortWindowReader
    import seekable_member as seek

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
    import seekable_member as seek

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
    import seekable_member as seek

    def rejects(call):
        try:
            call()
        except ValueError as error:
            return str(error)
        raise ValueError("Expected corrupt bytes to fail verification")

    start = clocks()
    with corrupt_tail(root, scope, skipped):
        full_error = rejects(lambda: receive(entry, chunk, "complete_encoded", scope))
        same = receive(entry, chunk, "on_demand", scope)[0] == reference
        with seek.open_member(root/"split", scope.root_pin, codec=scope.codec, prefix_samples=PREFIX) as reader:
            requested_error = rejects(lambda: reader.read(skipped, full=True))
    if not same or full_error != "Seekable member digest mismatch" or requested_error != full_error:
        raise ValueError("The corruption exercise changed the fixed interpretation of unread tails")
    return dict(visit=skipped, complete_encoded_error=full_error, requested_tail_error=requested_error,
                unrequested_corruption_preserved_output=same, timing=elapsed(start))


def run(root, case, *, clean_dense=False):
    import empty_bootstrap as staged

    start = clocks()
    _, specification, source_files, _, _ = staged.load_runtime()
    runtime_startup = elapsed(start)

    from aperture_trial import write
    from combined_frontier_run import PREFETCH_FILES, load_prefetch
    from reports.ALGO08.v3.ci16_packing import Packing, SOURCE
    from dense_geographic_trial import host
    from eight_ms_native_receiver import prepare
    from empty_bootstrap import checked, receiver_symbols, staged_scanner
    from full_short_run import EIGHT_MS_SHA, checked_recipe
    from leo.contracts.digests import canonical_digest
    from reports.ALGO08.v3.sparse_cold_input import frozen_function
    from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256, paired_decoded_hashes

    if root.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Stage the private derivative in tmpfs")
    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Commit the source and protocol before converting the original member")
    revision = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    machine = host()
    entry, chunk = source(case)
    observer = run_path(str(checkout/"tools/pipeline_eval/qualification/cache_residency.py"))
    before = residency(entry, chunk, observer)
    root.mkdir()
    start = clocks()
    binary = root / "packing.so"
    compiled = resource.getrusage(resource.RUSAGE_CHILDREN)
    subprocess.run([*BUILD, str(SOURCE), "-o", str(binary)], check=True)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    compilation = elapsed(start) | {"compiler_cpu_s": after.ru_utime + after.ru_stime - compiled.ru_utime - compiled.ru_stime,
                                    "compiler_input_blocks": after.ru_inblock - compiled.ru_inblock}
    start = clocks()
    checked(SHORT, EIGHT_MS_SHA)
    geometry = json.loads(checked(SHORT.parent.parent/"build.json", SHORT_BUILD))["geometry"]["8ms"]
    if (geometry["short_samples"] != PREFIX or geometry["stored_samples"] != ORIGINAL_SAMPLES
            or any(v > PREFIX for k, v in geometry.items() if k.startswith("first_unused"))):
        raise ValueError("The audited fixed ABI does not fit in the requested 8 ms samples")
    original_abi = Path(specification["detector"])
    checked(original_abi, specification["detector_sha256"])
    hasher = staged.PAYLOAD / "paired-sha256.so"
    checked(hasher, specification["paired_sha256"]["sha256"])
    if not PairedSha256(hasher).hardware:
        raise ValueError("The ordinary comparison requires the installed hardware paired SHA-256 path")
    assets = root / "assets"
    assets.mkdir()
    (assets / "cancellation-factors.so").symlink_to(original_abi)
    for edge in ("lower", "upper"):
        (assets / (edge+".f32")).symlink_to(staged.RELEASE/"assets"/(edge+".f32"))
    recipe = checked_recipe(eight_ms=True)
    detector = canonical_digest(recipe)
    scan = staged_scanner(source_files, detector=lambda *_: None)
    scan.PINS["cancellation-factors.so"] = detector[7:]
    scope = SimpleNamespace(scan=scan, detector=detector, symbols=receiver_symbols(source_files), prefetch=load_prefetch(),
                            assets=assets, codec=Packing(binary), hasher=hasher, paired=paired_decoded_hashes,
                            buffer=frozen_function(specification, "receiver_ingress.py", "compressed_input_buffer"))
    startup = elapsed(start)
    write(root/"binding.json", dict(case=case, original=entry, member=chunk, machine=machine, recipe=recipe,
         detector=scope.detector, source_pins={name: sha256((HERE/name).read_bytes()).hexdigest()
              for name in ("seekable_eight_raw.py", "seekable_member.py", "seekable-eight-raw-protocol.md", "mixed_aperture_receiver.py")},
         codec=scope.codec.programme(), checkout=revision, initial_residency=before, short_geometry=geometry,
         production_prefetch_sources=PREFETCH_FILES, sha256_hardware=True,
         original_short_build_sha256=SHORT_BUILD))
    if clean_dense:
        if case != "DS30-0008":
            raise ValueError("The clean paired control reuses only the already sealed dense derivative")
        prior = json.loads(checked(DENSE_TRIAL/"result.json", DENSE_TRIAL_SHA))
        if not prior["exact_native_parity"] or not prior["exact_eof_parity"]:
            raise ValueError("The earlier derivative did not reproduce ordinary acquisition")
        creation, scope.split = prior["creation"], DENSE_TRIAL/"split"
        scope.root_pin = creation["root_pin"]
        orders = (("ordinary", "complete_encoded"),)
    else:
        creation = convert(root, entry, chunk, scope)
        # Publish the digest independently of the private sidecar before any read.
        write(root/"attested-root.json", dict(bound_original=entry["manifest_digest"], **creation))
        scope.split = root/"split"
        scope.root_pin = json.loads((root/"attested-root.json").read_bytes())["root_pin"]
        orders = ORDERS
    records, reference = [], None
    for i, order in enumerate(orders):
        row = {}
        for mode in order:
            census = residency(entry, chunk, observer)
            native, record = receive(entry, chunk, mode, scope)
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
    reference_selected = {record["selected_native_digest"] for row in records for record in row.values()}
    if len(reference_selected) != 1:
        raise ValueError("The original EOF receiver selection diverged")
    corrupt = None
    if not clean_dense:
        short = records[0]["on_demand"]["loads"]
        unused = next(visit for visit, role in short.items() if role == "short_primary")
        corrupt = exercise_corruption(root, entry, chunk, scope, reference, unused)
    ending = residency(entry, chunk, observer)
    write(root/"original-native.json", reference)
    write(root/"result.json", dict(case=case, orders=orders, records=records, startup=startup, compilation=compilation,
         runtime_startup=runtime_startup,
         creation=creation, reused_creation=clean_dense, corrupt_tail=corrupt, final_residency=ending,
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
    cli.add_argument("--clean-dense", action="store_true")
    args = cli.parse_args()
    run(args.root, args.case, clean_dense=args.clean_dense)
