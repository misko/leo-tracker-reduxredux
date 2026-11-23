"""Measure the complete raw combination against named v3 on one saved recording."""

import argparse
import os
import subprocess
from pathlib import Path
from time import perf_counter

from aperture_trial import RELEASE, read, write
from dense_full_short_raw import checked, usage
from dense_geographic_trial import host
from full_short_physical import CACHE_LIB, CACHE_SHA, ISSUED, assigned, environment
from full_short_run import GEOGRAPHIC_SHA

HERE = Path(__file__).resolve().parent
STOCK = Path("/opt/leo-algo08/algo08v3/run")
STOCK_PIN = "fae032526227f55ca2419a0b29c69afc7fc97fa04508f33d0403802934f13448"
REFERENCE = Path("/var/tmp/leo-full-short-DS30-0016-pair/request.json")
REFERENCE_PIN = "d58723098826fc7e1478f92880dffdb500bcb3f5225b4d64a4b2949cfbceab06"


def run(output, geographic, stock_first=False):
    from leo.storage.fast_scan import FastScanStore
    from tools.pipeline_eval.qualification.cache_residency import bound_snapshot, load_query

    system = host()
    original = read(checked(REFERENCE, REFERENCE_PIN))
    request = assigned(Path(original["short_binary"]))
    if any(request[key] != original[key] for key in request):
        raise ValueError("Assignment no longer matches the sealed weak recording")
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
    commands = {
        "candidate": [python, "-BPs", str(HERE / "full_short_run.py"), *args, "--short-binary", request["short_binary"],
                      "--geographic-library", str(geographic), "--track-graph", "installed", "--reuse-cold-track-rows",
                      "--reuse-grid-phase-states", "--output", str(output / "candidate")],
        "stock": [str(STOCK), *args, "--bulk-root", str(output / "stock")],
    }
    (output / "stock").mkdir()
    order = ("stock", "candidate") if stock_first else ("candidate", "stock")
    write(output / "binding.json", dict(machine=system, commands=commands, order=order, request=request, inventory=digest))
    for arm in order:
        command = commands[arm]
        cache = bound_snapshot(store, recording, members, os.sysconf("SC_PAGE_SIZE"), query)
        if cache["members"] != cache["observed_members"]:
            raise ValueError("Incomplete cache observation")
        write(output / f"{arm}-before.json", cache)
        with (output / f"{arm}-stdout").open("x") as log:
            before, start = usage(), perf_counter()
            process = subprocess.run(command, env=env, stdout=log, stderr=subprocess.PIPE, text=True, timeout=90)
            wall, after = perf_counter() - start, usage()
        write(output / f"{arm}-clock.json", dict(elapsed_s=wall, status=process.returncode, stderr=process.stderr[-2000:],
              **{key: value - before[key] for key, value in after.items()}))
        process.check_returncode()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("geographic", type=Path)
    parser.add_argument("--stock-first", action="store_true")
    run(**vars(parser.parse_args()))
