"""Fit the actual stock-warmup waveform policy with the unchanged compact receiver."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from time import monotonic
from uuid import uuid4

from .. import whole_iq
from ..__main__ import ROOT, save_json
from ..scoring import validate_result
from . import bracketed_position as installed
from . import prefix_evidence_trial as trial
from .bracketed_position_results import service_result
from .fractional_runtime_whole import verify_request
from .full_v5_check import BULK, _sha
from .wide_roster_results import whole_support

METHOD = "prefix_evidence_causal"
MODULE = "tools.pipeline_eval.qualification.prefix_evidence_position"
LIMIT = 210


def early_raw_pair(ident):
    """Use the authenticated per-arm raw handoff while the fresh position pair is running."""
    parent = trial.receiver_choice_panel
    published = parent.REPORT / "source-lock.json"
    plan = whole_iq.read(whole_iq.checked(parent.WORK / "source-lock.json", _sha(published)))
    case = plan["cases"][ident]
    docs, sources, raw_data = {}, {}, {}
    for mode, role in (("stock", "control"), ("fifth", "candidate")):
        folder = parent.WORK / ident / role
        branch = whole_iq.read(folder / "plan.json")
        raw_path = folder / "raw.json"
        raw = whole_iq.read(raw_path)
        counts = raw["counts"]
        if (
            branch["case"] != ident
            or branch["recording"] != case["recording"]
            or branch["capture_era_request"] != case["request_sha256"]
            or branch["receiver_files"] != plan["receiver_files"]
            or branch["native_sources"] != plan["native_sources"]
            or branch["detector_sha256"] != plan["detectors"][role]["sha256"]
            or raw["raw_end"]["memory.max"] != whole_iq.MEMORY
            or raw["raw_end"]["memory.swap.max"] != 0
        ):
            raise ValueError("Fresh per-arm raw handoff differs from the original planned service")
        whole_support(
            dict(raw, dual_calls=counts["processed_windows"]), case, case["clock_authority"]
        )
        whole_iq.checked(folder / "recording/request.json", raw["request_sha256"])
        path = folder / "recording/native.json"
        doc = trial.native(path, raw["native_sha256"])
        if doc["provenance"]["detector_sha256"] != "sha256:" + branch["detector_sha256"]:
            raise ValueError("Fresh waveform source detector SHA changed")
        docs[mode] = doc
        sources[mode] = dict(
            path=str(path),
            sha256=raw["native_sha256"].removeprefix("sha256:"),
            raw_receipt_sha256=_sha(raw_path),
            branch_plan_sha256=_sha(folder / "plan.json"),
        )
        raw_data[mode] = (folder, raw)
    return docs, sources, plan, raw_data


def prefix_call_cost(raw_data, document, cutoff):
    support = {p["visit_index"]: p["valid_start_counter"] for p in document["source"]["probes"]}
    totals = {}
    for mode, (folder, raw) in raw_data.items():
        all_visits = set()
        times = []
        for i, lane in enumerate(raw["lanes"]):
            path = folder / "recording" / f"replayed-{i}.jsonl"
            with path.open() as stream:
                visits = [r for r in map(json.loads, stream) if r.get("status") == "processed"]
            for row, (wall, cpu) in zip(visits, lane["native_timings_s"], strict=True):
                if row["visit"] in all_visits or row["sample_start"] != support[row["visit"]]:
                    raise ValueError("Prefix call ledger differs from authenticated visit")
                all_visits.add(row["visit"])
                if row["sample_end"] <= cutoff:
                    times.append((wall, cpu))
        if all_visits != support.keys():
            raise ValueError("Prefix timing did not reconcile complete valid visits")
        totals[mode] = dict(
            calls=len(times),
            call_cpu_s=sum(y for _, y in times),
            sum_call_wall_s=sum(x for x, _ in times),
        )
    return totals


def request_binding(ident, plan, fresh):
    if not fresh:
        return whole_iq.binding(ident)
    case = plan["cases"][ident]["case"]
    path = whole_iq.checked(BULK / case["request"]["path"], case["request"]["sha256"])
    req = whole_iq.read(path)
    job = req["job"]
    if (
        job["evaluation_reference"] is not None
        or job["identity"]["session_id"] != case["session_id"]
    ):
        raise ValueError("Expected the original blind request")
    archive = Path(job["tle_root"])
    snapshots = {p.name: _sha(p) for p in archive.rglob("*.tle")}
    if snapshots != {k: v.removeprefix("sha256:") for k, v in req["causal_snapshots"].items()}:
        raise ValueError("Fresh request no longer shares the verified causal catalogue")
    whole_iq.checked(Path(job["track_config"]["path"]), job["track_config"]["sha256"])
    return case, req


def prepare(work, ident, cpu):
    _, choices = trial.verified(work)
    folder = work / ident
    folder.mkdir(exist_ok=False)
    if ident in trial.FRESH:
        docs, sources, plan, raw_data = early_raw_pair(ident)
        choice = trial.score_prefix(docs["stock"], docs["fifth"])
        choice["measured_prefix_call_cost"] = prefix_call_cost(
            raw_data, docs["stock"], choice["cutoff"]
        )
        fresh = True
        save_json(trial.REPORT / f"{ident}-choice.json", dict(choice, sources=sources))
    else:
        if ident != choices["actual_old_case"]:
            raise ValueError("Old fit case is outside the preregistered selection")
        choice = choices["cases"][ident]
        sources = choice["sources"]
        docs = {k: trial.native(Path(s["path"]), s["sha256"]) for k, s in sources.items()}
        plan = whole_iq.read(trial.complete_timing.roster.EIGHT / "source-lock.json")
        fresh = False
    installed.check_release(plan)
    case, request = request_binding(ident, plan, fresh)
    document, counts = trial.materialize(docs["stock"], docs["fifth"], choice, sources)
    capture = whole_iq.recording
    out = folder / "recording"
    out.mkdir()
    native, req = out / "native.json", out / "request.json"
    capture.save(native, document)
    if choice["chosen"] == "stock":
        # Original canonical bytes retain their scientific input identity on fallback.
        whole_iq.checked(native, sources["stock"]["sha256"])
    bound = capture.bind_request(case, native, req)
    verify_request(
        whole_iq.read(req), request, native_path=native, native_sha256=bound["native_sha256"]
    )
    plan_file = folder / "plan.json"
    raw = folder / "raw.json"
    save_json(
        plan_file,
        dict(
            receiver=plan["receiver"],
            receiver_files=plan["receiver_files"],
            native_sources=plan["native_sources"],
            cpu=cpu,
        ),
    )
    save_json(raw, dict(native_sha256=bound["native_sha256"], request_sha256=_sha(req)))
    witness = dict(
        id=ident,
        cpu=cpu,
        choice=choice,
        counts=counts,
        source=sources,
        native_sha256=_sha(native),
        bound_request_sha256=_sha(req),
        original_request_sha256=case["request"]["sha256"],
        paired_capture_sha256=case["native"]["sha256"],
        catalog_sha256=case["catalog"]["sha256"],
        tile=case["regions"][0],
        input_manifest_sha256=document["source"]["input_manifest_sha256"],
    )
    save_json(folder / "fit-binding.json", witness)
    return folder, witness


def worker(folder):
    plan = whole_iq.read(folder / "plan.json")
    if os.sched_getaffinity(0) != {plan["cpu"]}:
        raise ValueError("Compact worker left the scheduled core")
    installed.check_release(plan)
    witness = whole_iq.read(folder / "fit-binding.json")
    whole_iq.checked(folder / "recording/native.json", witness["native_sha256"])
    whole_iq.checked(folder / "recording/request.json", witness["bound_request_sha256"])
    save_json(
        folder / "start.json", whole_iq.raw.mark("adaptive native factors enter compact receiver")
    )
    whole_iq.position(folder)


def run(work, ident, cpu):
    folder = work / ident
    if folder.is_dir() and (folder / "fit-binding.json").is_file():
        witness = whole_iq.read(folder / "fit-binding.json")
        if witness["id"] != ident or witness["cpu"] != cpu:
            raise ValueError("Prior prepared native input belongs to a different attempt")
    else:
        folder, witness = prepare(work, ident, cpu)
    unit = "leo-prefix-pos-" + uuid4().hex[:12]
    cmd = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--unit=" + unit,
        "--working-directory=" + str(ROOT),
        "--property=MemoryMax=" + str(whole_iq.MEMORY),
        "--property=MemorySwapMax=0",
        "--property=Nice=10",
        "--property=KillMode=control-group",
        f"--property=RuntimeMaxSec={LIMIT}s",
        "--setenv=TMPDIR=" + str(folder),
        *("--setenv=" + k + "=" + v for k, v in whole_iq.recording.SINGLE_THREAD.items()),
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
    print(ident, witness["choice"]["chosen"], witness["counts"], "compact launch", flush=True)
    log = folder / "service.log"
    started = monotonic()
    with log.open("xb") as stream:
        status = subprocess.run(
            cmd, stdout=stream, stderr=subprocess.STDOUT, timeout=LIMIT + 30, check=False
        )
    state = subprocess.run(
        [
            "systemctl",
            "--user",
            "show",
            unit,
            "--property="
            "MainPID,ControlPID,Result,ExecMainStatus,CPUUsageNSec,MemoryPeak,"
            "MemorySwapPeak,ActiveEnterTimestampMonotonic,InactiveEnterTimestampMonotonic",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    service = dict(
        unit=unit,
        exit_code=status.returncode,
        log_sha256=_sha(log),
        supervisor_s=monotonic() - started,
        state=dict(line.split("=", 1) for line in state.stdout.splitlines() if "=" in line),
    )
    save_json(folder / "service.json", service)
    result, resources = service_result(folder, cpu)
    result.setdefault("boundary", "Causal stock-warmup native factors through unchanged compact v5")
    validate_result(result)
    row = dict(
        witness,
        method=METHOD,
        result=result,
        resources=resources,
        service=service,
        files={
            p.name: _sha(p)
            for p in (
                folder / "fit-binding.json",
                folder / "service.json",
                folder / "position.json",
                folder / "service.log",
            )
            if p.is_file()
        },
    )
    save_json(trial.REPORT / f"{ident}-fit.json", row)
    print(ident, result["status"], resources, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("run", "worker"))
    p.add_argument("folder", type=Path, nargs="?")
    p.add_argument("--work", type=Path, default=trial.WORK)
    p.add_argument("--case")
    p.add_argument("--cpu", type=int, choices=(0, 1))
    a = p.parse_args()
    if a.action == "worker" and a.folder:
        worker(a.folder)
    elif a.action == "run" and a.case and a.cpu is not None:
        run(a.work, a.case, a.cpu)
    else:
        p.error("run requires --case and --cpu, worker requires its attempt folder")
