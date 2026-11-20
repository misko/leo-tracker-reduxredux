"""Refit the clock chain from actual fractional detector factors on eight raw visits."""

import argparse
import gzip
import json
import subprocess
from pathlib import Path
from time import perf_counter

from ..__main__ import encoded, local_output, save_json, write
from ..scoring import validate_result
from ..variants import anchor_receiver, clock_offset
from . import (
    clock_chain_trial,
    clock_offset_trial,
    iq_joint_trial,
    native_joint_trial,
    ordinary_front_eval,
)
from .full_v5_check import _from_native, _load_case, _probe, _sha
from .pilot_kernel_eval import _windows
from .recording_to_v5 import digest, save

REPORT = ordinary_front_eval.REPORT
METHOD = ordinary_front_eval.METHOD
CONTROL = "ordinary_front_capture_control"
ARCHIVE = Path("/srv/bulk/leo-dev/20261119-clock-chain-full")
BOUNDARY = "Held native ordinary fractional IQ factor substitution plus complete ordinary archive"


def assemble(ident, work):
    case = _load_case(ident)
    source = ARCHIVE / ident / "native.json"
    prior = iq_joint_trial.read(clock_chain_trial.REPORT / "stage-receipts.json")[ident]
    if _sha(source) != prior["native_sha256"]:
        raise ValueError("Ordinary capture factors do not match the locked complete replay")
    recorded = json.loads(source.read_bytes())
    path = REPORT / f"{ident}-host.json.gz"
    table = json.loads(gzip.decompress(path.read_bytes()))
    windows = [
        w
        for segment, sequences in ordinary_front_eval.SCHEDULE
        for w in _windows(case, segment, sequences)
    ]
    rows = []
    stable = bool(table["controls"]) and all(r["exact"] for r in table["controls"].values())
    for observed, window in zip(table["rows"], windows, strict=True):
        visit = window.acquisition["global_visit"]
        if observed["iq_sha256"] != window.iq_sha256 or observed["visit"] != visit:
            raise ValueError("Measured native payload is attached to the wrong saved IQ")
        probes = []
        if observed["status"] == "processed":
            stable &= observed["exact"]
            output = observed["payloads"][METHOD]
            for row in output["rows"]:
                candidates = (_from_native(i, c) for i, c in enumerate(row["candidates"]))
                probes.append(_probe(window, row["receiver_id"], candidates))
        rows.append(
            dict(
                visit=visit,
                iq_sha256=window.iq_sha256,
                equal_status=True,
                sample_start=window.acquisition["sample_start"],
                native=probes,
            )
        )
    if not stable:
        raise ValueError("The measured candidate changed an ordinary detector payload")
    allowed = {r["visit"]: r["iq_sha256"] for r in recorded["provenance"]["excluded_windows"]}
    invalid = {r["visit"]: r["iq_sha256"] for r in rows if not r["native"]}
    if any(allowed.get(visit) != iq for visit, iq in invalid.items()):
        raise ValueError("Measured capture exclusions changed")
    replay = dict(
        rows=rows,
        producer={"run_id": recorded["provenance"]["run_id"]},
        archive_audit=dict(archive_exclusions_equal=True, archive_sha256=_sha(source)),
        source_sha256=digest(ordinary_front_eval.sources()),
        kernel_sha256=table["executable_sha256"][METHOD],
    )
    composed, changed = anchor_receiver.splice_probes(recorded, replay)
    if changed or encoded(composed["source"]["probes"]) != encoded(recorded["source"]["probes"]):
        raise ValueError("Actual substituted detector factors differ from the ordinary archive")
    composed["provenance"]["scope"] = BOUNDARY
    folder = work / f"partial-{ident}"
    folder.mkdir(exist_ok=False)
    file = folder / "native.json"
    save(file, composed)
    fresh = len(rows) - len(invalid)
    return (
        case,
        prior,
        file,
        dict(
            fresh_visits=fresh,
            archived_valid_visits=recorded["provenance"]["processed_windows"] - fresh,
            host_receipt_sha256=_sha(path),
            source_ordinary_sha256=_sha(source),
            factor_probes_sha256=digest(composed["source"]["probes"]),
        ),
    )


def position(ident, work, cpu):
    case, prior, file, scope = assemble(ident, work)
    packet, paths = iq_joint_trial.bind_fresh(case, file, _sha(file))
    ideal = dict(prior["packet"], native=packet["native"])
    if packet != ideal:
        raise ValueError("Partial ordinary replay changed the causal or regional request")
    parent = dict(
        native_query=ideal,
        graph_sha256=prior["worker"]["observation_sha256"],
        raw=prior["scope"]["fresh"]["raw"],
    )
    start = perf_counter()
    out = subprocess.run(
        clock_offset_trial.command(cpu, paths, native_joint_trial.BUNDLE),
        input=encoded(packet),
        capture_output=True,
        check=True,
        timeout=30,
    )
    result = json.loads(out.stdout)
    clock_chain_trial.verify_worker(result, BOUNDARY, packet, paths, parent)
    clock = result["models"][clock_offset.METHOD]
    original = prior["worker"]["models"][clock_offset.METHOD]
    for key in ("arms", "status", "reason"):
        if clock[key] != original[key]:
            raise ValueError("The fresh partial detector position changed its original output")
    ids = dict(
        id=ident,
        catalog_sha256=case["catalog"]["sha256"],
        observation_sha256=result["observation_sha256"],
        tile=packet["offer"],
    )
    trial = dict(
        ids,
        **scope,
        method=METHOD,
        result=clock,
        native_sha256=_sha(file),
        input_sha256=iq_joint_trial.sha256(encoded(packet)).hexdigest(),
        position_error_km=clock_chain_trial._errors(ident, clock),
    )
    stock = dict(
        ids,
        method=CONTROL,
        result=original,
        native_sha256=prior["native_sha256"],
        source_ordinary_sha256=scope["source_ordinary_sha256"],
        input_sha256=prior["input_sha256"],
        position_error_km=trial["position_error_km"],
    )
    for row in (trial, stock):
        validate_result(row["result"])
    save_json(
        work / f"{ident}-position.json",
        dict(
            trial=trial,
            stock=stock,
            worker=result["worker"],
            worker_wall_s=perf_counter() - start,
            stages=result["stages"],
            packet=packet,
        ),
    )


def summarize(cases):
    result = {}
    for arch in ("host", "arm"):
        reports = [
            json.loads(gzip.decompress((REPORT / f"{c}-{arch}.json.gz").read_bytes()))
            for c in cases
        ]
        held = [row for report in reports for row in report["rows"]]
        valid = [row for row in held if row["status"] == "processed"]
        controls = [row for report in reports for row in report["controls"].values()]
        timing = {}
        for mode in ("control", METHOD):
            reps = [rep for row in valid for rep in row["timings"][mode]]
            timing[mode] = dict(
                detector_cpu_ms=sum(rep["detector_cpu_ms"] for rep in reps),
                fractional_epoch_ms=sum(r["fractional_epoch"] for p in reps for r in p["rows"]),
                wall_s=sum(rep["wall_s"] for rep in reps),
                emulator_peak_kib=max((rep.get("emu_peak_kib", 0) for rep in reps), default=0),
                emitted_positives=sum(len(rx) for row in valid for rx in row["positives"][mode]),
            )
        control = timing["control"]
        trial = timing[METHOD]
        result[arch] = dict(
            timing=timing,
            scheduled=len(held),
            processed=len(valid),
            exact_payloads=sum(row["exact"] for row in valid),
            exact_controls=sum(row["exact"] for row in controls),
            controls=len(controls),
            whole_cpu_reduction=1 - trial["detector_cpu_ms"] / control["detector_cpu_ms"],
            no_fractional_stage_speedup_bound=(
                control["detector_cpu_ms"]
                / (control["detector_cpu_ms"] - control["fractional_epoch_ms"])
            ),
            paired_resident_peak_kib={r["case"]: r["paired_resident_peak_kib"] for r in reports},
        )
    host = result["host"]
    return dict(
        architectures=result,
        performance_gate=0.08,
        accepted=host["whole_cpu_reduction"] >= 0.08
        and host["exact_payloads"] == host["processed"]
        and host["exact_controls"] == host["controls"],
    )


def package(work):
    cases = iq_joint_trial.CASES
    save_json(REPORT / "qualification.json", summarize(cases))
    positions = {c: iq_joint_trial.read(work / f"{c}-position.json") for c in cases}
    for field, name in (("trial", "positions.jsonl.gz"), ("stock", "control-positions.jsonl.gz")):
        rows = [r[field] for r in positions.values()]
        write(REPORT / name, gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0))
    save_json(REPORT / "position-receipts.json", positions)
    names = (
        "PROTOCOL.md",
        "source-lock.json",
        "qualification.json",
        "position-receipts.json",
        "positions.jsonl.gz",
        "control-positions.jsonl.gz",
        *(f"{c}-{arch}.json.gz" for c in cases for arch in ("host", "arm")),
    )
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(cases),
            files={name: _sha(REPORT / name) for name in names},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--case", choices=iq_joint_trial.CASES)
    parser.add_argument("--cpu", type=int)
    args = parser.parse_args()
    work = local_output(args.work)
    if args.case is None:
        package(work)
    else:
        position(args.case, work, args.cpu)
