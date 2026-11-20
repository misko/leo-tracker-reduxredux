"""Measure exact wide dual-RX preparation on the existing authenticated saved IQ."""

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
from ..variants import glrt_reuse, iq_stream
from . import glrt_reuse_build, ordinary_front_eval
from . import scout_stage_figures as stage
from . import wide_kernel_eval as wide
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import _load_case, _sha
from .pilot_kernel_eval import _digest, _windows
from .wide_regional_eval import RATE, templates, validate

REPORT = ROOT / "reports/2026_11_19_receiver_screening/acquisition-frontier/glrt-reuse"
WORK = Path("/var/tmp/leo-glrt-reuse-offline.20261119")
STAGES = ("allocation", "preparation", "proposals", "search", "cleanup")
CLOCKS = tuple(f"{s}_{k}_ms" for s in STAGES for k in ("cpu", "wall"))
CASES, MODES = wide.CASES, wide.MODES


class Profile(ct.Structure):
    _fields_ = [(key, ct.c_double) for key in CLOCKS] + [("prepared_complex_times", ct.c_size_t)]


def release(work):
    built = wide.load(work / "build/release.json")
    paths = {role: work / Path(name).relative_to("/work") for role, name in built["paths"].items()}
    if any(_sha(path) != built["library_sha256"][role] for role, path in paths.items()):
        raise ValueError("stock or one-pass library SHA-256 differs from its offline build")
    return dict(built, paths={r: str(p) for r, p in paths.items()})


def freeze(work):
    previous = stage.verify(wide.REPORT, "evidence-lock.json")
    roster = wide.load(wide.REPORT / "source-lock.json")["cases"]
    for ident, rows in roster.items():
        data = wide.load(wide.REPORT / f"{ident}.json.gz")["rows"]
        for row, measured in zip(rows, data, strict=True):
            if any(measured[k] != v for k, v in row.items()):
                raise ValueError("prior measured waveform has a different selection")
            row["reference_payload_sha256"] = measured.get("payload_sha256", {}).get("control")
    programs = (
        Path(__file__),
        Path(glrt_reuse_build.__file__),
        Path(glrt_reuse.__file__),
        glrt_reuse.HEADER,
        REPORT / "PROTOCOL.md",
        *previous,
    )
    return dict(
        roster=roster,
        release=release(work),
        inputs={str(p.relative_to(ROOT)): _sha(p) for p in programs},
    )


def profiler(ctx):
    from leo.analysis.starlink.native_short_window import _Result

    func = ctx._library.leo_native_glrt_analyze_short_window_profiled
    func.argtypes = [
        ct.c_void_p,
        ct.POINTER(ct.c_int16),
        ct.c_size_t,
        ct.POINTER(_Result),
        ct.POINTER(Profile),
    ]
    func.restype = ct.c_int

    def measure(sample):
        out, clocks = _Result(), Profile()
        ctx._check(
            func(
                ctx._context,
                sample.ctypes.data_as(ct.POINTER(ct.c_int16)),
                len(sample),
                ct.byref(out),
                ct.byref(clocks),
            )
        )
        if clocks.prepared_complex_times != 200_000 or out.row_count != 2:
            raise ValueError("public profiler did not execute the complete dual-RX visit")
        return {k: getattr(clocks, k) for k in CLOCKS}

    return measure


def measure(sample, contexts, profiles, index):
    def detector(samples, role):
        cpu, wall = process_time_ns(), perf_counter_ns()
        result = contexts[role].analyze(samples, include_timings=True)
        return result, dict(
            cpu_ms=(process_time_ns() - cpu) / 1e6, wall_ms=(perf_counter_ns() - wall) / 1e6
        )

    with patch.object(ordinary_front_eval, "MODES", MODES):
        results = ordinary_front_eval.benchmark(sample, detector, index, 9)
    for payload in results["payloads"].values():
        validate(payload, 800_000)
    if not results["stable"]:
        raise ValueError("payload changed between fixed warm repetitions")
    for rep in range(9):
        for role in MODES if (rep + index) % 2 else MODES[::-1]:
            results["timings"][role][rep]["profile"] = profiles[role](sample)
    return results


def controls(window):
    alias = 1 / 4.4e-6
    fixtures = {
        "empty": (),
        "noise": (),
        "weak": ((735, 479_875, 128),),
        "positive_edge": ((730, 799_875, 640),),
        "negative_edge": ((731, -799_875, 640),),
        "same_epoch_pair": ((735, 719_750, 480), (735, 559_750, 184)),
        "aliased_pair": ((735, 689_250, 480), (2267, 689_250 - alias, 184)),
    }
    for i, (name, planted) in enumerate(fixtures.items()):
        sample = (
            np.zeros_like(window.samples)
            if name == "empty"
            else _test_signal(window, planted, 59491 + i).samples
        )
        yield name, planted, sample


def replay(ident, lock):
    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    case, policy = _load_case(ident), FastScanPolicyV2()
    output, diagnostic = [], {}
    with ExitStack() as stack:
        read_budget = 128 * iq_stream.MIB
        stack.enter_context(
            patch.multiple(iq_stream, MAX_CHUNK_PREFIX=read_budget, MAX_DECODE_BYTES=read_budget)
        )
        for index, row in enumerate(lock["roster"][ident]):
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
            wide.verify(window, row, status)
            if not index:
                pair = templates(RATE, window.target["edge"])
                contexts = {
                    k: stack.enter_context(
                        NativeShortWindow(path, *pair, sample_rate_hz=RATE, fractional_epoch=True)
                    )
                    for k, path in lock["release"]["paths"].items()
                }
                profiles = {k: profiler(ctx) for k, ctx in contexts.items()}
                for ctx in contexts.values():
                    ctx.analyze(window.samples)
            if status != "processed":
                output.append(row)
                continue
            data = measure(window.samples, contexts, profiles, index)
            if data["payload_sha256"]["control"] != row["reference_payload_sha256"]:
                raise ValueError("fresh stock detector differs from the authenticated raw control")
            output.append(dict(row, **data))
            if ident in wide.PANEL and not diagnostic:
                diagnostic = {
                    name: dict(
                        planted=tones,
                        iq_sha256=_digest(sample.tobytes()),
                        **measure(sample, contexts, profiles, i),
                    )
                    for i, (name, tones, sample) in enumerate(controls(window))
                }
    return dict(
        id=ident,
        cpu=sorted(os.sched_getaffinity(0)),
        lock_sha256=_digest(encoded(lock)),
        rows=output,
        controls=diagnostic,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=("freeze", *CASES))
    p.add_argument("--work", type=local_output, default=WORK)
    a = p.parse_args()
    target = REPORT / "source-lock.json"
    if a.stage == "freeze":
        if target.exists():
            raise ValueError("wide preparation visit schedule already sealed")
        save_json(target, freeze(a.work))
        return
    lock = json.loads(target.read_bytes())
    if lock["release"] != release(a.work) or any(
        _sha(ROOT / p) != h for p, h in lock["inputs"].items()
    ):
        raise ValueError("qualified source, roster, or ELF changed")
    data = replay(a.stage, lock)
    write(REPORT / f"{a.stage}.json.gz", gzip.compress(encoded(data), mtime=0))


if __name__ == "__main__":
    main()
