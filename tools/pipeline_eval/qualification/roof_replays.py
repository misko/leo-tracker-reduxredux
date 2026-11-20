"""Measure the extra receiver outputs used by the per-modification roof figures."""

import argparse
import gzip
import hashlib
import importlib
import json
import os
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .. import corpus
from ..__main__ import THREAD_ENV, encoded, local_output, public_cases, references, write
from ..scoring import validate_result

REGIONAL = (
    "orbit_interp",
    "shape_score",
    "track_reduce",
    "track_link",
    "projected_fit",
    "shared_doppler",
    "arc_validation",
)


def four_offers(case, inventory):
    entry = inventory[case["id"]]
    for key in ("observation", "catalog"):
        with Path(case[key + "_path"]).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != entry[key + "_sha256"]:
                raise ValueError(f"{case['id']} {key} differs from the original four-region trial")
    return entry["regions"]


def regional_positions(method, case, offers, directory):
    """Run the measured candidate on each offer, reusing its observation across the two searches."""
    from ..reference import receiver

    variant = importlib.import_module(f"tools.pipeline_eval.variants.{method}")
    observation = json.loads(Path(case["observation_path"]).read_bytes())
    catalogue = Path(case["catalog_path"]).read_bytes()
    solve = receiver.solve
    if method == "track_link":
        observation, *_ = variant._replay(Path(case["native_path"]), variant.Tracker())
        observation["catalog_timestamp_ns"] = variant._catalog_timestamp(case)
    elif method == "shape_score":
        solve = variant.solve
    elif method == "track_reduce":
        observation, _ = variant._reduce(observation)
    measured = []
    for mode, regions in offers.items():
        if method in ("projected_fit", "shared_doppler", "arc_validation"):
            result = variant.run(dict(case, regions=regions), directory)
        else:
            if method == "orbit_interp":
                solution = variant._trial(observation, regions, catalogue, cached=True).result
            else:
                solution = solve(observation, regions, catalogue)
            arm = dict(latlon=solution["latlon"], forced_latlon=solution["best_latlon"])
            result = dict(
                status="ok" if arm["latlon"] is not None else "withheld",
                reason=solution["reason"],
                boundary=f"{method} to regional position decision",
                metrics=dict(calibration_invariant=True),
                arms={"c0": arm, "fitted_c": arm},
            )
        measured.append((method, mode, result))
    return measured


def collect(item):
    method, case, regions, both, controls = item
    with tempfile.TemporaryDirectory(prefix="roof-figure-") as directory:
        if method == "frontends":
            from .pilot_positions import frontends

            measured = frontends(case, regions, Path(directory), controls)
        else:
            offers = {"four": regions}
            if both:
                offers["one"] = case["regions"]
            measured = regional_positions(method, case, offers, Path(directory))
    rows = []
    for name, mode, result in measured:
        validate_result(result)
        if result["status"] not in ("ok", "withheld"):
            raise ValueError(f"{case['id']} / {name} / {mode}: {result.get('reason')}")
        offered = case["regions"] if mode == "one" else regions
        rows.append(
            dict(
                id=case["id"],
                method=name,
                offers=mode,
                regions_sha256=hashlib.sha256(encoded(offered)).hexdigest(),
                result=result,
            )
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", choices=("roof16", "ds26-common127", "smoke"), default="roof16")
    parser.add_argument(
        "--method", choices=(*REGIONAL, "frontends"), action="append", required=True
    )
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--case", action="append")
    parser.add_argument(
        "--both-offers", action="store_true", help="also rerun the original single tile"
    )
    parser.add_argument(
        "--check-peak-controls",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="compare both modified Python GLRT peak searches to their controls",
    )
    parser.add_argument(
        "--cache", type=Path, default=Path.home() / ".cache/leo/pipeline-eval/inputs"
    )
    parser.add_argument("--out", type=Path, required=True, help="local .jsonl.gz result file")
    args = parser.parse_args()
    if args.jobs < 1 or not args.out.name.endswith(".jsonl.gz"):
        parser.error("pass a positive job count and a .jsonl.gz output file")
    os.environ.update(THREAD_ENV)
    panel, refs = references(args.panel, args.case)
    cases = public_cases(panel, refs, local_output(args.cache))
    offers = json.loads((corpus.FROZEN / "roof-four-offers.json").read_bytes())
    jobs = [
        (m, c, four_offers(c, offers), args.both_offers, args.check_peak_controls)
        for c in cases
        for m in dict.fromkeys(args.method)
    ]
    rows = []
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for measured in pool.map(collect, jobs):
            rows.extend(measured)
            print(measured[0]["id"], measured[0]["method"], len(measured), flush=True)
    content = b"".join(encoded(row) + b"\n" for row in rows)
    write(args.out, gzip.compress(content, mtime=0))


if __name__ == "__main__":
    main()
