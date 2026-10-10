"""One explicit member/phase slice; no automatic retry or membership selection."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from continuation import continue_slice
from ports import ROOT, dependencies
from search import search_slice

HERE = Path(__file__).resolve().parent


def verify(plan):
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        if os.environ.get(name) != "1":
            raise ValueError("one thread per worker required")
    if plan["policy"] != POLICY:
        raise ValueError("numerical/budget policy changed")
    for group in ("source_sha256", "input_sha256"):
        for name, expected in plan[group].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError("closure changed: " + name)


POLICY = dict(
    search_slices=6,
    slice_seconds=500,
    continuation_slices_per_branch=2,
    workers=2,
    threads=1,
    point_budget=400,
    levels_km=[40.0, 20.0, 10.0, 5.0],
    discovery_arm="fitted-c",
    modes=["native", "fixed"],
    basins=3,
    separation_km=12.5,
    local_radius_km=25.0,
    fresh_native=True,
    final_arms=["zero-c", "fitted-c"],
    fallback="none",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label")
    parser.add_argument("phase", choices=("search", "native", "fixed"))
    parser.add_argument("--protocol", type=Path, default=HERE / "protocol.json")
    parser.add_argument("--output", type=Path, default=HERE / "results")
    args = parser.parse_args()
    plan = json.loads(args.protocol.read_text())
    verify(plan)
    selected = [m for m in plan["members"] if m["label"] == args.label]
    if len(selected) != 1:
        raise ValueError("label outside fixed cohort")
    member = selected[0]
    entry, driver, adapter = dependencies()
    loader = entry.make_loader(ROOT, member["binding"])
    directory = args.output / args.label
    if args.phase == "search":
        result = search_slice(plan, member, directory / "search", loader, driver)
    else:
        result = continue_slice(
            plan,
            member,
            args.phase,
            directory / args.phase,
            directory / "search",
            loader,
            driver,
            adapter,
        )
    print(args.label, args.phase, result["status"], flush=True)


if __name__ == "__main__":
    main()
