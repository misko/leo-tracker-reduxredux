"""Measure the complete raw combination against named v3 on one saved recording."""

import argparse
import os
import subprocess
from pathlib import Path
from time import perf_counter, process_time

from aperture_trial import RELEASE, read, write
from dense_full_short_raw import checked, usage
from dense_geographic_trial import host
from full_short_physical import CACHE_LIB, CACHE_SHA, ISSUED, assigned, environment
from full_short_run import EIGHT_MS_SHA, GEOGRAPHIC_SHA

HERE = Path(__file__).resolve().parent
STOCK = Path("/opt/leo-algo08/algo08v3/run")
STOCK_PIN = "fae032526227f55ca2419a0b29c69afc7fc97fa04508f33d0403802934f13448"
REFERENCE = Path("/var/tmp/leo-full-short-DS30-0016-pair/request.json")
REFERENCE_PIN = "d58723098826fc7e1478f92880dffdb500bcb3f5225b4d64a4b2949cfbceab06"


def measure(command, env, output, arm):
    with (output / f"{arm}-stdout").open("x") as log:
        before, start = usage(), perf_counter()
        process = subprocess.run(command, env=env, stdout=log, stderr=subprocess.PIPE, text=True, timeout=90)
        wall, after = perf_counter() - start, usage()
    write(output / f"{arm}-clock.json", dict(elapsed_s=wall, status=process.returncode, stderr=process.stderr[-2000:],
          **{key: value - before[key] for key, value in after.items()}))
    process.check_returncode()


def run(output, geographic, stock_first=False, paired_eight_ms=None, frontier_libraries=None,
        matched_warm=False, skip_empty_proof=False):
    from leo.storage.fast_scan import FastScanStore
    from tools.pipeline_eval.qualification.cache_residency import bound_snapshot, load_query

    system = host()
    original = read(checked(REFERENCE, REFERENCE_PIN))
    request = assigned(Path(original["short_binary"]))
    if any(request[key] != original[key] for key in request):
        raise ValueError("Assignment no longer matches the sealed weak recording")
    if paired_eight_ms is not None:
        if frontier_libraries or skip_empty_proof:
            raise ValueError("The aperture comparison uses its frozen solver configuration")
        checked(paired_eight_ms, EIGHT_MS_SHA)
    else:
        checked(STOCK, STOCK_PIN)
    checked(geographic, GEOGRAPHIC_SHA)
    output.mkdir()
    store = FastScanStore(output)
    recording = Path(request["recording"])
    session, digest, inventory = store.inventory(recording, verify_windows=False)
    if (session, digest, inventory["window_count"]) != (request["session"], original["inventory_sha256"], ISSUED):
        raise ValueError("Expected original inventory")
    members = tuple((Path(item["path"]) / "manifest.json", item["manifest_digest"]) for item in inventory["segments"])
    query = load_query(checked(CACHE_LIB, CACHE_SHA))
    env = environment(output)
    python = str(RELEASE / "venv/bin/python")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    args = ["--recording", str(recording), "--archive", request["archive"]["root"], "--region", request["region_file"]]
    common = [python, "-BPs", str(HERE / "full_short_run.py"), *args,
              "--geographic-library", str(geographic), "--track-graph", "installed",
              "--reuse-cold-track-rows", "--reuse-grid-phase-states"]
    if paired_eight_ms is not None:
        order = ("12ms", "8ms")
        commands = {
            "12ms": [*common, "--short-binary", request["short_binary"], "--output", str(output / "12ms")],
            "8ms": [*common, "--short-binary", str(paired_eight_ms), "--eight-ms-primary", "--output", str(output / "8ms")],
        }
    else:
        order = ("stock", "candidate") if stock_first else ("candidate", "stock")
        commands = {
            "candidate": [*common, "--short-binary", request["short_binary"], "--output", str(output / "candidate")],
            "stock": [str(STOCK), *args, "--bulk-root", str(output / "stock")],
        }
        if frontier_libraries:
            block, tracks = frontier_libraries
            commands["candidate"][2] = str(HERE / "combined_frontier_run.py")
            commands["candidate"].extend(["--frontier-block-library", str(block), "--regional-track-library", str(tracks)])
        if skip_empty_proof:
            commands["candidate"].append("--skip-empty-proof")
        (output / "stock").mkdir()
    write(output / "binding.json", dict(machine=system, commands=commands, order=order, request=request, inventory=digest))
    if paired_eight_ms is not None:
        from triage_bounds import require_full_cache, warm_recording

        initial = bound_snapshot(store, recording, members, os.sysconf("SC_PAGE_SIZE"), query)
        write(output / "initial-cache.json", initial)
        if initial["cached_pages"] != initial["observed_file_pages"]:
            cpu, start = process_time(), perf_counter()
            warm_recording(members)
            write(output / "cache-prime-clock.json", dict(cpu_s=process_time()-cpu, elapsed_s=perf_counter()-start))
    for arm in order:
        cache = bound_snapshot(store, recording, members, os.sysconf("SC_PAGE_SIZE"), query)
        if matched_warm:
            from short_raw_diagnostic import require_warm, warm_recording
            initial = cache
            start = perf_counter()
            if initial["cached_pages"] != initial["observed_file_pages"]:
                warm_recording(members)
                cache = bound_snapshot(store, recording, members, os.sysconf("SC_PAGE_SIZE"), query)
            require_warm(cache)
            write(output / f"{arm}-conditioning.json", dict(initial=initial, elapsed_s=perf_counter()-start))
        if cache["members"] != cache["observed_members"]:
            raise ValueError("Incomplete cache observation")
        write(output / f"{arm}-before.json", cache)
        if paired_eight_ms is not None:
            require_full_cache(cache)
        measure(commands[arm], env, output, arm)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("geographic", type=Path)
    order = parser.add_mutually_exclusive_group()
    order.add_argument("--stock-first", action="store_true")
    order.add_argument("--paired-eight-ms", type=Path)
    parser.add_argument("--frontier-libraries", type=Path, nargs=2, metavar=("BLOCK", "TRACKS"))
    parser.add_argument("--matched-warm", action="store_true")
    parser.add_argument("--skip-empty-proof", action="store_true")
    run(**vars(parser.parse_args()))
