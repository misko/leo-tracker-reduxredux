"""Pin source and inputs, then run checksum-only stored-native receiver pairs."""

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from uuid import uuid4

from .. import iq_service, whole_iq
from ..__main__ import THREAD_ENV, encoded, local_output, save_json, write
from ..original_receiver import CALIBRATION, receiver_assets
from ..variants import final_region, track_preparation
from . import arm_execution_trial, capture_whole, sequential_fix_trial
from .full_v5_check import FROZEN, _sha
from .whole_memory_chain_worker import memory

REPORT = sequential_fix_trial.SCREEN / "native-receiver/catalog-checksum"
MODULE = "tools.pipeline_eval.qualification.catalog_bench"
WORKER = Path(__file__).with_name("catalog_bench_worker.py")
BRANCHES = ("installed", "frozen_checksum")
CPUS = (16, 17)
CAP = 180


def roster():
    prior = [
        sequential_fix_trial.SCREEN / "original-schedule/track-preparation/source-lock.json",
        arm_execution_trial.REPORT / "source-lock.json",
    ]
    excluded = set(sequential_fix_trial.EXCLUDED)
    for path in prior:
        excluded.update(whole_iq.read(path)["cases"])
    panels = whole_iq.read(FROZEN / "panels.json")
    inventory = sequential_fix_trial.inventory()
    eligibility, selected = {}, []
    for family, panel, limit in (("DS26", "ds26-common127", 2), ("DS29", "roof16", 1)):
        ranked = sorted(
            (r["recording"]["segments"][0]["sha256"], ident)
            for ident, r in inventory.items()
            if ident.startswith(family)
            and ident in panels[panel]
            and ident not in excluded
            and all(r.get(k) for k in ("request", "catalog", "track_config", "native", "recording"))
        )
        attempted, count = [], 0
        for digest, ident in ranked:
            row = dict(id=ident, first_manifest_sha256=digest)
            attempted.append(row)
            try:
                spec = sequential_fix_trial.prepare_recording(ident)
            except (ValueError, KeyError, OSError) as error:
                row["error"] = str(error)
                continue
            selected.append(spec)
            count += 1
            if count == limit:
                break
        if count != limit:
            raise ValueError(f"insufficient complete {family} recordings")
        eligibility[family] = dict(ranked=ranked, attempted=attempted)
    n_first, n_shifted, s_first = selected
    cases = {}
    for spec, role, cpu, order in (
        (n_first, "original", CPUS[0], BRANCHES),
        (n_shifted, "shifted", CPUS[1], BRANCHES),
        (s_first, "original", CPUS[0], BRANCHES[::-1]),
    ):
        tile = sequential_fix_trial.omitted(spec["tile"]) if role == "shifted" else spec["tile"]
        spec = spec | {"tile": {"width_km": 25.0} | tile}
        cases[spec["id"]] = dict(spec=spec, role=role, cpu=cpu, order=list(order))
    return dict(
        cases=cases,
        sequence=[n_first["id"], s_first["id"], n_shifted["id"]],
        eligibility=eligibility,
        exclusions=dict(prior={str(p): _sha(p) for p in prior}, ids=sorted(excluded)),
    )


def freeze(work, production, expected):
    if (REPORT / "source-lock.json").exists():
        raise FileExistsError("the source and roster have already been sealed")
    path = whole_iq.checked(production, expected)
    source = path.read_bytes()
    lock = roster() | dict(
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        research_files={
            str(p): _sha(p)
            for p in (
                Path(__file__),
                WORKER,
                Path(track_preparation.__file__),
                Path(iq_service.__file__),
            )
        },
        production_source=str(production),
        production_sha256=expected,
        receiver=str(CALIBRATION),
        installed_files=receiver_assets(CALIBRATION),
        cap_s=CAP,
        memory_max=whole_iq.MEMORY,
        swap_max=0,
    )
    work.mkdir()
    snapshot = work / "production-propagation.py"
    write(snapshot, source)
    whole_iq.checked(snapshot, expected)
    save_json(work / "source-lock.json", lock)
    save_json(REPORT / "source-lock.json", lock)


def worker(folder):
    plan = whole_iq.read(folder / "plan.json")
    work = folder.parents[1]
    lock = whole_iq.read(whole_iq.checked(work / "source-lock.json", plan["source_sha256"]))
    for filename, digest in lock["research_files"].items():
        whole_iq.checked(Path(filename), digest)
    row = lock["cases"][plan["id"]]
    spec = row["spec"]
    receiver = Path(lock["receiver"])
    before = memory()
    start = perf_counter()
    if receiver_assets(receiver) != lock["installed_files"] or before["cpus"] != [row["cpu"]]:
        raise ValueError("position worker is outside its pinned receiver or CPU")
    compact = arm_execution_trial.compact(spec)
    snapshots = {p.name: _sha(p) for p in Path(compact["archive"]).rglob("*.tle")}
    if snapshots != {k: v.removeprefix("sha256:") for k, v in spec["snapshots"].items()}:
        raise ValueError("causal TLE input differs from the original sealed request")
    request = dict(
        compact,
        native_backend=str(receiver / "native/manifest.json"),
        library=str(receiver / "projector.so"),
    )
    subprocess.run(
        [sys.executable, "-IB", str(WORKER), "position", str(folder)],
        input=encoded(request),
        check=True,
    )
    result = whole_iq.read(folder / "numerical.json")
    publication = final_region.publish(
        result["numerical"], spec["tile"], enabled=row["role"] == "shifted"
    )
    save_json(
        folder / "worker-result.json",
        dict(
            publication=publication,
            start=before,
            end=memory(),
            worker_wall_s=perf_counter() - start,
        ),
    )


def attempt(work, ident, row, branch):
    path = work / ident / branch
    path.mkdir(parents=True)
    cpu = row["cpu"]
    save_json(
        path / "plan.json",
        dict(
            id=ident,
            branch=branch,
            cpus=[cpu],
            limit_s=CAP,
            source_sha256=_sha(work / "source-lock.json"),
        ),
    )
    unit = "leo-iq-bench-" + uuid4().hex[:12]
    command = capture_whole.service(
        unit,
        CAP,
        [
            f"--setenv=TMPDIR={path}",
            *(f"--setenv={k}={v}" for k, v in THREAD_ENV.items()),
            "taskset",
            "-c",
            str(cpu),
            sys.executable,
            "-B",
            "-m",
            MODULE,
            "worker",
            str(path),
        ],
    )
    receipt = iq_service.run(path, command, unit, timeout=CAP + 20)
    print(ident, branch, receipt["systemd"]["Result"], flush=True)


def run(work):
    lock = whole_iq.read(
        whole_iq.checked(work / "source-lock.json", _sha(REPORT / "source-lock.json"))
    )

    def lane(cpu):
        for ident in lock["sequence"]:
            row = lock["cases"][ident]
            if row["cpu"] == cpu:
                for branch in row["order"]:
                    attempt(work, ident, row, branch)

    with patch.object(iq_service, "MODULE", MODULE), ThreadPoolExecutor(len(CPUS)) as pool:
        list(pool.map(lane, CPUS))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "worker", "run"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("--production", type=Path)
    parser.add_argument("--sha256")
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work, args.production, args.sha256)
    elif args.action == "run":
        run(args.work)
    else:
        worker(args.work)


if __name__ == "__main__":
    main()
