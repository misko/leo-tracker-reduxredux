"""Time stock, full-bank rescue, one-region rescue, and one-region sham on saved IQ."""

import argparse
import gzip
import hashlib
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, write
from ..variants import hinted_glrt, incremental_rescue, iq_stream
from . import center_union_eval as original
from . import (
    hinted_glrt_trial,
    incremental_rescue_build,
    ordinary_front_eval,
    whole_fftw_trial,
)
from . import incremental_rescue_gate as gate
from .full_v5_check import _load_case, _probe, _sha, compare_probes
from .pilot_kernel_eval import _digest, _windows
from .wide_regional_eval import RATE

REPORT = gate.REPORT
MODES = ("stock", "full", "incremental", "sham")
CLOCKS = ("scout_cpu_ns", "scout_wall_ns", "rescue_cpu_ns", "rescue_wall_ns")


def freeze(work):
    source = original.REPORT / "source-lock.json.gz"
    lock = whole_iq.read(original.REPORT / "evidence-lock.json")
    whole_iq.checked(source, lock["files"][source.name])
    paths, release = gate.release(work)
    prior = whole_fftw_trial.qualified()["hinted"]
    paths["hinted"] = prior["path"]
    hashes = dict(release["sha256"], hinted=prior["sha256"])
    whole_iq.checked(Path(prior["path"]), prior["sha256"])
    files = (
        Path(__file__),
        REPORT / "feature-gate.json",
        source,
        original.REPORT / "evidence-lock.json",
    )
    return dict(
        capture=original.load(source)["capture"],
        paths=paths,
        sha256=hashes,
        sources={str(p.relative_to(ROOT)): _sha(p) for p in files},
    )


def sham_epoch(identity, rx):
    return int.from_bytes(hashlib.sha256(f"{identity}:{rx}".encode()).digest()) % 13_333


def use_full(stock, native, proposals):
    hints = tuple(centers[0] if centers else None for centers, _ in proposals)
    if any(epoch is not None for epoch in hints):
        output, details = native(hints)
        selected = [
            gate.positive(p) and not gate.positive(s)
            for s, p in zip(stock["rows"], output["rows"], strict=True)
        ]
        rows = [
            p if take else s
            for s, p, take in zip(stock["rows"], output["rows"], selected, strict=True)
        ]
        return dict(stock, rows=rows), details
    return stock, []


def without_clock(trace):
    return [{k: v for k, v in lane.items() if k not in CLOCKS} for lane in trace]


def measure(sample, native, full, candidate, sham, scout, edge, identity, index):
    signatures, traces, proposals_by_mode = {}, {}, {}
    times = {mode: [] for mode in MODES}
    for repeat in range(3):
        slot = (index + repeat) % len(MODES)
        for mode in MODES[slot:] + MODES[:slot]:
            trace, proposals, breakdown = [], None, None
            wall, cpu = perf_counter_ns(), process_time_ns()
            if mode in ("stock", "full"):
                output = native.analyze(sample)
                if mode == "full":
                    start_wall, start_cpu = perf_counter_ns(), process_time_ns()
                    proposals = [
                        ([], []) if gate.positive(row) else scout(sample, edge, rx)
                        for rx, row in enumerate(output["rows"])
                    ]
                    full_wall, full_cpu = perf_counter_ns(), process_time_ns()
                    output, trace = use_full(output, lambda hints: full(sample, hints), proposals)
                    breakdown = dict(
                        stock_cpu_ns=start_cpu - cpu,
                        stock_wall_ns=start_wall - wall,
                        scout_cpu_ns=full_cpu - start_cpu,
                        scout_wall_ns=full_wall - start_wall,
                        rescue_cpu_ns=process_time_ns() - full_cpu,
                        rescue_wall_ns=perf_counter_ns() - full_wall,
                    )
            else:
                output, proposals, trace, breakdown = (
                    candidate if mode == "incremental" else sham
                )(sample)
            measured_wall, measured_cpu = perf_counter_ns() - wall, process_time_ns() - cpu
            signature = ordinary_front_eval._payload(output)
            trace = without_clock(trace)
            if (
                encoded(signature) != encoded(signatures.setdefault(mode, signature))
                or encoded(trace) != encoded(traces.setdefault(mode, trace))
                or encoded(proposals) != encoded(proposals_by_mode.setdefault(mode, proposals))
            ):
                raise ValueError(f"{identity} {mode} changed its deterministic detection fields")
            times[mode].append(
                dict(
                    wall_ms=measured_wall / 1e6,
                    cpu_ms=measured_cpu / 1e6,
                    breakdown=breakdown,
                )
            )
    if proposals_by_mode["full"] != proposals_by_mode["incremental"]:
        raise ValueError("full and incremental did not see identical desired hints")
    for role in ("incremental", "sham"):
        attempted = [lane["rx"] for lane in traces[role] if lane["decision"] != "stock_positive"]
        gate.check(signatures["stock"], signatures[role], traces[role], attempted)
    return dict(payloads=signatures, traces=traces, timings=times, proposals=proposals_by_mode)


def account(data, targets):
    factors = original.projections(data["payloads"])
    return dict(
        data,
        gate_counts={
            role: [sum(c["passed_fractional_margin_gate"] for c in p["candidates"]) for p in rows]
            for role, rows in factors.items()
        },
        gate_transitions={
            role: [compare_probes(a, b, RATE) for a, b in zip(factors["stock"], rows, strict=True)]
            for role, rows in factors.items()
            if role != "stock"
        },
        target_results=original.endpoints(data, factors, targets),
        target_count=len(targets),
    )


def replay(edge, lock):
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    outputs, controls = [], {}
    identity = None
    with ExitStack() as stack:
        native = gate.attach(stack, lock["paths"], edge, ("stock", "detector", "hinted"))
        scout = stack.enter_context(
            incremental_rescue.SingleLaneScout(lock["paths"]["scout"], edge)
        )
        full = hinted_glrt.HintedCall(native["hinted"])
        candidate = incremental_rescue.IncrementalRescueCall(native["detector"], edge, scout=scout)

        def nominate(_, band, rx):
            return [sham_epoch(identity, rx)], []

        sham = incremental_rescue.IncrementalRescueCall(native["detector"], edge, scout=nominate)
        for index, row in enumerate(r for r in lock["capture"] if r["edge"] == edge):
            identity = f"{row['case']}:{row['visit']}"
            case = _load_case(row["case"])
            if row["cohort"] == "additional":
                with patch.object(iq_stream, "MAX_CHUNK_PREFIX", 48 * iq_stream.MIB):
                    (window,) = _windows(case, row["segment"], (row["sequence"],))
                targets = []
            else:
                window = hinted_glrt_trial.load_selected(case, row)
                targets = [(row["receiver"], row["target"])]
            if window.iq_sha256 != row["iq_sha256"] or window.target["edge"] != edge:
                raise ValueError(f"{identity} differs from the frozen waveform")
            status = analyze_window(
                window,
                window.receiver_ids,
                None,
                FastScanPolicyV2(),
                detector=lambda _, ids: tuple(
                    FastScanReceiverV1(receiver_id=i, candidates=()) for i in ids
                ),
            ).status
            measured = {}
            if status == "processed":
                data = measure(
                    window.samples,
                    native["stock"],
                    full,
                    candidate,
                    sham,
                    scout,
                    edge,
                    identity,
                    index,
                )
                if "baseline" in row:
                    factors = original.projections(data["payloads"])["stock"]
                    stock = [_probe(window, i, p["candidates"]) for i, p in enumerate(factors)]
                    if encoded(stock) != encoded(row["baseline"]):
                        raise ValueError(
                            f"{identity} baseline differs from the archived projection"
                        )
                measured = account(data, targets)
            outputs.append(dict(row, status=status, **measured))
        for index, (name, sample, targets) in enumerate(original.synthetic(edge)):
            identity = f"control:{edge}:{name}"
            data = measure(
                sample, native["stock"], full, candidate, sham, scout, edge, identity, index
            )
            controls[name] = dict(iq_sha256=_digest(sample.tobytes()), **account(data, targets))
    return dict(edge=edge, measured=outputs, controls=controls, lock_sha256=_digest(encoded(lock)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "lower", "upper"))
    parser.add_argument("--work", type=local_output, default=incremental_rescue_build.WORK)
    args = parser.parse_args()
    target = REPORT / "source-lock.json.gz"
    if args.stage == "freeze":
        if target.exists():
            raise ValueError("retaining prospectively locked roster and source")
        write(target, gzip.compress(encoded(freeze(args.work)), mtime=0))
        return
    lock = original.load(target)
    for name, digest in lock["sources"].items():
        whole_iq.checked(ROOT / name, digest)
    for role, path in lock["paths"].items():
        whole_iq.checked(Path(path), lock["sha256"][role])
    data = replay(args.stage, lock)
    write(REPORT / f"{args.stage}.json.gz", gzip.compress(encoded(data), mtime=0))


if __name__ == "__main__":
    main()
