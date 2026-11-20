"""Replay held stored GLRT through the unchanged capped phase-release receiver."""

import argparse
import gzip
import hashlib
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic
from uuid import uuid4

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..variants import margin_admission
from . import bounded_cavity_trial
from . import margin_admission_inputs as inputs
from .cavity_lifetime_worker import binding
from .full_v5_check import _load_case, _sha
from .portable_gate_trials import compressed_rows

OUT = inputs.REPORT
MODES = {
    "original": "wide_original_margin",
    "scalar": "wide_scalar_margin",
    "thin": "wide_same_budget_hash",
}


def freeze():
    source = inputs.read(inputs.WIDE / "source-lock.json")
    receiver = Path(source["receiver"])
    if whole_iq.receiver_identity(receiver) != source["receiver_files"]:
        raise ValueError("the installed phase-release receiver differs from scout-full")
    files = (
        OUT / "PROTOCOL.md",
        Path(__file__),
        Path(inputs.__file__),
        Path(margin_admission.__file__),
        Path(whole_iq.__file__),
    )
    plan = dict(
        train=[inputs.authority(ident)[0] for ident in inputs.TRAIN],
        held=[inputs.authority(ident)[0] for ident in inputs.HELD],
        cores={ident: inputs.CPUS[i % 2] for i, ident in enumerate(inputs.HELD)},
        receiver=source["receiver"],
        receiver_files=source["receiver_files"],
        sources={p.name: _sha(p) for p in files},
        limit_s=inputs.LIMIT_S,
        memory_bytes=whole_iq.MEMORY,
        swap_bytes=0,
    )
    target = OUT / "plan.json"
    if target.exists():
        original = inputs.read(target)
        old_launcher = OUT / "initial-infrastructure" / "launcher.py.gz"
        launcher = Path(__file__).name
        old_hash = original["sources"][launcher]
        current_hash = plan["sources"][launcher]
        expected = dict(plan, sources=dict(plan["sources"], **{launcher: old_hash}))
        if original != expected:
            raise ValueError("the prospective replay plan changed")
        if current_hash != old_hash:
            if hashlib.sha256(gzip.decompress(old_launcher.read_bytes())).hexdigest() != old_hash:
                raise ValueError("missing exact initial launcher")
            save_json(
                OUT / "execution-lock.json",
                dict(
                    calibration_plan_sha256=_sha(target),
                    initial_launcher_sha256=old_hash,
                    launcher_sha256=current_hash,
                    reason="Set worker initial directory so the receiver module can be imported",
                ),
            )
        plan = original
    else:
        save_json(target, plan)
    return plan


def counts(doc):
    probes = doc["source"]["probes"]
    return dict(
        probes=len(probes),
        positive_probes=sum(
            margin_admission.probe_margin(p) >= margin_admission.STOCK for p in probes
        ),
        positive_candidates=sum(c[margin_admission.FLAG] for p in probes for c in p["candidates"]),
    )


def stage(work, ident, mode, threshold, receiver):
    raw, doc, authority = inputs.load(ident)
    case = _load_case(ident)
    if case["request"]["sha256"] != authority["capture_request_sha256"]:
        raise ValueError("exact original truth-free request required")
    work.mkdir(exist_ok=False, parents=True)
    folder = work / "recording"
    folder.mkdir()
    original = counts(doc)
    if mode != "original":
        probes = doc["source"]["probes"]
        if mode == "scalar":
            margin_admission.bind(probes, threshold)
        else:
            _, shadow, _ = inputs.load(ident)
            margin_admission.bind(shadow["source"]["probes"], threshold)
            keep = counts(shadow)["positive_candidates"]
            del shadow
            margin_admission.thin(probes, keep, doc["source"]["session_id"])
        lineage = whole_iq.recording.digest(
            [
                "stored-wide-margin-admission/v1",
                authority["wide_native_sha256"],
                mode,
                threshold.hex(),
                probes,
            ]
        )
        doc["source"]["analysis_manifest_sha256"] = lineage
        doc["provenance"]["run_id"] = "replay-" + lineage[7:39]
    native = folder / "native.json"
    if mode == "original":
        write(native, raw)
    else:
        whole_iq.recording.save(native, doc)
    request = folder / "request.json"
    native_sha = whole_iq.recording.bind_request(case, native, request)["native_sha256"]
    save_json(work / "plan.json", dict(receiver=receiver))
    save_json(work / "raw.json", dict(native_sha256=native_sha, request_sha256=_sha(request)))
    return dict(authority, evaluated_native_sha256=native_sha, before=original, after=counts(doc))


def work_position(unit, cpu, folder):
    group = binding(unit, cpu)
    before = whole_iq.raw.mark("stored-native position enter")
    whole_iq.position(folder)
    end = inputs.read(folder / "end.json")
    if before["cgroup"] != str(group) and not str(group).endswith(before["cgroup"]):
        raise ValueError("position worker used the wrong cgroup")
    if before["cpus"] != [cpu] or end["cpus"] != [cpu] or end["memory.swap.current"]:
        raise ValueError("position resource authorization changed")
    save_json(
        folder / "measured.json",
        dict(
            cpu_s=(end["cpu.stat.usage_usec"] - before["cpu.stat.usage_usec"]) / 1e6,
            wall_s=end["monotonic_s"] - before["monotonic_s"],
            peak_bytes=end["memory.peak"],
            start=before,
            end=end,
        ),
    )


def execute(plan, work, ident, mode, threshold):
    out = work / mode / ident
    row = stage(out, ident, mode, threshold, plan["receiver"])
    cpu = plan["cores"][ident]
    unit = "leo-margin-admission-" + uuid4().hex[:12]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--collect",
        f"--unit={unit}",
        f"--working-directory={ROOT}",
        f"--property=MemoryMax={plan['memory_bytes']}",
        "--property=MemorySwapMax=0",
        "--property=Nice=10",
        "--property=KillMode=control-group",
        f"--property=RuntimeMaxSec={plan['limit_s']}s",
        f"--setenv=TMPDIR={out}",
        *(f"--setenv={k}={v}" for k, v in whole_iq.recording.SINGLE_THREAD.items()),
        "taskset",
        "-c",
        str(cpu),
        sys.executable,
        "-B",
        "-m",
        "tools.pipeline_eval.qualification.margin_admission_trial",
        "worker",
        "--unit",
        unit,
        "--cpu",
        str(cpu),
        "--work",
        str(out),
    ]
    begin = monotonic()
    log = out / "service.log"
    with log.open("wb") as stream:
        job = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
    text = log.read_text(errors="replace")
    result, terminal = bounded_cavity_trial.result_for(text, job.returncode, out / "position.json")
    row.update(
        method=MODES[mode],
        position_mode=mode,
        result=result,
        cpu=cpu,
        unit=unit,
        terminal=terminal,
        supervisor_wall_s=monotonic() - begin,
        service_receipt=[
            r.strip()
            for r in text.splitlines()
            if r.strip().startswith(("Finished with result:", "CPU time consumed:", "Memory peak:"))
        ],
        position_resources=inputs.read(out / "measured.json")
        if (out / "measured.json").is_file()
        else None,
        log_sha256=_sha(log),
        native_sha256=row["evaluated_native_sha256"],
        paired_capture_sha256=row["capture_native_sha256"],
    )
    save_json(out / "attempt.json", row)
    print(ident, mode, result["status"], terminal, round(row["supervisor_wall_s"], 2), flush=True)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("replay", "thin", "worker"))
    parser.add_argument("--work", required=True, type=local_output)
    parser.add_argument("--unit")
    parser.add_argument("--cpu", type=int)
    args = parser.parse_args()
    if args.action == "worker":
        return work_position(args.unit, args.cpu, args.work)
    plan = freeze()
    plan_sha = _sha(OUT / "plan.json")
    lock = (
        inputs.read(OUT / "threshold-lock.json")
        if (OUT / "threshold-lock.json").exists()
        else inputs.lock_threshold(plan_sha)
    )
    if lock["plan_sha256"] != plan_sha or lock["threshold"].hex() != lock["threshold_hex"]:
        raise ValueError("scalar threshold differs from the prospective replay")
    print("threshold", lock["threshold_hex"], flush=True)
    started = monotonic()
    if args.action == "thin":
        if not (OUT / "prediction-lock.json").is_file():
            raise ValueError("finish the primary replay before the allocation control")
        rows = [execute(plan, args.work, "DS29-0127", "thin", lock["threshold"])]
        stem = "thinning"
    else:

        def lane(i):
            records = []
            for ident in inputs.HELD[i::2]:
                for mode in ("original", "scalar") if i == 0 else ("scalar", "original"):
                    records.append(execute(plan, args.work, ident, mode, lock["threshold"]))
            return records

        with ThreadPoolExecutor(2) as pool:
            rows = [r for chunk in pool.map(lane, range(2)) for r in chunk]
        stem = "prediction"
    archive = OUT / (stem + "s.jsonl.gz")
    write(archive, compressed_rows(rows))
    dependencies = [archive, OUT / "plan.json", OUT / "threshold-lock.json"]
    if (OUT / "execution-lock.json").is_file():
        dependencies.append(OUT / "execution-lock.json")
    save_json(
        OUT / (stem + "-lock.json"),
        dict(
            files={p.name: _sha(p) for p in dependencies},
            measured_wall_s=monotonic() - started,
            attempted=len(rows),
        ),
    )


if __name__ == "__main__":
    main()
