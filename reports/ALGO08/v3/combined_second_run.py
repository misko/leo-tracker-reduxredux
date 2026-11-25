"""Prepare the ordinary-grid candidate, verify custody, and admit its one original worker."""

import argparse
import fcntl
import json
import os
from pathlib import Path
from time import monotonic, process_time
from unittest.mock import patch

import combined_small_panel as panel
from combined_second_original import CAMPAIGN, CASE, cache, checked_doc, enrollment, extent
from combined_second_stage import ROOT as STAGE
from combined_small_panel_score import products, verifier_paths

HERE = Path(__file__).resolve().parent
CODE = (
    "combined_small_panel_entry.py",
    "combined_small_panel_meter.py",
    "held_cfo_features.py",
    "masked_cfo_saved.py",
)
PROTOCOL = "combined-second-original-protocol.md"
CAP = 22


def command(root, work, inputs, *extra, timed=False):
    runtime, build = panel.runtime_paths(root, "trial")
    bundle = root / "entry"
    entry = [bundle / CODE[0], "--ordinary-grid", runtime]
    if extra == ("--probe-ports",):
        entry.insert(1, "--probe-ports")
        return panel.capsule([panel.paired.PYTHON, "-IB", *entry], work, inputs)
    authority = inputs["authority"]
    flags = (
        *panel.paired.original_options(
            authority["recording"], inputs["archive"], inputs["offer"], work / "publication"
        ),
        "--authority",
        root / "authority.json",
        "--authority-sha256",
        inputs["authority_sha256"],
        "--build",
        build,
        "--build-sha256",
        panel.TRIAL,
        *extra,
    )
    worker = [panel.paired.PYTHON, "-IB", *entry, "--", *flags]
    if timed:
        worker = [
            panel.paired.PYTHON,
            "-IB",
            bundle / CODE[1],
            work / "numeric-process.json",
            *worker,
        ]
    return panel.capsule(worker, work, inputs)


def prepare(root):
    book = enrollment()
    root.mkdir(mode=0o700)
    panel.restore(root, ("trial",))
    bundle = root / "entry"
    bundle.mkdir()
    for name in CODE:
        (bundle / name).write_bytes((HERE / name).read_bytes())
    book["entry_sha256"] = {name: panel.digest((bundle / name).read_bytes()) for name in CODE}
    authority = CAMPAIGN / "cases" / CASE / "authority.json"
    authority_bytes = authority.read_bytes()
    book["authority_sha256"] = "sha256:" + panel.digest(authority_bytes)
    (root / "authority.json").write_bytes(authority_bytes)
    offer = root / "offer.json"
    offer.write_bytes(panel.check(CAMPAIGN / "offer.json", book["authority"]["region_sha256"]))
    book["offer"] = str(offer)
    dummy = root / "empty-recording-for-imports-only"
    dummy.mkdir()
    work = panel.new_work(root / "ports-readback")
    observed = panel.check_command(
        command(root, work, book | {"staged": str(dummy)}, "--probe-ports")
    )
    if observed != dict(ports=True, waveform_reads=0, graph_calls=0, solves=0):
        raise ValueError("The approved ordinary worker modules failed imports-only preflight")
    book["ports_readback"] = observed
    book["protocol_sha256"] = panel.digest((HERE / PROTOCOL).read_bytes())
    print(panel.write(root / "ready.json", book))


def custody(root, book):
    stage_receipt = STAGE / "verified-stage.json"
    if not stage_receipt.is_file():
        return dict(
            eligible=False,
            reason="the authenticated complete NVMe stage is missing",
            required_new_bytes=book["new_backing_bytes"],
        )
    body = stage_receipt.read_bytes()
    stage = json.loads(body)
    original = Path(book["authority"]["recording"])
    raw = STAGE / original.name
    if (
        stage["authority"] != book["authority"]
        or stage["state"] != "complete"
        or Path(stage["recording"]) != raw
        or raw.resolve(strict=True) != raw
    ):
        raise ValueError("The staged receipt does not enclose one authenticated original")
    archive = Path(stage["archive"])
    files = [(raw / item["relative"], item["size"]) for item in book["files"]]
    files.extend(
        (archive / "archive/space-track" / item["name"], item["size"]) for item in book["causal"]
    )
    paths = []
    for path, size in files:
        extent(path, size)
        paths.append(path)
    observed = cache(paths)
    missing = sum(max(0, row["size"] - row["res"]) for row in observed)
    if missing:
        return dict(
            eligible=False,
            reason="the detached input is incompletely resident",
            nonresident_bytes=missing,
        )
    return dict(
        eligible=True,
        staged=str(raw),
        archive=str(archive),
        files=[str(path) for path in paths],
        stage_sha256=panel.digest(body),
        offered_region=book["offered_region"],
    )


def read_ready(root, pin):
    book = checked_doc(root / "ready.json", pin)
    if book["protocol_sha256"] != panel.digest((HERE / PROTOCOL).read_bytes()):
        raise ValueError("Frozen second-original protocol changed")
    for name, expected in book["entry_sha256"].items():
        panel.check(root / "entry" / name, expected)
    panel.check(root / "authority.json", book["authority_sha256"])
    return book


def admit(root, pin):
    book = read_ready(root, pin)
    gate = custody(root, book)
    if not gate["eligible"]:
        print(json.dumps(gate, sort_keys=True))
        return
    work = panel.new_work(root / "signed-metadata")
    result = panel.check_command(command(root, work, book | gate, "--preflight"))
    if result != dict(
        preflight="ready", session_id=book["authority"]["session_id"], waveform_opens=0
    ):
        raise ValueError("The staged recording and causal view failed the original metadata checks")
    print(panel.write(root / "admission.json", dict(input=gate, meta=result, ready_sha256=pin)))


def launch(event, pid, root, book, admitted):
    work = root / "trial-publication"
    if work.exists():
        raise ValueError("The one original numerical worker is already enrolled or completed")
    argv = [
        "/usr/bin/taskset",
        "-c",
        "2",
        "/usr/bin/ionice",
        "-c2",
        "-n7",
        *command(root, work, book | admitted, timed=True),
    ]
    with panel.LOCK.open("rb") as lock, patch.dict(panel.CAP_SECONDS, {CASE: CAP}):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if custody(root, book) != admitted:
            raise ValueError("The exact detached sample admission changed")
        panel.driver_window(event, pid, 0, CASE, pending_0218=False)
        panel.new_work(work)
        panel.write(work / "intent.json", dict(command=argv, event=event, cap_s=CAP))
        process = panel.paired.child(argv, work, CAP, lock.fileno())
        panel.write(work / "outer-process.json", process)
    if process["exit_code"] or process["timed_out"]:
        raise ValueError(
            "The observed original launch failed. Retain the timing and error without replay"
        )
    started, cpu_start = monotonic(), process_time()
    inner = json.loads((work / "numeric-process.json").read_bytes())
    output = work / "publication"
    verified = panel.paired.publication(
        output, work, "successor", book, process, {"sha256": panel.TRIAL}
    )
    feature = json.loads((output / "combined-small-panel-witness.json").read_bytes())
    exact = json.loads((output / "exact-named-raw-witness.json").read_bytes())
    boundary = json.loads((output / "unified-short-bootstrap.json").read_bytes())
    if (
        verified["native_sha256"] != book["archived_controls"]["successor"]["native_sha256"]
        or feature["native_sha256"] != verified["native_sha256"]
        or feature["grid"]
        or (verified["outcome"] == "complete" and not feature.get("ordinary_grid"))
        or inner["exit_code"]
        or not boundary["total_before_receipt"]["cpu_s"] <= inner["cpu_s"] <= process["elapsed_s"]
    ):
        raise ValueError(
            "The ordinary grid, actual CPU meter or signed native handoff failed its frozen scope"
        )
    publication = products(output, verified, exact["evidence"]["owner_rows"])
    verification = dict(elapsed_s=monotonic() - started, cpu_s=process_time() - cpu_start)
    seal = panel.write(
        work / "verified.json",
        verified
        | publication
        | dict(
            actual_worker=inner,
            outer_process=process,
            validation=verification,
            acquisition=boundary["phases"],
            prefetch=boundary["prefetch"],
            feature=feature,
            detached_after=custody(root, book),
            elapsed_s=process["elapsed_s"] + verification["elapsed_s"],
            cpu_s=inner["cpu_s"] + verification["cpu_s"],
            archived_timing=book["archived_controls"],
        ),
    )
    return dict(status="one_original_verified", result_sha256=seal)


def watch(root, pin, admission, pid):
    if os.sched_getaffinity(0) != {3} or os.getpriority(os.PRIO_PROCESS, 0) < 15:
        raise ValueError("Use the CPU 3 low-priority launch controller")
    book = read_ready(root, pin)
    gate = checked_doc(root / "admission.json", admission)
    if gate["ready_sha256"] != pin or not gate["input"]["eligible"]:
        raise ValueError("The original has no authenticated staged admission")
    panel.check(panel.DRIVER, panel.DRIVER_PIN)
    verifier_paths()
    panel.controller_preflight()
    from reports.ALGO08.v3.profiled_grid_export_admission import observe

    result = observe(lambda event: launch(event, pid, root, book, gate["input"]), None)
    panel.write(root / f"watch-{result['watching_from']}.json", result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("prepare", "admit", "watch"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--ready-pin")
    cli.add_argument("--admission-pin")
    cli.add_argument("--driver-pid", type=int)
    args = cli.parse_args()
    if args.root.resolve() != args.root or args.root.parent != Path("/dev/shm"):
        cli.error("Choose a direct independent tmpfs runtime root")
    if args.mode == "prepare":
        prepare(args.root)
    elif args.mode == "admit" and args.ready_pin:
        admit(args.root, args.ready_pin)
    elif args.mode == "watch" and all((args.ready_pin, args.admission_pin, args.driver_pid)):
        watch(args.root, args.ready_pin, args.admission_pin, args.driver_pid)
    else:
        cli.error("Supply the sealed readiness and admission pins for a numerical watch")
