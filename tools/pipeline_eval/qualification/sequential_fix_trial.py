"""Run sealed position fits on cumulative original-GLRT factors and full controls."""

import argparse
import gzip
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from math import cos, radians
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from uuid import uuid4

from .. import cavity_runtime, iq_service, whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import validate_result
from ..variants import sequential_fix as policy
from . import capture_release, short_compact
from .full_v5_check import FROZEN, _sha

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "receiver-deadline/sequential-fix"
MODULE = "tools.pipeline_eval.qualification.sequential_fix_trial"
WORKER = Path(__file__).with_name("sequential_fix_worker.py")
ANCHORS = ("DS26-0237", "DS29-0082")
RAW = dict(
    zip(
        ANCHORS,
        ("original-support/prepared-waveform", "antenna-confirmation/capture-whole"),
        strict=True,
    )
)
EXCLUDED = frozenset(
    (
        "DS26-0036",
        "DS26-0122",
        "DS26-0237",
        "DS26-0142",
        "DS26-0223",
        "DS26-0301",
        "DS26-0168",
        "DS26-0261",
        "DS26-0102",
        "DS26-0235",
        "DS29-0082",
        "DS29-0174",
        "DS29-0247",
        "DS29-0357",
        "DS29-0604",
    )
)
CHECKPOINTS = (*policy.CHECKPOINTS, "full")
CAPS = {210: 150, 255: 150, "full": 180}
CPUS = (14, 15, 16, 17)


def inventory():
    authority = whole_iq.read(FROZEN / "provenance.json")["files"]
    path = whole_iq.checked(FROZEN / "inputs.jsonl", authority["inputs.jsonl"])
    return {row["id"]: row for row in map(json.loads, path.read_bytes().splitlines())}


def prepare_recording(ident):
    case, request = whole_iq.binding(ident)
    raw = capture_release.read_capture(case)
    spec = short_compact.original(ident)
    document = whole_iq.read(Path(spec["native"]))
    inputs = short_compact.scopes(document)
    source = document["source"]
    if (
        document["clock_anchor"]["before"]["realtime_ns"] != case["cutoff_utc_ns"]
        or source["session_id"] != case["session_id"]
        or source["sample_rate_hz"] != 10_000_000
        or source["probe_ms"] != 20
        or {p["channel"] for p in source["probes"]} != set(range(1, 9))
        or len(inputs) != case["recording"]["window_count"]
        or any(
            int(name.split("-")[0]) > case["cutoff_utc_ns"] for name in request["causal_snapshots"]
        )
        or not 295 <= (inputs[-1][1] - inputs[0][0]) / source["sample_rate_hz"] <= 305
    ):
        raise ValueError("incomplete 300 s native authority")
    return dict(
        spec,
        cutoff_utc_ns=case["cutoff_utc_ns"],
        raw_manifest_sha256=[r["sha256"] for r in case["recording"]["segments"]],
        input_manifest_sha256=raw["input_manifest_sha256"],
        original_windows=len(inputs),
    )


def roster():
    rows = inventory()
    cases = {ident: prepare_recording(ident) for ident in ANCHORS}
    eligibility = {}
    for family in ("DS26", "DS29"):
        ranked = sorted(
            (r["recording"]["segments"][0]["sha256"], ident)
            for ident, r in rows.items()
            if r["panel"] == family
            and ident not in EXCLUDED
            and all(r.get(k) for k in ("recording", "request", "native", "catalog", "track_config"))
        )
        checked = []
        eligible = 0
        for digest, ident in ranked:
            item = dict(id=ident, first_manifest_sha256=digest)
            checked.append(item)
            try:
                cases[ident] = prepare_recording(ident)
            except (OSError, ValueError, KeyError) as error:
                item["error"] = str(error)
                continue
            eligible += 1
            if eligible == 2:
                break
        if eligible != 2:
            raise ValueError(f"insufficient authenticated {family} holdouts")
        eligibility[family] = checked
    return cases, eligibility


def raw_bindings():
    result = {}
    for ident, name in RAW.items():
        path = SCREEN / name
        lock = whole_iq.read(path / "prediction-lock.json")
        if lock["cases"] != [ident]:
            raise ValueError("raw detector authority used a different original capture")
        files = ("timing.csv", "audit.json", "source-lock.json", "native.json.gz")
        for file in files:
            whole_iq.checked(path / file, lock["files"][file])
        result[ident] = dict(folder=name, files={f: lock["files"][f] for f in files})
    return result


def omitted(tile):
    lat, lon = tile["center"]
    return dict(
        center=[lat, lon + 15 / (111.32 * cos(radians(lat)))], id="east-15-km", width_km=25.0
    )


def prepare(base, report):
    if (report / "source-lock.json").exists():
        raise FileExistsError("the cumulative-prefix study is already sealed")
    cases, eligibility = roster()
    base.mkdir(exist_ok=False, parents=True)
    receiver = cavity_runtime.install(base / "receiver", profile="phase-release")
    scheduled = [(ident, "original") for ident in cases] + [
        (ident, "east-15-km") for ident in ANCHORS
    ]
    paths = (
        Path(__file__),
        WORKER,
        Path(policy.__file__),
        Path(short_compact.__file__),
        WORKER.with_name("short_compact_worker.py"),
        Path(iq_service.__file__),
    )
    lock = dict(
        sources={str(p.relative_to(ROOT)): _sha(p) for p in paths},
        protocol_sha256=_sha(report / "PROTOCOL.md"),
        cases=cases,
        eligible_ranked=eligibility,
        excluded=sorted(EXCLUDED),
        assignment=[
            dict(id=i, offer=o, cpu=CPUS[index % len(CPUS)])
            for index, (i, o) in enumerate(scheduled)
        ],
        caps_s={str(checkpoint): cap for checkpoint, cap in CAPS.items()},
        checkpoints=CHECKPOINTS,
        memory_bytes=whole_iq.MEMORY,
        swap_max_bytes=0,
        raw_anchor_timings=raw_bindings(),
        receiver_files=whole_iq.receiver_identity(receiver),
    )
    save_json(report / "source-lock.json", lock)
    (base / "source-lock.sha256").write_text(_sha(report / "source-lock.json"))
    for ident, offer in scheduled:
        print(ident, offer, flush=True)


def verified_plan(base, report):
    lock = whole_iq.read(
        whole_iq.checked(report / "source-lock.json", (base / "source-lock.sha256").read_text())
    )
    whole_iq.checked(report / "PROTOCOL.md", lock["protocol_sha256"])
    for p, digest in lock["sources"].items():
        whole_iq.checked(ROOT / p, digest)
    if whole_iq.receiver_identity(base / "receiver") != lock["receiver_files"]:
        raise ValueError("installed compact receiver changed from the source lock")
    return lock


def attempt(base, spec, doc, intervals, offer, cpu, checkpoint):
    folder = base / spec["id"] / offer / str(checkpoint)
    folder.mkdir(parents=True, exist_ok=False)
    started = perf_counter()
    view, support = short_compact.snapshot(
        doc, intervals, None if checkpoint == "full" else (0, checkpoint)
    )
    support["actual_end_s"] = support["seconds"][-1]
    tile = spec["tile"] if offer == "original" else omitted(spec["tile"])
    native = Path(spec["native"])
    if checkpoint != "full":
        native = folder / "native.json"
        write(native, encoded(view) + b"\n")
    receiver = base / "receiver"
    compact = dict(
        native=str(native),
        native_sha256=_sha(native),
        archive=spec["archive"],
        track_config=spec["track_config"],
        config_sha256=spec["config_sha256"],
        tile=tile["center"],
        width_km=tile.get("width_km", 25.0),
        screen_center=spec["screen_center"],
        session=spec["session"],
        native_backend=str(receiver / "native/manifest.json"),
        library=str(receiver / "projector.so"),
    )
    limit = CAPS[checkpoint]
    save_json(
        folder / "request.json",
        dict(
            receiver=str(receiver),
            compact=compact,
            support=support,
            cpu=cpu,
            diagnostics=checkpoint != "full",
        ),
    )
    save_json(folder / "plan.json", dict(cpus=[cpu], limit_s=limit))
    preparation = perf_counter() - started
    unit = "leo-iq-bench-" + uuid4().hex[:12]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        f"--unit={unit}",
        f"--working-directory={ROOT}",
        f"--property=MemoryMax={whole_iq.MEMORY}",
        "--property=MemorySwapMax=0",
        "--property=Nice=10",
        "--property=KillMode=control-group",
        f"--property=RuntimeMaxSec={limit}s",
        f"--setenv=TMPDIR={folder}",
        *(f"--setenv={key}={value}" for key, value in short_compact.THREAD_ENV.items()),
        "taskset",
        "-c",
        str(cpu),
        sys.executable,
        "-B",
        "-m",
        MODULE,
        "worker",
        str(folder),
    ]
    service = iq_service.run(folder, command, unit, timeout=limit + 20)
    manager = service["systemd"]
    result_path = folder / "worker-result.json"
    if iq_service.succeeded(service) and result_path.is_file():
        result = whole_iq.read(result_path)
        if result["metrics"]["causal_audit"]["causal_cutoff_utc_ns"] != spec["cutoff_utc_ns"]:
            raise ValueError("worker changed the causal catalogue cutoff")
    else:
        status = "timed_out" if manager.get("Result") == "timeout" else "failed"
        result = short_compact.no_fix(
            status, f"capped compact worker service result {manager.get('Result')}"
        )
    validate_result(result)
    accounting = service.get("resources", {})
    row = dict(
        id=spec["id"],
        offer=offer,
        checkpoint=checkpoint,
        cpu=cpu,
        tile=tile,
        support=support,
        result=result,
        recorded_native_sha256=spec["native_sha256"],
        input_native_sha256=compact["native_sha256"],
        catalog_sha256=spec["catalog_sha256"],
        track_config_sha256=spec["config_sha256"],
        original_request_sha256=spec["original_request_sha256"],
        input_preparation_wall_s=preparation,
        service=service,
        resources=accounting,
    )
    save_json(folder / "prediction.json", row)
    print(spec["id"], offer, checkpoint, result["status"], output_status(manager), flush=True)
    return row


def output_status(manager):
    return manager.get("Result"), manager.get("CPUUsageNSec"), manager.get("MemoryPeak")


def execute(base, report):
    plan = verified_plan(base, report)
    if (report / "prediction-lock.json").exists():
        raise FileExistsError("cumulative predictions are already sealed")

    def lane(cpu):
        rows = []
        for job in plan["assignment"]:
            if job["cpu"] != cpu:
                continue
            ident, offer = job["id"], job["offer"]
            spec = plan["cases"][ident]
            native = whole_iq.checked(Path(spec["native"]), spec["native_sha256"])
            doc = whole_iq.read(native)
            intervals = short_compact.scopes(doc)
            offers = [attempt(base, spec, doc, intervals, offer, cpu, t) for t in CHECKPOINTS]
            sky = {
                r["result"]["metrics"].get("causal_audit", {}).get("selected_tle_sha256")
                for r in offers
            }
            if len(sky - {None}) > 1:
                raise ValueError(
                    f"candidate catalogue changed with prefix length for {ident}/{offer}"
                )
            rows.extend(offers)
        return rows

    with (
        patch.object(iq_service, "MODULE", MODULE),
        ThreadPoolExecutor(max_workers=len(CPUS)) as pool,
    ):
        rows = [r for lane_rows in pool.map(lane, CPUS) for r in lane_rows]
    if plan != verified_plan(base, report):
        raise ValueError("source lock changed during measurement")
    predictions = report / "checkpoint-predictions.jsonl.gz"
    decisions = report / "release-decisions.json"
    write(predictions, gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0))
    save_json(
        decisions,
        [
            dict(id=group[0]["id"], offer=group[0]["offer"], **policy.release(*group[:2]))
            for group in (rows[i : i + 3] for i in range(0, len(rows), 3))
        ],
    )
    files = (predictions, decisions, report / "source-lock.json")
    save_json(
        report / "prediction-lock.json",
        dict(rows=len(rows), files={p.name: _sha(p) for p in files}),
    )


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "worker":
        raise SystemExit(
            subprocess.run(
                [sys.executable, "-IB", str(WORKER), sys.argv[2]], check=False
            ).returncode
        )
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("prepare", "run"))
    cli.add_argument("base", type=local_output)
    cli.add_argument("--report", type=local_output, default=REPORT)
    args = cli.parse_args()
    (prepare if args.action == "prepare" else execute)(args.base, args.report)


if __name__ == "__main__":
    main()
