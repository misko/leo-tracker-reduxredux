"""Measure full compact fits on sealed, matched offers of recorded original GLRT."""

import argparse
import gzip
from concurrent.futures import ThreadPoolExecutor
from math import cos, radians
from pathlib import Path
from unittest.mock import patch

from .. import cavity_runtime, iq_service, whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..original_receiver import CALIBRATION, receiver_assets
from . import sequential_fix_trial as sequential
from .full_v5_check import _sha

ROOT = sequential.ROOT
REPORT = sequential.SCREEN / "pilot-search-and-region/final-region"
CPUS = (8, 9, 10, 11)
ATTEMPTS = "prospective-attempts.jsonl.gz"


def offers(tile, index):
    lat, lon = tile["center"]
    longitude_km = 111.32 * cos(radians(lat))
    compass = ((30, 0), (0, 30), (-30, 0))
    offsets = ((16, 0), (20, 0), compass[index % len(compass)])
    return [
        dict(
            center=[lat + north / 111.0, lon + east / longitude_km],
            width_km=25.0,
            id=f"offer-{number + 1}",
        )
        for number, (east, north) in enumerate(offsets)
    ]


def stage(work, report):
    previous = whole_iq.read(sequential.REPORT / "source-lock.json")
    exclude = previous["cases"].keys() | {"DS26-0036", "DS26-0070", "DS26-0102"}
    inventory = sequential.inventory()
    cases, eligibility = {}, {}
    for family in ("DS26", "DS29"):
        ranked = sorted(
            (row["recording"]["segments"][0]["sha256"], ident)
            for ident, row in inventory.items()
            if row["panel"] == family
            and ident not in exclude
            and all(
                row.get(k) for k in ("recording", "request", "native", "catalog", "track_config")
            )
        )
        eligibility[family] = []
        included = 0
        for digest, ident in ranked:
            note = dict(id=ident, first_manifest_sha256=digest)
            eligibility[family].append(note)
            try:
                spec = sequential.prepare_recording(ident)
            except (KeyError, OSError, ValueError) as error:
                note["ineligible"] = str(error)
                continue
            cases[ident] = dict(spec=spec, offers=offers(spec["tile"], included))
            included += 1
            if included == 3:
                break
        if included != 3:
            raise ValueError(f"expected three new authenticated {family} recordings")

    preflight = report / "preflight-source-lock.json"
    if preflight.is_file() and cases != whole_iq.read(preflight)["cases"]:
        raise ValueError("the path correction must preserve all registered recordings and offers")
    work.mkdir(parents=True, exist_ok=False)
    receivers = {}
    for tile in next(iter(cases.values()))["offers"]:
        folder = work / tile["id"]
        folder.mkdir()
        installed = cavity_runtime.install(folder / "receiver", profile="phase-release")
        receivers[tile["id"]] = receiver_assets(installed)
    sources = (
        Path(__file__),
        Path(sequential.__file__),
        sequential.WORKER,
        sequential.WORKER.with_name("short_compact.py"),
        sequential.WORKER.with_name("short_compact_worker.py"),
        Path(iq_service.__file__),
    )
    plan = dict(
        cases=cases,
        exclude=sorted(exclude),
        eligibility=eligibility,
        assignments=[
            dict(id=ident, offer=tile["id"], cpu=CPUS[(index + number) % len(CPUS)])
            for index, (ident, case) in enumerate(cases.items())
            for number, tile in enumerate(case["offers"])
        ],
        limit_s=sequential.CAPS["full"],
        memory_bytes=whole_iq.MEMORY,
        swap_max_bytes=0,
        receiver=str(CALIBRATION),
        receiver_files=receivers,
        protocol_sha256=_sha(report / "PROTOCOL.md"),
        sources={str(path.relative_to(ROOT)): _sha(path) for path in sources},
    )
    save_json(report / "prospective-source-lock.json", plan)
    write(work / "lock.sha256", (_sha(report / "prospective-source-lock.json") + "\n").encode())
    for job in plan["assignments"]:
        print(job, flush=True)


def verified_plan(work, report):
    path = report / "prospective-source-lock.json"
    plan = whole_iq.read(whole_iq.checked(path, (work / "lock.sha256").read_text().strip()))
    whole_iq.checked(report / "PROTOCOL.md", plan["protocol_sha256"])
    for path, digest in plan["sources"].items():
        whole_iq.checked(ROOT / path, digest)
    for offer, files in plan["receiver_files"].items():
        if receiver_assets(work / offer / "receiver") != files:
            raise ValueError("installed compact receiver changed from the source lock")
    return plan


def execute(work, report):
    plan = verified_plan(work, report)

    def lane(cpu):
        rows = []
        for job in plan["assignments"]:
            if job["cpu"] != cpu:
                continue
            case = plan["cases"][job["id"]]
            tile = next(t for t in case["offers"] if t["id"] == job["offer"])
            spec = dict(case["spec"], tile=tile)
            doc = whole_iq.read(whole_iq.checked(Path(spec["native"]), spec["native_sha256"]))
            intervals = sequential.short_compact.scopes(doc)
            folder = work / tile["id"]
            row = sequential.attempt(folder, spec, doc, intervals, "original", cpu, "full")
            rows.append(dict(row, offer=tile["id"]))
        return rows

    with (
        patch.object(iq_service, "MODULE", sequential.MODULE),
        ThreadPoolExecutor(max_workers=len(CPUS)) as pool,
    ):
        rows = [row for group in pool.map(lane, CPUS) for row in group]
    if plan != verified_plan(work, report):
        raise ValueError("prospective source lock changed during measurement")
    rows.sort(key=lambda row: (row["id"], row["offer"]))
    write(report / ATTEMPTS, gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0))
    names = ("prospective-source-lock.json", ATTEMPTS)
    save_json(
        report / "prospective-prediction-lock.json",
        dict(attempts=len(rows), files={name: _sha(report / name) for name in names}),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "run"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("--report", type=local_output, default=REPORT)
    args = parser.parse_args()
    if args.action == "stage" and (args.report / "prospective-source-lock.json").is_file():
        parser.error("prospective inputs are already registered")
    if args.action == "run" and (args.report / "prospective-prediction-lock.json").is_file():
        parser.error("prospective predictions are already sealed")
    (stage if args.action == "stage" else execute)(args.work, args.report)


if __name__ == "__main__":
    main()
