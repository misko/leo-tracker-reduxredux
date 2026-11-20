"""Run the authenticated original no-repair v5 worker on paired generated-waveform factors."""

import argparse
import gzip
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic
from uuid import uuid4

from .. import iq_service
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ARMS, validate_result
from . import v5_regional_blind as blind
from . import v5_regional_reference as original
from .boundary_policy_trial import OLD_PUBLIC
from .phase_support_results import pack
from .whole_pressure_trial import rows_from

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "acquisition-frontier/waveform-v5"
RETROSPECTIVE = SCREEN / "track-recovery/waveform-site"
RETROSPECTIVE_PIN = "af7406395ba9037a641b6655f031e2d8b589484c767dc8378584e83b0e6639fa"
HOLDOUT = REPORT.with_name("waveform-holdout")
HOLDOUT_METHOD = REPORT / "holdout-method-lock-v2.json"
ROOF_PIN = "bcfbe09649d45b1d5e371e7351dbbc99a8bc59230b70172d85ea934183fa02df"
MODULE = "tools.pipeline_eval.qualification.waveform_v5"
METHOD = "waveform_v5_original"
LIMIT = 330
MEMORY = original.MEMORY


def read_checked(path, digest):
    original.checked(path, digest)
    return original.read(path)


def roof_authentication():
    roof = original.REPORT / "roof-retry"
    seal = read_checked(roof / "prediction-lock.json", ROOF_PIN)
    plan = read_checked(roof / "plan.json", seal["plan.json"])
    measured = read_checked(roof / "prediction.json", seal["prediction.json"])
    original.checked(Path(original.__file__), plan["adapter_sha256"])
    original.checked(original.ROOF_SOURCE, plan["earlier_archive_sha256"])
    (archived,) = [r for r in rows_from(original.ROOF_SOURCE) if r["id"] == original.ROOF]
    parity = original.parity(measured["result"], archived["result"])
    if not parity["exact"]:
        raise ValueError("original v5 route failed archived roof parity")
    return dict(parity, seal_sha256=ROOF_PIN, archive_sha256=plan["earlier_archive_sha256"])


def request_pair(rows, document):
    source = document["source"]
    cutoff = document["clock_anchor"]["before"]["realtime_ns"]
    pair = sorted((dict(row, cutoff_utc_ns=cutoff) for row in rows), key=lambda r: r["id"])
    if (
        len({row["id"] for row in pair}) != len(pair)
        or any(set(row) != blind.REQUIRED for row in pair)
        or {row["session"] for row in pair} != {source["session_id"]}
        or any(row[key] != pair[0][key] for row in pair for key in blind.SHARED)
        or len({tuple(row["tile"]) for row in pair}) != len(pair)
    ):
        raise ValueError("paired offers do not authenticate against the native clock and session")
    return pair


def freeze_holdout_method():
    template, case = original.roof_request()
    original.write(
        HOLDOUT_METHOD,
        dict(
            offer_selection="all three sealed offers in sorted opaque ID order",
            cpu_sequence=[18, 19, 18],
            concurrent_services=2,
            memory_max=MEMORY,
            swap_max=0,
            deadline_s=LIMIT,
            calibration_arms=ARMS,
            template_sha256=case["request"]["sha256"],
            model=template["model"],
            role=template["role"],
            policy=template["policy"],
            original_runtime=template["job"]["runtime"],
            original_execution_policy=template["job"]["execution_policy"],
            original_native_manifest=template["native_manifest"],
            original_engine=template["source"],
            roof_authentication=roof_authentication(),
            protocol_sha256=original.sha(REPORT / "HOLDOUT.md"),
            launcher_sha256=original.sha(Path(__file__)),
            initial_method_lock_sha256=original.sha(REPORT / "holdout-method-lock.json"),
            preflight_correction=(
                "Authenticate the scheduled instant at the recorded clock bracket midpoint. "
                "Retain its leading edge as the causal cutoff."
            ),
        ),
    )


def prepare(parent, pin, archive, work, report, cpus):
    roof = roof_authentication()
    holdout = len(cpus) == 3
    prereg = HOLDOUT_METHOD if holdout else None
    if prereg:
        declared = original.read(prereg)
        original.checked(Path(__file__), declared["launcher_sha256"])
        original.checked(REPORT / "HOLDOUT.md", declared["protocol_sha256"])
    primary_seal = "detector-lock.json" if holdout else "prediction-lock.json"
    seal = read_checked(parent / primary_seal, pin)
    for name, digest in seal["files"].items():
        original.checked(parent / name, digest)
    detector = (
        seal
        if holdout
        else read_checked(
            parent / "detector-lock.json",
            seal["files"]["detector-lock.json"],
        )
    )
    inputs = read_checked(parent / "input-lock.json", detector["files"]["input-lock.json"])
    for name, digest in inputs["files"].items():
        original.checked(parent / name, digest)
    schedule = original.read(parent / "schedule.json")
    if not detector["ready"] or detector["completed_visits"] != detector["scheduled_visits"]:
        raise ValueError("generated IQ detector receipts do not cover the scheduled visits")
    for name, digest in detector["files"].items():
        original.checked(parent / name, digest)
    native_bytes = gzip.decompress((parent / "native.json.gz").read_bytes())
    native = json.loads(native_bytes)
    if len(native["source"]["probes"]) != 2 * detector["completed_visits"]:
        raise ValueError("generated native document omits scheduled receiver probes")
    pair = request_pair(original.read(parent / "requests.json"), native)
    scheduled = {offer["id"]: offer for offer in schedule["offers"]}
    if len(pair) != len(cpus) or sorted(r["id"] for r in pair) != sorted(scheduled):
        raise ValueError("the matched original offers differ from the sealed compact roster")
    if not holdout and sorted(scheduled) != sorted(seal["cases"]):
        raise ValueError("the original and compact historical offer rosters disagree")
    before = native["clock_anchor"]["before"]["realtime_ns"]
    after = native["clock_anchor"]["after"]["realtime_ns"]
    if (before + after) // 2 != schedule["anchor_utc_ns"] or any(
        any(row[k] != scheduled[row["id"]][k] for k in ("tile", "screen_center"))
        or row["catalog_sha256"] != schedule["catalog_sha256"]
        for row in pair
    ):
        raise ValueError("detector requests changed original offered region, clock or catalogue")
    workspace = work / "public"
    workspace.mkdir(parents=True, exist_ok=False)
    write(workspace / "native.json", native_bytes)
    first = pair[0]
    config = parent / "track-config.json"
    original.checked(config, first["config_sha256"])
    shutil.copyfile(config, workspace / first["track_config"])
    history = original.read(parent / "causal-authority.json")
    for name, row in sorted(history.items()):
        if Path(name).name != name or row["collected_utc_ns"] >= first["cutoff_utc_ns"]:
            raise ValueError("non-causal catalogue or invalid filename")
        path = archive / name
        original.checked(path, row["sha256"])
        write(workspace / "tle/archive/space-track" / name, path.read_bytes())
    jobs, received = blind.prepare(pair, workspace, work)
    if received != {name: row["sha256"] for name, row in history.items()}:
        raise ValueError("the original worker received a different causal history")
    out = {}
    for row, (meta, request), cpu in zip(pair, jobs, cpus, strict=True):
        dest = work / meta["id"]
        request["job"]["output_root"] = str(dest)
        save_json(dest / "request.json", request)
        parent_input = {k: v for k, v in row.items() if k != "cutoff_utc_ns"}
        meta["rebound_input_sha256"] = meta["input_sha256"]
        meta["input_sha256"] = blind.digest_json(parent_input)
        out[meta["id"]] = dict(
            meta,
            cpu=cpu,
            request_sha256=original.sha(dest / "request.json"),
        )
    config = jobs[0][1]
    plan = dict(
        cohort=report.name,
        parent=str(parent.relative_to(SCREEN)),
        parent_seal=primary_seal,
        parent_sha256=pin,
        protocol_sha256=original.sha(REPORT / "PROTOCOL.md"),
        holdout_protocol_sha256=original.sha(REPORT / "HOLDOUT.md") if holdout else None,
        method_preregistration_sha256=original.sha(prereg) if prereg else None,
        launcher_sha256=original.sha(Path(__file__)),
        original_source=config["source"],
        original_model=config["model"],
        original_role=config["role"],
        original_policy=config["policy"],
        original_runtime=config["job"]["runtime"],
        original_execution_policy=config["job"]["execution_policy"],
        original_native_manifest=config["native_manifest"],
        original_entry_sha256=original.sha(Path(original.v5_lean.__file__)),
        adapter_sha256=original.sha(Path(original.__file__)),
        roof_authentication=roof,
        cases=out,
        causal_history=received,
        deadline_s=LIMIT,
        memory_max=MEMORY,
        swap_max=0,
    )
    original.write(report / "source-lock.json", plan)
    return plan


def worker(directory, cpu):
    original.CPU = cpu
    original.worker(directory / "request.json", directory / "result.json")


def attempt(work, meta, masked):
    out = work / meta["id"]
    original.checked(out / "request.json", meta["request_sha256"])
    unit = "leo-waveform-v5-" + uuid4().hex[:12]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        f"--unit={unit}",
        f"--working-directory={ROOT}",
        f"--property=RuntimeMaxSec={LIMIT}s",
        f"--property=MemoryMax={MEMORY}",
        "--property=MemorySwapMax=0",
        "--property=TimeoutStopSec=4s",
        "--property=KillMode=control-group",
        "--property=Nice=10",
        f"--setenv=PYTHONPATH={original.v5_lean.SOURCE}:{original.v5_lean.RUNNER}:{ROOT}",
        f"--setenv=TMPDIR={out}",
        *(
            f"--setenv={name}=1"
            for name in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "BLIS_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        ),
        "taskset",
        "-c",
        str(meta["cpu"]),
        "bwrap",
        "--die-with-parent",
        "--unshare-net",
        "--ro-bind",
        "/",
        "/",
        "--proc",
        "/proc",
        "--bind",
        str(out),
        str(out),
        "--tmpfs",
        str(ROOT / "reports"),
        *[arg for path in masked for arg in ("--tmpfs", str(path))],
        str(original.v5_lean.PYTHON),
        "-B",
        "-m",
        MODULE,
        "worker",
        str(out),
        str(meta["cpu"]),
    ]
    print(meta["id"], "starting original numerical v5", flush=True)
    before = monotonic()
    log_path = out / "service.log"
    with log_path.open("xb") as log:
        try:
            code = subprocess.run(
                command, stdout=log, stderr=subprocess.STDOUT, timeout=LIMIT + 20, check=False
            ).returncode
        except subprocess.TimeoutExpired:
            code = None
    elapsed = monotonic() - before
    state = iq_service._show(unit + ".service")
    if (
        state.get("MainPID") != "0"
        or state.get("ControlPID") != "0"
        or not iq_service._empty_cgroup(iq_service._cgroup(unit + ".service"))
    ):
        raise RuntimeError("terminal original v5 receipt has a live process")
    finish = out / "finish.json"
    log = log_path.read_text(errors="replace")
    result = endpoint(out, code, state, log)
    events = []
    for line in log.splitlines():
        if line.startswith("{"):
            data = json.loads(line)
            if data.get("event") in {"stage", "recovery_stage"}:
                events.append(data)
    measured = original.read(finish) if finish.is_file() else None
    accounting = dict(
        unit=unit,
        systemd=state,
        exit_code=code,
        elapsed_s=elapsed,
        command=command,
        log_sha256=original.sha(log_path),
        log_tail=log.splitlines()[-18:],
    )
    row = dict(
        meta,
        method=METHOD,
        result=result,
        service=accounting,
        events=events,
        worker_wall_s=elapsed,
        worker_cpu_s=measured["cpu_s"] if measured else nanoseconds(state.get("CPUUsageNSec")),
        worker_cgroup_peak_bytes=measured["memory_peak_bytes"]
        if measured
        else integer(state.get("MemoryPeak")),
        started=original.read(out / "start.json") if (out / "start.json").is_file() else None,
        finished=measured,
    )
    save_json(out / "receipt.json", row)
    print(meta["id"], result["status"], round(elapsed, 2), flush=True)
    return row


def integer(value):
    return int(value) if value is not None and value.isdecimal() else None


def nanoseconds(value):
    return int(value) / 1e9 if value is not None and value.isdecimal() else None


def endpoint(out, code, state, log):
    observed = state.get("Result")
    if (
        code == 0
        and observed in (None, "success")
        and (out / "finish.json").is_file()
        and (out / "result.json").is_file()
    ):
        result = original.read(out / "result.json")
        for arm, endpoint in result["arms"].items():
            rms = result["metrics"].get(f"{arm}_conditional_rms_hz")
            if rms is not None:
                endpoint["rf_rms_hz"] = rms
    else:
        if observed in (None, "success") and "result: timeout" in log:
            observed = "timeout"
        observed = observed or "unverified result"
        result = original.v5_lean._no_fix(
            f"Original v5 service terminal result: {observed}",
            status="timed_out" if observed == "timeout" else "failed",
        )
    validate_result(result)
    if set(result["arms"]) != set(ARMS):
        raise ValueError("original worker did not return both calibration arms")
    return result


def run(parent, pin, archive, work, report, cpus, masked):
    report.mkdir(parents=True, exist_ok=True)
    if (report / "source-lock.json").exists():
        raise FileExistsError("the matched original services are already frozen")
    plan = prepare(parent, pin, archive, work, report, cpus)
    lanes = {
        cpu: [meta for meta in plan["cases"].values() if meta["cpu"] == cpu]
        for cpu in sorted(set(cpus))
    }

    def run_lane(items):
        return [attempt(work, meta, masked) for meta in items]

    with ThreadPoolExecutor(max_workers=2) as executor:
        by_id = {row["id"]: row for lane in executor.map(run_lane, lanes.values()) for row in lane}
    rows = [by_id[ident] for ident in plan["cases"]]
    pack(report / "positions.jsonl.gz", rows)
    for row in rows:
        name = row["id"]
        write(report / f"{name}.log", (work / name / "service.log").read_bytes())
    files = ["source-lock.json", "positions.jsonl.gz", *(f"{r['id']}.log" for r in rows)]
    original.write(
        report / "prediction-lock.json",
        dict(
            cases=list(plan["cases"]),
            files={name: original.sha(report / name) for name in files},
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    child = commands.add_parser("worker")
    child.add_argument("work", type=Path)
    child.add_argument("cpu", type=int)
    retrospective = commands.add_parser("retrospective")
    retrospective.add_argument("work", type=local_output)
    holdout = commands.add_parser("holdout")
    holdout.add_argument("work", type=local_output)
    holdout.add_argument("public", type=Path)
    holdout.add_argument("detector_sha256")
    commands.add_parser("freeze-holdout")
    args = parser.parse_args()
    if args.mode == "worker":
        worker(args.work, args.cpu)
    elif args.mode == "freeze-holdout":
        freeze_holdout_method()
    elif args.mode == "retrospective":
        run(
            RETROSPECTIVE,
            RETROSPECTIVE_PIN,
            OLD_PUBLIC / "tle/archive/space-track",
            args.work,
            REPORT / "retrospective",
            (16, 17),
            (),
        )
    else:
        public = args.public.expanduser().resolve()
        if public.name != "public" or args.work.is_relative_to(public.parent):
            raise ValueError("holdout work must remain outside the private controller")
        run(
            HOLDOUT,
            args.detector_sha256,
            public / "tle/archive/space-track",
            args.work,
            REPORT / "holdout",
            (18, 19, 18),
            (public.parent,),
        )


if __name__ == "__main__":
    main()
