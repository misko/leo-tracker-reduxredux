"""One resident North strict split reader and installed raw-to-position control."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import os
import resource
import subprocess
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
LEAN = Path("/dev/shm/leo-v3-north-adaptive-raw-result01")
LEAN_RESULT = "042eeccded275c307d5b8c96866a61e939a96d7938e2ba66a5b11b02c1224c30"
LEAN_RAW = "2311d9e02ff577e4d3c850077a8d095f62689ccba426f5b8192c331b8e618a97"
NAMED_REFERENCE = "f6d27d8a834ab078dddfb6486082b5aa397e72577b249fc319640d476e788614"
TARGET = 1.6


def ceiling(total, acquisition, native, named):
    editable = acquisition-native
    remaining = total-editable
    return dict(baseline_elapsed_s=total, acquisition_s=acquisition, retained_native_s=native,
                removable_s=editable, zero_cost_floor_s=remaining, same_route_max_ratio=total/remaining,
                against_named_max_ratio=named/remaining, named_reference_s=named,
                required_after_s=named/TARGET, required_saving_s=total-named/TARGET)


def frozen():
    import gzip

    from empty_bootstrap import checked

    lean = json.loads(checked(LEAN/"verified-result.json", LEAN_RESULT))
    raw = json.loads(checked(LEAN/"containing/unified-short-bootstrap.json", LEAN_RAW))
    named = json.loads(gzip.decompress(checked(HERE/"measurements/current-north-control.json.gz", NAMED_REFERENCE)))
    if not all(named["checked_fields"].values()) or not all(lean["checks"].values()):
        raise ValueError("The historical North sources must be verified complete publications")
    budget = ceiling(lean["clock"]["elapsed_s"], lean["phases"]["authenticated_raw_acquisition"]["elapsed_s"],
                     sum(raw["receiver_audit"]["native"]["native_wall_ns"].values())/1e9, named["new"]["clock"]["elapsed_s"])
    return lean, raw, budget


def phase(body):
    from seekable_eight_raw import clocks, elapsed

    start = clocks()
    result = body()
    return result, elapsed(start)


def resident_packed(root, members, codec):
    from empty_bootstrap import checked
    from full_short_physical import CACHE_LIB, CACHE_SHA
    from next_resident_8ms import fully_resident
    from tools.pipeline_eval.qualification.cache_residency import cache_snapshot, load_query

    checked(CACHE_LIB, CACHE_SHA)
    names = ("seek.json", "source-manifest.json", "source-index.jsonl", *codec.part_files)
    files = [(path, name, (path/name).stat().st_size) for path in members for name in names]
    observed = cache_snapshot(files, os.sysconf("SC_PAGE_SIZE"), load_query(CACHE_LIB))
    if not fully_resident(observed) or observed["observed_members"] != 5*len(members) or not root.is_dir():
        raise ValueError("All exact derivative objects must remain resident")
    return observed


def transform(root, clip, observed, *, member_count=19):
    from aperture_trial import write
    from empty_bootstrap import BASELINE, BASELINE_PIN, PAYLOAD, checked
    from leo.storage.short_window import ShortWindowReader
    from packed_combined_input import STRICT_EIGHT_SCHEMA
    from reports.ALGO08.v3.ci16_packing import Packing, SOURCE
    from reports.ALGO08.v3.sparse_cold_input import frozen_function
    from runpy import run_path
    from seekable_eight_raw import BUILD, PREFIX, clocks, elapsed, original_member_only
    from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256, paired_decoded_hashes
    import seekable_member as seek

    begin = clocks()
    binary = root/"packing.so"
    checked(BASELINE, BASELINE_PIN)
    specification = run_path(str(BASELINE))["checked_spec"](PAYLOAD)
    hasher = PAYLOAD/"paired-sha256.so"
    checked(hasher, specification["paired_sha256"]["sha256"])
    if not PairedSha256(hasher).hardware:
        raise ValueError("Use the pinned production verifier during conversion")
    ingress = frozen_function(specification, "receiver_ingress.py", "compressed_input_buffer")
    cpu_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    _, compile_clock = phase(lambda: subprocess.run([*BUILD, str(SOURCE), "-o", str(binary)], check=True))
    cpu_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    compile_clock["compiler_cpu_s"] = cpu_after.ru_utime+cpu_after.ru_stime-cpu_before.ru_utime-cpu_before.ru_stime
    codec = Packing(binary)
    sidecars = root/"conversion"
    sidecars.mkdir()
    documents, members, dirs = [], [], []
    for snap in clip["manifests"]:
        original = Path(snap["path"])
        reader = ShortWindowReader(original.parent)
        if reader.manifest_sha256 != snap["digest"] or not original.resolve(strict=True).is_relative_to(Path(clip["recording"])):
            raise ValueError("The original signed segment changed")
        for chunk in reader.manifest.chunks:
            folder = sidecars/f"member-{len(members):06d}"
            start = clocks()
            source = dict(path=str(original.parent), manifest_digest=reader.manifest_sha256)
            opened = Counter()
            with original_member_only(source, chunk.model_dump(mode="json"), opened), ingress(), paired_decoded_hashes(hasher):
                root_pin = seek.create(reader, chunk.chunk_index, folder, codec=codec, prefix_samples=PREFIX)
            encode = elapsed(start)
            start = clocks()
            with seek.open_member(folder, root_pin, codec=codec, prefix_samples=PREFIX) as record:
                independent = record.verify_all()
                counts = record.counts()
            verify = elapsed(start)
            if (independent != chunk.uncompressed_sha256 or opened[chunk.payload_relative_path] != chunk.compressed_bytes
                    or counts["decoded_bytes"] != chunk.uncompressed_bytes or counts["full_checks"] != chunk.window_count):
                raise ValueError("The derivative recovered a different original full member")
            expect = dict(directory=folder.name, manifest_sha256=reader.manifest_sha256, chunk_index=chunk.chunk_index,
                          seek_sha256=root_pin)
            documents.append(dict(binding=expect, original=chunk.model_dump(mode="json"), encode=encode,
                                  verification=verify, original_reads=dict(opened), checked_derivative=counts))
            dirs.append(folder)
            members.append(expect)
    if (len(members) != member_count or sum(d["original"]["compressed_bytes"] for d in documents) != clip["compressed_bytes"]
            or sum(d["original"]["window_count"] for d in documents) != clip["issued"]):
        raise ValueError("The derivative must bind every original member and visit")
    mapping = sidecars/"map.json"
    payload = json.dumps(dict(schema=STRICT_EIGHT_SCHEMA, codec_sha256=seek.digest(binary.read_bytes()), members=members),
                         sort_keys=True, separators=(",", ":")).encode()
    seek.write(mapping, payload)
    request = dict(map=str(mapping), map_sha256=seek.digest(payload), codec=str(binary))
    packed = resident_packed(sidecars, dirs, codec)
    elapsed_total = elapsed(begin)
    write(root/"conversion.json", dict(original_residency=observed, packed_residency=packed, request=request,
         sections=documents, compiler=compile_clock, total_including_compiler_and_verification=elapsed_total,
         codec=codec.programme(), counts=codec.counts(), independent_check=True))
    return request, dirs, codec


def run(root):
    from adaptive_raw_trial import launch, prepare, work
    from aperture_trial import write
    from current_north_control import run as named
    from dense_geographic_trial import host
    from north_held_anchor_pair import tmpfs

    machine = host()
    tmpfs(root.parent)
    _, _, budget = frozen()
    if budget["against_named_max_ratio"] < TARGET:
        raise ValueError("The trace's allowed-savings bound is below the named target")
    clip, cache = work("north", root)
    before = cache()
    git = ["git", "-C", str(HERE.parents[2])]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Freeze the checked source before conversion")
    root.mkdir()
    write(root/"plan.json", dict(machine=machine, clip=clip, resume_order=["packed_candidate", "named_v3"],
         target=TARGET, arithmetic=budget, source=sha256(Path(__file__).read_bytes()).hexdigest(),
         revision=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()))
    strict, dirs, codec = transform(root, clip, before)
    prepare("north", root/"candidate", strict=strict)
    write(root/"packed-before.json", resident_packed(Path(strict["map"]).parent, dirs, codec))
    clock = launch(root/"candidate")
    write(root/"packed-after.json", resident_packed(Path(strict["map"]).parent, dirs, codec))
    if clock["exit_code"]:
        return
    named(root/"named", verify_after=False)


def score(root):
    from adaptive_raw_trial import score as adaptive_score
    from aperture_trial import read, write
    from current_north_control import score as named_score

    plan, conversion = (read(root/f"{name}.json") for name in ("plan", "conversion"))
    candidate = adaptive_score(root/"candidate")
    if not candidate["passed"]:
        write(root/"result.json", dict(candidate=candidate, elapsed_ratio=None, packed_exact=False))
        return
    named_receipt = root/"named/verified-comparison.json"
    named = read(named_receipt) if named_receipt.exists() else named_score(root/"named")
    old, old_raw, _ = frozen()
    raw = read(root/"candidate/containing/unified-short-bootstrap.json")
    usage = raw["packed_ci16_input"]
    rows = usage["members"]
    expected = conversion["sections"]
    if (not usage["strict_packed_eight"] or usage["fallback"] is not None or usage["original_windows"] or
            len(rows) != len(expected) or any(
                got["state"] != "strict-packed-eight" or got["encoded_blocks"] != 2*want["original"]["window_count"] or
                got["original_decoded_sha256"] != want["original"]["uncompressed_sha256"] or
                got["checks"]["payload_bytes"] != want["checked_derivative"]["payload_bytes"] or
                got["seek_sha256"] != want["binding"]["seek_sha256"]
                for got, want in zip(rows, expected, strict=True))):
        raise ValueError("Strict complete scope or packed input verification changed")
    apertures = Counter(value for row in rows for value in row["loads"].values())
    if (apertures != Counter(old_raw["receiver_audit"]["native"]["visits"]) or
            candidate["native_sha256"] != old["native_sha256"] or candidate["owner_counts"] != old["owner_counts"] or
            candidate["owners_sha256"] != old["owners_sha256"] or candidate["arms"] != old["arms"] or
            candidate["layout"]["sampled"] != old["layout"]["sampled"] or
            candidate["layout"]["phase_sha256"] != old["layout"]["phase_sha256"] or
            any(candidate["images"][key][digest] != old["images"][key][digest]
                for key in old["images"] for digest in ("sha256", "rgba_sha256")) or
            not all(named["checked_fields"].values())):
        raise ValueError("Packed candidate changed complete lean-route geometry, final evidence, or named control identity")
    wall = candidate["clock"]["elapsed_s"]
    named_wall = named["new"]["clock"]["elapsed_s"]
    paid = conversion["total_including_compiler_and_verification"]["wall_ns"]/1e9
    write(root/"result.json", dict(plan=plan, candidate=candidate, named=named, apertures=dict(apertures),
         signed_and_eight_products_equal_to_lean=True, packed_exact=True, elapsed_ratio=named_wall/wall,
         qualified=named_wall/wall >= TARGET, legacy_conversion_s=paid, legacy_first_s=paid+wall,
         encoded_bytes=sum(x["checks"]["payload_bytes"] for x in rows),
         decoded_bytes=sum(x["checks"]["decoded_bytes"] for x in rows),
         packed_integrity=usage, conversion_sha256=sha256((root/"conversion.json").read_bytes()).hexdigest()))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("run", "score"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    (run if args.action == "run" else score)(args.root)
