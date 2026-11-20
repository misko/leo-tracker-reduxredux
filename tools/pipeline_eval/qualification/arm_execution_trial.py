"""Measure paired vs independently requested compact calibration publication."""

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from uuid import uuid4

from .. import iq_service, whole_iq
from ..__main__ import THREAD_ENV, local_output, save_json
from ..original_receiver import CALIBRATION, receiver_assets
from ..scoring import validate_result
from ..variants import arm_execution, final_region
from . import capture_whole, sequential_fix_trial, whole_memory_chain_worker
from .full_v5_check import FROZEN, _sha

REPORT = sequential_fix_trial.SCREEN / "coarse-and-navigation/arm-execution"
EXCLUDED_STUDIES = (
    "receiver-deadline/sequential-fix",
    "antenna-confirmation/compact-cost",
    "support-preserving/short-compact",
)
EDGE = "15b30a4eff19c1ecd3af"
ANCHORS = ("DS29-0082", "DS26-0070")
CAP = 180
MODULE = "tools.pipeline_eval.qualification.arm_execution_trial"


def roster():
    excluded, schedules = set(ANCHORS), {}
    for study in EXCLUDED_STUDIES:
        file = sequential_fix_trial.SCREEN / study / "source-lock.json"
        cases = whole_iq.read(file)["cases"]
        excluded.update(
            cases
            if isinstance(cases, dict)
            else (row if isinstance(row, str) else row["id"] for row in cases)
        )
        schedules[str(file)] = _sha(file)
    inventory = sequential_fix_trial.inventory()
    panels = whole_iq.read(FROZEN / "panels.json")
    eligibility, selected = {}, []
    for family, panel in (("DS26", "ds26-common127"), ("DS29", "roof16")):
        claimed = sorted(
            (r["recording"]["segments"][0]["sha256"], ident)
            for ident, r in inventory.items()
            if ident.startswith(family)
            and ident in panels[panel]
            and ident not in excluded
            and all(r.get(k) for k in ("request", "catalog", "track_config", "native", "recording"))
        )
        eligible = []
        for digest, ident in claimed:
            row = dict(id=ident, first_segment_sha256=digest)
            eligible.append(row)
            try:
                spec = sequential_fix_trial.prepare_recording(ident)
            except (OSError, ValueError, KeyError) as error:
                row["unavailable"] = str(error)
                continue
            selected.append(spec)
            break
        else:
            raise ValueError(f"no available {family} capture for the registered study")
        eligibility[family] = dict(ordered_metadata=claimed, attempted=eligible)
    return selected, dict(excluded=sorted(excluded), schedules=schedules, eligibility=eligibility)


def compact(spec):
    return dict(
        native=spec["native"],
        native_sha256=spec["native_sha256"],
        archive=spec["archive"],
        track_config=spec["track_config"],
        config_sha256=spec["config_sha256"],
        session=spec["session"],
        tile=spec["tile"]["center"],
        screen_center=spec["screen_center"],
        width_km=spec["tile"].get("width_km", 25.0),
    )


def freeze(work):
    fresh, evidence = roster()
    established = [sequential_fix_trial.prepare_recording(i) for i in ANCHORS]
    source = sequential_fix_trial.SCREEN / "receiver-core/measured-boundary-policy/source-lock.json"
    edge = whole_iq.read(source)["offers"][EDGE]
    offered = established[1]
    if any(
        offered[key] != edge[key]
        for key in ("native_sha256", "original_request_sha256", "catalog_sha256")
    ):
        raise ValueError("withholding edge changed original input")
    offered = offered | dict(tile=edge["tile"], screen_center=edge["tile"]["center"])
    cases = {
        spec["id"]: dict(spec=spec, role=role, cpu=cpu, publication=publication, order=order)
        for spec, role, cpu, publication, order in (
            (established[0], "established", 14, "paired", ["control", "c0", "fitted_c"]),
            (offered, "established-edge", 15, "paired-interior", ["c0", "control", "fitted_c"]),
            (fresh[0], "hash-selected", 14, "paired", ["fitted_c", "control", "c0"]),
            (fresh[1], "hash-selected", 15, "paired", ["control", "fitted_c", "c0"]),
        )
    }
    work.mkdir()
    candidate = work / "receiver"
    candidate_files = arm_execution.install(CALIBRATION, candidate)
    if candidate_files != arm_execution.verify_install(candidate):
        raise ValueError("installed arm release did not pass independent verification")
    package = dict(
        control=str(CALIBRATION),
        candidate=str(candidate),
        control_files=receiver_assets(CALIBRATION),
        candidate_files=candidate_files,
    )
    path = REPORT / "source-lock.json"
    if path.exists():
        raise FileExistsError(path)
    code = (
        Path(__file__),
        Path(arm_execution.__file__),
        Path(final_region.__file__),
        Path(iq_service.__file__),
        REPORT / "PROTOCOL.md",
        source,
    )
    save_json(
        path,
        dict(
            cases=cases,
            package=package,
            sources={str(p): _sha(p) for p in code},
            selection=evidence,
            edge_offer=EDGE,
            limit_s=CAP,
            memory_max=whole_iq.MEMORY,
            swap_max=0,
        ),
    )
    save_json(work / "source-lock.json", whole_iq.read(path))
    if _sha(work / path.name) != _sha(path):
        raise ValueError("copied lock differs from the source seal")


def stock_command(receiver, values):
    return [
        sys.executable,
        "-IB",
        str(receiver),
        *(
            item
            for key, value in values.items()
            for item in (
                "--" + key.replace("_", "-"),
                *map(str, value if isinstance(value, list) else (value,)),
            )
        ),
    ]


def worker(folder):
    plan = whole_iq.read(folder / "plan.json")
    lock = whole_iq.read(
        whole_iq.checked(folder.parents[1] / "source-lock.json", plan["source_sha256"])
    )
    for name, digest in lock["sources"].items():
        whole_iq.checked(Path(name), digest)
    row = lock["cases"][plan["id"]]
    spec, mode = row["spec"], plan["mode"]
    if row["cpu"] != plan["cpus"][0]:
        raise ValueError("unassigned position service core")
    native = compact(spec)
    causal = {p.name: _sha(p) for p in Path(native["archive"]).rglob("*.tle")}
    if causal != {k: v.removeprefix("sha256:") for k, v in spec["snapshots"].items()}:
        raise ValueError("causal catalogue changed from the sealed complete request")
    before = whole_memory_chain_worker.memory()
    started = perf_counter()
    packages = lock["package"]
    if mode == "control":
        receiver = Path(packages["control"])
        if receiver_assets(receiver) != packages["control_files"]:
            raise ValueError("paired control package changed")
        result = subprocess.run(stock_command(receiver, native), stdout=subprocess.PIPE, check=True)
        numerical = json.loads(result.stdout)
        measured = dict(numerical=numerical)
    else:
        receiver = Path(packages["candidate"])
        if arm_execution.verify_install(receiver) != packages["candidate_files"]:
            raise ValueError("selected release differs from the pre-score seal")
        measured = arm_execution.solve_selected(receiver, native, mode, row["publication"])
        numerical = measured["numerical"]
    validate_result(numerical)
    published = final_region.publish(
        numerical, spec["tile"], enabled=row["publication"] == "paired-interior"
    )
    save_json(
        folder / "worker-result.json",
        dict(
            measured,
            publication=published,
            start=before,
            end=whole_memory_chain_worker.memory(),
            worker_wall_s=perf_counter() - started,
        ),
    )


def attempt(work, ident, row, mode):
    folder = work / ident / mode
    folder.mkdir(parents=True, exist_ok=False)
    cpu = row["cpu"]
    save_json(
        folder / "plan.json",
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
            f"--setenv=TMPDIR={folder}",
            *(f"--setenv={k}={v}" for k, v in THREAD_ENV.items()),
            "taskset",
            "-c",
            str(cpu),
            sys.executable,
            "-B",
            "-m",
            MODULE,
            "worker",
            str(folder),
        ],
    )
    service = iq_service.run(folder, command, unit, timeout=CAP + 20)
    print(ident, mode, service.get("systemd", {}).get("Result"), flush=True)


def run(work):
    path = whole_iq.checked(work / "source-lock.json", _sha(REPORT / "source-lock.json"))
    rows = whole_iq.read(path)["cases"]

    def lane(cpu):
        for ident, row in rows.items():
            if row["cpu"] == cpu:
                for mode in row["order"]:
                    attempt(work, ident, row, mode)

    with patch.object(iq_service, "MODULE", MODULE), ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lane, (14, 15)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "worker", "run"))
    parser.add_argument("path", type=local_output)
    args = parser.parse_args()
    dict(freeze=freeze, worker=worker, run=run)[args.action](args.path)


if __name__ == "__main__":
    main()
