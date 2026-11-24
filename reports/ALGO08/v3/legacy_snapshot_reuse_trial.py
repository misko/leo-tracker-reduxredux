"""Measure the checked mapped reader on one already resident physical member."""

import argparse
from collections import Counter
from contextlib import ExitStack, closing
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
import subprocess
from unittest.mock import patch

import numpy as np
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader
from tools.pipeline_eval.qualification.cache_residency import load_query

from . import legacy_block_input as port, legacy_block_multi as multi, legacy_block_seek as core
from . import sparse_cold_input as release
from .legacy_block_multi_trial import CENSUS, CENSUS_PIN, NAMES, ORDINAL, ORIGINAL, verified_reader
from .legacy_fused_map_trial import EIGHT_MS_SHA, INSTALLED_SHA, MAP_PIN, PILOT_SHA, SHORT, NativePath, analyze
from .legacy_snapshot_reuse import INGRESS_SHA, SnapshotSlot, descriptor_port
from .zstd_physical_structure import view_for


HERE = Path(__file__).resolve().parent
INGRESS = HERE.parents[2] / "tools/pipeline_eval/variants/experimental/receiver_ingress.py"
QUALIFIED = Path("/dev/shm/leo-v3-legacy-all-0016-result02")
LIBRARY_PIN = "sha256:ebe28b1326a99d49191616726195dc20bfdd2b59dcb63884cae1c959a1154ca4"
CUSTODY_PIN = "sha256:ff7b8f4723021bdcde736ef38df9d8199b7efc31082b62d132a18352c1449941"
WHOLE_AUDIT_PIN = "sha256:ab80cb8d785044264dc7217494280c283d3588145f844e33aebc93b5f8305bc3"
ORDER = ("stock", "reuse", "reuse", "stock")


def source():
    release.verified(INGRESS, INGRESS_SHA)
    definition = spec_from_file_location("legacy_research_pinned_ingress", INGRESS)
    ingress = module_from_spec(definition)
    definition.loader.exec_module(ingress)
    return ingress


def hashes(path):
    from hashlib import sha256

    return sha256(path.read_bytes()).hexdigest()


def attempt(mode, reader, row, prepared, binary, ingress, slot, natives, *, corrupt=False):
    plan = prepared["members"][ORDINAL]
    counts, raw_read = Counter(), Counter()
    original = ingress.read_regular
    ordinary_descriptor = ingress.read_regular_descriptor
    operation = descriptor_port(ordinary_descriptor, slot) if mode == "reuse" else ordinary_descriptor
    path = reader.path / row.payload_relative_path
    matched = reader.path / row.index_relative_path
    store = ingress.ScannerIqStore
    old_read = store._read_regular

    def read(request, limit):
        if request != path:
            if request != matched:
                raise ValueError("Read outside the original signed one-member scope")
            return old_read(request, limit)
        started = core.clock()
        result = original(request, limit)
        raw_read.update(core.elapsed(started))
        counts["compressed_snapshots"] += 1
        counts["compressed_bytes"] += len(result)
        if corrupt:
            # This array is the private ingestion copy, not the source file.
            result.obj[-1] ^= 1
            counts["private_tail_bytes_changed"] += 1
        return result

    def native_open():
        counts["native_decoder_opens"] += 1
        return old_open()

    old_open = binary.legacy_open
    before = getrusage(RUSAGE_SELF)
    start = core.clock()
    with (core.one_member(reader.path, row),
          patch.object(store, "_read_regular", staticmethod(read)),
          patch.object(ingress, "read_regular_descriptor", operation),
          patch.object(binary, "legacy_open", native_open)):
        data = port.checked_file(QUALIFIED / "maps" / plan["map"], plan["map_sha256"], multi.MAX_SIDECAR)
        try:
            with closing(multi.Selective(reader, row, data, plan["map_sha256"], binary)) as member:
                proof, native = analyze(reader, row, ((index, None) for index in member.rows),
                                        natives, load=member.read)
                work = dict(requests=dict(member.requests), spans=member.counts.report(),
                            metadata=member.metadata, authentication=member.authentication, setup=member.setup)
            del member
        except BundleCorruptionError as exc:
            if (not corrupt or str(exc) != f"short-window member changed: {row.payload_relative_path}"
                    or counts["native_decoder_opens"]):
                raise
            return dict(refusal=str(exc), counts=dict(counts))
    if corrupt:
        raise ValueError("Private final encoded byte corruption escaped authentication")
    timing = core.elapsed(start)
    after = getrusage(RUSAGE_SELF)
    return dict(total=timing, process=dict(minor_faults=after.ru_minflt-before.ru_minflt,
                major_faults=after.ru_majflt-before.ru_majflt, input_blocks=after.ru_inblock-before.ru_inblock),
                read=dict(raw_read), native_receiver=native, counts=dict(counts),
                slot=dict(slot.counts) if mode == "reuse" else None, evidence=proof, **work)


def bind():
    census = json.loads(release.verified(CENSUS, CENSUS_PIN))[ORDINAL]
    release.verified(release.CACHE_LIBRARY, release.CACHE_SHA)
    cache, view = view_for(ORIGINAL.path, NAMES, load_query(release.CACHE_LIBRARY))
    if (view is None or cache["filesystem"] != "tmpfs" or any(
            (ORIGINAL.path / name).resolve(strict=True) != ORIGINAL.path / name for name in NAMES)):
        raise ValueError("Only the exact resident original member in tmpfs is admissible")
    reader, chunk = verified_reader(census)
    prepared = port.load_custody(QUALIFIED / "maps/custody.json", CUSTODY_PIN)
    row = prepared["members"][ORDINAL]
    if (any(row[key] != value for key, value in port.member_identity(reader, chunk).items())
            or row["map_sha256"] != MAP_PIN or row["map_kind"] != "exception"):
        raise ValueError("The previously authorized map differs from the original member")
    binary = QUALIFIED / "maps/legacy-block.so"
    port.checked_file(binary, LIBRARY_PIN, 2_000_000)
    return cache, reader, chunk, prepared, core.load(binary)


def run(output):
    ioprio = subprocess.check_output(("ionice", "-p", str(os.getpid())), text=True).strip()
    if (output.parent.resolve() != Path("/dev/shm") or output.exists()
            or os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) != 15
            or ioprio != "best-effort: prio 7"
            or not Path(ShortWindowReader.windows.__code__.co_filename).is_relative_to(release.RELEASE)):
        raise ValueError("Expected one low-priority CPU and the installed original storage reader")
    cache, reader, chunk, prepared, binary = bind()
    ingress = source()
    full = release.PAYLOAD / "receiver.so"
    release.verified(full, INSTALLED_SHA)
    release.verified(SHORT, EIGHT_MS_SHA)
    pilot = np.frombuffer(release.verified(release.RELEASE / "assets/lower.f32", PILOT_SHA["lower"]), dtype="<f4")
    rows = []
    slot = SnapshotSlot()
    with ExitStack() as stack:
        stack.callback(slot.close)
        natives = {kind: NativePath(library, pilot, kind) for kind, library in (
            ("full", full), ("short_primary", SHORT))}
        for value in natives.values():
            stack.callback(value.close)
        for kind in ORDER:
            rows.append(attempt(kind, reader, chunk, prepared, binary, ingress, slot, natives))
        for key in ("evidence", "requests", "counts", "spans"):
            if any(row[key] != rows[0][key] for row in rows):
                raise ValueError(f"Authenticated measured outputs differ: {key}")
        if [v["slot"].get("reuses", 0) for v in rows if v["slot"] is not None] != [0, 1] or slot.in_use:
            raise ValueError("The second candidate did not recycle the same retired snapshot")
        failure = attempt("reuse", reader, chunk, prepared, binary, ingress, slot, natives, corrupt=True)
    with output.open("x") as stream:
        json.dump(dict(case="DS30-0016", member=prepared["members"][ORDINAL], residency=cache,
                       decoder_sha256=LIBRARY_PIN, custody_sha256=CUSTODY_PIN, whole_audit_sha256=WHOLE_AUDIT_PIN,
                       policy=dict(cpu=[2], nice=15, ionice=ioprio, schedule="member-local 20/8"),
                       occurrence_order=ORDER, runs=rows, corrupt_tail=failure,
                       sources={p.name: hashes(p) for p in (INGRESS, Path(__file__),
                               HERE / "legacy-snapshot-reuse-protocol.md", HERE / "legacy_snapshot_reuse.py")}),
                  stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
