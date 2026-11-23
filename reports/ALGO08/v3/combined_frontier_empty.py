"""Run the identical composite CLI on the small original withheld recording."""

import argparse
from contextlib import ExitStack
import gzip
import json
import mmap
from pathlib import Path
from statistics import median
import subprocess
from time import perf_counter

from aperture_trial import RELEASE, read, write
from combined_frontier_run import BLOCK_SHA, HERE, verify
from dense_geographic_trial import host
from full_short_physical import environment
from local_future_cli_trial import cache_before
from short_raw_diagnostic import (
    CACHE_LIB, CACHE_SHA, CASES, FastScanStore, assignment, cache_residency, checked, measure, pairs, science,
)
from triage_bounds import ShortWindowReader, confined_path


def gates(times):
    if not times or any(min(pair) <= 0 for pair in times):
        raise ValueError("Expected positive paired elapsed times")
    return median(c/s for s, c in times), sum(c for s, c in times)/sum(s for s, c in times)


def run(root, block, skip_empty_proof=False, weak_receipt=None):
    machine = host()
    case, pin, expected, visits, order = CASES[0]
    if (case, visits, expected, order) != ("DS30-0227", 18, "withheld", ("stock", "candidate")):
        raise ValueError("Changed tiny DS30 enrollment")
    reference = read(HERE / "measurements/local-future-cli-DS30-0227.json")
    pair, archived = assignment(case, pin, expected, visits)
    verify(block, BLOCK_SHA)
    pairs.verified_v3(pairs.NAMED_V3)
    root.mkdir()
    (root / "stock").mkdir()
    env = environment(root)
    python = str(RELEASE / "venv/bin/python")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    recording = Path(pair["recording"])
    store = FastScanStore(root)
    session, inventory_pin, inventory = store.inventory(recording, verify_windows=False)
    if session != archived["receipt"]["session_id"] or inventory["window_count"] != visits:
        raise ValueError("Changed source inventory")
    manifests = tuple((Path(r["path"])/"manifest.json", r["manifest_digest"]) for r in inventory["segments"])
    query = cache_residency.load_query(checked(CACHE_LIB, CACHE_SHA))
    libs = {k: v["path"] for k, v in reference["libraries"].items()}
    common = ["--recording", str(recording), "--region", pair["region"], "--archive", pair["archive"]["root"]]
    commands = dict(stock=[str(pairs.NAMED_V3), *common, "--bulk-root", str(root/"stock")],
                    candidate=[python, "-BPs", str(HERE/"combined_frontier_run.py"), *common, "--short-binary",
                               libs["short"], "--geographic-library", libs["geographic"], "--regional-track-library",
                               libs["regional"], "--frontier-block-library", str(block), "--track-graph", "installed",
                               "--reuse-cold-track-rows", "--reuse-grid-phase-states", "--output", str(root/"candidate")])
    runs = {}
    if skip_empty_proof:
        commands["candidate"].append("--skip-empty-proof")
    with ExitStack() as scope:
        start = perf_counter()
        mapped_bytes = sampled_pages = 0
        for manifest, digest in manifests:
            reader = ShortWindowReader(manifest.parent)
            if reader.manifest_sha256 != digest:
                raise ValueError("Changed manifest during cache conditioning")
            for chunk in reader.manifest.chunks:
                mapped_bytes += chunk.compressed_bytes
                if mapped_bytes > 32*1024**2:
                    raise ValueError("Expected the small withheld control")
                member = confined_path(reader.path, reader.path/chunk.payload_relative_path, must_exist=True)
                stream = scope.enter_context(member.open("rb"))
                view = scope.enter_context(mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ))
                sampled_pages += len(view[::mmap.PAGESIZE])
        conditioning_s = perf_counter() - start
        for arm in order:
            cache = cache_before(store, recording, manifests, query)
            timing = measure(commands[arm], env, root/arm)
            write(root/f"{arm}-time.json", timing)
            if timing["exit_code"]:
                raise RuntimeError(timing["stderr_tail"])
            results = science(root, arm, timing, archived, inventory_pin)
            if (results["native_sha256"] != reference["raw"][arm]["verified"]["native_sha256"]
                    or results["reason"] != "no_active_curvature" or results["decision"] != expected or results["pngs"]):
                raise ValueError("Changed detector or withheld result")
            runs[arm] = dict(cache=cache, timing=timing, verified=results, command=commands[arm])
    weak_receipt = weak_receipt or HERE/"measurements/combined-frontier-weak-warm.json.gz"
    warm = json.loads(gzip.decompress(weak_receipt.read_bytes()))
    if warm["composition"].get("skip_empty_proof", False) != skip_empty_proof:
        raise ValueError("Cannot pool two different candidate configurations")
    ratios = gates([(warm["runs"]["stock"]["clock"]["elapsed_s"], warm["runs"]["candidate"]["clock"]["elapsed_s"]),
                    (runs["stock"]["timing"]["elapsed_s"], runs["candidate"]["timing"]["elapsed_s"])])
    write(root/"result.json", dict(case=case, machine=machine, inventory=inventory_pin, runs=runs,
          read_only_conditioning=dict(bytes=mapped_bytes, pages=sampled_pages, elapsed_s=conditioning_s),
          composition=read(root/"candidate/combined-frontier.json"), paired_warm_median_and_sum=ratios))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("block", type=Path)
    parser.add_argument("--skip-empty-proof", action="store_true")
    parser.add_argument("--weak-receipt", type=Path)
    run(**vars(parser.parse_args()))
