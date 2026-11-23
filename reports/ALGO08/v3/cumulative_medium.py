"""Verify the one medium cumulative publication input and measure an admitted pair."""

from time import perf_counter, process_time

ENTRY = process_time(), perf_counter()

import argparse
import json
import os
from pathlib import Path


HERE = Path(__file__).resolve().parent
CONTROL = "7b12b73f5e104a56d9da7c47641c6014e8003bed54efc4e4174b8c08abd35e67"
MAX_FULL_IO_STALL = 10.0


def control():
    from short_raw_diagnostic import CASES, assignment, checked, read

    case, pin, decision, visits, _ = CASES[1]
    source, archived = assignment(case, pin, decision, visits)
    row = read(checked(HERE / "measurements/short-raw-diagnostic.json", CONTROL))["cases"][1]
    if (case, decision, visits) != ("DS30-0057", "complete", 2717):
        raise ValueError("Require the frozen medium physical workload")
    if any(row[key] != source[key] for key in ("recording", "archive")) or row["region_file"] != source["region"]:
        raise ValueError("Archived medium control no longer binds original acquisition or prior")
    return row, archived


def full_io_share(document):
    full = [line.split() for line in document.splitlines() if line.startswith("full ")]
    (row,) = full
    return float(dict(pair.split("=", 1) for pair in row[1:])["avg10"])


def admitted(cache, pressures):
    return (not cache["unavailable"] and cache["members"] == cache["observed_members"] > 0
            and cache["cached_pages"] == cache["observed_file_pages"] > 0
            and all(0 <= full_io_share(sample) <= MAX_FULL_IO_STALL for sample in pressures))


def preflight(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from short_raw_diagnostic import CACHE_LIB, CACHE_SHA, FastScanStore, cache_residency, checked

    settings = host()
    row, _ = control()
    root.mkdir()
    recording = Path(row["recording"])
    store = FastScanStore(root)
    session, digest, inventory = store.inventory(recording, verify_windows=False)
    if digest != row["runs"]["candidate"]["input_manifest"] or inventory["window_count"] != row["issued"]:
        raise ValueError("Medium input no longer matches the archived signed inventory")
    source = tuple((Path(m["path"]) / "manifest.json", m["manifest_digest"]) for m in inventory["segments"])
    query = cache_residency.load_query(checked(CACHE_LIB, CACHE_SHA))
    pressure = Path("/proc/pressure/io")
    start = pressure.read_text()
    cache = cache_residency.bound_snapshot(store, recording, source, os.sysconf("SC_PAGE_SIZE"), query)
    end = pressure.read_text()
    out = dict(case=row["case"], admission="raw" if admitted(cache, (start, end)) else "saved",
               max_full_io_stall_pct=MAX_FULL_IO_STALL, settings=settings, recording=str(recording), issue=row["issued"],
               session=session, input_manifest=digest, cache=cache, pressure=[start, end], waveform_calls=0,
               archive=row["archive"], region=row["region"], control_sha256=CONTROL)
    write(root / "admission.json", out)
    print(json.dumps(out))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    preflight(parser.parse_args().root)
