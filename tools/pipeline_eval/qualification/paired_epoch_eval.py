"""Compare per-lane positive recall and timing of the paired proposal union."""

import argparse
import ctypes as ct
import gzip
import json
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter, process_time

import numpy as np

from leo.analysis.starlink.native_short_window import NativeShortWindow

from ..__main__ import encoded, save_json, write
from ..variants import paired_epoch_overlay, paired_peaks
from . import capture_release
from . import paired_epoch_build as build
from . import wide_regional_eval as wide
from .cold_input import load
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import (
    _from_native,
    _load_case,
    _probe,
    _sha,
    compare_probes,
)
from .ordinary_front_eval import _payload, positive
from .pilot_kernel_eval import _windows

CASES = ("DS26-0036", "DS29-0082", "DS26-0122", "DS29-0247")
SCHEDULE = ((4, (0, 2, 5, 7)), (10, (0, 2, 5, 7)))
MODES = ("wide", "off", "union")
RATE = 10_000_000
REPORT = build.REPORT


class Trace(ct.Structure):
    _fields_ = [
        ("own_counts", ct.c_int32 * 2),
        ("own_centers", (ct.c_int32 * 4) * 2),
        ("active_counts", ct.c_int32 * 2),
        ("active", (ct.c_int32 * 24) * 2),
        ("union_enabled", ct.c_int32),
    ]


def members(centers, frame):
    return sorted({k for c in centers for k in range(max(0, c - 1), min(frame, c + 2))})


def trace(context, enabled):
    fn = context._library.leo_native_glrt_paired_epoch_trace
    fn.argtypes, fn.restype = [ct.c_void_p, ct.POINTER(Trace)], ct.c_int
    result = Trace()
    context._check(fn(context._context, ct.byref(result)))
    assert bool(result.union_enabled) == enabled
    own = [list(a[:n]) for a, n in zip(result.own_centers, result.own_counts, strict=True)]
    active = [list(a[:n]) for a, n in zip(result.active, result.active_counts, strict=True)]
    frame = round(context.sample_rate_hz / 750)
    union = members(own[0] + own[1], frame)
    assert active == ([union, union] if enabled else [members(a, frame) for a in own])
    return dict(own=own, active=active)


def contexts(stack, edge, rate=RATE, receivers=2):
    pair = wide.templates(rate, edge)
    r = json.loads((REPORT / "build.json").read_bytes())
    if (
        _sha(Path(r["library"])) != r["sha256"]
        or _sha(Path(r["wide_library"])) != build.BASE_SHA256
    ):
        raise ValueError("measured native files differ from paired-epoch build authority")
    bound = {
        mode: stack.enter_context(
            NativeShortWindow(
                r["wide_library" if mode == "wide" else "library"],
                *pair,
                sample_rate_hz=rate,
                receiver_count=receivers,
                fractional_epoch=True,
            )
        )
        for mode in MODES
    }
    if receivers == 2:
        off = bound["off"]
        fn = off._library.leo_native_glrt_paired_epoch_mode
        fn.argtypes, fn.restype = [ct.c_void_p, ct.c_int], ct.c_int
        off._check(fn(off._context, 0))
    return bound


def measure(bound, samples, index, repeats):
    timing = {m: [] for m in MODES}
    rows, traces = {}, {}
    paired = bound["union"].sample_rate_hz == RATE and bound["union"].receiver_count == 2
    for k in range(repeats):
        shift = (index + k) % len(MODES)
        for mode in MODES[shift:] + MODES[:shift]:
            ctx = bound[mode]
            wall, cpu = perf_counter(), process_time()
            measured = ctx.analyze(samples, include_timings=True)
            timing[mode].append(
                dict(
                    wall_s=perf_counter() - wall,
                    cpu_s=process_time() - cpu,
                    native_cpu_ms=measured["detector_cpu_ms"],
                )
            )
            value = _payload(measured)
            if value != rows.setdefault(mode, value):
                raise ValueError("same-IQ native output changed on repeat")
            if paired and mode != "wide":
                meta = trace(ctx, mode == "union")
                if meta != traces.setdefault(mode, meta):
                    raise ValueError("same-IQ proposal trace changed on repeat")
    if encoded(rows["off"]) != encoded(rows["wide"]) or (
        paired and traces["off"]["own"] != traces["union"]["own"]
    ):
        raise ValueError("disabling union changed the original wide results or own scouts")
    return rows, traces, timing


def canary():
    out = []
    for edge, sign in (("lower", 1), ("upper", -1)):
        window = wide.synthetic(RATE, edge, 1)
        with ExitStack() as stack:
            bound = contexts(stack, edge)
            strong = _test_signal(window, ((735, sign * 688125, 640),), 80211).samples
            same_epoch = _test_signal(window, ((735, sign * 681751, 610),), 80212).samples
            shifted = _test_signal(window, ((772, sign * 681751, 610),), 80212).samples
            specimens = (
                ("identical-zero-delay", strong, strong, ((735, sign * 688125),) * 2),
                (
                    "independent-zero-delay",
                    strong,
                    same_epoch,
                    ((735, sign * 688125), (735, sign * 681751)),
                ),
                (
                    "independent-plus-37",
                    strong,
                    shifted,
                    ((735, sign * 688125), (772, sign * 681751)),
                ),
                (
                    "noise",
                    _test_signal(window, (), 80201).samples,
                    _test_signal(window, (), 80202).samples,
                    (),
                ),
            )
            for i, (label, left, right, planted) in enumerate(specimens):
                values = np.concatenate((left, right), axis=1)
                rows, traces, timing = measure(bound, values, i, 4)
                matched = {
                    mode: [
                        sum(abs(e - epoch) <= 2 and abs(c - hz) <= 1000 for _, e, c, _ in row)
                        for (epoch, hz), row in zip(planted, positive(v), strict=False)
                    ]
                    for mode, v in rows.items()
                }
                if planted and not all(all(a) for a in matched.values()):
                    raise ValueError("synthetic planted candidate is absent")
                if label == "identical-zero-delay":
                    assert encoded(rows["union"]) == encoded(rows["wide"])
                    assert traces["union"]["own"][0] == traces["union"]["own"][1]
                out.append(
                    dict(
                        edge=edge,
                        condition=label,
                        iq_sha256=wide._digest(values.tobytes()),
                        planted=planted,
                        matches=matched,
                        traces=traces,
                        positives={k: positive(v) for k, v in rows.items()},
                        timings=timing,
                        union_equal=encoded(rows["union"]) == encoded(rows["wide"]),
                    )
                )
            for dwell, stride in ((120, 10), (120, 120)):
                values = np.tile(np.concatenate((strong, shifted), axis=1), (dwell // 20, 1, 1))
                outputs = {k: batch(ctx, values, dwell, stride) for k, ctx in bound.items()}
                assert all(encoded(v) == encoded(outputs["wide"]) for v in outputs.values())
                out.append(
                    dict(
                        edge=edge,
                        parity=f"ordinary API {dwell}/{stride} ms",
                        rows=len(outputs["wide"]),
                    )
                )
    for rate, count in ((RATE, 1), (5_000_000, 2)):
        with ExitStack() as stack:
            bound = contexts(stack, "lower", rate, count)
            values = _test_signal(
                wide.synthetic(rate, "lower", count), ((235, 193450, 640),), 80254
            ).samples
            rows, _, _ = measure(bound, values, 0, 2)
            assert encoded(rows["union"]) == encoded(rows["wide"])
            out.append(dict(parity=f"{rate} Hz {count} RX", rows=count))
    return out


def batch(ctx, samples, dwell, stride):
    from leo.analysis.starlink.native_short_window import _ROW_COUNTS, _candidate, _Result

    fn = ctx._library.leo_native_glrt_analyze
    fn.argtypes = [
        ct.c_void_p,
        ct.POINTER(ct.c_int16),
        ct.c_size_t,
        ct.c_uint32,
        ct.c_uint32,
        ct.POINTER(_Result),
    ]
    fn.restype = ct.c_int
    output = _Result()
    ctx._check(
        fn(
            ctx._context,
            samples.ctypes.data_as(ct.POINTER(ct.c_int16)),
            len(samples),
            dwell,
            stride,
            ct.byref(output),
        )
    )
    return [
        dict(
            {k: getattr(r, k) for k in _ROW_COUNTS},
            candidates=[_candidate(c) for c in r.candidates[: r.candidate_count]],
        )
        for r in output.rows[: output.row_count]
    ]


def pair_delays(capture, requested):
    streams, status = paired_peaks.synchronized(capture, False)
    result, all_calibrations = {}, []
    for band in (0, 1):
        fitted = []
        for (channel, _), visits in streams.items():
            if int(channel > 4) != band:
                continue
            for visit, t, x, y in visits:
                i, j, de, df = paired_peaks.edges(x, y, capture.sample_rate_hz / 750)
                use = (x[i, 3] > 0) & (y[j, 3] > 0)
                if use.any():
                    fitted.append((t, visit, de[use], df[use]))
        law = paired_peaks.calibrate(fitted, capture.duration_s)
        all_calibrations.append(law)
        if law["supported"]:
            slice_ = [p for p in fitted if p[1] in requested]
            matches = paired_peaks.nearest(
                slice_, law["offset_hz"], law["drift_hz_per_s"], capture.duration_s / 2
            )
            result.update(
                {
                    int(v): dict(delta_rx1_minus_rx0_samples=float(e), residual_cfo_hz=float(r))
                    for _, v, e, r in matches
                }
            )
    return result, dict(status, calibration=all_calibrations)


def run(case):
    item = _load_case(case)
    captured = load(case)
    catalog = {(p["visit_index"], p["receiver_id"]): p for p in captured.probes}
    authority = capture_release.read_capture(item)
    release = capture_release.producer(item, authority)
    windows = [(s, w) for s, seq in SCHEDULE for w in _windows(item, s, seq)]
    delays, calibration = pair_delays(captured, {w.acquisition["global_visit"] for _, w in windows})
    rows = []
    with ExitStack() as stack:
        bound = contexts(stack, authority["edge"])
        for j, (s, w) in enumerate(windows):
            visit = w.acquisition["global_visit"]
            record = dict(
                segment=s,
                sequence=w.sequence,
                visit=visit,
                iq_sha256=w.iq_sha256,
                start_counter=w.acquisition["sample_start"],
                stereo_positive_delta=delays.get(visit),
            )
            if (
                w.sample_rate_hz != RATE
                or w.receiver_ids != (0, 1)
                or w.target["edge"] != authority["edge"]
            ):
                raise ValueError("window has unexpected raw receiver or pilot geometry")
            if not all((visit, rx) in catalog for rx in w.receiver_ids):
                if any((visit, rx) in catalog for rx in w.receiver_ids):
                    raise ValueError("capture-era archive disagrees on paired receiver scope")
                rows.append(record | dict(status="capture_excluded"))
                continue
            data, trace_rows, timings = measure(bound, w.samples, j, 4)
            comparisons = {}
            for mode in ("wide", "union"):
                detectors = data[mode]["rows"]
                if tuple(d["receiver_id"] for d in detectors) != w.receiver_ids:
                    raise ValueError("native output does not preserve raw receiver identity")
                comparisons[mode] = [
                    compare_probes(
                        catalog[visit, rx],
                        _probe(w, rx, (_from_native(i, c) for i, c in enumerate(d["candidates"]))),
                        w.sample_rate_hz,
                    )
                    for rx, d in zip(w.receiver_ids, detectors, strict=True)
                ]
            print(
                case,
                s,
                w.sequence,
                [len(a) for a in trace_rows["off"]["active"]],
                len(trace_rows["union"]["active"][0]),
                [[len(a["positive_matches"]) for a in comparisons[m]] for m in comparisons],
                flush=True,
            )
            rows.append(
                record
                | dict(
                    status="processed",
                    traces=trace_rows,
                    timings=timings,
                    payloads={k: v for k, v in data.items() if k != "off"},
                    payload_sha256={k: wide._digest(encoded(v)) for k, v in data.items()},
                    comparisons=comparisons,
                )
            )
    return dict(
        case=case,
        run_id=item["run_id"],
        input_manifest_sha256=authority["input_manifest_sha256"],
        native_sha256=captured.native_sha256,
        capture_release=str(release.root),
        rows=rows,
        stereo_calibration=calibration,
    )


def source_lock():
    paths = [
        Path(__file__),
        Path(build.__file__),
        paired_epoch_overlay.HEADER,
        Path(paired_epoch_overlay.__file__),
        Path(wide.__file__),
        REPORT / "PROTOCOL.md",
        REPORT / "build.json",
    ]
    return {p.name: _sha(p) for p in paths}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES)
    args = parser.parse_args()
    pins = source_lock()
    artifact = run(args.case) if args.case else canary()
    if pins != source_lock():
        raise ValueError("paired-epoch qualification source changed before sealing")
    if args.case:
        write(
            REPORT / f"{args.case}.json.gz",
            gzip.compress(encoded(dict(pins=pins, **artifact)), mtime=0),
        )
    else:
        save_json(REPORT / "canary.json", dict(pins=pins, cases=artifact))
