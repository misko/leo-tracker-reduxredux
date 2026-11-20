"""Qualify fixed-coordinate late pilots on a bounded, authenticated IQ sample."""

import argparse
import gzip
import json
import os
import subprocess
import sys
from contextlib import ExitStack
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time

import numpy as np

from ..__main__ import encoded, write
from ..scoring import validate_result
from ..variants import pilot_confirmation
from ..variants.iq_stream import load_windows
from ..variants.pilot_confirmation import PilotConfirmation
from .full_v5_check import (
    BULK,
    MARGIN_GATE,
    NATIVE_LIBRARY,
    PRODUCERS,
    REPO,
    _bind_producer,
    _from_native,
    _load_case,
    _probe,
    _sha,
    compare_probes,
)
from .recording_to_v5 import ARCHIVE_PYTHON, SINGLE_THREAD, save

SEGMENTS = (0, 2, 4, 6, 8, 10, 12)
HOLDOUT_SEGMENTS = (1, 3, 5, 7, 9, 11, 13)
SEQUENCES = tuple(range(8))
EXCLUSION_WINDOWS = {"DS26-0036": (8, 22, 4118), "DS29-0082": (0, 1, 1)}


def _archive(case):
    path = BULK / case["native"]["path"]
    if _sha(path) != case["native"]["sha256"]:
        raise ValueError("the archived producer factors differ from their frozen hash")
    artifact = json.loads(path.read_bytes())
    if (
        artifact["source"]["session_id"] != case["session_id"]
        or artifact["provenance"]["run_id"] != case["run_id"]
    ):
        raise ValueError("the archived producer factors belong to a different run")
    return (
        {(r["visit_index"], r["receiver_id"]): r for r in artifact["source"]["probes"]},
        {r["visit"]: r for r in artifact["provenance"]["excluded_windows"]},
    )


def _classify(window, receivers, rows, evidence, reference):
    visit = window.acquisition["global_visit"]
    results = []
    for row in rows:
        receiver = row["receiver_id"]
        native = _probe(
            window,
            receivers[receiver],
            (_from_native(i, c) for i, c in enumerate(row["candidates"])),
        )
        production = reference[visit, receiver]
        comparison = compare_probes(production, native, window.sample_rate_hz)
        matched = {pair["native_rank"] for pair in comparison["positive_matches"]}
        for candidate in native["candidates"]:
            rank = candidate["candidate_rank"]
            if not candidate["passed_fractional_margin_gate"]:
                group = "native_below_margin"
            else:
                group = "archive_matched" if rank in matched else "native_only"
            results.append(
                dict(
                    candidate,
                    receiver=receiver,
                    group=group,
                    conditioned_fallback=row["candidates"][rank]["conditioned_fallback"],
                    confirmation=asdict(evidence[receiver, rank]),
                )
            )
    return results


def summarize(rows):
    groups = {}
    for row in rows:
        for candidate in row["candidates"]:
            label = candidate["group"]
            group = groups.setdefault(label, {"count": 0, "confirmed": 0})
            group["count"] += 1
            group["confirmed"] += int(candidate["confirmation"]["passed"])
    for group in groups.values():
        group["rate"] = group["confirmed"] / group["count"]
    positive = [
        row["confirmation_cpu_ms"] for row in rows if row["confirmation_cpu_ms"] is not None
    ]
    matched = groups.get("archive_matched", {}).get("rate", 0.0)
    native_only = groups.get("native_only", {}).get("rate", 1.0)
    median, p95 = np.percentile(positive, (50, 95))
    return dict(
        groups=groups,
        processed=len(positive),
        invalid_capture=len(rows) - len(positive),
        median_cpu_ms=float(median),
        p95_cpu_ms=float(p95),
        passed=bool(matched >= 0.85 and matched - native_only >= 0.15 and median < 10 and p95 < 25),
    )


def replay(case_id, library, segments=SEGMENTS):
    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    case = _load_case(case_id)
    policy = FastScanPolicyV2()
    producer = _bind_producer(case, PRODUCERS[case_id], policy)
    reference, exclusions = _archive(case)
    rate = policy.sample_rate_hz
    receipts = []
    library_digest = _sha(library)

    def make_trial(edge, stack):
        exact = np.asarray(qin_edge_pilot_frame(rate, edge), dtype="<c16")
        control = np.asarray(
            qin_edge_pilot_frame(rate, edge, symbol_roll=CONTROL_SYMBOL_ROLL), dtype="<c16"
        )
        native = stack.enter_context(
            NativeShortWindow(
                str(library), exact, control, sample_rate_hz=rate, fractional_epoch=True
            )
        )
        return (
            native,
            PilotConfirmation(rate, edge),
            PilotConfirmation(rate, edge, minimum_margin=-np.inf),
        )

    contexts = {}
    with ExitStack() as stack:
        for segment in segments:
            locator = case["recording"]["segments"][segment]
            windows = load_windows(
                dict(
                    recording_path=str(BULK / locator["path"]),
                    recording_sha256="sha256:" + locator["sha256"],
                ),
                SEQUENCES,
            )
            for window in windows:
                edge = window.target["edge"]
                if edge not in contexts:
                    contexts[edge] = make_trial(edge, stack)
                visit = window.acquisition["global_visit"]
                record = dict(
                    segment=segment,
                    sequence=window.sequence,
                    visit=visit,
                    iq_sha256=window.iq_sha256,
                    candidates=[],
                    confirmation_cpu_ms=None,
                    confirmation_wall_ms=None,
                    native_cpu_ms=None,
                )

                def detect(window, receivers, context=contexts[edge], receipt=record):
                    native, production_confirmation, diagnostic_confirmation = context
                    cpu = process_time()
                    rows = native.analyze(window.samples)["rows"]
                    receipt["native_cpu_ms"] = 1000 * (process_time() - cpu)
                    cpu, wall = process_time(), perf_counter()
                    positive = production_confirmation(window.samples, rows)
                    receipt["confirmation_cpu_ms"] = 1000 * (process_time() - cpu)
                    receipt["confirmation_wall_ms"] = 1000 * (perf_counter() - wall)
                    all_candidates = diagnostic_confirmation(window.samples, rows)
                    if any(all_candidates[key] != value for key, value in positive.items()):
                        raise ValueError("diagnostic and positive-only scoring differ")
                    receipt["candidates"] = _classify(
                        window, receivers, rows, all_candidates, reference
                    )
                    return tuple(
                        FastScanReceiverV1(receiver_id=rx, candidates=()) for rx in receivers
                    )

                status = analyze_window(window, window.receiver_ids, None, policy, detector=detect)
                record.update(status=status.status, reason=status.reason)
                if status.status == "invalid_capture":
                    expected = dict(
                        visit=visit,
                        reason=status.reason,
                        iq_sha256=window.iq_sha256,
                        sample_start=status.sample_start,
                        sample_end=status.sample_end,
                    )
                    if (
                        exclusions.get(visit) != expected
                        or record["confirmation_cpu_ms"] is not None
                    ):
                        raise ValueError("archived invalid capture differs from fresh validation")
                elif status.status != "processed" or visit in exclusions:
                    raise ValueError("archived and fresh capture status disagree")
                receipts.append(record)
            print(case_id, "segment", segment, "verified", flush=True)
    if _sha(library) != library_digest:
        raise ValueError("native detector binary changed during the qualification")
    return dict(
        case=case_id,
        producer=producer,
        native_sha256=library_digest,
        archive_sha256=case["native"]["sha256"],
        source_sha256={
            "trial": _sha(Path(__file__)),
            "confirmation": _sha(Path(pilot_confirmation.__file__)),
        },
        cpus=sorted(os.sched_getaffinity(0)),
        sample_rate_hz=rate,
        native_margin=MARGIN_GATE,
        summary=summarize(receipts),
        windows=receipts,
    )


def _read_exclusion(locator, sequence):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window
    from leo.storage.fast_scan import FastSegmentSource

    source = FastSegmentSource(
        dict(
            path=str((BULK / locator["path"]).parent),
            manifest_digest="sha256:" + locator["sha256"],
        ),
        start_sequence=sequence,
        stop_sequence=sequence + 1,
    )
    (window,) = source.windows()

    def unexpected_detector(*_):
        raise ValueError("excluded IQ reached the detector")

    status = analyze_window(
        window, source.receiver_ids, None, FastScanPolicyV2(), detector=unexpected_detector
    )
    if status.status != "invalid_capture":
        raise ValueError("targeted IQ exclusion did not reproduce the capture status")
    return dict(
        visit=window.acquisition["global_visit"],
        reason=status.reason,
        iq_sha256=window.iq_sha256,
        sample_start=status.sample_start,
        sample_end=status.sample_end,
    )


def audit_exclusion(case_id):
    """Exercise capture validation on one independently selected archive exclusion."""
    from leo.contracts.fast_scan_native import FastScanPolicyV2

    case = _load_case(case_id)
    producer = PRODUCERS[case_id]
    _bind_producer(case, producer, FastScanPolicyV2())
    _, exclusions = _archive(case)
    segment, sequence, visit = EXCLUSION_WINDOWS[case_id]
    locator = case["recording"]["segments"][segment]
    worker = subprocess.run(
        [
            "sudo",
            "-n",
            "-u",
            "leo",
            "--",
            "env",
            f"PYTHONPATH={producer.root}:{REPO}",
            *(f"{k}={v}" for k, v in SINGLE_THREAD.items()),
            str(ARCHIVE_PYTHON),
            "-B",
            "-m",
            __spec__.name,
            "--exclusion-worker",
        ],
        input=json.dumps([locator, sequence]),
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    receipt = json.loads(worker.stdout)
    if receipt != exclusions[visit]:
        raise ValueError("targeted IQ exclusion did not reproduce the capture archive")
    return dict(
        case=case_id, segment=segment, sequence=sequence, status="invalid_capture", **receipt
    )


def write_predictions(directory):
    """Publish detector measurements and explicit null position results for the gallery."""
    rows = []
    for case_id in PRODUCERS:
        reports = [
            json.loads(gzip.decompress((directory / f"{case_id}-{sample}.json.gz").read_bytes()))
            for sample in ("trial", "alternate")
        ]
        windows = [window for receipt in reports for window in receipt["windows"]]
        valid = [window for window in windows if window["status"] == "processed"]
        cpu_s = sum(w["confirmation_cpu_ms"] for w in valid) / 1000
        wall_s = sum(w["confirmation_wall_ms"] for w in valid) / 1000
        method_digest = reports[0]["source_sha256"]["confirmation"]
        if any(report["source_sha256"]["confirmation"] != method_digest for report in reports):
            raise ValueError("alternate sample changed the verification implementation")
        result = dict(
            status="withheld",
            boundary="Fixed late-pilot confirmation on authenticated dual-CI16 visits",
            reason=(
                "Matched-versus-native-only retention contrast missed the predeclared threshold. "
                "No whole-recording position fit was run for this gate."
            ),
            arms={name: {"latlon": None} for name in ("c0", "fitted_c")},
            metrics=dict(
                position_attempted=False,
                windows=len(windows),
                processed=len(valid),
                invalid_capture=len(windows) - len(valid),
                raw_confirmation_cpu_s=cpu_s,
                raw_confirmation_wall_s=wall_s,
                original_native_cpu_s=sum(w["native_cpu_ms"] for w in valid) / 1000,
                trial=reports[0]["summary"],
                alternate=reports[1]["summary"],
            ),
        )
        validate_result(result)
        rows.append(
            dict(
                id=case_id,
                method="pilot_confirmation",
                input_sha256=sha256(encoded([w["iq_sha256"] for w in windows])).hexdigest(),
                implementation_sha256=method_digest,
                worker_wall_s=wall_s,
                worker_cpu_s=cpu_s,
                result=result,
            )
        )
    data = b"".join(encoded(record) + b"\n" for record in rows)
    write(directory / "positions.jsonl.gz", gzip.compress(data, mtime=0))


def main():
    if sys.argv[1:] == ["--exclusion-worker"]:
        print(json.dumps(_read_exclusion(*json.load(sys.stdin))))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=PRODUCERS, required=True)
    parser.add_argument("--library", type=Path, default=NATIVE_LIBRARY)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--holdout", action="store_true", help="use the seven alternate segments")
    mode.add_argument("--audit-exclusion", action="store_true", help="verify one archive exclusion")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if len(os.sched_getaffinity(0)) != 1 or any(
        os.environ.get(k) != v for k, v in SINGLE_THREAD.items()
    ):
        parser.error("pin to one CPU and set one thread per numerical runtime")
    output = args.out.resolve()
    if (
        output.exists()
        or output.is_relative_to(BULK / "leo")
        or output.is_relative_to("/mnt/qnap01")
    ):
        parser.error("choose a new output file outside the recording archive")
    segments = HOLDOUT_SEGMENTS if args.holdout else SEGMENTS
    if args.audit_exclusion:
        save(output, audit_exclusion(args.case))
    else:
        receipt = replay(args.case, args.library.resolve(strict=True), segments)
        write(output, gzip.compress(encoded(receipt) + b"\n", mtime=0))


if __name__ == "__main__":
    main()
