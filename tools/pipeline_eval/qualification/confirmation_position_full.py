"""Measure the frozen late-pilot gate across all visits and refit both v5 arms."""

import argparse
import gzip
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from time import perf_counter, process_time

from ..__main__ import encoded, local_output, write
from ..variants import pilot_confirmation, v5_lean
from .confirmation_position import (
    CASES,
    ORDINARY,
    SOURCE_NAMES,
    SUPPORT,
    apply_gate,
    bind_published_source,
    decisions,
    fit,
    verified_ordinary,
    verify_selection,
)
from .confirmation_position import (
    METHOD as PUBLISHED_METHOD,
)
from .full_v5_check import BULK, PRODUCERS, REPO, _bind_producer, _load_case, _sha
from .recording_to_v5 import ARCHIVE_PYTHON, SINGLE_THREAD, save

DEADLINE_S = 900
METHOD = "pilot_confirmation_full"
BOUNDARY = "Late pilot gate on all of the complete ordinary native recording through frozen v5"
MODULE = "tools.pipeline_eval.qualification.confirmation_position_full"


def native_rows(probes):
    """Recover only the frozen IQ witness coordinates, preserving C candidate ranks."""
    rows = []
    for probe in probes:
        positive = [c for c in probe["candidates"] if c["passed_fractional_margin_gate"]]
        candidates = [
            dict(fractional_epoch={"status": "not_evaluated"})
            for _ in range(max((p["candidate_rank"] for p in positive), default=-1) + 1)
        ]
        for candidate in positive:
            candidates[candidate["candidate_rank"]] = dict(
                epoch=candidate["integer_epoch_sample"],
                fractional_epoch=dict(
                    status="complete",
                    margin=candidate["fractional_margin"],
                    offset_samples=candidate["fractional_epoch_offset_samples"],
                    tracking_cfo_hz=candidate["fractional_tracking_cfo_hz"],
                ),
            )
        rows.append(
            dict(
                receiver_id=probe["receiver_id"],
                probe_start_ms=probe["probe_start_ms"],
                candidates=candidates,
            )
        )
    return rows


def _raw_visit(window, source, ordinary, confirm, policy, analyze, receiver_type):
    """Run capture validation and the IQ witness on exactly one ordinary visit."""
    values = {}
    confirmation_cpu_s = 0.0

    def detect(window, receivers):
        nonlocal confirmation_cpu_s
        started = process_time()
        values.update(confirm(window.samples, native_rows(ordinary["probes"])))
        confirmation_cpu_s = process_time() - started
        return tuple(receiver_type(receiver_id=rx, candidates=()) for rx in receivers)

    status = analyze(window, source.receiver_ids, None, policy, detector=detect)
    support = dict(
        sequence=window.sequence,
        visit=int(window.acquisition["global_visit"]),
        iq_sha256=window.iq_sha256,
        sample_start=status.sample_start,
        sample_end=status.sample_end,
        status=status.status,
        reason=status.reason,
        segment=ordinary["segment"],
    )
    return dict(
        support,
        decisions=[(rx, rank, value.passed) for (rx, rank), value in values.items()],
        confirmation_cpu_s=confirmation_cpu_s,
    )


def stream(case):
    """Archive-owner worker. Each segment reader validates its complete IQ stream."""
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window
    from leo.storage.fast_scan import FastSegmentSource

    case_id = case["id"]
    policy = FastScanPolicyV2()
    _bind_producer(case, PRODUCERS[case_id], policy)
    source_dir = ORDINARY / SOURCE_NAMES[case_id]
    rows = defaultdict(list)
    for lane in range(2):
        with (source_dir / f"replayed-{lane}.jsonl").open() as stream:
            for record in map(json.loads, stream):
                if record["kind"] == "visit":
                    rows[record["segment"]].append(record)

    confirmations = {}
    archive = (BULK / "leo/fast-scan-recordings").resolve()
    code = _sha(Path(pilot_confirmation.__file__))
    for segment, locator in enumerate(case["recording"]["segments"]):
        manifest = (BULK / locator["path"]).resolve()
        if manifest.name != "manifest.json" or not manifest.is_relative_to(archive):
            raise ValueError("whole gate read must stay in the authenticated recording archive")
        source = FastSegmentSource(
            dict(path=str(manifest.parent), manifest_digest="sha256:" + locator["sha256"])
        )
        for window, ordinary in zip(source.windows(), rows[segment], strict=True):
            edge = window.target["edge"]
            if edge not in confirmations:
                confirmations[edge] = pilot_confirmation.PilotConfirmation(
                    policy.sample_rate_hz, edge
                )
            row = _raw_visit(
                window,
                source,
                ordinary,
                confirmations[edge],
                policy,
                analyze_window,
                FastScanReceiverV1,
            )
            print(encoded(row).decode(), flush=True)
        print("fully authenticated segment", segment, file=sys.stderr, flush=True)
    print(encoded(dict(terminal=True, method_sha256=code)).decode(), flush=True)


def read_gate(receipt, visits, partial):
    """Require complete authority and agreement with the original frozen sample decisions."""
    gate = {}
    confirmation_cpu_s = 0.0
    code = _sha(Path(pilot_confirmation.__file__))
    with receipt.open() as source:
        for row in map(json.loads, source):
            if row.get("terminal") is True:
                if row["method_sha256"] != code or source.readline():
                    raise ValueError("whole gate terminal authority differs from the frozen method")
                break
            visit = row["visit"]
            ordinary = visits.get(visit)
            if (
                ordinary is None
                or visit in gate
                or any(
                    row[key] != ordinary[key] for key in (*SUPPORT, "sample_start", "sample_end")
                )
            ):
                raise ValueError("whole gate replay changed visit support")
            values = {(rx, rank): passed for rx, rank, passed in row["decisions"]}
            if len(values) != len(row["decisions"]):
                raise ValueError("whole gate replay returned a duplicate proposal decision")
            gate[visit] = values
            confirmation_cpu_s += row["confirmation_cpu_s"]
        else:
            raise ValueError("whole gate worker lacks terminal authority")
    if gate.keys() != visits.keys() or any(
        gate[visit] != expected for visit, expected in partial.items()
    ):
        raise ValueError("whole gate replay omitted a visit or changed a frozen sample decision")
    return gate, confirmation_cpu_s


def run(case_id, work):
    started = perf_counter()
    case = _load_case(case_id)
    original, ordinary_path, visits, metrics = verified_ordinary(case)
    measured, advanced = verify_selection(case, original)
    partial = decisions(visits, measured)
    raw_receipt = work / "raw-confirmation.jsonl"
    producer = PRODUCERS[case_id]
    with raw_receipt.open("xb") as receipt, (work / "raw-confirmation.log").open("xb") as log:
        subprocess.run(
            [
                "timeout",
                "--kill-after=3s",
                "450s",
                "sudo",
                "-n",
                "-u",
                "leo",
                "--",
                "env",
                f"PYTHONPATH={producer.root}:{REPO}",
                *(f"{k}={v}" for k, v in SINGLE_THREAD.items()),
                str(ARCHIVE_PYTHON),
                "-Bu",
                "-m",
                MODULE,
                "--stream",
            ],
            input=encoded(case),
            stdout=receipt,
            stderr=log,
            check=True,
        )
    gate, cpu_s = read_gate(raw_receipt, visits, partial)
    identity = [
        "late-pilot-confirmation-full",
        _sha(Path(pilot_confirmation.__file__)),
        [(visit, sorted(values.items())) for visit, values in sorted(gate.items())],
    ]
    document, intervention = apply_gate(original, visits, gate, identity, BOUNDARY)
    save(work / "full-native.json", document)
    raw_wall_s = perf_counter() - started
    remaining = int(DEADLINE_S - raw_wall_s)
    if remaining <= 0:
        raise TimeoutError("whole late-pilot replay ended before its position phase")
    v5_lean.TIMEOUT_S = remaining
    fit(
        case,
        work / "full-native.json",
        work / METHOD,
        METHOD,
        BOUNDARY,
        dict(
            metrics,
            **intervention,
            positive_candidates=metrics["positive_candidates"]
            - intervention["removed_original_positive_candidates"],
            detector_sample_advancement_passed=advanced,
            raw_confirmation_cpu_s=cpu_s,
            raw_gate_and_assembly_wall_s=raw_wall_s,
            raw_receipt_sha256=_sha(raw_receipt),
            confirmation_sha256=_sha(Path(pilot_confirmation.__file__)),
            full_gate_runner_sha256=_sha(Path(__file__)),
            identical_overlap_visits=len(partial),
            ordinary_input_sha256="sha256:" + _sha(ordinary_path),
        ),
    )


def main():
    if sys.argv[1:] == ["--stream"]:
        return stream(json.load(sys.stdin))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--publish", type=Path)
    args = parser.parse_args()
    work = local_output(args.work)
    if work.is_relative_to(BULK):
        parser.error("use replay scratch outside the data archive")
    if args.publish is not None and args.case is None:
        rows = [json.loads((work / case / METHOD / "receipt.json").read_bytes()) for case in CASES]
        for case_id, row in zip(CASES, rows, strict=True):
            if row["id"] != case_id or row["method"] != METHOD:
                raise ValueError("whole gate position receipt belongs to a different replay")
            bind_published_source(row)
            row.update(method=PUBLISHED_METHOD, variant="all-visits")
        write(
            args.publish / "full-positions.jsonl.gz",
            gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0),
        )
        return
    if args.case is None or args.publish is not None:
        parser.error("select one replay case or publish two completed cases")
    if len(os.sched_getaffinity(0)) != 1 or any(
        os.environ.get(key) != value for key, value in SINGLE_THREAD.items()
    ):
        parser.error("pin live replay to one CPU and one thread per numerical runtime")
    case_work = work / args.case
    case_work.mkdir(parents=True, exist_ok=False)
    run(args.case, case_work)


if __name__ == "__main__":
    main()
