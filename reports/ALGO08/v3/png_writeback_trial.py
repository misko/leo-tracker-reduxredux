"""Compare two staged write schedules on a cached DS30-0057 publication."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns, sleep
from unittest.mock import patch

from batched_png_writeback import BatchedPngStore
from leo.storage.fast_scan import immutable_json
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from tools.pipeline_eval.qualification import cache_residency, paired_publication


STOCK = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/publications/DS30-0057/candidate")
RUN = "algo08-v2-a9f064341e3b6d1280bb03bbe6285545"
STOCK_SOURCE = "216ba5c22e173dfd5c061ad2323a209026ec34c553a8d37f617a227b760603df"
PNG_CACHE = paired_publication.LOCK.parent / "ds30-cache-residency.so"
PNG_CACHE_SHA = "4f10e0a2e23121e184ee7d37767f55c29fefc158f4182a2dd99c4268ff2ce6ab"
METADATA = {
    "manifest.json": "5e7d3a8c96de6caa1651b188ffb57ffcd9280d54a37e8cb38d62456e97765017",
    "position-grid.json": "59c0c24e8c888a937db27cf42534b91f8c33430b322c2ef7fdb8ded6a7f22525",
    "position-path.json": "d6fdfa4b1ba2a7d115808926e109b19290533ee8f35b8a8247b6504e1b122fad",
}
DEVICES = (Path("/var/tmp"), Path("/srv/bulk"), Path("/dev/shm"))
ORDERS = (("installed", "batched"), ("batched", "installed"))


def file_sha(path):
    return sha256(path.read_bytes()).hexdigest()


def load_archive():
    store = FastStandardAnalysisStore(STOCK)
    folder = store.folder(RUN)
    if file_sha(PNG_CACHE) != PNG_CACHE_SHA:
        raise ValueError("Page residency library changed")
    members = [(folder, p.name, p.stat().st_size) for p in sorted(folder.iterdir())]
    cache = cache_residency.cache_snapshot(members, os.sysconf("SC_PAGE_SIZE"), cache_residency.load_query(PNG_CACHE))
    if len(members) != 11 or cache["observed_members"] != 11:
        raise ValueError(f"Expected readable cache observations on the eight figures and three documents: {cache}")
    for name, expected in METADATA.items():
        if file_sha(folder / name) != expected:
            raise ValueError(f"Archived DS30-0057 {name} changed")
    manifest = json.loads((folder / "manifest.json").read_bytes())
    pngs = {row["name"]: store.artifact(RUN, row["name"], row["sha256"]) for row in manifest["artifacts"]}
    expected = METADATA | {row["sha256"][7:] + ".png": row["sha256"][7:] for row in manifest["artifacts"]}
    document = {key: val for key, val in manifest.items() if key != "artifacts"}
    return document, pngs, store.position_grid(RUN), store.position_path(RUN), expected, cache


def filesystem(path):
    source, fstype, device = subprocess.check_output(
        ["findmnt", "-T", str(path), "-no", "SOURCE,FSTYPE,MAJ:MIN"], text=True,
    ).split()
    return dict(source=source, fstype=fstype, device=device, available_bytes=shutil.disk_usage(path).free)


def nvme_snapshot():
    stats = Path("/sys/class/block/nvme0n1/stat").read_text().split()
    return tuple(map(int, stats[:11]))


def storage_health():
    mounts = {str(path): filesystem(path) for path in DEVICES}
    traces = []
    for _ in range(3):
        start, before = perf_counter_ns(), nvme_snapshot()
        sleep(1)
        elapsed_ms, after = (perf_counter_ns() - start) / 1e6, nvme_snapshot()
        writes = after[4] - before[4]
        traces.append(dict(utilization_pct=(after[9] - before[9]) * 100 / elapsed_ms,
                           write_await_ms=(after[7] - before[7]) / writes if writes else None,
                           requests_in_flight=after[8]))
    local, bulk, memory = (mounts[str(path)] for path in DEVICES)
    if (local["fstype"] != "ext4" or local["device"] == bulk["device"] or memory["fstype"] != "tmpfs"
            or not (Path("/sys/dev/block") / local["device"] / "slaves/nvme0n1p3").exists()):
        raise ValueError("Expected the independent local NVMe ext4, bulk and tmpfs mounts")
    healthy = local["available_bytes"] > 128 * 2**20 and all(
        row["utilization_pct"] < 10 and (row["write_await_ms"] or 0) < 5 and row["requests_in_flight"] < 2
        for row in traces)
    return mounts, traces, DEVICES[0 if healthy else 2]


def measure(kind, root, loaded):
    document, pngs, grid, path, expected, _ = loaded
    store_type = FastStandardAnalysisStore if kind == "installed" else BatchedPngStore
    root.mkdir()
    store = store_type(root)
    final = store.folder(RUN)
    real_sync = os.fsync
    trace = []
    first_png = None

    def observed_sync(fd):
        nonlocal first_png
        destination = Path(os.readlink(f"/proc/self/fd/{fd}"))
        attributes = os.fstat(fd)
        if final.exists():
            raise ValueError("A compact publication became visible before its fsyncs")
        is_png = destination.suffix == ".png"
        if is_png and first_png is None:
            first_png = {p.name: p.stat().st_size for p in destination.parent.glob("*.png")}
        phase = "png" if is_png else "directory" if stat.S_ISDIR(attributes.st_mode) else "json"
        started = perf_counter_ns()
        real_sync(fd)
        trace.append(dict(phase=phase, wall_ns=perf_counter_ns()-started,
                          inode=attributes.st_ino if is_png else None,
                          png=destination.name if is_png else None))

    with patch.object(os, "fsync", observed_sync):
        cpu, wall = process_time_ns(), perf_counter_ns()
        result = store.publish(RUN, document, pngs, position_grid=grid, position_path=path)
        elapsed, process = perf_counter_ns()-wall, process_time_ns()-cpu
    files = {p.name: file_sha(p) for p in final.iterdir()}
    expected_writes = ({name: len(blob) for name, blob in pngs_by_file(result, pngs)} if kind == "batched"
                       else {trace[0]["png"]: result["artifacts"][0]["byte_count"]})
    phases = [item["phase"] for item in trace]
    if (files != expected or first_png != expected_writes or phases != ["png"] * 8 + ["json", "directory"] * 3
            or len({row["inode"] for row in trace if row["phase"] == "png"}) != 8
            or list(final.parent.iterdir()) != [final]):
        raise ValueError("Unexpected published contents, sync schedule or abandoned staging output")
    return dict(arm=kind, wall_ns=elapsed, cpu_ns=process, raw_files_equal=True, syncs=trace,
                png_count_at_first_fsync=len(first_png), png_bytes_at_first_fsync=sum(first_png.values()),
                png_fsync_wall_ns=sum(row["wall_ns"] for row in trace if row["phase"] == "png"),
                all_fsync_wall_ns=sum(row["wall_ns"] for row in trace))


def pngs_by_file(manifest, pngs):
    return [(row["sha256"][7:] + ".png", pngs[row["name"]]) for row in manifest["artifacts"]]


def run(output):
    from inspect import getsourcefile

    source = Path(getsourcefile(FastStandardAnalysisStore))
    if file_sha(source) != STOCK_SOURCE:
        raise ValueError("Expected the byte-identical installed v3 publisher")
    loaded = load_archive()
    mounts, health, parent = storage_health()
    print(f"Measuring two reversed orders under {parent}", flush=True)
    pressure = Path("/proc/pressure/io").read_text()
    before = nvme_snapshot()
    with TemporaryDirectory(dir=parent, prefix="leo-v3-png-order-") as scratch:
        results = [[measure(arm, Path(scratch) / f"{pair}-{arm}", loaded) for arm in order]
                   for pair, order in enumerate(ORDERS)]
    pressure_after = Path("/proc/pressure/io").read_text()
    immutable_json(output, dict(case="DS30-0057", source_publication=str(STOCK), publication_run_id=RUN,
                               stock_source_sha256=STOCK_SOURCE, fixture_hashes=loaded[4], source_cache=loaded[5],
                               cache_library_sha256=PNG_CACHE_SHA, png_bytes=sum(map(len, loaded[1].values())),
                               mounts=mounts, output_parent=str(parent), device_health=health,
                               nvme_before=before, nvme_after=nvme_snapshot(), io_pressure_before=pressure,
                               io_pressure_after=pressure_after, pairs=results, cpu=sorted(os.sched_getaffinity(0)),
                               nice=os.getpriority(os.PRIO_PROCESS, 0),
                               ionice=subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip(),
                               driver_sha256=file_sha(Path(__file__)),
                               variant_sha256=file_sha(Path(getsourcefile(BatchedPngStore)))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with paired_publication.single_core_slot(2):
        run(args.output)
