"""Pair the native wide interpolation block on authenticated raw visits and controls."""

import argparse
import ctypes as ct
import gzip
import json
import os
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import distribution
from ..variants import iq_stream
from . import full_stride_audit, ordinary_front_eval, scout_stride_eval, wide_kernel_build
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import _from_native, _load_case, _probe, _sha
from .pilot_kernel_eval import _digest, _windows
from .wide_regional_eval import RATE, templates, validate

REPORT = ROOT / "reports/2026_11_19_receiver_screening/track-recovery/wide-kernel"
WORK = Path("/var/tmp/leo-wide-kernel-20261119")
WHOLE = Path("/home/mouse9911/.cache/leo-core-20261119-xJ4vRNwV/full-stride")
CASES = ("DS26-0036", "DS26-0162", "DS29-0082", "DS29-0519")
PANEL = (CASES[0], CASES[2])
MODES = ("control", "candidate")


def load(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def release(work):
    primary = load(work / "release/release.json")
    trace = load(work / "trace/release.json")
    if primary["control"] != trace["control"] or primary["trace"] or not trace["trace"]:
        raise ValueError("production and instrumented priorities differ from the release plan")
    bound = {k: primary[k] for k in MODES} | {"trace": trace["candidate"]}
    if any(_sha(Path(r["path"])) != r["sha256"] for r in bound.values()):
        raise ValueError("native library identity changed")
    return bound


def held_roster(ident):
    prior = scout_stride_eval.REPORT
    path = prior / f"{ident}-held.json.gz"
    if _sha(path) != load(prior / "prediction-lock.json")["files"][path.name]:
        raise ValueError("held waveform receipt changed")
    slots = ((s, i) for s, visits in scout_stride_eval.SCHEDULE for i in visits)
    rows = []
    for (segment, sequence), row in zip(slots, load(path)["rows"], strict=True):
        if sequence != row["sequence"]:
            raise ValueError("held waveform receipt changed its raw visit order")
        rows.append(
            dict(
                cohort="held",
                segment=segment,
                sequence=sequence,
                visit=row["visit"],
                iq_sha256=row["iq_sha256"],
                status=row["status"],
                product_sha256=row.get("payload_sha256", {}).get("control"),
            )
        )
    return rows


def tail_roster(ident, whole, resource, factor_sha):
    source = whole / ident / "control"
    raw = load(source / "raw.json")
    if (raw["native_sha256"].removeprefix("sha256:"), raw["counts"]) != (
        factor_sha,
        resource["counts"],
    ):
        raise ValueError("tail timing ledger does not name the sealed detector factor")
    candidates = []
    for lane, lane_data in enumerate(raw["lanes"]):
        clocks = lane_data["native_timings_s"]
        if {k: v for k, v in lane_data.items() if k != "native_timings_s"} != resource["lanes"][
            lane
        ]:
            raise ValueError("detector tail ledger lane metadata changed")
        with (source / f"recording/replayed-{lane}.jsonl").open() as stream:
            rows = (
                r
                for r in map(json.loads, stream)
                if r["kind"] == "visit" and r["status"] == "processed"
            )
            for (wall, cpu), row in zip(clocks, rows, strict=True):
                candidates.append(
                    dict(
                        {
                            k: row[k]
                            for k in ("segment", "sequence", "visit", "iq_sha256", "status")
                        },
                        cohort="cpu-tail",
                        old_wall_s=wall,
                        old_cpu_s=cpu,
                        product_sha256=_digest(encoded(row["probes"])),
                    )
                )
    if (
        len(candidates) != resource["dual_calls"]
        or sum(r["old_wall_s"] <= 0.02 for r in candidates) != resource["within_20ms"]
        or distribution([r["old_cpu_s"] * 1000 for r in candidates])
        != resource["detector_call_cpu_ms"]
    ):
        raise ValueError("detector tail ledger times differ from the sealed CPU distribution")
    return sorted(candidates, key=lambda r: (-r["old_cpu_s"], r["visit"]))[:2]


def source_files():
    return (
        Path(__file__),
        Path(wide_kernel_build.__file__),
        Path(wide_kernel_build.wide_kernel.__file__),
        wide_kernel_build.wide_kernel.HEADER,
        Path(ordinary_front_eval.__file__),
        Path(iq_stream.__file__),
        REPORT / "PROTOCOL.md",
        ROOT / "src/leo/analysis/starlink/native_short_window.py",
        scout_stride_eval.REPORT / "prediction-lock.json",
        full_stride_audit.REPORT / "prediction-lock.json",
    )


def freeze(work, whole):
    seal, checksum, source, resources = full_stride_audit.archive(full_stride_audit.REPORT)
    control = full_stride_audit.check.positions(
        full_stride_audit.REPORT,
        seal,
        full_stride_audit.published.method(source["spec"]["id"], "control"),
    )
    roster = {}
    for ident in CASES:
        tails = tail_roster(
            ident, whole, resources[ident]["control"], control[ident]["native_sha256"]
        )
        roster[ident] = (held_roster(ident) if ident in PANEL else []) + tails
    return dict(
        cases=roster,
        release=release(work),
        whole_prediction_sha256=checksum,
        source_files={str(path.relative_to(ROOT)): _sha(path) for path in source_files()},
    )


def verify(window, bound, status):
    if (
        window.iq_sha256 != bound["iq_sha256"]
        or status != bound["status"]
        or int(window.acquisition["global_visit"]) != bound["visit"]
    ):
        raise ValueError("raw visit identity or authenticated validity changed")


def counters(library):
    readback = ct.CDLL(library).leo_wide_kernel_fractional_counts
    readback.argtypes = [ct.POINTER(ct.c_uint64)]
    readback.restype = None

    def read():
        out = (ct.c_uint64 * 3)()
        readback(out)
        vector, tail, slow = out
        scalar = tail + slow
        return dict(
            batched_samples=vector,
            scalar_tail_samples=tail,
            scalar_binade_samples=slow,
            ordered_tap_multiplies_before=16 * (vector + scalar),
            ordered_tap_multiplies_after=16 * (vector // 2 + scalar),
        )

    return read


def benchmark(sample, contexts, count, index):
    def call(values, mode):
        wall, cpu = perf_counter_ns(), process_time_ns()
        out = contexts[mode].analyze(values, include_timings=True)
        return out, dict(
            wall_ms=(perf_counter_ns() - wall) / 1e6, python_cpu_ms=(process_time_ns() - cpu) / 1e6
        )

    with patch.object(ordinary_front_eval, "MODES", MODES):
        result = ordinary_front_eval.benchmark(sample, call, index, 9)
    for d in result["payloads"].values():
        validate(d, 800_000)
    count()
    trace = contexts["trace"].analyze(sample)
    result["instrumented_work"] = count()
    result["trace_payload_exact"] = encoded(trace) == encoded(result["payloads"]["candidate"])
    if not (result["stable"] and result["trace_payload_exact"]):
        raise ValueError("the repeated native or instrumented payload is unstable")
    return result


def planted(window):
    for i, (name, tones) in enumerate(
        (
            ("empty", ()),
            ("noise", ()),
            ("weak", ((735, 479875, 128),)),
            ("positive-edge", ((730, 799875, 640),)),
            ("negative-edge", ((731, -799875, 640),)),
        )
    ):
        sample = (
            np.zeros_like(window.samples)
            if name == "empty"
            else _test_signal(window, tones, 59491 + i).samples
        )
        yield name, sample, tones


def replay(ident, lock):
    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    case, policy = _load_case(ident), FastScanPolicyV2()
    result, canaries = [], {}
    with ExitStack() as stack:
        # One selected visit can sit near the end of a 64-visit archive chunk.
        # Prefix decoding keeps per-window SHA checks and discards unused samples.
        budget = 128 * iq_stream.MIB
        stack.enter_context(
            patch.multiple(iq_stream, MAX_CHUNK_PREFIX=budget, MAX_DECODE_BYTES=budget)
        )
        for index, row in enumerate(lock["cases"][ident]):
            (window,) = _windows(case, row["segment"], (row["sequence"],))
            status = analyze_window(
                window,
                window.receiver_ids,
                None,
                policy,
                detector=lambda _, ids: tuple(
                    FastScanReceiverV1(receiver_id=i, candidates=()) for i in ids
                ),
            ).status
            verify(window, row, status)
            if not index:
                edge = window.target["edge"]
                pair = templates(RATE, edge)
                contexts = {
                    mode: stack.enter_context(
                        NativeShortWindow(
                            rule["path"],
                            *pair,
                            sample_rate_hz=RATE,
                            fractional_epoch=True,
                        )
                    )
                    for mode, rule in lock["release"].items()
                }
                count = counters(lock["release"]["trace"]["path"])
                for ctx in contexts.values():
                    ctx.analyze(window.samples)
            if status != "processed":
                result.append(row)
                continue
            measured = benchmark(window.samples, contexts, count, index)
            baseline = measured["payloads"]["control"]
            if row["cohort"] == "held":
                product = baseline
            else:
                product = [
                    _probe(
                        window,
                        rx["receiver_id"],
                        (_from_native(i, c) for i, c in enumerate(rx["candidates"])),
                    )
                    for rx in baseline["rows"]
                ]
            if _digest(encoded(product)) != row["product_sha256"]:
                raise ValueError("baseline detector output differs from the authenticated archive")
            result.append(dict(row, **measured))
            if ident in PANEL and not canaries:
                canaries = {
                    name: dict(
                        tones=tones,
                        iq_sha256=_digest(x.tobytes()),
                        **benchmark(x, contexts, count, i),
                    )
                    for i, (name, x, tones) in enumerate(planted(window))
                }
    return dict(
        id=ident,
        cpu_affinity=sorted(os.sched_getaffinity(0)),
        source_lock_sha256=_digest(encoded(lock)),
        rows=result,
        controls=canaries,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=("freeze", *CASES))
    p.add_argument("--work", default=WORK, type=local_output)
    p.add_argument("--whole-scratch", default=WHOLE, type=local_output)
    a = p.parse_args()
    target = REPORT / "source-lock.json"
    if a.stage == "freeze":
        if target.exists():
            raise ValueError("the raw visit schedule was already sealed")
        save_json(target, freeze(a.work, a.whole_scratch))
        return
    lock = load(target)
    if lock["release"] != release(a.work) or any(
        _sha(ROOT / p) != sha for p, sha in lock["source_files"].items()
    ):
        raise ValueError("frozen native experiment changed before replay")
    result = replay(a.stage, lock)
    write(REPORT / f"{a.stage}.json.gz", gzip.compress(encoded(result), mtime=0))


if __name__ == "__main__":
    main()
