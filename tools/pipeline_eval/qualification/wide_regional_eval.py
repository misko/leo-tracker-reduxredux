"""Qualify prepared fractional release widths on saved windows and raw IQ canaries."""

import argparse
import ctypes as ct
import gzip
import json
import subprocess
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import iq_stream, wide_regional
from . import ordinary_front_build, ordinary_front_eval, wide_regional_build
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import PRODUCERS, _bind_producer, _load_case, _sha
from .pilot_kernel_eval import _digest, _windows

REPORT = ROOT / "reports/2026_11_19_receiver_screening/detector-origins/wide-regional"
RATE = 10_000_000
MODES = ("control", "wide")
SCHEDULE = tuple((s, (14, 18, 22, 26)) for s in (2, 7))
CHUNK_PREFIX = 48 * iq_stream.MIB


def templates(rate, edge):
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

    return tuple(
        np.asarray(qin_edge_pilot_frame(rate, edge, symbol_roll=r), dtype="<c16")
        for r in (0, CONTROL_SYMBOL_ROLL)
    )


def sources():
    paths = (
        Path(__file__),
        Path(wide_regional_build.__file__),
        Path(wide_regional.__file__),
        wide_regional.HEADER,
        Path(ordinary_front_eval.__file__),
        Path(iq_stream.__file__),
        REPORT / "PROTOCOL.md",
        ROOT / "src/leo/scanner/fast_scan_analysis.py",
    )
    return {p.name: _sha(p) for p in paths}


def validate(document, band):
    assert document["input_complex_times"] == document["sample_rate_hz"] // 50
    assert document["dwell_ms"] == 20 and len(document["rows"]) == document["receiver_count"]
    for row in document["rows"]:
        assert 0 <= row["candidate_count"] == len(row["candidates"]) <= 8
        for c in row["candidates"]:
            assert c["coarse_cfo_hz"] == -band + c["coarse_bin"] * 80_000
            assert abs(c["coarse_cfo_hz"]) <= band
            for key in ("fine_cfo_hz", "conditioned_cfo_hz", "acquired_cfo_hz"):
                if c[key] is not None:
                    assert abs(c[key]) <= band


def runner(stack, work, arch, rate, edge, label, receivers=2):
    from leo.analysis.starlink.native_short_window import NativeShortWindow

    pair = templates(rate, edge)
    paths, contexts = {}, {}
    for mode in MODES:
        base = work / (mode if arch == "host" else f"arm-{mode}")
        if arch == "host":
            paths[mode] = base / wide_regional_build.LIBRARY
            contexts[mode] = stack.enter_context(
                NativeShortWindow(
                    str(paths[mode]),
                    *pair,
                    sample_rate_hz=rate,
                    receiver_count=receivers,
                    fractional_epoch=True,
                )
            )
        else:
            paths[mode] = base / "leo-native-glrt-short-window"
    if arch == "host":

        def call(samples, mode):
            wall, cpu = perf_counter(), process_time()
            result = contexts[mode].analyze(samples, include_timings=True)
            return result, dict(wall_s=perf_counter() - wall, host_cpu_s=process_time() - cpu)
    else:
        folder = work / f"{label}-arm-input"
        folder.mkdir(exist_ok=False)
        exact, control = (folder / name for name in ("exact.c128", "control.c128"))
        for a, b in zip(pair, (exact, control), strict=True):
            a.tofile(b)
        receipt = json.loads((ordinary_front_build.ARM_CONTROL / "build-receipt.json").read_bytes())
        sysroot = Path(receipt["fftw_double_library"]).parents[2]

        def call(samples, mode):
            iq, rss = folder / "input.ci16", folder / "rss.txt"
            samples.tofile(iq)
            argv = [
                "/usr/bin/time",
                "-f",
                "%M",
                "-o",
                str(rss),
                "qemu-arm",
                "-cpu",
                "cortex-a9",
                "-L",
                str(sysroot),
                str(paths[mode]),
                "--rate-hz",
                str(rate),
                "--fractional-epoch",
                "--exact-template",
                str(exact),
                "--control-template",
                str(control),
                "--input-ci16",
                str(iq),
            ]
            start = perf_counter()
            proc = subprocess.run(argv, check=True, capture_output=True, timeout=15)
            return json.loads(proc.stdout), dict(
                wall_s=perf_counter() - start, emu_peak_kib=int(rss.read_text())
            )

    return call, paths, contexts


def benchmark(samples, call, index, reps):
    with patch.object(ordinary_front_eval, "MODES", MODES):
        result = ordinary_front_eval.benchmark(samples, call, index, reps)
    for mode, document in result["payloads"].items():
        band = 800_000 if mode == "wide" and document["sample_rate_hz"] == RATE else 400_000
        validate(document, band)
    return result


def synthetic(rate, edge, receivers=2):
    return iq_stream.IQWindow(
        0,
        np.empty((rate // 50, receivers, 2), dtype="<i2"),
        tuple(range(receivers)),
        rate,
        {"actual_if_center_hz": 0},
        "wide-regional-canary",
        {"edge": edge, "rf_center_hz": 0, "lnb_lo_hz": 0},
        "",
    )


def long_payload(context, samples):
    from leo.analysis.starlink.native_short_window import _ROW_COUNTS, _candidate, _Result

    analyze = context._library.leo_native_glrt_analyze
    analyze.argtypes = [
        ct.c_void_p,
        ct.POINTER(ct.c_int16),
        ct.c_size_t,
        ct.c_uint32,
        ct.c_uint32,
        ct.POINTER(_Result),
    ]
    analyze.restype = ct.c_int
    result = _Result()
    context._check(
        analyze(
            context._context,
            samples.ctypes.data_as(ct.POINTER(ct.c_int16)),
            len(samples),
            120,
            120,
            ct.byref(result),
        )
    )
    assert result.row_count == 2
    return [
        dict(
            {k: getattr(r, k) for k in _ROW_COUNTS},
            candidates=[_candidate(c) for c in r.candidates[: r.candidate_count]],
        )
        for r in result.rows[: result.row_count]
    ]


def canary(work, arch):
    results = []
    for edge, sign in (("lower", 1), ("upper", -1)):
        original = synthetic(RATE, edge)
        with ExitStack() as stack:
            call, paths, contexts = runner(stack, work, arch, RATE, edge, f"canary-{edge}")
            for j, f in enumerate((688_125, 799_875, 800_000, 810_000)):
                f *= sign
                plant = _test_signal(original, ((735, f, 640),), 80293 + j)
                measured = benchmark(plant.samples, call, j, 1)
                matches = {
                    mode: [
                        sum(abs(x[1] - 735) <= 2 and abs(x[2] - f) < 1000 for x in row)
                        for row in measured["positives"][mode]
                    ]
                    for mode in MODES
                }
                if j < 3:
                    assert all(matches["wide"]) and not any(matches["control"])
                results.append(
                    dict(
                        edge=edge,
                        planted_hz=f,
                        matches=matches,
                        iq_sha256=plant.iq_sha256,
                        iq_bytes=plant.samples.nbytes,
                        vote=measured,
                    )
                )
            if arch == "host":
                low = _test_signal(original, ((735, 111_177 * sign, 640),), 80251).samples
                long = np.zeros((RATE * 120 // 1000, 2, 2), dtype="<i2")
                long[: len(low)] = low
                pair = {m: long_payload(ctx, long) for m, ctx in contexts.items()}
                assert encoded(pair["control"]) == encoded(pair["wide"])
                results.append(
                    dict(
                        edge=edge,
                        parity="10 MS/s 120 ms after wide short",
                        sha256=_digest(encoded(pair["wide"])),
                        iq_bytes=long.nbytes,
                    )
                )
                # Restore the wide branch after the ordinary dwell on the same native context.
                restored = benchmark(plant.samples, call, 0, 1)
                assert restored["payload_sha256"] == measured["payload_sha256"]
            else:
                empty = np.zeros((RATE // 50, 2, 2), dtype="<i2")
                results.append(
                    dict(edge=edge, condition="empty", vote=benchmark(empty, call, 0, 1))
                )
    if arch == "host":
        for rate in (2_500_000, 5_000_000, 7_500_000):
            for receivers in (1, 2):
                window = synthetic(rate, "lower", receivers)
                test = _test_signal(window, ((235, 193_450, 640),), 80153)
                with ExitStack() as stack:
                    call, _, _ = runner(stack, work, arch, rate, "lower", "parity", receivers)
                    result = benchmark(test.samples, call, 0, 1)
                assert result["exact"] and any(result["positives"]["control"])
                results.append(
                    dict(
                        parity=f"{rate} short-window narrow {receivers} RX",
                        sha256=result["payload_sha256"]["wide"],
                    )
                )
    return dict(results=results, executable_sha256={m: _sha(p) for m, p in paths.items()})


def replay(case_id, work, arch):
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    case, policy = _load_case(case_id), FastScanPolicyV2()
    producer = _bind_producer(case, PRODUCERS[case_id], policy)
    with patch.object(iq_stream, "MAX_CHUNK_PREFIX", CHUNK_PREFIX):
        windows = [w for s, sequences in SCHEDULE for w in _windows(case, s, sequences)]
    rows = []
    with ExitStack() as stack:
        call, paths, _ = runner(stack, work, arch, RATE, windows[0].target["edge"], case_id)
        for i, window in enumerate(windows):
            result = analyze_window(
                window,
                window.receiver_ids,
                None,
                policy,
                detector=lambda _w, ids: tuple(
                    FastScanReceiverV1(receiver_id=r, candidates=()) for r in ids
                ),
            )
            measured = (
                benchmark(window.samples, call, i, 5 if arch == "host" else 1)
                if result.status == "processed"
                else {}
            )
            rows.append(
                dict(
                    measured,
                    visit=result.visit,
                    status=result.status,
                    iq_bytes=window.samples.nbytes,
                    iq_sha256=window.iq_sha256,
                )
            )
    return dict(
        case=case_id,
        arch=arch,
        rows=rows,
        producer=producer,
        executable_sha256={m: _sha(p) for m, p in paths.items()},
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--case", choices=PRODUCERS)
    cli.add_argument("--arch", choices=("host", "arm"), required=True)
    cli.add_argument("--work", type=Path, default=wide_regional_build.ROOT)
    opts = cli.parse_args()
    work = local_output(opts.work)
    frozen = sources()
    if json.loads((REPORT / "source-lock.json").read_bytes()) != frozen:
        raise ValueError("Widened regional qualification source changed")
    output = replay(opts.case, work, opts.arch) if opts.case else canary(work, opts.arch)
    if sources() != frozen:
        raise ValueError("Widened regional qualification source changed during replay")
    if opts.case:
        path = REPORT / f"{opts.case}-{opts.arch}.json.gz"
        write(path, gzip.compress(encoded(output), mtime=0))
    else:
        save_json(REPORT / f"canary-{opts.arch}.json", output)
