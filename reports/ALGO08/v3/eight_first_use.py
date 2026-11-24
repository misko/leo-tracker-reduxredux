"""One resident original dense member through offline capture and independent first readback."""

import argparse
from collections import Counter
from contextlib import ExitStack, nullcontext
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
from seekable_eight_raw import (BUILD, PREFIX, clocks, elapsed, opportunities, original_member_only, pinned_runtime,
                              receive, residency, source)


CASE = "DS30-0008"
ORDERS = (("named20", "ordinary8", "packed8"), ("packed8", "ordinary8"))


def bound_capture():
    """Reuse only the reviewed capture backend, without its historical benchmark imports."""
    import seekable_member as seek
    from empty_bootstrap import load_definitions
    import zstandard as zstd

    path = HERE/"future_capture_storage.py"
    source_bytes = path.read_bytes()
    namespace = dict(__name__="_private_capture_backend", seek=seek, zstd=zstd, sha256=sha256,
                     ExitStack=ExitStack, nullcontext=nullcontext, patch=patch, clock=clocks,
                     elapsed=elapsed, Counter=Counter, json=json, os=os, LEVELS={"ordinary": 1, "split-level-1": 1})
    load_definitions(source_bytes, path, ("ApertureWriter", "capture"), namespace)
    return namespace["capture"], sha256(source_bytes).hexdigest()


def receive_copy(scope, directory, root_pin, record, arm, reference, expected_window_hashes, eof_path, recipe):
    import seekable_member as seek
    from eight_ms_native_receiver import prepare
    from leo.contracts.digests import canonical_digest
    from leo.storage.short_window import ShortWindowReader

    packed = arm == "packed8"
    start = clocks()
    if packed:
        scope.split, scope.root_pin = directory, root_pin
        header = (directory/"source-manifest.json").read_bytes()
        manifest_pin = seek.digest(header)
        profile = seek.ShortWindowManifestV2.model_validate_json(header)
        mode = "full_first_readback"
    else:
        metadata = ShortWindowReader(directory)
        manifest_pin = metadata.manifest_sha256
        profile = metadata.manifest
        mode = "named" if arm == "named20" else "ordinary"
    (chunk,) = [row.model_dump(mode="json") for row in profile.chunks]
    if (chunk["uncompressed_sha256"] != reference["uncompressed_sha256"] or chunk["index_sha256"] != reference["index_sha256"]
            or not packed and (manifest_pin != root_pin or chunk["compressed_sha256"] != reference["compressed_sha256"])):
        raise ValueError("Offline capture changed the original raw member, original index or ordinary codec")
    entry = dict(path=str(directory), manifest_digest=manifest_pin, scope="one-member offline capture audit", windows=64)
    metadata_clock = elapsed(start)
    actual, acquisition = receive(entry, chunk, mode, scope)
    native = actual["source"]
    if (native["raw_recording_authority_digest"] != canonical_digest([native["input_manifest_sha256"], expected_window_hashes])
            or acquisition["reads"]["full_checks"] != 64 or acquisition["reads"]["decoded_bytes"] != reference["uncompressed_bytes"]
            or packed and acquisition["source_timings"]["verified_whole_decoded_sha256"] != reference["uncompressed_sha256"]):
        raise ValueError("First analysis did not independently recover and verify the original complete payload")
    selection = None
    eof = None
    if arm != "named20":
        start = clocks()
        selected, _, _, witness = prepare(actual, recipe, native["session_id"], native["input_manifest_sha256"], eof_path)
        eof = elapsed(start)
        selection = dict(probes=selected["source"]["probes"], choice=witness["choice"])
    summary = dict(capture=record, capture_metadata_admission=metadata_clock, acquisition=acquisition, delayed_eof=eof,
                   named=arm=="named20", exact_full_readback=True, input_window_hashes_sha256=canonical_digest(expected_window_hashes),
                   original_member_sha256=reference["uncompressed_sha256"], root_sha256=root_pin,
                   opportunities_sha256=canonical_digest(opportunities(actual)), native_sha256=canonical_digest(actual),
                   factors=sum(len(row["candidates"]) for row in native["probes"]), selection=selection and selection["choice"])
    return summary, actual, selection


def run(root):
    import empty_bootstrap as staged

    started = clocks()
    _, specification, sources, _, _ = staged.load_runtime()
    release_init = elapsed(started)

    from aperture_trial import write
    from dense_geographic_trial import host
    from leo.contracts.digests import canonical_json_bytes
    from leo.storage.fast_scan import immutable_json
    from leo.storage.short_window import ShortWindowReader
    from leo.storage.writer import _fsync_directory
    from reports.ALGO08.v3.ci16_packing import SOURCE
    import seekable_member as seek

    if root.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Research captures require a fresh local tmpfs root")
    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Commit the frozen protocol and source before the bounded rehearsal")
    revision = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    machine = host()
    entry, chunk = source(CASE)
    observer = run_path(str(checkout/"tools/pipeline_eval/qualification/cache_residency.py"))
    ambient = residency(entry, chunk, observer)
    root.mkdir()
    start = clocks()
    binary = root/"packing.so"
    child_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    subprocess.run([*BUILD, str(SOURCE), "-o", str(binary)], check=True)
    child_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    compile_clock = elapsed(start) | {
        "compiler_cpu_s": child_after.ru_stime + child_after.ru_utime - child_before.ru_stime - child_before.ru_utime}
    start = clocks()
    scope, recipe, geometry = pinned_runtime(root, specification, sources, binary, named=True)
    capture, writer_sha = bound_capture()
    shared_setup = elapsed(start)

    start = clocks()
    replay = ShortWindowReader(Path(entry["path"]))
    if replay.manifest_sha256 != entry["manifest_digest"] or replay.manifest.chunks[0].model_dump(mode="json") != chunk:
        raise ValueError("Source is outside the original signed physical first-member evidence")
    accessed = Counter()
    with original_member_only(entry, chunk, accessed), scope.buffer(), scope.paired(scope.hasher):
        windows = tuple(replay.windows(start_sequence=0, stop_sequence=64))
    if len(windows) != 64 or accessed[chunk["payload_relative_path"]] != chunk["compressed_bytes"]:
        raise ValueError("Did not authenticate all original windows exactly once for the emulator")
    hydration = elapsed(start)
    hashes = [window.index.iq_sha256 for window in windows]
    write(root/"binding.json", dict(machine=machine, commit=revision, case=CASE, original=entry, original_member=chunk,
         original_page_residency=ambient, source_reads=dict(accessed), codec=scope.codec.programme(),
         release_init=release_init, compile_clock=compile_clock, shared_setup=shared_setup, hydrated_fixture=hydration,
         writer_sha256=writer_sha, receiver_recipe=recipe, short_geometry=geometry, orders=ORDERS,
         report_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), authority_inputs=hashes))

    results, full_reference, mixed_reference = [], None, None
    for ordinal, order in enumerate(ORDERS, 1):
        result = {}
        for arm in order:
            output = root/f"{ordinal}-{arm}"
            packed = arm == "packed8"
            start = clocks()
            directory, pin, captured = capture(output, "packed-ci16" if packed else "ordinary", replay.manifest,
                                                windows, codec=scope.codec if packed else None, prefix_samples=PREFIX)
            # The capture-produced root is recorded outside the derived archive.
            document = dict(root=pin, archive=str(directory), current_source_manifest=entry["manifest_digest"])
            seek.write(output/"trusted-root.json", canonical_json_bytes(document))
            _fsync_directory(output)
            summary, actual, selection = receive_copy(scope, directory, pin, captured, arm, chunk, hashes,
                                                      output/"eof.json", recipe)
            immutable_json(output/"native.json", actual)
            summary["through_first_complete_verified_output"] = elapsed(start)
            if full_reference is None:
                full_reference = opportunities(actual)
            if opportunities(actual) != full_reference:
                raise ValueError("Actual receiver methods saw different signed physical opportunities")
            if arm != "named20":
                pair = actual["source"]["probes"], selection
                if mixed_reference is None:
                    mixed_reference = pair
                elif mixed_reference != pair:
                    raise ValueError("The stored format changed an actual signed 20/8 input or held EOF choice")
            result[arm] = summary
        results.append(result)
    write(root/"result.json", dict(case=CASE, arms=results, exact_opportunities=True, exact_20_8_factors_and_selector=True,
                                  bound_original_cache_after=residency(entry, chunk, observer),
                                  no_backing_waveform_access=True))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
