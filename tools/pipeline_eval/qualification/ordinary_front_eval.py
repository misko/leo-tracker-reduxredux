"""Compare the ordinary detector and its Cortex-A9 cross-build on the same saved windows."""

import argparse
import gzip
import json
import subprocess
from contextlib import ExitStack
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import perf_counter, process_time

import numpy as np

from ..__main__ import ROOT, encoded, local_output, write
from . import ordinary_front_build, spectral_grid_eval
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import NATIVE_LIBRARY, PRODUCERS, _bind_producer, _load_case, _sha
from .pilot_kernel_eval import _digest, _windows
from .refine_bank_eval import _noise

REPORT = ROOT / "reports/2026_11_19_receiver_screening/redesign/ordinary-front"
METHOD = "ordinary_front"
SCHEDULE = ((6, (0, 2, 5, 7)), (11, (0, 2, 5, 7)))
MODES = ("control", METHOD)
RATE = 10_000_000


def sources():
    paths = (
        Path(__file__),
        Path(ordinary_front_build.__file__),
        ordinary_front_build.HEADER,
        REPORT / "PROTOCOL.md",
    )
    return {p.name: _sha(p) for p in paths}


def _payload(document):
    return {
        k: (
            [{name: val for name, val in r.items() if name != "timings_ms"} for r in v]
            if k == "rows"
            else v
        )
        for k, v in document.items()
        if k not in {"detector_cpu_ms", "timings_ms"}
    }


def positive(document):
    return [
        [
            (
                rank,
                c["epoch"],
                c["fractional_epoch"]["tracking_cfo_hz"],
                c["fractional_epoch"]["margin"],
            )
            for rank, c in enumerate(r["candidates"])
            if c["fractional_epoch"]["status"] == "complete"
            and c["fractional_epoch"]["margin"] >= 0.025
        ]
        for r in document["rows"]
    ]


def benchmark(samples, call, index, repeats):
    clocks, output, stable = {m: [] for m in MODES}, {}, True
    for rep in range(repeats):
        order = MODES if (rep + index) % 2 == 0 else MODES[::-1]
        for mode in order:
            q, extra = call(samples, mode)
            result = _payload(q)
            stable &= result == output.setdefault(mode, result)
            row_timings = [r["timings_ms"] for r in q["rows"]]
            clocks[mode].append(
                dict(
                    extra,
                    detector_cpu_ms=q.get(
                        "detector_cpu_ms", q.get("timings_ms", {}).get("detector_cpu")
                    ),
                    rows=row_timings,
                )
            )
    return dict(
        exact=stable and encoded(output[MODES[0]]) == encoded(output[MODES[1]]),
        stable=stable,
        timings=clocks,
        payloads=output,
        positives={m: positive(d) for m, d in output.items()},
        payload_sha256={m: _digest(encoded(d)) for m, d in output.items()},
    )


def replay(ident, work, arch):
    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    case, policy = _load_case(ident), FastScanPolicyV2()
    producer = _bind_producer(case, PRODUCERS[ident], policy)
    windows = [
        (segment, w) for segment, sequences in SCHEDULE for w in _windows(case, segment, sequences)
    ]
    edge = windows[0][1].target["edge"]
    exact = np.asarray(qin_edge_pilot_frame(RATE, edge), dtype="<c16")
    template = np.asarray(
        qin_edge_pilot_frame(RATE, edge, symbol_roll=CONTROL_SYMBOL_ROLL), dtype="<c16"
    )
    folder = work / f"{ident}-{arch}-input"
    folder.mkdir(exist_ok=False)
    paths = {"control": NATIVE_LIBRARY, METHOD: work / "host/libleo-adaptive-detector.so"}
    with ExitStack() as stack:
        if arch == "host":
            contexts = {
                mode: stack.enter_context(
                    NativeShortWindow(
                        str(path),
                        exact,
                        template,
                        sample_rate_hz=RATE,
                        fractional_epoch=True,
                    )
                )
                for mode, path in paths.items()
            }

            def call(samples, mode):
                wall, cpu = perf_counter(), process_time()
                row = contexts[mode].analyze(samples, include_timings=True)
                return row, dict(wall_s=perf_counter() - wall, host_cpu_s=process_time() - cpu)

        else:
            receipt = json.loads(
                (ordinary_front_build.ARM_CONTROL / "build-receipt.json").read_bytes()
            )
            sysroot = Path(receipt["fftw_double_library"]).parents[2]
            executable = "leo-native-glrt-short-window"
            paths = {
                "control": ordinary_front_build.ARM_CONTROL / executable,
                METHOD: work / "arm" / executable,
            }
            exact.tofile(folder / "exact.c128")
            template.tofile(folder / "control.c128")

            def call(samples, mode):
                sample_path, rss_path = folder / "window.ci16", folder / "rss.txt"
                samples.tofile(sample_path)
                args = [
                    "/usr/bin/time",
                    "-f",
                    "%M",
                    "-o",
                    str(rss_path),
                    "qemu-arm",
                    "-cpu",
                    "cortex-a9",
                    "-L",
                    str(sysroot),
                    str(paths[mode]),
                    "--rate-hz",
                    str(RATE),
                    "--fractional-epoch",
                    "--exact-template",
                    str(folder / "exact.c128"),
                    "--control-template",
                    str(folder / "control.c128"),
                    "--input-ci16",
                    str(sample_path),
                ]
                wall = perf_counter()
                p = subprocess.run(args, check=True, capture_output=True, timeout=10)
                return json.loads(p.stdout), dict(
                    wall_s=perf_counter() - wall, emu_peak_kib=int(rss_path.read_text())
                )

        rows, controls = [], {}
        first = None
        for index, (segment, window) in enumerate(windows):
            result = analyze_window(
                window,
                window.receiver_ids,
                None,
                policy,
                detector=lambda _w, ids: tuple(
                    FastScanReceiverV1(receiver_id=r, candidates=()) for r in ids
                ),
            )
            if result.status == "processed":
                first = window if first is None else first
                output = benchmark(window.samples, call, index, 3 if arch == "host" else 1)
            else:
                output = {}
            rows.append(
                dict(
                    output,
                    visit=result.visit,
                    segment=segment,
                    sequence=window.sequence,
                    status=result.status,
                    iq_sha256=window.iq_sha256,
                )
            )
            print(ident, arch, result.visit, result.status, output.get("exact"), flush=True)
        empty, _ = spectral_grid_eval._synthetic(first)["empty"]
        inputs = dict(
            empty=empty,
            noise=_noise(first),
            faint=_test_signal(first, ((735, 48_000, 128),), 830819),
        )
        for name, window in inputs.items():
            controls[name] = dict(benchmark(window.samples, call, 0, 1), iq_sha256=window.iq_sha256)
    return dict(
        case=ident,
        arch=arch,
        producer=producer,
        rows=rows,
        controls=controls,
        executable_sha256={m: _sha(path) for m, path in paths.items()},
        paired_resident_peak_kib=getrusage(RUSAGE_SELF).ru_maxrss,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=PRODUCERS, required=True)
    parser.add_argument("--arch", choices=("host", "arm"), required=True)
    parser.add_argument("--work", required=True, type=Path)
    args = parser.parse_args()
    frozen = sources()
    if (REPORT / "source-lock.json").read_bytes() != encoded(frozen) + b"\n":
        raise ValueError("The scoring sources differ from the fixed study lock")
    receipt = replay(args.case, local_output(args.work), args.arch)
    if sources() != frozen:
        raise ValueError("The scoring sources changed during the held replay")
    write(REPORT / f"{args.case}-{args.arch}.json.gz", gzip.compress(encoded(receipt), mtime=0))


if __name__ == "__main__":
    main()
