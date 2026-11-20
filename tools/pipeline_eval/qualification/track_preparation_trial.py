"""Run matched stored-native track preparation and position services."""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from uuid import uuid4

from .. import iq_service, whole_iq
from ..__main__ import THREAD_ENV, local_output, save_json, write
from ..original_receiver import CALIBRATION, receiver_assets
from ..variants import final_region, track_preparation
from . import arm_execution_trial as compact_trial
from . import capture_whole, sequential_fix_trial, track_preparation_profile
from .full_v5_check import FROZEN, _sha
from .whole_memory_chain_worker import memory

SCREEN = sequential_fix_trial.SCREEN
REPORT = SCREEN / "original-schedule/track-preparation"
PRIOR_EDGE = SCREEN / "receiver-core/measured-boundary-policy"
EDGE_CASE = "DS26-0102"
DENSE_CASE = "DS29-0247"
CAP = 180
MODULE = "tools.pipeline_eval.qualification.track_preparation_trial"


def select():
    earlier = compact_trial.REPORT / "source-lock.json"
    excluded = (
        set(whole_iq.read(earlier)["cases"]) | set(track_preparation_profile.PILOTS) | {EDGE_CASE}
    )
    panels = whole_iq.read(FROZEN / "panels.json")
    inventory = sequential_fix_trial.inventory()
    eligibility, chosen = {}, []
    for family, panel in (("DS26", "ds26-common127"), ("DS29", "roof16")):
        ranked = sorted(
            (r["recording"]["segments"][0]["sha256"], ident)
            for ident, r in inventory.items()
            if ident.startswith(family)
            and ident in panels[panel]
            and ident not in excluded
            and all(r.get(k) for k in ("request", "catalog", "track_config", "native", "recording"))
        )
        attempted = []
        for digest, ident in ranked:
            row = dict(id=ident, manifest_sha256=digest)
            attempted.append(row)
            try:
                spec = sequential_fix_trial.prepare_recording(ident)
            except (OSError, ValueError, KeyError) as error:
                row["unavailable"] = str(error)
                continue
            chosen.append(spec)
            break
        else:
            raise ValueError(f"no complete {family} candidate")
        eligibility[family] = dict(ranked=ranked, attempted=attempted)
    return chosen, dict(
        excluded=sorted(excluded), known_source_sha256=_sha(earlier), eligibility=eligibility
    )


def edge_case():
    files = whole_iq.read(PRIOR_EDGE / "figure-lock.json")["files"]
    source = whole_iq.read(
        whole_iq.checked(PRIOR_EDGE / "source-lock.json", files["source-lock.json"])
    )
    queries = whole_iq.read(
        whole_iq.checked(PRIOR_EDGE / "figure-queries.json", files["figure-queries.json"])
    )
    (chosen,) = (
        row
        for row in queries["queries"]
        if row["recording"] == EDGE_CASE and row["condition"] == "near-outside"
    )
    offer = source["offers"][chosen["id"]]
    original = sequential_fix_trial.prepare_recording(EDGE_CASE)
    if any(
        original[k] != offer[k]
        for k in ("native_sha256", "catalog_sha256", "original_request_sha256")
    ):
        raise ValueError("historical shifted offer differs from the current causal input")
    return original | dict(tile=offer["tile"], screen_center=offer["tile"]["center"]), chosen["id"]


def freeze(work, profile_work):
    path = REPORT / "source-lock.json"
    if path.exists():
        raise FileExistsError(path)
    profiles = {}
    for ident in track_preparation_profile.PILOTS:
        folder = profile_work / ident
        service = whole_iq.read(folder / "service.json")
        if not iq_service.succeeded(service):
            raise ValueError("profile must reach a prepared result before replacing work")
        raw = folder / "profile.json"
        prior = whole_iq.read(raw)
        if prior["status"] != "inputs_prepared" or prior["id"] != ident:
            raise ValueError("profile does not identify the installed full preparation")
        write(REPORT / f"profile-{ident}.json", raw.read_bytes())
        profiles[ident] = dict(
            files={
                k: _sha(folder / k)
                for k in ("profile.json", "request.json", "service.json", "service.log")
            },
            directory=str(folder),
        )
    chosen, roster = select()
    edge, edge_id = edge_case()
    dense = sequential_fix_trial.prepare_recording(DENSE_CASE)
    cases = {}
    for spec, cpu, order, role in (
        (dense, 15, ["installed", "shared"], "dense"),
        (edge, 14, ["installed", "shared"], "shifted"),
        (chosen[0], 14, ["shared", "installed"], "hash-selected"),
        (chosen[1], 15, ["shared", "installed"], "hash-selected"),
    ):
        cases[spec["id"]] = dict(
            cpu=cpu,
            order=order,
            role=role,
            spec=spec
            | {
                "tile": {"width_km": 25.0} | spec["tile"],
            },
        )
    programs = (
        Path(__file__),
        Path(track_preparation.__file__),
        Path(capture_whole.__file__),
        Path(iq_service.__file__),
        REPORT / "PROTOCOL.md",
    )
    work.mkdir()
    lock = dict(
        source_files={str(p): _sha(p) for p in programs},
        cases=cases,
        roster=roster,
        receiver=str(CALIBRATION),
        receiver_files=receiver_assets(CALIBRATION),
        profiles=profiles,
        cap_s=CAP,
        memory_max=whole_iq.MEMORY,
        swap_max=0,
        edge_query=edge_id,
    )
    save_json(path, lock)
    save_json(work / path.name, lock)


def worker(folder):
    plan = whole_iq.read(folder / "plan.json")
    lock = whole_iq.read(
        whole_iq.checked(folder.parents[1] / "source-lock.json", plan["source_sha256"])
    )
    for filename, digest in lock["source_files"].items():
        whole_iq.checked(Path(filename), digest)
    row = lock["cases"][plan["id"]]
    receiver = Path(lock["receiver"])
    if receiver_assets(receiver) != lock["receiver_files"] or row["cpu"] != plan["cpus"][0]:
        raise ValueError("position service no longer matches its package or pinned core")
    spec = row["spec"]
    compact = compact_trial.compact(spec)
    causal = {p.name: _sha(p) for p in Path(compact["archive"]).rglob("*.tle")}
    if causal != {k: v.removeprefix("sha256:") for k, v in spec["snapshots"].items()}:
        raise ValueError("causal catalogue changed from its sealed request")
    before = memory()
    start = perf_counter()
    result = track_preparation.solve(receiver, compact, plan["mode"])
    published = final_region.publish(
        result["result"], spec["tile"], enabled=row["role"] == "shifted"
    )
    save_json(
        folder / "worker-result.json",
        dict(
            result,
            publication=published,
            start=before,
            end=memory(),
            whole_worker_wall_s=perf_counter() - start,
        ),
    )


def attempt(work, ident, row, mode):
    path = work / ident / mode
    path.mkdir(parents=True, exist_ok=False)
    cpu = row["cpu"]
    save_json(
        path / "plan.json",
        dict(
            id=ident,
            mode=mode,
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
    print(ident, mode, receipt["systemd"]["Result"], flush=True)


def run(work):
    lock = whole_iq.read(
        whole_iq.checked(work / "source-lock.json", _sha(REPORT / "source-lock.json"))
    )

    def lane(cpu):
        for ident, row in lock["cases"].items():
            if row["cpu"] == cpu:
                for mode in row["order"]:
                    attempt(work, ident, row, mode)

    with patch.object(iq_service, "MODULE", MODULE), ThreadPoolExecutor(2) as pool:
        list(pool.map(lane, (14, 15)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "worker", "run"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("--profile", type=local_output)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work, args.profile)
    elif args.action == "worker":
        worker(args.work)
    else:
        run(args.work)


if __name__ == "__main__":
    main()
