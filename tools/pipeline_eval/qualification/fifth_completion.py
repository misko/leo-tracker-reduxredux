"""Complete the missing fifth-center arms of the frozen whole-IQ stock roster."""

import argparse
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import capture_release, fresh_replay, whole_center_union, whole_fftw_raw
from .full_v5_check import _sha

SCREEN = whole_center_union.SCREEN
REPORT = SCREEN / "latency-and-support/fifth-completion"
WORK = Path("/var/tmp/leo-fifth-completion-20261119")
MODULE = "tools.pipeline_eval.qualification.fifth_completion"
METHOD = "fifth_completion_candidate"
STOCK = SCREEN / "track-recovery/wide-roster"
LANES = ([12, 13], [14, 15], [16, 17])
PINS = {
    "track-recovery/wide-roster/roster-lock.json": (
        "2f9e7f380445b076a8d16efc8317c9b70ed9eb01b7a1d8cd13fda9721e937fd8"
    ),
    "track-recovery/wide-roster/all-figure-lock.json": (
        "cc04b4499bece1da0a447cb965d5c6998a463cfdb850e5169a94194445fa24e3"
    ),
    "arrival-and-timing/fresh-replay/eight-figure-lock.json": (
        "7520dee62bdd2e62e910861f0aadee1f561dfc51dae36c3c19a3639cfc0adf29"
    ),
    "arrival-and-timing/fresh-replay/source-lock.json": (
        "296d02593f0c55b693f05928d74b67eb4505115fad5424b2c2f5efb0b0ee7d4b"
    ),
}


def roster(primary, chart, paired):
    stock = set(primary)
    previous = set(paired)
    remaining = stock - previous
    if (
        len(stock) != 12
        or len(chart) != 12
        or set(chart) != stock
        or len(paired) != 8
        or len(previous) != 8
        or len(remaining) != 10
    ):
        raise ValueError("the two authenticated rosters must have exactly two shared cases")
    return sorted(remaining)


def freeze(work):
    report = REPORT / "source-lock.json"
    if report.exists() or work.exists():
        raise FileExistsError("the completion roster is already frozen")
    frozen = {
        name: whole_iq.read(whole_iq.checked(SCREEN / name, sha)) for name, sha in PINS.items()
    }
    stock, chart, paired, release = frozen.values()
    selected = roster(stock["primary"], chart["cases"], paired["cases"])
    cases = {}
    stock_sources = {}
    for idx, ident in enumerate(selected):
        study = stock["primary"][ident]
        provenance = stock["studies"][study]
        folder = SCREEN / provenance["path"]
        if study not in stock_sources:
            seal = whole_iq.read(
                whole_iq.checked(folder / "prediction-lock.json", provenance["prediction_sha256"])
            )
            if seal["files"]["source-lock.json"] != provenance["source_sha256"]:
                raise ValueError("stock source changed after the original roster freeze")
            stock_sources[study] = whole_iq.read(
                whole_iq.checked(folder / "source-lock.json", provenance["source_sha256"])
            )
        original = stock_sources[study]["cases"][ident]
        case, request = whole_iq.binding(ident)
        capture = capture_release.read_capture(case)
        if (
            original["recording"] != case["recording"]
            or original["tile"] != case["regions"][0]
            or original["catalog_sha256"] != case["catalog"]["sha256"]
            or original.get("request_sha256", original.get("frozen_request_sha256"))
            != case["request"]["sha256"]
        ):
            raise ValueError(f"current waveform or request changed for {ident}")
        cases[ident] = dict(
            id=ident,
            cpus=LANES[idx % len(LANES)],
            cohort="completion",
            stock=provenance,
            capture_native_sha256=case["native"]["sha256"],
            request_sha256=case["request"]["sha256"],
            catalog_sha256=case["catalog"]["sha256"],
            tile=case["regions"][0],
            recording=case["recording"],
            clock_authority=capture["input_manifest_sha256"],
            orbit_snapshots=request["causal_snapshots"],
        )
    programs = release["programs"] | {str(Path(__file__).relative_to(ROOT)): _sha(Path(__file__))}
    plan = dict(
        cases=cases,
        roster_authorities=PINS,
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        memory_max=whole_iq.MEMORY,
        swap_max=0,
        limit_s=450,
        programs=programs,
        **{k: release[k] for k in ("detectors", "receiver", "receiver_files", "native_sources")},
    )
    inputs(plan)
    work.mkdir(parents=True, exist_ok=False)
    save_json(work / report.name, plan)
    save_json(report, plan)
    for ident, case in cases.items():
        print(ident, case["cpus"], case["clock_authority"], flush=True)


def inputs(plan):
    whole_iq.checked(REPORT / "PROTOCOL.md", plan["protocol_sha256"])
    for name, digest in plan["programs"].items():
        whole_iq.checked(ROOT / name, digest)
    for entry in plan["detectors"].values():
        whole_iq.checked(Path(entry["path"]), entry["sha256"])


def source(work):
    path = REPORT / "source-lock.json"
    plan = whole_iq.read(whole_iq.checked(work / path.name, _sha(path)))
    inputs(plan)
    return plan


def run(work, lane):
    plan = source(work)
    with patch.object(fresh_replay, "MODULE", MODULE), fresh_replay.hinted(plan):
        for ident, case in plan["cases"].items():
            if case["cpus"] == LANES[lane]:
                whole_center_union.service(
                    work, ident, "candidate", plan, evaluator=fresh_replay.runtime.evaluate
                )


def worker(path):
    plan = source(path.parents[1])
    whole_fftw_raw.library(Path(plan["detectors"]["candidate"]["path"]))
    with patch.object(fresh_replay, "MODULE", MODULE), fresh_replay.hinted(plan):
        fresh_replay.runtime.worker(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "worker"))
    parser.add_argument("attempt", type=local_output, nargs="?")
    parser.add_argument("--work", type=local_output, default=WORK)
    parser.add_argument("--lane", type=int, choices=range(len(LANES)))
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    elif args.action == "worker" and args.attempt is not None:
        worker(args.attempt)
    elif args.action == "run" and args.lane is not None:
        run(args.work, args.lane)
    else:
        parser.error("worker requires a path; run requires a lane")
