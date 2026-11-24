"""Passive enrollment for a complete physical positive or an original dense range."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
BULK = Path("/srv/bulk/leo/fast-scan-recordings")
FULL = {
    "DS30-0057": (Path("/dev/shm/leo-exact-solver-0057-result01/candidate/fast-scan-inputs"),
                  "5dff8a6bf2be444aeaccbc02def77693cfe864fbd0f3a9f7bfc3cc9befbed774"),
    "DS30-0316": (Path("/dev/shm/leo-v3-saved-0316-pair-01/stock/fast-scan-inputs"),
                  "061f319935b349c7d5edc858adb0a9827d95d1d87c48a5b8786a2068fe98b595"),
}
DENSE = (Path("/dev/shm/leo-held-anchor-selected-dense-01/selected/fast-scan-inputs"),
         "3f08c51c74fa878e0b5993311a840172c2b06d2d0be02988d13f0c29f502034b")
TAKE_SEGMENTS = 2
EXTENTS = {
    "dense-original--one": (
        Path("/dev/shm/leo-seekable-member-0008-case1/fast8-auto-20261113-075937-d9ab96ee-1-lower-segment-00000000"),
        dict(manifest=6812, windows=172750, iq=77442779), 64, 2.8123266),
    "dense-original--two": (
        Path("/srv/bulk/leo-dev/leo-physical-stage-envelope-2j7mlwtt/"
             "fast8-auto-20261113-075937-d9ab96ee-1-lower-segment-00000000"),
        dict(manifest=6812, windows=172750, iq=77442779), 128, 5.6479974),
    "second-site-original--one": (
        Path("/dev/shm/leo-receiver-ceiling-0169-results01/fast8-auto-20261116-022353-b914c97a-1-lower-segment-00000000"),
        dict(), 64, None),
}
ROLE_BYTES = {"payload": ("compressed_bytes", "compressed_sha256"), "index": ("index_bytes", "index_sha256")}


def read_pinned(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"The frozen source changed at {path}")
    return json.loads(data)


def inventory(enrollment):
    folder, pin = enrollment
    return read_pinned(folder / ("fast-" + pin[:32] + ".json"), pin)


def official(entry, sample):
    from next_resident_8ms import fully_resident, member_stubs

    directory = Path(entry["path"])
    if not directory.is_relative_to(BULK):
        raise ValueError("Expected only the previously signed physical input path")
    path = directory / "manifest.json"
    try:
        observed = sample([(directory, path.name, path.stat().st_size)])
        manifest = read_pinned(path, entry["manifest_digest"]) if fully_resident(observed) else None
        specs = {}
        for role, (extent, digest) in ROLE_BYTES.items():
            rows = [] if manifest is None else [
                dict(name=chunk[f"{role}_relative_path"], bytes=chunk[extent], sha256=chunk[digest])
                for chunk in manifest["chunks"]]
            paths = (member_stubs(directory, role) if manifest is None else
                     [(directory, row["name"], row["bytes"]) for row in rows])
            specs[role] = dict(bound_members=rows, bytes=sum(n for _, _, n in paths), pages=sample(paths))
    except OSError as error:
        return dict(path=str(directory), admitted=False, error=error.errno)
    return dict(path=str(directory), manifest_digest=entry["manifest_digest"], metadata_pages=observed,
                manifest_verified=manifest is not None,
                visits=None if manifest is None else manifest["window_count"], data=specs,
                admitted=manifest is not None and all(fully_resident(group["pages"]) for group in specs.values()))


def local(label, directory, expected, visits, span, sample):
    from next_resident_8ms import member_stubs

    try:
        by_role = {role: member_stubs(directory, role) for role in ROLE_BYTES}
        manifest = directory / "manifest.json"
        if manifest.is_file() and expected and manifest.stat().st_size != expected["manifest"]:
            raise ValueError(f"Detached manifest extent changed at {manifest}")
        result = {role: dict(bytes=sum(n for _, _, n in paths), pages=sample(paths),
                             names=[name for _, name, _ in paths]) for role, paths in by_role.items()}
    except OSError as error:
        result = {"error": error.errno}
    return dict(id=label, path=str(directory), issued=visits, counter_span_s=span, files=result)


def inspect(output):
    from aperture_trial import write
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import CACHE_LIB, CACHE_SHA
    from tools.pipeline_eval.qualification.cache_residency import cache_snapshot, load_query

    machine = host()
    pressure = Path("/proc/pressure/io")
    before = pressure.read_text()
    checked(CACHE_LIB, CACHE_SHA)
    query = load_query(CACHE_LIB)
    page_size = os.sysconf("SC_PAGE_SIZE")

    def sample(entries):
        return cache_snapshot(entries, page_size, query)

    complete = {}
    for key, source in FULL.items():
        data = inventory(source)
        segments = [official(row, sample) for row in data["segments"]]
        complete[key] = dict(inventory_sha256=source[1], issued=data["window_count"], segments=segments,
                             admitted=all(row["admitted"] for row in segments))
    data = inventory(DENSE)
    chosen = [official(row, sample) for row in data["segments"][:TAKE_SEGMENTS]]
    prefix = dict(case="DS30-0008", parent_inventory_sha256=DENSE[1], parent_issued=data["window_count"],
                  limit_segments=TAKE_SEGMENTS, segments=chosen, admitted=all(row["admitted"] for row in chosen))
    write(output, dict(machine=machine, complete=complete, dense_prefix=prefix,
                       local=[local(label, *entry, sample) for label, entry in EXTENTS.items()],
                       pressure_before=before, pressure_after=pressure.read_text(), raw_traversals=0,
                       original_waveform_bytes_read=0, conditioning_bytes=0,
                       workload_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    inspect(parser.parse_args().output)
